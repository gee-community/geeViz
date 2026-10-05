"""
geeViz MCP Server -- execution and introspection tools for Earth Engine via geeViz.

Unlike static doc snippets, this server executes code, inspects live GEE assets,
and dynamically queries API signatures. 12 tools.
"""
from __future__ import annotations

import os
import sys
print('Importing geeViz MCP Server from', __file__, file=sys.stderr, flush=True)
# ---------------------------------------------------------------------------
# CLI argument parsing (before heavy imports so --help is instant)
# ---------------------------------------------------------------------------
_SANDBOX_ENABLED: bool | None = None  # will be resolved in main()
_audit_user_code_active = False  # True only during user code execution in sandbox

# Parse --sandbox / --no-sandbox early so _help can document them
for _arg in sys.argv[1:]:
    if _arg == "--sandbox":
        _SANDBOX_ENABLED = True
        os.environ["GEEVIZ_SANDBOX"] = "1"
    elif _arg == "--no-sandbox":
        _SANDBOX_ENABLED = False

# ---------------------------------------------------------------------------
# Load the heavy C-extension stack HERE: single-threaded, and before the
# audit hook exists.
#
# numpy and pandas are imported later anyway, by the geeViz cascade in
# _ensure_initialized (outputLib.charts -> pandas -> numpy). Doing it
# there means a Windows DLL load (LoadLibraryExW, which takes the
# process-wide loader lock) happens while other threads are running and
# with an audit hook firing on every file access inside the import.
# That combination wedged the server: stack dumps caught it repeatedly,
# always parked in ``numpy/_core/multiarray.py`` inside
# ``create_module``, with the tool call that triggered it never
# returning and nothing logged.
#
# Up here there is exactly one thread and no hook, which is the same
# situation as ``python -c "import pandas"`` — which completes in 1.2s
# in the very venv where the in-server import hangs.
#
# Cost: ~1.5s of startup that was going to be paid on the first tool
# call regardless. Failures are non-fatal — if these are not installed
# the later import raises where it always did.
try:
    import numpy as _numpy_preload   # noqa: F401
    import pandas as _pandas_preload  # noqa: F401
except Exception as _preload_err:    # pragma: no cover - env dependent
    print(f"[geeViz MCP] numpy/pandas preload skipped: {_preload_err!r}",
          file=sys.stderr, flush=True)

# ---------------------------------------------------------------------------
# Audit hook — runtime-level defense that cannot be bypassed from Python.
# Catches os.system, subprocess.Popen, open(), exec(), import of blocked
# modules, etc. even when accessed via module attribute traversal
# (e.g. gv.os.system). Only active when --sandbox is set.
# ---------------------------------------------------------------------------
if _SANDBOX_ENABLED:
    _AUDIT_BLOCKED_IMPORTS = frozenset({
        # ── Filesystem / process control ──
        "os", "subprocess", "shutil", "pathlib", "tempfile", "glob",
        "mmap", "fcntl", "msvcrt", "resource", "signal",
        # ── Networking (any form) ──
        "socket", "http", "urllib", "requests", "ssl", "asyncio",
        # Kept in sync with _BLOCKED_MODULES — see the note there about
        # urllib3 making a real outbound request while requests was
        # blocked.
        "urllib3", "httpx", "httpcore", "h11", "h2", "hpack",
        "aiohttp", "aiohappyeyeballs", "aiosignal", "yarl",
        "httplib2", "websocket", "websockets", "curl_cffi", "socks",
        "socketserver",
        "select", "selectors", "smtplib", "ftplib", "poplib", "imaplib",
        "telnetlib", "nntplib", "xmlrpc",
        # ── Concurrency (indirect subprocess vectors) ──
        "threading", "multiprocessing",
        # ── Code execution / dynamic import bypasses ──
        # importlib.import_module("os") would sidestep static import checks;
        # marshal.loads on untrusted bytecode = arbitrary code exec;
        # runpy runs a module as __main__; zipimport imports from a zip
        # blob the attacker can construct via base64 → tempfile → import.
        "importlib", "marshal", "runpy", "zipimport", "builtins",
        "code", "codeop", "compileall", "py_compile",
        # ── Introspection (secret discovery in memory) ──
        # gc.get_objects() enumerates every live Python object — API keys,
        # session cookies, DB connection strings.  inspect.getsource on a
        # trusted-lib function could reveal internal secrets or an admin
        # code path the attacker hasn't discovered yet.
        "gc", "inspect", "dis", "traceback",
        # ── Archive libraries — file-extraction path traversal (zip slip) ──
        "zipfile", "tarfile", "gzip", "bz2", "lzma",
        # ── Serialization — unpickling can execute arbitrary code ──
        "pickle", "shelve", "dbm", "sqlite3",
        # ── Misc high-risk ──
        "pty", "pipes", "webbrowser", "getpass",
    })
    # Safe dotted submodules under otherwise-blocked top-levels. These are
    # stdlib housekeeping imports (locks, cleanup callbacks, event contexts)
    # that PIL / numpy / matplotlib / kaleido lazy-import as side effects of
    # legitimate library use. They don't spawn processes, open sockets, or
    # write files — blocking them breaks any user code that renders/saves
    # imagery. Dangerous surfaces (multiprocessing.Process, .Pool, .spawn,
    # os.system, subprocess.Popen) are still blocked because they require
    # the parent top-level import or a syscall audit event.
    _AUDIT_ALLOWED_SUBMODULES = frozenset({
        "multiprocessing.resource_tracker",
        "multiprocessing.util",
        "multiprocessing.context",
        "multiprocessing.reduction",
        "multiprocessing.synchronize",
        "urllib.parse",  # PIL and pandas parse URLs to sniff schemes
        "http.client",   # transient in some SSL init paths
    })
    # Track whether we're inside the server's own init (allow) or user code (block)
    _audit_user_code_active = False

    def _called_from_trusted_lib():
        """True ONLY if the call is from inside trusted library code with NO user
        code frame between the call site and the trusted frame.

        Walks the stack from the syscall site upward:
        - If we hit user code (filename '<mcp>') before any trusted frame → DENY
        - If we hit a trusted frame first → ALLOW
        - stdlib/site-packages frames are skipped (transparent)

        This prevents the exploit where user code passes a callback to a trusted
        function that calls back into user code which tries the syscall — that
        callback's user frame would be above the trusted frame, so it's denied.
        """
        import inspect as _ins
        # Substrings identifying trusted callers. User code lives in
        # ``<mcp>`` frames (compiled by the sandbox with that filename),
        # so anything installed as a third-party package under
        # ``site-packages`` is by definition NOT user code. Broad match
        # on ``site-packages`` covers numpy / pandas / matplotlib /
        # scikit-learn / any legit dep the tenant installs — their
        # internal marshal.loads / socket / etc. calls at import time
        # aren't attacker-controlled. Named entries left for clarity.
        _trusted_substrings = (
            "site-packages",
            # Frozen stdlib bootstrap frames — importlib itself loads cached
            # .pyc bytecode via marshal.loads, so any legitimate ``import X``
            # triggers this audit event with importlib._bootstrap on top.
            # Attacker can't write to disk (open is blocked) so can't seed a
            # bad .pyc — the bytecode is only whatever's already in the
            # sandbox's file system.
            "<frozen ",
            # Whole geeViz package tree is trusted — googleMapsLib, esriLib,
            # getImagesLib, changeDetectionLib, outputLib, all of it. These
            # modules legitimately open sockets / call urllib / spawn kaleido
            # to fulfill their documented tool contract (Street View HTTPS,
            # ESRI Feature Service HTTPS, EE tile fetches, chart export).
            # Matching just ``geeViz\outputLib`` (as before) broke every
            # other library. User code is still blocked FIRST at line 123
            # via the ``<mcp>`` check, so trusting the geeViz tree does NOT
            # let user code smuggle syscalls in — a ``<mcp>`` frame ABOVE
            # the geeViz frame denies the call before this list is consulted.
            "geeviz\\", "geeviz/",
            "kaleido", "plotly",
        )
        # server.py's OWN frames are neither user code nor a trusted lib —
        # they're the sandbox itself. Must be skipped in the walk, otherwise
        # the ``geeviz\`` trusted substring would match server.py and every
        # audit call would appear to originate from a trusted frame. Match
        # by exact filename (case-insensitive) since __file__ is stable.
        _self_fname_lower = (__file__ or "").lower()
        # Also skip anything under ``geeviz/mcp/`` — helper modules that
        # ship with the server (e.g. workload_tags helpers) are part of
        # the sandbox, not the trusted library surface. This is defined
        # by path substring so it works whether we're running from a
        # dev checkout, a pip install, or a container.
        _sandbox_dir_marker_bwd = "geeviz\\mcp\\"
        _sandbox_dir_marker_fwd = "geeviz/mcp/"
        try:
            f = _ins.currentframe()
            while f is not None:
                fname = (f.f_code.co_filename or "")
                fname_lower = fname.lower()
                # Skip the sandbox's own frames — they're neither user code
                # nor trusted library code; they're the enforcer.
                if (
                    fname_lower == _self_fname_lower
                    or _sandbox_dir_marker_bwd in fname_lower
                    or _sandbox_dir_marker_fwd in fname_lower
                ):
                    f = f.f_back
                    continue
                # User code lives in '<mcp>' frames (from exec(compile(..., '<mcp>')))
                if "<mcp>" in fname or "<string>" in fname:
                    return False  # User code is closer than any trusted lib → deny
                if any(s.lower() in fname_lower for s in _trusted_substrings):
                    return True
                f = f.f_back
        except Exception:
            pass
        # Walked the whole stack with no '<mcp>' user frame anywhere → this
        # call chain isn't user-initiated (it's the server itself invoking
        # compile()/marshal.load()/etc. to *set up* running user code, or
        # a thread-bootstrap frame we haven't marked trusted). Trust it.
        # Any real user code path would put '<mcp>' on the stack before
        # any syscall audit fires. This is what lets ``run_code``'s own
        # ``compile(code, '<mcp>', 'exec')`` inside the sandbox thread
        # succeed — without this default-allow, the compile audit hook
        # blocks the SERVER's compile and silently kills every run_code
        # (empty stdout, no namespace mutation, no file writes).
        return True

    def _connect_refusal(args):
        """Why this socket.connect must be refused even from trusted code,
        or None.

        Everything under site-packages is "trusted" -- which includes
        georest, a full HTTP client. So user code could call
        ``georest.restesri._http.fetch_json("http://169.254.169.254/...")``
        and read the instance's service-account token: georest has no
        SSRF policy, and geeViz's ``_ssrf.check_url`` only guards geeViz's
        own helpers. Checked here, at the connect -- after DNS and after
        any redirect, so neither a rebinding name nor a 30x gets past it:

        * link-local (169.254/16, fe80::/10 -- where cloud metadata
          lives) is refused for ALL sandboxed code;
        * a connect made from georest code gets geeViz's full library
          policy (no loopback/private/link-local/reserved), the same one
          esriLib applies before delegating to it.

        Loopback stays open to other trusted libraries: kaleido talks to
        its own local Chromium over it.
        """
        try:
            import ipaddress as _ip
            addr = args[1] if len(args) > 1 else None
            host = addr[0] if isinstance(addr, tuple) and addr else None
            if not isinstance(host, str):
                return None
            ip = _ip.ip_address(host.split("%", 1)[0])
        except (ValueError, TypeError):
            return None
        if ip.is_link_local:
            return (f"Sandbox: connecting to {host} is blocked -- link-local "
                    f"addresses serve cloud metadata (credentials).")
        f = sys._getframe(2)
        while f is not None:
            fn = f.f_code.co_filename.replace("\\", "/").lower()
            if "/georest/" in fn:
                from geeViz._ssrf import _is_forbidden
                if _is_forbidden(str(ip)):
                    return (f"Sandbox: georest may not connect to {host} -- "
                            f"loopback, private and link-local addresses are "
                            f"refused, as geeViz.esriLib refuses them.")
                return None
            f = f.f_back
        return None

    def _sandbox_audit_hook(event, args):
        if not _audit_user_code_active:
            return  # Allow server's own operations
        if event == "import":
            mod_name = args[0].split(".")[0] if args[0] else ""
            if mod_name in _AUDIT_BLOCKED_IMPORTS:
                # Safe stdlib housekeeping submodules — see comment on
                # _AUDIT_ALLOWED_SUBMODULES. These are triggered as side
                # effects of PIL/numpy/matplotlib work, not user intent.
                if args[0] in _AUDIT_ALLOWED_SUBMODULES:
                    return
                # Allow trusted library code (e.g. kaleido inside cl.save_chart_png)
                if _called_from_trusted_lib():
                    return
                raise ImportError(
                    f"Sandbox: import of '{args[0]}' is blocked. "
                    f"Only Earth Engine, geeViz, and standard data libraries are allowed."
                )
        elif event == "os.system":
            if _called_from_trusted_lib():
                return
            raise PermissionError("Sandbox: os.system() is blocked.")
        elif event == "subprocess.Popen":
            if _called_from_trusted_lib():
                return
            raise PermissionError("Sandbox: subprocess is blocked.")
        elif event in ("os.exec", "os.posix_spawn", "os.spawn"):
            if _called_from_trusted_lib():
                return
            raise PermissionError(f"Sandbox: {event} is blocked.")
        elif event == "socket.connect":
            # Outbound network. Belt-and-suspenders over the module-level
            # block on ``socket`` — if user code somehow reaches a connect
            # via a trusted-lib import chain that shouldn't have leaked
            # sockets through, fail loud rather than silently exfiltrate.
            _why = _connect_refusal(args)
            if _why:
                raise PermissionError(_why)
            if _called_from_trusted_lib():
                return
            raise PermissionError("Sandbox: socket.connect is blocked.")
        elif event == "socket.gethostbyname":
            # DNS lookups by themselves are info leaks (attacker learns
            # what hostnames resolve from the tenant's egress) even
            # without a subsequent connect.
            if _called_from_trusted_lib():
                return
            raise PermissionError("Sandbox: socket.gethostbyname is blocked.")
        elif event == "urllib.Request":
            # Any urllib construction — the module is import-blocked but
            # this is a defense-in-depth catch in case a trusted lib
            # accidentally exposes a factory.
            if _called_from_trusted_lib():
                return
            raise PermissionError("Sandbox: urllib.Request is blocked.")
        elif event == "compile":
            # Dynamic bytecode compilation. The builtin ``compile`` is
            # already removed from the exec namespace, but a trusted-lib
            # chain that offers it would let user code craft arbitrary
            # code objects (and then hand them to a trusted eval).
            if _called_from_trusted_lib():
                return
            raise PermissionError("Sandbox: compile() is blocked.")
        elif event in ("marshal.load", "marshal.loads"):
            # Deserializing an untrusted marshal payload constructs
            # arbitrary Python code objects — full RCE. Module is import-
            # blocked but hook this event anyway.
            if _called_from_trusted_lib():
                return
            raise PermissionError(f"Sandbox: {event} is blocked.")
        elif event == "open":
            # Path-scoped file access. Original design: block deny-listed
            # paths REGARDLESS of caller so attackers couldn't smuggle
            # sensitive paths into trusted-lib helpers. But that broke a
            # legit path — ``google.auth`` reads ADC from
            # ``~/.config/gcloud/application_default_credentials.json``
            # during ``ee.Initialize()``, and on Cloud Run + Windows dev
            # boxes the ADC path matches ``/.gcloud/`` / ``/root/`` /
            # ``AppData\Roaming\gcloud\`` (the last only in local dev).
            # Blocking it turns EE init into a hard failure every session.
            #
            # Compromise: allow trusted-lib callers to read anything (they
            # need ADC, cert bundles, metadata files, tzdata, etc), but
            # keep the deny-list for user-initiated calls. Attackers that
            # tried ``pd.read_csv('/proc/self/environ')`` still get caught
            # because the walker sees the user's ``<mcp>`` frame above
            # pandas. Attackers that call ``open('/etc/shadow')`` directly
            # still get caught because <mcp> is the immediate caller.
            try:
                _p = args[0] if args else None
                _mode = args[1] if len(args) > 1 else None
                # Integer file descriptors (dup, fdopen) — allow.
                if isinstance(_p, int):
                    return
                if _p is None:
                    return
                # Trusted callers (google.auth reading ADC, ee reading
                # tzdata, plotly reading templates, etc.) bypass path
                # checks. The trust check already excludes user (<mcp>)
                # frames — so a user chain smuggling a bad path INTO a
                # trusted helper still trips the deny-list because the
                # walker returns False on the <mcp> frame it finds first.
                if _called_from_trusted_lib():
                    return
                # Normalize to a plain string for comparison.
                if isinstance(_p, bytes):
                    _p = _p.decode("utf-8", errors="replace")
                else:
                    _p = str(_p)
                _plow = _p.replace("\\", "/").lower()
                # ── DENY: sensitive files that no legit user code should
                # touch. We deliberately DO NOT list ``/.gcloud/`` /
                # ``/.config/gcloud/`` / ``/root/`` here — ADC lives
                # under those and google-auth is a trusted caller
                # (handled by the ``_called_from_trusted_lib`` skip
                # above). User code that tries to open ADC directly
                # would come in via ``<mcp>`` and get caught by the
                # trust walker returning False, then would fall through
                # to the deny-list below — but we don't need path-level
                # coverage since trust already blocks the user chain.
                _DENY_SUBSTRINGS = (
                    "/proc/self/environ", "/proc/self/status",
                    "/sys/kernel/", "/dev/mem", "/dev/kmem",
                    "/etc/shadow", "/etc/gshadow", "/etc/sudoers",
                    "/etc/ssh/", "/.ssh/", "/.gnupg/", "/.aws/",
                    "/.docker/config.json", "/.netrc", ".pgpass",
                    "/.env", ".env.local", ".env.prod", ".env.test",
                    "service-account",
                )
                for _bad in _DENY_SUBSTRINGS:
                    if _bad in _plow:
                        raise PermissionError(
                            f"Sandbox: file access to '{_p}' is blocked "
                            f"(sensitive path)."
                        )
                # ── Everything else — allow. Read-only access to arbitrary
                # paths is a data-leak surface but the module blocks on
                # net/socket/subprocess prevent exfiltration. Write access
                # is bounded by container filesystem perms (Cloud Run
                # runs unprivileged; can only write /tmp and its own
                # workspace). Tightening further (allowlist by session
                # output_dir) would break legit imports of encodings,
                # tzdata, cert bundles, plotly templates, etc.
            except PermissionError:
                raise
            except Exception:
                # Never let a broken check silently allow — but never
                # crash the audit hook either. Default to allow so
                # library imports don't break on odd path types.
                return

    sys.addaudithook(_sandbox_audit_hook)


# ---------------------------------------------------------------------------
# Tool-response credential scrubber — last line of defense before returning
# any tool output to the model. The sandbox blocks the DANGEROUS operations
# through os / socket / subprocess, but pure reads like ``os.environ`` /
# ``getenv`` don't fire audit events, so a determined caller could still
# dump env values into stdout, an exception message, or a returned dict.
# The scrubber intercepts those before they enter the model's context —
# once a secret is in the LLM turn, it lives in the events DB and gets
# replayed to Gemini on every subsequent call.
#
# Two-layer detection:
#   1. Literal replace on values of every "secret-shaped" os.environ var
#      (KEY / TOKEN / SECRET / PASSWORD / B64 / CREDENTIALS / DSN /
#      DATABASE_URL / SESSION_SIGNING_KEY, etc). Snapshotted once on
#      first call; matches even if the secret is embedded in JSON,
#      concatenated with other text, or repr()'d.
#   2. Regex for well-known credential shapes: Google API keys
#      (``AIza…``), PEM private-key blocks, service-account JSON
#      fields, JWTs, Stripe/OpenAI/GitHub/AWS token prefixes.
# ---------------------------------------------------------------------------
import re as _scrub_re

_SECRET_ENV_HINTS = (
    "KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "B64",
    "CREDENTIAL", "DSN", "DATABASE_URL", "SIGNING",
)
_SECRET_ENV_ALLOW = frozenset({
    # Named vars whose "value" is a public identifier, not a secret.
    "GEE_PROJECT", "GOOGLE_CLOUD_PROJECT", "GCP_PROJECT",
    "MODEL_ARMOR_PROJECT", "MODEL_ARMOR_LOCATION", "MODEL_ARMOR_TEMPLATE",
    "MCP_TRANSPORT", "MCP_HOST", "MCP_PORT", "MCP_PATH",
})

def _snapshot_env_secrets() -> list[tuple[str, str]]:
    """Return [(env_name, value), ...] for every env var that looks secret.

    Sorted longest-value-first so a replace of a container value doesn't
    leave a substring of a shorter, contained secret un-redacted. Values
    shorter than 8 chars are dropped — too high a false-positive rate on
    common short strings like ``true`` / ``0`` / ``dev``.
    """
    out: list[tuple[str, str]] = []
    for name, val in os.environ.items():
        if not val or len(val) < 8:
            continue
        upper = name.upper()
        if upper in _SECRET_ENV_ALLOW:
            continue
        if not any(h in upper for h in _SECRET_ENV_HINTS):
            continue
        out.append((name, val))
    out.sort(key=lambda kv: len(kv[1]), reverse=True)
    return out

# Snapshotted lazily on first scrub call — env may still be loading at
# module import time (dotenv, secret manager fetches, etc).
_ENV_SECRETS_CACHE: list[tuple[str, str]] | None = None
_ENV_SECRETS_LOADED_AT: float = 0.0

_CREDENTIAL_PATTERNS = (
    # Google API keys — AIzaSy prefix + 33 URL-safe chars = 39 total.
    (_scrub_re.compile(r"AIza[0-9A-Za-z_\-]{35}"), "[REDACTED-GOOGLE-API-KEY]"),
    # PEM private-key blocks (RSA / EC / DSA / ENCRYPTED / OPENSSH / plain).
    (_scrub_re.compile(
        r"-----BEGIN (?:RSA |EC |DSA |ENCRYPTED |OPENSSH )?PRIVATE KEY-----"
        r"[\s\S]*?"
        r"-----END (?:RSA |EC |DSA |ENCRYPTED |OPENSSH )?PRIVATE KEY-----"
    ), "[REDACTED-PEM-PRIVATE-KEY]"),
    # Service-account JSON field.
    (_scrub_re.compile(r'"private_key"\s*:\s*"[^"]+"'),
     '"private_key": "[REDACTED-SA-PRIVATE-KEY]"'),
    (_scrub_re.compile(
        r'"private_key_id"\s*:\s*"[0-9a-f]{20,}"'
    ), '"private_key_id": "[REDACTED-SA-KEY-ID]"'),
    # JWT (header.payload.sig) — three base64url chunks joined by dots.
    (_scrub_re.compile(
        r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"
    ), "[REDACTED-JWT]"),
    # Common third-party token prefixes.
    (_scrub_re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"), "[REDACTED-OPENAI-KEY]"),
    (_scrub_re.compile(r"\bsk_(?:test|live)_[A-Za-z0-9]{16,}\b"),
     "[REDACTED-STRIPE-KEY]"),
    (_scrub_re.compile(r"\bghp_[A-Za-z0-9]{36}\b"), "[REDACTED-GITHUB-PAT]"),
    (_scrub_re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
     "[REDACTED-SLACK-TOKEN]"),
    (_scrub_re.compile(r"\bAKIA[A-Z0-9]{16}\b"), "[REDACTED-AWS-KEY-ID]"),
)

def _scrub_credentials(text: str) -> str:
    """Redact env-var values and known credential shapes from ``text``.

    Safe to call on ``None`` / non-strings — returns input unchanged.
    Runs before any tool response is returned to the model. Cheap: literal
    replace + a handful of compiled regex; O(n * secrets) on the text
    length. For the 50k-char cap we already apply to stdout, worst case
    is ~sub-millisecond.
    """
    if not isinstance(text, str) or not text:
        return text
    global _ENV_SECRETS_CACHE, _ENV_SECRETS_LOADED_AT
    # Refresh the snapshot every 60s — tenants can rotate a secret via
    # Secret Manager and Cloud Run reloads env without a process restart.
    import time as _time
    now = _time.time()
    if _ENV_SECRETS_CACHE is None or (now - _ENV_SECRETS_LOADED_AT) > 60:
        _ENV_SECRETS_CACHE = _snapshot_env_secrets()
        _ENV_SECRETS_LOADED_AT = now
    scrubbed = text
    for name, val in _ENV_SECRETS_CACHE:
        if val in scrubbed:
            scrubbed = scrubbed.replace(val, f"[REDACTED-{name}]")
    for pat, repl in _CREDENTIAL_PATTERNS:
        scrubbed = pat.sub(repl, scrubbed)
    return scrubbed


def _scrub_json_response(payload) -> str:
    """Recursively scrub every string in a dict / list / scalar, then dump.

    Convenience wrapper used at every ``return json.dumps({...})`` site
    in the MCP tools so no field escapes the sanitizer (stdout, stderr,
    result, error, message, output_markdown, nested tool payloads, etc).
    """
    import json as _json

    def _walk(o):
        if isinstance(o, str):
            return _scrub_credentials(o)
        if isinstance(o, list):
            return [_walk(x) for x in o]
        if isinstance(o, tuple):
            return tuple(_walk(x) for x in o)
        if isinstance(o, dict):
            return {k: _walk(v) for k, v in o.items()}
        return o

    return _json.dumps(_walk(payload))


if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
    _help = """usage: python -m geeViz.mcp.server [--help] [--sandbox | --no-sandbox]

geeViz MCP Server -- execution and introspection for Earth Engine via geeViz.

Options:
  -h, --help      Show this help and exit.
  --sandbox       Force run_code sandbox ON (block os, open, eval, etc.)
  --no-sandbox    Force run_code sandbox OFF (full Python access)

  Default: sandbox is OFF for stdio transport (local IDE use) and ON for
  streamable-http when binding to non-localhost (remote/cloud deployment).

Environment (optional):
  MCP_TRANSPORT   Transport: "stdio" (default) or "streamable-http"
  MCP_HOST        Host for HTTP (default: 127.0.0.1)
  MCP_PORT        Port for HTTP (default: 8000)
  MCP_PATH        Path for HTTP (default: /mcp)

Tools:
  run_code                 Execute Python/GEE code in a persistent REPL namespace
  inspect_asset            Get metadata for any GEE asset (with optional collection filters)
  search_codebase          Search geeViz + any REPL module (ee, pandas, numpy, ...) by name, query, or module
  map_control              View, export, preview, list layers, clear, or test the geeView map (action=view|export|preview|layers|clear|test_layers)
  save_session             Save run_code history to a .py file or .ipynb notebook
  env_info                 Get versions, REPL namespace, or project info (action=version|namespace|project)
  view_output              Return a saved raster (PNG/GIF/JPEG/WebP) as an inline image (does NOT work on HTML)
  export_image             Export ee.Image to asset, Drive, or Cloud Storage (destination=asset|drive|cloud)
  search_datasets          Search the GEE dataset catalog by keyword
  manage_asset             Delete, copy, move, create folder, or update ACL (action=delete|copy|move|create|update_acl)

Examples:
  python -m geeViz.mcp.server                   # stdio, no sandbox (default)
  python -m geeViz.mcp.server --sandbox          # stdio with sandbox
  MCP_TRANSPORT=streamable-http python -m geeViz.mcp.server  # HTTP, auto-sandbox
  python -m geeViz.mcp --help

See also: geeViz/mcp/README.md
"""
    print(_help, file=sys.stderr)
    sys.exit(0)

import importlib.util

# Path setup: ensure geeViz and package root are on path
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))  # .../geeViz/mcp
_GEEVIZ_DIR = os.path.dirname(_THIS_DIR)               # .../geeViz
_PACKAGE_ROOT = os.path.dirname(_GEEVIZ_DIR)            # .../geeVizBuilder
_EXAMPLES_DIR = os.path.join(_GEEVIZ_DIR, "examples")
sys.path = [p for p in sys.path if not (p.rstrip(os.sep).endswith("mcp") and _GEEVIZ_DIR in (p or ""))]
if _PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, _PACKAGE_ROOT)
if _GEEVIZ_DIR not in sys.path:
    sys.path.append(_GEEVIZ_DIR)


# Load FastMCP from the MCP SDK. When run as python -m geeViz.mcp.server, the name "mcp"
# resolves to this package (geeViz.mcp), so we load the SDK's fastmcp by file from site-packages.
# If mcp is not installed (e.g. during Sphinx doc build), a lightweight stub is used so the
# module can still be imported and @app.tool() decorators pass functions through unchanged.
def _load_fastmcp():
    import site as _site
    for _sp in _site.getsitepackages():
        _origin = os.path.join(_sp, "mcp", "server", "fastmcp.py")
        if os.path.isfile(_origin):
            spec = importlib.util.spec_from_file_location("_geeviz_mcp_sdk_fastmcp", _origin)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod.FastMCP
    try:
        from mcp.server.fastmcp import FastMCP
        return FastMCP
    except ModuleNotFoundError:
        return None


class _StubFastMCP:
    """Lightweight stand-in when the mcp SDK is not installed.

    Makes @app.tool() a no-op passthrough so functions keep their real
    type and docstrings (important for Sphinx autodoc).
    """

    def __init__(self, *args, **kwargs):
        pass

    def tool(self, **kwargs):
        """Identity decorator so ``@app.tool(...)`` compiles at import time.

        Real FastMCP registers the function into the MCP tool registry;
        the stub just returns the function unchanged so ``help()`` and
        ``inspect.signature()`` still work.
        """
        def _identity(fn):
            return fn
        return _identity

    def resource(self, *args, **kwargs):
        """Identity decorator for ``@app.resource(...)`` — see ``tool()``."""
        def _identity(fn):
            return fn
        return _identity

    def run(self, **kwargs):
        """Raise a clear error when the MCP server is asked to actually run.

        The stub exists only to keep imports working; running requires the
        real ``mcp`` package.

        Raises:
            RuntimeError: Always — install ``mcp`` to run the server.
        """
        raise RuntimeError("mcp SDK not installed; install with: pip install mcp")


_FastMCP = _load_fastmcp()
FastMCP = _FastMCP if _FastMCP is not None else _StubFastMCP

# Load ToolAnnotations for hinting read-only / destructive / etc.
try:
    from mcp.types import ToolAnnotations
except ImportError:
    # Stub if mcp SDK not installed
    class ToolAnnotations:
        """Fallback ``ToolAnnotations`` when the ``mcp`` package is absent.

        Accepts any kwargs (readOnlyHint, destructiveHint, etc.) and stores
        nothing — the real class ships hints to MCP clients, this one just
        keeps decorator calls valid at import time.
        """
        def __init__(self, **kwargs): pass

# Pre-built annotation sets
_READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True)
_READ_ONLY_OPEN = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)
_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False)
_WRITE_OPEN = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
_DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)


def _load_mcp_image():
    """Load the Image class from the mcp SDK for returning images from tools.

    IMPORTANT: Try the direct import first so we get the exact same Image class
    that FastMCP uses internally. If we load from file (as a standalone module),
    the class identity differs and FastMCP's isinstance() check fails, causing
    images to not display in clients like Cursor.
    """
    # Preferred: direct import matches FastMCP's own Image class
    try:
        from mcp.server.fastmcp.utilities.types import Image
        return Image
    except (ImportError, ModuleNotFoundError, AttributeError):
        pass
    # Fallback: load from file in site-packages (older SDK layouts)
    import site as _site
    for _sp in _site.getsitepackages():
        _types_path = os.path.join(_sp, "mcp", "server", "fastmcp", "utilities", "types.py")
        if os.path.isfile(_types_path):
            try:
                spec = importlib.util.spec_from_file_location("_geeviz_mcp_types", _types_path)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    cls = getattr(mod, "Image", None)
                    if cls is not None:
                        return cls
            except Exception:
                pass
    return None


_MCPImage = _load_mcp_image()


def _load_mcp_context():
    """Load the Context class from the MCP SDK for progress reporting in tools.

    Uses the same importlib approach as _load_fastmcp() to avoid name conflicts
    with the geeViz.mcp package.
    """
    # Preferred: direct import matches FastMCP's own Context class
    try:
        from mcp.server.fastmcp import Context
        return Context
    except (ImportError, ModuleNotFoundError, AttributeError):
        pass
    # Fallback: load from file in site-packages
    import site as _site
    for _sp in _site.getsitepackages():
        _origin = os.path.join(_sp, "mcp", "server", "fastmcp", "server.py")
        if os.path.isfile(_origin):
            try:
                spec = importlib.util.spec_from_file_location("_geeviz_mcp_sdk_context", _origin)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    return mod.Context
            except Exception:
                pass
    return None


_MCPContext = _load_mcp_context()
# Expose as module-level ``Context`` so typing.get_type_hints() can resolve the
# annotation in run_code's signature (required for FastMCP context injection).
Context = _MCPContext

# Load agent instructions from the bundled markdown file.
# These are injected as the MCP server instructions (like a system prompt)
# so every connected client automatically knows how to use the tools.
_INSTRUCTIONS_FILE = os.path.join(_THIS_DIR, "agent-instructions.md")
try:
    with open(_INSTRUCTIONS_FILE, "r", encoding="utf-8") as _f:
        _SERVER_INSTRUCTIONS = _f.read()
    # Substitute the AI-powered gmaps status marker based on the same env
    # var the runtime uses to gate the tools. This subprocess inherits
    # GEEVIZ_GMAPS_AI_ENABLED from its parent (run_ui.py sets it from the
    # tenant flag). Standalone use (no parent env) defaults to ENABLED,
    # matching googleMapsLib._check_gmaps_ai_enabled's default.
    _ai_val = str(os.environ.get("GEEVIZ_GMAPS_AI_ENABLED", "1")).strip().lower()
    _ai_on = _ai_val not in ("0", "false", "no", "off", "disabled")
    if _ai_on:
        _ai_block = (
            "**AI-powered gmaps tools — ENABLED.** In addition to the helpers above, "
            "`gm.interpret_image` (modes: streetview / satellite-map / hybrid-map / roadmap / "
            "terrain), `gm.label_image` (same modes), `gm.segment_image` (modes: streetview / "
            "aerial-urban / aerial-landcover / aerial-mixed / buildings / trees), and "
            "`gm.inventory_area` (design-based image inventory over a polygon/points/bounds "
            "with Wilson + bootstrap CIs) are available in the `gm` REPL alias — use them "
            "inside `run_code`. These issue Gemini calls and cost separately from your own "
            "model spend, so prefer them when the analysis genuinely needs them."
        )
    else:
        _ai_block = (
            "**AI-powered gmaps tools — DISABLED for this deployment.** Do NOT call "
            "`gm.interpret_image`, `gm.label_image`, `gm.segment_image`, or "
            "`gm.inventory_area` — they will raise `RuntimeError` at runtime. If the user "
            "asks for scene interpretation, labeling, segmentation, or design-based "
            "inventory over imagery, say the feature is disabled and offer Earth Engine "
            "alternatives (Landsat/Sentinel-2/NAIP inspection via `view_output`, "
            "`inspect_asset`, or a `simpleMask` + charting pipeline). The other `gm.*` "
            "helpers (geocode, search_places, streetview_*, static_map, elevation, air "
            "quality, solar, timezone, roads) remain available."
        )
    _SERVER_INSTRUCTIONS = _SERVER_INSTRUCTIONS.replace("<!--GMAPS_AI_STATUS-->", _ai_block)
    print(f"[geeViz MCP] Loaded instructions: {len(_SERVER_INSTRUCTIONS)} chars, {len(_SERVER_INSTRUCTIONS.split())} words (gmaps AI: {'ENABLED' if _ai_on else 'DISABLED'})", file=sys.stderr, flush=True)
except Exception:
    _SERVER_INSTRUCTIONS = None
    print("[geeViz MCP] WARNING: No agent instructions loaded", file=sys.stderr, flush=True)

app = FastMCP(
    "geeViz",
    instructions=_SERVER_INSTRUCTIONS,
    json_response=True,
) if _FastMCP is not None else _StubFastMCP()

# ---------------------------------------------------------------------------
# Workload-tag plumbing (EE billing attribution)
#
# When the geeViz ADK agent calls a tool, its before_tool_callback stamps
# ``_workload_tag`` into the arguments dict. We pop that off here, call
# ``ee.data.setWorkloadTag(tag)`` for the duration of the tool call, and
# ``ee.data.resetWorkloadTag()`` after — EE's own ContextVar then carries
# the tag into every outbound compute body via the library's existing
# ``_maybe_populate_workload_tag`` path.
#
# Why this hook (ToolManager.call_tool) and not ``app.call_tool``: FastMCP
# captures ``app.call_tool`` as a bound method at ``__init__`` and registers
# that reference with the lowlevel MCP server, so a later monkey-patch on
# ``app.call_tool`` is never reached. ``app._tool_manager.call_tool`` is
# the next layer down and is dereferenced fresh on every dispatch.
#
# Non-agent callers (Claude Code, etc.) just don't send ``_workload_tag``
# and EE's default workload-tag behavior applies — the MCP stays
# client-agnostic.
# ---------------------------------------------------------------------------
import re as _wl_re

_WL_TAG_DISALLOWED = _wl_re.compile(r"[^a-z0-9_\-]")

# ---------------------------------------------------------------------------
# Multi-tenant routing for Earth Engine traffic
#
# When the agent's before_tool_callback stamps ``_tenant`` into a tool's
# arguments, we pop it here and set ``geeViz.eeAuth.client.CURRENT_TENANT``
# for the call duration. The library's ``TenantAwareHttp`` transport
# reads that ContextVar on every outbound EE request and stamps the
# routing header. The proxy in ``run_ui.py`` reads the header, picks the
# right service account from the registry, and signs the request.
#
# This lets ONE Python process serve many tenants concurrently — no
# ``ee.Initialize`` race, no global credential state, no per-tenant
# subprocess. EE's normal SDK behavior is preserved for callers that
# don't send a tenant (Claude Code etc.) — they hit the default SA.
# ---------------------------------------------------------------------------
from geeViz.eeAuth.client import (
    CURRENT_TENANT as _CURRENT_TENANT_CV,
    CURRENT_USER_EMAIL as _CURRENT_USER_EMAIL_CV,
    CURRENT_SESSION_ID as _CURRENT_SESSION_ID_CV,
)


def _extract_user_and_session_from_tag(tag: str) -> tuple[str, str]:
    """Parse the workload tag the agent injected via ``_workload_tag``.

    The agent's ``build_workload_tag`` produces tags shaped like:

        ``agent__<tool_name>__<tenant>__<user_email>__<sess>``

    where the email is already sanitized (``@`` -> ``-``, ``.`` -> ``-``)
    and the session is a UUID prefix. We extract the user and session
    slots so ``TenantAwareHttp`` can stamp them as headers on every
    outbound EE call, giving the proxy an attribution source for MCP-
    initiated traffic (thumb, gif, chart, zonal stats) that has no
    browser Referer / cookie / IAP header.

    Returns ``(user_email, session_id)`` — both empty when the tag
    doesn't match the expected shape (or the user is ``anonymous``).
    """
    if not tag:
        return "", ""
    parts = tag.split("__")
    if len(parts) < 5:
        return "", ""
    # ``agent__<tool>__<tenant>__<user>__<sess>``: user is index 3,
    # session index 4. Drop the leading ``agent`` marker if present so
    # a caller can also pass the shorter <action>__<tenant>__<user>__<sess>
    # form without breaking the extraction.
    if parts[0] == "agent":
        user, session = parts[3], parts[4]
    else:
        user, session = parts[2], parts[3]
    if user == "anonymous":
        user = ""
    return user, session


def _sanitize_workload_tag(tag: str) -> str:
    """Coerce a tag to EE's accepted character set and 63-char limit.

    EE rule (from ee/_state.py): 1-63 chars, ``[a-z0-9]`` at the ends,
    ``[a-z0-9_-]`` in the middle. No uppercase, no dots, no other punct.
    """
    if not tag:
        return ""
    tag = tag.lower()
    tag = _WL_TAG_DISALLOWED.sub("-", tag)
    tag = _wl_re.sub(r"-{2,}", "-", tag)
    tag = tag.strip("-_")[:63].rstrip("-_")
    return tag


_orig_tool_manager_call_tool = app._tool_manager.call_tool


async def _tool_manager_call_tool_with_workload_tag(
    name, arguments, context=None, convert_result=False
):
    tag = None
    tenant = ""
    explicit_user = ""
    explicit_session = ""
    if isinstance(arguments, dict):
        raw = arguments.pop("_workload_tag", None)
        if raw:
            tag = _sanitize_workload_tag(str(raw))
        # Tenant is propagated separately from workload tag — proxy reads
        # it from the X-AskTerra-Tenant header set by TenantAwareHttp.
        raw_tenant = arguments.pop("_tenant", None)
        if raw_tenant:
            tenant = str(raw_tenant).strip().lower()
        # Explicit identity slots — the v2 short-hash tag (``wl_<16hex>``)
        # doesn't embed user/session the way the old long-form tag did,
        # so agent.py plumbs them alongside. Fall back to tag-parsing
        # only for legacy long-form tags.
        raw_user = arguments.pop("_agent_user_email", None)
        if raw_user:
            explicit_user = str(raw_user).strip()
        raw_session = arguments.pop("_agent_session_id", None)
        if raw_session:
            explicit_session = str(raw_session).strip()

    # ContextVar for tenant: TenantAwareHttp reads it on every outbound
    # EE request and stamps the routing header.
    tenant_token = _CURRENT_TENANT_CV.set(tenant) if tenant else None

    # ContextVars for user + session: TenantAwareHttp stamps them as
    # X-Agent-User-Email / X-Agent-Session-ID headers on outbound EE
    # calls. The proxy's ``_agent_workload_tag_builder`` picks them
    # up as a fallback attribution source when Referer/cookie/IAP
    # are absent — which is EVERY MCP-initiated EE call (thumb,
    # gif, chart, zonal stats). Prior to this, all those calls
    # tagged as ``anonymous`` in Cloud Monitoring and were invisible
    # in per-user cost attribution.
    # Prefer explicit slots (v2 short-hash tag path); fall back to parsing
    # a legacy long-form tag for backward compat.
    _user = explicit_user
    _session = explicit_session
    if not _user or not _session:
        _p_user, _p_session = _extract_user_and_session_from_tag(tag)
        _user = _user or _p_user
        _session = _session or _p_session
    user_token = _CURRENT_USER_EMAIL_CV.set(_user) if _user else None
    session_token = _CURRENT_SESSION_ID_CV.set(_session) if _session else None

    try:
        if not tag:
            return await _orig_tool_manager_call_tool(
                name, arguments, context=context, convert_result=convert_result
            )
        # EE's own setWorkloadTag uses a ContextVar internally, so the tag
        # carries through ``await`` boundaries to whatever EE call user code
        # eventually makes. resetWorkloadTag in ``finally`` keeps the state
        # clean across overlapping tool calls in the same process.
        try:
            import ee.data as _ee_data
            _ee_data.setWorkloadTag(tag)
        except Exception:
            # If EE isn't initialized yet, swallow — the agent's first tool
            # call is usually run_code, which initializes EE before doing
            # any actual compute. Subsequent calls will tag correctly.
            return await _orig_tool_manager_call_tool(
                name, arguments, context=context, convert_result=convert_result
            )
        try:
            return await _orig_tool_manager_call_tool(
                name, arguments, context=context, convert_result=convert_result
            )
        finally:
            try:
                _ee_data.resetWorkloadTag()
            except Exception:
                pass
    finally:
        if tenant_token is not None:
            _CURRENT_TENANT_CV.reset(tenant_token)
        if user_token is not None:
            _CURRENT_USER_EMAIL_CV.reset(user_token)
        if session_token is not None:
            _CURRENT_SESSION_ID_CV.reset(session_token)


def _scrub_tool_result(result):
    """Redact credentials in any string field of a FastMCP tool result.

    FastMCP tools return either a ``ToolResult`` (newer SDKs) with a
    ``.content`` list, or a bare list of ``Content`` items (older SDKs).
    ``TextContent`` items carry a ``.text`` attribute; other content
    types (ImageContent / EmbeddedResource) don't. We walk both shapes
    and scrub every ``.text`` in place — this is the single chokepoint
    that catches secrets escaping via ANY tool, not just ``run_code``
    (where we already scrub at each return site as belt-and-suspenders).
    """
    if result is None:
        return result
    # Iterable of Content items (list / tuple).
    if isinstance(result, (list, tuple)):
        for item in result:
            _scrub_content_item(item)
        return result
    # ToolResult with .content list.
    content = getattr(result, "content", None)
    if isinstance(content, (list, tuple)):
        for item in content:
            _scrub_content_item(item)
    # Some SDKs also carry a .structuredContent dict — scrub it too.
    structured = getattr(result, "structuredContent", None) or getattr(
        result, "structured_content", None
    )
    if isinstance(structured, dict):
        _scrub_dict_inplace(structured)
    return result


def _scrub_content_item(item) -> None:
    """Scrub a single Content item's textual payload in place."""
    if item is None:
        return
    text = getattr(item, "text", None)
    if isinstance(text, str) and text:
        try:
            setattr(item, "text", _scrub_credentials(text))
        except Exception:
            # Some Content types are frozen (pydantic v2 frozen models).
            # Fall back to mutating a __dict__ attribute directly if we can.
            try:
                item.__dict__["text"] = _scrub_credentials(text)
            except Exception:
                pass


def _scrub_dict_inplace(d: dict) -> None:
    """Recursively scrub every string value in a nested dict / list."""
    for k, v in list(d.items()):
        if isinstance(v, str):
            d[k] = _scrub_credentials(v)
        elif isinstance(v, dict):
            _scrub_dict_inplace(v)
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, str):
                    v[i] = _scrub_credentials(item)
                elif isinstance(item, dict):
                    _scrub_dict_inplace(item)


_pre_scrub_call_tool = _tool_manager_call_tool_with_workload_tag


async def _tool_manager_call_tool_with_scrub(
    name, arguments, context=None, convert_result=False
):
    """Post-process every tool response through the credential scrubber.

    Wraps the workload-tag layer — that layer handles EE routing /
    ContextVar plumbing and returns the FastMCP tool result unchanged;
    this wrapper walks the result and redacts any secret shape or
    exact env-var value before FastMCP serializes it back to the model.
    """
    result = await _pre_scrub_call_tool(
        name, arguments, context=context, convert_result=convert_result
    )
    try:
        return _scrub_tool_result(result)
    except Exception:
        # Fail-open on scrub crashes rather than break every tool call.
        # The per-return-site scrubs in run_code still catch its output.
        return result


# ---------------------------------------------------------------------------
# LLM usage collection (Gemini billing attribution)
#
# The sibling of the workload-tag plumbing above, for the other thing
# that costs money. Three geeViz modules call Gemini on their own —
# googleMapsLib, inventoryLib and outputLib.reports — and until now the
# tokens they burned reached nothing that accounts for spend. The agent
# paid for them and could not see them.
#
# geeViz cannot report that itself: it is a standalone library with no
# agent to import, no database credentials, and no idea who is being
# billed. So it announces each call through ``geeViz.llmUsage.report``,
# and this layer — which DOES know it is running as the agent's
# subprocess — collects whatever was announced during one tool call and
# attaches it to that call's result. The agent's after_tool_callback
# drains the field, records it, and strips it before the model ever
# sees it.
#
# Outermost of the call_tool wrappers, so the window spans everything
# the tool did.
_pre_usage_call_tool = _tool_manager_call_tool_with_scrub

# The field name is underscore-prefixed to mark it as transport, not
# tool output. It is removed by the agent before the response is
# persisted, so it should never appear in conversation history — if it
# does, the drain is not running.
_LLM_USAGE_FIELD = "_llm_usage"


def _put_in_structured(structured: dict, records: list) -> None:
    """Write the usage field into a structuredContent dict, in place.

    A single-key ``{"result": "<json string>"}`` envelope holds the real
    payload as text, so the field goes INSIDE it — that is where the
    agent's after_tool_callback unwraps to, and writing beside it puts
    the records somewhere nothing looks.
    """
    inner_text = structured.get("result")
    if len(structured) == 1 and isinstance(inner_text, str):
        try:
            inner = json.loads(inner_text)
            if isinstance(inner, dict):
                inner[_LLM_USAGE_FIELD] = records
                structured["result"] = json.dumps(inner)
                return
        except (json.JSONDecodeError, TypeError):
            pass
    structured[_LLM_USAGE_FIELD] = records


def _attach_llm_usage(result, records: list):
    """Put ``records`` on the tool result, wherever the result keeps data.

    Prefers ``structuredContent`` because it survives untouched; falls
    back to re-serializing the first JSON text part. Returns the result
    either way — a tool call must not fail because its accounting could
    not be attached.
    """
    if not records:
        return result

    # FastMCP's REAL dispatch passes convert_result=True, and that
    # returns a plain ``(content_list, structured_dict)`` TUPLE rather
    # than a ToolResult. Missing this meant nothing was ever attached on
    # the only path that matters: the tuple fell through to the
    # list/tuple branch below, whose two items are a list and a dict —
    # neither carries ``.text`` — so the function returned the result
    # untouched and every geeViz LLM call went unbilled. Silently.
    #
    # The unit test did not catch it because its fake inner returned a
    # ToolResult-shaped object: a shape the real dispatch never
    # produces. Test the wiring, not just the helper.
    if (isinstance(result, tuple) and len(result) == 2
            and isinstance(result[1], dict)):
        _put_in_structured(result[1], records)
        return result

    structured = getattr(result, "structuredContent", None) or getattr(
        result, "structured_content", None
    )
    if isinstance(structured, dict):
        _put_in_structured(structured, records)
        return result

    content = getattr(result, "content", None)
    if content is None and isinstance(result, (list, tuple)):
        content = result
    for item in (content or []):
        text = getattr(item, "text", None)
        if not isinstance(text, str) or not text:
            continue
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(payload, dict):
            continue
        payload[_LLM_USAGE_FIELD] = records
        new_text = json.dumps(payload)
        try:
            setattr(item, "text", new_text)
        except Exception:
            try:
                item.__dict__["text"] = new_text
            except Exception:
                return result
        return result
    return result


# Imported HERE, at module scope, and deliberately not inside the
# wrapper below.
#
# A call-time ``from geeViz import llmUsage`` inside the wrapper
# deadlocked the server. ``main()`` starts a daemon thread that prewarms
# EE and the geeViz imports; that thread holds the import lock for the
# ``geeViz`` package for tens of seconds. A tool call arriving in that
# window ran the import ON THE EVENT LOOP, which blocked waiting for the
# lock — so the tool finished, its result was never serialized back over
# stdio, and the agent sat on a spinner forever. The symptom was a
# completed tool call with no response and no error anywhere.
#
# This module imports nothing from geeViz and only stdlib, so hoisting
# it costs nothing and cannot cycle.
from geeViz import llmUsage as _lu


async def _tool_manager_call_tool_with_usage(
    name, arguments, context=None, convert_result=False
):
    """Collect LLM usage reported during one tool call and attach it."""
    with _lu.collect() as records:
        result = await _pre_usage_call_tool(
            name, arguments, context=context, convert_result=convert_result
        )
    try:
        return _attach_llm_usage(result, list(records))
    except Exception:
        # Accounting must never cost a caller their result.
        return result


app._tool_manager.call_tool = _tool_manager_call_tool_with_usage

# Wrap app.tool() to auto-log every tool invocation
_original_app_tool = app.tool


def _logging_tool_decorator(*dec_args, **dec_kwargs):
    """Replacement for app.tool() that wraps each tool function with logging."""
    original_decorator = _original_app_tool(*dec_args, **dec_kwargs)

    def wrapper(fn):
        import functools
        import inspect as _insp

        @functools.wraps(fn)
        async def logged_fn(*args, **kwargs):
            _log_tool_call(fn.__name__, kwargs)
            try:
                result = fn(*args, **kwargs)
                # Handle both sync and async tool functions
                if _insp.isawaitable(result):
                    result = await result
                _log_tool_call(fn.__name__, kwargs, result=result)
                return result
            except Exception as exc:
                _log_tool_call(fn.__name__, kwargs, error=exc)
                raise

        # Expose the LOGGED (but not FastMCP-decorated) function on THIS
        # module's namespace so in-process callers (e.g. run_ui.py's
        # /scripts/{id}/run route) can invoke it directly. Calling the
        # FastMCP-decorated tool in-process hangs forever — it expects
        # an MCP peer to respond. Use globals() (not sys.modules lookup)
        # because server.py may be loaded under multiple names
        # (``server`` via sys.path.insert AND ``geeViz.mcp.server`` via
        # package import) — globals() always resolves to THIS module's
        # actual namespace regardless of which alias the caller used.
        try:
            globals()[f"_{fn.__name__}_direct"] = logged_fn
        except Exception:
            pass

        # If original fn is not async, keep it sync for FastMCP
        if not _insp.iscoroutinefunction(fn):
            @functools.wraps(fn)
            def logged_fn_sync(*args, **kwargs):
                _log_tool_call(fn.__name__, kwargs)
                try:
                    result = fn(*args, **kwargs)
                    _log_tool_call(fn.__name__, kwargs, result=result)
                    return result
                except Exception as exc:
                    _log_tool_call(fn.__name__, kwargs, error=exc)
                    raise
            return original_decorator(logged_fn_sync)

        return original_decorator(logged_fn)

    return wrapper


app.tool = _logging_tool_decorator

# ---------------------------------------------------------------------------
# Tool call logging -- every MCP tool invocation is logged with timestamp,
# tool name, arguments, and status (success/error).
# Log file: <mcp_dir>/logs/tool_calls.log
# ---------------------------------------------------------------------------
import logging as _logging
import datetime as _datetime

_LOG_DIR = os.path.join(_THIS_DIR, "logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_TOOL_LOG_FILE = os.path.join(_LOG_DIR, "tool_calls.log")

_tool_logger = _logging.getLogger("geeViz.mcp.tools")
_tool_logger.setLevel(_logging.DEBUG)
_tool_fh = _logging.FileHandler(_TOOL_LOG_FILE, encoding="utf-8")
_tool_fh.setFormatter(_logging.Formatter("%(message)s"))
_tool_logger.addHandler(_tool_fh)
_log_result_limit = 5000

def _log_tool_call(tool_name: str, args: dict, result=None, error=None):
    """Log a tool invocation to the tool_calls.log file."""
    ts = _datetime.datetime.now().isoformat(timespec="seconds")
    # Truncate large arg values for readability
    clean_args = {}
    for k, v in (args or {}).items():
        s = str(v)
        clean_args[k] = s[:_log_result_limit] + "..." if len(s) > _log_result_limit else s
    entry = {
        "timestamp": ts,
        "tool": tool_name,
        "args": clean_args,
    }
    if error:
        entry["status"] = "ERROR"
        entry["error"] = str(error)[:_log_result_limit]
    else:
        result_str = str(result)
        entry["status"] = "OK"
        entry["result_preview"] = result_str[:_log_result_limit] + "..." if len(result_str) > _log_result_limit else result_str
    import json as _json_log
    _tool_logger.info(_json_log.dumps(entry))


# ---------------------------------------------------------------------------
# Lazy initialization -- defer all geeViz imports until first tool call
# that needs them.  Every geeViz module import triggers robustInitializer()
# at module level, so we must not import at top level.
# ---------------------------------------------------------------------------
import threading
import json

# Opt-in all-thread stack dump, for when this server stops responding.
#
# Set ``GEEVIZ_MCP_STACK_DUMP_SECS=45`` on the AGENT (its environment is
# handed to this subprocess verbatim) and every N seconds each thread's
# stack is printed to stderr, which lands in the agent's log.
#
# Worth keeping because the failure mode this server has had twice is a
# HANG, not a crash: a tool logs "status": "OK", never returns, and
# nothing is written anywhere. There is no traceback to find, and a
# hung thread is invisible to every other kind of instrumentation. The
# prewarm deadlock was diagnosed from one of these dumps in minutes
# after days of hypotheses — the cycle (prewarm holding _init_lock
# inside a numpy C-extension load, tool thread blocked acquiring it)
# is only visible when you can see ALL threads at once.
#
# Off unless the variable is set, and it only prints.
if os.environ.get("GEEVIZ_MCP_STACK_DUMP_SECS"):
    import faulthandler as _fh
    try:
        _every = int(os.environ["GEEVIZ_MCP_STACK_DUMP_SECS"])
    except ValueError:
        _every = 0
    if _every > 0:
        _fh.dump_traceback_later(_every, repeat=True, exit=False,
                                 file=sys.stderr)
        print("[geeViz MCP] all-thread stack dump armed every %ss" % _every,
              file=sys.stderr, flush=True)

_init_lock = threading.RLock()  # reentrant: _ensure_initialized holds it
                                # while calling _ensure_ee_initialized which
                                # also acquires it on the same thread.
_initialized = False

# Set once global EE + geeViz init has finished. The dataset-catalog
# prewarm waits on this rather than running alongside init: it is a
# second background thread pulling in heavy dependencies (the BigQuery
# client), and concurrent C-extension imports from two threads are
# exactly what wedged the EE prewarm. Waiting costs nothing — the
# catalog build is only needed by search_datasets, which cannot be
# called before init anyway.
_init_done = threading.Event()

# Dynamic module tree — populated at init time by _build_module_tree()
_MODULE_TREE = {}  # short_name -> {"fq": fully_qualified_path, "mod": module_object}
_MODULE_MAP = {}   # short_name -> fully_qualified_path (backward compat)

# Packages to skip during module discovery
# - mcp: this server itself (circular)
# - examples: importing them triggers EE calls and side effects (use `examples` tool instead)
_SKIP_PACKAGES = {"geeViz.mcp", "geeViz.examples", "geeViz.migrateGEEAssets"}


def _ast_extract_members(filepath):
    """Parse a .py file with AST and extract public members without importing.

    Returns a list of dicts: {name, type, signature, docstring}.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception:
        return [], ""

    module_doc = ast.get_docstring(tree) or ""
    members = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            # Build signature from args
            args = node.args
            params = []
            # Positional args (skip 'self' if present)
            all_args = [a.arg for a in args.args]
            defaults = [None] * (len(all_args) - len(args.defaults)) + [ast.dump(d) for d in args.defaults]
            for arg_name, default in zip(all_args, defaults):
                if arg_name == "self":
                    continue
                params.append(f"{arg_name}=..." if default else arg_name)
            if args.vararg:
                params.append(f"*{args.vararg.arg}")
            for kw, default in zip(args.kwonlyargs, args.kw_defaults):
                params.append(f"{kw.arg}=..." if default else kw.arg)
            if args.kwarg:
                params.append(f"**{args.kwarg.arg}")
            sig = f"{node.name}({', '.join(params)})"
            doc = ast.get_docstring(node) or ""
            first_line = doc.split("\n")[0].strip() if doc else ""
            members.append({"name": node.name, "type": "function", "signature": sig, "description": first_line, "docstring": doc})

        elif isinstance(node, ast.ClassDef):
            if node.name.startswith("_"):
                continue
            doc = ast.get_docstring(node) or ""
            first_line = doc.split("\n")[0].strip() if doc else ""
            # Extract public methods
            methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not item.name.startswith("_"):
                    methods.append(item.name)
            members.append({"name": node.name, "type": "class", "description": first_line, "docstring": doc, "methods": methods})

        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    entry = {"name": target.id, "type": "variable", "description": ""}
                    try:
                        entry["value"] = ast.literal_eval(node.value)
                    except (ValueError, TypeError):
                        # Store source text so the agent can read the expression
                        try:
                            entry["value"] = ast.unparse(node.value)
                        except Exception:
                            pass
                    members.append(entry)

        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and not node.target.id.startswith("_"):
                entry = {"name": node.target.id, "type": "variable", "description": ""}
                if node.value is not None:
                    try:
                        entry["value"] = ast.literal_eval(node.value)
                    except (ValueError, TypeError):
                        try:
                            entry["value"] = ast.unparse(node.value)
                        except Exception:
                            pass
                members.append(entry)

    return members, module_doc


def _list_example_files():
    """Return sorted list of example filenames."""
    if not os.path.isdir(_EXAMPLES_DIR):
        return []
    return sorted(f for f in os.listdir(_EXAMPLES_DIR)
                  if (f.endswith(".py") or f.endswith(".ipynb")) and f != "__init__.py")


def _read_example_source(filename, name, description=""):
    """Read an example file and return JSON with its source."""
    fpath = os.path.join(_EXAMPLES_DIR, filename)
    if filename.endswith(".py"):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                return json.dumps({"name": name, "file": filename, "type": "python",
                                   "description": description, "source": f.read()})
        except Exception as exc:
            return json.dumps({"error": f"Failed to read {filename}: {exc}"})
    elif filename.endswith(".ipynb"):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                nb = json.load(f)
            cells = [{"cell_type": c.get("cell_type", ""), "source": "".join(c.get("source", []))}
                     for c in nb.get("cells", []) if "".join(c.get("source", [])).strip()]
            return json.dumps({"name": name, "file": filename, "type": "notebook",
                               "description": description, "cells": cells})
        except Exception as exc:
            return json.dumps({"error": f"Failed to read notebook: {exc}"})
    return json.dumps({"error": f"Unknown file type: {filename}"})


def _build_module_tree():
    """Walk the geeViz package and build a searchable index using AST.

    No modules are imported. Populates ``_MODULE_TREE`` with module paths
    and pre-parsed member indices (names, types, signatures, docstrings).
    Modules are only imported on-demand when live values are needed
    (e.g. dict contents via ``search_codebase(name=...)``).
    """
    global _MODULE_TREE, _MODULE_MAP
    import pkgutil
    import geeViz

    tree = {}
    fq_map = {}

    for importer, modname, ispkg in pkgutil.walk_packages(
        geeViz.__path__, prefix="geeViz."
    ):
        # Skip excluded packages
        if any(modname == skip or modname.startswith(skip + ".") for skip in _SKIP_PACKAGES):
            continue
        # Skip private modules
        leaf = modname.rsplit(".", 1)[-1]
        if leaf.startswith("_"):
            continue
        # Skip test modules. They are not API, and indexing them actively
        # HURT discovery: a real session asked for "evalidator" and the
        # only hit was test_njson_shape.test_legacy_evalidator_output_
        # still_parses, because the term appears in that test's NAME but
        # only in the BODY of the docstrings on fia.estimate/validate.
        # The agent burned three searches before guessing module="fia".
        if leaf.startswith("test_") or ".tests" in modname or leaf == "tests":
            continue

        # Find the source file without importing
        try:
            spec = importlib.util.find_spec(modname)
            if spec is None or spec.origin is None:
                continue
        except (ModuleNotFoundError, ValueError):
            continue

        # Parse with AST
        members, module_doc = _ast_extract_members(spec.origin)
        first_line = module_doc.split("\n")[0].strip()[:100] if module_doc else ""

        short = leaf
        entry = {"fq": modname, "mod": None, "file": spec.origin,
                 "members": members, "doc": first_line, "is_pkg": ispkg,
                 # Full module docstring, kept for search only. A module
                 # can be the right answer on its own ("which module
                 # talks to EVALIDator?") and matching just the summary
                 # line missed that entirely.
                 "module_doc": module_doc}
        tree[modname] = entry
        if short not in tree:
            tree[short] = entry
        fq_map[short] = modname
        fq_map[modname] = modname

    # --- Packages list their submodules -------------------------------
    # A package's spec.origin is its __init__.py, and a re-export-only
    # __init__ has no def/class of its own — so AST extraction returned
    # NOTHING and search_codebase(module="fsInsights") answered
    # ``count: 0``. The package name is the obvious first guess, and it
    # dead-ended into "this doesn't exist" when the truth was "its
    # contents are in submodules". Point the caller at them instead.
    for modname, entry in list(tree.items()):
        if not entry.get("is_pkg") or entry.get("members"):
            continue
        subs = []
        for other, oe in tree.items():
            if other == modname or "." not in other:
                continue
            parent, _, child = other.rpartition(".")
            if parent != modname:
                continue
            subs.append({"name": child, "type": "module",
                         "description": oe.get("doc", "")})
        if subs:
            entry["members"] = sorted(subs, key=lambda d: d["name"])

    # --- Index examples (AST parse .py, JSON parse .ipynb) ---
    example_members = []
    for fname in _list_example_files():
        fpath = os.path.join(_EXAMPLES_DIR, fname)
        base = fname.rsplit(".", 1)[0]
        desc = ""
        if fname.endswith(".py"):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    source = f.read()
                try:
                    ex_tree = ast.parse(source)
                    doc = ast.get_docstring(ex_tree) or ""
                    desc = doc.split("\n")[0].strip()[:100] if doc else ""
                except SyntaxError:
                    pass
                if not desc:
                    for line in source.split("\n")[:20]:
                        s = line.strip()
                        if s.startswith("#") and len(s) > 2:
                            desc = s.lstrip("#").strip()
                            break
            except Exception:
                pass
        elif fname.endswith(".ipynb"):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    nb = json.load(f)
                for cell in nb.get("cells", []):
                    if cell.get("cell_type") == "markdown":
                        src = "".join(cell.get("source", [])).strip()
                        if src:
                            desc = src.split("\n")[0].lstrip("#").strip()[:100]
                            break
            except Exception:
                pass
        example_members.append({"name": base, "type": "example", "description": desc or fname, "file": fname})

    tree["examples"] = {
        "fq": "geeViz.examples", "mod": None, "file": _EXAMPLES_DIR,
        "members": example_members, "doc": "geeViz example scripts and notebooks",
    }
    fq_map["examples"] = "geeViz.examples"

    _MODULE_TREE = tree
    _MODULE_MAP = fq_map
    n_mods = len(set(e["fq"] for e in tree.values()))
    n_examples = len(example_members)
    # stderr, NOT stdout: this server speaks JSON-RPC over stdio, and
    # _build_module_tree() runs from _ensure_initialized_locked() — i.e.
    # lazily, on the FIRST tool call, not at import. Printing to stdout
    # there injects a non-JSON line into the protocol stream mid-session,
    # desyncs the client's parser, and the in-flight request never gets a
    # matching response. It surfaces as:
    #   McpError: Timed out while waiting for response to ClientRequest.
    #             Waited 300.0 seconds.
    # which reads like a hung EE call but is a corrupted pipe.
    print(f"[geeViz MCP] Module tree: {n_mods} modules, {n_examples} examples indexed (zero imports)",
          file=sys.stderr, flush=True)


def _get_module(entry):
    """Lazy-import a module from a tree entry. Caches the result."""
    if entry["mod"] is None:
        try:
            entry["mod"] = importlib.import_module(entry["fq"])
        except Exception as exc:
            print(f"[geeViz MCP] Failed to import {entry['fq']}: {exc}", file=sys.stderr, flush=True)
            return None
    return entry["mod"]


def _describe_object(obj, name="", module_name="", max_size=20000):
    """Return a JSON-safe description of any Python object."""
    result = {"name": name}
    if module_name:
        result["module"] = module_name

    if _inspect.ismodule(obj):
        members = [m for m in sorted(dir(obj)) if not m.startswith("_")]
        result["type"] = "module"
        result["docstring"] = (_inspect.getdoc(obj) or "")[:500]
        result["public_members"] = members[:200]
        if len(members) > 200:
            result["note"] = f"Showing 200 of {len(members)} members. Use query= to filter."
        return result

    if _inspect.isclass(obj):
        methods = [m for m in sorted(dir(obj)) if not m.startswith("_") and callable(getattr(obj, m, None))]
        result["type"] = "class"
        result["docstring"] = _inspect.getdoc(obj) or ""
        result["public_methods"] = methods
        try:
            result["constructor"] = f"{name}{_inspect.signature(obj.__init__)}"
        except (ValueError, TypeError):
            pass
        return result

    if callable(obj):
        result["type"] = "function"
        try:
            result["signature"] = f"{name}{_inspect.signature(obj)}"
        except (ValueError, TypeError):
            result["signature"] = f"{name}(...)"
        result["docstring"] = _inspect.getdoc(obj) or ""
        return result

    # Non-callable: dict, list, constant, etc.
    result["type"] = type(obj).__name__

    # Check for ee objects — never call getInfo
    try:
        import ee as _ee
        if isinstance(obj, _ee.ComputedObject):
            result["repr"] = repr(obj)[:500]
            return result
    except Exception:
        pass

    if isinstance(obj, dict):
        serialized = json.dumps(_make_serializable(obj), default=str)
        if len(serialized) > max_size:
            result["keys"] = list(obj.keys())[:100]
            # Show sample of first 3 entries
            sample = {k: _make_serializable(v) for k, v in list(obj.items())[:3]}
            result["sample"] = sample
            result["note"] = f"Large dict ({len(obj)} keys). Showing keys + 3 samples."
        else:
            result["value"] = _make_serializable(obj)
        return result

    if isinstance(obj, (list, tuple)):
        if len(obj) > 50:
            result["length"] = len(obj)
            result["sample"] = _make_serializable(list(obj[:5]))
            result["note"] = f"Large {type(obj).__name__} ({len(obj)} items). Showing first 5."
        else:
            result["value"] = _make_serializable(list(obj))
        return result

    # Scalar or other
    try:
        result["value"] = _make_serializable(obj)
    except Exception:
        result["repr"] = repr(obj)[:500]
    return result

# ---------------------------------------------------------------------------
# Per-session state — isolates REPL namespace, Map, code history, outputs,
# and reports across concurrent users/sessions.
# ---------------------------------------------------------------------------
import threading as _threading

_BASE_OUTPUT_DIR = os.path.join(_THIS_DIR, "generated_outputs")
_BASE_SCRIPT_DIR = os.path.join(_THIS_DIR, "generated_scripts")
_DEFAULT_SESSION_ID = "_default"


class _SessionState:
    """All mutable state scoped to a single session."""
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.namespace: dict = {}
        self.code_history: list[str] = []
        # Per-block dependency metadata parallel to ``code_history``.
        # Each entry is a dict:
        #   {
        #     "source": str,          # exact block text (mirror of code_history[i])
        #     "names_bound": set[str], # names this block DEFINED
        #     "names_read": set[str],  # names this block READ before binding
        #     "names_touched": set[str], # names mutated via subscript/attribute store
        #     "is_import": bool,      # block contains at least one Import/ImportFrom
        #     "wildcard_import": bool,# block has `from X import *` (opaque bindings)
        #     "succeeded": bool,      # block ran to completion without error
        #   }
        # Populated in run_code after each successful (or failed) exec.
        # Consumed by _slice_history() at save-session time to build a
        # minimal script — only blocks whose bindings are transitively
        # read by the final successful block are kept.
        self.code_history_meta: list[dict] = []
        self.current_script_path: str | None = None
        self.active_report = None
        self.initialized = False
        # Per-session output directory
        if session_id == _DEFAULT_SESSION_ID:
            self.output_dir = _BASE_OUTPUT_DIR
            self.script_dir = _BASE_SCRIPT_DIR
        else:
            self.output_dir = os.path.join(_BASE_OUTPUT_DIR, session_id)
            self.script_dir = os.path.join(_BASE_SCRIPT_DIR, session_id)
        # Stdout streaming file
        self.stdout_stream_file = os.path.join(self.output_dir, ".stdout_stream")
        self.stdout_active = False
        # Original Map reference (set during init, used to restore if clobbered)
        self._map_ref = None
        # Per-session run_code call timestamps for the runaway-retry circuit
        # breaker. Persona testing showed agents can stack 25+ run_code calls
        # in a single turn while thrashing on the same equity join or
        # unfamiliar geometry lookup, with the same minor tweak each time.
        # Prompt-level rule "max 2 retries then restructure" alone is not
        # sufficient. The breaker counts calls in a sliding window and
        # returns a hard RESTRUCTURE_REQUIRED before executing call N+1.
        self._recent_call_ts: list[float] = []
        # When the breaker has fired this many times for this session, the
        # next call is allowed through unconditionally (so we don't deadlock
        # the agent if it actually does need many quick calls after a real
        # restructure).
        self._breaker_acks: int = 0


_sessions: dict[str, _SessionState] = {}
_sessions_lock = _threading.Lock()


def _get_session(session_id: str | None = None) -> _SessionState:
    """Get or create a session state object. Thread-safe."""
    sid = session_id or _DEFAULT_SESSION_ID
    if sid in _sessions:
        return _sessions[sid]
    with _sessions_lock:
        if sid not in _sessions:
            _sessions[sid] = _SessionState(sid)
        return _sessions[sid]


# Backward-compatible module-level references for non-session-aware code
_output_dir = _BASE_OUTPUT_DIR
_script_dir = _BASE_SCRIPT_DIR


def _load_env():
    """Load .env file from the geeViz package directory into os.environ.

    Parses KEY=VALUE lines (ignoring comments and blank lines).
    Does NOT override existing environment variables.
    Looks for .env in the geeViz root (parent of mcp/).
    """
    env_path = os.path.join(os.path.dirname(_THIS_DIR), ".env")
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass

_load_env()


def _init_ee_via_proxy():
    """Initialize Earth Engine to route ALL outbound traffic through the
    agent's ``/ee-api`` proxy, with tenant-aware routing.

    Requires ``EE_PROXY_URL`` env var (e.g. ``http://localhost:8888/ee-api``).
    Delegates to ``geeViz.eeAuth.initialize_via_proxy`` which is the
    canonical client-side init helper for the library.

    The tool wrapper below maintains its OWN ContextVar
    (``_CURRENT_TENANT_CV``) and copies the tenant into
    ``geeViz.eeAuth.client.CURRENT_TENANT`` for each call — that ensures
    the library's ``TenantAwareHttp`` transport sees the right value
    even though the MCP wrapper is what knows about ``_tenant`` args.

    Passes the SA's project explicitly so EE builds API URLs with the
    real consumer project. Without this, ``initialize_via_proxy``
    defaults to ``"ee-proxy-placeholder"`` and EE emits
    ``projects/ee-proxy-placeholder/value:compute`` to upstream which
    404s. Project is sourced from ``GEE_PROJECT`` env var first, then
    by decoding any ``GEE_SERVICE_ACCOUNT_B64`` blob present in env —
    no separate translation step needed.
    """
    proxy_url = os.environ.get("EE_PROXY_URL", "").strip().rstrip("/")
    if not proxy_url:
        return False

    project = os.environ.get("GEE_PROJECT", "").strip()
    if not project:
        b64 = os.environ.get("GEE_SERVICE_ACCOUNT_B64", "")
        if b64:
            import base64 as _b64
            import json as _json
            try:
                project = _json.loads(
                    _b64.b64decode(b64.encode()).decode()
                ).get("project_id") or ""
            except Exception:
                project = ""

    from geeViz.eeAuth import initialize_via_proxy
    return initialize_via_proxy(proxy_url, project=project or None)


def _init_ee_credentials():
    """Initialize Earth Engine credentials for this MCP process.

    Two paths:

    - **Proxy mode** (``EE_PROXY_URL`` set): EE routes all REST calls
      through the agent's ``/ee-api`` proxy with TenantAwareHttp adding
      the tenant header. Used in production (Cloud Run) where the agent
      and MCP share a process. The agent's proxy holds the credentials;
      this subprocess just points ``ee.Initialize`` at the proxy URL.

    - **Direct mode** (no proxy): hand off to
      :func:`geeViz.eeAuth.robust_init`, the same bootstrap geeView /
      external callers use. It runs the full credential discovery —
      ``$GOOGLE_APPLICATION_CREDENTIALS``, the EE persistent file,
      gcloud ADC, ``$GEE_SERVICE_ACCOUNT_B64``, per-tenant SA env vars
      (keyed + keyless), and an ADC fallback for Cloud Run / GKE / AWS
      WIF deployments. Multi-tenant deployments get the in-process
      proxy spun up automatically; single-tenant deployments get a
      direct ``ee.Initialize`` call.

    The direct-mode discovery is owned by ``geeViz.eeAuth.eeCreds`` —
    this function is a thin dispatch, not a credential-handling layer
    of its own.
    """
    if _init_ee_via_proxy():
        return
    from geeViz.eeAuth import robust_init
    robust_init(verbose=False, interactive=False)


def _ensure_ee_initialized():
    """Initialize EE credentials once (global, not per-session).

    EE init runs with the sandbox audit hook FORCED OFF for its duration,
    regardless of what the exec thread has set the module-global flag to.
    Rationale: ``ee.Initialize()`` legitimately reads ADC files, hits the
    GCE metadata server, opens cert bundles, imports helper modules — all
    of these are server-side infrastructure, not user code, and MUST NOT
    trip any deny rule. Prior to this saved/restored context, a race with
    a concurrent ``_exec`` thread that had flipped ``_audit_user_code_active``
    to True caused ADC-read PermissionErrors that left ``_initialized``
    False and made every subsequent tool call retry-and-fail the same way
    (austin_geo test 2026-08-04). Any audit fire during EE init is a bug
    — this wrapper guarantees the window is safe.
    """
    global _initialized, _audit_user_code_active
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        _saved_audit = _audit_user_code_active
        _audit_user_code_active = False
        try:
            _init_ee_credentials()
            # Import geeViz to trigger ee.Initialize
            import geeViz.geeView  # noqa: F401
            _initialized = True
            # Neutralize ee.Initialize() so agent-generated code that
            # re-initializes (a common mistake — the REPL already
            # initialized EE via the parent's /ee-api proxy) doesn't blow
            # up with "no project found". Bare ``ee.Initialize()`` reads
            # only local credentials + falls back to a quota project the
            # runtime SA may not have permission on, killing the session.
            # We keep the original around under ``_geeviz_original_Initialize``
            # in case anything ever needs to re-init deliberately.
            # Evidence: austin_geo test 2026-08-04 demo session, first
            # run_code block generated by the agent contained
            # ``import ee; ee.Initialize()`` and 503'd the whole session.
            import ee as _ee_mod
            if not hasattr(_ee_mod, "_geeviz_original_Initialize"):
                _ee_mod._geeviz_original_Initialize = _ee_mod.Initialize
                def _noop_ee_initialize(*_args, **_kwargs):
                    # Silent no-op; the REPL initialized EE via proxy.
                    return None
                _ee_mod.Initialize = _noop_ee_initialize
        finally:
            _audit_user_code_active = _saved_audit


def _ensure_initialized(session_id: str | None = None):
    """Lazy-initialize EE (global) and populate session namespace.

    The whole body runs under ``_init_lock`` (reentrant) so concurrent tool
    calls cannot race the module-tree build or the geeViz submodule import
    cascade — that race wedged the asyncio dispatcher for 5+ minutes once
    proxy-routed EE init was added in v2026.5.1 (the longer per-call init
    widened the race window enough to hit reliably).
    """
    with _init_lock:
        sess = _ensure_initialized_locked(session_id)
    # Set AFTER the lock is released and every import is done — setting
    # it mid-cascade would let the catalog thread start alongside the
    # numpy/pandas import that wedged the old prewarm.
    _init_done.set()
    return sess


def _ensure_initialized_locked(session_id: str | None = None):
    _ensure_ee_initialized()
    if not _MODULE_TREE:
        _build_module_tree()
    sess = _get_session(session_id)
    if sess.initialized:
        return sess

    import geeViz.geeView as gv
    import geeViz.getImagesLib as gil
    import geeViz.getSummaryAreasLib as sal
    import geeViz.edwLib as edw
    import geeViz.geePalettes as palettes
    import geeViz.weather as wx
    from geeViz.outputLib import charts as cl
    from geeViz.outputLib import thumbs as tl
    from geeViz.outputLib import reports as rl
    import ee
    # googleMapsLib is optional — it depends on requests + (for
    # interpret_image / label_image) google-genai + Pillow. If any of
    # those aren't installed, or if the module itself errors on import,
    # the MCP still starts and `gm` simply isn't in the REPL namespace.
    try:
        import geeViz.googleMapsLib as gm
    except Exception as _gm_err:
        gm = None
        _GM_IMPORT_ERROR = repr(_gm_err)
    # fsInsights (FIA + LCMS). Optional for the same reason as gm — it
    # needs requests — and absent it the REPL simply has no `fs`.
    #
    # It is here because the MCP's three FIA/LCMS tools are a deliberate
    # SUBSET: fia_estimate exposes 4 of estimate()'s 11 parameters, so
    # str_filter, forest_definition, max_se_pct and min_plots were
    # unreachable from the agent by any route. Everything else in geeViz
    # already has a REPL handle (gil, sal, cl, tl, rl); this one did not,
    # and an agent that wanted the full API had to guess the import path.
    try:
        from geeViz import fsInsights as fs
    except Exception as _fs_err:
        fs = None
        _FS_IMPORT_ERROR = repr(_fs_err)
    else:
        _GM_IMPORT_ERROR = None
    # pandas and numpy are de-facto standard helpers the agent reaches for
    # constantly; pre-load them so `search_codebase(name="pd.DataFrame.to_markdown")`
    # and `search_codebase(module="pd", query="...")` resolve without requiring
    # the agent to `import pandas` inside run_code first. Both are already
    # geeViz dependencies (setup.py) and on the sandbox allowlist.
    # georest -- RCR's Esri/ArcGIS REST client, which geeViz.esriLib now
    # delegates to. Pre-loaded (submodules too, so dotted paths resolve)
    # for the same reason as pandas: search_codebase(module=
    # "georest.restesri.portal") has to find it, or an agent told to use
    # it concludes it does not exist. Its network access from run_code is
    # held to geeViz's SSRF policy by _connect_refusal.
    try:
        import georest as _georest_mod
        import georest.restesri.portal  # noqa: F401
        import georest.restesri.services  # noqa: F401
    except Exception:
        _georest_mod = None
    import pandas as _pd_mod
    import numpy as _np_mod

    # Each session gets its own Map instance for layer isolation
    session_map = gv.mapper() if session_id and session_id != _DEFAULT_SESSION_ID else gv.Map

    # Per-session save_file writes to session's output dir
    def _session_save_file(filename, content, mode="w"):
        return _safe_write_file(filename, content, mode, output_dir=sess.output_dir)

    sess._map_ref = session_map
    # Helpful stubs that fire when the agent accidentally tries to call an
    # MCP tool name as a Python function INSIDE run_code. The session audit
    # found NameError: search_datasets and NameError: geeviz_search_places
    # happening because the agent doesn't always remember MCP tools are
    # separate tool calls, not importable symbols. A clear runtime message
    # is more direct than the agent reading the rule in instructions.
    def _mcp_tool_stub(tool_name: str):
        def _raise(*_args, **_kwargs):
            raise NameError(
                f"'{tool_name}' is an MCP tool, not a Python function — call "
                f"it as a separate tool from the model layer, not inside "
                f"run_code. Inside run_code use ee.*/geeViz helpers (sal, "
                f"gil, cl, tl, rl, Map, etc.) for the equivalent operation."
            )
        _raise.__name__ = tool_name
        return _raise

    _ns_update = {
        "ee": ee,
        "Map": session_map,
        "gv": gv,
        "gil": gil,
        "sal": sal,
        "edw": edw,
        "georest": _georest_mod,
        "palettes": palettes,
        # Forecast wind/temperature/precipitation from ECMWF, GFS and
        # WeatherNext, plus Map.addWindLayer. Core, not optional: it
        # needs only ee and geeViz itself.
        "wx": wx,
        "weather": wx,
        "cl": cl,
        "tl": tl,
        "rl": rl,
        # Both aliases for each lib so search_codebase finds them either way.
        "pandas": _pd_mod,
        "pd": _pd_mod,
        "numpy": _np_mod,
        "np": _np_mod,
        "save_file": _session_save_file,
        # Clear-error stubs for MCP tool names the agent sometimes calls
        # from inside run_code as if they were Python functions.
        "search_datasets": _mcp_tool_stub("search_datasets"),
        "search_codebase": _mcp_tool_stub("search_codebase"),
        "inspect_asset": _mcp_tool_stub("inspect_asset"),
        "map_control": _mcp_tool_stub("map_control"),
        "env_info": _mcp_tool_stub("env_info"),
        "view_output": _mcp_tool_stub("view_output"),
        "manage_asset": _mcp_tool_stub("manage_asset"),
        "export_image": _mcp_tool_stub("export_image"),
        "save_session": _mcp_tool_stub("save_session"),
        "__builtins__": _make_safe_builtins(),
    }
    # Only expose gm when googleMapsLib actually loaded — otherwise
    # `gm.geocode(...)` would AttributeError on None, which is worse than
    # a plain NameError telling the user the module isn't installed.
    if gm is not None:
        _ns_update["gm"] = gm
    # Both spellings, matching the pd/pandas pattern above, so
    # search_codebase(module=...) resolves whichever the agent tries.
    if fs is not None:
        _ns_update["fs"] = fs
        _ns_update["fsInsights"] = fs

    # inventoryLib.inventory_area writes reports only when ``output_dir``
    # is passed. Without the wrapper below, an agent that forgets the
    # kwarg gets DataFrames but no HTML/JSON/MD files, and then when the
    # user asks "show me the report" the agent has to either re-run the
    # whole (expensive) inventory or work from the return dict manually.
    # Default output_dir to the session's isolated output dir so reports
    # are always on disk, viewable via the run_code output_markdown scan.
    # Also RESOLVE any relative ``output_dir`` against ``sess.output_dir``
    # so `output_dir='generated_outputs'` lands under the session dir
    # instead of process cwd (where the file-scanner wouldn't see it).
    # An explicit ``output_dir=None`` from the caller still opts out.
    # The wrapper is applied to BOTH ``inventoryLib.inventory_area``
    # (bare name in the REPL) AND ``googleMapsLib.inventory_area``
    # (agent's usual ``gm.inventory_area`` call path). Without patching
    # both, callers picking the ``gm.`` route silently bypass the auto-
    # default and their reports vanish into process cwd.
    try:
        import geeViz.inventoryLib as _inv_mod
        import geeViz.googleMapsLib as _gm_mod
        import functools as _ft
        import os as _os_wrap
        _orig_inventory_area = _inv_mod.inventory_area
        _INV_UNSET = object()
        @_ft.wraps(_orig_inventory_area)
        def _session_inventory_area(*args, output_dir=_INV_UNSET, **kwargs):
            if output_dir is _INV_UNSET:
                output_dir = sess.output_dir
            elif isinstance(output_dir, str) and output_dir and not _os_wrap.path.isabs(output_dir):
                output_dir = _os_wrap.path.join(sess.output_dir, output_dir)
            return _orig_inventory_area(*args, output_dir=output_dir, **kwargs)
        _ns_update["inventory_area"] = _session_inventory_area
        # Patch the re-export in googleMapsLib too so ``gm.inventory_area``
        # (the agent's usual entry point) picks up the same default.
        # Preserve the original for tests/restore.
        _gm_mod._orig_inventory_area = getattr(_gm_mod, "inventory_area", None)
        _gm_mod.inventory_area = _session_inventory_area
    except Exception:
        # Any import/wrap failure falls back to the un-injected name —
        # agent can still ``from geeViz.inventoryLib import inventory_area``
        # inside run_code and pass output_dir explicitly.
        pass

    sess.namespace.update(_ns_update)
    sess.initialized = True
    return sess


def _reset_namespace(session_id: str | None = None):
    """Clear and re-populate a session's REPL namespace. Also resets code history."""
    sess = _get_session(session_id)
    sess.namespace.clear()
    sess.code_history.clear()
    sess.code_history_meta.clear()
    sess.current_script_path = None
    sess.initialized = False
    _ensure_initialized(session_id)


# ---------------------------------------------------------------------------
# Per-block dependency analysis + backward-slicing helpers.
#
# Purpose: the "download session as script" flow used to concatenate every
# successful run_code block, exploratory noise and all — heavy, hard to
# reproduce, hard for a user to hand to a colleague. The tracker below
# records what each block BINDS and READS as it executes; the slicer walks
# the resulting DAG backward from the last successful block, keeping only
# ancestors whose bindings the final state actually depends on. Import
# blocks and blocks containing wildcard imports are always kept because
# their effects can't be traced by name-binding alone.
#
# This is the Level 2 approach from the design discussion — AST analysis
# for reads/writes plus a namespace snapshot diff for ground-truth
# bindings, no IPython kernel or ipyflow dependency required. Overhead is
# a few milliseconds per block; the exact-name accuracy comes from
# reading the namespace after exec, not from static guessing.
# ---------------------------------------------------------------------------


def _analyze_block_ast(source: str) -> dict:
    """Static AST analysis of a single code block.

    Returns a dict with:
      - ``read``: names read as ``ast.Load`` context (approximate; may
        include names later bound in the same block — the caller can
        subtract those out).
      - ``bound_static``: names in ``ast.Store`` context, function/class
        defs, import aliases, function params. Used as a fallback when
        the runtime snapshot-diff isn't available (e.g. failed blocks).
      - ``touched``: names on the LHS of subscript-store (``x[k] = v``)
        or attribute-store (``x.a = v``). These are mutations that
        static Store-name analysis alone would miss because they don't
        (re)bind ``x`` itself.
      - ``is_import``: True if the block contains any Import / ImportFrom.
        Import blocks are ALWAYS kept in the slice — their side effects
        (loading modules, registering hooks, etc.) don't appear as name
        reads downstream but the script won't run without them.
      - ``wildcard_import``: True if the block does ``from X import *``.
        Wildcard imports bind an unknowable set of names, so slicing
        past them is unsafe — always keep them.
      - ``parse_error``: True if the source didn't parse at all. The
        caller should treat unparseable blocks as opaque (always-kept).

    Best-effort: if AST parsing fails, returns a conservative "keep me"
    dict rather than raising.
    """
    result = {
        "read": set(),
        "bound_static": set(),
        "touched": set(),
        "is_import": False,
        "wildcard_import": False,
        "parse_error": False,
    }
    try:
        tree = ast.parse(source)
    except SyntaxError:
        result["parse_error"] = True
        return result

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result["is_import"] = True
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                result["bound_static"].add(bound)
        elif isinstance(node, ast.ImportFrom):
            result["is_import"] = True
            for alias in node.names:
                if alias.name == "*":
                    result["wildcard_import"] = True
                else:
                    bound = alias.asname or alias.name
                    result["bound_static"].add(bound)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            result["bound_static"].add(node.name)
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Store):
                result["bound_static"].add(node.id)
            elif isinstance(node.ctx, ast.Load):
                result["read"].add(node.id)
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
            # ``df["x"] = 5`` — record the ROOT name as touched (df).
            root = node.value
            while isinstance(root, ast.Subscript):
                root = root.value
            if isinstance(root, ast.Name):
                result["touched"].add(root.id)
            elif isinstance(root, ast.Attribute):
                # ``df.iloc[0] = 5`` — walk attributes back to the root Name.
                while isinstance(root, ast.Attribute):
                    root = root.value
                if isinstance(root, ast.Name):
                    result["touched"].add(root.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
            # ``model.data = X`` — record ``model`` as touched.
            root = node.value
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                result["touched"].add(root.id)

    # Subtract bound-in-this-block from read: a name defined earlier in
    # the block is not a "free variable" of the block. We don't do full
    # flow analysis (which would need to track scope-order), so this is
    # an over-approximation — a name defined LATER in the block that's
    # also read EARLIER stays in read. That's fine; slicing conservatively
    # over-keeps rather than under-keeps.
    result["read"] -= result["bound_static"]
    # Also don't count a name as read if it's ONLY in the touched set
    # (touched implies read as well, so this is redundant to keep both).
    # ``touched`` remains its own set so the slicer can distinguish
    # "b reads a" (only ancestors that BIND a matter) from "b touches a"
    # (also every ancestor that touched a AFTER the last binder matters).
    return result


def _snapshot_namespace_ids(ns: dict) -> dict:
    """Snapshot ``{name: id(obj)}`` for user-facing names in a namespace.

    Skips dunder names and callables that came from the REPL bootstrap so
    the diff doesn't drown in framework noise. Cheap — one dict comprehension.
    """
    return {
        name: id(obj)
        for name, obj in ns.items()
        if not name.startswith("_")
    }


def _diff_namespace(before: dict, after: dict, skip_names: set = None) -> set:
    """Names in ``after`` that are new OR rebound relative to ``before``.

    ``skip_names`` filters out framework-bootstrap names so we don't count
    (e.g.) ``ee``, ``Map`` as newly bound every block. The caller
    typically passes the REPL bootstrap set.
    """
    skip_names = skip_names or set()
    bound = set()
    for name, obj_id in after.items():
        if name in skip_names:
            continue
        if name not in before or before[name] != obj_id:
            bound.add(name)
    return bound


# Names pre-populated by the REPL bootstrap. Excluded from
# ``names_bound`` diffs so they don't appear to be "defined" by every
# block that happens to reference them.
_REPL_BOOTSTRAP_NAMES = {
    "ee", "Map", "gv", "gil", "sal", "cl", "tl", "rl", "gm",
    "palettes", "save_file", "__builtins__",
}


def _slice_history(sess: "_SessionState") -> list[int]:
    """Return the list of ``code_history`` indexes to keep in the slice.

    Anchor: the LAST block with ``succeeded=True``. Every earlier block
    that binds or touches a name transitively read/touched by the anchor
    is included. Import blocks and wildcard-import blocks are always
    included. Unparseable blocks (``parse_error=True``) are always
    included (we can't tell what they do statically).

    Returns indexes in original chronological order. If the metadata is
    missing (e.g. legacy session before the tracker was added), falls
    back to "keep everything" so no data is lost.
    """
    meta = sess.code_history_meta
    if not meta or len(meta) != len(sess.code_history):
        return list(range(len(sess.code_history)))

    # Anchor = last succeeded block. If none, no slice — return the whole
    # history (nothing "worked" so the user gets everything they tried).
    anchor_idx = None
    for i in range(len(meta) - 1, -1, -1):
        if meta[i].get("succeeded"):
            anchor_idx = i
            break
    if anchor_idx is None:
        return list(range(len(sess.code_history)))

    keep = set()
    # Frontier: names we still need to explain. Start with the anchor's
    # reads + touches. Blocks reachable from any of these names get
    # walked and their own reads/touches added to the frontier.
    frontier = set(meta[anchor_idx].get("names_read", set())) | set(
        meta[anchor_idx].get("names_touched", set())
    )
    keep.add(anchor_idx)

    # Walk backward. For each earlier block, add it to the slice if it
    # (a) binds a name currently in the frontier — that block PRODUCES a
    # value the future depends on, OR (b) touches a name in the frontier
    # after it was last bound (its mutation is part of the state the
    # future observes), OR (c) is an import block, OR (d) has a
    # wildcard import, OR (e) failed to parse. Each newly-included block
    # extends the frontier with its own reads and touches.
    for i in range(anchor_idx - 1, -1, -1):
        m = meta[i]
        include = False
        if m.get("is_import") or m.get("wildcard_import") or m.get("parse_error"):
            include = True
        else:
            bound = set(m.get("names_bound", set()))
            touched = set(m.get("names_touched", set()))
            if bound & frontier or touched & frontier:
                include = True
        if include:
            keep.add(i)
            frontier |= set(m.get("names_read", set()))
            frontier |= set(m.get("names_touched", set()))
            # A block that binds a name removes it from the frontier
            # for even-earlier ancestors: something UPSTREAM only
            # matters if the current block DOESN'T fully define what
            # downstream needs. This is the standard slicing rule.
            frontier -= set(m.get("names_bound", set()))

    return sorted(keep)


def _save_history_to_file_sliced(sess: "_SessionState") -> str:
    """Write the SLICED code history to a timestamped .py file.

    Same header as ``_save_history_to_file`` but only emits the blocks
    that contribute to the final successful state. Sets
    ``sess.current_script_path`` so subsequent saves overwrite the same
    file (mirrors the legacy behavior).
    """
    import datetime
    os.makedirs(sess.script_dir, exist_ok=True)
    if sess.current_script_path is None:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        sess.current_script_path = os.path.join(
            sess.script_dir, f"session_{ts}.py",
        )

    keep_idxs = _slice_history(sess)
    total = len(sess.code_history)
    dropped = total - len(keep_idxs)

    header = (
        "# Auto-generated by geeViz MCP server (sliced export).\n"
        f"# Retained {len(keep_idxs)} of {total} run_code blocks; "
        f"{dropped} exploratory/dead block(s) dropped.\n"
        "# Backward-slice anchor: the last successful block.\n\n"
        "import geeViz.geeView as gv\n"
        "import geeViz.getImagesLib as gil\n"
        "import geeViz.getSummaryAreasLib as sal\n"
        "import geeViz.edwLib as edw\n"
        "import geeViz.googleMapsLib as gm\n"
        "from geeViz.outputLib import charts as cl\n"
        "from geeViz.outputLib import thumbs as tl\n"
        "from geeViz.outputLib import reports as rl\n"
        "ee = gv.ee\n"
        "Map = gv.Map\n\n"
    )
    body_parts = []
    for out_i, orig_i in enumerate(keep_idxs, 1):
        block = sess.code_history[orig_i]
        body_parts.append(
            f"# --- block {out_i} (originally call #{orig_i + 1}) ---\n{block}"
        )
    with open(sess.current_script_path, "w", encoding="utf-8") as f:
        f.write(header + "\n\n".join(body_parts) + "\n")
    return sess.current_script_path


def _save_history_to_notebook_sliced(sess: "_SessionState",
                                       nb_path: str) -> str:
    """Emit the sliced code history as an .ipynb notebook.

    Same notebook structure as the legacy save_session ipynb path (one
    markdown header cell, one setup cell with the pre-populated imports,
    one code cell per surviving block) but only surviving blocks are
    emitted. Retention count is written into the header cell so the
    user knows what was pruned.

    Uses ``nbformat`` (already a hard dep of the framework) for the file
    write.
    """
    import datetime
    import sys as _sys
    keep_idxs = _slice_history(sess)
    total = len(sess.code_history)
    dropped = total - len(keep_idxs)

    cells: list[dict] = []
    cells.append({
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "# geeViz MCP Session (sliced export)\n",
            "\n",
            f"Auto-generated on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.\n",
            f"Retained **{len(keep_idxs)}** of **{total}** run_code blocks; "
            f"**{dropped}** exploratory/dead block(s) dropped.\n",
        ],
    })
    cells.append({
        "cell_type": "code",
        "metadata": {},
        "source": [
            "import geeViz.geeView as gv\n",
            "import geeViz.getImagesLib as gil\n",
            "import geeViz.getSummaryAreasLib as sal\n",
            "from geeViz.outputLib import charts as cl\n",
            "from geeViz.outputLib import thumbs as tl\n",
            "from geeViz.outputLib import reports as rl\n",
            "ee = gv.ee\n",
            "Map = gv.Map",
        ],
        "execution_count": None,
        "outputs": [],
    })
    for out_i, orig_i in enumerate(keep_idxs, 1):
        block = sess.code_history[orig_i]
        lines = block.splitlines(True)
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        cells.append({
            "cell_type": "code",
            "metadata": {"originally_call": orig_i + 1, "slice_index": out_i},
            "source": lines,
            "execution_count": None,
            "outputs": [],
        })

    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": _sys.version.split()[0],
            },
        },
        "cells": cells,
    }
    os.makedirs(os.path.dirname(nb_path) or ".", exist_ok=True)
    with open(nb_path, "w", encoding="utf-8") as f:
        json.dump(notebook, f, indent=1, ensure_ascii=False)
    return nb_path


def _save_history_to_file(sess: _SessionState) -> str:
    """Write accumulated code history to a timestamped .py file. Returns the path."""
    import datetime
    os.makedirs(sess.script_dir, exist_ok=True)
    if sess.current_script_path is None:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        sess.current_script_path = os.path.join(sess.script_dir, f"session_{ts}.py")
    header = (
        "# Auto-generated by geeViz MCP server\n"
        "# Each section below is one run_code call, in order.\n\n"
        "import geeViz.geeView as gv\n"
        "import geeViz.getImagesLib as gil\n"
        "import geeViz.getSummaryAreasLib as sal\n"
        "import geeViz.edwLib as edw\n"
        "import geeViz.googleMapsLib as gm\n"
        "from geeViz.outputLib import charts as cl\n"
        "from geeViz.outputLib import thumbs as tl\n"
        "from geeViz.outputLib import reports as rl\n"
        "ee = gv.ee\n"
        "Map = gv.Map\n\n"
    )
    body = "\n\n".join(
        f"# --- run_code call {i+1} ---\n{block}"
        for i, block in enumerate(sess.code_history)
    )
    with open(sess.current_script_path, "w", encoding="utf-8") as f:
        f.write(header + body + "\n")
    return sess.current_script_path


# ---------------------------------------------------------------------------
# Tool 1: run_code
# ---------------------------------------------------------------------------
import ast
import asyncio
import io
import contextlib
import traceback


# Collection type names that are dangerous to call .getInfo() on without .limit()
_COLLECTION_NAMES = {"ImageCollection", "FeatureCollection"}

# ---------------------------------------------------------------------------
# Security: Tier 1 hardening for run_code
# ---------------------------------------------------------------------------

# Modules that are blocked from import in run_code. These provide OS/network/process
# access that is unnecessary for Earth Engine workflows and dangerous if the server
# is exposed remotely.
_BLOCKED_MODULES = frozenset({
    # Kept in sync with _AUDIT_BLOCKED_IMPORTS in the audit-hook block
    # near the top of this file. If you add here, add there too — the
    # two layers are defense-in-depth and MUST agree, otherwise an
    # attacker who bypasses one still hits the other.
    # ── Filesystem / process ──
    "os", "sys", "subprocess", "shutil", "pathlib", "tempfile", "glob",
    "mmap", "fcntl", "msvcrt", "resource", "signal", "ctypes",
    # ── Network ──
    "socket", "http", "urllib", "requests", "ssl", "asyncio",
    # The HTTP stack UNDER requests/urllib. Blocking the friendly
    # wrappers while leaving these importable blocks nothing: verified
    # by making a real outbound GET from sandboxed run_code with
    # ``urllib3.PoolManager().request(...)`` — status 200, 559 bytes,
    # while ``import requests`` on the line above was refused.
    # httpx / aiohttp / httplib2 / websocket ship as transitive deps and
    # were equally importable.
    "urllib3", "httpx", "httpcore", "h11", "h2", "hpack",
    "aiohttp", "aiohappyeyeballs", "aiosignal", "yarl",
    "httplib2", "websocket", "websockets", "curl_cffi", "socks",
    "socketserver", "ftplib",
    "select", "selectors", "smtplib", "poplib", "imaplib",
    "telnetlib", "nntplib", "xmlrpc",
    # ── Concurrency ──
    "threading", "multiprocessing",
    # ── Dynamic import / code exec ──
    "importlib", "marshal", "runpy", "zipimport", "builtins",
    "code", "codeop", "compileall", "py_compile",
    # ── Introspection ──
    "gc", "inspect", "dis", "traceback",
    # ── Archives / serialization ──
    "zipfile", "tarfile", "gzip", "bz2", "lzma",
    "pickle", "shelve", "dbm", "sqlite3",
    # ── Misc ──
    "pty", "pipes", "webbrowser", "getpass",
})
# Note: ``io`` is NOT blocked. ``io.BytesIO`` / ``io.StringIO`` are
# essential for the matplotlib → PIL → ``save_file`` flow and are pure
# in-memory objects with no filesystem access. The dangerous parts of
# io (``io.open``, ``io.FileIO``) require a file path that the sandbox
# doesn't grant anyway — and ``open`` is already blocked as a builtin.

# !!! NOT ENFORCED — this list is currently INERT. !!!
#
# It is defined here and extended by MCP_EXTRA_ALLOWED_MODULES below, and
# then nothing reads it. Verified: `uuid`, `hashlib`, `base64`, `csv`,
# `random`, `typing` and `warnings` are all absent from this tuple and
# all import successfully under --sandbox. It is also why scipy and
# scikit-learn worked the moment they were installed, with no config
# change.
#
# So the real import policy is the DENY list (_BLOCKED_MODULES) plus the
# AST rules in _check_code_patterns — a denylist, with the well-known
# denylist problem that every path to a capability must be enumerated.
# Three holes found in one session (urllib3 behind requests,
# pd.read_pickle behind pickle, gil.os behind os) were all that shape.
#
# Left in place rather than deleted because switching to real allowlist
# enforcement is a live design question, and the answer is not obviously
# "yes": an allowlist is stricter, and the agent is already reported as
# over-constrained. Whoever picks that up should decide deliberately —
# but until then, DO NOT read this tuple as a control that exists, and
# do not set MCP_EXTRA_ALLOWED_MODULES expecting it to do anything.
#
# Original intent, kept for whoever wires it up: top-level module
# prefixes allowed in import statements; anything not matching these AND
# not in _BLOCKED_MODULES was meant to warn rather than hard-block, so
# legitimate but uncommon imports keep working.
_ALLOWED_MODULE_PREFIXES = (
    "ee", "geeViz", "json", "datetime", "math", "collections",
    "numpy", "np", "pandas", "pd", "plotly", "copy", "re",
    "functools", "itertools", "operator", "statistics",
    "pprint", "textwrap", "string", "decimal", "fractions",
    # Plotting libraries the agent reaches for in exploration.
    # Available iff the agent runtime installs them (see Dockerfile).
    # ``cl.apply_theme(...)`` themes their output to match geeViz charts.
    "matplotlib", "seaborn", "mpl_toolkits", "io",
)

# Per-deployment additions — comma-separated env var. Lets a tenant
# config enable extra libraries (e.g. ``altair``, ``bokeh``, ``sklearn``)
# without forking the code. Each addition is still a security review;
# don't set this casually.
_EXTRA_ALLOWED = tuple(
    p.strip() for p in os.environ.get("MCP_EXTRA_ALLOWED_MODULES", "").split(",")
    if p.strip()
)
if _EXTRA_ALLOWED:
    _ALLOWED_MODULE_PREFIXES = _ALLOWED_MODULE_PREFIXES + _EXTRA_ALLOWED

# Builtins that are blocked from the execution namespace.
#: Calls that deserialize pickled data. Blocked in sandbox mode because
#: unpickling runs whatever the file says to run, and the sandbox hands
#: user code a working file-write primitive (``save_file``). Verified
#: exploitable via both pandas and numpy before this existed.
#:
#: Matched on the ATTRIBUTE NAME, so ``pd.read_pickle``,
#: ``pandas.read_pickle`` and ``read_pickle`` are all caught without
#: having to guess how the module was aliased.
_UNPICKLING_CALLS = frozenset({
    "read_pickle",      # pandas
    "loads",            # pickle.loads / joblib.loads, if either is reached
    "load_npz",         # scipy.sparse — unpickles object arrays
})

#: Module names that must not be reachable as an ATTRIBUTE of something
#: else. Any module that does ``import os`` at the top re-exports it:
#: ``gil.os``, ``gv.os`` and ``cl.os`` are all the real os module, so the
#: import blocklist — which only sees ``import`` statements — never fired.
#:
#: Demonstrated against a live sandbox: ``gv.os.environ`` listed
#: GEMINI_API_KEY and GOOGLE_MAPS_PLATFORM_API_KEY with values present,
#: and ``cl.os.listdir('.')`` walked the filesystem. ``gil.os.system()``
#: was already caught, but only because the audit hook watches that one
#: SYSCALL — reading os.environ raises no audit event at all.
#:
#: Deliberately NOT the whole of _BLOCKED_MODULES. Several entries there
#: are ordinary attribute names in analysis code and blocking them would
#: break real work:
#:   select   -> ee.Image.select(), the single most used call in geeViz
#:   signal   -> scipy.signal
#:   code     -> a status code on a response object
#:   resource, glob, io -> common field names
#: This list is the intersection of "dangerous when traversed" and
#: "never a legitimate attribute in this codebase".
_BLOCKED_MODULE_ATTRS = frozenset({
    "os", "sys", "subprocess", "shutil", "pathlib", "tempfile",
    "socket", "requests", "urllib", "urllib3", "httpx", "httpcore",
    "aiohttp", "httplib2", "websocket", "smtplib", "ftplib",
    "importlib", "marshal", "runpy", "zipimport", "builtins", "ctypes",
    "pickle", "shelve", "dbm", "sqlite3", "multiprocessing",
    "threading", "webbrowser", "getpass", "mmap",
})

_BLOCKED_BUILTINS = frozenset({
    "__import__", "eval", "exec", "compile", "open",
    "breakpoint", "exit", "quit",
    "globals", "locals", "vars",
    "getattr", "setattr", "delattr",
})

# Attribute accesses (``.__class__``, ``.__bases__``, ``.__subclasses__``,
# etc.) that enable the classic ``().__class__.__bases__[0].__subclasses__()``
# pyjail escape — an attacker walks from any literal up to ``object`` then
# enumerates every live subclass to find one that shells out (usually
# ``os._wrap_close`` or similar). Blocking ANY link in that chain kills
# the attack. We block the whole set — none of these are needed for
# legitimate geospatial analysis code. Frame introspection (``f_globals``
# / ``f_back``) is added because it's a second escape vector: get a
# frame, read its globals, find the trusted ``os`` reference the tool
# server itself imported.
_BLOCKED_DUNDER_ATTRS = frozenset({
    # Object model walk
    "__class__", "__bases__", "__subclasses__", "__mro__",
    # Function / code object introspection (can extract bytecode,
    # closures, source, module globals of any function)
    "__globals__", "__builtins__", "__code__", "__closure__",
    "__wrapped__", "__self__", "__func__",
    # Import / loader introspection
    "__loader__", "__spec__", "__import__",
    # Frame introspection — reachable via sys._getframe() (sys is
    # module-blocked but a trusted lib could accidentally expose a
    # frame object)
    "f_globals", "f_back", "f_locals", "f_builtins", "f_code", "f_trace",
    # Generic escape roots
    "__reduce__", "__reduce_ex__",   # pickle protocol → arbitrary construct
    "__getattribute__",              # bypass __getattr__ hooks
})


def _safe_write_file(filename: str, content: str, mode: str = "w",
                     output_dir: str | None = None) -> str:
    """Write content to a file in the safe output directory.

    Only allows writing to geeViz/mcp/generated_outputs/ (or a session
    subdirectory) to prevent arbitrary file system access.

    Args:
        filename: Just the filename (no directory). e.g. "chart.html"
        content: String content to write.
        mode: Write mode, "w" (text) or "wb" (binary). Default "w".
        output_dir: Override output directory (used for session isolation).

    Returns:
        Full path to the written file.
    """
    _out = output_dir or _output_dir
    safe_name = os.path.basename(filename)
    if not safe_name:
        raise ValueError("filename must not be empty")
    os.makedirs(_out, exist_ok=True)
    full_path = os.path.join(_out, safe_name)
    # Auto-detect mode from content type
    if isinstance(content, bytes):
        mode = "wb"
    elif isinstance(content, str):
        mode = "w"
    kwargs = {"encoding": "utf-8"} if "b" not in mode else {}
    with open(full_path, mode, **kwargs) as f:
        f.write(content)
    return full_path


def _make_safe_builtins() -> dict:
    """Return a copy of __builtins__, optionally with dangerous functions removed.

    When sandbox is disabled (local/stdio use), returns the full builtins dict
    so that run_code has unrestricted Python access.
    """
    import builtins
    if not _SANDBOX_ENABLED:  # False or None (unresolved) → no restrictions
        # No restrictions — full Python access
        return dict(vars(builtins))
    safe = {k: v for k, v in vars(builtins).items() if k not in _BLOCKED_BUILTINS}
    # Provide a safe __import__ that blocks dangerous modules
    def _safe_import(name, *args, **kwargs):
        top = name.split(".")[0]
        if top in _BLOCKED_MODULES:
            raise ImportError(
                f"Import of '{name}' is blocked for security. "
                f"Only Earth Engine, geeViz, and standard data libraries are allowed."
            )
        return __builtins__["__import__"](name, *args, **kwargs) if isinstance(__builtins__, dict) \
            else builtins.__import__(name, *args, **kwargs)
    safe["__import__"] = _safe_import
    return safe


def _check_code_patterns(code: str) -> list[str]:
    """AST analysis: detect risky EE patterns AND blocked security patterns.

    Returns a list of warning/error strings. Strings starting with "BLOCKED:"
    will cause run_code to refuse execution.

    When sandbox is disabled, security checks (import blocking, builtin blocking)
    are skipped — only EE performance warnings are emitted.
    """
    warnings: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return warnings  # let the executor report syntax errors

    # Per-module remediation hints — every one of these is a wrong path the
    # agent has tried in a real session, so tell it what to do instead
    # instead of just saying "no". Prevents the "try requests → try urllib
    # → try httpx → try pandas.read_json" thrash cycle when a bare
    # "blocked" message isn't enough of a nudge.
    _BLOCKED_MODULE_HINTS = {
        "requests":   "HTTP libraries are unavailable in the sandbox. Use the domain wrapper: Map.addEsriFeatureService(url) (draw) or georest.restesri (search / metadata / query) for ArcGIS / AGOL / .arcgis.com URLs, edwLib for USFS EDW, sal.* for census/counties/parks, ee.FeatureCollection.runBigQuery(sql, geometryColumn='geom') for BigQuery. Do NOT retry with urllib / httpx / aiohttp / pandas.read_json — same block.",
        "urllib":     "HTTP libraries are unavailable in the sandbox. See georest / Map.addEsri* / edwLib / sal / ee.FeatureCollection.runBigQuery. Trying a different HTTP library will not work — the block is intentional.",
        "httpx":      "HTTP libraries are unavailable in the sandbox. Use the domain wrapper for the data source (georest, edwLib, sal, ee.FeatureCollection.runBigQuery).",
        "aiohttp":    "HTTP libraries are unavailable in the sandbox. Use the domain wrapper for the data source (georest, edwLib, sal, ee.FeatureCollection.runBigQuery).",
        "os":         "os is blocked. Use save_file(path, bytes) for output, and let geeViz/EE handle any filesystem or environment access.",
        "subprocess": "subprocess is blocked. Use geeViz helpers instead of shelling out.",
        "socket":     "Raw sockets are blocked. Route network access through a domain wrapper (georest, edwLib, sal, gm, ee).",
        "shutil":     "shutil is blocked. If you need to save a file, use save_file(path, bytes).",
        "pathlib":    "pathlib is blocked. Filesystem work goes through save_file / view_output; you don't need to build paths manually.",
        "inspect":    "inspect is blocked. To check a function's signature or whether it exists, call the MCP tool search_codebase(module='<lib>', name='<fn>') from the model layer — do NOT try to introspect via Python. Same for pydoc / dis / types.",
        "pydoc":      "pydoc is blocked. Use the MCP tool search_codebase(module='<lib>', name='<fn>') to look up functions and docstrings.",
        "dis":        "dis is blocked. Bytecode introspection isn't available in the sandbox — use search_codebase to read source.",
        "importlib":  "importlib is blocked (dynamic import escape). All modules must be imported statically via a top-level `import` statement; if the module isn't in the allowed list, no runtime import path will unblock it.",
    }
    def _hint_for(name: str) -> str:
        top = name.split(".")[0]
        return _BLOCKED_MODULE_HINTS.get(top,
            "Only Earth Engine, geeViz, and standard data libraries are permitted.")

    for node in ast.walk(tree):
        if _SANDBOX_ENABLED:
            # --- Security: check imports (sandbox only) ---
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in _BLOCKED_MODULES:
                        warnings.append(
                            f"BLOCKED: import of '{alias.name}' is not allowed. "
                            f"{_hint_for(alias.name)}"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top = node.module.split(".")[0]
                    if top in _BLOCKED_MODULES:
                        warnings.append(
                            f"BLOCKED: import from '{node.module}' is not allowed. "
                            f"{_hint_for(node.module)}"
                        )

            # --- Security: check for dangerous builtin calls (sandbox only) ---
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in ("eval", "exec", "compile", "open", "breakpoint", "__import__"):
                    warnings.append(
                        f"BLOCKED: call to '{node.func.id}()' is not allowed for security."
                    )
            # --- Security: block dunder-attribute escape chains (sandbox only) ---
            # Covers ``().__class__.__bases__[0].__subclasses__()`` and
            # every variant that walks the object model to reach ``os`` or
            # any trusted-lib global. See _BLOCKED_DUNDER_ATTRS for the
            # full list + rationale.
            if isinstance(node, ast.Attribute) and node.attr in _BLOCKED_DUNDER_ATTRS:
                warnings.append(
                    f"BLOCKED: attribute access '.{node.attr}' is not allowed. "
                    f"This dunder is a common sandbox-escape vector."
                )
            # Module re-export traversal — see _BLOCKED_MODULE_ATTRS.
            # getattr() is already blocked as a builtin, so refusing the
            # static form closes the dynamic one too.
            if (isinstance(node, ast.Attribute)
                    and node.attr in _BLOCKED_MODULE_ATTRS):
                warnings.append(
                    f"BLOCKED: '.{node.attr}' reaches a restricted module "
                    f"through another one. Modules that import "
                    f"'{node.attr}' re-export it, so this is the same as "
                    f"importing it directly."
                )

        # --- Deserialization back doors (sandbox only) --------------
        # ``pickle`` is already blocked as a module, but several libraries
        # that ARE available will unpickle for you from a trusted frame,
        # which turns attacker-chosen bytes into arbitrary code execution.
        #
        # Demonstrated end to end against this sandbox with no extra
        # dependencies:
        #
        #   save_file('x.pkl', <bytes whose __reduce__ calls anything>)
        #   pd.read_pickle(path)        -> executed
        #   np.load(path, allow_pickle=True) -> executed
        #
        # ``save_file`` is deliberately exposed and pandas/numpy are
        # deliberately available, so the write half and the read half are
        # both legitimate on their own. Blocking the READ is the narrow
        # fix: nothing in a geospatial analysis needs to unpickle a file
        # the same session just wrote.
        #
        # np.load WITHOUT allow_pickle is fine (plain .npy arrays cannot
        # execute), so only the pickle-enabling form is refused.
        if _SANDBOX_ENABLED and isinstance(node, ast.Call):
            _fname = ""
            if isinstance(node.func, ast.Attribute):
                _fname = node.func.attr
            elif isinstance(node.func, ast.Name):
                _fname = node.func.id
            if _fname in _UNPICKLING_CALLS:
                warnings.append(
                    f"BLOCKED: '{_fname}()' deserializes pickled data, which "
                    f"executes arbitrary code. Load data with a format that "
                    f"cannot execute — pd.read_csv / pd.read_parquet / "
                    f"pd.read_json, or np.loadtxt."
                )
            if _fname == "load":
                for _kw in node.keywords:
                    if _kw.arg == "allow_pickle" and not (
                            isinstance(_kw.value, ast.Constant)
                            and _kw.value.value is False):
                        warnings.append(
                            "BLOCKED: allow_pickle=True executes arbitrary "
                            "code from the file being loaded. Save and load "
                            "plain arrays instead (np.save writes .npy that "
                            "loads fine without allow_pickle)."
                        )

        # --- Batch export blocking (sandbox only): block .start() and task.start() ---
        # Export wrapper functions are allowed (they support start=False),
        # but actually starting tasks is blocked in sandbox mode.
        if _SANDBOX_ENABLED:
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "start":
                    warnings.append(
                        "BLOCKED: .start() calls are not allowed in this environment. "
                        "Batch exports (to Assets, Drive, or Cloud Storage) cannot run here. "
                        "Download the code using the Download button and run it locally to execute exports."
                    )

        # --- EE performance: detect .getInfo() calls (always active) ---
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "getInfo"):
            continue

        # Check if .getInfo() is inside a for/while loop — BLOCKED, not just a warning
        for parent in ast.walk(tree):
            if isinstance(parent, (ast.For, ast.While)):
                for child in ast.walk(parent):
                    if child is node:
                        warnings.append(
                            "BLOCKED: .getInfo() inside a loop is not allowed — it causes "
                            "extreme slowness (one server round-trip per iteration). "
                            "Use server-side operations instead: ee.List, ee.Dictionary, "
                            ".map(), or pass the full collection to cl.summarize_and_chart()."
                        )
                        break

        # Check for .getInfo() on a collection without .limit()
        target = node.func.value
        chain = _get_method_chain(target)
        has_limit = "limit" in chain or "first" in chain
        has_collection = any(name in _COLLECTION_NAMES for name in chain)
        if has_collection and not has_limit:
            warnings.append(
                "Warning: .getInfo() on a collection without .limit() can be very slow. "
                "Consider adding .limit(N) or using .first().getInfo()."
            )

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    return unique


def _get_method_chain(node: ast.AST) -> list[str]:
    """Walk an attribute/call chain and return method/attribute names encountered."""
    names: list[str] = []
    current = node
    while True:
        if isinstance(current, ast.Call):
            current = current.func
        elif isinstance(current, ast.Attribute):
            names.append(current.attr)
            current = current.value
        elif isinstance(current, ast.Name):
            names.append(current.id)
            break
        else:
            break
    return names


def _save_and_clean_result(result_val):
    """Save any binary/HTML outputs to files and return a small, JSON-safe result.

    Walks the result value, saves bytes to .png/.gif files and large HTML
    to .html files in generated_outputs/, then returns a clean dict/string
    with file paths instead of raw data. Guaranteed to be small and
    JSON-serializable.
    """
    if result_val is None:
        return None

    import time as _t
    os.makedirs(_output_dir, exist_ok=True)
    ts = int(_t.time())

    _EXT_MAP = {"image": ".png"}

    def _clean(obj, depth=0):
        if depth > 5:
            return "<nested too deep>"
        if isinstance(obj, (bytes, bytearray)):
            # Save bytes to file, return path
            fname = f"output_{ts}_{id(obj) % 10000}.bin"
            fpath = os.path.join(_output_dir, fname).replace("\\", "/")
            with open(fpath, "wb") as f:
                f.write(obj)
            return f"saved to {fpath}"
        if isinstance(obj, str):
            if len(obj) > 10000 and ("data:image" in obj or "<html" in obj.lower()
                                      or "data:text/html" in obj):
                # Large HTML or data URI — save to file
                fname = f"output_{ts}_{id(obj) % 10000}.html"
                fpath = os.path.join(_output_dir, fname).replace("\\", "/")
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(obj)
                return f"saved to {fpath}"
            if len(obj) > 5000:
                return obj[:200] + f"... <truncated, {len(obj)} chars>"
            return obj
        if isinstance(obj, dict):
            clean = {}
            for k, v in obj.items():
                # Use known extension for common keys
                if isinstance(v, (bytes, bytearray)) and len(v) > 0:
                    if k == "bytes":
                        # Use sibling "format" key to determine extension
                        fmt = obj.get("format", "png")
                        ext = f".{fmt}"
                    else:
                        ext = _EXT_MAP.get(k, ".bin")
                    fname = f"output_{ts}{ext}"
                    fpath = os.path.join(_output_dir, fname).replace("\\", "/")
                    with open(fpath, "wb") as f:
                        f.write(v)
                    clean[k] = f"saved to {fpath}"
                else:
                    clean[k] = _clean(v, depth + 1)
            return clean
        if isinstance(obj, (list, tuple)):
            items = [_clean(x, depth + 1) for x in obj[:20]]
            if len(obj) > 20:
                items.append(f"... ({len(obj) - 20} more)")
            return items
        # Primitives (int, float, bool, None)
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return repr(obj)[:500]

    cleaned = _clean(result_val)

    # Final safety check — ensure it's JSON-serializable and not too big
    try:
        s = json.dumps(cleaned)
        if len(s) > 50000:
            return "<result too large after cleaning>"
        return cleaned
    except (TypeError, ValueError):
        return repr(cleaned)[:2000]


class _StreamingStdout(io.StringIO):
    """StringIO that also appends output to a file for cross-process polling.

    Used by ``run_code`` so a separate reader (usually the agent's UI
    poller) can tail the file to watch a long-running script produce
    output in real time, while the in-memory StringIO still captures
    the full output for the tool's final response.
    """
    def __init__(self, stream_file: str):
        super().__init__()
        self._stream_file = stream_file

    def write(self, s):
        """Append ``s`` to the stream file AND to the in-memory buffer."""
        try:
            with open(self._stream_file, "a", encoding="utf-8") as f:
                f.write(s)
        except Exception:
            pass
        return super().write(s)


# Audit-driven error-translation table. Real-world recurring EE/geeViz error
# strings the agent sees, mapped to one-line plain-English hints that point
# at the actual fix. The original traceback is preserved underneath — these
# just prepend a clear summary so the agent acts on the right thing instead
# of retrying the same broken filter.
_EE_ERROR_HINTS = [
    (
        "Element.toDictionary: Parameter 'element' is required and may not be null",
        "HINT: You called .toDictionary() on a null Feature. This almost "
        "always means the FeatureCollection you filtered returned 0 features "
        "before .first(). Print fc.size().getInfo() to confirm, then either "
        "fix the filter property/value or branch on the empty case.",
    ),
    (
        "Image.bandNames: Parameter 'image' is required and may not be null",
        "HINT: You called .bandNames() on a null Image. The ImageCollection "
        "you filtered returned 0 images before .first() / .mosaic(). Print "
        "ic.size().getInfo() to confirm, then loosen the date / bounds / "
        "filter.",
    ),
    (
        "Image.bandNames: Parameter 'image' is required and may not be null.\nAvailable band names: []",
        "HINT: Same as above — the filtered ImageCollection is empty.",
    ),
    (
        "Image.select: No match for",
        "HINT: The band you asked for doesn't exist in this image. Call "
        "inspect_asset(asset_id=...) to see the real band names — do not "
        "guess. LCMS uses 'Land_Cover', NLCD uses 'landcover', Hansen uses "
        "'lossyear' (NOT 'forest_loss'), Sentinel-2 SR uses 'B4/B8/B12', etc.",
    ),
    (
        "Band pattern",
        "HINT: A .select() pattern didn't match. inspect_asset(asset_id=...) "
        "to see the actual band names; do not guess.",
    ),
    (
        "User memory limit exceeded",
        "HINT: EE compute too large. **DO NOT RETRY THE SAME EXPRESSION** "
        "— it will fail every time at the same scale/AOI/time range. You "
        "MUST change at least ONE of these on the next attempt: "
        "(a) coarsen scale (Sentinel-2 30m → MODIS 250m/1000m, Landsat 30m → 250-1000m), "
        "(b) restrict AOI (state → county, or tile the AOI), "
        "(c) reduce time range (multi-decade → single year or seasonal slice), "
        "(d) switch to a coarser dataset entirely (S2/Landsat NDSI → MODIS MOD10A1, "
        "Hansen 30m → JRC GSW for water, Landsat NDVI for huge regions → MODIS MOD13A2). "
        "Agent rule #5 caps retries at 2 — after the second failure here, "
        "stop using getProcessedLandsatScenes / Sentinel-2 and switch to MODIS or "
        "tell the user the AOI is too large.",
    ),
    (
        "Description length exceeds maximum",
        "HINT: Your EE expression chain is too complex — almost always from "
        "passing a many-polygon FeatureCollection (e.g. sal.getUSStates()) "
        "into .filterBounds(...). Use ee.Geometry.BBox(...) for the bounds "
        "instead of the FC, or skip .filterBounds entirely on already-clipped "
        "assets like CONUS LCMS / NLCD.",
    ),
    (
        "EEException: Computation timed out",
        "HINT: EE-side timeout. Coarsen scale (e.g. 30 -> 300 -> 1000), or "
        "tile the AOI, or reduce the time range. Don't just retry the same "
        "expression — it'll keep timing out.",
    ),
    (
        "'Element' object has no attribute",
        "HINT: An EE Element-typed object hit a method only Image/FC has. "
        "Almost always from .copyProperties() / .get(...) / .first() which "
        "returns ee.Element, not ee.Image. Wrap the result: "
        "ee.Image(img.copyProperties(other)). Same fix for ee.Feature("
        "fc.first()) when you want Feature methods.",
    ),
    (
        "ReduceRegion.AggregationContainer",
        "HINT: A Reducer.group() / Reducer.combine() needs exactly the band "
        "shape it was asked for. Common cause: passing a 1-band image to a "
        "Reducer that needs 2 (e.g. histogram by group). Either ensure the "
        "image has the right band count, or use a simpler reducer like "
        "ee.Reducer.frequencyHistogram() for class counts.",
    ),
    (
        "Group input must come after weighted inputs",
        "HINT: Reducer.group() requires the GROUP input to be added AFTER "
        "any weighted inputs (per EE's reducer-construction rules). When "
        "chaining Reducer.combine() / .group(), put .group(groupField=N) "
        "as the LAST step in the chain, not in the middle.",
    ),
    (
        "Map.centerObject: bounds resolved to None",
        "HINT (same family as toDictionary-on-null): an upstream filter "
        "returned 0 features. Print fc.size().getInfo() before adding "
        "the layer; fix the filter property/value or short-circuit on "
        "the empty case so you don't paint a layer the viewer can't "
        "center on.",
    ),
    (
        "Output of image computation is too large",
        "HINT: A reduceRegions / reduceRegion over many features blew up. "
        "This is the equity-join failure mode. **DO NOT RETRY** the same "
        "shape — change ONE: "
        "(a) coarsen scale (30 → 300 → 1000), "
        "(b) reduce the number of features (filter the FC first, or use a "
        "smaller boundary asset like census TRACT instead of BLOCK), "
        "(c) split the FC and reduce in chunks (use .toList() + slice loop), "
        "(d) for thematic + SVI/equity joins, compute per-class area "
        "server-side with ee.Reducer.frequencyHistogram().forEach(...) "
        "instead of joining DataFrames in Python.",
    ),
    (
        "Collection.iterate",
        "HINT: An iterate chain failed. Iterate accumulates server-side; if "
        "you're using it to join FCs against properties, switch to "
        "ee.Join.saveFirst() or ee.Join.inner() — they're cheaper. Or do the "
        "join client-side: getInfo() both FCs and merge as DataFrames.",
    ),
    (
        "Request payload size exceeds the limit",
        "HINT: Your EE expression graph is too big — almost always from "
        "iteratively building a FeatureCollection inside a Python loop, or "
        "passing a huge FC into .filterBounds(). Build the expression in one "
        "pass with ee.FeatureCollection(list_of_features), or replace "
        ".filterBounds(big_fc) with ee.Geometry.BBox(...).",
    ),
]


def _translate_ee_error(error_text: str) -> str:
    """Prepend an actionable HINT line to recurring EE/geeViz errors.

    The agent's session audit (47 sessions, 95 errors) showed that the same
    handful of cryptic EE errors appear repeatedly and trigger long retry
    chains because the agent doesn't immediately see the actual cause.
    Catching them once at the run_code boundary saves ~3-5 retry round-trips
    per occurrence. The original traceback is preserved verbatim underneath.
    """
    if not error_text:
        return error_text
    for needle, hint in _EE_ERROR_HINTS:
        if needle in error_text:
            return f"{hint}\n\n--- original traceback below ---\n{error_text}"
    return error_text


# ---------------------------------------------------------------------------
# Thread-local stdout/stderr routing for stdio MCP servers.
#
# Problem: when this module is run as a stdio MCP server, FastMCP uses raw
# stdout as the JSON-RPC byte channel. ANY ``print()`` from a tool function
# (e.g. ``map_control`` doing ``print("Validating layer(s)...")``) lands
# directly on that channel and corrupts the protocol — the parent reads
# garbage between two well-formed JSON-RPC messages, request/response IDs
# desync, and subsequent ``list_tools`` requests time out at the 300s
# connection limit ("Failed to get tools from MCP server").
#
# Additional bug we used to ship: ``run_code`` wrapped its exec thread in
# ``contextlib.redirect_stdout(buf)``, which mutates ``sys.stdout``
# PROCESS-WIDE — every other thread's writes (including FastMCP's protocol
# writer if it touched ``sys.stdout`` at the wrong moment) went into the
# user-code buffer until the ``with`` block exited.
#
# Fix: install a single thread-local proxy as ``sys.stdout`` /
# ``sys.stderr`` once at module init. The proxy routes per-thread:
#   - Thread registered via ``register(buf)`` → writes go to ``buf``
#     (``run_code`` uses this to capture user-code output).
#   - Every other thread (FastMCP tool dispatch, asyncio loop, logging,
#     stray ``print()`` calls in any tool) → writes go to ``sys.__stderr__``,
#     the ORIGINAL stderr captured at interpreter startup. That keeps the
#     output visible to the operator while guaranteeing it never reaches
#     the JSON-RPC byte stream.
#
# FastMCP's protocol writer itself is unaffected: ``mcp/server/stdio.py``
# wraps ``sys.stdout.buffer`` (the raw underlying buffer) at startup,
# bypassing this proxy via ``__getattr__``. Protocol bytes go to the real
# stdout pipe, ``print()`` strings go to stderr — clean separation.
# ---------------------------------------------------------------------------
class _ThreadLocalStreamProxy:
    """Per-thread write router for sys.stdout / sys.stderr.

    Unregistered threads fall back to ``sys.__stderr__`` rather than the
    captured original stream — for ``sys.stdout`` that's critical: the
    original stdout IS the JSON-RPC byte channel and must never receive
    arbitrary ``print()`` output.
    """

    def __init__(self, real_stream):
        # ``_real`` is the proxy's pass-through target for non-write
        # attribute access (encoding, fileno, buffer, etc.). FastMCP relies
        # on ``.buffer`` resolving to the original raw byte buffer.
        self._real = real_stream
        self._by_thread: dict[int, object] = {}

    def register(self, target) -> None:
        """Route the calling thread's writes to ``target`` until unregistered.

        Args:
            target: File-like sink (typically a ``StringIO``) that will
                receive every ``print()`` from THIS thread. Other threads
                are unaffected.
        """
        self._by_thread[threading.get_ident()] = target

    def unregister(self) -> None:
        """Stop routing this thread's writes. Falls back to ``sys.__stderr__``."""
        self._by_thread.pop(threading.get_ident(), None)

    def _resolve(self):
        # Non-registered → stderr, NEVER the captured stdout (which would
        # corrupt JSON-RPC).
        return self._by_thread.get(threading.get_ident(), sys.__stderr__)

    def write(self, s):
        """Route ``s`` to this thread's registered sink (or ``sys.__stderr__``)."""
        try:
            return self._resolve().write(s)
        except Exception:
            return 0

    def flush(self):
        """Flush this thread's routed sink; swallows any error from the sink."""
        try:
            return self._resolve().flush()
        except Exception:
            return None

    def isatty(self):
        """Always False — the proxy is never a TTY regardless of the underlying stream."""
        return False

    # Forward anything else (encoding, fileno, buffer, etc.) to the real
    # stream so libraries that introspect sys.stdout don't break. In
    # particular, FastMCP grabs ``sys.stdout.buffer`` once at startup —
    # this attribute lookup gets the ORIGINAL stdout's raw buffer, so
    # protocol writes bypass the routing logic entirely.
    def __getattr__(self, name):
        return getattr(self._real, name)


_TL_STDOUT = _ThreadLocalStreamProxy(sys.stdout)
_TL_STDERR = _ThreadLocalStreamProxy(sys.stderr)
sys.stdout = _TL_STDOUT
sys.stderr = _TL_STDERR


@app.tool(annotations=_WRITE)
async def run_code(code: str, timeout: int = 120, reset: bool = False,
                   stream_stdout: bool = False, session_id: str = None,
                   ctx: Context = None) -> str:
    """Execute Python/GEE code in a persistent REPL namespace (like Jupyter).

    The namespace persists across calls -- variables set in one call are
    available in the next.  Pre-populated with: ee, Map (gv.Map), gv
    (geeViz.geeView), gil (geeViz.getImagesLib), sal
    (geeViz.getSummaryAreasLib), tl (geeViz.outputLib.thumbs), rl (geeViz.outputLib.reports),
    save_file.

    **Sandbox mode:** When the server is run with ``--sandbox`` or over HTTP
    to a non-localhost address, ``open()``, ``os``, ``sys``, ``eval``, etc.
    are blocked. For local/stdio use (the default), sandbox is OFF and full
    Python access is available. Use ``save_file(filename, content)`` to write
    files to the ``generated_outputs/`` directory regardless of sandbox mode.

    While executing, progress heartbeats are sent every ~10 seconds to keep the
    MCP client connection alive and inform the agent that the tool is still running.

    Args:
        code: Python code to execute.
        timeout: Max seconds to wait (default 120). On Windows a hung
                 getInfo() cannot be force-killed; the thread continues
                 in background.
        reset: If True, clear the namespace and re-initialize before
               executing.
        stream_stdout: If True, print output is available in real-time
                       via the /stdout polling endpoint. Default False.
        session_id: Session identifier for namespace isolation. Default
                    None (shared default session).
        ctx: MCP Context (auto-injected by FastMCP). Used for progress reporting.

    Returns:
        JSON with keys: success (bool), stdout, stderr, result, error.
    """
    if reset:
        _reset_namespace(session_id)
    sess = _ensure_initialized(session_id)

    # Runaway-retry circuit breaker. Window: last 90s. Threshold: 15 calls.
    # When tripped, the agent gets a hard RESTRUCTURE_REQUIRED instead of
    # executing the code, AND the recent-call list is half-cleared so it
    # doesn't immediately trip again. The breaker self-disarms after a few
    # acks so the agent isn't permanently throttled if it legitimately
    # needs many quick calls after a real restructure.
    # Use ``_time`` — module-top imports ``time as _time`` (bare ``time``
    # is not in this module's namespace).
    _now = _time.time()
    sess._recent_call_ts = [t for t in sess._recent_call_ts if _now - t < 90.0]
    if len(sess._recent_call_ts) >= 15 and sess._breaker_acks < 2:
        sess._recent_call_ts = sess._recent_call_ts[len(sess._recent_call_ts) // 2:]
        sess._breaker_acks += 1
        return json.dumps({
            "success": False,
            "stdout": "",
            "stderr": "",
            "result": None,
            "error": (
                "RESTRUCTURE_REQUIRED: you have made 15+ run_code calls in the last "
                "90 seconds — this is the runaway-retry pattern. **STOP RETRYING THE "
                "SAME APPROACH.** Tell the user the current approach is not working "
                "and ask which restructure to take: "
                "(a) coarsen scale (30 → 300 → 1000), "
                "(b) reduce AOI (county/tract instead of state/ZIP), "
                "(c) shorter time range, "
                "(d) different (coarser) dataset (Landsat → MODIS, Sentinel-2 → MODIS), "
                "(e) compute server-side with frequencyHistogram instead of FC×FC join. "
                "Do NOT call run_code again until you have a fundamentally different plan."
            ),
            "script_path": None,
        })
    sess._recent_call_ts.append(_now)

    # Strip redundant imports that would clobber pre-populated namespace variables.
    # The REPL already has ee, Map, gv, gil, sal, cl, tl, rl, gm, palettes, save_file.
    # Agents frequently write `from geeViz import geeView as Map` which replaces the
    # mapper instance with the module, breaking Map.addLayer/clearMap/etc.
    try:
        _tree = ast.parse(code)
        _stripped = []
        for node in _tree.body:
            skip = False
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    bound_name = alias.asname or alias.name.split(".")[-1]
                    if bound_name in ("ee", "Map", "gv", "gil", "sal", "cl", "tl", "rl", "gm", "palettes", "save_file"):
                        skip = True
                        break
            if not skip:
                _stripped.append(node)
        if len(_stripped) < len(_tree.body):
            _tree.body = _stripped
            code = ast.unparse(_tree)
    except SyntaxError:
        pass  # let the actual exec catch it

    # Static analysis: detect risky and blocked patterns before execution
    code_warnings = _check_code_patterns(code)

    # Refuse execution if any BLOCKED patterns were found
    blocked = [w for w in code_warnings if w.startswith("BLOCKED:")]
    if blocked:
        return json.dumps({
            "success": False,
            "stdout": "",
            "stderr": "\n".join(blocked),
            "result": None,
            "error": "Code was blocked by security policy. " + " ".join(blocked),
            "script_path": None,
        })

    # Set up stdout capture — streaming version appends to a file for polling
    if stream_stdout:
        try:
            os.makedirs(os.path.dirname(sess.stdout_stream_file), exist_ok=True)
            with open(sess.stdout_stream_file, "w", encoding="utf-8") as f:
                f.write("")  # clear
        except Exception:
            pass
        sess.stdout_active = True
        stdout_buf = _StreamingStdout(sess.stdout_stream_file)
    else:
        stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    result_holder: list = [None]
    error_holder: list = [None]

    # Snapshot output files before execution to detect new/modified ones.
    # We track both existence and mtime so files overwritten in place
    # (common with save_file when the agent re-generates an image) are
    # still reported as outputs.
    os.makedirs(sess.output_dir, exist_ok=True)
    _mtimes_before = {
        f: os.path.getmtime(os.path.join(sess.output_dir, f))
        for f in os.listdir(sess.output_dir)
        if os.path.isfile(os.path.join(sess.output_dir, f))
    }
    _files_before = set(_mtimes_before.keys())

    # --- Dependency-tracking snapshot (Level 2) ---
    # Take a namespace-id snapshot BEFORE exec so we can diff after and
    # compute the exact set of names this block bound (new keys +
    # rebound keys). AST analysis runs alongside for reads/touches.
    # Cheap: ~1 ms per block for a few hundred names.
    _block_ast = _analyze_block_ast(code)
    _ns_before_ids = _snapshot_namespace_ids(sess.namespace)

    _ns = sess.namespace  # capture for closure

    def _exec():
        global _audit_user_code_active
        # Route THIS thread's stdout/stderr to the per-call buffers via the
        # thread-local proxy. Other threads in the process (notably the MCP
        # asyncio loop writing JSON-RPC responses) are unaffected — they
        # still write to the original stdout, so the protocol pipe stays
        # uncorrupted even with overlapping run_code calls.
        _TL_STDOUT.register(stdout_buf)
        _TL_STDERR.register(stderr_buf)
        try:
            if _SANDBOX_ENABLED:
                _audit_user_code_active = True
            tree = ast.parse(code)
            if tree.body and isinstance(tree.body[-1], ast.Expr):
                if len(tree.body) > 1:
                    mod = ast.Module(body=tree.body[:-1], type_ignores=[])
                    exec(compile(mod, "<mcp>", "exec"), _ns)
                expr = ast.Expression(body=tree.body[-1].value)
                result_holder[0] = eval(compile(expr, "<mcp>", "eval"), _ns)
            else:
                exec(compile(code, "<mcp>", "exec"), _ns)
        except Exception:
            error_holder[0] = traceback.format_exc()
        finally:
            _audit_user_code_active = False
            _TL_STDOUT.unregister()
            _TL_STDERR.unregister()

    # Run user code inside a snapshot of THIS task's context so the
    # attribution ContextVars (user email, session id, tenant) survive
    # the hop onto the worker thread. Without this every EE call made by
    # user code reached the ee-proxy with no X-Agent-* headers and was
    # logged ``via=ANONYMOUS`` — the proxy then minted an unattributed
    # workload tag, so run_code compute (the bulk of EE spend) was billed
    # to nobody. See geeViz.eeAuth.threadctx.
    from geeViz.eeAuth.threadctx import run_in_context as _ric
    thread = threading.Thread(target=_ric(_exec), daemon=True)
    thread.start()

    # Heartbeat loop: poll every 1s, timeout only after `timeout` seconds
    # of *inactivity* (no new stdout/stderr output). Active code that keeps
    # printing can run indefinitely.
    elapsed = 0.0
    idle_time = 0.0
    report_interval = 10
    poll_interval = 1
    next_report = report_interval
    last_stdout_len = 0
    last_stderr_len = 0
    while thread.is_alive() and idle_time < timeout:
        await asyncio.sleep(min(poll_interval, timeout - idle_time))
        elapsed += poll_interval

        # Check for new output activity
        cur_stdout_len = stdout_buf.tell()
        cur_stderr_len = stderr_buf.tell()
        if cur_stdout_len != last_stdout_len or cur_stderr_len != last_stderr_len:
            idle_time = 0.0  # reset idle timer on any new output
            last_stdout_len = cur_stdout_len
            last_stderr_len = cur_stderr_len
        else:
            idle_time += poll_interval

        if thread.is_alive() and ctx and elapsed >= next_report:
            next_report += report_interval
            try:
                await ctx.report_progress(elapsed, timeout)
                await ctx.info(f"run_code executing... ({int(elapsed)}s elapsed, {int(idle_time)}s idle / {timeout}s timeout)")
            except Exception:
                pass  # don't let reporting errors kill the tool

    # On timeout the exec thread is a daemon that may keep running, but its
    # writes are routed via the thread-local proxy — they land in the
    # registered buffer, never on the global stdout/stderr that the MCP
    # JSON-RPC protocol uses. The exec thread cleans up its OWN routing
    # entry in its finally block when it eventually completes, so nothing
    # to undo from the main thread here.

    # Guard: restore Map if user code clobbered it
    # (e.g. `from geeViz import geeView as Map` replaces the mapper instance with the module)
    import geeViz.geeView as _gv_mod
    if not isinstance(_ns.get("Map"), _gv_mod.mapper):
        _ns["Map"] = sess._map_ref

    # Clear streaming flag
    if stream_stdout:
        sess.stdout_active = False

    # Prepend static analysis warnings to stderr
    stderr_val = stderr_buf.getvalue()
    if code_warnings:
        warning_block = "\n".join(code_warnings) + "\n"
        stderr_val = warning_block + stderr_val

    if thread.is_alive():
        timeout_hints = (
            f"Execution timed out after {int(idle_time)}s of inactivity ({int(elapsed)}s total). Common causes:\n"
            "- .getInfo() on a large ImageCollection -- use .limit(N) or inspect_asset with date/region filters\n"
            "- .getInfo() on a high-res Image over a large region -- reduce the region or increase scale\n"
            "- Complex server-side computation -- break into smaller steps\n"
            "Note: on Windows, the thread continues in background."
        )
        if elapsed >= 60:
            timeout_hints += (
                "\nHint: the call ran for over 60s with no output. If this was a .getInfo() call, "
                "consider using inspect_asset with filters, or reduce scale/region size."
            )
        return _scrub_json_response({
            "success": False,
            "code": code,
            "stdout": stdout_buf.getvalue(),
            "stderr": stderr_val,
            "result": None,
            "error": timeout_hints,
        })

    if error_holder[0]:
        return _scrub_json_response({
            "success": False,
            "code": code,
            "stdout": stdout_buf.getvalue(),
            "stderr": stderr_val,
            "result": None,
            "error": _translate_ee_error(error_holder[0]),
            "script_path": None,
        })

    # Success -- record in history AND record per-block metadata (Level 2
    # tracker). ``names_bound`` uses the runtime namespace diff — that's
    # ground-truth for what this block actually created or rebound. Merge
    # with static-AST bound names so wildcard-import-side-effects or dynamic
    # bindings (setattr, updating globals()) that appeared as new keys
    # get counted. Reads and touches come from the AST walker.
    sess.code_history.append(code)
    _ns_after_ids = _snapshot_namespace_ids(sess.namespace)
    _bound_runtime = _diff_namespace(
        _ns_before_ids, _ns_after_ids, skip_names=_REPL_BOOTSTRAP_NAMES,
    )
    sess.code_history_meta.append({
        "source": code,
        "names_bound": _bound_runtime | _block_ast["bound_static"],
        "names_read": set(_block_ast["read"]),
        "names_touched": set(_block_ast["touched"]),
        "is_import": _block_ast["is_import"],
        "wildcard_import": _block_ast["wildcard_import"],
        "parse_error": _block_ast["parse_error"],
        "succeeded": True,
    })
    script_path = _save_history_to_file(sess)

    result_val = result_holder[0]

    # --- Auto-save any binary/HTML outputs and build a clean result ---
    # This is the ONLY place that handles bytes/large data.
    # Everything that comes out of here is guaranteed small and JSON-safe.
    result_str = _save_and_clean_result(result_val)

    # Detect new or modified output files (from save_file, auto-save, or direct writes)
    _files_after = [
        f for f in os.listdir(sess.output_dir)
        if os.path.isfile(os.path.join(sess.output_dir, f))
    ]
    _new_files = []
    for f in _files_after:
        fpath = os.path.join(sess.output_dir, f)
        mt = os.path.getmtime(fpath)
        if f not in _files_before or mt > _mtimes_before.get(f, 0):
            _new_files.append(f)
    _new_files = sorted(_new_files)
    _IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
    output_markdown = None
    if _new_files:
        md_lines = []
        for fname in _new_files:
            fpath = os.path.join(sess.output_dir, fname).replace("\\", "/")
            ext = os.path.splitext(fname)[1].lower()
            label = os.path.splitext(fname)[0].replace("_", " ").replace("-", " ").title()
            if ext in _IMG_EXTS:
                md_lines.append(f"![{label}]({fpath})")
            else:
                md_lines.append(f"[{label}]({fpath})")
        output_markdown = "\n".join(md_lines)

    # Clean stderr — strip noisy library logs (Kaleido, Chromium, http retries)
    # that bloat the response without useful info for the model
    _noise_patterns = {"kaleido", "chromium", "browser_async", "_tmpfile",
                       "shutil.rmtree", "TemporaryDirectory", "Conforming",
                       "navigates", "Getting tab", "Got ", "Processing fig",
                       "Sending big command", "Sent big command", "Reloading tab",
                       "Putting tab", "Waiting for all", "Exiting Kaleido",
                       "Cancelling tasks", "Opening browser", "Closing browser",
                       "Temp directory", "Found chromium"}
    _filtered_stderr = []
    for _line in stderr_val.splitlines():
        _lower = _line.lower()
        if any(p in _lower for p in _noise_patterns):
            continue
        _filtered_stderr.append(_line)
    stderr_val = "\n".join(_filtered_stderr).strip()

    # Clean stdout — strip base64 data URIs and cap size
    import re as _re
    stdout_val = stdout_buf.getvalue()
    stdout_val = _re.sub(
        r'data:(image|text)/[^;]+;base64,[A-Za-z0-9+/=]{100,}',
        '<base64 data stripped>',
        stdout_val,
    )
    if len(stdout_val) > 50000:
        stdout_val = stdout_val[:50000] + "\n... (truncated)"

    return _scrub_json_response({
        "success": True,
        "code": code,
        "stdout": stdout_val,
        "stderr": stderr_val,
        "result": result_str,
        "error": None,
        "script_path": script_path,
        "output_markdown": output_markdown,
    })


# ---------------------------------------------------------------------------
# Tool 2: inspect_asset
# ---------------------------------------------------------------------------

@app.tool(annotations=_READ_ONLY_OPEN)
def inspect_asset(
    asset_id: str,
    start_date: str = "",
    end_date: str = "",
    region_var: str = "",
    session_id: str = None,
) -> str:
    """Get detailed metadata for any GEE asset (Image, ImageCollection, FeatureCollection, etc.).

    Returns band names/types, CRS, scale, date range, size, columns, and
    properties. Uses ee.data.getInfo for fast catalog metadata, then fetches
    live details with a 10-second timeout per query to avoid hangs on large
    collections. Also handles BigQuery-backed FeatureCollections — when the
    standard catalog lookup returns "not found" and the id looks BQ-shaped
    (``project.dataset.table``), retries via
    ``ee.FeatureCollection.loadBigQueryTable`` so tables like
    ``bigquery-public-data.overture_maps.place`` describe cleanly.

    Args:
        asset_id: Full Earth Engine asset ID (e.g.
                  ``"COPERNICUS/S2_SR_HARMONIZED"``) OR a BigQuery table
                  path in the form ``project.dataset.table`` (e.g.
                  ``"bigquery-public-data.overture_maps.place"``). EE
                  catalog is tried first; BQ is the fallback.
        start_date: Optional start date filter for ImageCollections (YYYY-MM-DD).
        end_date: Optional end date filter for ImageCollections (YYYY-MM-DD).
        region_var: Optional name of an ee.Geometry or ee.FeatureCollection
                    variable in the REPL namespace for spatial filtering
                    (ImageCollections only).

    Returns:
        JSON with asset metadata. For BQ-backed hits, ``source=bigquery``
        is set so the caller knows to use ``ee.FeatureCollection.loadBigQueryTable``
        (not ``ee.FeatureCollection``) when constructing the FC.
    """
    import concurrent.futures
    import datetime as _dt

    _TIMEOUT = 10  # seconds per EE query

    sess = _ensure_initialized(session_id)
    ee = sess.namespace["ee"]

    def _looks_like_bq(aid: str) -> bool:
        """Heuristic: BigQuery table paths are ``project.dataset.table`` —
        at least two dots, no slashes (EE catalog IDs use slashes)."""
        return aid.count(".") >= 2 and "/" not in aid

    def _try_bigquery_fallback(aid: str) -> str | None:
        """Try to describe ``aid`` as a BigQuery-backed FeatureCollection.
        Returns a JSON string on success, or None if this path isn't
        applicable / doesn't work. Best-effort — errors are captured in
        the returned JSON so the caller sees WHY the fallback didn't
        salvage the lookup."""
        try:
            fc = ee.FeatureCollection.loadBigQueryTable(aid)
        except Exception as _bq_exc:
            return json.dumps({
                "error": f"Not in EE catalog and BigQuery fallback failed: {_bq_exc}",
                "asset_id": aid,
            })
        # Validate + pull schema with the same 10s guard the EE path uses.
        schema, err = _getinfo_with_timeout(fc.limit(1))
        if err:
            return json.dumps({
                "error": (f"Not in EE catalog. BigQuery loadBigQueryTable "
                          f"accepted the id but getInfo failed: {err}. "
                          f"Verify the caller has BigQuery read access and "
                          f"the table exists as {aid!r}."),
                "asset_id": aid,
                "source": "bigquery",
            })
        out = {
            "asset_id": aid,
            "type": "FEATURE_COLLECTION",
            "source": "bigquery",
            "note": ("Loaded via ee.FeatureCollection.loadBigQueryTable — "
                     "use loadBigQueryTable when constructing this FC in "
                     "run_code, not ee.FeatureCollection(...)."),
        }
        if isinstance(schema, dict):
            feats = schema.get("features") or []
            if feats:
                sample_props = feats[0].get("properties") or {}
                if sample_props:
                    out["columns"] = sorted(sample_props.keys())
                    out["sample_row"] = sample_props
        return json.dumps(out)

    # Local wrapper so the BQ fallback closure can use it before the main
    # definition below. Same body — kept here for scoping simplicity.
    def _getinfo_with_timeout(ee_obj, timeout=_TIMEOUT):
        import threading
        _result_box = [None, None]
        def _run():
            try:
                _result_box[0] = ee_obj.getInfo()
            except Exception as _exc:
                _result_box[1] = str(_exc)
        # getInfo() is an EE call; carry the caller's attribution context
        # onto the worker thread or it bills to nobody (see threadctx).
        from geeViz.eeAuth.threadctx import run_in_context as _ric
        t = threading.Thread(target=_ric(_run), daemon=True)
        t.start()
        t.join(timeout=timeout)
        if t.is_alive():
            return None, "timeout"
        return _result_box[0], _result_box[1]

    # --- Step 1: Fast catalog metadata (no compute, never hangs) ---
    try:
        info = ee.data.getInfo(asset_id)
    except Exception as exc:
        # EE catalog raised (auth failure, malformed id, etc.). If the id
        # looks BQ-shaped, still worth trying the BQ path — the exception
        # from the EE side isn't proof BQ can't answer.
        if _looks_like_bq(asset_id):
            bq_result = _try_bigquery_fallback(asset_id)
            if bq_result is not None:
                return bq_result
        return json.dumps({"error": str(exc), "asset_id": asset_id})

    if info is None:
        # Not in EE catalog. Try BigQuery if the id shape suggests it.
        if _looks_like_bq(asset_id):
            bq_result = _try_bigquery_fallback(asset_id)
            if bq_result is not None:
                return bq_result
        return json.dumps({"error": f"Asset not found: {asset_id}", "asset_id": asset_id})

    asset_type = info.get("type", "UNKNOWN")
    result: dict = {"asset_id": asset_id, "type": asset_type}

    # Include catalog-level properties (skip long description HTML)
    cat_props = info.get("properties", {})
    if cat_props:
        dr = cat_props.get("date_range")
        if dr and isinstance(dr, list) and len(dr) == 2:
            try:
                result["first_date"] = _dt.datetime.utcfromtimestamp(dr[0] / 1000).strftime("%Y-%m-%d")
                result["last_date"] = _dt.datetime.utcfromtimestamp(dr[1] / 1000).strftime("%Y-%m-%d")
            except Exception:
                pass
        _CATALOG_KEYS = ("title", "provider", "keywords", "tags", "period",
                         "visualization_0_bands", "visualization_0_min",
                         "visualization_0_max", "visualization_0_name",
                         "provider_url")
        for key in _CATALOG_KEYS:
            if key in cat_props:
                result.setdefault("catalog", {})[key] = cat_props[key]
        # Include column info for FeatureCollections
        if "columns" in info:
            result["columns"] = info["columns"]

    try:
        if asset_type in ("IMAGE", "Image"):
            img_info, err = _getinfo_with_timeout(ee.Image(asset_id))
            if img_info and "bands" in img_info:
                result["bands"] = [
                    {"name": b.get("id", ""), "data_type": b.get("data_type", {}).get("precision", ""),
                     "crs": b.get("crs", ""), "scale": b.get("crs_transform", [None])[0]}
                    for b in img_info["bands"]
                ]
                # Include image properties (class metadata, etc.)
                if "properties" in img_info:
                    result["properties"] = img_info["properties"]
            elif err:
                result["detail_error"] = err

        elif asset_type in ("IMAGE_COLLECTION", "ImageCollection"):
            collection = ee.ImageCollection(asset_id)

            # Apply filters
            filters_applied = {}
            if start_date:
                collection = collection.filterDate(start_date, end_date or "2099-01-01")
                filters_applied["start_date"] = start_date
                filters_applied["end_date"] = end_date or "2099-01-01"
            elif end_date:
                collection = collection.filterDate("1970-01-01", end_date)
                filters_applied["start_date"] = "1970-01-01"
                filters_applied["end_date"] = end_date
            if region_var:
                region = sess.namespace.get(region_var)
                if region is None:
                    return json.dumps({"error": f"Variable {region_var!r} not found in namespace."})
                if isinstance(region, ee.FeatureCollection):
                    region = region.geometry()
                elif not isinstance(region, ee.Geometry):
                    return json.dumps({
                        "error": f"Variable {region_var!r} is {type(region).__name__}, "
                                 "expected ee.Geometry or ee.FeatureCollection.",
                    })
                collection = collection.filterBounds(region)
                filters_applied["region_var"] = region_var
            if filters_applied:
                result["filters_applied"] = filters_applied

            # --- Run queries with individual timeouts ---
            # Each query runs in its own daemon thread so hangs don't block
            queries = {}
            queries["count"] = collection.size()

            # Date range: use catalog date_range if no filters applied,
            # otherwise compute from the filtered collection
            if filters_applied or "first_date" not in result:
                queries["first_date"] = collection.sort("system:time_start", True).first().date().format("YYYY-MM-dd")
                queries["last_date"] = collection.sort("system:time_start", False).first().date().format("YYYY-MM-dd")

            # Band info from first image
            queries["first_image"] = collection.first()

            import threading
            results_map = {}
            _lock = threading.Lock()

            def _run_query(key, ee_obj):
                try:
                    val = ee_obj.getInfo()
                    with _lock:
                        results_map[key] = val
                except Exception as exc:
                    with _lock:
                        results_map[key] = f"__ERROR__:{exc}"

            threads = []
            # One context snapshot PER thread: contextvars.Context.run
            # refuses re-entry, so a single shared wrapper would raise on
            # the second query. See threadctx's "one wrapper per thread".
            from geeViz.eeAuth.threadctx import run_in_context as _ric
            for key, ee_obj in queries.items():
                t = threading.Thread(
                    target=_ric(_run_query), args=(key, ee_obj), daemon=True)
                t.start()
                threads.append(t)

            # Wait up to _TIMEOUT for all threads
            deadline = __import__("time").time() + _TIMEOUT
            for t in threads:
                remaining = max(0.1, deadline - __import__("time").time())
                t.join(timeout=remaining)

            # Mark any that didn't finish
            for key in queries:
                if key not in results_map:
                    results_map[key] = "__TIMEOUT__"

            # Process results
            count_val = results_map.get("count")
            if isinstance(count_val, int):
                result["image_count"] = count_val
            elif count_val == "__TIMEOUT__":
                result["image_count"] = "timeout (large collection)"
            else:
                result["image_count_error"] = str(count_val)

            # Dates
            fd = results_map.get("first_date")
            ld = results_map.get("last_date")
            if isinstance(fd, str) and not fd.startswith("__"):
                result["first_date"] = fd
            if isinstance(ld, str) and not ld.startswith("__"):
                result["last_date"] = ld

            # Bands and sample image properties
            first_img = results_map.get("first_image")
            if isinstance(first_img, dict):
                if "bands" in first_img:
                    result["bands"] = [
                        {"name": b.get("id", ""), "data_type": b.get("data_type", {}).get("precision", ""),
                         "crs": b.get("crs", ""), "scale": b.get("crs_transform", [None])[0]}
                        for b in first_img["bands"]
                    ]
                # Include first image's property names (not values — those can be huge)
                img_props = first_img.get("properties", {})
                if img_props:
                    result["image_property_names"] = sorted(img_props.keys())
                    # Include a few key properties if they exist
                    for k in ("system:time_start", "system:index"):
                        if k in img_props:
                            result.setdefault("sample_image", {})[k] = img_props[k]

            # If count timed out, note it
            if count_val == "__TIMEOUT__":
                result["note"] = "Collection too large to count within timeout."

        elif asset_type in ("TABLE", "FeatureCollection"):
            # Try full metadata first, fall back to limited sample
            fc = ee.FeatureCollection(asset_id)
            fc_info, err = _getinfo_with_timeout(fc.limit(5), _TIMEOUT)
            if fc_info:
                result["asset"] = _strip_coordinates(fc_info)
                # Get column info
                if "columns" in info:
                    result["columns"] = info["columns"]
            elif err == "timeout":
                # Try even smaller sample
                fc_info2, err2 = _getinfo_with_timeout(fc.limit(1), _TIMEOUT)
                if fc_info2:
                    result["asset"] = _strip_coordinates(fc_info2)
                    result["note"] = "Large FeatureCollection; showing 1 sample feature."
                else:
                    result["detail_error"] = "timeout fetching features"
                if "columns" in info:
                    result["columns"] = info["columns"]
            else:
                result["detail_error"] = err or "unknown error"

        else:
            # Folder or other type — return raw info
            result["info"] = info

    except Exception as exc:
        result["detail_error"] = str(exc)

    # --- Detect thematic/categorical bands ---
    # If any band has matching {band}_class_values, {band}_class_names, and
    # {band}_class_palette properties, flag the dataset as thematic and tell
    # the agent exactly what viz params to use. This eliminates the most
    # common agent mistake (hardcoding min/max for thematic data).
    bands = result.get("bands", [])
    props = result.get("properties", {})
    if not props:
        # For ImageCollections, properties come from the first image info
        # which was fetched in the queries above. Use locals() safely.
        try:
            _first_img = locals().get("results_map", {}).get("first_image")
            if isinstance(_first_img, dict):
                props = _first_img.get("properties", {})
        except Exception:
            pass

    thematic_bands = []
    for band in bands:
        bname = band.get("name", "")
        if bname and all(
            "{}_class_{}".format(bname, suffix) in props
            for suffix in ("values", "names", "palette")
        ):
            thematic_bands.append(bname)

    if thematic_bands:
        result["thematic_bands"] = thematic_bands
        # Normalize class properties: some assets store them as comma-separated
        # strings instead of lists. Convert to lists so downstream code (and the
        # agent) gets consistent types.
        def _normalize_prop(v, as_int=False):
            if v is None or v == "":
                return []
            if isinstance(v, str):
                parts = [p.strip() for p in v.split(",") if p.strip()]
            elif isinstance(v, (list, tuple)):
                parts = list(v)
            else:
                return [v]
            if as_int:
                out = []
                for p in parts:
                    try:
                        out.append(int(p))
                    except (ValueError, TypeError):
                        try:
                            out.append(int(float(p)))
                        except (ValueError, TypeError):
                            out.append(p)
                return out
            return parts

        normalized_any = False
        for bname in thematic_bands:
            for suffix, as_int in (("values", True), ("names", False), ("palette", False)):
                key = f"{bname}_class_{suffix}"
                raw = props.get(key)
                if isinstance(raw, str):
                    normalized_any = True
                normalized = _normalize_prop(raw, as_int=as_int)
                props[key] = normalized
                # Also update the band-level properties (if present)
                for band in bands:
                    if band.get("name") == bname and "properties" in band:
                        band["properties"][key] = normalized

        result["viz_recommendation"] = (
            "THEMATIC DATA DETECTED — bands {} have class properties. "
            "You MUST use {{'autoViz': True}} as the viz params when adding "
            "this layer to the map. Do NOT use min/max. Example: "
            "Map.addLayer(data, {{'autoViz': True}}, 'Layer Name')"
        ).format(thematic_bands)
        if normalized_any:
            result["viz_recommendation"] += (
                " NOTE: This asset stored class properties as comma-separated strings. "
                "They have been normalized to lists in this response. Use the values shown."
            )

    # Cap response size to prevent token overflow
    response = json.dumps(result)
    if len(response) > 100000:
        # Strip large fields to fit
        for key in ("asset", "info", "bands"):
            if key in result and len(json.dumps(result.get(key, ""))) > 20000:
                result[key] = f"<truncated: {len(json.dumps(result[key]))} chars>"
        response = json.dumps(result)
    return response


# ---------------------------------------------------------------------------
# Unified search/introspection tool
# ---------------------------------------------------------------------------
import inspect as _inspect


def _resolve_module(name, session_ns=None):
    """Resolve a name to a container we can list members of.

    Accepts:
    - A geeViz module short name in ``_MODULE_TREE`` (``"getImagesLib"``).
    - A REPL alias for a geeViz module (``"sal"`` → ``getSummaryAreasLib``,
      ``"gil"`` → ``getImagesLib``, ``"cl"`` → ``outputLib.charts``, etc).
      Agents routinely guess the alias or invent alternative long-names
      (``"studyAreasLib"``, ``"chartingLib"``) — the alias map catches
      both.
    - A top-level REPL name that points to a module (``"ee"``, ``"pd"``).
    - A dotted path that traverses attributes from a top-level REPL name
      (``"ee.ImageCollection"``, ``"ee.Reducer"``, ``"pd.DataFrame"``).
      Each step uses ``getattr`` so classes count as valid containers —
      ``dir()`` returns their methods, which is what callers want.

    Returns ``(short_name, container)`` or ``(None, None)``.
    """
    # REPL aliases + common misnomers → real geeViz module short-name.
    # Kept in one place so future renames surface here, not in prompts.
    # Values MUST match _MODULE_TREE's short-name keys (charts, thumbs,
    # reports, getSummaryAreasLib, etc). Full paths like outputLib.charts
    # ARE in the tree but the tree indexer stores them separately; short
    # names are what the search_codebase docs promise, so map to those.
    _ALIASES = {
        "sal":            "getSummaryAreasLib",
        "studyareaslib":  "getSummaryAreasLib",   # common mis-guess
        "summarylib":     "getSummaryAreasLib",
        "gil":            "getImagesLib",
        "imageslib":      "getImagesLib",
        "cl":               "charts",
        "chartinglib":      "charts",
        "chartlib":         "charts",
        "outputlib.charts": "charts",
        "tl":               "thumbs",
        "thumbslib":        "thumbs",
        "outputlib.thumbs": "thumbs",
        "rl":               "reports",
        "reportslib":       "reports",
        "outputlib.reports": "reports",
        "gm":             "googleMapsLib",
        "gmapslib":       "googleMapsLib",
        "edw":            "edwLib",
        "esri":           "esriLib",
        "gv":               "geeView",
        "eeauth":           "eeAuth",
        "eeauth.client":    "client",
        "eeauth.eecreds":   "eeCreds",
        "eeauth.registry":  "registry",
        "eeauth.server":    "server",
        "eeauth.tags":      "tags",
        "cd":               "changeDetectionLib",
        "cdl":              "changeDetectionLib",
        "assetmgr":         "assetManagerLib",
        "aml":              "assetManagerLib",
        "taskmgr":          "taskManagerLib",
        "tml":              "taskManagerLib",
        "cloudstoragemgr":  "cloudStorageManagerLib",
        "csml":             "cloudStorageManagerLib",
        "csm":              "cloudStorageManagerLib",
        "invl":             "inventoryLib",
        "il":               "inventoryLib",
        "gcpl":             "gcpLib",
        "gml":              "googleMapsLib",
        "edwl":             "edwLib",
        "esril":            "esriLib",
        "palettes":         "geePalettes",
        "wx":               "weather",
        "weatherlib":       "weather",
        "forecast":         "weather",
    }
    # Strip a leading ``geeViz.`` before looking anything up.
    #
    # It is the real import path, so it is the first thing anyone types —
    # and it matched nothing. One session burned eight search_codebase
    # calls hunting a single function, cycling ``thumbs`` /
    # ``outputLib.thumbs`` / ``geeViz.outputLib.thumbs`` /
    # ``geeViz.outputLib.thumb`` because the prefixed forms returned
    # "Module not found" and the agent could not tell a wrong spelling
    # from a missing function. The alias table below already accepts the
    # unprefixed ``outputlib.thumbs``; this makes the qualified form a
    # synonym rather than a dead end.
    _name = name.strip()
    _low = _name.lower()
    if _low.startswith("geeviz."):
        _name = _name[len("geeViz."):]
        _low = _name.lower()

    aliased = _ALIASES.get(_low)
    if aliased and aliased in _MODULE_TREE:
        mod = _get_module(_MODULE_TREE[aliased])
        if mod is not None:
            return aliased, mod

    # Exact match in the geeViz module tree — try the stripped name as
    # well, so "geeViz.getImagesLib" resolves like "getImagesLib".
    for _candidate in (name, _name):
        entry = _MODULE_TREE.get(_candidate)
        if entry:
            mod = _get_module(entry)
            if mod is not None:
                return _candidate, mod

    if session_ns:
        # Top-level REPL hit (no dots)
        if "." not in name:
            obj = session_ns.get(name)
            if _inspect.ismodule(obj) or _inspect.isclass(obj):
                return name, obj
            return None, None

        # Dotted path: walk attributes from the head identifier.
        parts = name.split(".")
        head = session_ns.get(parts[0])
        if head is None:
            return None, None
        obj = head
        for attr in parts[1:]:
            obj = getattr(obj, attr, None)
            if obj is None:
                return None, None
        # Only accept containers (module/class). Functions/instances have
        # members too but listing them is usually noise.
        if _inspect.ismodule(obj) or _inspect.isclass(obj):
            return name, obj
    return None, None


def _iter_module_members(mod, query="", include_non_callable=True):
    """Yield (name, obj, kind, first_line, sig) for public members of a module."""
    q = query.lower() if query else ""
    for attr_name in sorted(dir(mod)):
        if attr_name.startswith("_"):
            continue
        obj = getattr(mod, attr_name, None)
        if obj is None:
            continue
        # Skip sub-modules from listing (too noisy)
        if _inspect.ismodule(obj):
            continue

        is_callable = callable(obj) or _inspect.isclass(obj)
        if not include_non_callable and not is_callable:
            continue

        doc = _inspect.getdoc(obj) or ""
        first_line = doc.split("\n")[0].strip() if doc else ""

        if q and q not in attr_name.lower() and q not in first_line.lower():
            continue

        if _inspect.isclass(obj):
            kind = "class"
        elif callable(obj):
            kind = "function"
        else:
            kind = type(obj).__name__

        sig = ""
        if callable(obj) and not _inspect.isclass(obj):
            try:
                sig = f"{attr_name}{_inspect.signature(obj)}"
            except (ValueError, TypeError):
                pass

        yield attr_name, obj, kind, first_line, sig


# Dataset-name keywords for the search_codebase → search_datasets fallback.
# Only used when search_codebase returns 0 hits — the agent very often calls
# search_codebase("modis") when they actually want search_datasets("modis").
_DATASET_KEYWORDS = frozenset([
    "modis", "landsat", "sentinel", "viirs", "chirps", "gpm", "era5",
    "worldcover", "nlcd", "lcms", "mtbs", "hansen", "gedi", "srtm", "aster",
    "alos", "dynamic world", "alpha earth", "copernicus", "esa", "noaa",
    "jaxa", "jrc", "prism", "daymet", "umd", "usda", "usgs", "planet",
    "cams", "airs", "firms", "worldpop", "ghsl",
])


def _looks_like_dataset_query(q: str) -> bool:
    """True when a query is more likely an EE asset / dataset name than
    a Python identifier."""
    if not q:
        return False
    q_lower = q.lower().strip()
    if "/" in q_lower and len(q_lower) > 3:
        return True
    return any(kw in q_lower for kw in _DATASET_KEYWORDS)


@app.tool(annotations=_READ_ONLY)
def search_codebase(query: str = "", name: str = "", module: str = "", session_id: str = None) -> str:
    """Search geeViz — plus any module in the REPL namespace (ee, pandas, numpy, etc.).

    A unified introspection tool. Look up functions, classes, dicts,
    constants, viz params, band mappings, palettes, method signatures,
    example scripts — anything reachable by name.

    **Modules it searches**

    - Every geeViz module (``getImagesLib``, ``getSummaryAreasLib``,
      ``geeView``, ``geePalettes``, ``edwLib``, ``googleMapsLib`` when
      available, ``outputLib.charts`` / ``.thumbs`` / ``.reports``,
      etc.) — indexed via AST at startup, so no imports fire until you
      actually request a runtime value.
    - Example scripts under ``geeViz/examples/`` — ``module="examples"``
      lists them, ``name="<script_name>"`` returns source.
    - Any module already loaded in the REPL namespace — that includes
      Earth Engine (``ee``), pandas (``pd`` / ``pandas``), numpy
      (``np`` / ``numpy``), and anything else prior ``run_code`` blocks
      imported. Pass ``module="ee"`` / ``module="pd"`` / etc. to browse.

    Args:
        query: Search term (case-insensitive). Matches against names and
               first-line docstrings across every indexed module.
        name: Exact name to look up. Accepts bare names
              (``"vizParamsFalse"``, ``"simpleMask"``,
              ``"DataFrame.to_markdown"``) or dotted paths
              (``"getImagesLib.vizParamsFalse"``, ``"mapper.addLayer"``,
              ``"ee.Image.reduceRegion"``, ``"pd.DataFrame"``). Returns
              full details — signature and docstring for functions;
              keys / values for dicts; value for constants.
        module: Module to search or list. Accepts short geeViz names
                (``"getImagesLib"``, ``"charts"``, ``"thumbs"``), full
                paths (``"geeViz.outputLib.charts"``), legacy aliases
                (``"chartingLib"``), or any REPL-loaded module
                (``"ee"``, ``"pandas"`` / ``"pd"``, ``"numpy"`` /
                ``"np"``).

    Returns:
        JSON with results. Shape depends on the query:
        - No args: list of all discovered modules
        - module only: all public members (functions, classes, variables)
        - query only: search results across all modules
        - name only: detailed description of the named object
        - name + module: direct lookup within a specific module
    """
    sess = _ensure_initialized(session_id)
    ns = sess.namespace

    # --- Direct name lookup ---
    if name:
        # Example source lookup: name="examples.CCDCViz" or bare example name
        _ex_name = name
        if name.startswith("examples."):
            _ex_name = name.split(".", 1)[1]
        ex_entry = _MODULE_TREE.get("examples")
        if ex_entry:
            for m in ex_entry.get("members", []):
                if m["name"] == _ex_name:
                    return _read_example_source(m["file"], m["name"], m.get("description", ""))

        # Dotted path: split into module/object + attribute
        if "." in name and not module:
            parts = name.split(".", 1)
            mod_name, attr_path = parts[0], parts[1]
            # Try module tree first
            _, mod_obj = _resolve_module(mod_name, ns)
            # Then try REPL namespace (covers Map, gv, gil, etc.)
            if mod_obj is None and mod_name in ns:
                mod_obj = ns[mod_name]
            if mod_obj is not None:
                try:
                    obj = mod_obj
                    for p in attr_path.split("."):
                        obj = getattr(obj, p)
                    return json.dumps(_describe_object(obj, name=name, module_name=mod_name))
                except AttributeError:
                    pass
            # Fallback: the module part may be more than one segment.
            #
            # The split above takes only the FIRST segment, so a fully
            # qualified name — "geeViz.fsInsights.fia.estimate", or
            # "geeViz.getImagesLib.simpleMask" — resolved mod_name to
            # "geeViz", which is not itself in the tree, and answered
            # "not found in any geeViz module".
            #
            # That spelling is exactly what an agent produces after
            # search_codebase hands it back a fully qualified module
            # path, and `module=` has always ACCEPTED the prefix, so the
            # two arguments disagreed about the same name. Observed
            # twice in five probe sessions.
            #
            # Try progressively shorter module prefixes, longest first,
            # so the most specific module wins. Reaching this point means
            # the single-segment attempt above did not return, so this is
            # purely additive — no path that used to succeed changes.
            _segs = name.split(".")
            for _i in range(len(_segs) - 1, 0, -1):
                _mod = ".".join(_segs[:_i])
                _attr = ".".join(_segs[_i:])
                if _mod == mod_name:
                    continue              # already tried above
                _, _obj = _resolve_module(_mod, ns)
                if _obj is None and _mod in ns:
                    _obj = ns[_mod]
                if _obj is None:
                    continue
                try:
                    _cur = _obj
                    for _p in _attr.split("."):
                        _cur = getattr(_cur, _p)
                except AttributeError:
                    continue
                return json.dumps(
                    _describe_object(_cur, name=name, module_name=_mod))

            # Fallback: mod_name might be a class inside a module (e.g. "mapper.addLayer")
            if mod_obj is None:
                for short, entry in _MODULE_TREE.items():
                    if short != entry["fq"]:
                        continue
                    for m in entry.get("members", []):
                        if m["type"] == "class" and m["name"] == mod_name:
                            _mod = _get_module(entry)
                            if _mod:
                                cls = getattr(_mod, mod_name, None)
                                if cls:
                                    try:
                                        obj = cls
                                        for p in attr_path.split("."):
                                            obj = getattr(obj, p)
                                        return json.dumps(_describe_object(obj, name=name, module_name=entry["fq"].rsplit(".", 1)[-1]))
                                    except AttributeError:
                                        pass

        # If module specified, look there
        if module:
            _, mod_obj = _resolve_module(module, ns)
            if mod_obj is None:
                return json.dumps({"error": f"Module {module!r} not found."})
            # Walk a dotted name within the module ("mapper.addLayer"). A single
            # getattr(mod, "mapper.addLayer") can never succeed -- a dotted
            # string is not an attribute name -- so this branch used to report
            # "not found" for methods the unscoped lookup found fine, and the
            # agent took the disagreement to mean the function did not exist.
            # A name that repeats the module ("geeView.mapper.addLayer") is
            # accepted too, since that is the full path people copy.
            _parts = name.split(".")
            if len(_parts) > 1 and _parts[0] in (module, module.rsplit(".", 1)[-1]):
                _parts = _parts[1:]
            obj = mod_obj
            for _p in _parts:
                obj = getattr(obj, _p, None)
                if obj is None:
                    break
            # geeView mapper fallback
            if obj is None and module in ("geeView", "geeViz.geeView"):
                mapper_cls = getattr(mod_obj, "mapper", None)
                if mapper_cls:
                    obj = getattr(mapper_cls, name, None)
                    if obj is not None:
                        name = f"mapper.{name}"
            if obj is not None:
                return json.dumps(_describe_object(obj, name=name, module_name=module))
            return json.dumps({"error": f"{name!r} not found in {module}."})

        # Bare name — check AST index first (no import needed if value was extracted)
        for short, entry in _MODULE_TREE.items():
            if short != entry["fq"]:
                continue
            for m in entry.get("members", []):
                if m["name"] == name:
                    # If AST captured the value, return it without importing
                    if "value" in m:
                        result = {"name": name, "module": entry["fq"].rsplit(".", 1)[-1],
                                  "type": type(m["value"]).__name__, "value": _make_serializable(m["value"])}
                        return json.dumps(result)
                    # For functions/classes, return AST info without importing
                    if m["type"] in ("function", "class"):
                        result = {"name": name, "module": entry["fq"].rsplit(".", 1)[-1], "type": m["type"]}
                        if m.get("signature"):
                            result["signature"] = m["signature"]
                        if m.get("docstring"):
                            result["docstring"] = m["docstring"]
                        elif m.get("description"):
                            result["docstring"] = m["description"]
                        if m.get("methods"):
                            result["methods"] = m["methods"]
                        return json.dumps(result)
                    # Variable without literal value — return source expression if available
                    result = {"name": name, "module": entry["fq"].rsplit(".", 1)[-1], "type": "variable"}
                    if "value" in m:
                        result["value"] = m["value"]
                    return json.dumps(result)

        # Fallback: geeView mapper methods (not in top-level AST)
        gv_entry = _MODULE_TREE.get("geeViz.geeView")
        if gv_entry:
            # Check mapper class members from AST
            for m in gv_entry.get("members", []):
                if m["type"] == "class" and m["name"] == "mapper":
                    if name in m.get("methods", []):
                        mod_obj = _get_module(gv_entry)
                        if mod_obj:
                            mapper_cls = getattr(mod_obj, "mapper", None)
                            if mapper_cls:
                                obj = getattr(mapper_cls, name, None)
                                if obj:
                                    return json.dumps(_describe_object(obj, name=f"mapper.{name}", module_name="geeView"))
                    break

        # Search class methods across all modules (e.g. bare "addTimeLapse" finds mapper.addTimeLapse)
        for short, entry in _MODULE_TREE.items():
            if short != entry["fq"]:
                continue
            for m in entry.get("members", []):
                if m["type"] == "class" and m.get("methods") and name in m["methods"]:
                    # Found as a method — import to get full docstring
                    mod_obj = _get_module(entry)
                    if mod_obj:
                        cls = getattr(mod_obj, m["name"], None)
                        if cls:
                            obj = getattr(cls, name, None)
                            if obj:
                                return json.dumps(_describe_object(obj, name=f"{m['name']}.{name}", module_name=entry["fq"].rsplit(".", 1)[-1]))

        # Check REPL namespace as last resort
        if name in ns:
            return json.dumps(_describe_object(ns[name], name=name, module_name="(REPL namespace)"))

        return json.dumps({"error": f"{name!r} not found in any geeViz module or REPL namespace."})

    # --- Module listing (AST-based, no import) ---
    if module:
        tree_entry = _MODULE_TREE.get(module)
        if tree_entry and "members" in tree_entry:
            # Use AST index — zero imports
            q = query.lower() if query else ""
            results = []
            for m in tree_entry["members"]:
                name_match = not q or q in m["name"].lower() or q in m.get("description", "").lower()
                if name_match:
                    r = {"name": m["name"], "type": m["type"]}
                    if m.get("description"):
                        r["description"] = m["description"]
                    if m.get("signature"):
                        r["signature"] = m["signature"]
                    if m.get("methods"):
                        r["methods"] = m["methods"]
                    results.append(r)
                # Also list class methods as individual entries
                if m["type"] == "class" and m.get("methods"):
                    for meth in m["methods"]:
                        if not q or q in meth.lower():
                            results.append({"name": f"{m['name']}.{meth}", "type": "method",
                                            "description": f"Method of {m['name']}"})
            return json.dumps({"module": module, "count": len(results), "results": results})

        # Fallback for REPL modules (ee, etc.) — must import/inspect
        _, mod_obj = _resolve_module(module, ns)
        if mod_obj is None:
            return json.dumps({"error": f"Module {module!r} not found."})
        results = []
        for attr_name, obj, kind, first_line, sig in _iter_module_members(mod_obj, query):
            r = {"name": attr_name, "type": kind, "description": first_line}
            if sig:
                r["signature"] = sig
            results.append(r)
        # When a query is given, also match METHODS on classes exposed by
        # this module — surfaced as "ClassName.method". Without this,
        # search_codebase(module="ee", query="getThumbURL") returns 0
        # because getThumbURL lives on ee.Image (a class attribute), not
        # on the ee module itself. Mirrors the geeViz-AST branch above
        # (see the `class + methods` block in the AST path), so REPL
        # modules and geeViz modules behave the same for method search.
        if query:
            q_lower = query.lower()
            seen_names = {r["name"] for r in results}
            for cls_name in dir(mod_obj):
                if cls_name.startswith("_"):
                    continue
                cls = getattr(mod_obj, cls_name, None)
                if not _inspect.isclass(cls):
                    continue
                for m_name in dir(cls):
                    if m_name.startswith("_") or q_lower not in m_name.lower():
                        continue
                    m_obj = getattr(cls, m_name, None)
                    if m_obj is None or not callable(m_obj):
                        continue
                    full = f"{cls_name}.{m_name}"
                    if full in seen_names:
                        continue
                    seen_names.add(full)
                    entry = {"name": full, "type": "method"}
                    m_doc = _inspect.getdoc(m_obj) or ""
                    first = m_doc.split("\n")[0].strip()
                    entry["description"] = first if first else f"Method of {cls_name}"
                    try:
                        entry["signature"] = f"{m_name}{_inspect.signature(m_obj)}"
                    except (ValueError, TypeError):
                        pass
                    results.append(entry)
        return json.dumps({"module": module, "count": len(results), "results": results})

    # --- Search across all modules (AST-based, no import) ---
    if query:
        q = query.lower()
        results = []
        seen_fqs = set()
        # Matching used to be name-or-FIRST-DOCSTRING-LINE, unranked. Two
        # failures came out of that, both seen in a live session:
        #
        #   "evalidator" -> 0 real hits. EVALIDator is what the FIA API
        #       is called and it is all over fia.py, but never in a name
        #       or a summary line, so the code was invisible under the
        #       word a user would actually type.
        #   "carbon"     -> 0 hits, same reason.
        #
        # So match the WHOLE docstring. That alone would bury the good
        # hits under incidental prose, hence the rank: an exact name beats
        # a partial name beats a summary line beats a mention in the body.
        RANK_EXACT, RANK_NAME, RANK_SUMMARY, RANK_BODY = 0, 1, 2, 3
        for short, entry in _MODULE_TREE.items():
            fq = entry["fq"]
            if fq in seen_fqs:
                continue
            seen_fqs.add(fq)
            mod_short = fq.rsplit(".", 1)[-1]

            # The MODULE itself can be the answer. "which module talks to
            # EVALIDator?" is a real question, and answering it with a
            # list of functions that each mention the word in passing is
            # worse than naming the module.
            mod_name_l = mod_short.lower()
            if q in mod_name_l or q in entry.get("module_doc", "").lower():
                results.append({
                    "_rank": RANK_EXACT if q == mod_name_l else RANK_SUMMARY,
                    # Full path here, not the short name — a row reading
                    # {"module": "fia", "name": "fia"} tells the reader
                    # nothing about where it lives.
                    "module": fq, "name": mod_short, "type": "module",
                    "description": entry.get("doc", ""),
                    "hint": f"search_codebase(module='{mod_short}') to list it",
                })

            for m in entry.get("members", []):
                name_l = m["name"].lower()
                desc_l = m.get("description", "").lower()
                body_l = m.get("docstring", "").lower()
                if name_l == q:
                    rank = RANK_EXACT
                elif q in name_l:
                    rank = RANK_NAME
                elif q in desc_l:
                    rank = RANK_SUMMARY
                elif q in body_l:
                    rank = RANK_BODY
                else:
                    # Also check class method names
                    if m["type"] == "class" and m.get("methods"):
                        matching_methods = [meth for meth in m["methods"] if q in meth.lower()]
                        for meth in matching_methods:
                            results.append({"_rank": RANK_NAME,
                                            "module": mod_short, "name": f"{m['name']}.{meth}", "type": "method",
                                            "description": f"Method of {m['name']}"})
                    continue
                r = {"_rank": rank, "module": mod_short, "name": m["name"], "type": m["type"]}
                if m.get("description"):
                    r["description"] = m["description"]
                if m.get("signature"):
                    r["signature"] = m["signature"]
                results.append(r)
                # If it's a class, also include matching methods
                if m["type"] == "class" and m.get("methods"):
                    for meth in m["methods"]:
                        if q in meth.lower():
                            results.append({"_rank": RANK_NAME,
                                            "module": mod_short, "name": f"{m['name']}.{meth}", "type": "method",
                                            "description": f"Method of {m['name']}"})

        # Best matches first. Ties keep their discovery order, which is
        # module-walk order — stable, so the same query always answers
        # the same way.
        results.sort(key=lambda r: r.get("_rank", RANK_BODY))
        total = len(results)
        # Whole-docstring matching makes a common word ("image", "band")
        # match a great deal. Cap what comes back, and SAY the cap was
        # hit rather than silently serving the top slice as if it were
        # everything.
        _CAP = 40
        truncated = total > _CAP
        results = results[:_CAP]
        for r in results:
            r.pop("_rank", None)
        if truncated:
            return json.dumps({
                "query": query, "count": len(results), "total_matches": total,
                "truncated": True,
                "note": (f"{total} matches; showing the {_CAP} best. Narrow "
                         f"the query, or use module=... to list one module."),
                "results": results,
            })

        # Empty result + dataset-shaped query → transparently forward to
        # search_datasets so the agent doesn't need a second tool call.
        # A `routed_to` note tells the agent what happened.
        if not results and _looks_like_dataset_query(query):
            try:
                ds_json = search_datasets(query=query)
                ds = json.loads(ds_json) if isinstance(ds_json, str) else ds_json
                if isinstance(ds, list):
                    ds = {"results": ds}
                ds["routed_to"] = "search_datasets"
                ds["reason"] = (
                    "search_codebase returned 0 code hits; query looked "
                    "dataset-shaped, forwarded to search_datasets"
                )
                return json.dumps(ds)
            except Exception:
                pass

        return json.dumps({"query": query, "count": len(results), "results": results})

    # --- No args: list all modules (AST-based, no import) ---
    seen = set()
    modules = []
    for short, entry in sorted(_MODULE_TREE.items()):
        fq = entry["fq"]
        if fq in seen or short != fq.rsplit(".", 1)[-1]:
            continue
        seen.add(fq)
        modules.append({"name": short, "full_path": fq, "description": entry.get("doc", "")})
    return json.dumps({
        "modules": modules,
        "count": len(modules),
        "usage": 'Use module="<name>" to list members, query="<term>" to search, name="<object>" for details.',
    })


# Examples tool removed -- use search_codebase(module="examples") to list,
# search_codebase(name="CCDCViz") to read source.
# ---------------------------------------------------------------------------
# Map control (consolidated)
# ---------------------------------------------------------------------------

@app.tool(annotations=_WRITE)
def map_control(action: str = "view", open_browser: bool = True, filename: str = "map.html", session_id: str = None):
    """Control the geeView interactive map.

    ``action="view"`` writes the per-session runGeeViz.js to disk and opens
    ``geeView/index.html``. In plain Python this is a ``file:///`` URL;
    in notebooks it uses an in-process threaded HTTP server
    (``http://localhost:<port>/...``) for iframe display. The access
    token is passed via URL query string.

    Supported ``action`` values:

    - ``"view"`` (default) — validates all layers first (runs
      ``test_layers`` internally). If any layer fails, returns the errors
      without opening the map. If all pass, opens the map and returns
      the URL.
    - ``"layers"`` — list current layers with visibility and viz params.
    - ``"layer_names"`` — quick list of just layer names (lightweight).
    - ``"clear"`` — remove all layers and commands.
    - ``"test_layers"`` — fast validation, calls ``getMapId()`` on all
      layers in parallel. Catches bad bands, invalid viz, computation
      errors. No browser required. Returns pass/fail per layer.
    - ``"preview"`` — quick visual check. Fetches a small grid of EE
      map tiles for each layer around the current center/zoom and
      returns them as inline images (one per layer). No browser
      required. Use to visually verify layers have data in the right
      area. Returns ``{layer_name: PNG image}`` plus center and zoom.
      Optional: ``"preview,zoom=10,grid=2"`` to override zoom or grid.
    - ``"export"`` — validates all layers first (like ``"view"``), then
      writes a self-contained geeView HTML to
      ``generated_outputs/{filename}``. If any layer fails, returns
      errors without exporting. The HTML uses absolute asset paths
      under ``/geeView/static`` and a ``__GEEVIZ_TOKEN__`` placeholder
      for the access token. Suitable for chat UIs that serve the HTML
      themselves and inject a fresh token on load. Use this for
      chat-embedded maps that should survive session reloads.
    - ``"export_layers_json"`` — bundle every currently-added layer
      into a JSON file under ``generated_outputs/{filename}``. Use when
      the agent is building a CUSTOM HTML dashboard (Leaflet, MapLibre,
      etc.) and needs the EE layers to be re-mintable. The returned
      ``refresh_url`` is an endpoint the agent embeds in its HTML;
      fetching it returns fresh tile URLs for every layer so dashboards
      survive after EE map IDs expire. Handles all the same input
      types as ``addLayer`` (Image, ImageCollection, Geometry, Feature,
      FeatureCollection) plus tile-URL layers added via
      ``Map.addTileLayer``.

    Args:
        action: One of the values listed above.
        open_browser: For ``action="view"``, whether to open in browser
            (default True).
        filename: For ``action="export"``, the output filename (saved
            under ``generated_outputs/``). Defaults to ``map.html``.
        session_id: Session identifier for namespace isolation.

    Returns:
        JSON with action-specific results.
    """
    sess = _ensure_initialized(session_id)
    Map = sess.namespace["Map"]
    act = action.lower().strip()

    # Use the same streaming stdout as run_code so the frontend polls it
    try:
        os.makedirs(os.path.dirname(sess.stdout_stream_file), exist_ok=True)
        with open(sess.stdout_stream_file, "w", encoding="utf-8") as f:
            f.write("")
    except Exception:
        pass
    # Redirect stdout to the streaming file for live polling by the frontend.
    # Use _StreamingStdout (same as run_code) so print() calls appear in the UI.
    _mc_stdout = _StreamingStdout(sess.stdout_stream_file)
    _mc_orig = sys.stdout
    sys.stdout = _mc_stdout

    try:
        result_json = _map_control_inner(Map, act, sess, open_browser, filename, _mc_stdout)
        # Inject captured stdout into the response so the frontend shows it
        stdout_text = _mc_stdout.getvalue().strip()
        if stdout_text:
            try:
                result = json.loads(result_json)
                result["stdout"] = stdout_text
                result_json = json.dumps(result)
            except (json.JSONDecodeError, TypeError):
                pass
        return result_json
    finally:
        sys.stdout = _mc_orig


def _map_control_inner(Map, act, sess, open_browser, filename, _mc_stdout):
    """Inner logic for map_control, wrapped so stdout is always restored."""

    if act == "view":
        # --- Pre-flight: validate all layers before opening the map ---
        n_layers = len(getattr(Map, "idDictList", []))
        print(f"Validating {n_layers} layer(s)...")
        try:
            test_result = Map.testLayers()
            failed = [l for l in test_result["layers"] if l["status"] == "error"]
            passed = [l for l in test_result["layers"] if l["status"] == "ok"]
            for l in passed:
                print(f"  PASS: {l['name']}")
                for w in l.get("warnings") or []:
                    print(f"    WARN: {w}")
            for l in failed:
                print(f"  FAIL: {l['name']} — {l.get('error', 'unknown error')[:100]}")
            if failed:
                print(f"Validation failed — {len(failed)} layer(s) have errors.")
                return json.dumps({
                    "pass": False,
                                        "message": f"Map not opened — {len(failed)} layer(s) failed validation. Fix errors and retry.",
                    "layers": test_result["layers"],
                })
            print(f"All {n_layers} layer(s) passed validation.")
        except Exception as exc:
            print(f"Validation error: {exc}")
            return json.dumps({
                "pass": False,
                                "message": f"Layer validation raised an exception: {exc}. Map not opened.",
            })

        # If any layer has canAreaChart=True and no turnOn command is already set,
        # auto-enable area charting instead of the default inspector.
        try:
            existing_cmds = list(getattr(Map, "mapCommandList", []))
            has_turn_on = any("turnOn" in c for c in existing_cmds)
            if not has_turn_on:
                has_area_chart = False
                for entry in getattr(Map, "idDictList", []):
                    viz_raw = entry.get("viz", "{}")
                    try:
                        viz = json.loads(viz_raw) if isinstance(viz_raw, str) else viz_raw
                    except (json.JSONDecodeError, TypeError):
                        viz = {}
                    if isinstance(viz, dict) and viz.get("canAreaChart"):
                        has_area_chart = True
                        break
                if has_area_chart:
                    Map.turnOnAutoAreaCharting()
        except Exception:
            pass  # fall back to default inspector behavior in Map.view()

        url_buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(url_buf):
                Map.view(open_browser=open_browser, open_iframe=False)
        except Exception as exc:
            return json.dumps({"error": str(exc)})
        printed = url_buf.getvalue()
        url = None
        # Look for a URL on the "geeView URL:" line. Accept both http(s)://
        # (legacy server mode) and file:/// (srcdoc mode, the new default).
        for line in printed.splitlines():
            line = line.strip()
            if "geeView URL:" in line:
                tail = line.split("geeView URL:", 1)[1].strip()
                if tail:
                    url = tail
                break
        # Fallback: find any line starting with http or file
        if url is None:
            for line in printed.splitlines():
                line = line.strip()
                if line.startswith(("http://", "https://", "file:///")):
                    url = line
                    break
        layer_count = len(Map.idDictList) if hasattr(Map, "idDictList") else 0
        print(f"Map opened with {layer_count} layer(s).")
        return json.dumps({
            "url": url,
            "layer_count": layer_count,
                        "message": f"Map opened with {layer_count} layer(s)." if url else "Map.view() ran but no URL was captured.",
            "raw_output": printed.strip(),
        })

    elif act == "layers":
        layers = []
        for entry in getattr(Map, "idDictList", []):
            viz_raw = entry.get("viz", "{}")
            try:
                viz = json.loads(viz_raw) if isinstance(viz_raw, str) else viz_raw
            except (json.JSONDecodeError, TypeError):
                viz = viz_raw
            layers.append({
                "name": entry.get("name", "(unnamed)"),
                "visible": entry.get("visible", "true"),
                "function": entry.get("function", ""),
                "viz": viz,
            })
        commands = list(getattr(Map, "mapCommandList", []))
        return json.dumps({"layer_count": len(layers), "layers": layers, "commands": commands})

    elif act == "layer_names":
        names = [entry.get("name", "(unnamed)") for entry in getattr(Map, "idDictList", [])]
        return json.dumps({"layer_count": len(names), "layer_names": names})

    elif act == "clear":
        try:
            Map.clearMap()
        except Exception as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps({"success": True, "message": "Map cleared. All layers and commands removed."})

    elif act == "test_layers":
        try:
            result = Map.testLayers()
        except Exception as exc:
            return json.dumps({"error": str(exc)})

        errors = [l for l in result["layers"] if l["status"] == "error"]
        warnings = [l for l in result["layers"] if l.get("warnings")]
        parts = []
        if errors:
            parts.append(f"{len(errors)} layer error(s) detected.")
        if warnings:
            parts.append(f"{len(warnings)} layer(s) with warnings.")
        if not parts:
            parts.append("All layers passed.")
        return json.dumps({
            "pass": result["pass"] and not errors,
            "message": " ".join(parts),
            "layers": result["layers"],
        })

    elif act == "preview" or act.startswith("preview,"):
        # Quick tile-based preview — returns per-layer images the LLM can see
        grid_size = 3
        zoom_override = None
        if "," in act:
            # e.g. action="preview,zoom=10,grid=2"
            for part in act.split(",")[1:]:
                part = part.strip()
                if part.startswith("zoom="):
                    try: zoom_override = int(part.split("=")[1])
                    except ValueError: pass
                elif part.startswith("grid="):
                    try: grid_size = int(part.split("=")[1])
                    except ValueError: pass

        try:
            result = Map.previewMap(grid_size=grid_size, zoom=zoom_override)
        except Exception as exc:
            return json.dumps({"error": f"Preview failed: {exc}"})

        layer_images = result.get("layers", {})
        n_ok = sum(1 for v in layer_images.values() if v is not None)
        n_fail = sum(1 for v in layer_images.values() if v is None)
        center = result.get("center", [0, 0])
        z = result.get("zoom", 8)

        # Save preview images to session output dir
        import os as _os
        out = sess.output_dir
        _os.makedirs(out, exist_ok=True)
        saved = {}
        for name, img_bytes in layer_images.items():
            if img_bytes is not None:
                safe = name.replace(" ", "_").replace("/", "_")[:40]
                fname = f"preview_{safe}.png"
                with open(_os.path.join(out, fname), "wb") as f:
                    f.write(img_bytes)
                saved[name] = fname

        # Build response — JSON summary (visible in UI) + inline images (visible to LLM)
        summary = {
            "message": f"Preview generated for {n_ok} layer(s) at zoom {z}.",
            "center": center,
            "zoom": z,
        }
        if n_fail:
            summary["failed"] = n_fail

        if _MCPImage and saved:
            # Build viz context for each layer so LLM can interpret colors
            layer_viz = {}
            for idDict in Map.idDictList:
                lname = idDict.get("name", "")
                viz = idDict.get("_viz", {})
                if lname in saved:
                    desc_parts = []
                    if viz.get("bands"):
                        desc_parts.append(f"bands={viz['bands']}")
                    if viz.get("palette"):
                        p = viz["palette"]
                        if isinstance(p, list) and len(p) > 5:
                            desc_parts.append(f"palette=[{p[0]}...{p[-1]}] ({len(p)} colors)")
                        else:
                            desc_parts.append(f"palette={p}")
                    if viz.get("min") is not None:
                        desc_parts.append(f"min={viz['min']}")
                    if viz.get("max") is not None:
                        desc_parts.append(f"max={viz['max']}")
                    lt = viz.get("layerType", "")
                    if "Vector" in lt or "vector" in lt:
                        desc_parts.append("vector")
                    if lt == "tileMapService":
                        # Includes Map.addTileLayer + esriLib.addEsri{Map,Image}Service
                        # (cached tile path). Show the tile source so the user knows
                        # it's an external XYZ layer, not an EE image.
                        _tpl = idDict.get("_tile_url_template", "")
                        _host = _tpl.split("/")[2] if "://" in _tpl else _tpl[:40]
                        desc_parts.append(f"tile ({_host})")
                    if lt == "dynamicMapService":
                        # Map.addDynamicMapService (also the esriLib fallback for
                        # dynamic MapServers like FEMA NFHL). Uses per-viewport
                        # ArcGIS /export?f=image — cartography preserved from source.
                        _bu = idDict.get("_dyn_base_url_1", "")
                        _host = _bu.split("/")[2] if "://" in _bu else _bu[:40]
                        desc_parts.append(f"dynamic Esri MapService ({_host})")
                    for vk in ("strokeColor", "color", "fillColor", "pointRadius", "width"):
                        if viz.get(vk) is not None:
                            desc_parts.append(f"{vk}={viz[vk]}")
                    if viz.get("autoViz"):
                        desc_parts.append("autoViz=True (thematic/class data)")
                    if idDict.get("_is_mosaic_preview"):
                        desc_parts.append("MOSAIC of time-lapse — single representative tile, not animated")
                    layer_viz[lname] = ", ".join(desc_parts) if desc_parts else ""

            content_parts = [json.dumps(summary)]
            for name, fname in saved.items():
                # Add layer label + viz context before each image
                ctx = layer_viz.get(name, "")
                label = f"Layer: {name}"
                if ctx:
                    label += f" ({ctx})"
                content_parts.append(label)
                fpath = _os.path.join(out, fname)
                with open(fpath, "rb") as f:
                    content_parts.append(_MCPImage(data=f.read(), format="png"))
            return content_parts

        # Fallback: return JSON with file paths
        summary["files"] = saved
        return json.dumps(summary)

    elif act == "export":
        # --- Pre-flight: validate all layers before exporting ---
        n_layers = len(getattr(Map, "idDictList", []))
        print(f"Validating {n_layers} layer(s)...")
        try:
            test_result = Map.testLayers()
            failed = [l for l in test_result["layers"] if l["status"] == "error"]
            passed = [l for l in test_result["layers"] if l["status"] == "ok"]
            for l in passed:
                print(f"  PASS: {l['name']}")
                for w in l.get("warnings") or []:
                    print(f"    WARN: {w}")
            for l in failed:
                print(f"  FAIL: {l['name']} — {l.get('error', 'unknown error')[:100]}")
            if failed:
                print(f"Validation failed — {len(failed)} layer(s) have errors.")
                return json.dumps({
                    "pass": False,
                    "message": f"Map not exported — {len(failed)} layer(s) failed validation. Fix errors and retry.",
                    "layers": test_result["layers"],
                })
            print(f"All {n_layers} layer(s) passed. Exporting map...")
        except Exception as exc:
            print(f"Validation error: {exc}")
            return json.dumps({
                "pass": False,
                "message": f"Layer validation raised an exception: {exc}. Map not exported.",
            })

        # Same auto-area-charting fallback as `view`
        try:
            existing_cmds = list(getattr(Map, "mapCommandList", []))
            has_turn_on = any("turnOn" in c for c in existing_cmds)
            if not has_turn_on:
                has_area_chart = False
                for entry in getattr(Map, "idDictList", []):
                    viz_raw = entry.get("viz", "{}")
                    try:
                        viz = json.loads(viz_raw) if isinstance(viz_raw, str) else viz_raw
                    except (json.JSONDecodeError, TypeError):
                        viz = {}
                    if isinstance(viz, dict) and viz.get("canAreaChart"):
                        has_area_chart = True
                        break
                if has_area_chart:
                    Map.turnOnAutoAreaCharting()
        except Exception:
            pass

        # Resolve output path under the session's generated_outputs directory.
        out_path = filename if os.path.isabs(filename) else os.path.join(sess.output_dir, filename)
        try:
            written_path = Map.export_html(out_path)
        except Exception as exc:
            return json.dumps({"error": str(exc)})
        layer_count = len(Map.idDictList) if hasattr(Map, "idDictList") else 0
        print(f"Map exported with {layer_count} layer(s) to {os.path.basename(written_path)}.")
        return json.dumps({
            "path": written_path,
            "layer_count": layer_count,
                        "message": f"Map exported with {layer_count} layer(s) to {os.path.basename(written_path)}.",
        })

    elif act == "export_layers_json":
        # Serialize all currently-added layers to a JSON file. A separate
        # /api/dashboard/urls endpoint reads this file at viewing time,
        # calls getMapId on each layer, and returns fresh tile URLs — so
        # custom HTML dashboards survive expiration.
        try:
            result = Map.exportLayerJson(filename=filename or "dashboard_layers.json",
                                         output_dir=sess.output_dir)
        except Exception as exc:
            return json.dumps({"error": str(exc)})
        # Add the refresh URL the agent should embed in its custom HTML.
        # sess.session_id is the canonical per-session identifier — `session_id`
        # is the outer map_control() parameter and isn't in scope inside
        # _map_control_inner().
        sid = sess.session_id or ""
        # Relative URL — works when the dashboard HTML is served from the
        # same origin as the agent (i.e., embedded in the agent UI). For
        # standalone hosting on a different origin, the dashboard would
        # need an absolute URL and CORS — out of scope for now.
        result["refresh_url"] = (
            f"/api/dashboard/urls?session_id={sid}"
            f"&file={os.path.basename(result['path'])}"
        )
        result["message"] = (
            f"{result['layer_count']} layer(s) saved to {os.path.basename(result['path'])}. "
            f"Embed refresh_url in your custom HTML to fetch fresh tile URLs."
        )
        return json.dumps(result)

    else:
        return json.dumps({"error": f"Unknown action: {action!r}. Use 'view', 'layers', 'layer_names', 'clear', 'test_layers', 'preview', 'export', or 'export_layers_json'."})


# ---------------------------------------------------------------------------
# Tool 13: save_session
# ---------------------------------------------------------------------------

@app.tool(annotations=_WRITE)
def save_session(filename: str = "", format: str = "py",
                  sliced: bool = True, session_id: str = None) -> str:
    """Save the accumulated run_code history to a .py script or .ipynb notebook.

    Args:
        filename: Optional custom filename (saved in geeViz/mcp/generated_scripts/).
                  If omitted, uses a timestamped default. The correct extension
                  is added automatically based on format.
        format: Output format -- "py" (default) for a standalone Python script,
                "ipynb" for a Jupyter notebook.
        sliced: When True (default), run backward program slicing anchored on
                the last successful block and emit ONLY the surviving blocks —
                exploratory dead code and superseded assignments are dropped.
                When False, emit every successful block verbatim (legacy
                behavior; useful when the slicer's judgment is wrong for a
                specific session). See ``_slice_history`` for the rules.

    Returns:
        JSON with the file path, block-retention counts, and status.
    """
    sess = _get_session(session_id)

    if format not in ("py", "ipynb"):
        return json.dumps({
            "error": f"Invalid format: {format!r}. Must be 'py' or 'ipynb'.",
        })

    if not sess.code_history:
        return json.dumps({
            "error": "No code has been executed yet. Use run_code first.",
        })

    total_blocks = len(sess.code_history)
    keep_idxs = _slice_history(sess) if sliced else list(range(total_blocks))
    dropped = total_blocks - len(keep_idxs)

    if format == "py":
        if filename:
            if not filename.endswith(".py"):
                filename += ".py"
            os.makedirs(sess.script_dir, exist_ok=True)
            sess.current_script_path = os.path.join(sess.script_dir, filename)

        if sliced:
            path = _save_history_to_file_sliced(sess)
        else:
            path = _save_history_to_file(sess)
        return json.dumps({
            "success": True,
            "script_path": path,
            "code_blocks": len(keep_idxs),
            "total_blocks": total_blocks,
            "dropped": dropped,
            "sliced": sliced,
            "message": (
                f"Saved {len(keep_idxs)} of {total_blocks} code block(s) "
                f"to {path}" + (f" ({dropped} dropped by slicer)" if dropped else "")
            ),
        })

    # format == "ipynb"
    import datetime
    os.makedirs(sess.script_dir, exist_ok=True)

    if filename:
        if not filename.endswith(".ipynb"):
            filename += ".ipynb"
        nb_path = os.path.join(sess.script_dir, filename)
    else:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        nb_path = os.path.join(sess.script_dir, f"session_{ts}.ipynb")

    if sliced:
        _save_history_to_notebook_sliced(sess, nb_path)
        return json.dumps({
            "success": True,
            "notebook_path": nb_path,
            "code_cells": len(keep_idxs),
            "total_cells": total_blocks,
            "dropped": dropped,
            "sliced": True,
            "message": (
                f"Saved {len(keep_idxs)} of {total_blocks} code cell(s) "
                f"to {nb_path}" + (f" ({dropped} dropped by slicer)" if dropped else "")
            ),
        })

    # Build notebook structure (nbformat 4.5)
    cells = []

    # Markdown header cell
    cells.append({
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "# geeViz MCP Session\n",
            "\n",
            f"Auto-generated by geeViz MCP server on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.\n",
        ],
    })

    # Import cell
    cells.append({
        "cell_type": "code",
        "metadata": {},
        "source": [
            "import geeViz.geeView as gv\n",
            "import geeViz.getImagesLib as gil\n",
            "import geeViz.getSummaryAreasLib as sal\n",
            "from geeViz.outputLib import charts as cl\n",
            "from geeViz.outputLib import thumbs as tl\n",
            "from geeViz.outputLib import reports as rl\n",
            "ee = gv.ee\n",
            "Map = gv.Map",
        ],
        "execution_count": None,
        "outputs": [],
    })

    # One code cell per run_code call
    for i, block in enumerate(sess.code_history):
        lines = block.splitlines(True)  # keep line endings
        # Ensure last line has newline for notebook format
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        cells.append({
            "cell_type": "code",
            "metadata": {},
            "source": lines,
            "execution_count": None,
            "outputs": [],
        })

    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": sys.version.split()[0],
            },
        },
        "cells": cells,
    }

    with open(nb_path, "w", encoding="utf-8") as f:
        json.dump(notebook, f, indent=1, ensure_ascii=False)

    return json.dumps({
        "success": True,
        "notebook_path": nb_path,
        "code_cells": len(sess.code_history),
        "message": f"Saved {len(sess.code_history)} code cell(s) to {nb_path}",
    })


# ---------------------------------------------------------------------------
# Environment info (consolidated)
# ---------------------------------------------------------------------------

_NAMESPACE_BUILTINS = {"ee", "Map", "gv", "gil"}


@app.tool(annotations=_READ_ONLY_OPEN)
def env_info(action: str = "version", session_id: str = None) -> str:
    """Get environment information: versions, REPL namespace, or project details.

    Args:
        action: What to return:
            - "version" (default): geeViz, EE, and Python versions.
            - "namespace": User-defined variables in the REPL (no getInfo calls).
            - "project": Current EE project ID and root assets.

    Returns:
        JSON with action-specific results.
    """
    act = action.lower().strip()

    if act == "version":
        import geeViz
        result = {
            "geeViz_version": geeViz.__version__,
            "python_version": sys.version,
            "platform": sys.platform,
        }
        try:
            import ee
            result["ee_version"] = ee.__version__
        except Exception:
            result["ee_version"] = "(not available)"
        return json.dumps(result)

    elif act == "namespace":
        sess = _ensure_initialized(session_id)
        ee = sess.namespace["ee"]
        entries = []
        for name, obj in sorted(sess.namespace.items()):
            if name.startswith("_") or name in _NAMESPACE_BUILTINS:
                continue
            type_name = type(obj).__name__
            for ee_type in ("Image", "ImageCollection", "FeatureCollection",
                            "Feature", "Geometry", "Number", "String",
                            "List", "Dictionary", "Filter", "Reducer",
                            "ComputedObject"):
                if isinstance(obj, getattr(ee, ee_type, type(None))):
                    type_name = f"ee.{ee_type}"
                    break
            try:
                r = repr(obj)
                if len(r) > 2000:
                    r = r[:2000] + "..."
            except Exception:
                r = "(repr failed)"
            entries.append({"name": name, "type": type_name, "repr": r})
        return json.dumps({
            "count": len(entries), "variables": entries,
            "note": "Excludes builtins (ee, Map, gv, gil). No getInfo() calls made.",
        })

    elif act == "project":
        sess = _ensure_initialized(session_id)
        ee = sess.namespace["ee"]
        result: dict = {}
        try:
            result["project_id"] = ee.data._get_state().cloud_api_user_project
        except Exception as exc:
            result["project_id"] = None
            result["project_error"] = str(exc)
        if result.get("project_id"):
            try:
                root = f"projects/{result['project_id']}/assets"
                assets_response = ee.data.listAssets({"parent": root})
                assets = assets_response.get("assets", [])
                result["root_assets"] = [
                    {"id": a.get("id") or a.get("name", ""), "type": a.get("type", "UNKNOWN")}
                    for a in assets[:500]
                ]
                result["root_asset_count"] = len(assets)
            except Exception as exc:
                result["root_assets"] = []
                result["assets_error"] = str(exc)
        return json.dumps(result)

    elif act == "reload":
        # Force-reload all geeViz modules in the running process.
        # Use this after editing geeViz source files to pick up changes
        # without restarting the MCP server or ADK session.
        import importlib
        reloaded = []
        for mod_name in sorted(sys.modules.keys()):
            if mod_name.startswith("geeViz"):
                try:
                    importlib.reload(sys.modules[mod_name])
                    reloaded.append(mod_name)
                except Exception:
                    pass
        # Re-initialize the REPL namespace with fresh modules
        _reset_namespace(session_id)
        return json.dumps({
            "action": "reload",
            "reloaded_modules": reloaded,
            "count": len(reloaded),
            "message": "All geeViz modules reloaded. REPL namespace reset.",
        })

    else:
        return json.dumps({"error": f"Unknown action: {action!r}. Use 'version', 'namespace', 'project', or 'reload'."})


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# View generated output (returns image inline for LLM visual inspection)
# ---------------------------------------------------------------------------
# NOTE: view_output is registered below ONLY if _MCPImage loaded successfully.
# It returns an Image object that MCP clients render inline.

@app.tool(annotations=_READ_ONLY)
def view_output(filename: str, session_id: str = None):
    """View a generated output file (PNG, GIF, JPEG) as an inline image.

    Use this to visually inspect charts, thumbnails, previews, or any
    image file in the generated_outputs directory. The image is returned
    directly so the LLM can see it.

    For map previews, first call map_control(action="preview") to generate
    preview PNGs, then call view_output("preview_Layer_Name.png") to see them.

    Args:
        filename: Name of the file in generated_outputs/ (e.g. "chart.png",
                  "preview_Elevation.png"). Just the filename, no directory.
        session_id: Session identifier for namespace isolation.

    Returns:
        The image content (displayed inline by the MCP client), or an error string.
    """
    import os as _os
    sess = _ensure_initialized(session_id)
    out_dir = sess.output_dir
    safe = _os.path.basename(filename)
    path = _os.path.join(out_dir, safe)
    # Also check base output dir as fallback
    if not _os.path.isfile(path):
        path = _os.path.join(_BASE_OUTPUT_DIR, safe)
    if not _os.path.isfile(path):
        return f"File not found: {safe}"
    ext = _os.path.splitext(safe)[1].lower()
    fmt_map = {".png": "png", ".gif": "gif", ".jpg": "jpeg", ".jpeg": "jpeg", ".webp": "webp"}
    fmt = fmt_map.get(ext)
    if not fmt:
        return f"Unsupported image format: {ext}. Supported: {', '.join(fmt_map.keys())}"
    with open(path, "rb") as f:
        data = f.read()

    import io
    from PIL import Image as _PILImage
    max_dim = 256  # Aggressive — LLM doesn't need pixel-perfect, just a recognizable preview

    def _shrink_to_jpeg(pil_img):
        """Downscale and convert to JPEG bytes for minimal context cost."""
        if max(pil_img.size) > max_dim:
            ratio = max_dim / max(pil_img.size)
            pil_img = pil_img.resize((int(pil_img.width * ratio), int(pil_img.height * ratio)), _PILImage.LANCZOS)
        if pil_img.mode in ("RGBA", "P", "LA"):
            bg = _PILImage.new("RGB", pil_img.size, (255, 255, 255))
            if pil_img.mode == "P":
                pil_img = pil_img.convert("RGBA")
            bg.paste(pil_img, mask=pil_img.split()[-1] if pil_img.mode in ("RGBA", "LA") else None)
            pil_img = bg
        elif pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=70, optimize=True)
        return buf.getvalue()

    # GIFs: extract a few key frames as JPEGs
    if fmt == "gif" and _MCPImage is not None:
        try:
            img = _PILImage.open(io.BytesIO(data))
            n_frames = getattr(img, "n_frames", 1)
            if n_frames > 1:
                max_frames = 6  # Reduced from 8 to keep context smaller
                step = max(1, n_frames // max_frames)
                parts = [f"GIF with {n_frames} frames — showing {min(n_frames, max_frames)} sampled frames:"]
                for i in range(0, n_frames, step):
                    if len([p for p in parts if not isinstance(p, str)]) >= max_frames:
                        break
                    img.seek(i)
                    frame = img.convert("RGBA")
                    jpeg_bytes = _shrink_to_jpeg(frame)
                    parts.append(f"Frame {i + 1}/{n_frames}:")
                    parts.append(_MCPImage(data=jpeg_bytes, format="jpeg"))
                return parts
        except Exception:
            pass  # Fall through to static handling

    # Static images: aggressive downscale to JPEG
    try:
        img = _PILImage.open(io.BytesIO(data))
        data = _shrink_to_jpeg(img)
        fmt = "jpeg"
    except Exception:
        pass
    if _MCPImage is not None:
        return _MCPImage(data=data, format=fmt)
    # Fallback: return full base64 data URI
    import base64 as _b64
    encoded = _b64.b64encode(data).decode("ascii")
    return f"data:image/{fmt};base64,{encoded}"


# Export image (consolidated)
# ---------------------------------------------------------------------------

@app.tool(annotations=_WRITE_OPEN)
def export_image(
    destination: str,
    image_var: str,
    region_var: str = "",
    scale: int = 30,
    crs: str = "EPSG:4326",
    overwrite: bool = False,
    asset_id: str = "",
    pyramiding_policy: str = "mean",
    output_name: str = "",
    drive_folder: str = "",
    bucket: str = "",
    output_no_data: int = -32768,
    file_format: str = "GeoTIFF",
    session_id: str = None,
) -> str:
    """Export an ee.Image to a GEE asset, Google Drive, or Cloud Storage.

    Args:
        destination: Where to export -- "asset", "drive", or "cloud".
        image_var: Name of the ee.Image variable in the REPL namespace.
        region_var: Name of an ee.Geometry or ee.FeatureCollection variable
                    for the export region. Required for drive/cloud exports;
                    optional for asset exports (uses image footprint if omitted).
        scale: Output resolution in meters (default 30).
        crs: Coordinate reference system (default "EPSG:4326").
        overwrite: If True, overwrite existing asset/file (default False).

        Asset-specific:
            asset_id: Full destination asset ID (required for destination="asset").
            pyramiding_policy: "mean" (default), "mode", "min", "max", "median", "sample".

        Drive-specific:
            output_name: Output filename without extension (required for drive/cloud).
            drive_folder: Google Drive folder name (required for destination="drive").

        Cloud Storage-specific:
            output_name: Output filename without extension (required for drive/cloud).
            bucket: GCS bucket name (required for destination="cloud").
            output_no_data: NoData value (default -32768).
            file_format: "GeoTIFF" (default) or "TFRecord".

    Returns:
        JSON with export status or an error.
    """
    sess = _ensure_initialized(session_id)
    ee = sess.namespace["ee"]
    gil = sess.namespace["gil"]
    dest = destination.lower().strip()

    if dest not in ("asset", "drive", "cloud"):
        return json.dumps({"error": f"Unknown destination: {destination!r}. Use 'asset', 'drive', or 'cloud'."})

    # Look up image
    image = sess.namespace.get(image_var)
    if image is None:
        return json.dumps({"error": f"Variable {image_var!r} not found in namespace."})
    if not isinstance(image, ee.Image):
        return json.dumps({"error": f"Variable {image_var!r} is {type(image).__name__}, not ee.Image."})

    # Look up region
    region = None
    if region_var:
        region = sess.namespace.get(region_var)
        if region is None:
            return json.dumps({"error": f"Variable {region_var!r} not found in namespace."})
        if isinstance(region, ee.FeatureCollection):
            region = region.geometry()
        elif not isinstance(region, ee.Geometry):
            return json.dumps({"error": f"Variable {region_var!r} is {type(region).__name__}, expected ee.Geometry or ee.FeatureCollection."})
    elif dest in ("drive", "cloud"):
        return json.dumps({"error": f"region_var is required for destination='{dest}'."})

    stdout_buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_buf):
            # In sandbox mode, create task but don't start it
            _start = not _SANDBOX_ENABLED

            if dest == "asset":
                if not asset_id:
                    return json.dumps({"error": "asset_id is required for destination='asset'."})
                asset_name = asset_id.split("/")[-1]
                gil.exportToAssetWrapper(
                    image, asset_name, asset_id,
                    pyramidingPolicyObject={"default": pyramiding_policy},
                    roi=region, scale=scale, crs=crs, overwrite=overwrite,
                    start=_start,
                )
            elif dest == "drive":
                if not output_name or not drive_folder:
                    return json.dumps({"error": "output_name and drive_folder are required for destination='drive'."})
                gil.exportToDriveWrapper(
                    image, output_name, drive_folder,
                    region, scale, crs, None, output_no_data,
                    start=_start,
                )
            elif dest == "cloud":
                if not output_name or not bucket:
                    return json.dumps({"error": "output_name and bucket are required for destination='cloud'."})
                gil.exportToCloudStorageWrapper(
                    image, output_name, bucket,
                    region, scale, crs, None, output_no_data,
                    file_format, {"cloudOptimized": True}, overwrite,
                    start=_start,
                )
    except Exception as exc:
        return json.dumps({"error": f"Export failed: {exc}", "stdout": stdout_buf.getvalue()})

    if _SANDBOX_ENABLED:
        return json.dumps({
            "success": False,
            "destination": dest,
            "message": "Export task was created but NOT started (sandbox mode). "
                       "Download the code and run it locally to execute the export.",
        })

    return json.dumps({
        "success": True,
        "destination": dest,
        "scale": scale,
        "crs": crs,
        "stdout": stdout_buf.getvalue().strip(),
        "message": f"Export to {dest} started. Use track_tasks() to monitor progress.",
    })


import urllib.request
import urllib.parse
import urllib.error

# Dataset catalog cache (for search_datasets)
_CACHE_DIR = os.path.join(_THIS_DIR, ".cache")
_CACHE_META_FILE = os.path.join(_CACHE_DIR, "meta.json")
_CACHE_TTL = 30 * 24 * 3600  # 30 days — STAC catalog barely changes; long TTL
                              # avoids day-2 chat spinner while the first
                              # tool call refreshes 500+ STAC leaves.
_CATALOG_FILES = {
    "official": "official_catalog.json",
    "community": "community_catalog.json",
    # bigquery-public-data enumerated via BQ API (no URL — see
    # _fetch_bigquery_catalog). Cached the same way as the EE catalogs.
    "bigquery": "bigquery_catalog.json",
}
_CATALOG_URLS = {
    "official": "https://earthengine-stac.storage.googleapis.com/catalog/catalog.json",
    "community": "https://raw.githubusercontent.com/samapriya/awesome-gee-community-datasets/master/community_datasets.json",
}
# All catalog names known to the cache layer. Keep in sync with
# _CATALOG_FILES; search_datasets validates ``source`` against this set.
_CATALOG_NAMES = tuple(_CATALOG_FILES.keys())
_cache_lock = threading.Lock()
import time as _time

def _fetch_catalog(url: str, name: str) -> list[dict] | None:
    """Fetch a dataset catalog from a URL and return a flat list of dataset dicts.

    For the official EE STAC catalog (nested 2-level structure), crawls all
    child catalogs to build a flat index. For the community catalog (already
    flat), returns as-is.
    """
    import concurrent.futures

    def _fetch_json(u, timeout=10):
        req = urllib.request.Request(u, headers={"User-Agent": "geeViz-MCP/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        data = _fetch_json(url, timeout=15)
    except Exception:
        return None

    # Already a flat list (community catalog)
    if isinstance(data, list):
        return data

    # Nested STAC catalog — crawl child links
    if isinstance(data, dict) and "links" in data:
        children = [l["href"] for l in data["links"] if l.get("rel") == "child"]
        datasets = []

        def _crawl_child(child_url):
            """Fetch a child catalog and extract dataset entries."""
            results = []
            try:
                child = _fetch_json(child_url, timeout=8)
                leaves = [l["href"] for l in child.get("links", []) if l.get("rel") == "child"]
                # Fetch all leaf datasets in this child catalog
                for leaf_url in leaves:
                    try:
                        leaf = _fetch_json(leaf_url, timeout=5)
                        entry = {
                            "id": leaf.get("id", ""),
                            "title": leaf.get("title", ""),
                            "type": leaf.get("gee:type", ""),
                            "provider": ", ".join(
                                p.get("name", "") for p in leaf.get("providers", [])
                            ),
                            "tags": ", ".join(leaf.get("keywords", [])),
                            "source": "official",
                            "date_range": "",
                        }
                        # Extract date range from extent
                        ext = leaf.get("extent", {}).get("temporal", {}).get("interval", [[]])
                        if ext and ext[0]:
                            entry["date_range"] = f"{ext[0][0] or ''} to {ext[0][1] or 'present'}"
                        # STAC URL for get_catalog_info
                        for link in leaf.get("links", []):
                            if link.get("rel") == "self":
                                entry["stac_url"] = link["href"]
                                break
                        results.append(entry)
                    except Exception:
                        pass
            except Exception:
                pass
            return results

        # Crawl all children in parallel (max 20 threads)
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            for child_results in pool.map(_crawl_child, children):
                datasets.extend(child_results)

        return datasets if datasets else None

    return None


def _fetch_bigquery_catalog() -> list[dict] | None:
    """Enumerate ``bigquery-public-data`` datasets + tables via the BQ API.

    Returns a flat list of dicts that scores identically to the EE
    catalogs inside ``search_datasets`` — one entry per DATASET and one
    per TABLE, so a query like "overture places" can resolve directly to
    ``bigquery-public-data.overture_maps.place`` without the caller
    knowing which dataset the table lives in.

    Auth: requires ADC (application-default credentials) for a project
    that has the BigQuery API enabled — the caller only needs
    ``bigquery.jobs.create`` on THEIR project; ``bigquery-public-data``
    is world-readable. Returns ``None`` when the dep isn't installed or
    auth fails, so ``search_datasets`` degrades cleanly to EE-only
    without noise on operational error.

    Cost: one ``list_datasets`` call (~1s) + one ``list_tables`` call per
    dataset (parallelized across 20 threads → ~10-15s total for
    bigquery-public-data). Cached to disk via the same
    ``_get_cached_catalog`` stale-while-revalidate wrapper as the EE
    catalogs, so day-2 lookups are instant.
    """
    try:
        from google.cloud import bigquery
        from google.auth import default as _adc_default
    except ImportError:
        print(
            "[geeViz MCP] bigquery: google-cloud-bigquery not installed; "
            "bigquery-public-data source will be empty",
            file=sys.stderr, flush=True,
        )
        return None
    try:
        creds, project = _adc_default()
    except Exception as _adc_err:
        print(
            f"[geeViz MCP] bigquery: ADC unavailable: {_adc_err!r}; "
            f"bigquery-public-data source will be empty",
            file=sys.stderr, flush=True,
        )
        return None
    if not project:
        print(
            "[geeViz MCP] bigquery: ADC has no default project; "
            "bigquery-public-data source will be empty",
            file=sys.stderr, flush=True,
        )
        return None

    try:
        client = bigquery.Client(project=project, credentials=creds)
        datasets = list(client.list_datasets(project="bigquery-public-data"))
    except Exception as _ls_err:
        print(
            f"[geeViz MCP] bigquery: list_datasets failed: {_ls_err!r}",
            file=sys.stderr, flush=True,
        )
        return None

    entries: list[dict] = []

    # Dataset-level rows first — coarse hits (e.g. a search for
    # "overture" returns the dataset directly, useful when the user
    # doesn't know which table they want yet).
    for d in datasets:
        entries.append({
            "id": f"bigquery-public-data.{d.dataset_id}",
            "title": d.friendly_name or d.dataset_id,
            "type": "BIGQUERY_DATASET",
            "provider": "BigQuery Public Data",
            # ``tags`` doubles as free-text scored by search_datasets.
            # Split the snake_case id so token queries like
            # "overture places" match "overture_maps".
            "tags": d.dataset_id.replace("_", " "),
            "kind": "dataset",
        })

    # Table-level rows — parallelised list_tables per dataset. This is
    # the slow phase (~15s wall-clock for ~357 datasets in a 20-thread
    # pool) but it only runs once per 30-day cache cycle, and it's on a
    # background thread inside a prewarm — never on the request path.
    import concurrent.futures
    def _list_one(dataset_ref):
        try:
            return dataset_ref.dataset_id, list(client.list_tables(dataset_ref.reference))
        except Exception:
            return dataset_ref.dataset_id, []

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        for dataset_id, tables in pool.map(_list_one, datasets):
            for t in tables:
                entries.append({
                    "id": f"bigquery-public-data.{dataset_id}.{t.table_id}",
                    "title": f"{dataset_id}.{t.table_id}",
                    "type": "BIGQUERY_TABLE",
                    "provider": "BigQuery Public Data",
                    "tags": f"{dataset_id} {t.table_id}".replace("_", " "),
                    "kind": "table",
                    "parent_dataset": f"bigquery-public-data.{dataset_id}",
                })

    print(
        f"[geeViz MCP] bigquery: cached {len(entries)} entries "
        f"({len(datasets)} datasets)",
        file=sys.stderr, flush=True,
    )
    return entries


def _fetch_catalog_by_name(name: str) -> list[dict] | None:
    """Dispatch fetcher by catalog name. ``bigquery`` uses the BQ API;
    everything else is a straight URL fetch. Returns ``None`` on any
    failure — the caller (stale-while-revalidate wrapper) treats ``None``
    as "keep whatever's on disk"."""
    if name == "bigquery":
        return _fetch_bigquery_catalog()
    url = _CATALOG_URLS.get(name)
    if not url:
        return None
    return _fetch_catalog(url, name)


def _read_cache_meta() -> dict:
    """Read the cache timestamp metadata file."""
    if os.path.isfile(_CACHE_META_FILE):
        try:
            with open(_CACHE_META_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _write_cache_meta(meta: dict) -> None:
    """Write the cache timestamp metadata file."""
    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(_CACHE_META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f)


# Track in-flight background refreshes per catalog so we don't spawn N
# refresh threads when the model fires N tool calls in quick succession.
_catalog_refresh_inflight: dict[str, bool] = {}


def _background_refresh_catalog(name: str) -> None:
    """Re-fetch a catalog from upstream and write it to the cache.

    Designed to be called from a daemon thread. Holds ``_cache_lock`` only
    around the disk writes — the long-running HTTP crawl happens outside
    the lock so concurrent reads of the existing (stale) cache aren't
    blocked. Any failure leaves the existing cache untouched.
    """
    try:
        data = _fetch_catalog_by_name(name)
        if not data:
            return
        cache_file = os.path.join(_CACHE_DIR, _CATALOG_FILES[name])
        with _cache_lock:
            os.makedirs(_CACHE_DIR, exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
            meta = _read_cache_meta()
            meta[f"{name}_ts"] = _time.time()
            _write_cache_meta(meta)
    except Exception:
        pass
    finally:
        _catalog_refresh_inflight.pop(name, None)


def _get_cached_catalog(name: str) -> list[dict] | None:
    """Return parsed JSON list for a catalog using stale-while-revalidate.

    - Cache present and fresh    → return it.
    - Cache present but stale    → return it, kick off a background refresh.
    - Cache missing              → fetch synchronously (first-install only).

    The synchronous-fetch path is the ONLY one that can block, and it only
    fires when the catalog has never been cached on this machine. Day-2+
    callers always get an instant response.
    """
    cache_file = os.path.join(_CACHE_DIR, _CATALOG_FILES[name])
    meta = _read_cache_meta()
    ts_key = f"{name}_ts"
    now = _time.time()

    cached_exists = os.path.isfile(cache_file)
    cache_fresh = cached_exists and (now - meta.get(ts_key, 0)) < _CACHE_TTL

    if cached_exists:
        # Return whatever's on disk immediately. Spawn a background refresh
        # if the cache is stale and no refresh is already running.
        if not cache_fresh and not _catalog_refresh_inflight.get(name):
            _catalog_refresh_inflight[name] = True
            threading.Thread(
                target=_background_refresh_catalog,
                args=(name,),
                daemon=True,
            ).start()
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass  # Corrupt cache — fall through to a sync fetch.

    # No cache on disk — block on the fetch this one time.
    with _cache_lock:
        # Re-check inside the lock in case another thread populated it.
        if os.path.isfile(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        try:
            data = _fetch_catalog_by_name(name)
            if data:
                os.makedirs(_CACHE_DIR, exist_ok=True)
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                meta[ts_key] = now
                _write_cache_meta(meta)
                return data
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Tool 20: search_datasets
# ---------------------------------------------------------------------------

@app.tool(annotations=_READ_ONLY)
def search_datasets(query: str, source: str = "all", max_results: int = 50) -> str:
    """Search the GEE dataset catalog PLUS BigQuery public data by keyword.

    Searches three catalogs, all cached with 30-day stale-while-revalidate:

    - **official** — Earth Engine STAC catalog (~500+ datasets).
    - **community** — awesome-gee-community-datasets (~200+ datasets).
    - **bigquery** — every dataset AND table under ``bigquery-public-data``
      (~357 datasets, ~3000 tables). Table-level indexing means a query
      like "overture places" resolves directly to
      ``bigquery-public-data.overture_maps.place`` — no need to enumerate
      tables yourself afterwards. Results have ``source=bigquery``, plus
      ``kind`` set to ``"dataset"`` or ``"table"``. For a BQ table row,
      construct the FeatureCollection with
      ``ee.FeatureCollection.loadBigQueryTable(id)`` — NOT
      ``ee.FeatureCollection(id)`` — because the id is a BQ path, not an
      EE asset path. ``inspect_asset`` on a BQ id auto-falls back through
      the same helper.

    Uses word-level matching against title, tags, id, and provider fields
    with relevance scoring.

    Args:
        query: Search terms (e.g. "landsat surface reflectance", "DEM",
               "sentinel fire", "overture places"). Case-insensitive.
        source: Which catalog to search: "official", "community",
                "bigquery", or "all" (default — spans all three).
        max_results: Maximum number of results to return (default 50).

    Returns:
        JSON list of matching datasets with id, title, type, provider,
        tags, source, and additional metadata.
    """
    if source not in ("official", "community", "bigquery", "all"):
        return json.dumps({
            "error": (f"Invalid source: {source!r}. Must be 'official', "
                      f"'community', 'bigquery', or 'all'."),
        })

    sources_to_search = (
        ["official", "community", "bigquery"] if source == "all"
        else [source]
    )

    # Load catalogs
    catalogs: dict[str, list[dict]] = {}
    errors: list[str] = []
    for src in sources_to_search:
        data = _get_cached_catalog(src)
        if data is not None:
            catalogs[src] = data
        else:
            errors.append(f"Failed to load {src} catalog (no cache available).")

    if not catalogs:
        return json.dumps({"error": " ".join(errors)})

    # Split query into words for multi-word matching
    query_words = query.lower().split()
    if not query_words:
        return json.dumps({"error": "Empty query."})

    # Field weights
    weights = {"title": 3, "tags": 2, "id": 2, "provider": 1}

    scored: list[tuple[int, dict]] = []

    for src_name, entries in catalogs.items():
        for entry in entries:
            if not isinstance(entry, dict):
                continue  # skip malformed entries
            # Extract searchable fields
            title = (entry.get("title") or "").lower()
            tags = (entry.get("tags") or "").lower()
            eid = (entry.get("id") or "").lower()
            provider = (entry.get("provider") or "").lower()

            fields = {"title": title, "tags": tags, "id": eid, "provider": provider}

            # Score: sum of (weight × number of query words matched in field)
            score = 0
            for field_name, field_val in fields.items():
                for word in query_words:
                    if word in field_val:
                        score += weights[field_name]

            if score == 0:
                continue

            # Build result entry
            result_entry: dict = {
                "id": entry.get("id", ""),
                "title": entry.get("title", ""),
                "type": entry.get("type", ""),
                "provider": entry.get("provider", ""),
                "tags": entry.get("tags", ""),
                "source": src_name,
            }

            if src_name == "official":
                result_entry["date_range"] = entry.get("date_range", "")
                # Build STAC URL
                eid_raw = entry.get("id", "")
                if eid_raw:
                    parts = eid_raw.split("/")
                    stac_dir = parts[0]
                    stac_file = eid_raw.replace("/", "_")
                    result_entry["stac_url"] = (
                        f"https://earthengine-stac.storage.googleapis.com/"
                        f"catalog/{stac_dir}/{stac_file}.json"
                    )
            elif src_name == "bigquery":
                # BQ rows: kind distinguishes "dataset" (browse) from
                # "table" (directly usable via loadBigQueryTable).
                # parent_dataset lets the caller jump one level up when
                # they picked a table but want to see siblings.
                result_entry["kind"] = entry.get("kind", "")
                if entry.get("parent_dataset"):
                    result_entry["parent_dataset"] = entry["parent_dataset"]
                # Nudge the agent to the right construction path — the id
                # here is a BQ path, not an EE asset path.
                if entry.get("kind") == "table":
                    result_entry["construct_via"] = (
                        "ee.FeatureCollection.loadBigQueryTable(id)"
                    )
            else:
                # Community catalog fields
                result_entry["thematic_group"] = entry.get("thematic_group", "")
                result_entry["docs"] = entry.get("docs", "")

            scored.append((score, result_entry))

    # Sort by score descending, then by title alphabetically
    scored.sort(key=lambda x: (-x[0], x[1].get("title", "")))

    results = [entry for _, entry in scored[:max_results]]

    out: dict = {
        "query": query,
        "source": source,
        "count": len(results),
        "total_matches": len(scored),
        "results": results,
    }
    if errors:
        out["warnings"] = errors

    return json.dumps(out)


import base64 as _base64
# ---------------------------------------------------------------------------
# Asset management (consolidated)
# ---------------------------------------------------------------------------

@app.tool(annotations=_DESTRUCTIVE)
def manage_asset(
    action: str,
    asset_id: str = "",
    dest_id: str = "",
    overwrite: bool = False,
    folder_type: str = "Folder",
    all_users_can_read: bool = False,
    readers: str = "",
    writers: str = "",
    session_id: str = None,
) -> str:
    """Manage GEE assets: delete, copy, move, create folders, update permissions.

    Args:
        action: Operation to perform:
            - "delete": Delete a single asset.
            - "copy": Copy asset_id to dest_id.
            - "move": Copy asset_id to dest_id, then delete source.
            - "create": Create a folder or ImageCollection at asset_id.
            - "update_acl": Update permissions on asset_id.
        asset_id: Full asset path. Required for all actions.
                  For "create", this is the folder path to create.
        dest_id: Destination path (required for "copy" and "move").
        overwrite: If True, overwrite existing destination (default False).
        folder_type: For action="create" -- "Folder" (default) or "ImageCollection".
        all_users_can_read: For action="update_acl" -- make publicly readable.
        readers: For action="update_acl" -- comma-separated reader emails.
        writers: For action="update_acl" -- comma-separated writer emails.

    Returns:
        JSON confirmation or error.
    """
    sess = _ensure_initialized(session_id)
    ee = sess.namespace["ee"]
    import geeViz.assetManagerLib as aml
    act = action.lower().strip()

    if not asset_id and act != "create":
        return json.dumps({"error": "asset_id is required."})

    if act == "delete":
        if not aml.ee_asset_exists(asset_id):
            return json.dumps({"error": f"Asset not found: {asset_id}"})
        try:
            ee.data.deleteAsset(asset_id)
        except Exception as exc:
            return json.dumps({"error": f"Delete failed: {exc}"})
        return json.dumps({"success": True, "message": f"Asset {asset_id} deleted."})

    elif act in ("copy", "move"):
        if not dest_id:
            return json.dumps({"error": f"dest_id is required for action='{act}'."})
        if not aml.ee_asset_exists(asset_id):
            return json.dumps({"error": f"Source asset not found: {asset_id}"})
        if aml.ee_asset_exists(dest_id):
            if overwrite:
                try:
                    ee.data.deleteAsset(dest_id)
                except Exception as exc:
                    return json.dumps({"error": f"Failed to delete existing dest: {exc}"})
            else:
                return json.dumps({"error": f"Destination exists: {dest_id}. Set overwrite=True to replace."})
        try:
            ee.data.copyAsset(asset_id, dest_id)
        except Exception as exc:
            return json.dumps({"error": f"Copy failed: {exc}"})
        if act == "move":
            try:
                ee.data.deleteAsset(asset_id)
            except Exception as exc:
                return json.dumps({"error": f"Copied to {dest_id} but failed to delete source: {exc}", "dest_id": dest_id})
        verb = "moved" if act == "move" else "copied"
        return json.dumps({"success": True, "message": f"Asset {verb} from {asset_id} to {dest_id}."})

    elif act == "create":
        folder_path = asset_id or dest_id
        if not folder_path:
            return json.dumps({"error": "asset_id is required for action='create' (the folder path)."})
        if folder_type not in ("Folder", "ImageCollection"):
            return json.dumps({"error": f"Invalid folder_type: {folder_type!r}. Use 'Folder' or 'ImageCollection'."})
        stdout_buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout_buf):
                if folder_type == "ImageCollection":
                    aml.create_image_collection(folder_path)
                else:
                    aml.create_asset(folder_path, recursive=True)
        except Exception as exc:
            return json.dumps({"error": f"Create failed: {exc}", "stdout": stdout_buf.getvalue()})
        return json.dumps({"success": True, "message": f"{folder_type} created at {folder_path}.", "stdout": stdout_buf.getvalue().strip()})

    elif act == "update_acl":
        readers_list = [r.strip() for r in readers.split(",") if r.strip()] if readers else []
        writers_list = [w.strip() for w in writers.split(",") if w.strip()] if writers else []
        stdout_buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout_buf):
                aml.updateACL(asset_id, writers=writers_list, all_users_can_read=all_users_can_read, readers=readers_list)
        except Exception as exc:
            return json.dumps({"error": f"ACL update failed: {exc}", "stdout": stdout_buf.getvalue()})
        return json.dumps({"success": True, "message": f"Permissions updated for {asset_id}.", "stdout": stdout_buf.getvalue().strip()})

    else:
        return json.dumps({"error": f"Unknown action: {action!r}. Use 'delete', 'copy', 'move', 'create', or 'update_acl'."})


def _strip_coordinates(obj):
    """Recursively strip GeoJSON coordinates from nested dicts/lists.

    Replaces ``"coordinates": [...]`` with ``"coordinates": "(stripped)"``
    to keep large coordinate arrays out of the LLM context window.
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "coordinates" and isinstance(v, list):
                out[k] = "(stripped)"
            else:
                out[k] = _strip_coordinates(v)
        return out
    if isinstance(obj, list):
        return [_strip_coordinates(v) for v in obj]
    return obj


def _make_serializable(obj):
    """Recursively convert ee objects to JSON-safe values.

    GeoJSON coordinates are stripped to avoid injecting huge coordinate
    arrays into the LLM context.
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, list):
        return [_make_serializable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    # ee.Geometry -> type only (coordinates are too large for context)
    try:
        import ee as _ee
        if isinstance(obj, _ee.Geometry):
            geojson = obj.getInfo()
            return {"type": geojson.get("type", "Geometry"), "coordinates": "(stripped)"}
    except Exception:
        pass
    # Other ee objects -> repr string
    return repr(obj)


    # get_reference_data removed — use search_codebase(name="vizParamsFalse") instead


# get_streetview and geeviz_search_places tools removed — use the
# googleMapsLib helpers directly from run_code instead (e.g.
# gm.streetview_image, gm.search_places, gm.geocode). googleMapsLib
# is exposed as `gm` in the REPL namespace when the optional
# `google-genai` / requests deps import successfully.



# ---------------------------------------------------------------------------
# Report tools removed — use rl.Report() in run_code instead.
# See agent-instructions.md Key patterns > Reports.

# Report tools removed -- use rl.Report() in run_code instead.


# ---------------------------------------------------------------------------
# Tools 13-15: Forest Service data services (FIA + LCMS)
#
# Three tools, not ten, matching the reduction that took this server from
# 21 tools to 12. The discovery tool is the load-bearing one: FIA's
# parameter space is 752 x 96 x 96 x 1129, which no model can guess its
# way through, and every wrong guess costs a turn plus a slow round trip.
# ---------------------------------------------------------------------------

@app.tool(annotations=_READ_ONLY)
def search_fia(query: str = "", kind: str = "attributes",
               state: str = "", growth_only: bool = False,
               max_results: int = 20) -> str:
    """Search the FIA vocabulary: estimate attributes, groupings, evaluations.

    **Call this before fia_estimate — always.** FIA's ``/fullreport``
    takes an attribute, two groupings and an evaluation drawn from 752 /
    96 / 1,129 options respectively. Guessing a parameter produces an
    opaque server error, not a helpful one.

    Resolved from catalogs bundled with geeViz, so this is instant and
    works with no network — including while FIADB-API is down, which it
    intermittently is.

    Args:
        query: Free text. For ``attributes``, matched against the
            description and estimate group ("carbon", "net growth
            volume", "mortality"). For ``groupings``, against the label
            and database column ("species", "county", "ownership").
        kind: ``"attributes"`` (what to estimate), ``"groupings"`` (how
            to break it out), or ``"evaluations"`` (which inventory).
        state: For ``kind="evaluations"`` — state name prefix.
        growth_only: For ``kind="evaluations"`` — keep only evaluations
            with growth accounting, required by every growth, removals
            and mortality attribute.
        max_results: Cap on rows returned.

    Returns:
        JSON. Attributes carry ``snum``, ``description``, ``units`` and
        ``eval_typ``; groupings carry the exact ``label`` string that
        ``fia_estimate`` needs; evaluations carry ``wc`` and
        ``growth_acct``.
    """
    try:
        from geeViz import fsInsights as _fs
    except Exception as exc:
        return json.dumps({"error": f"fsInsights unavailable: {exc}"})

    kind = (kind or "attributes").lower()
    try:
        if kind.startswith("attr"):
            df = _fs.find_attributes(query, limit=max_results)
        elif kind.startswith("group"):
            df = _fs.find_groupings(query, limit=max_results)
        elif kind.startswith("eval"):
            df = _fs.find_evaluations(state, growth_only=growth_only,
                                      limit=max_results)
        else:
            return json.dumps({
                "error": f"kind must be 'attributes', 'groupings' or "
                         f"'evaluations', got {kind!r}"})
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

    rows = df.to_dict("records") if hasattr(df, "to_dict") else list(df)
    return json.dumps({"kind": kind, "query": query, "count": len(rows),
                       "results": rows}, default=str)


@app.tool(annotations=_READ_ONLY)
def fia_estimate(wc: int, snum: int, rselected: str = "",
                 cselected: str = "", max_results: int = 60) -> str:
    """Run an FIA estimate. Returns values WITH their sampling error.

    Get ``wc``, ``snum`` and the grouping strings from ``search_fia``
    first — the grouping arguments are exact display strings, so a near
    miss fails.

    **You must not report any value from this tool without its standard
    error.** FIA is a probability sample, not a census. Rows carry
    ``se_pct`` and ``plots``, and ``unreliable`` is set when the cell is
    too thin to report (SE > 30% or fewer than 30 plots, with ``n = 0``
    and ``n = 1`` called out separately because a zero-plot cell reports
    a *zero* standard error — reading as maximum precision when it means
    no information).

    Do not report a row where ``unreliable`` is true. Say the estimate
    is too uncertain to give, and name why from ``unreliable_reason``.
    "Alabama has 15,748 acres of white pine" is a confident falsehood
    built from correct data when the truth is 15,748 +/- 54.9% from four
    plots.

    Args:
        wc: Evaluation group from ``search_fia(kind="evaluations")``.
        snum: Attribute number from ``search_fia(kind="attributes")``.
        rselected: Row grouping — exact ``label`` from ``search_fia``.
        cselected: Column grouping. Optional; cross-tabulating thins the
            plot count per cell fast, so expect more flagged rows.
        max_results: Cap on rows returned.

    Returns:
        JSON with ``rows``, plus ``reliable_count`` / ``unreliable_count``
        and the ``forest_definition`` the API actually applied.
    """
    try:
        from geeViz import fsInsights as _fs
    except Exception as exc:
        return json.dumps({"error": f"fsInsights unavailable: {exc}"})

    try:
        df = _fs.estimate(wc=wc, snum=snum, rselected=rselected,
                          cselected=cselected)
    except Exception as exc:
        # Validation errors name the fix; upstream errors say it is not
        # the caller's fault. Both are more useful than a raw traceback.
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

    rows = df.to_dict("records") if hasattr(df, "to_dict") else list(df)
    n_bad = sum(1 for r in rows if r.get("unreliable"))
    fd = rows[0].get("forest_definition") if rows else ""
    return json.dumps({
        "count": len(rows),
        "reliable_count": len(rows) - n_bad,
        "unreliable_count": n_bad,
        "forest_definition": fd,
        "note": ("Every value carries se_pct and plots. Do not report a "
                 "row with unreliable=true; give the reason instead."),
        "rows": rows[:max_results],
        "truncated": len(rows) > max_results,
    }, default=str)


@app.tool(annotations=_READ_ONLY)
def lcms_summary(product: str = "Land_Cover", state: str = "",
                 county: str = "", region: str = "", forest: str = "",
                 district: str = "", year: int = 0,
                 max_results: int = 80) -> str:
    """LCMS land cover / land use / change areas for a named area.

    Wall-to-wall 30 m maps, 1985-2025. Complements FIA: LCMS answers
    *what changed and where*, FIA answers *what is there, plus or minus
    error*.

    Only the 3,643 precomputed areas are available here — 3,137 counties,
    502 ranger districts, and CONUS / All-Lands rollups. Arbitrary
    geometry is not served by this API; that needs Earth Engine, via
    ``run_code`` with ``geeViz.fsInsights.lcms_summary(geometry=...)``.

    Args:
        product: ``"Land_Cover"``, ``"Land_Use"`` or ``"Change"``.
        state: State name. Required alongside ``county``.
        county: County name.
        region, forest, district: Forest Service units. ``district``
            requires ``forest``.
        year: A single year, or 0 for the full 1985-2025 series.
        max_results: Cap on rows returned.

    Returns:
        JSON rows of ``year``, ``class_name``, ``acres``, ``hectares``.

    Note:
        Do not equate these areas with FIA area estimates. One is a
        classified map, the other a probability sample; comparing them
        conflates map accuracy with sampling error. Report them
        separately and say which is which.
    """
    try:
        from geeViz import fsInsights as _fs
    except Exception as exc:
        return json.dumps({"error": f"fsInsights unavailable: {exc}"})

    try:
        df = _fs.lcms_summary(product, state=state, county=county,
                              region=region, forest=forest,
                              district=district,
                              year=(year or None))
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

    rows = df.to_dict("records") if hasattr(df, "to_dict") else list(df)
    return json.dumps({
        "product": product,
        "count": len(rows),
        "rows": rows[:max_results],
        "truncated": len(rows) > max_results,
    }, default=str)


# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point — start the geeViz MCP server on stdio transport.

    Reads config from the environment (EE_PROXY_URL, GEE_PROJECT,
    GEE_SERVICE_ACCOUNT_B64, MCP_SANDBOX, MCP_STREAM_DIR), spawns a
    background prewarm thread that eagerly initializes EE + imports the
    heavy geeViz modules, then blocks in ``app.run()`` speaking JSON-RPC
    over stdin/stdout for the MCP client (Claude Desktop, ADK, etc.).

    Invoked as ``python -m geeViz.mcp`` or by an MCP client configured
    with ``command: python -m geeViz.mcp``.
    """
    global _SANDBOX_ENABLED

    # Prewarm EE + geeViz imports + module tree in a background thread so the
    # first real tool call doesn't pay the full ~30-60s cold-start
    # (ee.Initialize + geeView / getImagesLib / edwLib / outputLib imports).
    # NO PREWARM THREAD. This is deliberate, and it is the third time
    # this decision has been made — the two previous rounds are why the
    # comment above exists.
    #
    #   round 1: a prewarm thread raced the first tool call -> removed
    #   round 2: re-added, "guarded" by _init_lock
    #   round 3: the lock turned the race into a DEADLOCK -> removed
    #
    # Round 3, from an all-thread stack dump of a wedged server:
    #
    #   prewarm thread   holds _init_lock, stuck forever inside
    #                    create_module loading numpy's C extension
    #                    (outputLib.charts -> pandas -> numpy)
    #   tool thread      inspect_asset -> _ensure_initialized, blocked
    #                    acquiring _init_lock
    #
    # Neither ever moves. The tool logs "status": "OK" on entry, never
    # returns, and the agent sits on a spinner with nothing in any log.
    #
    # The lock could not have fixed this, because the lock was never the
    # problem. Two threads doing the SAME heavy initialization is the
    # problem; serializing them only decides which one hangs. The
    # prewarm cannot make the first call faster than doing the work
    # takes — at best it moves the work a few seconds earlier, and at
    # worst it moves it to a thread whose failure nobody can see.
    #
    # So: one code path. ``_ensure_initialized`` runs on the call that
    # needs it, under a lock that is now essentially uncontended. The
    # first tool call pays ~10-20s, which is what the UI already tells
    # the user it will. A failure raises into that call, where the agent
    # can report it, instead of leaving ``_initialized`` False forever.
    print("[geeViz MCP] Ready (EE + geeViz init runs on the first tool "
          "call that needs it)", file=sys.stderr, flush=True)

    # Also prewarm the dataset catalogs (STAC + community + bigquery-public-data)
    # in a separate background thread so the first ``search_datasets`` call
    # doesn't pay a 15-60s catalog-build cost. ``_get_cached_catalog`` is
    # already stale-while-revalidate — this just kicks the first-install path.
    # bigquery is the expensive one (~15s of BQ API calls) and cleanly no-ops
    # to None when BQ dep / auth is unavailable.
    def _prewarm_catalogs():
        # Wait for global init rather than racing it. Unbounded on
        # purpose: if init never happens, there is nothing to prewarm
        # for, and a timeout here would just reintroduce the overlap
        # this wait exists to prevent.
        _init_done.wait()
        for _cat in _CATALOG_NAMES:
            try:
                _get_cached_catalog(_cat)
            except Exception as _cat_err:
                print(f"[geeViz MCP] catalog {_cat!r} prewarm failed: {_cat_err!r}", file=sys.stderr, flush=True)
    threading.Thread(target=_prewarm_catalogs, daemon=True, name="geeviz-mcp-catalog-prewarm").start()

    # stdio is standard for Cursor/IDE integration; use streamable-http for HTTP
    transport = os.environ.get("MCP_TRANSPORT", "stdio")

    if transport == "streamable-http":
        host = os.environ.get("MCP_HOST", "127.0.0.1")
        port = int(os.environ.get("MCP_PORT", "8000"))
        path = os.environ.get("MCP_PATH", "/mcp")
        # Normalize: strip Windows-mangled Git Bash paths and ensure leading /
        if len(path) > 4 and ":" in path[:3]:  # e.g. "C:/Program Files/Git/mcp"
            path = "/" + path.rsplit("/", 1)[-1]
        if not path.startswith("/"):
            path = "/" + path

        # Resolve sandbox default: ON for non-localhost HTTP, OFF for localhost
        if _SANDBOX_ENABLED is None:
            _is_localhost = host in ("127.0.0.1", "localhost", "::1")
            _SANDBOX_ENABLED = not _is_localhost

        # FastMCP.run() doesn't accept host/port kwargs; set them on the
        # settings object directly so uvicorn picks them up.
        app.settings.host = host
        app.settings.port = port
        app.settings.streamable_http_path = path
        # When binding to 0.0.0.0 (cloud deployment), disable DNS rebinding
        # protection so external hostnames (e.g. Cloud Run) are accepted.
        if host == "0.0.0.0":
            app.settings.transport_security.enable_dns_rebinding_protection = False
        print(f"MCP server starting at http://{host}:{port}{path} (sandbox={'ON' if _SANDBOX_ENABLED else 'OFF'})", file=sys.stderr)
        app.run(transport=transport, mount_path=path)
    else:
        # stdio transport — default sandbox OFF (local IDE use)
        if _SANDBOX_ENABLED is None:
            _SANDBOX_ENABLED = False
        print(f"MCP server starting (stdio, sandbox={'ON' if _SANDBOX_ENABLED else 'OFF'})", file=sys.stderr)
        app.run(transport=transport)


if __name__ == "__main__":
    # print(inspect_asset("COPERNICUS/S2_SR_HARMONIZED"))
    main()
# %%
"""
geeViz MCP Server -- execution and introspection tools for Earth Engine via geeViz.

Unlike static doc snippets, this server executes code, inspects live GEE assets,
and dynamically queries API signatures. 21 tools.
"""
from __future__ import annotations

import os
import sys
print('Importing geeViz MCP Server from', __file__)
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
# Audit hook — runtime-level defense that cannot be bypassed from Python.
# Catches os.system, subprocess.Popen, open(), exec(), import of blocked
# modules, etc. even when accessed via module attribute traversal
# (e.g. gv.os.system). Only active when --sandbox is set.
# ---------------------------------------------------------------------------
if _SANDBOX_ENABLED:
    _AUDIT_BLOCKED_IMPORTS = frozenset({
        "os", "subprocess", "shutil", "pathlib", "socket", "http",
        "urllib", "requests", "ctypes", "signal", "threading",
        "multiprocessing", "webbrowser", "tempfile", "code", "codeop",
        "pty", "pipes", "resource", "pickle", "shelve", "xmlrpc",
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
        _trusted_substrings = ("geeViz\\outputLib", "geeViz/outputLib", "kaleido", "plotly")
        try:
            f = _ins.currentframe()
            while f is not None:
                fname = (f.f_code.co_filename or "")
                fname_lower = fname.lower()
                # User code lives in '<mcp>' frames (from exec(compile(..., '<mcp>')))
                if "<mcp>" in fname or "<string>" in fname:
                    return False  # User code is closer than any trusted lib → deny
                if any(s.lower() in fname_lower for s in _trusted_substrings):
                    return True
                f = f.f_back
        except Exception:
            pass
        return False

    def _sandbox_audit_hook(event, args):
        if not _audit_user_code_active:
            return  # Allow server's own operations
        if event == "import":
            mod_name = args[0].split(".")[0] if args[0] else ""
            if mod_name in _AUDIT_BLOCKED_IMPORTS:
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

    sys.addaudithook(_sandbox_audit_hook)


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

Tools (12):
  run_code                 Execute Python/GEE code in a persistent REPL namespace
  inspect_asset            Get metadata for any GEE asset (with optional collection filters)
  search_geeviz            Search geeViz modules, functions, classes, dicts, variables, examples, and REPL modules
  map_control              View, export, preview, list layers, clear, or test the geeView map (action=view|export|preview|layers|clear|test_layers)
  save_session             Save run_code history to a .py file or .ipynb notebook
  env_info                 Get versions, REPL namespace, or project info (action=version|namespace|project)
  export_image             Export ee.Image to asset, Drive, or Cloud Storage (destination=asset|drive|cloud)
  search_datasets          Search the GEE dataset catalog by keyword
  manage_asset             Delete, copy, move, create folder, or update ACL (action=delete|copy|move|create|update_acl)
  get_streetview           Get Google Street View imagery at a location for ground-truthing
  geeviz_search_places     Search for places, landmarks, or businesses using Google Places API

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
        """Return identity decorator -- the function is unchanged."""
        def _identity(fn):
            return fn
        return _identity

    def resource(self, *args, **kwargs):
        def _identity(fn):
            return fn
        return _identity

    def run(self, **kwargs):
        raise RuntimeError("mcp SDK not installed; install with: pip install mcp")


_FastMCP = _load_fastmcp()
FastMCP = _FastMCP if _FastMCP is not None else _StubFastMCP

# Load ToolAnnotations for hinting read-only / destructive / etc.
try:
    from mcp.types import ToolAnnotations
except ImportError:
    # Stub if mcp SDK not installed
    class ToolAnnotations:
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
    print(f"[geeViz MCP] Loaded instructions: {len(_SERVER_INSTRUCTIONS)} chars, {len(_SERVER_INSTRUCTIONS.split())} words")
except Exception:
    _SERVER_INSTRUCTIONS = None
    print("[geeViz MCP] WARNING: No agent instructions loaded")

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
from geeViz.eeAuth.client import CURRENT_TENANT as _CURRENT_TENANT_CV


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
    if isinstance(arguments, dict):
        raw = arguments.pop("_workload_tag", None)
        if raw:
            tag = _sanitize_workload_tag(str(raw))
        # Tenant is propagated separately from workload tag — proxy reads
        # it from the X-AskTerra-Tenant header set by TenantAwareHttp.
        raw_tenant = arguments.pop("_tenant", None)
        if raw_tenant:
            tenant = str(raw_tenant).strip().lower()

    # ContextVar for tenant: TenantAwareHttp reads it on every outbound
    # EE request and stamps the routing header.
    tenant_token = _CURRENT_TENANT_CV.set(tenant) if tenant else None

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


app._tool_manager.call_tool = _tool_manager_call_tool_with_workload_tag

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

_init_lock = threading.Lock()
_initialized = False

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
    (e.g. dict contents via ``search_geeviz(name=...)``).
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
                 "members": members, "doc": first_line}
        tree[modname] = entry
        if short not in tree:
            tree[short] = entry
        fq_map[short] = modname
        fq_map[modname] = modname

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
    print(f"[geeViz MCP] Module tree: {n_mods} modules, {n_examples} examples indexed (zero imports)")


def _get_module(entry):
    """Lazy-import a module from a tree entry. Caches the result."""
    if entry["mod"] is None:
        try:
            entry["mod"] = importlib.import_module(entry["fq"])
        except Exception as exc:
            print(f"[geeViz MCP] Failed to import {entry['fq']}: {exc}")
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
    """Initialize EE credentials once (global, not per-session)."""
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        _init_ee_credentials()
        # Import geeViz to trigger ee.Initialize
        import geeViz.geeView  # noqa: F401
        _initialized = True


def _ensure_initialized(session_id: str | None = None):
    """Lazy-initialize EE (global) and populate session namespace. Thread-safe."""
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
    import geeViz.googleMapsLib as gm
    import geeViz.geePalettes as palettes
    from geeViz.outputLib import charts as cl
    from geeViz.outputLib import thumbs as tl
    from geeViz.outputLib import reports as rl
    import ee
    # pandas and numpy are de-facto standard helpers the agent reaches for
    # constantly; pre-load them so `search_geeviz(name="pd.DataFrame.to_markdown")`
    # and `search_geeviz(module="pd", query="...")` resolve without requiring
    # the agent to `import pandas` inside run_code first. Both are already
    # geeViz dependencies (setup.py) and on the sandbox allowlist.
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

    sess.namespace.update({
        "ee": ee,
        "Map": session_map,
        "gv": gv,
        "gil": gil,
        "sal": sal,
        "edw": edw,
        "gm": gm,
        "palettes": palettes,
        "cl": cl,
        "tl": tl,
        "rl": rl,
        # Both aliases for each lib so search_geeviz finds them either way.
        "pandas": _pd_mod,
        "pd": _pd_mod,
        "numpy": _np_mod,
        "np": _np_mod,
        "save_file": _session_save_file,
        # Clear-error stubs for MCP tool names the agent sometimes calls
        # from inside run_code as if they were Python functions.
        "search_datasets": _mcp_tool_stub("search_datasets"),
        "search_geeviz": _mcp_tool_stub("search_geeviz"),
        "inspect_asset": _mcp_tool_stub("inspect_asset"),
        "geeviz_search_places": _mcp_tool_stub("geeviz_search_places"),
        "search_places": _mcp_tool_stub("search_places"),
        "lookup_weather": _mcp_tool_stub("lookup_weather"),
        "compute_routes": _mcp_tool_stub("compute_routes"),
        "map_control": _mcp_tool_stub("map_control"),
        "env_info": _mcp_tool_stub("env_info"),
        "view_output": _mcp_tool_stub("view_output"),
        "manage_asset": _mcp_tool_stub("manage_asset"),
        "export_image": _mcp_tool_stub("export_image"),
        "save_session": _mcp_tool_stub("save_session"),
        "__builtins__": _make_safe_builtins(),
    })
    sess.initialized = True
    return sess


def _reset_namespace(session_id: str | None = None):
    """Clear and re-populate a session's REPL namespace. Also resets code history."""
    sess = _get_session(session_id)
    sess.namespace.clear()
    sess.code_history.clear()
    sess.current_script_path = None
    sess.initialized = False
    _ensure_initialized(session_id)


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
    "os", "sys", "subprocess", "socket", "shutil", "ctypes", "signal",
    "multiprocessing", "threading", "http", "urllib", "requests",
    "pathlib", "tempfile", "glob", "importlib", "code", "codeop",
    "pickle", "shelve", "marshal", "builtins",
})
# Note: ``io`` is NOT blocked. ``io.BytesIO`` / ``io.StringIO`` are
# essential for the matplotlib → PIL → ``save_file`` flow and are pure
# in-memory objects with no filesystem access. The dangerous parts of
# io (``io.open``, ``io.FileIO``) require a file path that the sandbox
# doesn't grant anyway — and ``open`` is already blocked as a builtin.

# Top-level module prefixes that are allowed in import statements.
# Anything not matching these prefixes AND not in _BLOCKED_MODULES gets a warning
# (not a hard block) to avoid breaking legitimate but uncommon imports.
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
_BLOCKED_BUILTINS = frozenset({
    "__import__", "eval", "exec", "compile", "open",
    "breakpoint", "exit", "quit",
    "globals", "locals", "vars",
    "getattr", "setattr", "delattr",
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

    for node in ast.walk(tree):
        if _SANDBOX_ENABLED:
            # --- Security: check imports (sandbox only) ---
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in _BLOCKED_MODULES:
                        warnings.append(
                            f"BLOCKED: import of '{alias.name}' is not allowed. "
                            f"Only Earth Engine, geeViz, and standard data libraries are permitted."
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top = node.module.split(".")[0]
                    if top in _BLOCKED_MODULES:
                        warnings.append(
                            f"BLOCKED: import from '{node.module}' is not allowed. "
                            f"Only Earth Engine, geeViz, and standard data libraries are permitted."
                        )

            # --- Security: check for dangerous builtin calls (sandbox only) ---
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in ("eval", "exec", "compile", "open", "breakpoint", "__import__"):
                    warnings.append(
                        f"BLOCKED: call to '{node.func.id}()' is not allowed for security."
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
    """StringIO that also appends output to a file for cross-process polling."""
    def __init__(self, stream_file: str):
        super().__init__()
        self._stream_file = stream_file

    def write(self, s):
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
        self._by_thread[threading.get_ident()] = target

    def unregister(self) -> None:
        self._by_thread.pop(threading.get_ident(), None)

    def _resolve(self):
        # Non-registered → stderr, NEVER the captured stdout (which would
        # corrupt JSON-RPC).
        return self._by_thread.get(threading.get_ident(), sys.__stderr__)

    def write(self, s):
        try:
            return self._resolve().write(s)
        except Exception:
            return 0

    def flush(self):
        try:
            return self._resolve().flush()
        except Exception:
            return None

    def isatty(self):
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

    thread = threading.Thread(target=_exec, daemon=True)
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
        return json.dumps({
            "success": False,
            "code": code,
            "stdout": stdout_buf.getvalue(),
            "stderr": stderr_val,
            "result": None,
            "error": timeout_hints,
        })

    if error_holder[0]:
        return json.dumps({
            "success": False,
            "code": code,
            "stdout": stdout_buf.getvalue(),
            "stderr": stderr_val,
            "result": None,
            "error": _translate_ee_error(error_holder[0]),
            "script_path": None,
        })

    # Success -- record in history and save to file
    sess.code_history.append(code)
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

    return json.dumps({
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
    collections.

    Args:
        asset_id: Full Earth Engine asset ID (e.g. "COPERNICUS/S2_SR_HARMONIZED").
        start_date: Optional start date filter for ImageCollections (YYYY-MM-DD).
        end_date: Optional end date filter for ImageCollections (YYYY-MM-DD).
        region_var: Optional name of an ee.Geometry or ee.FeatureCollection
                    variable in the REPL namespace for spatial filtering
                    (ImageCollections only).

    Returns:
        JSON with asset metadata.
    """
    import concurrent.futures
    import datetime as _dt

    _TIMEOUT = 10  # seconds per EE query

    sess = _ensure_initialized(session_id)
    ee = sess.namespace["ee"]

    # --- Step 1: Fast catalog metadata (no compute, never hangs) ---
    try:
        info = ee.data.getInfo(asset_id)
    except Exception as exc:
        return json.dumps({"error": str(exc), "asset_id": asset_id})

    if info is None:
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

    def _getinfo_with_timeout(ee_obj, timeout=_TIMEOUT):
        """Run ee_obj.getInfo() in a daemon thread with timeout. Returns (result, error)."""
        import threading
        _result_box = [None, None]  # [value, error]
        def _run():
            try:
                _result_box[0] = ee_obj.getInfo()
            except Exception as exc:
                _result_box[1] = str(exc)
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=timeout)
        if t.is_alive():
            return None, "timeout"
        return _result_box[0], _result_box[1]

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
            for key, ee_obj in queries.items():
                t = threading.Thread(target=_run_query, args=(key, ee_obj), daemon=True)
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
    - A top-level REPL name that points to a module (``"ee"``, ``"pd"``).
    - A dotted path that traverses attributes from a top-level REPL name
      (``"ee.ImageCollection"``, ``"ee.Reducer"``, ``"pd.DataFrame"``).
      Each step uses ``getattr`` so classes count as valid containers —
      ``dir()`` returns their methods, which is what callers want.

    Returns ``(short_name, container)`` or ``(None, None)``.
    """
    # Exact match in the geeViz module tree
    entry = _MODULE_TREE.get(name)
    if entry:
        mod = _get_module(entry)
        if mod is not None:
            return name, mod

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


@app.tool(annotations=_READ_ONLY)
def search_geeviz(query: str = "", name: str = "", module: str = "", session_id: str = None) -> str:
    """Search geeViz modules, functions, classes, variables, and any REPL module.

    A unified introspection tool — replaces search_functions and
    get_reference_data. Can look up functions, classes, dicts, constants,
    viz params, band mappings, palettes, and more.

    Args:
        query: Search term (case-insensitive). Matches against names and
               first-line docstrings across all geeViz modules.
        name: Exact name to look up. Accepts bare names (``"vizParamsFalse"``,
              ``"simpleMask"``) or dotted paths (``"getImagesLib.vizParamsFalse"``,
              ``"mapper.addLayer"``). Returns full details: signature, docstring
              for functions; keys/values for dicts; value for constants.
        module: Module to search or list. Accepts short names (``"getImagesLib"``,
                ``"charts"``, ``"thumbs"``), full paths (``"geeViz.outputLib.charts"``),
                or legacy aliases (``"chartingLib"``). Also accepts any module in
                the REPL namespace (``"ee"``) for on-the-fly lookups.

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
            # Try direct attribute
            obj = getattr(mod_obj, name, None)
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
        return json.dumps({"module": module, "count": len(results), "results": results})

    # --- Search across all modules (AST-based, no import) ---
    if query:
        q = query.lower()
        results = []
        seen_fqs = set()
        for short, entry in _MODULE_TREE.items():
            fq = entry["fq"]
            if fq in seen_fqs:
                continue
            seen_fqs.add(fq)
            mod_short = fq.rsplit(".", 1)[-1]

            for m in entry.get("members", []):
                if q not in m["name"].lower() and q not in m.get("description", "").lower():
                    # Also check class method names
                    if m["type"] == "class" and m.get("methods"):
                        matching_methods = [meth for meth in m["methods"] if q in meth.lower()]
                        for meth in matching_methods:
                            results.append({"module": mod_short, "name": f"{m['name']}.{meth}", "type": "method",
                                            "description": f"Method of {m['name']}"})
                    continue
                r = {"module": mod_short, "name": m["name"], "type": m["type"]}
                if m.get("description"):
                    r["description"] = m["description"]
                if m.get("signature"):
                    r["signature"] = m["signature"]
                results.append(r)
                # If it's a class, also include matching methods
                if m["type"] == "class" and m.get("methods"):
                    for meth in m["methods"]:
                        if q in meth.lower():
                            results.append({"module": mod_short, "name": f"{m['name']}.{meth}", "type": "method",
                                            "description": f"Method of {m['name']}"})

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


# Examples tool removed -- use search_geeviz(module="examples") to list,
# search_geeviz(name="CCDCViz") to read source.
# ---------------------------------------------------------------------------
# Map control (consolidated)
# ---------------------------------------------------------------------------

@app.tool(annotations=_WRITE)
def map_control(action: str = "view", open_browser: bool = True, filename: str = "map.html", session_id: str = None):
    """Control the geeView interactive map.

    `action="view"` writes the per-session runGeeViz.js to disk and opens
    `geeView/index.html`. In plain Python this is a `file:///` URL; in
    notebooks it uses an in-process threaded HTTP server
    (`http://localhost:<port>/...`) for iframe display. The access token
    is passed via URL query string.

    Args:
        action: Action to perform:
            - "view" (default): Validates all layers first (runs
              test_layers internally). If any layer fails, returns the
              errors without opening the map. If all pass, opens the map
              and returns the URL.
            - "layers": List current layers with visibility and viz params.
            - "layer_names": Quick list of just layer names (lightweight).
            - "clear": Remove all layers and commands.
            - "test_layers": Fast validation — calls getMapId() on all layers
              in parallel. Catches bad bands, invalid viz, computation errors.
              No browser required. Returns pass/fail per layer.
            - "preview": Quick visual check — fetches a small grid of EE map
              tiles for each layer around the current center/zoom and returns
              them as inline images (one per layer). No browser required.
              Use this to visually verify layers have data in the right area.
              Returns a dict of {layer_name: PNG image} plus center and zoom.
              Optional: "preview,zoom=10,grid=2" to override zoom or grid size.
            - "export": Validates all layers first (like "view"), then
              writes a self-contained geeView HTML to
              ``generated_outputs/{filename}``. If any layer fails, returns
              errors without exporting. The HTML uses absolute asset paths
              under ``/geeView/static`` and a ``__GEEVIZ_TOKEN__``
              placeholder for the access token. Suitable for chat UIs that
              serve the HTML themselves and inject a fresh token on load.
              Use this for chat-embedded maps that should survive session
              reloads.
            - "export_layers_json": Bundle every currently-added layer
              into a JSON file under ``generated_outputs/{filename}``.
              Use this when the agent is building a CUSTOM HTML dashboard
              (Leaflet, MapLibre, etc.) and needs the EE layers to be
              re-mintable. The returned ``refresh_url`` is an endpoint
              the agent embeds in its HTML; fetching it returns fresh
              tile URLs for every layer so dashboards survive after EE
              mapids expire. Handles all the same input types as ``addLayer``
              (Image, ImageCollection, Geometry, Feature, FeatureCollection)
              plus tile-URL layers added via ``Map.addTileLayer``.
        open_browser: For action="view", whether to open in browser (default True).
        filename: For action="export", the output filename (saved under
            ``generated_outputs/``). Defaults to ``map.html``.
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
def save_session(filename: str = "", format: str = "py", session_id: str = None) -> str:
    """Save the accumulated run_code history to a .py script or .ipynb notebook.

    Args:
        filename: Optional custom filename (saved in geeViz/mcp/generated_scripts/).
                  If omitted, uses a timestamped default. The correct extension
                  is added automatically based on format.
        format: Output format -- "py" (default) for a standalone Python script,
                "ipynb" for a Jupyter notebook.

    Returns:
        JSON with the file path and number of code blocks/cells saved.
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

    if format == "py":
        if filename:
            if not filename.endswith(".py"):
                filename += ".py"
            os.makedirs(sess.script_dir, exist_ok=True)
            sess.current_script_path = os.path.join(sess.script_dir, filename)

        path = _save_history_to_file(sess)
        return json.dumps({
            "success": True,
            "script_path": path,
            "code_blocks": len(sess.code_history),
            "message": f"Saved {len(sess.code_history)} code block(s) to {path}",
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
}
_CATALOG_URLS = {
    "official": "https://earthengine-stac.storage.googleapis.com/catalog/catalog.json",
    "community": "https://raw.githubusercontent.com/samapriya/awesome-gee-community-datasets/master/community_datasets.json",
}
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
    url = _CATALOG_URLS[name]
    try:
        data = _fetch_catalog(url, name)
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
        url = _CATALOG_URLS[name]
        try:
            data = _fetch_catalog(url, name)
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
    """Search the GEE dataset catalog by keyword.

    Searches both the official Earth Engine catalog (~500+ datasets) and
    the community catalog (~200+ datasets). Uses word-level matching
    against title, tags, id, and provider fields with relevance scoring.

    Args:
        query: Search terms (e.g. "landsat surface reflectance", "DEM",
               "sentinel fire"). Case-insensitive.
        source: Which catalog to search: "official", "community", or
                "all" (default).
        max_results: Maximum number of results to return (default 10).

    Returns:
        JSON list of matching datasets with id, title, type, provider,
        tags, source, and additional metadata.
    """
    if source not in ("official", "community", "all"):
        return json.dumps({
            "error": f"Invalid source: {source!r}. Must be 'official', 'community', or 'all'.",
        })

    sources_to_search = (
        ["official", "community"] if source == "all"
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


    # get_reference_data removed — use search_geeviz(name="vizParamsFalse") instead


# ---------------------------------------------------------------------------
# USFS Enterprise Data Warehouse (EDW) (consolidated)
# ---------------------------------------------------------------------------
@app.tool(annotations=_READ_ONLY_OPEN)
def get_streetview(
    lon: float,
    lat: float,
    headings: str = "0,90,180,270",
    pitch: float = 0,
    fov: float = 90,
    radius: int = 50,
    source: str = "default",
    session_id: str = None,
) -> str:
    """Get Google Street View imagery at a location for ground-truthing.

    Checks if Street View coverage exists, then fetches static images
    at the requested headings (compass directions). Returns images
    inline for visual inspection.

    Useful for ground-truthing remote sensing analysis — see what a
    location actually looks like from the ground.

    Args:
        lon: Longitude in decimal degrees.
        lat: Latitude in decimal degrees.
        headings: Comma-separated compass headings in degrees
                  (0=North, 90=East, 180=South, 270=West).
                  Default "0,90,180,270" (all 4 cardinal directions).
        pitch: Camera pitch (-90 to 90). 0=horizontal, positive=up.
        fov: Field of view in degrees (1-120). Lower = more zoom.
             Default 90.
        radius: Search radius in meters for nearest panorama. Default 50.
        source: "default" (all) or "outdoor" (outdoor only).

    Returns:
        Metadata (date, location, copyright) and Street View images.
        Returns error if no imagery exists at the location.
    """
    sess = _ensure_initialized(session_id)
    import geeViz.googleMapsLib as _gm

    # Check metadata first (free)
    try:
        meta = _gm.streetview_metadata(lon, lat, radius=radius, source=source)
    except Exception as exc:
        return json.dumps({"error": f"Street View metadata request failed: {exc}"})

    if meta.get("status") != "OK":
        return json.dumps({
            "status": meta.get("status", "UNKNOWN"),
            "message": f"No Street View imagery at ({lat}, {lon}) within {radius}m.",
            "tip": "Try increasing the radius or checking a nearby road/trail.",
        })

    # Parse headings
    heading_list = [float(h.strip()) for h in headings.split(",") if h.strip()]

    _direction_labels = {0: "N", 45: "NE", 90: "E", 135: "SE",
                         180: "S", 225: "SW", 270: "W", 315: "NW"}

    # Fetch images and save to files
    os.makedirs(sess.output_dir, exist_ok=True)
    saved_images = []
    md_lines = []
    for h in heading_list:
        try:
            img_bytes = _gm.streetview_image(
                lon, lat, heading=h, pitch=pitch, fov=fov,
                radius=radius, source=source,
            )
            if img_bytes:
                label = _direction_labels.get(int(h) % 360, f"{h}deg")
                fname = f"streetview_{label}.jpg"
                fpath = os.path.join(sess.output_dir, fname).replace("\\", "/")
                with open(fpath, "wb") as f:
                    f.write(img_bytes)
                saved_images.append({"heading": h, "label": label, "path": fpath, "size": len(img_bytes)})
                md_lines.append(f"![Street View {label}]({fpath})")
        except Exception:
            pass

    loc = meta.get("location", {})
    return json.dumps({
        "status": "OK",
        "date": meta.get("date"),
        "location": meta.get("location"),
        "copyright": meta.get("copyright"),
        "images_fetched": len(saved_images),
        "images": saved_images,
        "output_markdown": "\n".join(md_lines) if md_lines else None,
    })


@app.tool(annotations=_READ_ONLY_OPEN)
def geeviz_search_places(
    query: str,
    lon: float = 0,
    lat: float = 0,
    radius: float = 5000,
    max_results: int = 10,
    session_id: str = None,
) -> str:
    """Search for places using the Google Places API.

    Useful for finding landmarks, businesses, or points of interest near
    a study area. Can also geocode addresses.

    Args:
        query: Search text (e.g. "fire station", "visitor center",
               "100S 200 E, SLC, UT").
        lon: Longitude for location bias (0 = no bias).
        lat: Latitude for location bias (0 = no bias).
        radius: Bias radius in meters. Default 5000.
        max_results: Maximum results (1-20). Default 10.

    Returns:
        JSON with matching places (name, address, coordinates, rating, types).
    """
    _ensure_initialized(session_id)
    import geeViz.googleMapsLib as _gm

    kwargs: dict[str, Any] = {
        "query": query,
        "max_results": max_results,
        "radius": radius,
    }
    if lat != 0 and lon != 0:
        kwargs["lat"] = lat
        kwargs["lon"] = lon

    try:
        places = _gm.search_places(**kwargs)
    except Exception as exc:
        return json.dumps({"error": f"Places search failed: {exc}"})

    return json.dumps({
        "count": len(places),
        "places": places,
    })





# ---------------------------------------------------------------------------
# Report tools removed — use rl.Report() in run_code instead.
# See agent-instructions.md Key patterns > Reports.

# Report tools removed -- use rl.Report() in run_code instead.


# Entry point
# ---------------------------------------------------------------------------

def _eager_init():
    """Pre-initialize EE in a background thread so the first tool call is fast."""
    import threading

    def _init():
        try:
            _ensure_initialized()
            print("EE initialized (background warmup)", file=sys.stderr)
        except Exception as exc:
            print(f"Background warmup failed (will retry on first tool call): {exc}", file=sys.stderr)

    t = threading.Thread(target=_init, daemon=True)
    t.start()


def main() -> None:
    global _SANDBOX_ENABLED

    # Pre-warm EE auth so first tool call doesn't stall
    _eager_init()

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
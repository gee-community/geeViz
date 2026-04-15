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

# Parse --sandbox / --no-sandbox early so _help can document them
for _arg in sys.argv[1:]:
    if _arg == "--sandbox":
        _SANDBOX_ENABLED = True
    elif _arg == "--no-sandbox":
        _SANDBOX_ENABLED = False

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

Tools (21):
  run_code                 Execute Python/GEE code in a persistent REPL namespace
  inspect_asset            Get metadata for any GEE asset (with optional collection filters)
  search_functions         Search, list, or get full docs for geeViz functions
  examples                 List or read geeViz example scripts (action=list|get)
  list_assets              List assets in a GEE folder
  track_tasks              Get status of recent EE tasks
  cancel_tasks             Cancel running/ready EE tasks (all or by name)
  map_control              View, list layers, clear, or test the geeView map (action=view|layers|clear|test)
  save_session             Save run_code history to a .py file or .ipynb notebook
  env_info                 Get versions, REPL namespace, or project info (action=version|namespace|project)
  export_image             Export ee.Image to asset, Drive, or Cloud Storage (destination=asset|drive|cloud)
  search_datasets          Search the GEE dataset catalog by keyword
  manage_asset             Delete, copy, move, create folder, or update ACL (action=delete|copy|move|create|update_acl)
  get_reference_data       Look up reference dicts (band mappings, viz params, collection IDs, etc.)
  get_streetview           Get Google Street View imagery at a location for ground-truthing
  search_places            Search for places, landmarks, or businesses using Google Places API
  create_report            Create a new report (title, theme, layout, tone)
  add_report_section       Add a section to the active report (ee.Image/IC + geometry)
  generate_report          Generate the report (HTML, Markdown, or PDF)
  get_report_status        Check active report status and section list
  clear_report             Discard the active report

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

# Module short-name -> fully qualified import path
_MODULE_MAP = {
    "geeView": "geeViz.geeView",
    "getImagesLib": "geeViz.getImagesLib",
    "changeDetectionLib": "geeViz.changeDetectionLib",
    "gee2Pandas": "geeViz.gee2Pandas",
    "assetManagerLib": "geeViz.assetManagerLib",
    "taskManagerLib": "geeViz.taskManagerLib",
    "foliumView": "geeViz.foliumView",
    "phEEnoViz": "geeViz.phEEnoViz",
    "cloudStorageManagerLib": "geeViz.cloudStorageManagerLib",
    "chartingLib": "geeViz.outputLib.charts",
    "thumbLib": "geeViz.outputLib.thumbs",
    "reportLib": "geeViz.outputLib.reports",
    "getSummaryAreasLib": "geeViz.getSummaryAreasLib",
    "edwLib": "geeViz.edwLib",
    "googleMapsLib": "geeViz.googleMapsLib",
    "geePalettes": "geeViz.geePalettes",
}

# Persistent REPL namespace for run_code
_namespace: dict = {}

# Code history for save_session
_code_history: list[str] = []
_script_dir = os.path.join(_THIS_DIR, "generated_scripts")
_output_dir = os.path.join(_THIS_DIR, "generated_outputs")
_current_script_path: str | None = None


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


def _init_ee_credentials():
    """Initialize Earth Engine with service account or default credentials.

    Checks for credentials in this order (env vars can come from .env file):

    1. ``GEE_SERVICE_ACCOUNT_KEY`` env var → path to a JSON key file
    2. ``GEE_SERVICE_ACCOUNT_KEY_JSON`` env var → inline JSON key string
    3. ``GOOGLE_APPLICATION_CREDENTIALS`` env var → standard ADC key file
    4. Fall back to Application Default Credentials (user login, attached
       service account on GCE/Cloud Run, etc.)

    The ``GEE_PROJECT`` env var sets the EE project for billing/quotas.
    If not set, falls back to ``project_id`` from the service account key JSON.
    """
    import ee

    project = os.environ.get("GEE_PROJECT")
    key_path = os.environ.get("GEE_SERVICE_ACCOUNT_KEY")
    key_json = os.environ.get("GEE_SERVICE_ACCOUNT_KEY_JSON")

    if key_path and os.path.isfile(key_path):
        # Service account key file
        import json
        with open(key_path) as f:
            key_data = json.load(f)
        credentials = ee.ServiceAccountCredentials(
            key_data["client_email"], key_file=key_path,
        )
        # Use project from env var, or fall back to project_id in the key file
        _project = project or key_data.get("project_id")
        ee.Initialize(credentials=credentials, project=_project)
        print(f"EE initialized with service account: {key_data['client_email']}"
              f" (project={_project or 'default'})", file=sys.stderr)
    elif key_json:
        # Inline JSON key (for container secrets / env injection)
        import json, tempfile
        key_data = json.loads(key_json)
        # ee.ServiceAccountCredentials needs a file path, so write a temp file
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(key_data, tmp)
        tmp.close()
        credentials = ee.ServiceAccountCredentials(
            key_data["client_email"], key_file=tmp.name,
        )
        # Use project from env var, or fall back to project_id in the key file
        _project = project or key_data.get("project_id")
        ee.Initialize(credentials=credentials, project=_project)
        os.unlink(tmp.name)
        print(f"EE initialized with service account (inline key): "
              f"{key_data['client_email']} (project={_project or 'default'})", file=sys.stderr)
    else:
        # Fall back to geeViz default (ADC, user credentials, etc.)
        # geeViz.geeView handles ee.Initialize() on import
        pass


def _ensure_initialized():
    """Lazy-initialize EE and populate the REPL namespace. Thread-safe."""
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return

        # Initialize EE credentials before importing geeViz
        # (geeViz.geeView calls ee.Initialize on import)
        _init_ee_credentials()

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

        _namespace.update({
            "ee": ee,
            "Map": gv.Map,
            "gv": gv,
            "gil": gil,
            "sal": sal,
            "edw": edw,
            "gm": gm,
            "palettes": palettes,
            "cl": cl,
            "tl": tl,
            "rl": rl,
            "save_file": _safe_write_file,
            "__builtins__": _make_safe_builtins(),
        })
        _initialized = True


def _reset_namespace():
    """Clear and re-populate the REPL namespace. Also resets code history."""
    global _initialized, _current_script_path
    _namespace.clear()
    _code_history.clear()
    _current_script_path = None
    _initialized = False
    _ensure_initialized()


def _save_history_to_file() -> str:
    """Write accumulated code history to a timestamped .py file. Returns the path."""
    global _current_script_path
    import datetime
    os.makedirs(_script_dir, exist_ok=True)
    if _current_script_path is None:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        _current_script_path = os.path.join(_script_dir, f"session_{ts}.py")
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
        for i, block in enumerate(_code_history)
    )
    with open(_current_script_path, "w", encoding="utf-8") as f:
        f.write(header + body + "\n")
    return _current_script_path


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
    "pathlib", "tempfile", "glob", "io", "importlib", "code", "codeop",
    "pickle", "shelve", "marshal", "builtins",
})

# Top-level module prefixes that are allowed in import statements.
# Anything not matching these prefixes AND not in _BLOCKED_MODULES gets a warning
# (not a hard block) to avoid breaking legitimate but uncommon imports.
_ALLOWED_MODULE_PREFIXES = (
    "ee", "geeViz", "json", "datetime", "math", "collections",
    "numpy", "np", "pandas", "pd", "plotly", "copy", "re",
    "functools", "itertools", "operator", "statistics",
    "pprint", "textwrap", "string", "decimal", "fractions",
)

# Builtins that are blocked from the execution namespace.
_BLOCKED_BUILTINS = frozenset({
    "__import__", "eval", "exec", "compile", "open",
    "breakpoint", "exit", "quit",
    "globals", "locals", "vars",
    "getattr", "setattr", "delattr",
})


def _safe_write_file(filename: str, content: str, mode: str = "w") -> str:
    """Write content to a file in the safe output directory.

    Only allows writing to geeViz/mcp/generated_outputs/ to prevent
    arbitrary file system access. Returns the full path of the written file.

    Args:
        filename: Just the filename (no directory). e.g. "chart.html"
        content: String content to write.
        mode: Write mode, "w" (text) or "wb" (binary). Default "w".

    Returns:
        Full path to the written file.
    """
    # Strip any path components — only allow bare filenames
    safe_name = os.path.basename(filename)
    if not safe_name:
        raise ValueError("filename must not be empty")
    os.makedirs(_output_dir, exist_ok=True)
    full_path = os.path.join(_output_dir, safe_name)
    with open(full_path, mode) as f:
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

        # --- EE performance: detect .getInfo() calls (always active) ---
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "getInfo"):
            continue

        # Check if .getInfo() is inside a for/while loop
        for parent in ast.walk(tree):
            if isinstance(parent, (ast.For, ast.While)):
                for child in ast.walk(parent):
                    if child is node:
                        warnings.append(
                            "Warning: .getInfo() inside a loop can be very slow. "
                            "Consider gathering results server-side with ee.List or ee.Dictionary."
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

    _EXT_MAP = {"thumb_bytes": ".png", "gif_bytes": ".gif", "image": ".png"}

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


@app.tool(annotations=_WRITE)
async def run_code(code: str, timeout: int = 120, reset: bool = False, ctx: Context = None) -> str:
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
        ctx: MCP Context (auto-injected by FastMCP). Used for progress reporting.

    Returns:
        JSON with keys: success (bool), stdout, stderr, result, error.
    """
    if reset:
        _reset_namespace()
    else:
        _ensure_initialized()

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

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    result_holder: list = [None]
    error_holder: list = [None]

    # Snapshot output files before execution to detect new ones
    os.makedirs(_output_dir, exist_ok=True)
    _files_before = set(os.listdir(_output_dir))

    # Save original streams so we can restore them after timeout (redirect_stdout
    # modifies sys.stdout globally, which would capture the main thread's output
    # if the exec thread is still running when we time out).
    _orig_stdout = sys.stdout
    _orig_stderr = sys.stderr

    def _exec():
        try:
            with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                # Try to detect if the last statement is an expression
                tree = ast.parse(code)
                if tree.body and isinstance(tree.body[-1], ast.Expr):
                    # Execute everything except the last statement
                    if len(tree.body) > 1:
                        mod = ast.Module(body=tree.body[:-1], type_ignores=[])
                        exec(compile(mod, "<mcp>", "exec"), _namespace)
                    # Eval the last expression to capture its value
                    expr = ast.Expression(body=tree.body[-1].value)
                    result_holder[0] = eval(compile(expr, "<mcp>", "eval"), _namespace)
                else:
                    exec(compile(code, "<mcp>", "exec"), _namespace)
        except Exception:
            error_holder[0] = traceback.format_exc()

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

    # Restore original streams in case the thread's redirect is still active
    # (happens on timeout when the thread's `with` block hasn't exited yet).
    sys.stdout = _orig_stdout
    sys.stderr = _orig_stderr

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
            "error": error_holder[0],
            "script_path": None,
        })

    # Success -- record in history and save to file
    _code_history.append(code)
    script_path = _save_history_to_file()

    result_val = result_holder[0]

    # --- Auto-save any binary/HTML outputs and build a clean result ---
    # This is the ONLY place that handles bytes/large data.
    # Everything that comes out of here is guaranteed small and JSON-safe.
    result_str = _save_and_clean_result(result_val)

    # Detect new output files (from save_file, auto-save, or direct writes)
    _files_after = set(os.listdir(_output_dir))
    _new_files = sorted(_files_after - _files_before)
    _IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
    output_markdown = None
    if _new_files:
        md_lines = []
        for fname in _new_files:
            fpath = os.path.join(_output_dir, fname).replace("\\", "/")
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

    _ensure_initialized()
    ee = _namespace["ee"]

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
                region = _namespace.get(region_var)
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
        result["viz_recommendation"] = (
            "THEMATIC DATA DETECTED — bands {} have class properties. "
            "You MUST use {{'autoViz': True}} as the viz params when adding "
            "this layer to the map. Do NOT use min/max. Example: "
            "Map.addLayer(data, {{'autoViz': True}}, 'Layer Name')"
        ).format(thematic_bands)

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
# ---------------------------------------------------------------------------
# Internal API reference lookup (used by search_functions)
# ---------------------------------------------------------------------------
import inspect as _inspect


def _get_api_reference(module: str, function_name: str = "") -> str:
    """Look up the signature and docstring of a geeViz function or module.

    Internal helper called by ``search_functions(function_name=...)``.

    Args:
        module: Short module name. One of: geeView, getImagesLib,
                changeDetectionLib, gee2Pandas, assetManagerLib,
                taskManagerLib, foliumView, phEEnoViz, cloudStorageManagerLib,
                chartingLib, thumbLib, reportLib, getSummaryAreasLib, edwLib.
        function_name: Optional function or class name within the module.
                       If omitted, returns the module-level docstring.

    Returns:
        Signature and docstring text, or error message.
    """
    _ensure_initialized()

    fq = _MODULE_MAP.get(module)
    if not fq:
        return json.dumps({
            "error": f"Unknown module: {module!r}. Valid modules: {', '.join(sorted(_MODULE_MAP))}",
        })

    try:
        mod = importlib.import_module(fq)
    except Exception as exc:
        return json.dumps({"error": f"Failed to import {fq}: {exc}"})

    if not function_name:
        return json.dumps({
            "module": module,
            "docstring": _inspect.getdoc(mod) or "(no module docstring)",
        })

    # Resolve dotted names (e.g. "mapper.addLayer") by walking the attribute chain
    obj = None
    parts = function_name.split(".")
    try:
        obj = mod
        for part in parts:
            obj = getattr(obj, part)
    except AttributeError:
        obj = None

    # Fallback: for geeView, try the mapper class if a bare name isn't found at module level
    if obj is None and module == "geeView" and len(parts) == 1:
        mapper_cls = getattr(mod, "mapper", None)
        if mapper_cls:
            obj = getattr(mapper_cls, function_name, None)
            if obj is not None:
                # Rewrite for clearer output
                function_name = f"mapper.{function_name}"

    if obj is None:
        # Provide a hint if it might be a mapper method
        hint = ""
        if module == "geeView":
            mapper_cls = getattr(mod, "mapper", None)
            if mapper_cls:
                methods = [m for m in dir(mapper_cls) if not m.startswith("_")
                           and function_name.lower() in m.lower()]
                if methods:
                    hint = f" Did you mean: {', '.join('mapper.' + m for m in methods)}?"
        return json.dumps({"error": f"{function_name!r} not found in {module}.{hint}"})

    # Handle classes: show class docstring + public method list
    if _inspect.isclass(obj):
        methods = [
            m for m in dir(obj)
            if not m.startswith("_") and callable(getattr(obj, m, None))
        ]
        return json.dumps({
            "module": module,
            "name": function_name,
            "type": "class",
            "docstring": _inspect.getdoc(obj) or "(no docstring)",
            "public_methods": methods,
        })

    # Function or callable
    try:
        sig = str(_inspect.signature(obj))
    except (ValueError, TypeError):
        sig = "(signature unavailable)"

    return json.dumps({
        "module": module,
        "name": function_name,
        "signature": f"{function_name}{sig}",
        "docstring": _inspect.getdoc(obj) or "(no docstring)",
    })


# ---------------------------------------------------------------------------
# Tool 4: search_functions
# ---------------------------------------------------------------------------

@app.tool(annotations=_READ_ONLY)
def search_functions(query: str = "", module: str = "", function_name: str = "") -> str:
    """Search for functions, list module contents, or get full API docs for a specific function.

    Combines search, listing, and detailed lookup into one tool:
    - query only → search all modules for matching functions (by name or docstring)
    - module only → list all public functions in that module
    - both query + module → search within a specific module
    - function_name + module → return full signature and docstring for a specific function
    - function_name only → search all modules for that exact function name
    - neither → return list of available modules with usage hint

    Args:
        query: Search term (case-insensitive). Matched against function names
               and the first line of their docstrings.
        module: Short module name to restrict search to a single module.
                Valid names: geeView, getImagesLib, changeDetectionLib,
                gee2Pandas, assetManagerLib, taskManagerLib, foliumView,
                phEEnoViz, cloudStorageManagerLib, chartingLib,
                getSummaryAreasLib, thumbLib, reportLib, edwLib.
        function_name: Exact function name to get full documentation for.
                       Returns the complete signature and docstring.
                       If module is omitted, searches all modules for the name.

    Returns:
        JSON with matching functions. Each entry has module, name, type,
        signature, and description. When function_name is provided, also
        includes the full docstring.
    """
    _ensure_initialized()

    # --- Detailed lookup mode: function_name provided ---
    if function_name:
        # If module specified, look up directly
        if module:
            return _get_api_reference(module, function_name)
        # No module specified — search all modules for the exact name
        for short_name, fq_name in _MODULE_MAP.items():
            try:
                mod = importlib.import_module(fq_name)
            except Exception:
                continue
            # Try direct attribute
            obj = getattr(mod, function_name, None)
            if obj is not None and (callable(obj) or _inspect.isclass(obj)):
                return _get_api_reference(short_name, function_name)
            # Try mapper class for geeView
            if short_name == "geeView":
                mapper_cls = getattr(mod, "mapper", None)
                if mapper_cls:
                    obj = getattr(mapper_cls, function_name, None)
                    if obj is not None and callable(obj):
                        return _get_api_reference(short_name, f"mapper.{function_name}")
        return json.dumps({"error": f"Function {function_name!r} not found in any module."})

    # Neither query nor module -- list available modules
    if not query and not module:
        return json.dumps({
            "modules": sorted(_MODULE_MAP.keys()),
            "usage": (
                'Pass module="<name>" to list all functions in a module, '
                'query="<term>" to search across all modules, '
                "or both to search within a specific module."
            ),
        })

    # Determine which modules to search
    if module:
        fq = _MODULE_MAP.get(module)
        if not fq:
            return json.dumps({
                "error": f"Unknown module: {module!r}. Valid modules: {', '.join(sorted(_MODULE_MAP))}",
            })
        modules_to_search = {module: fq}
    else:
        modules_to_search = _MODULE_MAP

    q = query.lower() if query else ""
    results = []

    for short_name, fq_name in modules_to_search.items():
        try:
            mod = importlib.import_module(fq_name)
        except Exception:
            continue

        for name in sorted(dir(mod)):
            if name.startswith("_"):
                continue
            obj = getattr(mod, name, None)
            if obj is None or not (callable(obj) or _inspect.isclass(obj)):
                continue

            doc = _inspect.getdoc(obj) or ""
            first_line = doc.split("\n")[0].strip() if doc else "(no description)"

            if q and q not in name.lower() and q not in first_line.lower():
                continue

            kind = "class" if _inspect.isclass(obj) else "function"
            # Include signature so agents can use functions without a
            # separate get_api_reference call
            sig = ""
            if not _inspect.isclass(obj):
                try:
                    sig = f"{name}{_inspect.signature(obj)}"
                except (ValueError, TypeError):
                    sig = ""
            results.append({
                "module": short_name,
                "name": name,
                "type": kind,
                "signature": sig,
                "description": first_line,
            })

        # For geeView, also include mapper class methods
        if short_name == "geeView":
            mapper_cls = getattr(mod, "mapper", None)
            if mapper_cls and _inspect.isclass(mapper_cls):
                for mname in sorted(dir(mapper_cls)):
                    if mname.startswith("_"):
                        continue
                    mobj = getattr(mapper_cls, mname, None)
                    if not callable(mobj):
                        continue

                    doc = _inspect.getdoc(mobj) or ""
                    first_line = doc.split("\n")[0].strip() if doc else "(no description)"

                    if q and q not in mname.lower() and q not in first_line.lower():
                        continue

                    sig = ""
                    try:
                        sig = f"mapper.{mname}{_inspect.signature(mobj)}"
                    except (ValueError, TypeError):
                        sig = ""
                    results.append({
                        "module": short_name,
                        "name": f"mapper.{mname}",
                        "type": "method",
                        "signature": sig,
                        "description": first_line,
                    })

    return json.dumps({"query": query, "module": module, "count": len(results), "results": results})


# ---------------------------------------------------------------------------
# Examples (consolidated)
# ---------------------------------------------------------------------------

@app.tool(annotations=_READ_ONLY)
def examples(action: str = "list", name: str = "", filter: str = "") -> str:
    """List or read geeViz example scripts.

    Args:
        action: "list" (default) to list available examples, or
                "get" to read the source of a specific example.
        name: For action="get", the example name (with or without extension).
        filter: For action="list", optional substring filter (case-insensitive).

    Returns:
        For "list": JSON list of {name, description} objects.
        For "get": The example source code.
    """
    act = action.lower().strip()

    if act == "get":
        if not name:
            return json.dumps({"error": "Provide 'name' for action='get'."})
        base = name
        for ext in (".py", ".ipynb"):
            if base.endswith(ext):
                base = base[:-len(ext)]
                break
        py_path = os.path.join(_EXAMPLES_DIR, base + ".py")
        nb_path = os.path.join(_EXAMPLES_DIR, base + ".ipynb")
        if os.path.isfile(py_path):
            with open(py_path, "r", encoding="utf-8") as f:
                return json.dumps({"example": base + ".py", "type": "python", "source": f.read()})
        if os.path.isfile(nb_path):
            try:
                with open(nb_path, "r", encoding="utf-8") as f:
                    nb = json.load(f)
                cells = [{"cell_type": c.get("cell_type", ""), "source": "".join(c.get("source", []))}
                         for c in nb.get("cells", []) if "".join(c.get("source", [])).strip()]
                return json.dumps({"example": base + ".ipynb", "type": "notebook", "cells": cells})
            except Exception as exc:
                return json.dumps({"error": f"Failed to read notebook: {exc}"})
        available = _list_example_files()
        return json.dumps({"error": f"Example not found: {name!r}", "available_examples": available})

    # action == "list"
    files = _list_example_files()
    results = []
    for fname in files:
        if filter and filter.lower() not in fname.lower():
            continue
        fpath = os.path.join(_EXAMPLES_DIR, fname)
        desc = ""
        if fname.endswith(".py"):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    lines = [f.readline() for _ in range(20)]
                text = "".join(lines)
                try:
                    tree = ast.parse(text)
                    if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant):
                        desc = str(tree.body[0].value.value).split("\n")[0].strip()
                except SyntaxError:
                    pass
                if not desc:
                    for line in lines:
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
                        source = "".join(cell.get("source", [])).strip()
                        if source:
                            desc = source.split("\n")[0].lstrip("#").strip()
                            break
            except Exception:
                pass
        results.append({"name": fname, "description": desc or "(no description)"})
    return json.dumps({"count": len(results), "examples": results})


def _list_example_files() -> list[str]:
    """Return sorted list of example filenames."""
    if not os.path.isdir(_EXAMPLES_DIR):
        return []
    return sorted(f for f in os.listdir(_EXAMPLES_DIR)
                  if (f.endswith(".py") or f.endswith(".ipynb")) and f != "__init__.py")


# ---------------------------------------------------------------------------
# Tool 7: list_assets
# ---------------------------------------------------------------------------

@app.tool(annotations=_READ_ONLY_OPEN)
def list_assets(folder: str) -> str:
    """List assets in a GEE folder or collection.

    Args:
        folder: Full asset path (e.g. "projects/my-project/assets/my-folder").

    Returns:
        JSON list of {id, type, sizeBytes} for each asset (max 200).
    """
    _ensure_initialized()
    ee = _namespace["ee"]

    try:
        result = ee.data.listAssets({"parent": folder})
    except Exception as exc:
        return json.dumps({"error": str(exc), "folder": folder})

    assets = result.get("assets", [])
    entries = []
    for a in assets[:2000]:
        entries.append({
            "id": a.get("id") or a.get("name", ""),
            "type": a.get("type", "UNKNOWN"),
            "sizeBytes": a.get("sizeBytes"),
        })

    out: dict = {"folder": folder, "count": len(entries), "assets": entries}
    if len(assets) > 2000:
        out["note"] = f"Showing 2000 of {len(assets)} assets. Narrow your query for the rest."

    return json.dumps(out)


# ---------------------------------------------------------------------------
# Tool 8: track_tasks
# ---------------------------------------------------------------------------

@app.tool(annotations=_READ_ONLY_OPEN)
def track_tasks(name_filter: str = "") -> str:
    """Get status of recent Earth Engine tasks.

    Args:
        name_filter: Optional case-insensitive filter on task description.

    Returns:
        JSON list of recent tasks with description, state, type, start time,
        runtime, and error message (max 50).
    """
    _ensure_initialized()
    ee = _namespace["ee"]

    try:
        tasks = ee.data.getTaskList()
    except Exception as exc:
        return json.dumps({"error": str(exc)})

    entries = []
    for t in tasks[:500]:
        desc = t.get("description", "")
        if name_filter and name_filter.lower() not in desc.lower():
            continue
        entries.append({
            "description": desc,
            "state": t.get("state", "UNKNOWN"),
            "task_type": t.get("task_type", ""),
            "start_timestamp_ms": t.get("start_timestamp_ms"),
            "update_timestamp_ms": t.get("update_timestamp_ms"),
            "error_message": t.get("error_message", ""),
        })

    return json.dumps({"count": len(entries), "tasks": entries})


# ---------------------------------------------------------------------------
# Map control (consolidated)
# ---------------------------------------------------------------------------

@app.tool(annotations=_WRITE)
def map_control(action: str = "view", open_browser: bool = True):
    """Control the geeView interactive map.

    `action="view"` writes the per-session runGeeViz.js to disk and opens
    `geeView/index.html`. In plain Python this is a `file:///` URL; in
    notebooks it uses an in-process threaded HTTP server
    (`http://localhost:<port>/...`) for iframe display. The access token
    is passed via URL query string.

    Args:
        action: Action to perform:
            - "view" (default): Open the map and return the URL.
            - "layers": List current layers with visibility and viz params.
            - "layer_names": Quick list of just layer names (lightweight).
            - "clear": Remove all layers and commands.
            - "test": Capture a PNG of the viewer via headless Chrome
              using the DevTools Protocol (CDP). Returns output_markdown with
              an image reference, plus tile_errors (HTTP 4xx/5xx on EE tile
              URLs) and console_messages (JS errors/warnings). Requires
              websocket-client (pip install websocket-client). Falls back to
              simple screenshot if not installed (no console capture).
        open_browser: For action="view", whether to open in browser (default True).

    Returns:
        JSON with action-specific results.
    """
    _ensure_initialized()
    Map = _namespace["Map"]
    act = action.lower().strip()

    if act == "view":
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

    elif act == "test":
        # Re-trigger view (open_browser=False) to get/refresh the URL
        view_result = json.loads(map_control(action="view", open_browser=False))
        url = view_result.get("url")
        if not url:
            return json.dumps({"error": "No viewer URL available — add layers first."})

        from geeViz.outputLib import charts as _cl

        # CDP-based screenshot — also captures JS console errors + network failures
        png_bytes, console_msgs = _cl.screenshot_url(url, width=1280, height=900, wait_seconds=12)

        if not png_bytes:
            return json.dumps({
                "error": "Test failed.",
                "console": console_msgs,
            })

        # Separate tile errors from other console output for easy scanning
        tile_errors = [m for m in console_msgs if "earthengine" in m or "googleapis" in m
                       or "HTTP 4" in m or "HTTP 5" in m or "LOAD FAIL" in m]
        other_msgs = [m for m in console_msgs if m not in tile_errors]

        # Always save the PNG to disk for human inspection
        import datetime as _dt
        os.makedirs(_output_dir, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(_output_dir, f"map_screenshot_{ts}.png")
        with open(screenshot_path, "wb") as f:
            f.write(png_bytes)

        status = f"{len(tile_errors)} tile error(s) detected — see tile_errors." if tile_errors \
            else "No tile/JS errors detected."
        result = {
            "message": f"Map view test complete. {status}",
            "tile_errors": tile_errors,
            "console_messages": other_msgs,
            "screenshot_path": screenshot_path,
        }

        # Return text-only. Model uses tile_errors + console_messages to detect/fix bugs.
        # No output_markdown → after_tool_callback never promotes this to a user artifact.
        return json.dumps(result)

    else:
        return json.dumps({"error": f"Unknown action: {action!r}. Use 'view', 'layers', 'layer_names', 'clear', or 'test'."})


# ---------------------------------------------------------------------------
# Tool 13: save_session
# ---------------------------------------------------------------------------

@app.tool(annotations=_WRITE)
def save_session(filename: str = "", format: str = "py") -> str:
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
    if format not in ("py", "ipynb"):
        return json.dumps({
            "error": f"Invalid format: {format!r}. Must be 'py' or 'ipynb'.",
        })

    if not _code_history:
        return json.dumps({
            "error": "No code has been executed yet. Use run_code first.",
        })

    if format == "py":
        global _current_script_path
        if filename:
            if not filename.endswith(".py"):
                filename += ".py"
            os.makedirs(_script_dir, exist_ok=True)
            _current_script_path = os.path.join(_script_dir, filename)

        path = _save_history_to_file()
        return json.dumps({
            "success": True,
            "script_path": path,
            "code_blocks": len(_code_history),
            "message": f"Saved {len(_code_history)} code block(s) to {path}",
        })

    # format == "ipynb"
    import datetime
    os.makedirs(_script_dir, exist_ok=True)

    if filename:
        if not filename.endswith(".ipynb"):
            filename += ".ipynb"
        nb_path = os.path.join(_script_dir, filename)
    else:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        nb_path = os.path.join(_script_dir, f"session_{ts}.ipynb")

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
    for i, block in enumerate(_code_history):
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
        "code_cells": len(_code_history),
        "message": f"Saved {len(_code_history)} code cell(s) to {nb_path}",
    })


# ---------------------------------------------------------------------------
# Environment info (consolidated)
# ---------------------------------------------------------------------------

_NAMESPACE_BUILTINS = {"ee", "Map", "gv", "gil"}


@app.tool(annotations=_READ_ONLY_OPEN)
def env_info(action: str = "version") -> str:
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
        _ensure_initialized()
        ee = _namespace["ee"]
        entries = []
        for name, obj in sorted(_namespace.items()):
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
        _ensure_initialized()
        ee = _namespace["ee"]
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
        _reset_namespace()
        return json.dumps({
            "action": "reload",
            "reloaded_modules": reloaded,
            "count": len(reloaded),
            "message": "All geeViz modules reloaded. REPL namespace reset.",
        })

    else:
        return json.dumps({"error": f"Unknown action: {action!r}. Use 'version', 'namespace', 'project', or 'reload'."})


# ---------------------------------------------------------------------------
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
    _ensure_initialized()
    ee = _namespace["ee"]
    gil = _namespace["gil"]
    dest = destination.lower().strip()

    if dest not in ("asset", "drive", "cloud"):
        return json.dumps({"error": f"Unknown destination: {destination!r}. Use 'asset', 'drive', or 'cloud'."})

    # Look up image
    image = _namespace.get(image_var)
    if image is None:
        return json.dumps({"error": f"Variable {image_var!r} not found in namespace."})
    if not isinstance(image, ee.Image):
        return json.dumps({"error": f"Variable {image_var!r} is {type(image).__name__}, not ee.Image."})

    # Look up region
    region = None
    if region_var:
        region = _namespace.get(region_var)
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
            if dest == "asset":
                if not asset_id:
                    return json.dumps({"error": "asset_id is required for destination='asset'."})
                asset_name = asset_id.split("/")[-1]
                gil.exportToAssetWrapper(
                    image, asset_name, asset_id,
                    pyramidingPolicyObject={"default": pyramiding_policy},
                    roi=region, scale=scale, crs=crs, overwrite=overwrite,
                )
            elif dest == "drive":
                if not output_name or not drive_folder:
                    return json.dumps({"error": "output_name and drive_folder are required for destination='drive'."})
                gil.exportToDriveWrapper(
                    image, output_name, drive_folder,
                    region, scale, crs, None, output_no_data,
                )
            elif dest == "cloud":
                if not output_name or not bucket:
                    return json.dumps({"error": "output_name and bucket are required for destination='cloud'."})
                gil.exportToCloudStorageWrapper(
                    image, output_name, bucket,
                    region, scale, crs, None, output_no_data,
                    file_format, {"cloudOptimized": True}, overwrite,
                )
    except Exception as exc:
        return json.dumps({"error": f"Export failed: {exc}", "stdout": stdout_buf.getvalue()})

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
_CACHE_TTL = 7 * 24 * 3600  # 1 week
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


def _get_cached_catalog(name: str) -> list[dict] | None:
    """Return parsed JSON list for a catalog, fetching/caching as needed.

    Args:
        name: "official" or "community"

    Returns:
        List of dataset dicts, or None if unavailable.
    """
    with _cache_lock:
        cache_file = os.path.join(_CACHE_DIR, _CATALOG_FILES[name])
        meta = _read_cache_meta()
        ts_key = f"{name}_ts"
        now = _time.time()

        # Check if cache is fresh
        cached_exists = os.path.isfile(cache_file)
        cache_fresh = cached_exists and (now - meta.get(ts_key, 0)) < _CACHE_TTL

        if cache_fresh:
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass  # Fall through to fetch

        # Fetch from remote
        url = _CATALOG_URLS[name]
        try:
            data = _fetch_catalog(url, name)
            if data:
                # Cache the normalized result
                os.makedirs(_CACHE_DIR, exist_ok=True)
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                meta[ts_key] = now
                _write_cache_meta(meta)
                return data
        except Exception:
            # Fetch failed -- use stale cache if available
            if cached_exists:
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
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
@app.tool(annotations=_DESTRUCTIVE)
def cancel_tasks(name_filter: str = "") -> str:
    """Cancel running and ready Earth Engine tasks.

    If name_filter is provided, cancels only tasks whose description
    contains the filter string. Otherwise cancels ALL ready/running tasks.

    Uses geeViz's taskManagerLib for the actual cancellation.

    Args:
        name_filter: Optional substring filter. Only tasks whose description
                     contains this string will be cancelled. If empty, all
                     ready/running tasks are cancelled.

    Returns:
        JSON with task counts and cancellation status.
    """
    _ensure_initialized()
    import geeViz.taskManagerLib as tml

    # Get current task state before cancellation
    task_state = tml.getTasks()
    ready_count = len(task_state.get("ready", []))
    running_count = len(task_state.get("running", []))

    stdout_buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_buf):
            if name_filter:
                tml.cancelByName(name_filter)
            else:
                tml.batchCancel()
    except Exception as exc:
        return json.dumps({
            "error": f"Cancel failed: {exc}",
            "stdout": stdout_buf.getvalue(),
        })

    return json.dumps({
        "success": True,
        "name_filter": name_filter or "(all)",
        "ready_before": ready_count,
        "running_before": running_count,
        "stdout": stdout_buf.getvalue().strip(),
        "message": "Task cancellation completed.",
    })


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
    _ensure_initialized()
    ee = _namespace["ee"]
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


_REFERENCE_DATA = {
    "sensorBandNameDict": {"attr": "sensorBandNameDict", "description": "Standard band names by sensor/TOA-SR"},
    "sensorBandDict": {"attr": "sensorBandDict", "description": "Raw band IDs by sensor/TOA-SR"},
    "vizParamsFalse": {"attr": "vizParamsFalse", "description": "False color viz params (swir2/nir/red, 0-0.4)"},
    "vizParamsFalse10k": {"attr": "vizParamsFalse10k", "description": "False color viz params (swir1/nir/red, 0-10000)"},
    "vizParamsTrue": {"attr": "vizParamsTrue", "description": "True color viz params (red/green/blue, 0-0.4)"},
    "vizParamsTrue10k": {"attr": "vizParamsTrue10k", "description": "True color viz params (red/green/blue, 0-10000)"},
    "landsatCollectionDict": {"attr": "landsatCollectionDict", "description": "Landsat collection IDs by sensor/TOA-SR"},
    "s2CollectionDict": {"attr": "s2CollectionDict", "description": "Sentinel-2 collection IDs by TOA/SR"},
    "changeDirDict": {"attr": "changeDirDict", "description": "Expected change direction per index (+1 or -1)"},
    "testAreas": {"attr": "testAreas", "description": "Pre-defined test area geometries (CA, CO, HI, etc.)"},
    "palettes_cmocean": {"attr": "cmocean", "module": "geeViz.geePalettes", "description": "cmocean palettes (Thermal, Haline, Solar, Ice, Deep, Dense, Algae, etc.)"},
    "palettes_matplotlib": {"attr": "matplotlib", "module": "geeViz.geePalettes", "description": "matplotlib palettes (magma, inferno, plasma, viridis)"},
    "palettes_colorbrewer": {"attr": "colorbrewer", "module": "geeViz.geePalettes", "description": "ColorBrewer palettes (sequential, diverging, qualitative)"},
    "palettes_crameri": {"attr": "crameri", "module": "geeViz.geePalettes", "description": "Crameri scientific colour maps"},
    "palettes_misc": {"attr": "misc", "module": "geeViz.geePalettes", "description": "Miscellaneous palettes"},
}


@app.tool(annotations=_READ_ONLY)
def get_reference_data(name: str = "") -> str:
    """Look up geeViz reference dictionaries (band mappings, collection IDs, viz params, etc.).

    Args:
        name: Name of the reference dict to retrieve.
              Pass "" (empty) to list all available dicts with descriptions.

    Returns:
        JSON string with the dict contents or listing of available dicts.
    """
    _ensure_initialized()

    # Listing mode
    if not name:
        listing = [
            {"name": k, "description": v["description"]}
            for k, v in _REFERENCE_DATA.items()
        ]
        return json.dumps({
            "available": listing,
            "count": len(listing),
            "usage": 'Call get_reference_data(name="<dict_name>") to retrieve contents.',
            "note": "getImagesLib has additional module-level objects not listed here; use run_code to access them.",
        })

    # Lookup mode
    entry = _REFERENCE_DATA.get(name)
    if entry is None:
        available = sorted(_REFERENCE_DATA.keys())
        return json.dumps({"error": f"Unknown reference dict: {name!r}", "available": available})

    try:
        mod_path = entry.get("module", "geeViz.getImagesLib")
        import importlib
        mod = importlib.import_module(mod_path)
        raw = getattr(mod, entry["attr"])
        data = _make_serializable(raw)
        result = json.dumps({"name": name, "description": entry["description"], "data": data})
        # Cap size for large palette dicts
        if len(result) > 50000:
            # Return just the top-level keys
            if isinstance(raw, dict):
                summary = {k: list(v.keys()) if isinstance(v, dict) else type(v).__name__ for k, v in raw.items()}
                return json.dumps({"name": name, "description": entry["description"], "keys": summary,
                                   "note": "Large dict — showing keys only. Access individual palettes via run_code: palettes.cmocean['Thermal'][7]"})
        return result
    except Exception as exc:
        return json.dumps({"error": f"Failed to read {name}: {exc}"})


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
    _ensure_initialized()
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
    os.makedirs(_output_dir, exist_ok=True)
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
                fpath = os.path.join(_output_dir, fname).replace("\\", "/")
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
def search_places(
    query: str,
    lon: float = 0,
    lat: float = 0,
    radius: float = 5000,
    max_results: int = 10,
) -> str:
    """Search for places using the Google Places API.

    Useful for finding landmarks, businesses, or points of interest near
    a study area. Can also geocode addresses.

    Args:
        query: Search text (e.g. "fire station", "visitor center",
               "4240 S Olympic Way, SLC, UT").
        lon: Longitude for location bias (0 = no bias).
        lat: Latitude for location bias (0 = no bias).
        radius: Bias radius in meters. Default 5000.
        max_results: Maximum results (1-20). Default 10.

    Returns:
        JSON with matching places (name, address, coordinates, rating, types).
    """
    _ensure_initialized()
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
# Report tools
# ---------------------------------------------------------------------------

# Global report instance — persists across tool calls
_active_report = None


@app.tool(annotations=_WRITE)
def create_report(
    title: str = "Report",
    theme: str = "dark",
    layout: str = "report",
    tone: str = "neutral",
    header_text: str = "",
    prompt: str = "",
) -> str:
    """Create (or reset) a report. Must be called before add_report_section.

    Initializes a new Report object that persists across MCP calls.
    Any previously active report is discarded.

    Args:
        title: Report title.
        theme: "dark" (default) or "light".
        layout: "report" (portrait, vertical) or "poster" (landscape grid).
        tone: "neutral" (default), "informative", "technical", or custom tone.
        header_text: Introductory text below the title.
        prompt: Additional guidance for the executive summary LLM narrative.

    Returns:
        Confirmation with the report title and settings.
    """
    _ensure_initialized()
    global _active_report
    from geeViz.outputLib import reports as _rl

    _active_report = _rl.Report(
        title=title,
        theme=theme,
        layout=layout,
        tone=tone,
        header_text=header_text or None,
        prompt=prompt or None,
    )
    return json.dumps({
        "success": True,
        "message": f"Report '{title}' created ({theme} theme, {layout} layout, {tone} tone).",
        "tip": "Use add_report_section to add sections, then generate_report to produce output.",
    })


@app.tool(annotations=_WRITE)
def add_report_section(
    ee_obj_var: str,
    geometry_var: str,
    title: str = "Section",
    prompt: str = "",
    thumb_format: str = "png",
    band_names: str = "",
    scale: int = 30,
    chart_types: str = "",
    basemap: str = "",
    burn_in_geometry: bool = False,
    geometry_outline_color: str = "",
    geometry_fill_color: str = "",
    transition_periods: str = "",
    sankey_band_name: str = "",
    feature_label: str = "",
    area_format: str = "Percentage",
    date_format: str = "YYYY",
    reducer: str = "",
    generate_table: bool = True,
    generate_chart: bool = True,
) -> str:
    """Add a section to the active report.

    Each section analyses one ee.Image or ee.ImageCollection over a geometry.
    The report automatically generates a thumbnail, data table, chart, and
    LLM narrative for each section.

    Args:
        ee_obj_var: Name of an ee.Image or ee.ImageCollection variable in the
                    REPL namespace.
        geometry_var: Name of an ee.Geometry, ee.Feature, or ee.FeatureCollection
                      variable in the REPL namespace.
        title: Section heading.
        prompt: Optional per-section guidance for the LLM narrative.
        thumb_format: "png" (static), "gif" (animated), "filmstrip" (grid),
                      or "none" (no thumbnail). Default "png".
        band_names: Comma-separated band names (auto-detected if empty).
        scale: Pixel scale in meters (default 30).
        chart_types: Comma-separated list of chart types to produce (0-3).
                     Valid types: "bar", "line+markers", "donut", "scatter",
                     "sankey", "stacked_bar", "stacked_line+markers".
                     When "sankey" is included, transition_periods and
                     sankey_band_name are used for that chart.
                     Leave empty to auto-detect a single chart type.
                     Examples: "sankey,line+markers", "bar,donut", "sankey".
        basemap: Basemap preset for thumbnail (e.g. "esri-satellite").
        burn_in_geometry: Burn study area boundary onto the thumbnail.
        geometry_outline_color: Boundary outline color (e.g. "white", "red").
        geometry_fill_color: Boundary fill color with alpha (e.g. "FFFFFF33").
        transition_periods: JSON list of year pairs for Sankey
                            (e.g. "[[1985,2000],[2000,2024]]").
        sankey_band_name: Band name for Sankey (auto-detected if empty).
        feature_label: Property for per-feature labels (FeatureCollection).
        area_format: "Percentage" (default), "Hectares", "Acres", "Pixels".
        date_format: EE date format (default "YYYY").
        reducer: Override reducer ("mean", "first", "mode", etc.).
        generate_table: Include a data table (default True).
        generate_chart: Include a chart (default True).

    Returns:
        Confirmation with the section index and title.
    """
    _ensure_initialized()
    global _active_report
    ee = _namespace["ee"]

    if _active_report is None:
        return json.dumps({"error": "No active report. Call create_report first."})

    # Resolve EE objects from namespace
    ee_obj = _namespace.get(ee_obj_var)
    if ee_obj is None:
        return json.dumps({"error": f"Variable '{ee_obj_var}' not found in REPL namespace."})
    geom = _namespace.get(geometry_var)
    if geom is None:
        return json.dumps({"error": f"Variable '{geometry_var}' not found in REPL namespace."})

    # Build kwargs
    kwargs = {"scale": scale, "area_format": area_format, "date_format": date_format}

    # Parse chart_types — comma-separated list
    ct_list = [c.strip() for c in chart_types.split(",") if c.strip()] if chart_types else []

    if band_names:
        kwargs["band_names"] = [b.strip() for b in band_names.split(",")]
    if basemap:
        kwargs["basemap"] = basemap
    if burn_in_geometry:
        kwargs["burn_in_geometry"] = True
    if geometry_outline_color:
        kwargs["geometry_outline_color"] = geometry_outline_color
    if geometry_fill_color:
        kwargs["geometry_fill_color"] = geometry_fill_color
    if feature_label:
        kwargs["feature_label"] = feature_label
    if reducer:
        _reducer_map = {
            "first": ee.Reducer.first(),
            "mean": ee.Reducer.mean(),
            "median": ee.Reducer.median(),
            "min": ee.Reducer.min(),
            "max": ee.Reducer.max(),
            "sum": ee.Reducer.sum(),
            "mode": ee.Reducer.mode(),
            "stdDev": ee.Reducer.stdDev(),
            "count": ee.Reducer.count(),
        }
        kwargs["reducer"] = _reducer_map.get(reducer.strip())
    if transition_periods:
        try:
            kwargs["transition_periods"] = json.loads(transition_periods)
        except json.JSONDecodeError:
            return json.dumps({"error": f"Invalid transition_periods JSON: {transition_periods}"})
    if sankey_band_name:
        kwargs["sankey_band_name"] = sankey_band_name

    tf = thumb_format.lower().strip() if thumb_format else "png"
    if tf == "none":
        tf = None

    try:
        _active_report.add_section(
            ee_obj=ee_obj,
            geometry=geom,
            title=title,
            prompt=prompt or None,
            generate_table=generate_table,
            generate_chart=generate_chart,
            thumb_format=tf,
            chart_types=ct_list if ct_list else None,
            **kwargs,
        )
    except Exception as exc:
        return json.dumps({"error": f"Failed to add section: {exc}"})

    n = len(_active_report._sections)
    return json.dumps({
        "success": True,
        "message": f"Section {n} '{title}' added to report '{_active_report.title}'.",
        "total_sections": n,
        "tip": "Add more sections or call generate_report to produce the output.",
    })


@app.tool(annotations=_WRITE_OPEN)
def generate_report(
    format: str = "html",
    output_filename: str = "",
) -> str:
    """Generate the report from all added sections.

    Runs all EE computations (thumbnails, charts, tables) and LLM narratives
    in parallel, then renders the final output. This may take 30-120 seconds
    depending on the number of sections.

    Args:
        format: Output format -- "html" (interactive charts, default),
                "md" (markdown text only), or "pdf" (static images).
        output_filename: Filename for the output (saved to generated_outputs/).
                         Auto-generated if empty.

    Returns:
        The file path of the generated report, plus a metadata summary.
    """
    _ensure_initialized()
    global _active_report

    if _active_report is None:
        return json.dumps({"error": "No active report. Call create_report first."})
    if not _active_report._sections:
        return json.dumps({"error": "Report has no sections. Call add_report_section first."})

    fmt = format.lower().strip()
    if fmt not in ("html", "md", "pdf"):
        return json.dumps({"error": f"Invalid format '{format}'. Use 'html', 'md', or 'pdf'."})

    # Determine output path
    os.makedirs(_output_dir, exist_ok=True)
    if output_filename:
        out_path = os.path.join(_output_dir, output_filename)
    else:
        import time as _time_mod
        ts = int(_time_mod.time())
        ext = {"html": ".html", "md": ".md", "pdf": ".pdf"}[fmt]
        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in _active_report.title)[:40].strip()
        out_path = os.path.join(_output_dir, f"report_{safe_title}_{ts}{ext}")

    try:
        result = _active_report.generate(format=fmt, output_path=out_path)
    except Exception as exc:
        return json.dumps({"error": f"Report generation failed: {exc}"})

    # Build metadata
    try:
        meta_df = _active_report.metadata()
        meta_md = meta_df.to_markdown(index=False)
    except Exception:
        meta_md = "(metadata unavailable)"

    return json.dumps({
        "success": True,
        "format": fmt,
        "output_path": out_path,
        "sections": len(_active_report._sections),
        "metadata": meta_md,
        "tip": f"Report saved to {out_path}",
    })


@app.tool(annotations=_READ_ONLY)
def get_report_status() -> str:
    """Check the current report status -- title, theme, section count, and
    section titles.

    Returns:
        Report status or a message if no report is active.
    """
    global _active_report
    if _active_report is None:
        return json.dumps({
            "active": False,
            "message": "No active report. Call create_report to start one.",
        })

    sections = []
    for i, sec in enumerate(_active_report._sections):
        sections.append({
            "index": i + 1,
            "title": sec.title,
            "thumb_format": sec.thumb_format,
            "generate_table": sec.generate_table,
            "generate_chart": sec.generate_chart,
        })

    return json.dumps({
        "active": True,
        "title": _active_report.title,
        "theme": _active_report.theme,
        "layout": _active_report.layout,
        "tone": _active_report.tone,
        "section_count": len(_active_report._sections),
        "sections": sections,
    })


@app.tool(annotations=_DESTRUCTIVE)
def clear_report() -> str:
    """Discard the active report and all its sections.

    Returns:
        Confirmation that the report was cleared.
    """
    global _active_report
    old_title = _active_report.title if _active_report else None
    _active_report = None
    if old_title:
        return json.dumps({"success": True, "message": f"Report '{old_title}' cleared."})
    return json.dumps({"success": True, "message": "No active report to clear."})


# ---------------------------------------------------------------------------
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
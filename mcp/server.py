"""
geeViz MCP Server -- execution and introspection tools for Earth Engine via geeViz.

Unlike static doc snippets, this server executes code, inspects live GEE assets,
and dynamically queries API signatures. 33 tools replace the previous 49.
"""
from __future__ import annotations

import os
import sys

# Help before any heavy imports so "python -m geeViz.mcp.server --help" works without the mcp package
if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
    _help = """usage: python -m geeViz.mcp.server [--help]

geeViz MCP Server -- execution and introspection for Earth Engine via geeViz.

Options:
  -h, --help    Show this help and exit.

Environment (optional):
  MCP_TRANSPORT   Transport: "stdio" (default) or "streamable-http"
  MCP_HOST        Host for HTTP (default: 127.0.0.1)
  MCP_PORT        Port for HTTP (default: 8000)
  MCP_PATH        Path for HTTP (default: /mcp)

Tools (33):
  run_code                 Execute Python/GEE code in a persistent REPL namespace
  inspect_asset            Get metadata for any GEE asset
  get_api_reference        Look up function signatures and docstrings
  list_functions           List public functions in a geeViz module
  search_functions         Search across ALL geeViz modules for a function
  get_example              Read source code of a geeViz example script
  list_examples            List available example scripts
  list_assets              List assets in a GEE folder
  track_tasks              Get status of recent EE tasks
  view_map                 Open the geeView map and return the URL
  get_map_layers           See what layers are currently on the map
  clear_map                Clear all map layers and commands
  save_script              Save accumulated run_code history to a .py file
  get_version_info         Return geeViz, EE, and Python version info
  get_namespace            Inspect user-defined variables in the REPL
  get_project_info         Return current EE project ID and root assets
  save_notebook            Save run_code history as a Jupyter notebook
  export_to_asset          Export an ee.Image to a GEE asset (via geeViz wrapper)
  geocode                  Geocode a place name to coordinates / GEE boundaries
  search_datasets          Search the GEE dataset catalog by keyword
  get_dataset_info         Get detailed STAC metadata for a GEE dataset
  get_thumbnail            Get a PNG/GIF thumbnail of an ee.Image or ImageCollection
  export_to_drive          Export an ee.Image to Google Drive
  export_to_cloud_storage  Export an ee.Image to Google Cloud Storage
  cancel_tasks             Cancel running/ready EE tasks (all or by name)
  sample_values            Sample pixel values from an ee.Image at a point/region
  get_time_series          Extract band values over time from an ImageCollection
  delete_asset             Delete a single GEE asset
  copy_asset               Copy a GEE asset to a new location
  move_asset               Move a GEE asset (copy + delete source)
  create_folder            Create a GEE folder or ImageCollection
  update_acl               Update permissions (ACL) on a GEE asset
  get_collection_info      Get summary info for an ImageCollection

Examples:
  python -m geeViz.mcp.server
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

    def tool(self):
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

# Load agent instructions from the bundled markdown file.
# These are injected as the MCP server instructions (like a system prompt)
# so every connected client automatically knows how to use the tools.
_INSTRUCTIONS_FILE = os.path.join(_THIS_DIR, "agent-instructions.md")
try:
    with open(_INSTRUCTIONS_FILE, "r", encoding="utf-8") as _f:
        _SERVER_INSTRUCTIONS = _f.read()
except Exception:
    _SERVER_INSTRUCTIONS = None

app = FastMCP(
    "geeViz",
    instructions=_SERVER_INSTRUCTIONS,
    json_response=True,
) if _FastMCP is not None else _StubFastMCP()

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
}

# Persistent REPL namespace for run_code
_namespace: dict = {}

# Code history for save_script
_code_history: list[str] = []
_script_dir = os.path.join(_THIS_DIR, "generated_scripts")
_current_script_path: str | None = None


def _ensure_initialized():
    """Lazy-initialize EE and populate the REPL namespace. Thread-safe."""
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        import geeViz.geeView as gv
        import geeViz.getImagesLib as gil
        import ee

        _namespace.update({
            "ee": ee,
            "Map": gv.Map,
            "gv": gv,
            "gil": gil,
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
import io
import contextlib
import traceback


@app.tool()
def run_code(code: str, timeout: int = 120, reset: bool = False) -> str:
    """Execute Python/GEE code in a persistent REPL namespace (like Jupyter).

    The namespace persists across calls -- variables set in one call are
    available in the next.  Pre-populated with: ee, Map (gv.Map), gv
    (geeViz.geeView), gil (geeViz.getImagesLib).

    Args:
        code: Python code to execute.
        timeout: Max seconds to wait (default 120). On Windows a hung
                 getInfo() cannot be force-killed; the thread continues
                 in background.
        reset: If True, clear the namespace and re-initialize before
               executing.

    Returns:
        JSON with keys: success (bool), stdout, stderr, result, error.
    """
    if reset:
        _reset_namespace()
    else:
        _ensure_initialized()

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    result_holder: list = [None]
    error_holder: list = [None]

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
    thread.join(timeout=timeout)

    if thread.is_alive():
        return json.dumps({
            "success": False,
            "stdout": stdout_buf.getvalue(),
            "stderr": stderr_buf.getvalue(),
            "result": None,
            "error": f"Execution timed out after {timeout}s. "
                     "Note: on Windows, the thread continues in background and cannot be force-killed.",
        })

    if error_holder[0]:
        return json.dumps({
            "success": False,
            "stdout": stdout_buf.getvalue(),
            "stderr": stderr_buf.getvalue(),
            "result": None,
            "error": error_holder[0],
            "script_path": None,
        })

    # Success -- record in history and save to file
    _code_history.append(code)
    script_path = _save_history_to_file()

    result_val = result_holder[0]
    # Make result JSON-serializable
    result_str = None
    if result_val is not None:
        try:
            json.dumps(result_val)
            result_str = result_val
        except (TypeError, ValueError):
            result_str = repr(result_val)

    return json.dumps({
        "success": True,
        "stdout": stdout_buf.getvalue(),
        "stderr": stderr_buf.getvalue(),
        "result": result_str,
        "error": None,
        "script_path": script_path,
    })


# ---------------------------------------------------------------------------
# Tool 2: inspect_asset
# ---------------------------------------------------------------------------

@app.tool()
def inspect_asset(asset_id: str) -> str:
    """Get detailed metadata for any GEE asset (Image, ImageCollection, FeatureCollection, etc.).

    Returns band names/types, CRS, scale, dimensions, date range, size,
    column names, geometry type, and properties as appropriate.

    Args:
        asset_id: Full Earth Engine asset ID (e.g. "COPERNICUS/S2_SR_HARMONIZED").

    Returns:
        JSON with asset metadata.
    """
    _ensure_initialized()
    ee = _namespace["ee"]

    try:
        info = ee.data.getInfo(asset_id)
    except Exception as exc:
        return json.dumps({"error": str(exc), "asset_id": asset_id})

    if info is None:
        return json.dumps({"error": f"Asset not found: {asset_id}", "asset_id": asset_id})

    asset_type = info.get("type", "UNKNOWN")
    result: dict = {"asset_id": asset_id, "type": asset_type}

    try:
        if asset_type in ("IMAGE", "Image"):
            asset = ee.Image(asset_id)

        elif asset_type in ("IMAGE_COLLECTION", "ImageCollection"):
            asset = ee.ImageCollection(asset_id).limit(5)

        elif asset_type in ("TABLE", "FeatureCollection"):
            asset = ee.FeatureCollection(asset_id).limit(5)

        else:
            # Folder or other -- just return raw info
            asset = None

    except Exception as exc:
        asset = None
        result["detail_error"] = str(exc)

    if asset is not None:
        result["asset"] = asset.getInfo()
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool 3: get_api_reference
# ---------------------------------------------------------------------------
import inspect as _inspect


@app.tool()
def get_api_reference(module: str, function_name: str = "") -> str:
    """Look up the signature and docstring of a geeViz function or module.

    Uses Python's inspect module -- always reflects the installed code.

    Args:
        module: Short module name. One of: geeView, getImagesLib,
                changeDetectionLib, gee2Pandas, assetManagerLib,
                taskManagerLib, foliumView, phEEnoViz, cloudStorageManagerLib.
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

    obj = getattr(mod, function_name, None)
    if obj is None:
        return json.dumps({"error": f"{function_name!r} not found in {module}"})

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
# Tool 4: list_functions
# ---------------------------------------------------------------------------

@app.tool()
def list_functions(module: str, filter: str = "") -> str:
    """List all public functions and classes in a geeViz module with one-line descriptions.

    Args:
        module: Short module name (see get_api_reference for valid names).
        filter: Optional substring filter (case-insensitive) to narrow results.
                Useful for getImagesLib which has 100+ functions.

    Returns:
        JSON list of {name, type, description} objects.
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

    entries = []
    for name in sorted(dir(mod)):
        if name.startswith("_"):
            continue
        obj = getattr(mod, name, None)
        if obj is None:
            continue
        if not (callable(obj) or _inspect.isclass(obj)):
            continue
        if filter and filter.lower() not in name.lower():
            continue

        doc = _inspect.getdoc(obj) or ""
        first_line = doc.split("\n")[0].strip() if doc else "(no description)"
        kind = "class" if _inspect.isclass(obj) else "function"
        entries.append({"name": name, "type": kind, "description": first_line})

    # For geeView, also list mapper class methods if present
    if module == "geeView":
        mapper_cls = getattr(mod, "mapper", None)
        if mapper_cls and _inspect.isclass(mapper_cls):
            for mname in sorted(dir(mapper_cls)):
                if mname.startswith("_"):
                    continue
                mobj = getattr(mapper_cls, mname, None)
                if not callable(mobj):
                    continue
                if filter and filter.lower() not in mname.lower():
                    continue
                doc = _inspect.getdoc(mobj) or ""
                first_line = doc.split("\n")[0].strip() if doc else "(no description)"
                entries.append({
                    "name": f"mapper.{mname}",
                    "type": "method",
                    "description": first_line,
                })

    return json.dumps({"module": module, "count": len(entries), "functions": entries})


# ---------------------------------------------------------------------------
# Tool 5: get_example
# ---------------------------------------------------------------------------

@app.tool()
def get_example(example_name: str) -> str:
    """Read the source code of a geeViz example script.

    Args:
        example_name: Name of the example, with or without extension.
                      Supports .py (returns source) and .ipynb (extracts
                      code and markdown cells).

    Returns:
        The example source code, or an error listing available examples.
    """
    # Normalize: strip extension if given
    base = example_name
    for ext in (".py", ".ipynb"):
        if base.endswith(ext):
            base = base[:-len(ext)]
            break

    # Try .py first, then .ipynb
    py_path = os.path.join(_EXAMPLES_DIR, base + ".py")
    nb_path = os.path.join(_EXAMPLES_DIR, base + ".ipynb")

    if os.path.isfile(py_path):
        with open(py_path, "r", encoding="utf-8") as f:
            source = f.read()
        return json.dumps({
            "example": base + ".py",
            "type": "python",
            "source": source,
        })

    if os.path.isfile(nb_path):
        try:
            with open(nb_path, "r", encoding="utf-8") as f:
                nb = json.load(f)
            cells = []
            for cell in nb.get("cells", []):
                cell_type = cell.get("cell_type", "")
                source = "".join(cell.get("source", []))
                if cell_type in ("code", "markdown") and source.strip():
                    cells.append({"cell_type": cell_type, "source": source})
            return json.dumps({
                "example": base + ".ipynb",
                "type": "notebook",
                "cells": cells,
            })
        except Exception as exc:
            return json.dumps({"error": f"Failed to read notebook: {exc}"})

    # Not found -- list available
    available = _list_example_files()
    return json.dumps({
        "error": f"Example not found: {example_name!r}",
        "available_examples": available,
    })


def _list_example_files() -> list[str]:
    """Return sorted list of example filenames (.py and .ipynb)."""
    if not os.path.isdir(_EXAMPLES_DIR):
        return []
    return sorted(
        f for f in os.listdir(_EXAMPLES_DIR)
        if (f.endswith(".py") or f.endswith(".ipynb")) and f != "__init__.py"
    )


# ---------------------------------------------------------------------------
# Tool 6: list_examples
# ---------------------------------------------------------------------------

@app.tool()
def list_examples(filter: str = "") -> str:
    """List available geeViz example scripts with descriptions.

    Args:
        filter: Optional substring filter (case-insensitive).

    Returns:
        JSON list of {name, description} objects.
    """
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
                    # Read first few lines looking for a docstring or comment
                    lines = []
                    for _ in range(20):
                        line = f.readline()
                        if not line:
                            break
                        lines.append(line)
                    text = "".join(lines)
                    # Try to extract docstring
                    try:
                        tree = ast.parse(text)
                        if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant):
                            desc = str(tree.body[0].value.value).split("\n")[0].strip()
                    except SyntaxError:
                        pass
                    # Fall back to first comment
                    if not desc:
                        for line in lines:
                            stripped = line.strip()
                            if stripped.startswith("#") and len(stripped) > 2:
                                desc = stripped.lstrip("#").strip()
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
                            # First non-empty line, strip markdown headers
                            desc = source.split("\n")[0].lstrip("#").strip()
                            break
            except Exception:
                pass

        results.append({"name": fname, "description": desc or "(no description)"})

    return json.dumps({"count": len(results), "examples": results})


# ---------------------------------------------------------------------------
# Tool 7: list_assets
# ---------------------------------------------------------------------------

@app.tool()
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
    for a in assets[:200]:
        entries.append({
            "id": a.get("id") or a.get("name", ""),
            "type": a.get("type", "UNKNOWN"),
            "sizeBytes": a.get("sizeBytes"),
        })

    out: dict = {"folder": folder, "count": len(entries), "assets": entries}
    if len(assets) > 200:
        out["note"] = f"Showing 200 of {len(assets)} assets. Narrow your query for the rest."

    return json.dumps(out)


# ---------------------------------------------------------------------------
# Tool 8: track_tasks
# ---------------------------------------------------------------------------

@app.tool()
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
    for t in tasks[:50]:
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
# Tool 9: view_map
# ---------------------------------------------------------------------------

@app.tool()
def view_map(open_browser: bool = True) -> str:
    """Open the geeView interactive map and return the URL.

    Call this after adding layers with run_code. The Map object is the
    same singleton used by run_code, so all layers added there will appear.

    Args:
        open_browser: Whether to open the map in the default browser (default True).

    Returns:
        JSON with the map URL and layer count.
    """
    _ensure_initialized()
    Map = _namespace["Map"]

    # Capture the URL that view() prints to stdout
    url_buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(url_buf):
            Map.view(open_browser=open_browser, open_iframe=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)})

    # Extract URL from printed output
    printed = url_buf.getvalue()
    url = None
    for line in printed.splitlines():
        line = line.strip()
        if line.startswith("http"):
            url = line
            break

    layer_count = len(Map.idDictList) if hasattr(Map, "idDictList") else 0

    return json.dumps({
        "url": url,
        "layer_count": layer_count,
        "message": f"Map opened with {layer_count} layer(s)." if url else "Map.view() ran but no URL was captured.",
        "raw_output": printed.strip(),
    })


# ---------------------------------------------------------------------------
# Tool 10: get_map_layers
# ---------------------------------------------------------------------------

@app.tool()
def get_map_layers() -> str:
    """See what layers are currently on the map.

    Returns layer names, types, visibility, and visualization parameters.
    Useful for debugging why a map looks wrong or checking state.

    Returns:
        JSON with layers list and active map commands.
    """
    _ensure_initialized()
    Map = _namespace["Map"]

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

    return json.dumps({
        "layer_count": len(layers),
        "layers": layers,
        "commands": commands,
    })


# ---------------------------------------------------------------------------
# Tool 11: clear_map
# ---------------------------------------------------------------------------

@app.tool()
def clear_map() -> str:
    """Clear all layers and commands from the map.

    Resets the Map to a blank state so you can start fresh.

    Returns:
        JSON confirmation.
    """
    _ensure_initialized()
    Map = _namespace["Map"]

    try:
        Map.clearMap()
    except Exception as exc:
        return json.dumps({"error": str(exc)})

    return json.dumps({
        "success": True,
        "message": "Map cleared. All layers and commands removed.",
    })


# ---------------------------------------------------------------------------
# Tool 12: search_functions
# ---------------------------------------------------------------------------

@app.tool()
def search_functions(query: str) -> str:
    """Search for a function across ALL geeViz modules by name or docstring.

    Unlike list_functions (which searches one module), this searches everything
    at once. Useful when you don't know which module a function is in.

    Args:
        query: Search term (case-insensitive). Matched against function names
               and the first line of their docstrings.

    Returns:
        JSON list of {module, name, type, description} matches.
    """
    _ensure_initialized()
    q = query.lower()
    results = []

    for short_name, fq_name in _MODULE_MAP.items():
        try:
            mod = importlib.import_module(fq_name)
        except Exception:
            continue

        for name in dir(mod):
            if name.startswith("_"):
                continue
            obj = getattr(mod, name, None)
            if obj is None or not (callable(obj) or _inspect.isclass(obj)):
                continue

            doc = _inspect.getdoc(obj) or ""
            first_line = doc.split("\n")[0].strip() if doc else ""

            if q in name.lower() or q in first_line.lower():
                kind = "class" if _inspect.isclass(obj) else "function"
                results.append({
                    "module": short_name,
                    "name": name,
                    "type": kind,
                    "description": first_line or "(no description)",
                })

    return json.dumps({"query": query, "count": len(results), "results": results})


# ---------------------------------------------------------------------------
# Tool 13: save_script
# ---------------------------------------------------------------------------

@app.tool()
def save_script(filename: str = "") -> str:
    """Save the accumulated run_code history to a standalone .py file.

    The script includes all necessary imports and every successful run_code
    call in order, so it can be run independently.

    Args:
        filename: Optional custom filename (saved in geeViz/mcp/generated_scripts/).
                  If omitted, uses the auto-generated session filename.

    Returns:
        JSON with the file path and number of code blocks saved.
    """
    if not _code_history:
        return json.dumps({
            "error": "No code has been executed yet. Use run_code first.",
        })

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


# ---------------------------------------------------------------------------
# Tool 14: get_version_info
# ---------------------------------------------------------------------------

@app.tool()
def get_version_info() -> str:
    """Return version information for geeViz, Earth Engine, and Python.

    Useful for debugging environment issues or confirming which versions
    are active in the MCP server session.

    Returns:
        JSON with geeViz_version, ee_version, python_version, platform.
    """
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


# ---------------------------------------------------------------------------
# Tool 15: get_namespace
# ---------------------------------------------------------------------------

# Builtins pre-populated by _ensure_initialized -- excluded from get_namespace
_NAMESPACE_BUILTINS = {"ee", "Map", "gv", "gil"}


@app.tool()
def get_namespace() -> str:
    """Inspect user-defined variables in the persistent REPL namespace.

    Shows what variables exist after run_code calls. Excludes the
    built-in entries (ee, Map, gv, gil). For each variable, reports
    name, type, and a truncated repr. No getInfo() calls are made --
    this is pure Python-side introspection.

    Returns:
        JSON with a list of {name, type, repr} objects.
    """
    _ensure_initialized()
    ee = _namespace["ee"]

    entries = []
    for name, obj in sorted(_namespace.items()):
        if name.startswith("_") or name in _NAMESPACE_BUILTINS:
            continue

        # Detect ee-specific types
        type_name = type(obj).__name__
        if isinstance(obj, ee.Image):
            type_name = "ee.Image"
        elif isinstance(obj, ee.ImageCollection):
            type_name = "ee.ImageCollection"
        elif isinstance(obj, ee.FeatureCollection):
            type_name = "ee.FeatureCollection"
        elif isinstance(obj, ee.Feature):
            type_name = "ee.Feature"
        elif isinstance(obj, ee.Geometry):
            type_name = "ee.Geometry"
        elif isinstance(obj, ee.Number):
            type_name = "ee.Number"
        elif isinstance(obj, ee.String):
            type_name = "ee.String"
        elif isinstance(obj, ee.List):
            type_name = "ee.List"
        elif isinstance(obj, ee.Dictionary):
            type_name = "ee.Dictionary"
        elif isinstance(obj, ee.Filter):
            type_name = "ee.Filter"
        elif isinstance(obj, ee.Reducer):
            type_name = "ee.Reducer"
        elif isinstance(obj, ee.ComputedObject):
            type_name = "ee.ComputedObject"

        # Truncated repr (no getInfo)
        try:
            r = repr(obj)
            if len(r) > 200:
                r = r[:200] + "..."
        except Exception:
            r = "(repr failed)"

        entries.append({"name": name, "type": type_name, "repr": r})

    return json.dumps({
        "count": len(entries),
        "variables": entries,
        "note": "Excludes builtins (ee, Map, gv, gil). No getInfo() calls made.",
    })


# ---------------------------------------------------------------------------
# Tool 16: get_project_info
# ---------------------------------------------------------------------------

@app.tool()
def get_project_info() -> str:
    """Return the current Earth Engine project ID and a sample of root assets.

    Useful for confirming which GEE project the session is using and
    seeing what top-level assets are available.

    Returns:
        JSON with project_id and a list of root assets.
    """
    _ensure_initialized()
    ee = _namespace["ee"]

    result: dict = {}

    # Get project ID
    try:
        project = ee.data._get_cloud_api_user_project()
        result["project_id"] = project
    except Exception as exc:
        result["project_id"] = None
        result["project_error"] = str(exc)

    # List root assets
    if result.get("project_id"):
        try:
            root = f"projects/{result['project_id']}/assets"
            assets_response = ee.data.listAssets({"parent": root})
            assets = assets_response.get("assets", [])
            result["root_assets"] = [
                {
                    "id": a.get("id") or a.get("name", ""),
                    "type": a.get("type", "UNKNOWN"),
                }
                for a in assets[:50]
            ]
            result["root_asset_count"] = len(assets)
        except Exception as exc:
            result["root_assets"] = []
            result["assets_error"] = str(exc)

    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool 17: save_notebook
# ---------------------------------------------------------------------------

@app.tool()
def save_notebook(filename: str = "") -> str:
    """Save the accumulated run_code history as a Jupyter notebook (.ipynb).

    Creates one code cell per run_code call, with a markdown header cell
    and an import cell at the top. Uses nbformat 4.5 structure (plain JSON,
    no nbformat library required).

    Args:
        filename: Optional custom filename (saved in geeViz/mcp/generated_scripts/).
                  If omitted, uses a timestamped default. Extension .ipynb is
                  added automatically if missing.

    Returns:
        JSON with the file path and number of code cells saved.
    """
    if not _code_history:
        return json.dumps({
            "error": "No code has been executed yet. Use run_code first.",
        })

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
# Tool 18: export_to_asset
# ---------------------------------------------------------------------------

@app.tool()
def export_to_asset(
    image_var: str,
    asset_id: str,
    region_var: str = "",
    scale: int = 30,
    crs: str = "EPSG:4326",
    overwrite: bool = False,
    pyramiding_policy: str = "mean",
) -> str:
    """Export an ee.Image from the REPL namespace to a GEE asset.

    Uses geeViz's exportToAssetWrapper which handles existing assets,
    pyramiding policy, and region clipping automatically.

    Args:
        image_var: Name of the ee.Image variable in the REPL namespace.
        asset_id: Full destination asset ID
                  (e.g. "projects/my-project/assets/my_export").
        region_var: Optional name of an ee.Geometry or ee.FeatureCollection
                    variable to use as the export region. If omitted, the
                    image's footprint is used.
        scale: Output resolution in meters (default 30).
        crs: Coordinate reference system (default "EPSG:4326").
        overwrite: If True, overwrite an existing asset (default False).
        pyramiding_policy: Pyramiding policy for bands -- "mean", "mode",
                           "min", "max", "median", or "sample" (default "mean").

    Returns:
        JSON with export status or an error.
    """
    _ensure_initialized()
    ee = _namespace["ee"]
    gil = _namespace["gil"]

    # Look up image
    image = _namespace.get(image_var)
    if image is None:
        return json.dumps({"error": f"Variable {image_var!r} not found in namespace."})
    if not isinstance(image, ee.Image):
        return json.dumps({
            "error": f"Variable {image_var!r} is {type(image).__name__}, not ee.Image.",
        })

    # Look up region (optional)
    region = None
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

    # Derive asset name from the asset path
    asset_name = asset_id.split("/")[-1]

    # Build pyramiding policy object
    pyramiding_obj = {"default": pyramiding_policy}

    # Call the geeViz wrapper (captures stdout since it prints status)
    stdout_buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_buf):
            gil.exportToAssetWrapper(
                image, asset_name, asset_id,
                pyramidingPolicyObject=pyramiding_obj,
                roi=region, scale=scale, crs=crs,
                overwrite=overwrite,
            )
    except Exception as exc:
        return json.dumps({
            "error": f"Export failed: {exc}",
            "stdout": stdout_buf.getvalue(),
        })

    return json.dumps({
        "success": True,
        "asset_id": asset_id,
        "scale": scale,
        "crs": crs,
        "overwrite": overwrite,
        "pyramiding_policy": pyramiding_policy,
        "stdout": stdout_buf.getvalue().strip(),
        "message": "Export task started. Use track_tasks() to monitor progress.",
    })


# ---------------------------------------------------------------------------
# Tool 19: geocode
# ---------------------------------------------------------------------------
import urllib.request
import urllib.parse
import urllib.error


@app.tool()
def geocode(place_name: str, use_boundaries: bool = False) -> str:
    """Geocode a place name to coordinates and optionally find GEE boundary polygons.

    Uses OpenStreetMap Nominatim for point/bounding-box geocoding (no API key
    needed). When use_boundaries=True, also searches GEE boundary collections
    (WDPA, FAO/GAUL, TIGER States/Counties) for a matching polygon and returns
    the asset ID and filter expression for use in run_code.

    Args:
        place_name: Place name to geocode (e.g. "Yellowstone National Park",
                    "Montana", "Bozeman, MT").
        use_boundaries: If True, also search GEE boundary FeatureCollections
                        for a matching polygon. Default False.

    Returns:
        JSON with coordinates, bounding box, ee code snippets, and optionally
        matching GEE boundary info.
    """
    # --- Nominatim geocoding (stdlib only) ---
    params = urllib.parse.urlencode({
        "q": place_name,
        "format": "json",
        "limit": "1",
        "addressdetails": "1",
    })
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "geeViz-MCP/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return json.dumps({"error": f"Nominatim request failed: {exc}"})

    if not data:
        return json.dumps({"error": f"No results found for {place_name!r}."})

    hit = data[0]
    lat = float(hit["lat"])
    lon = float(hit["lon"])
    display_name = hit.get("display_name", place_name)
    osm_type = hit.get("type", "")
    bbox = hit.get("boundingbox", [])  # [south, north, west, east] as strings

    result: dict = {
        "place_name": place_name,
        "display_name": display_name,
        "latitude": lat,
        "longitude": lon,
        "osm_type": osm_type,
        "ee_point_code": f"ee.Geometry.Point([{lon}, {lat}])",
    }

    if bbox and len(bbox) == 4:
        south, north, west, east = [float(x) for x in bbox]
        result["bbox"] = {"south": south, "north": north, "west": west, "east": east}
        result["ee_bbox_code"] = (
            f"ee.Geometry.Rectangle([{west}, {south}, {east}, {north}])"
        )

    # --- Optional GEE boundary search ---
    if use_boundaries:
        _ensure_initialized()
        ee = _namespace["ee"]

        # Boundary collections to search: (asset_id, name_property, description)
        boundary_sources = [
            ("WCMC/WDPA/current/polygons", "NAME", "WDPA Protected Areas"),
            ("FAO/GAUL/2015/level0", "ADM0_NAME", "GAUL Countries"),
            ("FAO/GAUL/2015/level1", "ADM1_NAME", "GAUL Admin Level 1"),
            ("FAO/GAUL/2015/level2", "ADM2_NAME", "GAUL Admin Level 2"),
            ("TIGER/2018/States", "NAME", "US States"),
            ("TIGER/2018/Counties", "NAME", "US Counties"),
        ]

        matches = []
        search_term = place_name.strip()

        for asset_id, name_prop, source_desc in boundary_sources:
            try:
                fc = ee.FeatureCollection(asset_id)
                # Case-insensitive search using ee.Filter
                filtered = fc.filter(ee.Filter.eq(name_prop, search_term))
                count = filtered.size().getInfo()
                if count > 0:
                    # Get the name of the first match for confirmation
                    first_name = filtered.first().get(name_prop).getInfo()
                    matches.append({
                        "source": source_desc,
                        "asset_id": asset_id,
                        "filter_property": name_prop,
                        "filter_value": first_name,
                        "feature_count": count,
                        "ee_code": (
                            f"ee.FeatureCollection('{asset_id}')"
                            f".filter(ee.Filter.eq('{name_prop}', '{first_name}'))"
                        ),
                    })
            except Exception:
                continue  # Skip collections that error (e.g. access issues)

        result["boundary_matches"] = matches
        if not matches:
            result["boundary_note"] = (
                "No exact boundary match found. Try a different spelling, "
                "or use the ee_point_code / ee_bbox_code above with .buffer()."
            )

    return json.dumps(result)


# ---------------------------------------------------------------------------
# Dataset catalog cache helpers
# ---------------------------------------------------------------------------
import time as _time

_CACHE_DIR = os.path.join(_THIS_DIR, "dataset_cache")
_CACHE_TTL = 86400  # 24 hours in seconds
_CACHE_META_FILE = os.path.join(_CACHE_DIR, "cache_meta.json")
_cache_lock = threading.Lock()

_CATALOG_URLS = {
    "official": "https://raw.githubusercontent.com/samapriya/Earth-Engine-Datasets-List/master/gee_catalog.json",
    "community": "https://raw.githubusercontent.com/samapriya/awesome-gee-community-datasets/master/community_datasets.json",
}

_CATALOG_FILES = {
    "official": "gee_catalog.json",
    "community": "community_datasets.json",
}


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
            req = urllib.request.Request(url, headers={"User-Agent": "geeViz-MCP/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            # Cache the result
            os.makedirs(_CACHE_DIR, exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(raw)
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

@app.tool()
def search_datasets(query: str, source: str = "all", max_results: int = 10) -> str:
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


# ---------------------------------------------------------------------------
# Tool 21: get_dataset_info
# ---------------------------------------------------------------------------

@app.tool()
def get_dataset_info(dataset_id: str) -> str:
    """Get detailed STAC metadata for a GEE dataset.

    Fetches the full STAC JSON record from earthengine-stac.storage.googleapis.com
    and returns it as-is. The record includes bands (with classes, wavelengths,
    scale/offset), description, temporal/spatial extent, keywords, license,
    visualization parameters, provider info, and links.

    This is the "drill down" companion to search_datasets -- use
    search_datasets to find datasets, then get_dataset_info for full details.

    Only works for official GEE datasets (STAC records don't exist for
    community datasets). For community datasets, use inspect_asset instead.

    Args:
        dataset_id: Full GEE dataset ID (e.g. "LANDSAT/LC09/C02/T1_L2").

    Returns:
        The full STAC JSON record for the dataset, or an error message.
    """
    # Build STAC URL: first segment is directory, full ID with / -> _ is filename
    parts = dataset_id.split("/")
    if not parts:
        return json.dumps({"error": "Empty dataset_id."})

    stac_dir = parts[0]
    stac_file = dataset_id.replace("/", "_")
    stac_url = (
        f"https://earthengine-stac.storage.googleapis.com/"
        f"catalog/{stac_dir}/{stac_file}.json"
    )

    try:
        req = urllib.request.Request(stac_url, headers={"User-Agent": "geeViz-MCP/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            stac = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return json.dumps({
                "error": f"No STAC record found for {dataset_id!r}. "
                         "This may be a community dataset -- try inspect_asset instead.",
                "dataset_id": dataset_id,
                "stac_url": stac_url,
            })
        return json.dumps({
            "error": f"HTTP {exc.code} fetching STAC record: {exc.reason}",
            "stac_url": stac_url,
        })
    except Exception as exc:
        return json.dumps({"error": f"Failed to fetch STAC record: {exc}", "stac_url": stac_url})

    # Return the full STAC record as-is
    return json.dumps(stac)


# ---------------------------------------------------------------------------
# Tool 22: get_thumbnail
# ---------------------------------------------------------------------------
import base64 as _base64


@app.tool()
def get_thumbnail(
    variable: str,
    viz_params: str = "{}",
    dimensions: int = 512,
    region_var: str = "",
    frames_per_second: int = 3,
):
    """Get a satellite imagery thumbnail from Earth Engine for visual inspection.

    Returns the image directly so you (the AI) can see and describe what is
    on the ground. These are satellite images captured from space -- here is
    how to interpret common band combinations:

    - **True color (e.g. B4,B3,B2 or B_R,B_G,B_B):** Shows the Earth as the
      human eye would see it. Green = vegetation, brown = bare soil, white =
      clouds/snow, blue/dark = water, grey = urban/rock.
    - **False color (e.g. B5,B4,B3 or NIR,Red,Green):** Vegetation appears
      bright red/magenta, bare ground is tan/brown, water is dark blue/black,
      urban areas are cyan/grey, burned areas are dark brown/black.
    - **Single band with palette (e.g. NDVI, elevation):** Color ramp maps
      values to colors -- check the palette and min/max to interpret.

    When describing what you see, mention: dominant land cover types, any
    visible change patterns (for animations), cloud cover if present, and
    spatial patterns (e.g. river corridors, urban grids, agricultural fields).

    For ee.Image, returns a PNG thumbnail. For ee.ImageCollection, returns an
    animated GIF via getVideoThumbURL (useful for showing change over time).

    IMPORTANT for ImageCollection GIFs: You MUST provide viz_params with
    exactly 3 bands (or 1 band + palette) to produce a valid RGB animation.
    The EE API requires RGB/RGBA visualization for video thumbnails.

    Args:
        variable: Name of an ee.Image or ee.ImageCollection variable in the
                  REPL namespace (set via run_code).
        viz_params: JSON string of visualization parameters. Common keys:
                    bands (list of 3 for RGB, or 1 + palette), min, max,
                    palette, gamma.
                    Example: '{"bands": ["B4","B3","B2"], "min": 0, "max": 3000}'
                    ALWAYS provide bands + min/max -- without them, EE uses
                    unhelpful defaults and GIFs will fail.
        dimensions: Thumbnail width in pixels (default 512).
        region_var: Optional name of an ee.Geometry or ee.FeatureCollection
                    variable to use as the thumbnail region.
        frames_per_second: Animation speed for ImageCollection GIFs
                           (default 3). Ignored for single images.

    Returns:
        A list containing the image (PNG/GIF) and a text message with the
        thumbnail URL. IMPORTANT: Always share the thumbnail URL with the
        user so they can open it in a browser -- especially for animated
        GIFs, which may not play inline in chat UIs.
    """
    _ensure_initialized()
    ee = _namespace["ee"]

    # Look up variable
    obj = _namespace.get(variable)
    if obj is None:
        return json.dumps({
            "error": f"Variable {variable!r} not found in namespace. "
                     "Use run_code to create it first.",
        })

    # Parse viz params
    try:
        params = json.loads(viz_params) if isinstance(viz_params, str) else viz_params
    except (json.JSONDecodeError, TypeError) as exc:
        return json.dumps({"error": f"Invalid viz_params JSON: {exc}"})

    if not isinstance(params, dict):
        return json.dumps({"error": "viz_params must be a JSON object (dict)."})

    params["dimensions"] = dimensions

    # Handle region
    if region_var:
        region = _namespace.get(region_var)
        if region is None:
            return json.dumps({"error": f"Region variable {region_var!r} not found in namespace."})
        if isinstance(region, ee.FeatureCollection):
            region = region.geometry()
        if isinstance(region, ee.Geometry):
            params["region"] = region
        else:
            return json.dumps({
                "error": f"Variable {region_var!r} is {type(region).__name__}, "
                         "expected ee.Geometry or ee.FeatureCollection.",
            })

    # Generate thumbnail URL
    is_collection = False
    try:
        if isinstance(obj, ee.Image):
            params["format"] = "png"
            thumb_url = obj.getThumbURL(params)
        elif isinstance(obj, ee.ImageCollection):
            is_collection = True
            # Validate: GIF requires RGB visualization (3 bands or 1 band + palette)
            bands = params.get("bands", [])
            palette = params.get("palette")
            if not bands and not palette:
                return json.dumps({
                    "error": "ImageCollection GIFs require viz_params with 'bands' "
                             "(3 bands for RGB, or 1 band + 'palette'). "
                             "Example: '{\"bands\": [\"B4\",\"B3\",\"B2\"], \"min\": 0, \"max\": 3000}'",
                })
            count = obj.size().getInfo()
            if count == 0:
                return json.dumps({"error": "ImageCollection is empty -- no images to animate."})
            if count > 40:
                obj = obj.limit(40)
            # getVideoThumbURL always returns GIF; format param is optional
            # but framesPerSecond is needed for animation timing
            params["framesPerSecond"] = frames_per_second
            thumb_url = obj.getVideoThumbURL(params)
        else:
            return json.dumps({
                "error": f"Variable {variable!r} is {type(obj).__name__}, "
                         "expected ee.Image or ee.ImageCollection.",
            })
    except Exception as exc:
        return json.dumps({"error": f"Failed to generate thumbnail: {exc}"})

    # Download the image
    img_format = "gif" if is_collection else "png"
    try:
        req = urllib.request.Request(thumb_url, headers={"User-Agent": "geeViz-MCP/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            img_bytes = resp.read()
    except Exception as exc:
        return json.dumps({
            "error": f"Failed to download thumbnail: {exc}",
            "thumb_url": thumb_url,
        })

    # Validate the response is the expected format
    if is_collection:
        # GIF magic bytes: GIF87a or GIF89a
        if len(img_bytes) < 6 or img_bytes[:3] != b"GIF":
            return json.dumps({
                "error": "Earth Engine did not return a valid GIF. "
                         "Ensure viz_params has exactly 3 bands (RGB) or "
                         "1 band + palette, and that the collection is not empty.",
                "thumb_url": thumb_url,
                "response_size": len(img_bytes),
                "response_start": img_bytes[:20].hex() if img_bytes else "",
            })
    else:
        # PNG magic bytes: 89 50 4E 47
        if len(img_bytes) < 4 or img_bytes[:4] != b"\x89PNG":
            return json.dumps({
                "error": "Earth Engine did not return a valid PNG.",
                "thumb_url": thumb_url,
                "response_size": len(img_bytes),
            })

    # Build a text message with the URL -- always included so the LLM can
    # share it with the user (GIFs won't animate inline in most chat UIs).
    if is_collection:
        url_text = (
            f"Animated GIF thumbnail URL (share with user -- GIFs may not "
            f"animate inline):\n{thumb_url}"
        )
    else:
        url_text = f"Thumbnail URL:\n{thumb_url}"

    # Return as [Image, text] so the LLM sees the image AND gets the URL.
    # FastMCP's _convert_to_content flattens lists: Image → ImageContent,
    # str → TextContent.
    if _MCPImage is not None:
        try:
            return [_MCPImage(data=img_bytes, format=img_format), url_text]
        except Exception:
            pass

    # Fallback: base64-encoded image in JSON (when MCP Image type unavailable)
    return json.dumps({
        "image_base64": _base64.b64encode(img_bytes).decode("ascii"),
        "mime_type": f"image/{img_format}",
        "image_url": thumb_url,
        "note": f"Satellite image returned as base64 {img_format.upper()}. "
                "MCP Image type was not available. SHARE THE image_url WITH "
                "THE USER so they can view it in a browser.",
    })


# ---------------------------------------------------------------------------
# Tool 23: export_to_drive
# ---------------------------------------------------------------------------

@app.tool()
def export_to_drive(
    image_var: str,
    output_name: str,
    drive_folder: str,
    region_var: str,
    scale: int = 30,
    crs: str = "EPSG:4326",
    output_no_data: int = -32768,
) -> str:
    """Export an ee.Image from the REPL namespace to Google Drive.

    Uses geeViz's exportToDriveWrapper. A region variable is required
    for Drive exports.

    Args:
        image_var: Name of the ee.Image variable in the REPL namespace.
        output_name: Output filename (without extension).
        drive_folder: Google Drive folder name to export into.
        region_var: Name of an ee.Geometry or ee.FeatureCollection variable
                    to use as the export region. Required for Drive exports.
        scale: Output resolution in meters (default 30).
        crs: Coordinate reference system (default "EPSG:4326").
        output_no_data: NoData value for the output (default -32768).

    Returns:
        JSON with export status or an error.
    """
    _ensure_initialized()
    ee = _namespace["ee"]
    gil = _namespace["gil"]

    # Look up image
    image = _namespace.get(image_var)
    if image is None:
        return json.dumps({"error": f"Variable {image_var!r} not found in namespace."})
    if not isinstance(image, ee.Image):
        return json.dumps({
            "error": f"Variable {image_var!r} is {type(image).__name__}, not ee.Image.",
        })

    # Look up region (required)
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

    stdout_buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_buf):
            gil.exportToDriveWrapper(
                image, output_name, drive_folder,
                region, scale, crs, None, output_no_data,
            )
    except Exception as exc:
        return json.dumps({
            "error": f"Export to Drive failed: {exc}",
            "stdout": stdout_buf.getvalue(),
        })

    return json.dumps({
        "success": True,
        "output_name": output_name,
        "drive_folder": drive_folder,
        "scale": scale,
        "crs": crs,
        "stdout": stdout_buf.getvalue().strip(),
        "message": "Export to Drive task started. Use track_tasks() to monitor progress.",
    })


# ---------------------------------------------------------------------------
# Tool 24: export_to_cloud_storage
# ---------------------------------------------------------------------------

@app.tool()
def export_to_cloud_storage(
    image_var: str,
    output_name: str,
    bucket: str,
    region_var: str,
    scale: int = 30,
    crs: str = "EPSG:4326",
    output_no_data: int = -32768,
    file_format: str = "GeoTIFF",
    overwrite: bool = False,
) -> str:
    """Export an ee.Image from the REPL namespace to Google Cloud Storage.

    Uses geeViz's exportToCloudStorageWrapper with Cloud Optimized GeoTIFF
    format options by default.

    Args:
        image_var: Name of the ee.Image variable in the REPL namespace.
        output_name: Output filename (without extension).
        bucket: Google Cloud Storage bucket name.
        region_var: Name of an ee.Geometry or ee.FeatureCollection variable
                    to use as the export region. Required for GCS exports.
        scale: Output resolution in meters (default 30).
        crs: Coordinate reference system (default "EPSG:4326").
        output_no_data: NoData value for the output (default -32768).
        file_format: Output format -- "GeoTIFF" (default) or "TFRecord".
        overwrite: If True, overwrite existing files (default False).

    Returns:
        JSON with export status or an error.
    """
    _ensure_initialized()
    ee = _namespace["ee"]
    gil = _namespace["gil"]

    # Look up image
    image = _namespace.get(image_var)
    if image is None:
        return json.dumps({"error": f"Variable {image_var!r} not found in namespace."})
    if not isinstance(image, ee.Image):
        return json.dumps({
            "error": f"Variable {image_var!r} is {type(image).__name__}, not ee.Image.",
        })

    # Look up region (required)
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

    stdout_buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_buf):
            gil.exportToCloudStorageWrapper(
                image, output_name, bucket,
                region, scale, crs, None, output_no_data,
                file_format, {"cloudOptimized": True}, overwrite,
            )
    except Exception as exc:
        return json.dumps({
            "error": f"Export to Cloud Storage failed: {exc}",
            "stdout": stdout_buf.getvalue(),
        })

    return json.dumps({
        "success": True,
        "output_name": output_name,
        "bucket": bucket,
        "scale": scale,
        "crs": crs,
        "file_format": file_format,
        "overwrite": overwrite,
        "stdout": stdout_buf.getvalue().strip(),
        "message": "Export to Cloud Storage task started. Use track_tasks() to monitor progress.",
    })


# ---------------------------------------------------------------------------
# Tool 25: cancel_tasks
# ---------------------------------------------------------------------------

@app.tool()
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
# Tool 26: sample_values
# ---------------------------------------------------------------------------

@app.tool()
def sample_values(
    image_var: str,
    geometry_var: str = "",
    lon: float = None,
    lat: float = None,
    scale: int = 30,
    reducer: str = "first",
) -> str:
    """Sample pixel values from an ee.Image at a point or region.

    Provide either lon/lat coordinates for a point sample, or a geometry
    variable name for a region reduction.

    Args:
        image_var: Name of the ee.Image variable in the REPL namespace.
        geometry_var: Optional name of an ee.Geometry or ee.FeatureCollection
                      variable. Used if lon/lat are not provided.
        lon: Longitude for a point sample.
        lat: Latitude for a point sample.
        scale: Scale in meters for the reduction (default 30).
        reducer: Reducer to use -- "first", "mean", "median", "min", "max",
                 "sum", "stdDev", or "count" (default "first").

    Returns:
        JSON dict of band name -> sampled value.
    """
    _ensure_initialized()
    ee = _namespace["ee"]

    # Look up image
    image = _namespace.get(image_var)
    if image is None:
        return json.dumps({"error": f"Variable {image_var!r} not found in namespace."})
    if not isinstance(image, ee.Image):
        return json.dumps({
            "error": f"Variable {image_var!r} is {type(image).__name__}, not ee.Image.",
        })

    # Determine geometry
    if lon is not None and lat is not None:
        geometry = ee.Geometry.Point([lon, lat])
    elif geometry_var:
        geometry = _namespace.get(geometry_var)
        if geometry is None:
            return json.dumps({"error": f"Variable {geometry_var!r} not found in namespace."})
        if isinstance(geometry, ee.FeatureCollection):
            geometry = geometry.geometry()
        elif not isinstance(geometry, ee.Geometry):
            return json.dumps({
                "error": f"Variable {geometry_var!r} is {type(geometry).__name__}, "
                         "expected ee.Geometry or ee.FeatureCollection.",
            })
    else:
        return json.dumps({
            "error": "Provide either lon/lat coordinates or a geometry_var name.",
        })

    # Map reducer string to ee.Reducer
    reducer_map = {
        "first": ee.Reducer.first(),
        "mean": ee.Reducer.mean(),
        "median": ee.Reducer.median(),
        "min": ee.Reducer.min(),
        "max": ee.Reducer.max(),
        "sum": ee.Reducer.sum(),
        "stdDev": ee.Reducer.stdDev(),
        "count": ee.Reducer.count(),
    }
    ee_reducer = reducer_map.get(reducer)
    if ee_reducer is None:
        return json.dumps({
            "error": f"Unknown reducer: {reducer!r}. "
                     f"Valid: {', '.join(sorted(reducer_map))}",
        })

    try:
        result = image.reduceRegion(
            reducer=ee_reducer,
            geometry=geometry,
            scale=scale,
            maxPixels=1e9,
        ).getInfo()
    except Exception as exc:
        return json.dumps({"error": f"Sample failed: {exc}"})

    return json.dumps({
        "success": True,
        "reducer": reducer,
        "scale": scale,
        "values": result,
    })


# ---------------------------------------------------------------------------
# Tool 27: get_time_series
# ---------------------------------------------------------------------------

# Check for matplotlib at module level
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False


@app.tool()
def get_time_series(
    collection_var: str,
    geometry_var: str = "",
    lon: float = None,
    lat: float = None,
    band: str = "",
    start_date: str = "",
    end_date: str = "",
    scale: int = 30,
    reducer: str = "mean",
):
    """Extract time series of band values from an ImageCollection.

    Reduces each image in the collection over the given geometry and returns
    date-value pairs. If matplotlib is available, also returns a line chart PNG.

    Args:
        collection_var: Name of the ee.ImageCollection variable in the REPL namespace.
        geometry_var: Optional name of an ee.Geometry or ee.FeatureCollection variable.
        lon: Longitude for a point sample (used if geometry_var is empty).
        lat: Latitude for a point sample (used if geometry_var is empty).
        band: Band name to extract. If empty, uses the first band.
        start_date: Optional start date filter (YYYY-MM-DD).
        end_date: Optional end date filter (YYYY-MM-DD).
        scale: Scale in meters for the reduction (default 30).
        reducer: Reducer to use -- "mean", "median", "min", "max", "first",
                 "sum" (default "mean").

    Returns:
        JSON with date-value data (and a PNG chart image if matplotlib is available).
    """
    _ensure_initialized()
    ee = _namespace["ee"]

    # Look up collection
    collection = _namespace.get(collection_var)
    if collection is None:
        return json.dumps({"error": f"Variable {collection_var!r} not found in namespace."})
    if not isinstance(collection, ee.ImageCollection):
        return json.dumps({
            "error": f"Variable {collection_var!r} is {type(collection).__name__}, "
                     "not ee.ImageCollection.",
        })

    # Determine geometry
    if lon is not None and lat is not None:
        geometry = ee.Geometry.Point([lon, lat])
    elif geometry_var:
        geometry = _namespace.get(geometry_var)
        if geometry is None:
            return json.dumps({"error": f"Variable {geometry_var!r} not found in namespace."})
        if isinstance(geometry, ee.FeatureCollection):
            geometry = geometry.geometry()
        elif not isinstance(geometry, ee.Geometry):
            return json.dumps({
                "error": f"Variable {geometry_var!r} is {type(geometry).__name__}, "
                         "expected ee.Geometry or ee.FeatureCollection.",
            })
    else:
        return json.dumps({
            "error": "Provide either lon/lat coordinates or a geometry_var name.",
        })

    # Apply date filters
    if start_date:
        collection = collection.filterDate(start_date, end_date or "2099-01-01")
    elif end_date:
        collection = collection.filterDate("1970-01-01", end_date)

    # Map reducer string
    reducer_map = {
        "first": ee.Reducer.first(),
        "mean": ee.Reducer.mean(),
        "median": ee.Reducer.median(),
        "min": ee.Reducer.min(),
        "max": ee.Reducer.max(),
        "sum": ee.Reducer.sum(),
    }
    ee_reducer = reducer_map.get(reducer)
    if ee_reducer is None:
        return json.dumps({
            "error": f"Unknown reducer: {reducer!r}. "
                     f"Valid: {', '.join(sorted(reducer_map))}",
        })

    # Determine band name
    if not band:
        try:
            band = collection.first().bandNames().get(0).getInfo()
        except Exception as exc:
            return json.dumps({"error": f"Could not determine band name: {exc}"})

    # Select the band and map reduceRegion over each image
    collection = collection.select(band)

    def _extract(img):
        date = img.date().format("YYYY-MM-dd")
        val = img.reduceRegion(
            reducer=ee_reducer, geometry=geometry,
            scale=scale, maxPixels=1e9,
        ).get(band)
        return ee.Feature(None, {"date": date, "value": val})

    try:
        fc = collection.map(_extract)
        data = fc.getInfo()
    except Exception as exc:
        return json.dumps({"error": f"Time series extraction failed: {exc}"})

    # Parse features into date-value list
    series = []
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        series.append({
            "date": props.get("date"),
            "value": props.get("value"),
        })

    # Sort by date
    series.sort(key=lambda x: x.get("date") or "")

    # Filter out null values for charting
    valid_series = [p for p in series if p["value"] is not None and p["date"] is not None]

    # Generate chart if matplotlib is available
    if _HAS_MPL and valid_series and _MCPImage is not None:
        try:
            import datetime as _dt
            dates = [_dt.datetime.strptime(p["date"], "%Y-%m-%d") for p in valid_series]
            values = [p["value"] for p in valid_series]

            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(dates, values, marker=".", markersize=3, linewidth=0.8)
            ax.set_xlabel("Date")
            ax.set_ylabel(band)
            ax.set_title(f"Time Series: {band}")
            fig.autofmt_xdate()
            fig.tight_layout()

            buf = io.BytesIO()
            plt.savefig(buf, format="png", bbox_inches="tight", dpi=100)
            plt.close(fig)
            buf.seek(0)

            return _MCPImage(data=buf.getvalue(), format="png")
        except Exception:
            pass  # Fall through to JSON-only response

    return json.dumps({
        "success": True,
        "band": band,
        "reducer": reducer,
        "scale": scale,
        "count": len(series),
        "series": series,
    })


# ---------------------------------------------------------------------------
# Tool 28: delete_asset
# ---------------------------------------------------------------------------

@app.tool()
def delete_asset(asset_id: str) -> str:
    """Delete a single GEE asset.

    Checks that the asset exists before attempting deletion.
    Only deletes a single asset -- will not recursively delete folders.

    Args:
        asset_id: Full asset path (e.g. "projects/my-project/assets/my_image").

    Returns:
        JSON confirmation or error.
    """
    _ensure_initialized()
    ee = _namespace["ee"]
    import geeViz.assetManagerLib as aml

    if not aml.ee_asset_exists(asset_id):
        return json.dumps({"error": f"Asset not found: {asset_id}"})

    try:
        ee.data.deleteAsset(asset_id)
    except Exception as exc:
        return json.dumps({"error": f"Delete failed: {exc}"})

    return json.dumps({
        "success": True,
        "asset_id": asset_id,
        "message": f"Asset {asset_id} deleted.",
    })


# ---------------------------------------------------------------------------
# Tool 29: copy_asset
# ---------------------------------------------------------------------------

@app.tool()
def copy_asset(source_id: str, dest_id: str, overwrite: bool = False) -> str:
    """Copy a GEE asset to a new location.

    Args:
        source_id: Full path of the source asset.
        dest_id: Full path for the destination asset.
        overwrite: If True and the destination exists, delete it first
                   (default False).

    Returns:
        JSON confirmation or error.
    """
    _ensure_initialized()
    ee = _namespace["ee"]
    import geeViz.assetManagerLib as aml

    if not aml.ee_asset_exists(source_id):
        return json.dumps({"error": f"Source asset not found: {source_id}"})

    if aml.ee_asset_exists(dest_id):
        if overwrite:
            try:
                ee.data.deleteAsset(dest_id)
            except Exception as exc:
                return json.dumps({"error": f"Failed to delete existing dest: {exc}"})
        else:
            return json.dumps({
                "error": f"Destination already exists: {dest_id}. "
                         "Set overwrite=True to replace it.",
            })

    try:
        ee.data.copyAsset(source_id, dest_id)
    except Exception as exc:
        return json.dumps({"error": f"Copy failed: {exc}"})

    return json.dumps({
        "success": True,
        "source_id": source_id,
        "dest_id": dest_id,
        "message": f"Asset copied from {source_id} to {dest_id}.",
    })


# ---------------------------------------------------------------------------
# Tool 30: move_asset
# ---------------------------------------------------------------------------

@app.tool()
def move_asset(source_id: str, dest_id: str, overwrite: bool = False) -> str:
    """Move a GEE asset (copy to destination, then delete source).

    The copy is performed first; the source is only deleted after a
    successful copy.

    Args:
        source_id: Full path of the source asset.
        dest_id: Full path for the destination asset.
        overwrite: If True and the destination exists, delete it first
                   (default False).

    Returns:
        JSON confirmation or error.
    """
    _ensure_initialized()
    ee = _namespace["ee"]
    import geeViz.assetManagerLib as aml

    if not aml.ee_asset_exists(source_id):
        return json.dumps({"error": f"Source asset not found: {source_id}"})

    if aml.ee_asset_exists(dest_id):
        if overwrite:
            try:
                ee.data.deleteAsset(dest_id)
            except Exception as exc:
                return json.dumps({"error": f"Failed to delete existing dest: {exc}"})
        else:
            return json.dumps({
                "error": f"Destination already exists: {dest_id}. "
                         "Set overwrite=True to replace it.",
            })

    # Copy first
    try:
        ee.data.copyAsset(source_id, dest_id)
    except Exception as exc:
        return json.dumps({"error": f"Copy step failed: {exc}"})

    # Delete source only after successful copy
    try:
        ee.data.deleteAsset(source_id)
    except Exception as exc:
        return json.dumps({
            "error": f"Asset copied to {dest_id} but failed to delete source: {exc}",
            "dest_id": dest_id,
        })

    return json.dumps({
        "success": True,
        "source_id": source_id,
        "dest_id": dest_id,
        "message": f"Asset moved from {source_id} to {dest_id}.",
    })


# ---------------------------------------------------------------------------
# Tool 31: create_folder
# ---------------------------------------------------------------------------

@app.tool()
def create_folder(
    folder_path: str,
    folder_type: str = "Folder",
) -> str:
    """Create a GEE folder or ImageCollection.

    Creates intermediate folders recursively if they don't exist.

    Args:
        folder_path: Full asset path for the new folder
                     (e.g. "projects/my-project/assets/my_folder").
        folder_type: "Folder" (default) or "ImageCollection".

    Returns:
        JSON confirmation or error.
    """
    _ensure_initialized()
    import geeViz.assetManagerLib as aml

    if folder_type not in ("Folder", "ImageCollection"):
        return json.dumps({
            "error": f"Invalid folder_type: {folder_type!r}. "
                     "Must be 'Folder' or 'ImageCollection'.",
        })

    stdout_buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_buf):
            if folder_type == "ImageCollection":
                aml.create_image_collection(folder_path)
            else:
                aml.create_asset(folder_path, recursive=True)
    except Exception as exc:
        return json.dumps({
            "error": f"Create failed: {exc}",
            "stdout": stdout_buf.getvalue(),
        })

    return json.dumps({
        "success": True,
        "folder_path": folder_path,
        "folder_type": folder_type,
        "stdout": stdout_buf.getvalue().strip(),
        "message": f"{folder_type} created at {folder_path}.",
    })


# ---------------------------------------------------------------------------
# Tool 32: update_acl
# ---------------------------------------------------------------------------

@app.tool()
def update_acl(
    asset_id: str,
    all_users_can_read: bool = False,
    readers: str = "",
    writers: str = "",
) -> str:
    """Update permissions (ACL) on a GEE asset.

    Uses geeViz's assetManagerLib.updateACL to set the access control list.

    Args:
        asset_id: Full asset path.
        all_users_can_read: If True, the asset is publicly readable
                            (default False).
        readers: Comma-separated email addresses of users with read access.
        writers: Comma-separated email addresses of users with write access.

    Returns:
        JSON confirmation or error.
    """
    _ensure_initialized()
    import geeViz.assetManagerLib as aml

    readers_list = [r.strip() for r in readers.split(",") if r.strip()] if readers else []
    writers_list = [w.strip() for w in writers.split(",") if w.strip()] if writers else []

    stdout_buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_buf):
            aml.updateACL(
                asset_id,
                writers=writers_list,
                all_users_can_read=all_users_can_read,
                readers=readers_list,
            )
    except Exception as exc:
        return json.dumps({
            "error": f"ACL update failed: {exc}",
            "stdout": stdout_buf.getvalue(),
        })

    return json.dumps({
        "success": True,
        "asset_id": asset_id,
        "all_users_can_read": all_users_can_read,
        "readers": readers_list,
        "writers": writers_list,
        "stdout": stdout_buf.getvalue().strip(),
        "message": f"Permissions updated for {asset_id}.",
    })


# ---------------------------------------------------------------------------
# Tool 33: get_collection_info
# ---------------------------------------------------------------------------

@app.tool()
def get_collection_info(
    collection_id: str,
    start_date: str = "",
    end_date: str = "",
    region_var: str = "",
) -> str:
    """Get summary information for an Earth Engine ImageCollection.

    Loads a collection by asset ID (does NOT require a namespace variable),
    applies optional date and region filters, and returns image count,
    date range, band names/types, and spatial extent.

    Args:
        collection_id: Full asset ID of the ImageCollection
                       (e.g. "LANDSAT/LC09/C02/T1_L2").
        start_date: Optional start date filter (YYYY-MM-DD).
        end_date: Optional end date filter (YYYY-MM-DD).
        region_var: Optional name of an ee.Geometry or ee.FeatureCollection
                    variable for spatial filtering.

    Returns:
        JSON with collection statistics.
    """
    _ensure_initialized()
    ee = _namespace["ee"]

    try:
        collection = ee.ImageCollection(collection_id)
    except Exception as exc:
        return json.dumps({"error": f"Failed to load collection: {exc}"})

    # Apply filters
    if start_date:
        collection = collection.filterDate(start_date, end_date or "2099-01-01")
    elif end_date:
        collection = collection.filterDate("1970-01-01", end_date)

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

    result: dict = {"collection_id": collection_id}

    try:
        count = collection.size().getInfo()
        result["image_count"] = count
    except Exception as exc:
        return json.dumps({"error": f"Failed to get collection size: {exc}"})

    if count == 0:
        result["message"] = "Collection is empty (with applied filters)."
        return json.dumps(result)

    # Date range
    try:
        date_range = collection.reduceColumns(
            ee.Reducer.minMax(), ["system:time_start"]
        ).getInfo()
        import datetime as _dt
        min_ms = date_range.get("min")
        max_ms = date_range.get("max")
        if min_ms is not None:
            result["first_date"] = _dt.datetime.utcfromtimestamp(min_ms / 1000).strftime("%Y-%m-%d")
        if max_ms is not None:
            result["last_date"] = _dt.datetime.utcfromtimestamp(max_ms / 1000).strftime("%Y-%m-%d")
    except Exception:
        pass

    # Band info from first image
    try:
        first_info = collection.first().getInfo()
        if first_info and "bands" in first_info:
            bands = []
            for b in first_info["bands"]:
                bands.append({
                    "name": b.get("id", ""),
                    "data_type": b.get("data_type", {}).get("precision", ""),
                    "crs": b.get("crs", ""),
                    "dimensions": b.get("dimensions"),
                    "scale": b.get("crs_transform", [None])[0],
                })
            result["bands"] = bands
    except Exception:
        pass

    return json.dumps(result)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # stdio is standard for Cursor/IDE integration; use streamable-http for HTTP
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        host = os.environ.get("MCP_HOST", "127.0.0.1")
        port = int(os.environ.get("MCP_PORT", "8000"))
        path = os.environ.get("MCP_PATH", "/mcp")
        print(f"MCP server starting at http://{host}:{port}{path}", file=sys.stderr)
        try:
            app.run(transport=transport, host=host, port=port, path=path)
        except TypeError:
            # SDK may not accept host/port/path; use env or defaults
            app.run(transport=transport)
    else:
        app.run(transport=transport)


if __name__ == "__main__":
    # print(inspect_asset("COPERNICUS/S2_SR_HARMONIZED"))
    main()
# %%
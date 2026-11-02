"""A function that turns a dotted string into the live object is an import
the sandbox never sees.

Found 2026-10-26 while checking that ``import inspect`` is refused and
pointed at search_codebase. ``pydoc`` had a redirect hint but was never on
the block list, and under --sandbox:

    pydoc.locate('os').getcwd()                  -> real path
    pkgutil.resolve_name('os').environ           -> 71 variables, API keys among them
    logging.config._resolve('os').getcwd()       -> real path
    pydoc.locate('builtins.open')                -> the real open

The audit hook still refused os.system and subprocess.run, but reading
os.environ raises no audit event. These run the real run_code in a
--sandbox subprocess, the way the agent starts the server, because the
AST checks are skipped entirely without that flag.
"""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

PROBES = {
    "pydoc_locate": "import pydoc\nprint('REACHED', pydoc.locate('os').getcwd())",
    "pkgutil_environ": "import pkgutil\nprint('REACHED', len(pkgutil.resolve_name('os').environ))",
    "logging_config_resolve": "import logging\nprint('REACHED', logging.config._resolve('os').getcwd())",
    "logging_config_import": "from logging.config import _resolve\nprint('REACHED', _resolve('os').getcwd())",
    "aliased_logging": "import logging as L\nprint('REACHED', L.config._resolve('os').getcwd())",
    "dict_config": "import logging.config as lc\nlc.dictConfig({'version': 1})\nprint('REACHED')",
    "locate_builtin_open": "import pydoc\nprint('REACHED', pydoc.locate('builtins.open'))",
    "inspect": "import inspect\nprint('REACHED', inspect.signature(gil.simpleMask))",
    # The other direction: ordinary analysis code still runs.
    "ordinary": "import logging, json, math\nlogging.getLogger('x')\nprint('REACHED', json.dumps({'a': math.pi > 3}))",
}

_HARNESS = textwrap.dedent("""
    import asyncio, json, sys
    sys.argv = ['x', '--sandbox']
    import geeViz.mcp.server as srv
    probes = json.loads(sys.stdin.read())
    fn = getattr(srv.run_code, 'fn', srv.run_code)
    out = {}
    for name, code in probes.items():
        saved = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = srv._TL_STDOUT, srv._TL_STDERR
        try:
            out[name] = json.loads(asyncio.run(fn(code=code, session_id='resolver-' + name)))
        finally:
            sys.stdout, sys.stderr = saved
    # The server replaces sys.stdout with a proxy that sends unregistered
    # threads to stderr.
    sys.__stdout__.write('RESULTS ' + json.dumps({'sandbox': srv._SANDBOX_ENABLED, 'out': out}) + '\\n')
    sys.__stdout__.flush()
""")


@pytest.fixture(scope="module")
def results():
    proc = subprocess.run(
        [sys.executable, "-c", _HARNESS], input=json.dumps(PROBES),
        capture_output=True, text=True, cwd=ROOT, timeout=600,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    line = next((l for l in proc.stdout.splitlines() if l.startswith("RESULTS ")), None)
    assert line, f"harness produced no results:\n{proc.stderr[-3000:]}"
    data = json.loads(line[len("RESULTS "):])
    assert data["sandbox"] is True, "the probes ran without the sandbox"
    return data["out"]


@pytest.mark.parametrize("name", [n for n in PROBES if n != "ordinary"])
def test_a_resolver_is_refused_before_it_runs(results, name):
    out = results[name]
    assert out["success"] is False, f"{name} ran under the sandbox: {out}"
    assert "REACHED" not in (out.get("stdout") or "")
    assert "BLOCKED" in out["error"], f"refused for the wrong reason: {out['error']}"


def test_inspect_is_pointed_at_search_codebase(results):
    err = results["inspect"]["error"]
    assert "search_codebase" in err and err.count("BLOCKED") == 1, err


def test_ordinary_code_still_runs(results):
    out = results["ordinary"]
    assert out["success"] is True, out
    assert out["stdout"] == "REACHED {\"a\": true}\n"

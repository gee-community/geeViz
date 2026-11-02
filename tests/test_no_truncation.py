"""Tool output reaches the model, the user and the logs whole.

A cap added to keep a prompt small (code cut at 2,500 characters) hid a
Map.addTimeLapse call at character 3,028 from every regression check.
These pin the places that used to cut text short without saying so.
"""
import json
import types

import geeViz.mcp.server as srv


def test_the_tool_log_keeps_long_arguments_and_results():
    code = "x = 1\n" * 3000
    srv._log_tool_call("run_code", {"code": code}, result="R" * 9000)
    with open(srv._TOOL_LOG_FILE, encoding="utf-8") as f:
        last = json.loads(f.read().splitlines()[-1])
    assert last["args"]["code"] == code
    assert last["result_preview"] == "R" * 9000


def test_the_tool_log_keeps_long_errors():
    srv._log_tool_call("run_code", {}, error="E" * 9000)
    with open(srv._TOOL_LOG_FILE, encoding="utf-8") as f:
        last = json.loads(f.read().splitlines()[-1])
    assert last["error"] == "E" * 9000


def test_a_module_docstring_is_returned_whole():
    mod = types.ModuleType("long_doc")
    mod.__doc__ = "Intro.\n\n" + "A parameter described at length. " * 60
    out = srv._describe_object(mod, name="long_doc")
    assert len(mod.__doc__) > 1500
    assert out["docstring"].rstrip() == mod.__doc__.rstrip()


def test_map_check_failures_print_the_whole_error():
    src = open(srv.__file__, encoding="utf-8").read()
    code = "\n".join(l.split("#")[0] for l in src.splitlines())
    fails = [l for l in code.splitlines() if "FAIL: {l['name']}" in l]
    assert len(fails) == 2
    assert all("unknown error')}" in l for l in fails)


def _code(rel):
    import os
    path = os.path.join(os.path.dirname(srv.__file__), "..", rel)
    with open(path, encoding="utf-8") as f:
        return "\n".join(l.split("#")[0] for l in f.read().splitlines())


LIBRARY_WITHOUT_CUTS = {
    "geeView.py": ["err[:300]", "orphan_prefixes)[:3]", "band_names[:5]"],
    "outputLib/reports.py": ["(truncated)", "narrative[:200]", "columns[:10]",
                             "errors=\"replace\")[:200]", "max_rows=100"],
    "outputLib/charts.py": ["req_url[:120]", "resp_url[:120]"],
    "inventoryLib.py": ["canonical_labels\", [])[:10]"],
    "mcp/run_tests.py": ["str(result)[:", "str(e)[:", "e[:100]"],
    "mcp/hard_tests_v2.py": ["str(result)[:", "str(e)[:", "tb[:", "outputs)[:", "e[:200]"],
}


def test_library_sources_cut_nothing():
    found = [f"{rel}: {n}" for rel, needles in LIBRARY_WITHOUT_CUTS.items()
             for n in needles if n in _code(rel)]
    assert not found, found


def test_a_report_table_keeps_every_row():
    import pandas as pd
    from geeViz.outputLib.reports import Report
    df = pd.DataFrame({"year": range(200), "value": range(200)})
    table = Report._df_to_table_str(None, df)
    assert "truncated" not in table
    assert len(table.splitlines()) == 202


SERVER_WITHOUT_CUTS = [
    "stdout_val[:", "obj[:200]", "obj[:20]", "too large after cleaning", "repr(cleaned)[:",
    "repr(obj)[:", "members[:200]", "keys())[:100]", "obj[:5]", "max_size",
    "<truncated", "_CAP", "assets[:500]", "r[:2000]", ".strip()[:100]",
]


def test_the_mcp_server_returns_tool_output_whole():
    code = _code("mcp/server.py")
    found = [n for n in SERVER_WITHOUT_CUTS if n in code]
    assert not found, found


def test_a_large_object_is_described_whole():
    big = {f"k{i}": i for i in range(5000)}
    assert srv._describe_object(big, name="big")["value"] == big
    lst = list(range(500))
    assert srv._describe_object(lst, name="lst")["value"] == lst
    mod = types.ModuleType("many")
    for i in range(300):
        setattr(mod, f"f{i}", i)
    assert len(srv._describe_object(mod, name="many")["public_members"]) == 300


def test_printed_tables_and_arrays_are_not_elided(monkeypatch):
    import asyncio
    import sys
    # The server installs its thread-local proxy as sys.stdout; pytest's
    # capture replaces it, so put it back for the call.
    monkeypatch.setattr(sys, "stdout", srv._TL_STDOUT)
    monkeypatch.setattr(sys, "stderr", srv._TL_STDERR)
    run = getattr(srv.run_code, "fn", srv.run_code)
    code = ("df = pd.DataFrame({'year': range(1900, 2000), 'v': range(100)})\n"
            "print(df)\nprint(np.arange(5000))\n")
    # Twice: numpy keeps print options per context, and the second run in a
    # session is where a once-per-session setting was lost.
    for _ in range(2):
        out = asyncio.run(run(code=code, session_id="no-elide-test"))
        stdout = (out if isinstance(out, dict) else __import__("json").loads(out))["stdout"]
        assert "1950" in stdout and "1999" in stdout
        assert "4999" in stdout and "2500" in stdout
        assert "..." not in stdout


def test_a_deeply_nested_result_comes_back_whole():
    # A getInfo() of a FeatureCollection nests deeper than five levels
    # (features, geometry, coordinates, rings, points); the cleaner used
    # to replace anything past that with "<nested too deep>".
    deep = {"a": [{"b": [[[[[[1, 2]]]]]]}]}
    assert srv._save_and_clean_result(deep) == deep
    loop = []
    loop.append(loop)
    assert srv._save_and_clean_result(loop) == ["<contains itself>"]

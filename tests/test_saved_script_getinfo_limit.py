"""A saved script is not one model turn: the getInfo cap counts per chat block.

run_code blocks more than 3 separate .getInfo() calls in one call, to make
the model batch them. The agent's /scripts page joins every block of a chat
into one run, so script c1c51f24fdc3 (15 blocks, each within the cap) was
refused with "BLOCKED: 11 separate .getInfo() calls in one block".

The script runner now calls run_saved_script, which skips that one
whole-code count. It is not an MCP tool, so the model cannot use it, and
every check on a single construct still applies.
"""
import asyncio
import json

import geeViz.mcp.server as srv

FIVE = "\n".join(f"x{k} = ee.Number({k}).getInfo()" for k in range(5)) + "\nprint(x4)"


def test_run_code_still_blocks_many_getinfo_calls():
    out = json.loads(asyncio.run(srv.run_code(FIVE, session_id="saved-script-chat")))
    assert out["success"] is False
    assert "5 separate .getInfo() calls" in out["error"]


def test_a_saved_script_may_make_them():
    out = json.loads(asyncio.run(srv.run_saved_script(code=FIVE, session_id="saved-script-run")))
    assert "separate .getInfo() calls" not in (out.get("error") or "")
    assert out["success"] is True


def test_a_saved_script_still_gets_the_per_construct_blocks():
    code = "for i in range(3):\n    print(ee.Number(i).getInfo())"
    out = json.loads(asyncio.run(srv.run_saved_script(code=code, session_id="saved-script-loop")))
    assert out["success"] is False
    assert "inside a loop" in out["error"]


def test_the_exemption_does_not_outlive_the_script():
    asyncio.run(srv.run_saved_script(code="x = 1", session_id="saved-script-reset"))
    assert srv._SAVED_SCRIPT_RUN.get() is False
    assert any("separate .getInfo() calls" in w for w in srv._check_code_patterns(FIVE))


def test_a_saved_script_gets_no_typed_data_note():
    """The note asks the model to name its source; on the scripts page a
    person reads it as noise under their own output."""
    table = "x = [" + ", ".join(str(k * k + 0.5) for k in range(25)) + "]"
    out = json.loads(asyncio.run(srv.run_saved_script(code=table, session_id="saved-script-note")))
    assert out["success"] is True
    assert "NOTE:" not in (out.get("stdout") or "")
    chat = json.loads(asyncio.run(srv.run_code(table, session_id="saved-script-note-chat")))
    assert "NOTE: this code types 25 data values" in chat["stdout"]


def test_the_model_cannot_reach_it():
    tools = asyncio.run(srv.app.list_tools())
    names = {t.name for t in tools}
    assert "run_code" in names and "run_saved_script" not in names


def test_the_agent_script_runner_uses_it():
    from pathlib import Path
    import re
    src = (Path(srv.__file__).resolve().parents[2] / "geeViz_agent" / "run_ui.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    assert re.search(r'getattr\(_mcp_server, "run_saved_script", None\)', code)

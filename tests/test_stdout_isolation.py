"""A tool that captures its own prints must not take other sessions' output.

``run_code`` routes each exec thread's prints to that call's buffer through
the thread-local proxy installed as ``sys.stdout``. ``map_control`` (and a
few other tools) used to capture their prints by assigning ``sys.stdout``
process-wide, so a ``run_code`` in another session that printed while a map
check ran lost that output to the other session's map result: its own
reply came back ``success`` with empty stdout.
"""
import ast
import json
import threading
import types
from pathlib import Path

import geeViz.mcp.server as srv

ROOT = Path(srv.__file__).resolve().parent


def _print(text):
    # what print() does in the server, where sys.stdout is the proxy (under
    # pytest sys.stdout is pytest's capture stream)
    srv._TL_STDOUT.write(text + "\n")


def _fake_session(tmp_path):
    return types.SimpleNamespace(
        namespace={"Map": object()},
        stdout_stream_file=str(tmp_path / ".stdout_stream"),
    )


def test_map_control_leaves_registered_threads_output_alone(tmp_path, monkeypatch):
    other_buf = __import__("io").StringIO()

    def other_session_run_code():
        srv._TL_STDOUT.register(other_buf)
        try:
            _print("other-session-output")
        finally:
            srv._TL_STDOUT.unregister()

    def fake_inner(Map, act, sess, open_browser, filename, _mc_stdout):
        _print("map-check-output")
        # map validation prints from pool threads (auto_viz warnings)
        w = threading.Thread(target=lambda: _print("pool-worker-output"))
        w.start(); w.join()
        t = threading.Thread(target=other_session_run_code)
        t.start(); t.join()
        return json.dumps({"success": True})

    sess = _fake_session(tmp_path)
    monkeypatch.setattr(srv, "_ensure_initialized", lambda session_id=None: sess)
    monkeypatch.setattr(srv, "_map_control_inner", fake_inner)

    before = srv.sys.stdout
    out = json.loads(srv.map_control(action="test_layers"))

    assert other_buf.getvalue() == "other-session-output\n"
    assert "other-session-output" not in out["stdout"]
    assert "map-check-output" in out["stdout"]
    assert "pool-worker-output" in out["stdout"]
    assert srv.sys.stdout is before


def test_capture_nests_and_restores():
    a, b = __import__("io").StringIO(), __import__("io").StringIO()
    with srv._TL_STDOUT.capture_unregistered(a):
        _print("one")
        with srv._TL_STDOUT.capture_unregistered(b):
            _print("two")
        _print("three")
    assert a.getvalue() == "one\nthree\n"
    assert b.getvalue() == "two\n"
    assert srv._TL_STDOUT._resolve() is srv.sys.__stderr__


def test_no_tool_swaps_sys_stdout_process_wide():
    """AST, not text: the comments above the proxy name the old pattern."""
    tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8"))
    redirects, assigns = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if name in ("redirect_stdout", "redirect_stderr"):
                redirects.append(node.lineno)
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if (isinstance(t, ast.Attribute) and t.attr in ("stdout", "stderr")
                        and isinstance(t.value, ast.Name) and t.value.id == "sys"):
                    assigns.append(node.lineno)
    assert redirects == [], f"process-wide redirect at lines {redirects}"
    # the two install lines of the proxy itself
    assert len(assigns) == 2, f"sys.stdout/stderr assigned at lines {assigns}"

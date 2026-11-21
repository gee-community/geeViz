"""The MCP server keeps one session's slow tool from stalling another's.

FastMCP runs a SYNC tool inline on its one event loop. Every geeViz tool
but run_code was sync, so a slow one (an Earth Engine metadata lookup, a
map build, an FIA estimate) froze every other session's tool calls and
the agent's per-step list_tools. In a 50-session comparison run,
map_control took a median of 13 s and inspect_asset 14 s; alone they
take ~1 s. Sync tools now run on worker threads, state-touching tools
take turns within a session, and run_code wakes the moment its code
finishes instead of on a once-a-second poll.
"""
import asyncio
import inspect
import io
import json
import threading
import time

import pytest

import geeViz.mcp.server as srv

SLOW = 0.6


def _tm():
    return srv.app._tool_manager


@pytest.fixture
def dummy_tools(monkeypatch):
    """Register throwaway sync tools on the real app, and remove them after."""
    names = []

    def register(fn):
        srv.app.tool()(fn)
        names.append(fn.__name__)
        return _tm()._tools[fn.__name__].fn

    yield register
    for n in names:
        _tm()._tools.pop(n, None)


# ── sync tools run off the event loop ───────────────────────────────────

def test_every_sync_tool_is_registered_with_an_async_front():
    tools = _tm()._tools
    assert "inspect_asset" in tools and "map_control" in tools
    for name, tool in tools.items():
        assert tool.is_async, f"{name} would run on the event loop"


def test_module_names_stay_sync_for_in_process_callers():
    for name in ("inspect_asset", "search_codebase", "map_control", "save_session"):
        fn = getattr(srv, name)
        assert not inspect.iscoroutinefunction(fn), name


def test_registered_tools_keep_their_parameters():
    """FastMCP builds each schema from the signature, through the wrapper."""
    params = _tm()._tools["inspect_asset"].parameters["properties"]
    assert {"asset_id", "start_date", "end_date", "region_var"} <= set(params)


def test_a_slow_sync_tool_does_not_hold_up_another(dummy_tools):
    def zz_slow_lookup(session_id: str = None) -> str:
        time.sleep(SLOW)
        return "slow"

    def zz_quick_lookup(session_id: str = None) -> str:
        return "quick"

    slow = dummy_tools(zz_slow_lookup)
    quick = dummy_tools(zz_quick_lookup)

    async def main():
        t0 = time.perf_counter()
        slow_task = asyncio.ensure_future(slow(session_id="a"))
        await asyncio.sleep(0.05)              # the slow one is under way
        assert await quick(session_id="b") == "quick"
        quick_done = time.perf_counter() - t0
        assert await slow_task == "slow"
        return quick_done

    assert asyncio.run(main()) < SLOW / 2


def test_attribution_context_reaches_the_worker_thread(dummy_tools):
    from geeViz.eeAuth.client import CURRENT_USER_EMAIL

    def zz_whoami(session_id: str = None) -> str:
        return CURRENT_USER_EMAIL.get() or ""

    fn = dummy_tools(zz_whoami)

    async def main():
        CURRENT_USER_EMAIL.set("someone@example.com")
        return await fn()

    assert asyncio.run(main()) == "someone@example.com"


# ── state-touching tools take turns within a session ────────────────────

def _timed_pair(fn, sid_a, sid_b):
    async def main():
        t0 = time.perf_counter()
        await asyncio.gather(fn(session_id=sid_a), fn(session_id=sid_b))
        return time.perf_counter() - t0
    return asyncio.run(main())


def test_state_tools_in_one_session_run_one_at_a_time(dummy_tools, monkeypatch):
    def zz_map_step(session_id: str = None) -> str:
        time.sleep(SLOW)
        return "ok"

    monkeypatch.setattr(srv, "_SESSION_SERIAL_TOOLS",
                        srv._SESSION_SERIAL_TOOLS | {"zz_map_step"})
    fn = dummy_tools(zz_map_step)
    assert _timed_pair(fn, "same", "same") >= 2 * SLOW * 0.95
    assert _timed_pair(fn, "one", "other") < 1.6 * SLOW


def test_lookups_in_one_session_run_in_parallel(dummy_tools):
    def zz_lookup_step(session_id: str = None) -> str:
        time.sleep(SLOW)
        return "ok"

    fn = dummy_tools(zz_lookup_step)
    assert _timed_pair(fn, "same", "same") < 1.6 * SLOW


def test_the_state_tools_are_the_ones_that_touch_a_session():
    assert {"run_code", "map_control", "save_session", "view_output",
            "export_image"} <= srv._SESSION_SERIAL_TOOLS
    assert "inspect_asset" not in srv._SESSION_SERIAL_TOOLS
    assert "search_codebase" not in srv._SESSION_SERIAL_TOOLS


# ── captured output stays with its own call ─────────────────────────────

def _print(text):
    srv._TL_STDOUT.write(text + "\n")


def test_two_calls_capturing_at_once_keep_their_own_output():
    bufs = {"a": io.StringIO(), "b": io.StringIO()}
    both_in = threading.Barrier(2)

    def call(name):
        with srv._TL_STDOUT.capture_unregistered(bufs[name]):
            both_in.wait()                    # both captures open together
            _print(f"from-{name}")
            w = threading.Thread(target=lambda: _print(f"pool-{name}"))
            w.start(); w.join()
            both_in.wait()

    ts = [threading.Thread(target=call, args=(n,)) for n in "ab"]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert bufs["a"].getvalue() == "from-a\npool-a\n"
    assert bufs["b"].getvalue() == "from-b\npool-b\n"


def test_a_thread_that_outlives_its_capture_stops_writing_into_it():
    buf = io.StringIO()
    go = threading.Event()
    done = threading.Event()

    def late():
        go.wait()
        _print("too-late")
        done.set()

    with srv._TL_STDOUT.capture_unregistered(buf):
        t = threading.Thread(target=late)
        t.start()
    go.set(); done.wait(5); t.join()
    assert "too-late" not in buf.getvalue()


def test_a_thread_started_elsewhere_is_not_captured():
    buf = io.StringIO()
    ready = threading.Event()
    go = threading.Event()

    def bystander():
        ready.set()
        go.wait()
        _print("bystander")

    t = threading.Thread(target=bystander)      # started outside the capture
    t.start()
    ready.wait()
    with srv._TL_STDOUT.capture_unregistered(buf):
        go.set()
        t.join()
    assert buf.getvalue() == ""


# ── run_code returns when the code does ─────────────────────────────────

def test_run_code_returns_without_waiting_for_a_poll():
    sid = "concurrency-run-code"
    asyncio.run(srv.run_code("x = 1", session_id=sid))      # warm the session
    t0 = time.perf_counter()
    out = json.loads(asyncio.run(srv.run_code("y = 2", session_id=sid)))
    took = time.perf_counter() - t0
    assert out.get("success") is not False, out
    # The old loop slept a whole second before its first look.
    assert took < 0.5, took

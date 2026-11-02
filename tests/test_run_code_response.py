"""What run_code returns is what the model reads, every call, so it carries
only what the model can use.

Measured on 45 days of prod tool calls (2026-10-26): of the characters
run_code returned, 57% was the model's own code echoed back, 4% a local
script path, and an error was mostly Earth Engine and Google client
frames. One error alone was 2.8 MB, because pd.read_json reported the
whole GeoJSON string it was given as a "file name too long".

Nothing printed is cut: output stays whole, and only a repeat of
something the model already has is referred to instead of repeated.
"""
import asyncio
import contextlib
import json
import sys
import textwrap


import geeViz.mcp.server as srv


@contextlib.contextmanager
def _through_the_server_proxy():
    # run_code captures prints through the thread-local proxy the server
    # installs as sys.stdout. pytest installs its own capture at the start
    # of each test's call phase, so a fixture cannot put the proxy back.
    saved = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = srv._TL_STDOUT, srv._TL_STDERR
    try:
        yield
    finally:
        sys.stdout, sys.stderr = saved


def _run(code, sid):
    run = getattr(srv.run_code, "fn", srv.run_code)
    with _through_the_server_proxy():
        return json.loads(asyncio.run(run(code=textwrap.dedent(code), session_id=sid)))


def _saved(code, sid):
    with _through_the_server_proxy():
        return json.loads(asyncio.run(srv.run_saved_script(code=textwrap.dedent(code), session_id=sid)))


# --- what a successful call returns ------------------------------------------

def test_a_success_returns_output_not_the_code():
    out = _run("x = 2\nprint('hello', x)", "rc-shape-ok")
    assert out["success"] is True
    assert out["stdout"] == "hello 2\n"
    for gone in ("code", "error", "result"):
        assert gone not in out, f"{gone} is back in the response: {out}"


def test_a_value_is_returned_when_there_is_one():
    out = _run("1 + 2", "rc-shape-result")
    assert out["result"] == 3


def test_a_success_names_the_history_script():
    # A client on the same machine (Claude Code, an IDE) opens it.
    sid = "rc-shape-history"
    out = _run("kept_in_history = 1", sid)
    path = out["script_path"]
    assert path == srv._get_session(sid).current_script_path
    with open(path, encoding="utf-8") as fh:
        assert "kept_in_history = 1" in fh.read()


# --- what a failed call returns ----------------------------------------------

def test_an_error_names_the_line_and_keeps_the_message():
    out = _run("""\
        a = 1
        b = {}['missing_key']
        """, "rc-shape-err")
    assert out["success"] is False
    err = out["error"]
    assert "line 2: b = {}['missing_key']" in err, err
    assert "KeyError: 'missing_key'" in err
    assert "Traceback (most recent call last)" not in err
    assert "server.py" not in err, "the server's own frames are not the model's"


def test_an_error_inside_a_function_shows_each_line_of_the_model_code():
    out = _run("""\
        def area(d):
            return d['acres']
        area({})
        """, "rc-shape-fn")
    err = out["error"]
    assert "line 3: area({})" in err and "line 2 (in area): return d['acres']" in err, err


def test_a_function_from_an_earlier_call_is_not_given_this_call_source():
    # Every block compiles as "<mcp>", so a line number from an earlier
    # block would pick the wrong line out of this one.
    sid = "rc-shape-earlier"
    _run("def boom():\n    return 1 / 0\n", sid)
    out = _run("x = 5\nboom()\n", sid)
    err = out["error"]
    assert "line 2: boom()" in err
    assert "line 2 of boom(), defined in an earlier call" in err, err
    assert "x = 5" not in err


def test_an_earth_engine_error_is_said_once_without_client_frames():
    out = _run("ee.Image('NOT/AN/ASSET').bandNames().getInfo()", "rc-shape-ee")
    err = out["error"]
    assert "Image asset 'NOT/AN/ASSET' not found" in err, err
    assert err.count("not found") == 1, "the HttpError repeated the EEException"
    assert "googleapiclient" not in err and "ee/data.py" not in err.replace("\\", "/")


def test_an_error_inside_geeviz_says_where():
    out = _run("gil.getUTMEpsg(None)", "rc-shape-geeviz")
    assert out["success"] is False
    assert "in geeViz/getImagesLib.py, line" in out["error"].replace("\\", "/"), out["error"]


def test_a_long_message_is_kept_whole():
    out = _run("raise ValueError('E' * 9000)", "rc-shape-long")
    assert "E" * 9000 in out["error"]


def test_an_error_repeating_the_input_names_it_instead():
    # pd.read_csv given a long string reports it whole as a bad file name.
    out = _run("""\
        s = 'x' * 5000 + '.csv'
        pd.read_csv(s)
        """, "rc-shape-echo")
    err = out["error"]
    assert "x" * 5000 not in err
    assert "<the 5,004-character value of s in your code>" in err, err


def test_a_syntax_error_shows_the_line():
    out = _run("x = (1,\n", "rc-shape-syntax")
    assert "SyntaxError" in out["error"] and "x = (1," in out["error"]


def test_a_blocked_call_says_why_once():
    out = _run("""\
        for i in range(3):
            print(ee.Number(i).getInfo())
        """, "rc-shape-blocked")
    assert out["success"] is False
    assert out["error"].count("BLOCKED: .getInfo() inside a loop") == 1
    assert "stderr" not in out


# --- printed output ----------------------------------------------------------

def test_printing_an_earth_engine_object_says_it_is_not_computed():
    out = _run("print(ee.Image(1).add(2))\nprint(ee.Number(3).getInfo())", "rc-shape-eeprint")
    assert "functionInvocationValue" not in out["stdout"]
    assert "<ee.Image: not computed yet" in out["stdout"]
    assert out["stdout"].rstrip().endswith("3")


def test_a_long_value_printed_again_is_shown_once():
    out = _run("""\
        crs = 'PROJCS[' + 'A' * 400 + ']'
        print({'b1': {'crs': crs}, 'b2': {'crs': crs}, 'b3': {'crs': crs}})
        """, "rc-shape-repeat")
    assert out["stdout"].count("A" * 400) == 1
    assert out["stdout"].count("<same as above>") == 2


def test_a_long_value_printed_once_is_whole():
    out = _run("print(repr('Q' * 5000))", "rc-shape-once")
    assert "Q" * 5000 in out["stdout"]


# --- a saved script is read by a person, not the model -----------------------

def test_a_saved_script_keeps_the_full_traceback_and_output():
    out = _saved("""\
        print(ee.Image(1))
        {}['k']
        """, "rc-shape-saved")
    assert "Traceback (most recent call last)" in out["error"]
    assert "functionInvocationValue" in out["stdout"] or "constantValue" in out["stdout"]

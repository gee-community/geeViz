"""A refused run_code block ran nothing, and the refusal says so by name.

Seen in prod (daily review 2026-10-28): after a block was refused for its
.getInfo() calls, the model's next block used names the refused block
would have assigned (a pixel-area image, a scale, a summary table) and
failed with NameError, four times in two sessions. The refusal said
why the block was refused but not that none of it ran.
"""
import asyncio
import contextlib
import json
import sys
import textwrap

import geeViz.mcp.server as srv


@contextlib.contextmanager
def _through_the_server_proxy():
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


_REFUSED = """\
    scale = 60
    px_area = ee.Image.pixelArea()
    def per_class(img):
        return img
    import json as js
    for row in range(2):
        rows = row
    a = ee.Number(1).getInfo()
    b = ee.Number(2).getInfo()
    c = ee.Number(3).getInfo()
    d = ee.Number(4).getInfo()
    """


def test_a_refused_block_names_what_it_did_not_define():
    out = _run(_REFUSED, "blocked-names-new")
    assert out["success"] is False
    err = out["error"]
    assert "BLOCKED:" in err
    assert "Nothing in this block ran" in err, err
    for name in ("scale", "px_area", "per_class", "js", "row", "rows", "a", "d"):
        assert f"`{name}`" in err, f"{name} missing from: {err}"


def test_a_name_already_defined_is_said_to_keep_its_earlier_value():
    sid = "blocked-names-earlier"
    assert _run("scale = 30", sid)["success"] is True
    err = _run(_REFUSED, sid)["error"]
    assert "Still holding values from an earlier block, not this one: `scale`" in err, err
    assert "Not defined: `px_area`" in err, err
    # The refused block's value never replaced the earlier one.
    assert _run("print(scale)", sid)["stdout"].strip() == "30"


def test_a_refused_block_that_assigns_nothing_says_only_why():
    out = _run("""\
        print(ee.Number(1).getInfo())
        print(ee.Number(2).getInfo())
        print(ee.Number(3).getInfo())
        print(ee.Number(4).getInfo())
        """, "blocked-names-none")
    err = out["error"]
    assert "Nothing in this block ran" in err
    assert "Not defined" not in err and "earlier block" not in err


def test_the_next_block_is_told_to_fix_the_refusal_not_resend_it():
    err = _run(_REFUSED, "blocked-names-fix")["error"]
    assert "with the cause of the refusal fixed" in err, err


def test_a_deeply_nested_refused_block_is_still_refused_cleanly():
    # Nested past the recursion limit of a recursive walk, not of ast.parse.
    terms = " + ".join(["ee.Number(1).getInfo()"] * 1200)
    out = _run(f"x = {terms}\n", "blocked-names-deep")
    assert out["success"] is False
    assert "BLOCKED:" in out["error"] and "Not defined: `x`" in out["error"]


def test_names_from_except_and_match_are_counted():
    names = srv._names_a_block_assigns(
        "try:\n    pass\nexcept Exception as err:\n    pass\n"
        "match v:\n    case {'k': kk, **rest}:\n        pass\n"
        "    case [*tail]:\n        pass\n")
    for name in ("err", "kk", "rest", "tail"):
        assert name in names, names


def test_a_refused_import_is_not_named_as_something_to_assign(monkeypatch):
    # Telling the model to assign `urllib` again invites the same import.
    monkeypatch.setattr(srv, "_SANDBOX_ENABLED", True)
    names = srv._names_a_block_assigns(
        "import urllib.request\nfrom socket import socket\nimport json\nresp = 1\n")
    assert names == ["json", "resp"], names

"""esriLib is deprecated and delegates to georest.

georest is the maintained implementation of everything in this module
that talks to an Esri REST endpoint — same function names, compatible
signatures, and stdlib-only, so depending on it costs an install
nothing. It also does considerably more than esriLib ever did.

What this file guards is the part that is easy to get wrong: delegating
must not quietly change what callers see. A deprecated module people
already depend on has to keep raising what it documented, keep its
signatures, and say once — not per call — that it has moved.
"""
import inspect
import warnings

import pytest

import geeViz.esriLib as el


# ── it delegates rather than reimplementing ───────────────────────────

def test_georest_is_a_declared_dependency():
    """A delegation to a package that is not installed is an ImportError
    at the worst moment. It has to be in install_requires, not a hopeful
    import."""
    import pathlib
    # Walk up rather than counting parents: geeViz is installed into the
    # venvs as a SYMLINK to this tree, so the depth of __file__ depends
    # on which interpreter is running the test.
    here = pathlib.Path(el.__file__).resolve()
    for parent in here.parents:
        cand = parent / "setup.py"
        if cand.exists():
            setup = cand.read_text(encoding="utf-8")
            break
    else:
        pytest.skip("setup.py not found above the installed geeViz")
    i = setup.index("install_requires=[")
    j = setup.index("]", i)
    assert "georest" in setup[i:j], "georest is not declared in install_requires"


def test_georest_imports_and_has_what_we_delegate_to():
    from georest.esri import portal
    assert callable(portal.searchPortal)
    assert callable(portal.getServiceMetadata)


@pytest.mark.parametrize("name,target", [
    ("searchPortal", "searchPortal"),
    ("getServiceMetadata", "getServiceMetadata"),
])
def test_the_body_delegates(name, target):
    """Not merely that the function still exists — that the REST work
    happens in georest now. A copy left behind here is a copy that
    drifts."""
    src = inspect.getsource(getattr(el, name))
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.strip().startswith("#"))
    assert "georest" in code, f"{name} does not delegate"
    assert f"_gp.{target}(" in code


def test_the_signatures_still_match_georest():
    """The migration note tells people the change is the import line.
    That has to be true, or the note is worse than no note."""
    from georest.esri import portal

    for name in ("searchPortal", "getServiceMetadata"):
        ours = inspect.signature(getattr(el, name)).parameters
        theirs = inspect.signature(getattr(portal, name)).parameters
        missing = set(ours) - set(theirs)
        assert not missing, (
            f"esriLib.{name} accepts {missing} which georest does not — "
            f"callers following the migration note would break")


# ── it says so, once ──────────────────────────────────────────────────

def test_calling_it_warns():
    el._WARNED.clear()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            el.getServiceMetadata("https://example.invalid/ImageServer")
        except Exception:
            pass
    msgs = [str(x.message) for x in w
            if issubclass(x.category, DeprecationWarning)]
    assert msgs, "no DeprecationWarning raised"
    assert "georest" in msgs[0], "the warning does not name the replacement"


def test_it_warns_once_not_once_per_call():
    """A deprecation is a message to whoever reads the code. A loop over
    500 services should not pay for it 500 times, and nobody reads the
    500th copy."""
    el._WARNED.clear()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        for _ in range(5):
            try:
                el.getServiceMetadata("https://example.invalid/ImageServer")
            except Exception:
                pass
    msgs = [x for x in w if issubclass(x.category, DeprecationWarning)]
    assert len(msgs) == 1, f"warned {len(msgs)} times for 5 calls"


def test_the_module_docstring_names_the_replacement():
    """Someone landing on this module from an old example needs to be
    told where it went, in the first thing they read."""
    doc = el.__doc__ or ""
    assert "DEPRECATED" in doc.upper()
    assert "georest" in doc


# ── delegating must not change what callers catch ─────────────────────

def test_an_unreachable_service_still_raises_ConnectionError():
    """georest reports this as RuntimeError. esriLib has always
    documented and raised ConnectionError, and callers catch that — so
    the boundary translates rather than rewriting the contract of a
    module people already depend on.
    """
    import urllib.error
    from unittest.mock import patch

    with patch("urllib.request.urlopen",
               side_effect=urllib.error.URLError("unreachable")):
        with pytest.raises(ConnectionError):
            el.getServiceMetadata("https://unreachable.example.com/ImageServer")


def test_a_non_json_body_is_still_a_ValueError():
    """The other documented failure, and a different meaning — it must
    not get flattened into the network case."""
    assert "ValueError" in (el._fetch_json.__doc__ or "")


# ── the map helpers stay here ─────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "addEsriImageService", "addEsriMapService",
    "addEsriFeatureService", "addEsriService",
])
def test_the_map_helpers_are_not_going_to_georest(name):
    """They add layers to a geeViz Map, which is geeViz's concern and
    not a REST client's. They stay callable here and as Map.addEsri*."""
    assert callable(getattr(el, name))


def test_the_docstring_says_where_the_map_helpers_stand():
    """Otherwise 'esriLib is deprecated' reads as 'Map.addEsri* is going
    away', which is not true and would send people rewriting working
    code."""
    doc = el.__doc__ or ""
    assert "addEsri" in doc




def _body_code(fn):
    """A function's executable source: no comments, NO DOCSTRING.

    The docstrings here describe the REST work in the very words these
    assertions look for -- "returnCountOnly=true pre-flight",
    "/tile/{z}/{y}/{x}". Stripping only ``#`` lines leaves them, and
    the first version of these tests failed against correct code for
    exactly that reason. Comments are stripped too, per the standing
    hazard in this repo: source-grepping tests have repeatedly matched
    their own explanation and passed vacuously.
    """
    import ast, textwrap
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    fn_node = tree.body[0]
    body = fn_node.body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    return chr(10).join(ast.unparse(n) for n in body)

# ── the shim is a patch over georest, not a fork of it ────────────────
#
# Everything below pins the second half of the migration: esriLib keeps
# only what is geeViz's (a Map to add layers to, an SSRF policy) and
# hands every REST and parsing concern to georest. Each of these was a
# byte-identical copy before, which is the shape that gets a fix in one
# place and not the other.


@pytest.mark.parametrize("name,target", [
    ("_resolve_portal", "_resolve_portal"),
    ("_detect_service_type", "_detect_service_type"),
    ("_resolve_url", "_resolve_url"),
])
def test_the_private_helpers_delegate_too(name, target):
    src = inspect.getsource(getattr(el, name))
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.strip().startswith("#"))
    assert "georest" in code, f"{name} still has its own copy"
    assert f"_gp.{target}(" in code


def test_portals_is_georests_dict_not_a_copy():
    """It is documented as editable at runtime, and the lookup now
    happens inside georest. A copy would accept
    ``esriLib.PORTALS['x'] = ...`` and then ignore it -- the worst kind
    of wrong, because the assignment appears to work."""
    from georest.esri import portal
    assert el.PORTALS is portal.PORTALS

    el.PORTALS["__probe__"] = "https://probe.example"
    try:
        assert el._resolve_portal("__probe__") == "https://probe.example", (
            "a portal added through esriLib is not seen by the resolver")
    finally:
        el.PORTALS.pop("__probe__", None)


def test_the_feature_query_is_georests():
    """The count pre-flight, the spatial filter, the overflow guard and
    the GeoJSON fetch were ~70 lines here and are one call now."""
    code = _body_code(el.addEsriFeatureService)
    assert "_gs.queryFeatureService(" in code
    assert "returnCountOnly" not in code, "the pre-flight was rebuilt here"
    assert "urlopen" not in code


def test_the_tile_template_is_georests():
    code = _body_code(el.addEsriImageService)
    assert "_gs.getImageServiceTileUrl(" in code
    assert "/tile/{z}" not in code, "the template was rebuilt here"


def test_the_ssrf_guard_survives_delegation():
    """geeViz's policy, not georest's -- and it used to be reached only
    through _fetch_json. Calling georest directly skips that path, so
    the guard has to be applied at the new boundary, or delegation
    quietly removes a security check.

    Asserted on the EXCEPTION, not on "nothing hit the network": this
    function imports geeViz.geeView, which legitimately talks to the
    local Earth Engine proxy. A first draft patched urlopen and counted
    calls, and caught that traffic instead -- a test that fails on
    correct code for a reason that has nothing to do with SSRF.
    """
    from geeViz._ssrf import BlockedAddressError

    for blocked in ("http://169.254.169.254/FeatureServer/0",
                    "http://127.0.0.1/FeatureServer/0",
                    "http://[::1]/FeatureServer/0"):
        with pytest.raises(BlockedAddressError):
            el.addEsriFeatureService(blocked)


def test_the_guard_runs_before_georest_is_called():
    """Order matters: georest has no SSRF policy, so the check has to
    happen on this side of the call rather than inside it."""
    code = _body_code(el.addEsriFeatureService)
    assert "_check_url" in code, "the SSRF guard is gone from this path"
    assert code.index("_check_url") < code.index("_gs.queryFeatureService"), (
        "the request is built before the address is checked")

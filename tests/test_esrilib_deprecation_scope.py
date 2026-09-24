"""Only the functions georest replaces are deprecated, not the whole surface.

``geeViz.esriLib`` is deprecated as a module, but not uniformly, and the
distinction is load-bearing:

* ``searchPortal`` / ``getServiceMetadata`` have a direct georest
  equivalent. Calling them SHOULD warn and name it.
* the ``addEsri*Service`` helpers do not. They add a layer to a geeViz
  ``Map``, which georest has no business doing, so they are the supported
  surface and there is nowhere else to send a caller. geeViz's own MCP
  server instructs agents to use exactly these -- it is the only way to
  reach an ArcGIS service from inside the sandbox, which blocks raw HTTP.

Warning on the supported surface is therefore worse than noise: it tells
a caller to stop doing the only thing that works. ``addEsriMapService``
did, because it reached the metadata through this module's own deprecated
public wrapper instead of going to georest directly.

Filtering on the message matters: an unrelated DeprecationWarning from
jupyter_core or ipykernel arrives during these calls, and a test that
counts warnings rather than reading them concludes the opposite of the
truth. This asserts on warnings that name ``geeViz.esriLib``.
"""
import warnings

import pytest

import geeViz.esriLib as el

UNREACHABLE = "https://example.invalid/MapServer"


def _esrilib_warnings(fn, *args, **kwargs):
    """DeprecationWarnings raised BY esriLib, ignoring ambient ones.

    ``_WARNED`` is cleared first, and without that this whole file is
    vacuous. ``_deprecated`` warns once per NAME per PROCESS, so the first
    test to touch ``getServiceMetadata`` consumes the only warning it will
    ever emit and every later assertion sees silence no matter what the
    code does. Verified: with the fix reverted, the un-cleared version
    still passed 7/7.
    """
    el._WARNED.clear()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            fn(*args, **kwargs)
        except Exception:
            # Network failure is fine and expected; we are watching
            # warnings, not return values.
            pass
    return [str(w.message) for w in caught
            if issubclass(w.category, DeprecationWarning)
            and "geeViz.esriLib" in str(w.message)]


@pytest.mark.parametrize("name", ["searchPortal", "getServiceMetadata"])
def test_a_function_georest_replaces_warns_and_names_it(name):
    msgs = _esrilib_warnings(getattr(el, name), "anything")
    assert msgs, f"{name} should warn -- georest has a direct replacement"
    assert any("georest" in m for m in msgs), (
        f"{name}'s warning must name the replacement, or it tells a caller "
        f"to stop without saying what to do instead")


@pytest.mark.parametrize("name", [
    "addEsriMapService",
    "addEsriService",
    "addEsriImageService",
    "addEsriFeatureService",
])
def test_the_supported_map_helpers_do_not_warn(name):
    """Mutation guard for the real fix: restore the internal call to this
    module's own ``getServiceMetadata`` and this fails."""
    msgs = _esrilib_warnings(getattr(el, name), UNREACHABLE)
    assert not msgs, (
        f"{name} emitted {msgs} -- it is the supported surface and the MCP "
        f"sandbox has no alternative, so a deprecation here is advice a "
        f"caller cannot act on. Something on this path is calling a "
        f"deprecated public wrapper instead of georest directly.")


def test_the_module_still_declares_itself_deprecated():
    """The module-level notice stays; this is about per-function scope."""
    assert "DEPRECATED" in (el.__doc__ or "")
    assert "georest" in (el.__doc__ or "")

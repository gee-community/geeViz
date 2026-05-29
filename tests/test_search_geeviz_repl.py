"""Tests for the two search_geeviz REPL-introspection gaps that bit us
in a live agent run:

1. ``_resolve_module`` couldn't walk dotted paths like ``"ee.ImageCollection"``
   — only top-level REPL module names worked.
2. ``pandas`` / ``numpy`` weren't in the default REPL namespace, so
   ``search_geeviz(name="pd.DataFrame.to_markdown")`` returned "not found".

These tests don't require Earth Engine connectivity. They exercise the
resolver logic on a mock namespace and verify the namespace-loading
source contains the new pre-imports.
"""
import inspect as _inspect
import os
import re


# ----- Reproduce _resolve_module logic from server.py -----
class _FakeModuleTree(dict):
    """Stand-in for server._MODULE_TREE — empty so we test the REPL path."""
    pass


def _resolve_module(name, session_ns=None, module_tree=None):
    """Copy of server._resolve_module — kept in sync to avoid importing
    the full server module (which triggers EE init)."""
    mt = module_tree if module_tree is not None else _FakeModuleTree()
    entry = mt.get(name)
    if entry is not None:
        return name, entry  # already resolved in this mock
    if session_ns:
        if "." not in name:
            obj = session_ns.get(name)
            if _inspect.ismodule(obj) or _inspect.isclass(obj):
                return name, obj
            return None, None
        parts = name.split(".")
        head = session_ns.get(parts[0])
        if head is None:
            return None, None
        obj = head
        for attr in parts[1:]:
            obj = getattr(obj, attr, None)
            if obj is None:
                return None, None
        if _inspect.ismodule(obj) or _inspect.isclass(obj):
            return name, obj
    return None, None


# ----- Fixtures: a mock namespace shaped like the agent's REPL -----
def _make_repl_ns():
    """Build a namespace mimicking what server.py:_ensure_initialized sets up.
    Uses real ee and pandas modules so getattr chains work."""
    import ee
    import pandas as pd
    import numpy as np
    return {
        "ee": ee,
        "pd": pd,
        "pandas": pd,
        "np": np,
        "numpy": np,
    }


# ----------------- _resolve_module tests -----------------
def test_top_level_repl_module():
    ns = _make_repl_ns()
    name, obj = _resolve_module("ee", ns)
    assert name == "ee"
    assert _inspect.ismodule(obj)


def test_dotted_ee_class():
    """ee.ImageCollection is a class — the resolver should accept it as
    a container (its dir() returns the class methods, which is what the
    agent wants to list)."""
    ns = _make_repl_ns()
    name, obj = _resolve_module("ee.ImageCollection", ns)
    assert name == "ee.ImageCollection"
    assert _inspect.isclass(obj)
    assert obj is ns["ee"].ImageCollection


def test_dotted_pd_class():
    ns = _make_repl_ns()
    name, obj = _resolve_module("pd.DataFrame", ns)
    assert name == "pd.DataFrame"
    assert _inspect.isclass(obj)


def test_dotted_full_pandas_name():
    ns = _make_repl_ns()
    name, obj = _resolve_module("pandas.DataFrame", ns)
    assert _inspect.isclass(obj)


def test_dotted_path_three_deep():
    """We don't currently traverse beyond 1 level often, but the resolver
    should handle multi-step paths if they land on a class/module."""
    ns = _make_repl_ns()
    # ee.Reducer is a class; ee.Reducer.percentile is a method (callable
    # but neither class nor module). We expect None,None for the method.
    name, obj = _resolve_module("ee.Reducer.percentile", ns)
    assert (name, obj) == (None, None), \
        "Methods are not containers — should not resolve as module=..."


def test_dotted_path_missing_attribute():
    ns = _make_repl_ns()
    name, obj = _resolve_module("ee.NotARealThing", ns)
    assert (name, obj) == (None, None)


def test_dotted_path_unknown_head():
    ns = _make_repl_ns()
    name, obj = _resolve_module("nonexistent.X", ns)
    assert (name, obj) == (None, None)


def test_repl_class_resolves_without_dots():
    """If someone names a class directly (e.g. it was assigned to the
    top-level REPL namespace), accept it."""
    ns = {"MyClass": dict}  # dict is a class
    name, obj = _resolve_module("MyClass", ns)
    assert name == "MyClass"
    assert obj is dict


# ----------------- Namespace-setup source test -----------------
def test_server_namespace_preloads_pandas_and_numpy():
    """The default REPL namespace must include pandas/pd and numpy/np
    so search_geeviz can find them by name. Verified via source
    inspection — importing server.py triggers EE init."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "mcp", "server.py"),
               encoding="utf-8").read()
    # The literal namespace.update keys must mention pd and np
    m = re.search(r"sess\.namespace\.update\(\{(.*?)\}\)", src, re.S)
    assert m, "Couldn't find sess.namespace.update block in server.py"
    block = m.group(1)
    for key in ('"pd"', '"pandas"', '"np"', '"numpy"'):
        assert key in block, f"{key} not added to default REPL namespace"


def test_server_resolve_module_handles_dotted_paths():
    """Verify server.py's _resolve_module has the dotted-path branch."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "mcp", "server.py"),
               encoding="utf-8").read()
    m = re.search(r"def _resolve_module\(.*?(?=\ndef )", src, re.S)
    assert m, "Couldn't find _resolve_module function"
    body = m.group(0)
    assert "parts = name.split" in body, \
        "Dotted-path traversal missing from _resolve_module"
    assert "for attr in parts[1:]" in body, \
        "getattr loop missing from _resolve_module"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print()
    if failed:
        print(f"{failed}/{len(tests)} tests FAILED")
        raise SystemExit(1)
    print(f"{len(tests)}/{len(tests)} tests passed")

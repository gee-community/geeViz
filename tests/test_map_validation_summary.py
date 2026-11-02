"""A layer that passed with warnings is not reported as a clean pass.

map_control printed "WARN: No visible pixels ... every pixel there is
masked" for two post-flood layers and then "All 7 layer(s) passed.", and
the answer went on to describe flood features in layers that showed
nothing. The summary now names the warned layers and what to do.
"""
from pathlib import Path

import geeViz.mcp.server as srv

ROOT = Path(__file__).resolve().parents[1]


def test_clean_layers_say_all_passed():
    s = srv._passed_summary([{"name": "a"}, {"name": "b", "warnings": []}], 2, "Exporting map...")
    assert s == "All 2 layer(s) passed. Exporting map..."


def test_warned_layers_are_named_and_not_called_a_clean_pass():
    passed = [{"name": "Pre-flood"}, {"name": "Post-flood", "warnings": ["No visible pixels"]}]
    s = srv._passed_summary(passed, 2, "Exporting map...")
    assert not s.startswith("All"), s
    assert "1 of 2" in s and "WITH WARNINGS: Post-flood" in s
    assert "action='preview'" in s and "do not describe them" in s


def test_view_and_export_both_use_it():
    src = (ROOT / "mcp" / "server.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    assert code.count("print(_passed_summary(passed, n_layers,") == 2
    assert "layer(s) passed validation.\")" not in code and "layer(s) passed. Exporting map...\")" not in code

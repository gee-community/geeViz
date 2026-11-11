"""geeViz.skills: workflows an agent loads only when a request needs one.

What would go wrong quietly: a skill whose front matter is malformed
disappearing without a word (so the agent never hears of it), an app's
skill folder not being read, the instructions shipping with the raw
placeholder instead of the index, and a skill's code drifting from the
library it shows (the agent is told it need not look those calls up, so
a stale signature becomes a failed run).
"""
import inspect
import re
from pathlib import Path

import pytest

from geeViz import skills

ROOT = Path(__file__).resolve().parents[1]


def _write(d: Path, name: str, front: str, body="Body.\n"):
    (d / name).mkdir(parents=True)
    (d / name / "SKILL.md").write_text(f"---\n{front}\n---\n{body}", encoding="utf-8")


def test_the_fire_skill_is_listed_and_loads():
    s = skills.list_skills()
    assert s["fire"]["source"] == "geeViz"
    assert "burn severity" in s["fire"]["description"]
    body = skills.load_skill("fire")
    assert body.startswith("# Fire") and "---" not in body.splitlines()[0]


def test_an_unknown_skill_names_the_ones_there_are():
    with pytest.raises(KeyError, match="skills: .*fire"):
        skills.load_skill("nope")


def test_app_folders_are_read_and_can_override(tmp_path, monkeypatch):
    _write(tmp_path, "export-panel", "name: export-panel\ndescription: The export panel.")
    _write(tmp_path, "fire", "name: fire\ndescription: An app's own fire skill.", body="App fire.\n")
    monkeypatch.setenv(skills.ENV_VAR, str(tmp_path))
    s = skills.list_skills()
    assert s["export-panel"]["source"] == "app"
    assert s["fire"]["source"] == "app" and skills.load_skill("fire") == "App fire.\n"


@pytest.mark.parametrize("front", [
    "description: no name",
    "name: Bad Name\ndescription: spaces and capitals",
    "name: nodesc",
])
def test_malformed_front_matter_is_skipped(tmp_path, monkeypatch, front):
    _write(tmp_path, "x", front)
    monkeypatch.setenv(skills.ENV_VAR, str(tmp_path))
    assert set(skills.list_skills()) == {"fire"}


def test_crlf_files_parse(tmp_path, monkeypatch):
    (tmp_path / "w").mkdir()
    (tmp_path / "w" / "SKILL.md").write_bytes(b"---\r\nname: w\r\ndescription: Windows.\r\n---\r\nBody\r\n")
    monkeypatch.setenv(skills.ENV_VAR, str(tmp_path))
    assert skills.list_skills()["w"]["description"] == "Windows."
    assert skills.load_skill("w").strip() == "Body"


def test_the_index_is_one_line_per_skill():
    idx = skills.index_markdown()
    assert idx.splitlines()[0].startswith("- `fire`: ")
    assert len(idx.splitlines()) == len(skills.list_skills())


def test_the_instructions_carry_the_placeholder_and_both_readers_fill_it():
    md = (ROOT / "mcp" / "agent-instructions.md").read_text(encoding="utf-8")
    assert md.count("<!--SKILLS_INDEX-->") == 1
    assert "load_skill(name)" in md
    server = (ROOT / "mcp" / "server.py").read_text(encoding="utf-8")
    assert '.replace("<!--SKILLS_INDEX-->", _skills_mod.index_markdown())' in server
    assert "def load_skill(name: str) -> str:" in server


def test_fire_requests_are_routed_to_the_skill_not_a_search():
    md = (ROOT / "mcp" / "agent-instructions.md").read_text(encoding="utf-8")
    assert 'searchPortal("wildfire perimeters"' not in md
    edw = next(line for line in md.splitlines() if line.startswith("- **EDW (USFS"))
    assert "fire perimeters" not in edw and "`fire` skill" in edw


def test_the_fire_skill_shows_burn_change_as_it_really_is():
    """The skill tells the agent it need not look this up, so its
    signature line must match the function exactly."""
    import geeViz.fireLib as fl

    body = skills.load_skill("fire")
    line = next(x for x in body.splitlines() if x.startswith("- `fl.burn_change("))
    shown = re.search(r"fl\.burn_change\((.*)\)`", line).group(1)
    params = inspect.signature(fl.burn_change).parameters.values()
    real = ", ".join(p.name if p.default is inspect.Parameter.empty else f"{p.name}={p.default!r}"
                     for p in params)
    assert shown.replace(" ", "") == real.replace(" ", "")
    for key in ("pre", "post", "dnbr", "severity", "perimeter", "info", "candidates", "dates", "viz", "names", "notes"):
        assert f"`{key}`" in body

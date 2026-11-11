"""Skills: short, tested workflows an agent loads only when it needs one.

An agent's instructions are read on every model call, so everything in
them costs time and tokens on every turn, including the turns that never
touch it. A skill is the opposite: the always-loaded instructions carry
one line per skill (its name and when to use it), and the body (the
workflow, the one or two library calls that do it, and that subject's
pitfalls) is read only when a request needs it.

Each skill is a folder holding ``SKILL.md`` with a short front matter::

    ---
    name: fire
    description: Fire perimeters, before/after change and burn severity ...
    ---
    # body: markdown

This is the open Agent Skills layout, so the same folders also work in
Claude Code and other clients that read it.

Skills are gathered from, in order (a later one with the same name wins):

* geeViz's own ``geeViz/skills/`` (Earth Engine workflows),
* ``georest/skills/`` when georest is installed (data access without
  Earth Engine),
* every folder in the ``GEEVIZ_SKILL_DIRS`` environment variable
  (``os.pathsep``-separated): an application's own, such as the geeViz
  agent's chat-UI skills.

Example::

    from geeViz import skills
    print(skills.index_markdown())     # the one-line-per-skill list
    print(skills.load_skill("fire"))   # one skill's body
"""
from __future__ import annotations

import os
import re
from pathlib import Path

ENV_VAR = "GEEVIZ_SKILL_DIRS"
_HERE = Path(__file__).resolve().parent
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.S)
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _roots() -> list[tuple[str, Path]]:
    roots = [("geeViz", _HERE)]
    try:
        import georest

        roots.append(("georest", Path(georest.__file__).resolve().parent / "skills"))
    except Exception:  # georest is optional here
        pass
    for d in (os.environ.get(ENV_VAR) or "").split(os.pathsep):
        if d.strip():
            roots.append(("app", Path(d.strip())))
    return roots


def _parse(text: str) -> tuple[dict, str]:
    """Front matter (simple ``key: value`` lines) and body."""
    m = _FRONT.match(text.replace("\r\n", "\n"))
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t", "#")):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip("'\"")
    return meta, m.group(2).lstrip("\n")


def list_skills() -> dict[str, dict]:
    """Every skill, by name: ``{"name", "description", "source", "path"}``.

    A folder without a readable ``SKILL.md``, or whose front matter lacks
    a valid ``name`` (lowercase letters, digits and hyphens) or a
    ``description``, is skipped rather than guessed at.
    """
    out: dict[str, dict] = {}
    for source, root in _roots():
        if not root.is_dir():
            continue
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            f = d / "SKILL.md"
            if not f.is_file():
                continue
            try:
                meta, _ = _parse(f.read_text(encoding="utf-8"))
            except OSError:
                continue
            name, desc = meta.get("name", ""), meta.get("description", "")
            if _NAME.match(name) and desc:
                out[name] = {"name": name, "description": desc, "source": source, "path": str(f)}
    return out


def load_skill(name: str) -> str:
    """One skill's body (without its front matter).

    Raises:
        KeyError: No skill has that name; the message lists the ones that do.
    """
    skills = list_skills()
    key = str(name or "").strip().lower()
    if key not in skills:
        raise KeyError(f"no skill named {name!r}; skills: {', '.join(sorted(skills)) or 'none'}")
    _, body = _parse(Path(skills[key]["path"]).read_text(encoding="utf-8"))
    return body


def index_markdown() -> str:
    """The one-line-per-skill list for an agent's instructions."""
    skills = list_skills()
    if not skills:
        return ""
    lines = [f"- `{s['name']}`: {s['description']}" for s in sorted(skills.values(), key=lambda s: s["name"])]
    return "\n".join(lines)

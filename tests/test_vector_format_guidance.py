"""Asked for a shapefile, the agent said it could not make one (2026-11-18).

It can: a GeoJSON saved with save_file() gets a download button that
converts it to KML, GeoPackage or a zipped Shapefile on the server. But
the instructions said to write the other formats yourself when the user
names one, and in the deployed sandbox that needs tempfile, zipfile and
os, which are blocked. So the agent tried, hit the block, and told the
user the format was unavailable.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTR = (ROOT / "mcp" / "agent-instructions.md").read_text(encoding="utf-8")
SERVER = (ROOT / "mcp" / "server.py").read_text(encoding="utf-8")


def _py(src):
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    return re.sub(r"(?m)^\s*#.*$", "", src)


def test_stripper_removes_comments():
    assert "x" not in _py('# x\n"""x"""')


def test_instructions_send_named_formats_through_the_geojson_download():
    assert "unless the user asks for one by name" not in INSTR
    assert "even when the user asks for a Shapefile, KML or GeoPackage" in INSTR
    assert "**When the user asks for a Shapefile, KML or GeoPackage, say yes.**" in INSTR
    assert "Never tell the user a vector format can't be produced." in INSTR


def test_the_blocked_import_hints_point_to_the_geojson_download():
    code = _py(SERVER)
    i = code.index("_BLOCKED_MODULE_HINTS = {")
    hints = code[i:code.index("}", i)]
    for mod in ("tempfile", "zipfile"):
        line = re.search(rf'"{mod}":\s*"([^"]*)"', hints)
        assert line, mod
        assert "save_file('name.geojson'" in line.group(1)
        assert "download button" in line.group(1)
        # Both are still blocked: the hint explains the block, it is not a hole.
        assert f'"{mod}"' in code[code.index("_BLOCKED_MODULES = frozenset({"):][:3000]

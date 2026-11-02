"""run_code asks where typed-in data came from.

Session e4561fe2 (2026-10-22): asked for 30 years of world vanilla
production, the model typed a 31-row table from memory into run_code,
charted it as "FAOSTAT historical global vanilla production data", and
told the user the data came from FAOSTAT. The instruction "never write a
number you haven't seen in tool output" did not stop it: once typed into
run_code and printed, the numbers were tool output.

run_code now counts the numbers typed into any one literal table and, at
20 or more, appends a note to stdout asking the model to name the source
or say the values are from memory. Coordinates handed to ee.Geometry,
evenly spaced runs (years) and arguments to calls are not counted.
"""
import asyncio
import json
import re
import textwrap
from pathlib import Path

import geeViz.mcp.server as srv

INSTRUCTIONS = (Path(srv.__file__).parent / "agent-instructions.md").read_text(
    encoding="utf-8")

# The shape of the code from session e4561fe2, shortened to 8 years.
VANILLA = """
import pandas as pd
# FAOSTAT historical global vanilla production data (metric tonnes)
data = [
    {"year": 1994, "world_total": 4120, "madagascar": 1580, "indonesia": 1820, "mexico": 240},
    {"year": 1995, "world_total": 4350, "madagascar": 1640, "indonesia": 1950, "mexico": 250},
    {"year": 1996, "world_total": 4580, "madagascar": 1720, "indonesia": 2040, "mexico": 265},
    {"year": 1997, "world_total": 4810, "madagascar": 1800, "indonesia": 2180, "mexico": 270},
    {"year": 1998, "world_total": 5050, "madagascar": 1950, "indonesia": 2240, "mexico": 280},
    {"year": 1999, "world_total": 5260, "madagascar": 2100, "indonesia": 2310, "mexico": 275},
    {"year": 2000, "world_total": 5100, "madagascar": 1780, "indonesia": 2420, "mexico": 285},
    {"year": 2001, "world_total": 5340, "madagascar": 1900, "indonesia": 2510, "mexico": 300},
]
df = pd.DataFrame(data)
print(len(df))
"""


def _run(code, sid):
    return json.loads(asyncio.run(srv.run_code(textwrap.dedent(code), session_id=sid)))


# --- the count ---------------------------------------------------------------

def test_the_vanilla_table_is_counted():
    assert srv._typed_data_values(VANILLA) == 40


def test_a_dict_of_columns_is_one_table():
    code = "d = {'a': [3.1, 4.7, 2.2, 9.9, 1.0], 'b': [5, 8, 1, 7, 2]}"
    assert srv._typed_data_values(code) == 10


def test_a_table_typed_one_list_per_column_is_counted():
    """A replay of the vanilla chart typed 5 column lists of 11 values;
    measuring only the largest list (11) let it through."""
    code = textwrap.dedent("""
        years = [1993, 1996, 2000, 2003, 2006, 2011, 2014, 2017, 2020, 2022, 2024]
        madagascar = [1400, 1500, 1450, 1800, 6200, 2791, 3139, 3002, 2975, 3344, 3090]
        indonesia  = [1500, 1600, 1850, 2200, 2399, 3500, 2000, 2067, 2306, 2270, 1526]
        mexico     = [ 250,  280,  300,  320,  306,  362,  420,  515,  589,  782,  510]
        china      = [ 100,  150,  300,  500, 1000,  799,  286,  416,  433,  476,  435]
        others     = [ 700,  670,  550,  380,  575,  308, 1105, 1300, 1377,  958, 1554]
    """)
    assert srv._typed_data_values(code) == 66
    assert "types 66 data values" in srv._typed_data_note(code)


def test_scattered_settings_do_not_add_up():
    code = textwrap.dedent("""
        v1 = {'min': 0, 'max': 3000}
        v2 = {'min': -1, 'max': 1, 'gamma': 1.4}
        Map.setCenter(-111.5, 40.2, 9)
        p = [5, 50, 95]
        d = {'scale': 30, 'maxPixels': 1e13}
        q = (0.1, 0.2)
    """ * 4)
    assert srv._typed_data_values(code) == 0


def test_evenly_spaced_years_are_an_index_not_data():
    assert srv._typed_data_values("years = [1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020, 2025] * 3") == 0


def test_arguments_to_a_call_are_settings():
    """Each short list counts on its own (5), not the dictionary around
    the calls (17 numbers in all)."""
    code = """
    out = ee.Dictionary({
        'p': img.reduceRegion(reducer=ee.Reducer.percentile([50, 75, 90, 95, 99]),
                              geometry=geom, scale=30, maxPixels=1e13),
        'q': img.reduceRegion(reducer=ee.Reducer.percentile([5, 10, 25]),
                              geometry=geom, scale=30, maxPixels=1e13),
    })
    """
    assert srv._typed_data_values(textwrap.dedent(code)) == 5


def test_a_table_passed_to_a_call_is_still_counted():
    code = "df = pd.DataFrame([[1.5, 2.5, 3.1], [4.2, 5.9, 6.3]])"
    assert srv._typed_data_values(code) == 6


def test_geometry_coordinates_are_not_counted():
    code = "g = ee.Geometry.Polygon([[[-111.1, 40.2], [-111.3, 40.9], [-110.7, 40.4], [-110.2, 40.8], [-111.6, 40.1], [-111.9, 40.5], [-111.1, 40.2]]] * 3)"
    assert srv._typed_data_values(code) == 0


def test_code_that_does_not_parse_counts_nothing():
    assert srv._typed_data_values("data = [1, 2,") == 0


# --- the note ----------------------------------------------------------------

def test_the_threshold():
    nineteen = "x = [" + ", ".join(str(k * k + 0.5) for k in range(19)) + "]"
    twenty = "x = [" + ", ".join(str(k * k + 0.5) for k in range(20)) + "]"
    assert srv._typed_data_note(nineteen) == ""
    assert "types 20 data values" in srv._typed_data_note(twenty)


def test_the_note_asks_for_a_source_or_an_admission():
    note = srv._typed_data_note(VANILLA)
    assert "name that source" in note
    assert "own memory" in note and "first sentence" in note
    assert "approximate" in note
    assert "dataset or agency name" in note
    # A replay typed the table, searched afterward and credited the search.
    assert "made before this code" in note and "after typing them" in note


# --- the wiring --------------------------------------------------------------

def test_run_code_appends_the_note_to_stdout():
    out = _run(VANILLA, "typed-data-vanilla")
    # pytest's capture swallows print() here, so only the note is checked.
    assert out["success"] is True
    assert "NOTE: this code types 40 data values" in out["stdout"]


def test_ordinary_code_gets_no_note():
    out = _run("""
        vis = {'min': 0, 'max': 3000, 'bands': ['red', 'green', 'blue']}
        print(sum(range(10)))
    """, "typed-data-ordinary")
    assert out["success"] is True
    assert "NOTE:" not in (out["stdout"] or "")


# --- the instruction ---------------------------------------------------------

def _rule():
    m = re.search(r"^- \*\*Numbers you type into code are not data from a tool\.\*\*.*$",
                  INSTRUCTIONS, re.M)
    assert m, "the rule is in agent-instructions.md"
    return m.group(0)


def test_the_rule_sits_with_the_number_rule():
    lines = INSTRUCTIONS.splitlines()
    i = next(k for k, ln in enumerate(lines)
             if ln.startswith("- **Never write a number you haven't seen in tool output.**"))
    assert lines[i + 1] == _rule()


def test_the_rule_covers_the_failure():
    rule = _rule()
    assert "first sentence" in rule, "says up front that no tool reaches the data"
    assert "web search" in rule, "offers the sourced alternative"
    assert "FAOSTAT" in rule, "no agency name on typed values"
    assert "my own knowledge" in rule, "answers 'where did this come from' honestly"
    assert "made before you typed them" in rule, "a later search does not source them"


def test_a_summary_layer_does_not_replace_the_time_lapse():
    """With "alongside it" alone, a replay drew one summary layer and no time lapse."""
    start = INSTRUCTIONS.index("**Change over time is a time lapse, by default.**")
    rule = INSTRUCTIONS[start:INSTRUCTIONS.index("\n", start)]
    assert "Map.addTimeLapse" in rule and "without waiting to be asked" in rule
    assert "not instead of it" in rule

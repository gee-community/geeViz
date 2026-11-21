"""The wind speed raster stays on its place through a fast pan (2026-11-13).

Reported from the field: drag a WeatherNext wind map and let go so it
keeps gliding, and the colored speed raster slid along with it and
stayed there, offset from the basemap, showing one place's wind over
another. For hazard response that is the worst kind of wrong: plausible
and quiet.

The map's center moves ahead of the overlay's ``draw()``. A repaint in
between laid the raster out from draw()'s OLD origin but cached it under
the NEW center, so when draw() then moved the canvas to the new origin
the cache key still matched and nothing repainted. Measured on the old
source with this probe: 323 px off, still 323 px after the next frame.

Two changes, each guarded here:

* the cache key is draw()'s own geometry, not ``map.getCenter()``, so a
  paint is only reused at the exact position it was laid out for
  (``coversView``);
* the raster canvas is placed where its paint belongs, so between a
  move and the repaint it moves with the map instead of carrying old
  pixels to a new place (``afterDraw``).

Driven through node against the real source with a fake Mercator
projection, because where a canvas sits against where it was painted
for is a fact about behavior that the source text does not show.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "geeView" / "src" / "js" / "wind-particles.js"
PROBE = HERE / "wind_anchor_probe.js"


@pytest.fixture(scope="module")
def run():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    out = subprocess.run([node, str(PROBE), str(SRC)], capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_anchored_when_settled(run):
    assert run["settled"] == 0


def test_a_moving_center_does_not_reuse_or_misplace_the_paint(run):
    # The center has moved, draw() has not: nothing moves on screen.
    assert run["midMomentum"] == 0


def test_the_raster_moves_with_the_map_until_it_repaints(run):
    assert run["afterDraw"] == 0


def test_the_raster_is_repainted_for_the_view_draw_settled_on(run):
    assert run["afterRepaint"] == 0
    assert run["coversView"] is True


def test_no_repaint_when_nothing_moved(run):
    # Initial paint plus the one after draw() caught up; the final
    # ensure with an unchanged view reuses the cache.
    assert run["paints"] == 2


def test_dateline_picks_the_copy_of_the_world_nearest_the_view(run):
    # A paint 150 px east of the view's corner across the dateline is
    # placed 150 px east, not a world width away.
    assert run["datelineDx"] == 150

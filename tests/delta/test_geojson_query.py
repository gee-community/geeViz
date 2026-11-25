"""GeoJSON layers answer the Query tool by hit test on what is drawn
(geeView/delta/js/engine/hittest.js), with no Earth Engine: a point within
8 pixels of its marker, a line within 5 pixels, a polygon when the click is
inside it.

Needs the local eeCreds proxy (it serves the page).
"""
import time

import pytest

pytestmark = pytest.mark.live

C = (-105.0, 40.0)
Z = 12
DPP = 360 / (256 * 2 ** Z)  # degrees of longitude per pixel at Z
MAP_CENTER = (750, 437)


def at(dx_px):
    return C[0] + dx_px * DPP


def build(Map):
    Map.addLayer({"type": "Feature", "properties": {"kind": "a point", "n": 1},
                  "geometry": {"type": "Point", "coordinates": [at(-200), C[1]]}},
                 {"strokeColor": "d62728"}, "Point")
    Map.addLayer({"type": "Feature", "properties": {"kind": "a line", "n": 2},
                  "geometry": {"type": "LineString", "coordinates": [[at(200), C[1] - 0.01], [at(200), C[1] + 0.01]]}},
                 {"strokeColor": "1f77b4"}, "Line")
    sq = [[at(-50), C[1] - 0.003], [at(50), C[1] - 0.003], [at(50), C[1] + 0.003], [at(-50), C[1] + 0.003], [at(-50), C[1] - 0.003]]
    Map.addLayer({"type": "Feature", "properties": {"kind": "a polygon", "n": 3},
                  "geometry": {"type": "Polygon", "coordinates": [sq]}},
                 {"strokeColor": "2ca02c", "fillOpacity": 0.3}, "Polygon")
    Map.setCenter(C[0], C[1], Z)
    Map.turnOnInspector()


def wait_for(page, js, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(js):
            return
        time.sleep(0.25)
    raise AssertionError("timed out waiting for: " + js)


def query(page, dx, dy=0):
    page.evaluate("() => __delta.store.set({results: []}, 'test')")
    page.mouse.dblclick(MAP_CENTER[0] + dx, MAP_CENTER[1] + dy)
    wait_for(page, "() => __delta.store.get().querying === false && __delta.store.get().results.length >= 3")
    return {r["title"]: r for r in page.evaluate("__delta.store.get().results")}


def rows(card):
    return dict(card["data"]["rows"])


def test_geojson_layers_answer_the_query_tool(live_map):
    seen = []
    page = live_map(build, setup=lambda ctx: ctx.on("request", lambda req: seen.append(req.url)))
    wait_for(page, "() => __delta.store.get().layers.length === 3 && __delta.store.get().layers.every(l => !l.loading)")
    near_point = query(page, -200 + 5)
    assert rows(near_point["Point"]).get("kind") == "a point", near_point["Point"]
    assert near_point["Polygon"]["meta"] == "No features here"
    near_line = query(page, 200 + 3)
    assert rows(near_line["Line"]).get("kind") == "a line", near_line["Line"]
    in_poly = query(page, 0)
    assert rows(in_poly["Polygon"]).get("kind") == "a polygon"
    assert in_poly["Point"]["meta"] == "No features here"
    far = query(page, -200 + 25)
    assert far["Point"]["meta"] == "No features here"
    assert [u for u in seen if "ee_api_js" in u or "/ee-api/" in u] == []

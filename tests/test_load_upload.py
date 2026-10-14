"""run_code reads the user's uploads whole: load_upload / list_uploads.

An uploaded shapefile used to reach the model only as GeoJSON pasted into
the prompt, so code could use it only by retyping it. A 23-feature,
13,059-vertex neighborhoods layer came back as a 369-vertex copy with a
mistyped coordinate, after a first attempt that returned nothing at all.
The web server now stages each converted upload in the session's sandbox
folder (<output dir>/uploads/), and these helpers read it there.
"""
import asyncio
import json
import os
import shutil
import uuid

import pytest

import geeViz.mcp.server as srv

FC = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"NAME": f"N{i}"},
     "geometry": {"type": "Polygon", "coordinates": [[[i, 0], [i + 1, 0], [i + 1, 1], [i, 1], [i, 0]]]}}
    for i in range(23)]}


@pytest.fixture
def session_with_upload():
    sid = "test_upl_" + uuid.uuid4().hex[:10]
    folder = os.path.join(srv._BASE_OUTPUT_DIR, sid, "uploads")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "slc_neighborhoods.geojson"), "w", encoding="utf-8") as fh:
        json.dump(FC, fh)
    yield sid
    shutil.rmtree(os.path.join(srv._BASE_OUTPUT_DIR, sid), ignore_errors=True)


def _run(code, sid):
    return json.loads(asyncio.run(srv.run_code(code, session_id=sid)))


def test_code_loads_the_whole_upload_by_the_name_the_user_gave(session_with_upload):
    # The result is the block's last expression (pytest's own capture
    # swallows run_code's stdout, so the values come back that way).
    out = _run(
        "gj = load_upload('slc_neighborhoods.zip')\n"          # the name the user uploaded
        "fc = ee.FeatureCollection(load_upload())\n"            # the only upload
        "[list_uploads(), len(gj['features']), gj['features'][22]['properties']['NAME'],"
        " fc.size().getInfo()]\n",
        session_with_upload)
    assert out["success"], out.get("error")
    assert out["result"] == [["slc_neighborhoods.geojson"], 23, "N22", 23]


def test_no_upload_asks_for_it_again_without_saying_it_never_arrived():
    # A file attached earlier can be out of reach later (the conversation
    # moved to another server instance, or a small text file was sent
    # inside the message rather than stored). "It never arrived" had the
    # agent tell users who had attached it that they had not.
    sid = "test_upl_" + uuid.uuid4().hex[:10]
    out = _run("load_upload('x.zip')", sid)
    assert out["success"] is False
    err = out.get("error") or ""
    assert "No uploaded file is available" in err
    assert "attach it again" in err
    assert "never arrived" not in err
    shutil.rmtree(os.path.join(srv._BASE_OUTPUT_DIR, sid), ignore_errors=True)


def test_an_unknown_name_lists_what_is_there(session_with_upload):
    out = _run("load_upload('other.zip')", session_with_upload)
    assert out["success"] is False and "slc_neighborhoods.geojson" in out["error"]


def test_the_name_cannot_walk_out_of_the_uploads_folder(session_with_upload):
    out = _run("load_upload('../../../server.py')", session_with_upload)
    assert out["success"] is False

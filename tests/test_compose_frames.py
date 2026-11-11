"""compose_frames: generate_gif's finishing (padding or basemap, date,
legend, scalebar, north arrow, title, margins) as a public function, so
frames rendered elsewhere (the agent's Earth Engine batch exports) are
finished exactly as geeViz finishes its own GIFs and thumbnails."""
import io
import re
from pathlib import Path

import pytest

pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

from geeViz.outputLib import thumbs  # noqa: E402

SRC = Path(thumbs.__file__).read_text(encoding="utf-8")


def _code(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    return "\n".join(line.split("#", 1)[0] for line in src.splitlines())


def _frames(n=2, size=(200, 120)):
    out = []
    for i in range(n):
        im = Image.new("RGBA", size, (0, 0, 0, 0))
        im.paste((40 * i, 120, 200, 255), (20, 20, 180, 100))
        out.append(im)
    return out


THEMATIC = {"type": "thematic", "class_names": ["Trees", "Grass"],
            "class_palette": ["005e00", "ffd700"]}
BOUNDS = (-111.0, 40.0, -110.8, 40.1)


def test_frames_are_finished_alike_and_grow_with_the_decorations():
    plain = thumbs.compose_frames(_frames(), None, burn_in_date=False,
                                  scalebar=False, north_arrow=False, inset_map=False)
    full = thumbs.compose_frames(_frames(), BOUNDS, date_labels=["2020", "2021"],
                                 legend_info=THEMATIC, title="Land cover",
                                 inset_map=False)
    assert len(full) == 2 and all(f.mode == "RGBA" for f in full)
    assert full[0].size == full[1].size, "every frame the same size, for the GIF"
    w0, h0 = plain[0].size
    w1, h1 = full[0].size
    assert w1 > w0, "the legend panel widens the picture"
    assert h1 > h0, "the title strip and scalebar add height"


def test_the_date_is_burned_into_each_frame():
    a = thumbs.compose_frames(_frames(1), None, date_labels=["2020"], scalebar=False,
                              north_arrow=False, inset_map=False)[0]
    b = thumbs.compose_frames(_frames(1), None, date_labels=["2020"], burn_in_date=False,
                              scalebar=False, north_arrow=False, inset_map=False)[0]
    assert a.size == b.size and a.tobytes() != b.tobytes()


def test_gif_and_png_bytes():
    frames = thumbs.compose_frames(_frames(3), BOUNDS, date_labels=["a", "b", "c"],
                                   inset_map=False)
    gif = Image.open(io.BytesIO(thumbs.frames_to_gif(frames, fps=2)))
    assert gif.format == "GIF" and gif.n_frames == 3
    png = Image.open(io.BytesIO(thumbs.picture_to_png(frames[0])))
    assert png.format == "PNG" and png.size == frames[0].size


def test_no_basemap_fetch_without_a_basemap(monkeypatch):
    called = []
    monkeypatch.setattr(thumbs, "_fetch_basemap", lambda *a, **k: called.append(a))
    thumbs.compose_frames(_frames(1), BOUNDS, burn_in_date=False, inset_map=False)
    assert called == []


def test_the_basemap_is_fetched_once_at_frame_size_in_the_basemap_crs(monkeypatch):
    calls = []

    def fake(bounds, w, h, basemap, crs=None):
        calls.append((bounds, w, h, basemap, crs))
        return Image.new("RGBA", (w, h), (90, 90, 90, 255))
    monkeypatch.setattr(thumbs, "_fetch_basemap", fake)
    thumbs.compose_frames(_frames(3), BOUNDS, basemap="esri-topo", crs="EPSG:32612",
                          basemap_crs="EPSG:3857", burn_in_date=False, inset_map=False)
    assert calls == [(BOUNDS, 200, 120, "esri-topo", "EPSG:3857")]


def test_continuous_legend_info_matches_the_extractor():
    viz = {"bands": ["NDVI"], "min": 0, "max": 1, "palette": "000000,00ff00"}
    assert thumbs.continuous_legend_info(viz) == {
        "type": "continuous", "min": 0, "max": 1,
        "palette": ["000000", "00ff00"], "band_name": "NDVI"}
    assert thumbs.continuous_legend_info({"bands": ["r", "g", "b"], "min": 0, "max": 1,
                                          "palette": ["000000"]}) is None
    assert thumbs.continuous_legend_info({"min": 0, "max": 1}) is None


def test_generate_gif_finishes_its_frames_with_compose_frames():
    code = _code(SRC)
    gif = code[code.index("def generate_gif("):code.index("def compose_frames(")]
    assert "final_frames = compose_frames(" in gif
    assert "_assemble_with_cartography(" not in gif, "one finishing path, not two"
    ext = code[code.index("def _extract_legend_info("):code.index("def _hex_to_rgb(")]
    assert "return continuous_legend_info(viz_params, band_name=band_name)" in ext

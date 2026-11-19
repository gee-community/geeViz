"""Offline catalog-helper contracts, parity, and optional runtime boundaries."""

from dataclasses import asdict, FrozenInstanceError
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import MappingProxyType, ModuleType, SimpleNamespace
from unittest.mock import call, Mock, sentinel

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def source_helpers():
    package = pytest.importorskip(
        "ee_catalog_helpers", reason="optional source characterization baseline"
    )
    modules = [
        importlib.import_module(f"ee_catalog_helpers.{name}")
        for name in (
            "core.ingest", "core.jsonnet", "core.parsing", "core.properties",
            "core.text", "catalog", "discovery", "table_metadata", "raster",
        )
    ]
    exports = {
        name: value
        for module in modules
        for name, value in vars(module).items()
        if not name.startswith("_")
    }
    return SimpleNamespace(
        **exports, __name__=package.__name__, __file__=package.__file__
    )


@pytest.fixture
def catalog_helpers(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "geeViz.eeCatalogHelpers", ROOT / "eeCatalogHelpers.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=["source", "geeviz"])
def helpers(request):
    return request.getfixturevalue(
        "source_helpers" if request.param == "source" else "catalog_helpers"
    )


def _profiles(helpers, tmp_path, records=None):
    path = tmp_path / "profiles.json"
    if records is None:
        records = [
            {
                "name": name,
                "source_suffix": f"_{name}.tif",
                "source_location": "root",
                "pyramiding_policy": " mode ",
                "valid_min": 0,
                "valid_max": 10,
                "data_type": "uint8",
                "conversion": "round_nearest",
                "source_valid_values": [0, 1],
                "value_map": {"0": 0, "1": 2},
                "description": name,
            }
            for name in ("red", "green")
        ]
    path.write_text(json.dumps({"bands": records}), encoding="utf-8")
    return helpers.load_band_profiles(path)


def test_ordered_frozen_plans_and_deterministic_preview(helpers, tmp_path):
    profiles = _profiles(helpers, tmp_path)
    sources = {name: tmp_path / f"{name}.tif" for name in ("green", "red")}
    bands = helpers.build_planned_bands(
        profiles, sources, "gs://bucket/data",
        {"red": "255.0", "green": 255.0}, object_prefix="/v1/",
    )
    expected = [
        {
            "bandName": name, "pyramidingPolicy": "MODE",
            "gcsURI": f"gs://bucket/data/v1/{name}.tif", "noDataValue": 255,
        }
        for name in ("red", "green")
    ]
    assert isinstance(profiles, tuple)
    assert isinstance(bands, tuple)
    assert [profile.name for profile in profiles] == ["red", "green"]
    assert profiles[0].source_valid_values == (0.0, 1.0)
    assert profiles[0].value_map == {0.0: 0, 1.0: 2}
    assert [band.as_ingest_entry() for band in bands] == expected
    assert helpers.build_ingest_entry("red", "MODE", expected[0]["gcsURI"], "255.0") == expected[0]

    image = helpers.PlannedImage(
        "example", "projects/example/assets/image", bands, {"year": 2024}
    )
    for instance, field in (
        (profiles[0], "name"), (bands[0], "gcs_uri"), (image, "asset_id")
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(instance, field, "changed")
    preview = {
        "image_name": "example",
        "asset_id": image.asset_id,
        "bands": [
            {"source_path": str(sources[entry["bandName"]]), **entry}
            for entry in expected
        ],
        "properties": {"year": 2024},
    }
    assert image.as_preview() == preview
    destination = tmp_path / "plans" / "manifest.json"
    helpers.write_manifest_preview([image], destination)
    first = destination.read_bytes()
    helpers.write_manifest_preview([image], destination)
    assert destination.read_bytes() == first
    assert destination.read_text(encoding="utf-8") == json.dumps([preview], indent=2, sort_keys=True) + "\n"


@pytest.mark.parametrize(
    ("records", "error", "message"),
    [
        ([], ValueError, "non-empty 'bands' list"),
        ([None], TypeError, "index 0 is not an object"),
        ([{"name": "red"}], ValueError, "index 0 is missing"),
    ],
)
def test_profile_validation_diagnostics(helpers, tmp_path, records, error, message):
    with pytest.raises(error, match=message):
        _profiles(helpers, tmp_path, records)


def test_source_band_set_diagnostics(helpers, tmp_path):
    profiles = _profiles(helpers, tmp_path)
    with pytest.raises(ValueError, match=r"Missing=\['green'\], unexpected=\['blue'\]"):
        helpers.build_planned_bands(
            profiles, {"red": tmp_path / "r.tif", "blue": tmp_path / "b.tif"},
            "gs://bucket", {},
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), (" ", None), ("255.0", 255), (255.0, 255),
     (" -2.5 ", -2.5), ("unknown", "unknown"), (0, 0)],
)
def test_nodata_coercion(helpers, value, expected):
    result = helpers.coerce_nodata_value(value)
    assert result == expected
    assert type(result) is type(expected)


def test_gcs_uri_preserves_identifier_text(helpers):
    assert helpers.join_gcs_uri(
        " gs://MixedCase-Bucket/Folder/// ", "/A file+1.TIF"
    ) == "gs://MixedCase-Bucket/Folder/A file+1.TIF"


@pytest.mark.parametrize("prefix", ["", "gs://", "gs:///", "https://bucket"])
def test_gcs_uri_requires_nonempty_gs_prefix(helpers, prefix):
    with pytest.raises(ValueError, match="non-empty gs:// prefix"):
        helpers.join_gcs_uri(prefix, "red.tif")


def _discover(helpers, folder, **kwargs):
    return helpers.build_image_dict(
        image_folder=folder, name_format="item_{attribute}.tif",
        pyramiding_policies={"canonical": "MODE"}, nodata_values={"canonical": "255"},
        gcs_prefix="gs://bucket/data", **kwargs,
    )


def test_recursive_discovery_filters_before_normalizing(helpers, tmp_path):
    nested = tmp_path / "delivery" / "Tif"
    nested.mkdir(parents=True)
    source = nested / "item_RED.tif"
    source.touch()
    (nested / "item_SKIP.tif").touch()
    (nested / "unrelated.tif").touch()
    seen = []

    def normalize(attribute):
        seen.append(attribute)
        return "canonical"

    result = _discover(
        helpers, tmp_path, include_attribute=lambda name: name != "SKIP",
        normalize_attribute_name=normalize,
    )
    assert seen == ["RED"]
    assert result == {
        str(source): {
            "bandName": "canonical", "pyramidingPolicy": "MODE",
            "gcsURI": "gs://bucket/data/item_RED.tif", "noDataValue": 255,
        }
    }


@pytest.mark.parametrize("selection", ["first", "second", "none", "unrelated"])
def test_duplicate_band_selection(helpers, tmp_path, selection):
    first = tmp_path / "a" / "item_old.tif"
    second = tmp_path / "b" / "item_new.tif"
    for path in (first, second):
        path.parent.mkdir()
        path.touch()
    choices = {"first": first, "second": second, "none": None,
               "unrelated": tmp_path / "other.tif"}
    calls = []

    def resolve(band, old, new):
        calls.append((band, old, new))
        return choices[selection]

    kwargs = {
        "normalize_attribute_name": lambda name: "canonical",
        "resolve_duplicate_band": resolve,
    }
    if selection in ("none", "unrelated"):
        with pytest.raises(ValueError, match="same band name"):
            _discover(helpers, tmp_path, **kwargs)
    else:
        assert list(_discover(helpers, tmp_path, **kwargs)) == [str(choices[selection])]
    assert calls == [("canonical", first, second)]


def test_duplicate_bands_require_explicit_resolution(helpers, tmp_path):
    (tmp_path / "item_old.tif").touch()
    (tmp_path / "item_new.tif").touch()
    with pytest.raises(ValueError, match="same band name"):
        _discover(helpers, tmp_path, normalize_attribute_name=lambda name: "canonical")


def test_catalog_artifacts_are_ordered_utf8_and_repeatable(helpers, tmp_path):
    name = helpers.catalog_filename(" /projects/example/assets/Product/v1/ ")
    assert name == "projects_example_assets_Product_v1.jsonnet"
    assert helpers.catalog_filename("projects/example/assets/Product", ".js").endswith("_Product.js")
    artifacts = {Path("templates") / "versions.libsonnet": "[]\n", name: "// caf\u00e9\n{}\n"}
    written = helpers.write_text_artifacts(tmp_path, artifacts)
    assert written == [tmp_path.resolve() / path for path in artifacts]
    contents = [path.read_bytes() for path in written]
    assert contents == [text.encode("utf-8") for text in artifacts.values()]
    assert helpers.write_text_artifacts(tmp_path, artifacts) == written
    assert [path.read_bytes() for path in written] == contents


@pytest.mark.parametrize("kind", ["parent", "nested-parent", "absolute"])
def test_catalog_artifacts_cannot_escape_output(helpers, tmp_path, kind):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    path = {
        "parent": Path("..") / outside.name,
        "nested-parent": Path("nested") / ".." / ".." / outside.name,
        "absolute": outside,
    }[kind]
    with pytest.raises(ValueError, match="remain below"):
        helpers.write_text_artifacts(tmp_path, {path: "nope"})
    assert not outside.exists()


def test_jsonnet_literals_nested_rendering_and_unit_conversion(helpers):
    value = {
        "bands": [{"gee:units": "units.percent", "enabled": True, "missing": None}],
        "raw": helpers.JsonnetLiteral("ee_const.var_type.int"),
    }
    converted = helpers.replace_unit_literals(value)
    expected = (
        "{\n"
        "  bands: [\n"
        "    {\n"
        '      "gee:units": units.percent,\n'
        "      enabled: true,\n"
        "      missing: null,\n"
        "    },\n"
        "  ],\n"
        "  raw: ee_const.var_type.int,\n"
        "}"
    )
    assert helpers.render_jsonnet_value(converted) == expected
    assert value["bands"][0]["gee:units"] == "units.percent"
    assert helpers.render_jsonnet_catalog_blocks(
        value["bands"], gee_visualizations=[]
    ) == {
        "eo_bands": helpers.render_jsonnet_value(converted["bands"]),
        "gee_visualizations": "[]",
    }
    assert helpers.render_jsonnet_table_blocks(
        [], gee_visualizations=[], feature_view_ingestion_params={"max_features_per_tile": 1500}
    ) == {
        "gee_schema": "[]", "gee_visualizations": "[]",
        "feature_view_ingestion_params": "{\n  max_features_per_tile: 1500,\n}",
    }
    assert helpers.is_jsonnet_identifier("_band1")
    assert not helpers.is_jsonnet_identifier("gee:units")
    with pytest.raises(TypeError, match="keys must be strings"):
        helpers.render_jsonnet_value({1: "invalid"})
    with pytest.raises(TypeError, match="Unsupported value type"):
        helpers.render_jsonnet_value({1, 2})


def test_image_property_lookup_aliases_defaults_and_resolution(helpers):
    record = {"version_name": "v1", "version_decimal": 1.1, "version_integer": 110}
    assert [helpers.resolve_lookup_value(record, key) for key in ("name", "version", "number")] == [
        "v1", 1.1, 110,
    ]
    assert helpers.resolve_lookup_value({"name": "preferred", **record}, "name") == "preferred"
    assert helpers.resolve_lookup_value({}, "absent", "fallback") == "fallback"
    context = {"code": 110, "year": 2024}
    lookup = {"lookup": {"110": record}, "lookup_key": "code", "value_key": "name"}
    fields = {
        "version": lookup, "year": "year", "constant": "unchanged",
        "next": lambda ctx: ctx["year"] + 1, "number": 7,
    }
    assert helpers.build_image_properties(list(fields), fields, context) == {
        "version": "v1", "year": 2024, "constant": "unchanged", "next": 2025, "number": 7,
    }
    assert helpers.resolve_property_value({**lookup, "lookup": {}, "default": "unknown"}, context) == "unknown"
    assert helpers.resolve_property_value({**lookup, "lookup": {110: record}}, context) == "v1"
    with pytest.raises(ValueError, match="Invalid lookup spec"):
        helpers.resolve_property_value({"lookup": {}}, context)
    with pytest.raises(KeyError, match="No lookup defined.*missing"):
        helpers.build_image_properties(["missing"], fields, context)


@pytest.mark.parametrize(
    ("values", "expected"),
    [(["1", "", "-2"], "int"), (["1", "2.5"], "double"),
     (["1", "unknown"], "string"), (["", "  "], "string")],
)
def test_table_type_inference_uses_all_populated_values(helpers, values, expected):
    assert helpers.infer_table_field_type(values) == expected


def test_table_schema_order_overrides_and_rendering(helpers, tmp_path):
    path = tmp_path / "table.csv"
    path.write_text("\ufeffVALUE,LABEL,RATIO\n1,One,1.5\n2,Two,2\n", encoding="utf-8")
    schema = helpers.build_table_schema_from_csv(
        path, {"VALUE": " Stored value. ", "LABEL": "Class label.", "RATIO": "Ratio."},
        type_overrides={"VALUE": "string"},
    )
    assert [field["name"] for field in schema] == ["VALUE", "LABEL", "RATIO"]
    assert [field["description"] for field in schema] == ["Stored value.", "Class label.", "Ratio."]
    assert [field["type"].expression for field in schema] == [
        "ee_const.var_type.string", "ee_const.var_type.string", "ee_const.var_type.double",
    ]
    rendered = helpers.render_jsonnet_table_blocks(schema)["gee_schema"]
    assert "type: ee_const.var_type.string," in rendered
    assert "type: ee_const.var_type.double," in rendered


@pytest.mark.parametrize(
    ("text", "descriptions", "overrides", "message"),
    [
        ("", {}, {}, "no header"),
        ("VALUE,VALUE\n1,2\n", {"VALUE": "Value."}, {}, "duplicate field names"),
        ("VALUE,LABEL\n1,One\n", {"VALUE": "Value."}, {}, "Missing table field descriptions: LABEL"),
        ("VALUE\n1\n", {"VALUE": "Value.", "OTHER": "Other."}, {}, "Descriptions reference fields"),
        ("VALUE\n1\n", {"VALUE": "Value."}, {"OTHER": "int"}, "Type overrides reference fields"),
        ("VALUE\n1\n", {"VALUE": "Value."}, {"VALUE": "float"}, "Unsupported table field types"),
    ],
)
def test_table_schema_validation(helpers, tmp_path, text, descriptions, overrides, message):
    path = tmp_path / "table.csv"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        helpers.build_table_schema_from_csv(path, descriptions, type_overrides=overrides)


def test_text_normalization_and_column_preferences(helpers):
    assert helpers.clean_text("\ufeff  Mixed \n case\tvalue ") == "Mixed case value"
    assert helpers.clean_text(None) == ""
    assert helpers.normalize_for_matching(" n/A ") == ""
    assert helpers.normalize_for_matching(" NULL ", null_tokens={"missing"}) == "NULL"
    assert helpers.normalize_for_matching(" missing ", null_tokens={"missing"}) == ""
    assert helpers.choose_preferred_column(["Label", "VALUE"], ["value", "label"]) == "VALUE"
    assert helpers.choose_preferred_column(["Label"], ["missing"]) is None


@pytest.mark.parametrize(
    ("value", "expected"), [(" 2.9 ", 2), ("-2", -2), ("N/A", None), ("bad", None), (None, None)]
)
def test_integer_parsing(helpers, value, expected):
    assert helpers.value_to_int(value) == expected


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"HEX": "#a1b2c3"}, "#A1B2C3"),
        ({"HEX": "a1b2c3", "R": 0, "G": 0, "B": 0}, "#A1B2C3"),
        ({"R": "255.0", "G": 128, "B": 0}, "#FF8000"),
        ({"RED": 0, "GREEN": 16, "BLUE": 255}, "#0010FF"),
        ({"HEX": "bad", "R": 1, "G": 2, "B": 3}, "#010203"),
    ],
)
def test_hex_and_rgb_colors(helpers, row, expected):
    assert helpers.color_from_row(row) == expected


@pytest.mark.parametrize(
    ("row", "message"),
    [({}, "Could not determine color"), ({"R": "bad", "G": 0, "B": 0}, "Invalid RGB"),
     ({"R": 256, "G": 0, "B": 0}, "out of range")],
)
def test_color_diagnostics(helpers, row, message):
    with pytest.raises(ValueError, match=message):
        helpers.color_from_row(row)


def test_import_is_offline_safe_in_clean_process(helpers, tmp_path):
    module_name = helpers.__name__
    module_root = Path(helpers.__file__).resolve().parent.parent
    script = f"""
import importlib
import importlib.abc
import sys
sys.path.insert(0, {str(module_root)!r})
blocked = ('ee', 'geeViz.geeView', 'geeViz.assetManagerLib', 'osgeo')
class NoRuntimeImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + '.') for name in blocked):
            raise AssertionError('Eager runtime import: ' + fullname)
        helper_name = {module_name!r}
        is_helper = (fullname == helper_name or fullname.startswith(helper_name + '.')
                     or helper_name.startswith(fullname + '.'))
        if fullname.split('.')[0] not in sys.stdlib_module_names and not is_helper:
            raise ModuleNotFoundError('Non-standard-library import: ' + fullname, name=fullname)
sys.meta_path.insert(0, NoRuntimeImports())
module = importlib.import_module({module_name!r})
assert module.__file__ == {str(Path(helpers.__file__).resolve())!r}, module.__file__
assert not [name for name in sys.modules
            if any(name == prefix or name.startswith(prefix + '.') for prefix in blocked)]
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", script], cwd=tmp_path,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_source_and_geeviz_workflow_parity(source_helpers, catalog_helpers, tmp_path):
    rasters = tmp_path / "delivery" / "Tif"
    rasters.mkdir(parents=True)
    sources = {name: rasters / f"item_{name}.tif" for name in ("green", "red")}
    for path in sources.values():
        path.touch()
    table = tmp_path / "table.csv"
    table.write_text("VALUE,LABEL,RATIO\n1,One,1.5\n2,Two,2\n", encoding="utf-8")
    results = []
    for index, api in enumerate((source_helpers, catalog_helpers)):
        profiles = _profiles(api, tmp_path)
        bands = api.build_planned_bands(
            profiles, sources, "gs://bucket/data", {"red": "255.0", "green": 255}
        )
        properties = api.build_image_properties(
            ["year", "next"], {"year": "year", "next": lambda ctx: ctx["year"] + 1},
            {"year": 2024},
        )
        image = api.PlannedImage("example", "projects/example/assets/image", bands, properties)
        schema = api.build_table_schema_from_csv(
            table, {"VALUE": "Value.", "LABEL": "Label.", "RATIO": "Ratio."}
        )
        blocks = {
            **api.render_jsonnet_table_blocks(schema),
            **api.render_jsonnet_catalog_blocks(
                [{"name": "red", "gee:units": "units.percent"}],
                [{"display_name": "Red", "bands": ["red"]}],
            ),
        }
        name = api.catalog_filename(image.asset_id)
        output = tmp_path / str(index)
        written = api.write_text_artifacts(
            output, {name: json.dumps(blocks, indent=2), Path("nested") / "note.txt": "caf\u00e9\n"}
        )
        manifest = output / "manifest.json"
        api.write_manifest_preview([image], manifest)
        results.append({
            "profiles": [asdict(profile) for profile in profiles],
            "preview": image.as_preview(),
            "manifest": manifest.read_bytes(),
            "discovery": api.build_image_dict(
                tmp_path / "delivery", "item_{attribute}.tif",
                {"red": "MODE", "green": "MODE"}, {"red": "255.0", "green": 255},
                "gs://bucket/data",
            ),
            "blocks": blocks,
            "artifacts": [(path.relative_to(output.resolve()), path.read_bytes()) for path in written],
        })
    assert results[0] == results[1]


@pytest.mark.parametrize("kind", ["default", "explicit", "in-place"])
@pytest.mark.parametrize("legacy_options", [False, True])
def test_cog_conversion_is_atomic_and_normalizes_options(
    helpers, tmp_path, monkeypatch, kind, legacy_options
):
    source = tmp_path / "input raster.tif"
    source.write_bytes(b"source")
    output = {
        "default": source.with_suffix(".cog.tif"),
        "explicit": tmp_path / "custom output.tif",
        "in-place": source,
    }[kind]
    original = b"source" if kind == "in-place" else b"previous output"
    output.write_bytes(original)
    partial = output.with_name(f"{output.stem}.partial{output.suffix}")
    partial.write_bytes(b"stale partial")
    options = [" -co COMPRESS=DEFLATE ", "-co", "TILED=YES"] if legacy_options else None
    expected_options = (
        ["-co", "COMPRESS=DEFLATE", "-co", "TILED=YES"] if legacy_options else
        ["-co", "COMPRESS=LZW", "-co", "TILED=YES", "-co", "BIGTIFF=IF_SAFER"]
    )

    def translate(argv, *, check):
        assert check is True
        assert argv == ["gdal_translate", *expected_options, str(source), str(partial)]
        assert output.read_bytes() == original
        assert not partial.exists()
        partial.write_bytes(b"converted")

    run = Mock(side_effect=translate)
    monkeypatch.setattr(helpers.subprocess, "run", run)
    kwargs = {} if kind == "default" else {"cog_path": output}
    assert helpers.convert_tif_to_cog(source, options=options, **kwargs) is None
    run.assert_called_once()
    assert output.read_bytes() == b"converted"
    assert not partial.exists()
    if kind != "in-place":
        assert source.read_bytes() == b"source"
    if legacy_options:
        assert options == [" -co COMPRESS=DEFLATE ", "-co", "TILED=YES"]


def test_cog_conversion_respects_no_overwrite(helpers, tmp_path, monkeypatch):
    source = tmp_path / "input.tif"
    output = tmp_path / "existing.tif"
    output.write_bytes(b"keep")
    run = Mock()
    monkeypatch.setattr(helpers.subprocess, "run", run)
    assert helpers.convert_tif_to_cog(source, output, overwrite=False) is None
    run.assert_not_called()
    assert output.read_bytes() == b"keep"


@pytest.mark.parametrize("failure", ["translation", "replacement", "missing-executable"])
def test_failed_cog_conversion_cleans_partial_and_preserves_output(
    helpers, tmp_path, monkeypatch, failure
):
    source = tmp_path / "input.tif"
    source.touch()
    output = tmp_path / "output.tif"
    output.write_bytes(b"keep")
    partial = tmp_path / "output.partial.tif"
    error = {
        "translation": subprocess.CalledProcessError(1, ["gdal_translate"]),
        "replacement": OSError("replacement failed"),
        "missing-executable": FileNotFoundError("gdal_translate is unavailable"),
    }[failure]

    def translate(argv, *, check):
        partial.write_bytes(b"incomplete")
        if failure != "replacement":
            raise error

    monkeypatch.setattr(helpers.subprocess, "run", Mock(side_effect=translate))
    if failure == "replacement":
        monkeypatch.setattr(helpers.os, "replace", Mock(side_effect=error))
    with pytest.raises(type(error)) as raised:
        helpers.convert_tif_to_cog(source, output)
    assert raised.value is error
    assert output.read_bytes() == b"keep"
    assert not partial.exists()


@pytest.mark.parametrize(
    "options,message",
    [("-co COMPRESS=LZW", "must be a list"), (["-co", 1], "entries must be strings")],
)
def test_cog_options_validation(helpers, tmp_path, monkeypatch, options, message):
    run = Mock()
    monkeypatch.setattr(helpers.subprocess, "run", run)
    with pytest.raises(ValueError, match=message):
        helpers.convert_tif_to_cog(tmp_path / "input.tif", options=options)
    run.assert_not_called()


@pytest.mark.parametrize("stdout,expected", [("LAYOUT=COG\n", True), ("Driver: GTiff\n", False)])
def test_confirm_cog_preserves_gdalinfo_contract(helpers, tmp_path, monkeypatch, stdout, expected):
    path = tmp_path / "input.tif"
    run = Mock(return_value=SimpleNamespace(stdout=stdout))
    monkeypatch.setattr(helpers.subprocess, "run", run)
    assert helpers.confirm_cog(path) is expected
    run.assert_called_once_with(["gdalinfo", str(path)], capture_output=True, text=True)


@pytest.fixture
def fake_gdal(monkeypatch):
    band = SimpleNamespace(ReadAsArray=Mock(return_value=sentinel.pixels))
    dataset = SimpleNamespace(
        RasterXSize=7, RasterYSize=11, GetRasterBand=Mock(return_value=band)
    )
    gdal = ModuleType("osgeo.gdal")
    gdal.GA_ReadOnly = 0
    gdal.UseExceptions = Mock()
    gdal.Open = Mock(return_value=dataset)
    osgeo = ModuleType("osgeo")
    osgeo.gdal = gdal
    monkeypatch.setitem(sys.modules, "osgeo", osgeo)
    monkeypatch.setitem(sys.modules, "osgeo.gdal", gdal)
    return SimpleNamespace(gdal=gdal, dataset=dataset, band=band)


@pytest.mark.parametrize("size", [(7, 11), (1, 1), (0, 0)])
def test_raster_validation_reads_first_and_last_pixels(helpers, tmp_path, fake_gdal, size):
    path = tmp_path / "input.tif"
    path.touch()
    fake_gdal.dataset.RasterXSize, fake_gdal.dataset.RasterYSize = size
    assert helpers.validate_tif_for_ingest(path) is None
    fake_gdal.gdal.UseExceptions.assert_called_once_with()
    fake_gdal.gdal.Open.assert_called_once_with(str(path), fake_gdal.gdal.GA_ReadOnly)
    fake_gdal.dataset.GetRasterBand.assert_called_once_with(1)
    assert fake_gdal.band.ReadAsArray.call_args_list == [
        call(0, 0, 1, 1), call(max(size[0] - 1, 0), max(size[1] - 1, 0), 1, 1)
    ]


@pytest.mark.parametrize("failure", ["open", "null-dataset", "missing-band", "first-pixel", "last-pixel"])
def test_raster_validation_adds_path_and_cause_to_errors(helpers, tmp_path, fake_gdal, failure):
    path = tmp_path / "input.tif"
    path.touch()
    error = RuntimeError("unreadable raster")
    if failure == "open":
        fake_gdal.gdal.Open.side_effect = error
    elif failure == "null-dataset":
        fake_gdal.gdal.Open.return_value = None
    elif failure == "missing-band":
        fake_gdal.dataset.GetRasterBand.return_value = None
    else:
        fake_gdal.band.ReadAsArray.side_effect = (
            [error] if failure == "first-pixel" else [sentinel.pixels, error]
        )
    with pytest.raises(RuntimeError, match="failed GDAL readability checks") as raised:
        helpers.validate_tif_for_ingest(path)
    assert str(path) in str(raised.value)
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert str(raised.value.__cause__) in str(raised.value)
    if failure in ("open", "first-pixel", "last-pixel"):
        assert raised.value.__cause__ is error


def test_missing_raster_is_reported_before_loading_gdal(helpers, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "osgeo", None)
    with pytest.raises(FileNotFoundError, match="Input TIFF does not exist"):
        helpers.validate_tif_for_ingest(tmp_path / "missing.tif")


def test_missing_gdal_has_geeviz_installation_guidance(catalog_helpers, tmp_path, monkeypatch):
    path = tmp_path / "input.tif"
    path.touch()
    monkeypatch.setitem(sys.modules, "osgeo", None)
    monkeypatch.setitem(sys.modules, "osgeo.gdal", None)
    with pytest.raises(ModuleNotFoundError, match="GDAL.*geeViz") as raised:
        catalog_helpers.validate_tif_for_ingest(path)
    assert "platform-compatible GDAL build" in str(raised.value)
    assert "ee-catalog-helpers" not in str(raised.value)
    assert isinstance(raised.value.__cause__, ModuleNotFoundError)


@pytest.fixture
def fake_asset_manager(monkeypatch):
    package = ModuleType("geeViz")
    package.__path__ = [str(ROOT)]
    manager = ModuleType("geeViz.assetManagerLib")
    manager.ingestFromGCSImagesAsBands = Mock()
    package.assetManagerLib = manager
    monkeypatch.setitem(sys.modules, "geeViz", package)
    monkeypatch.setitem(sys.modules, "geeViz.assetManagerLib", manager)
    return manager.ingestFromGCSImagesAsBands


@pytest.mark.parametrize("kwargs", [{}, {"overwrite": False}, {"overwrite": True}, {"overwrite": sentinel.overwrite}])
def test_planned_image_adapter_preserves_conversion_order_and_copies_properties(
    catalog_helpers, tmp_path, monkeypatch, fake_asset_manager, kwargs
):
    api = catalog_helpers
    profiles = _profiles(api, tmp_path)
    bands = api.build_planned_bands(
        reversed(profiles), {profile.name: tmp_path / f"{profile.name}.tif" for profile in profiles},
        "gs://bucket/data", {"red": 255, "green": 255},
    )
    properties = MappingProxyType({"system:time_start": "2024-01-01T00:00:00Z", "year": 2024})
    image = api.PlannedImage("example", "projects/example/assets/image", bands, properties)
    converted = []
    original_conversion = api.PlannedBand.as_ingest_entry

    def convert(band):
        entry = {**original_conversion(band), "gcsURI": f"gs://converted/{band.profile.name}.tif"}
        converted.append((band, entry))
        return entry

    monkeypatch.setattr(api.PlannedBand, "as_ingest_entry", convert)
    submitted_properties = []

    def submit(entries, asset_id, *, overwrite, properties):
        assert type(properties) is dict
        assert properties is not image.properties
        assert properties == dict(image.properties)
        submitted_properties.append(properties)
        properties.pop("system:time_start")
        return sentinel.task

    fake_asset_manager.side_effect = submit
    assert api.ingest_planned_image(image, **kwargs) is sentinel.task
    assert [band for band, entry in converted] == list(bands)
    assert [entry["bandName"] for band, entry in converted] == ["green", "red"]
    fake_asset_manager.assert_called_once_with(
        [entry for band, entry in converted], image.asset_id,
        overwrite=kwargs.get("overwrite", False), properties=submitted_properties[0],
    )
    actual_entries = fake_asset_manager.call_args.args[0]
    assert all(actual is entry for actual, (_, entry) in zip(actual_entries, converted))
    assert fake_asset_manager.call_args.kwargs["overwrite"] is kwargs.get("overwrite", False)
    assert dict(image.properties) == {"system:time_start": "2024-01-01T00:00:00Z", "year": 2024}


def test_planned_image_adapter_preserves_runtime_exceptions(catalog_helpers, fake_asset_manager):
    error = RuntimeError("submission failed")
    fake_asset_manager.side_effect = error
    image = catalog_helpers.PlannedImage("empty", "projects/example/assets/image", (), {})
    with pytest.raises(RuntimeError, match="submission failed") as raised:
        catalog_helpers.ingest_planned_image(image)
    assert raised.value is error

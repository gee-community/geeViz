"""Offline ingestion characterization; strict xfails track step 8 hardening.

The integration plan targets tileset_id, pyramiding_policy, and missing_data.
The REST reference and official Python CLI document camel-case output instead;
snake-case normalization still needs live verification (see the plan's notes).
Camel-case bandName/pyramidingPolicy/gcsURI/noDataValue remain public inputs.
"""

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[1]
ASSET = "projects/example/assets/collection/image"
URI = "gs://example/red.tif"


@pytest.fixture
def runtime(monkeypatch):
    ee = ModuleType("ee")
    ee.data = SimpleNamespace(
        ASSET_TYPE_FOLDER="FOLDER", ASSET_TYPE_IMAGE_COLL="IMAGE_COLLECTION",
        newTaskId=Mock(return_value=["task-123"]),
        startIngestion=Mock(return_value={"id": "task-123", "started": "OK"}),
    )
    package = ModuleType("geeViz")
    package.__path__ = [str(ROOT)]
    package.geeView = ModuleType("geeViz.geeView")
    monkeypatch.setitem(sys.modules, "ee", ee)
    monkeypatch.setitem(sys.modules, "geeViz", package)
    monkeypatch.setitem(sys.modules, "geeViz.geeView", package.geeView)
    spec = importlib.util.spec_from_file_location(
        "geeViz.assetManagerLib", ROOT / "assetManagerLib.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ee_asset_exists", Mock(return_value=False))
    monkeypatch.setattr(module, "create_image_collection", Mock())
    return SimpleNamespace(module=module, data=ee.data)


def _manifest(runtime):
    runtime.data.startIngestion.assert_called_once()
    task, manifest, overwrite = runtime.data.startIngestion.call_args.args
    assert task == "task-123"
    return manifest, overwrite


def _expected(uris, bands=None):
    return {
        "name": ASSET,
        "tilesets": [
            {"id": f"tileset_for_band{i}", "sources": [{"uris": [uri]}]}
            for i, uri in enumerate(uris, 1)
        ],
        "bands": bands if bands is not None else [
            {"tileset_id": f"tileset_for_band{i}", "id": f"Band{i}"}
            for i in range(1, len(uris) + 1)
        ],
    }


@pytest.mark.parametrize("kind", ["string", "strings", "dictionaries", "mixed"])
def test_supported_inputs_generate_complete_ordered_manifests(runtime, kind):
    uris = [URI] if kind == "string" else [URI, "gs://example/green.tif"]
    inputs = {
        "string": URI,
        "strings": list(uris),
        "dictionaries": [{"gcsURI": uri} for uri in uris],
        "mixed": [{"gcsURI": uris[0]}, uris[-1]],
    }
    runtime.module.ingestFromGCSImagesAsBands(inputs[kind], ASSET)
    assert _manifest(runtime) == (_expected(uris), False)
    runtime.data.newTaskId.assert_called_once_with(1)
    runtime.module.create_image_collection.assert_called_once_with(
        "projects/example/assets/collection"
    )


def test_dictionary_band_name_nodata_and_input_immutability(runtime):
    entries = [
        {"gcsURI": URI, "bandName": "red", "noDataValue": 0},
        {"gcsURI": "gs://example/green.tif", "bandName": 2, "noDataValue": -9999},
    ]
    original = deepcopy(entries)
    runtime.module.ingestFromGCSImagesAsBands(entries, ASSET)
    assert _manifest(runtime) == (
        _expected(
            [URI, "gs://example/green.tif"],
            [
                {"tileset_id": "tileset_for_band1", "id": "red", "missing_data": {"values": [0]}},
                {"tileset_id": "tileset_for_band2", "id": "2", "missing_data": {"values": [-9999]}},
            ],
        ),
        False,
    )
    assert entries == original


@pytest.mark.xfail(
    strict=True, raises=AssertionError,
    reason="step 8: planned normalization from pyramidingPolicy to pyramiding_policy",
)
def test_camel_case_policy_input_emits_python_manifest_schema(runtime):
    runtime.module.ingestFromGCSImagesAsBands(
        [{"gcsURI": URI, "bandName": "red", "pyramidingPolicy": "MODE", "noDataValue": 255}],
        ASSET,
    )
    assert _manifest(runtime) == (
        _expected([URI], [{
            "tileset_id": "tileset_for_band1", "id": "red",
            "pyramiding_policy": "MODE", "missing_data": {"values": [255]},
        }]),
        False,
    )


@pytest.mark.parametrize("exists,overwrite", [(False, False), (False, True), (True, True), (True, False)])
def test_existing_asset_and_overwrite_behavior(runtime, exists, overwrite, capsys):
    runtime.module.ee_asset_exists.return_value = exists
    runtime.module.ingestFromGCSImagesAsBands(URI, ASSET, overwrite=overwrite)
    if exists and not overwrite:
        runtime.data.newTaskId.assert_not_called()
        runtime.module.create_image_collection.assert_not_called()
        runtime.data.startIngestion.assert_not_called()
        assert f"{ASSET} already exists" in capsys.readouterr().out
    else:
        assert _manifest(runtime) == (_expected([URI]), overwrite)
    if overwrite:
        runtime.module.ee_asset_exists.assert_not_called()
    else:
        runtime.module.ee_asset_exists.assert_called_once_with(ASSET)


@pytest.mark.parametrize(
    "times",
    [
        {"system:time_start": "2024-01-01T00:00:00Z"},
        {"system:time_end": "2025-01-01T00:00:00Z"},
        {"system:time_start": 1704067200000, "system:time_end": 1735689600000},
    ],
)
def test_time_properties_are_mapped_into_manifest_fields(runtime, times):
    runtime.module.ingestFromGCSImagesAsBands(URI, ASSET, properties={"year": 2024, **times})
    expected = _expected([URI])
    expected["properties"] = {"year": 2024}
    for source, target in (("system:time_start", "start_time"), ("system:time_end", "end_time")):
        if source in times:
            expected[target] = times[source]
    assert _manifest(runtime) == (expected, False)


def test_ee_dates_are_formatted_without_loading_earth_engine(runtime):
    class Date:
        def __init__(self):
            self.patterns = []
            self.parts = []

        def format(self, pattern):
            self.patterns.append(pattern)
            return self

        def cat(self, part):
            self.parts.append(part)
            return self

        def getInfo(self):
            return "2024-01-01T00:00:00Z"

    Date.__module__ = "ee.ee_date"
    Date.__qualname__ = "Date"
    date = Date()
    runtime.module.ingestFromGCSImagesAsBands(
        URI, ASSET, properties={"system:time_start": date}
    )
    manifest, _ = _manifest(runtime)
    assert manifest["start_time"] == "2024-01-01T00:00:00Z"
    assert manifest["properties"] == {}
    assert date.patterns == ["YYYY-MM-dd", "HH:mm:SS"]
    assert date.parts == ["T", date, "Z"]


@pytest.mark.parametrize("properties", [None, {}, {"year": 2024}])
def test_optional_properties(runtime, properties):
    original = deepcopy(properties)
    runtime.module.ingestFromGCSImagesAsBands(URI, ASSET, properties=properties)
    expected = _expected([URI])
    if properties is not None:
        expected["properties"] = properties
    assert _manifest(runtime) == (expected, False)
    assert properties == original


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="step 8: caller URI lists are currently rewritten")
def test_caller_uri_list_is_not_modified(runtime):
    entries = [URI, "gs://example/green.tif"]
    original = deepcopy(entries)
    runtime.module.ingestFromGCSImagesAsBands(entries, ASSET)
    assert entries == original


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="step 8: caller time properties are currently popped")
def test_caller_properties_are_not_modified(runtime):
    properties = {
        "system:time_start": "2024-01-01T00:00:00Z",
        "system:time_end": "2025-01-01T00:00:00Z",
        "year": 2024,
    }
    original = deepcopy(properties)
    runtime.module.ingestFromGCSImagesAsBands(URI, ASSET, properties=properties)
    assert properties == original


def test_missing_gcs_uri_has_actionable_error_and_is_not_submitted(runtime):
    with pytest.raises(ValueError, match="key for 'gcsURI'"):
        runtime.module.ingestFromGCSImagesAsBands([{"bandName": "red"}], ASSET)
    runtime.data.startIngestion.assert_not_called()


@pytest.mark.parametrize(
    "entry",
    [
        {"gcsURI": None}, {"gcsURI": ""}, {"gcsURI": "https://example/red.tif"},
        {"gcsURI": URI, "bandName": ""},
        {"gcsURI": URI, "pyramidingPolicy": "INVALID"},
        {"gcsURI": URI, "noDataValue": "not numeric"},
    ],
)
@pytest.mark.xfail(
    strict=True, raises=AssertionError,
    reason="step 8: validate URI and optional band values before submission",
)
def test_malformed_entries_are_rejected(runtime, entry):
    try:
        runtime.module.ingestFromGCSImagesAsBands([entry], ASSET)
    except ValueError:
        runtime.data.startIngestion.assert_not_called()
    else:
        raise AssertionError("Malformed ingestion entry was accepted")


@pytest.mark.parametrize("entries", [None, 42])
@pytest.mark.xfail(strict=True, raises=TypeError, reason="step 8: malformed top-level inputs need ValueError diagnostics")
def test_malformed_input_container_has_value_error(runtime, entries):
    with pytest.raises(ValueError):
        runtime.module.ingestFromGCSImagesAsBands(entries, ASSET)
    runtime.data.startIngestion.assert_not_called()

"""Offline ingestion characterization tests for ingestFromGCSImagesAsBands.

Camel-case bandName/pyramidingPolicy/gcsURI/noDataValue remain public inputs;
the manifest uses the snake-case tileset_id/pyramiding_policy/missing_data
spellings (confirmed against the live Earth Engine API on 2026-11-19).
"""

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, call

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
        getAsset=Mock(), listAssets=Mock(return_value={}), createAsset=Mock(), copyAsset=Mock(),
    )
    ee.EEException = type("EEException", (Exception,), {})
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
    result = runtime.module.ingestFromGCSImagesAsBands(inputs[kind], ASSET)
    assert result == {"id": "task-123", "started": "OK"}
    assert _manifest(runtime) == (_expected(uris), False)
    runtime.data.newTaskId.assert_called_once_with(1)
    runtime.module.create_image_collection.assert_called_once_with(
        "projects/example/assets/collection"
    )


def test_dict_values_and_generators_are_accepted(runtime):
    # uploadToGEEAssetImagesAsBands passes tif_dict.values().
    tif_dict = {"a.tif": {"gcsURI": URI, "bandName": "red"}}
    runtime.module.ingestFromGCSImagesAsBands(tif_dict.values(), ASSET)
    manifest, _ = _manifest(runtime)
    assert manifest["bands"][0]["id"] == "red"
    assert manifest["tilesets"][0]["sources"] == [{"uris": [URI]}]


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


def test_none_nodata_is_omitted_and_numpy_scalars_accepted(runtime):
    import numpy as np

    entries = [
        {"gcsURI": URI, "bandName": "red", "noDataValue": None},
        {"gcsURI": "gs://example/green.tif", "bandName": "green", "noDataValue": np.int64(7)},
    ]
    runtime.module.ingestFromGCSImagesAsBands(entries, ASSET)
    manifest, _ = _manifest(runtime)
    assert "missing_data" not in manifest["bands"][0]
    assert manifest["bands"][1]["missing_data"] == {"values": [7]}
    assert type(manifest["bands"][1]["missing_data"]["values"][0]) is int
    assert entries[0]["noDataValue"] is None


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


def test_caller_uri_list_is_not_modified(runtime):
    entries = [URI, "gs://example/green.tif"]
    original = deepcopy(entries)
    runtime.module.ingestFromGCSImagesAsBands(entries, ASSET)
    assert entries == original


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
def test_malformed_entries_are_rejected(runtime, entry):
    try:
        runtime.module.ingestFromGCSImagesAsBands([entry], ASSET)
    except ValueError:
        runtime.data.startIngestion.assert_not_called()
    else:
        raise AssertionError("Malformed ingestion entry was accepted")


@pytest.mark.parametrize("entries", [None, 42])
def test_malformed_input_container_has_value_error(runtime, entries):
    with pytest.raises(ValueError):
        runtime.module.ingestFromGCSImagesAsBands(entries, ASSET)
    runtime.data.startIngestion.assert_not_called()


# --- strict GCS upload (step 6) -------------------------------------------

@pytest.fixture
def gcloud(runtime, monkeypatch, tmp_path):
    tif = tmp_path / "a.tif"
    tif.write_bytes(b"x")
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr(runtime.module.subprocess, "run", run)
    monkeypatch.setattr(
        runtime.module.shutil, "which",
        lambda name: "C:/g/gcloud.cmd" if name == "gcloud.cmd" else None,
    )
    return SimpleNamespace(module=runtime.module, tif=tif, run=run, monkeypatch=monkeypatch)


@pytest.mark.parametrize("overwrite,tail", [(False, ["-n"]), (True, [])])
def test_upload_tif_runs_argument_list_without_shell(gcloud, overwrite, tail):
    # The no-clobber check (``storage ls``) reports a missing object (exit 1).
    gcloud.run.side_effect = lambda cmd, **kw: SimpleNamespace(
        returncode=1 if cmd[1:3] == ["storage", "ls"] else 0, stdout="", stderr=""
    )
    gcloud.module.upload_tif(gcloud.tif, "gs://b/o/a.tif", overwrite=overwrite)
    cp = call(
        ["C:/g/gcloud.cmd", "storage", "cp", str(gcloud.tif), "gs://b/o/a.tif"] + tail,
        capture_output=True, text=True,
    )
    assert gcloud.run.call_args_list[-1] == cp
    assert gcloud.run.call_count == (2 if not overwrite else 1)


def test_upload_tif_refuses_to_skip_existing_object(gcloud):
    # ``storage ls`` succeeds -> object exists; ``cp -n`` would silently skip it.
    with pytest.raises(FileExistsError, match="overwrite=True"):
        gcloud.module.upload_tif(gcloud.tif, "gs://b/o/a.tif")
    assert all(c.args[0][2] != "cp" for c in gcloud.run.call_args_list)


def test_upload_tif_validation(gcloud, tmp_path):
    with pytest.raises(FileNotFoundError, match="Input TIFF"):
        gcloud.module.upload_tif(tmp_path / "missing.tif", "gs://b/a.tif")
    for bad in ("s3://b/a.tif", "gs://bucket", "gs://bucket/", "gs://b/folder/", None):
        with pytest.raises(ValueError):
            gcloud.module.upload_tif(gcloud.tif, bad)
    gcloud.monkeypatch.setattr(gcloud.module.shutil, "which", lambda name: None)
    with pytest.raises(FileNotFoundError, match="gcloud"):
        gcloud.module.upload_tif(gcloud.tif, "gs://b/a.tif")
    gcloud.run.assert_not_called()


def test_upload_tif_failure_is_actionable(gcloud):
    gcloud.run.side_effect = None
    gcloud.run.return_value = SimpleNamespace(returncode=2, stdout="out", stderr="denied")
    with pytest.raises(RuntimeError, match=r"Exit code: 2[\s\S]*stdout: out[\s\S]*stderr: denied"):
        gcloud.module.upload_tif(gcloud.tif, "gs://b/a.tif")


def test_legacy_upload_tif_to_gcs_unchanged(runtime, monkeypatch):
    popen = Mock()
    monkeypatch.setattr(runtime.module.subprocess, "Popen", popen)
    runtime.module.uploadTifToGCS("a.tif", "bucket/", overwrite=False)
    popen.assert_called_once_with("gcloud storage cp a.tif gs://bucket -n", shell=True)


# --- Earth Engine asset operations (step 7) ------------------------------

PROJ = "projects/p/assets"


NOT_FOUND = "Asset 'x' does not exist or doesn't allow this operation."


def _ee_error(msg):
    return sys.modules["ee"].EEException(msg)


def _raiser(msg):
    def raise_it(*args, **kwargs):
        raise _ee_error(msg)
    return raise_it


def test_get_asset_if_exists_distinguishes_not_found(runtime):
    m, d = runtime.module, runtime.data
    d.getAsset.side_effect = _ee_error("Asset 'x' not found.")
    assert m.get_asset_if_exists("x") is None
    d.getAsset.side_effect = _ee_error("Permission denied")
    with pytest.raises(RuntimeError, match="Failed to get"):
        m.get_asset_if_exists("x")
    d.getAsset.side_effect = None
    d.getAsset.return_value = ["not", "a", "dict"]
    with pytest.raises(RuntimeError, match="Unexpected"):
        m.get_asset_if_exists("x")
    with pytest.raises(RuntimeError, match="Unexpected"):
        m.get_asset("x")
    d.getAsset.return_value = {"type": "IMAGE"}
    assert m.get_asset("x") == {"type": "IMAGE"}


def test_get_asset_wraps_ee_errors(runtime):
    runtime.data.getAsset.side_effect = _ee_error(NOT_FOUND)
    with pytest.raises(RuntimeError) as info:
        runtime.module.get_asset("x")
    assert isinstance(info.value.__cause__, sys.modules["ee"].EEException)


def test_ensure_asset_path_creates_only_missing_folders_in_order(runtime):
    existing = {f"{PROJ}/a": {"type": "FOLDER"}}

    def get(path):
        if path in existing:
            return existing[path]
        raise _ee_error(NOT_FOUND)

    runtime.data.getAsset.side_effect = get
    runtime.module.ensure_asset_path(f"{PROJ}/a/b/c")
    assert [c.args for c in runtime.data.createAsset.call_args_list] == [
        ({"type": "FOLDER"}, f"{PROJ}/a/b"), ({"type": "FOLDER"}, f"{PROJ}/a/b/c"),
    ]


def test_ensure_asset_path_validation_and_type_conflicts(runtime):
    for bad in ("users/x/a", "projects/p/assets", "projects/p/foo/a", "projects/p/assets//a", None):
        with pytest.raises(ValueError):
            runtime.module.ensure_asset_path(bad)
    with pytest.raises(ValueError):
        runtime.module.ensure_parent_asset_path(f"{PROJ}/only")
    runtime.data.getAsset.return_value = {"type": "IMAGE"}
    with pytest.raises(RuntimeError, match="not a folder"):
        runtime.module.ensure_asset_folder(f"{PROJ}/a")
    runtime.data.createAsset.assert_not_called()


def test_ensure_parent_asset_path_creates_parent_only(runtime):
    runtime.data.getAsset.side_effect = _raiser(NOT_FOUND)
    runtime.module.ensure_parent_asset_path(f"{PROJ}/a/img")
    assert [c.args[1] for c in runtime.data.createAsset.call_args_list] == [f"{PROJ}/a"]


def test_child_listing_paginates_and_ignores_malformed_items(runtime):
    runtime.data.listAssets.side_effect = [
        {"assets": [{"id": f"{PROJ}/c/b"}, {"name": f"{PROJ}/c/a"}, "junk", {"id": 5}], "nextPageToken": "t"},
        {"assets": [{"id": f"{PROJ}/c/z"}]},
    ]
    assert runtime.module.list_child_asset_basenames(f"{PROJ}/c") == {"a", "b", "z"}
    assert runtime.data.listAssets.call_args_list[1].args[0] == {"parent": f"{PROJ}/c", "pageToken": "t"}
    runtime.data.listAssets.side_effect = None
    runtime.data.listAssets.return_value = "bad"
    with pytest.raises(RuntimeError, match="Unexpected"):
        runtime.module.list_child_asset_basenames("x")


def test_find_missing_children_is_sorted(runtime):
    runtime.data.listAssets.side_effect = [
        {"assets": [{"id": "s/c"}, {"id": "s/a"}, {"id": "s/b"}]}, {"assets": [{"id": "d/b"}]},
    ]
    assert runtime.module.find_missing_collection_children("s", "d") == ["a", "c"]


def test_copy_collection_creates_destination_and_forwards_overwrite(runtime):
    runtime.data.getAsset.side_effect = _raiser(NOT_FOUND)
    runtime.data.listAssets.return_value = {"assets": [{"id": "s/b"}, {"id": "s/a"}]}
    runtime.module.copy_collection("s", "d", overwrite=True)
    runtime.data.createAsset.assert_called_once_with({"type": "IMAGE_COLLECTION"}, "d")
    assert [c.args for c in runtime.data.copyAsset.call_args_list] == [
        ("s/a", "d/a", True), ("s/b", "d/b", True),
    ]


def test_copy_collection_default_does_not_overwrite_and_validates_destination(runtime):
    runtime.data.getAsset.return_value = {"type": "IMAGE_COLLECTION"}
    runtime.data.listAssets.return_value = {"assets": [{"id": "s/a"}]}
    runtime.module.copy_collection("s", "d")
    runtime.data.copyAsset.assert_called_once_with("s/a", "d/a", False)
    runtime.data.getAsset.return_value = {"type": "TABLE"}
    with pytest.raises(RuntimeError, match="not an ImageCollection"):
        runtime.module.copy_collection("s", "d")


def test_copy_collection_aggregates_child_failures(runtime):
    runtime.data.getAsset.return_value = {"type": "IMAGE_COLLECTION"}
    runtime.data.listAssets.return_value = {"assets": [{"id": f"s/{n}"} for n in "abc"]}

    def copy(source, destination, overwrite):
        if source != "s/b":
            raise _ee_error(f"boom {source}")

    runtime.data.copyAsset.side_effect = copy
    with pytest.raises(RuntimeError, match=r"Failed to copy 2 of 3[\s\S]*a: boom s/a[\s\S]*c: boom s/c"):
        runtime.module.copy_collection("s", "d")
    assert runtime.data.copyAsset.call_count == 3


def test_copy_collection_reports_every_failed_child(runtime):
    # every failure is named, not the first ten
    runtime.data.getAsset.return_value = {"type": "IMAGE_COLLECTION"}
    names = [f"img{i:02d}" for i in range(15)]
    runtime.data.listAssets.return_value = {"assets": [{"id": f"s/{n}"} for n in names]}
    runtime.data.copyAsset.side_effect = _raiser("boom")
    with pytest.raises(RuntimeError) as info:
        runtime.module.copy_collection("s", "d")
    assert "Failed to copy 15 of 15" in str(info.value)
    for n in names:
        assert f"{n}: boom" in str(info.value), n


@pytest.mark.parametrize("asset_type", ["IMAGE", "TABLE", "FEATURE_COLLECTION"])
def test_promote_copies_single_assets(runtime, asset_type):
    def get(path):
        if path == f"{PROJ}/tmp":
            return {"type": asset_type}
        raise _ee_error(NOT_FOUND)

    runtime.data.getAsset.side_effect = get
    runtime.module.promote_assets_to_catalog(f"{PROJ}/tmp", f"{PROJ}/cat/final", overwrite=True)
    runtime.data.createAsset.assert_called_once_with({"type": "FOLDER"}, f"{PROJ}/cat")
    runtime.data.copyAsset.assert_called_once_with(f"{PROJ}/tmp", f"{PROJ}/cat/final", True)


def test_promote_collection_and_unsupported_type(runtime):
    def get(path):
        if path in (f"{PROJ}/tmp", f"{PROJ}/cat"):
            return {"type": "IMAGE_COLLECTION"}
        raise _ee_error(NOT_FOUND)

    runtime.data.getAsset.side_effect = get
    runtime.data.listAssets.return_value = {"assets": [{"id": f"{PROJ}/tmp/x"}]}
    runtime.module.promote_assets_to_catalog(f"{PROJ}/tmp", f"{PROJ}/cat/final")
    runtime.data.copyAsset.assert_called_once_with(f"{PROJ}/tmp/x", f"{PROJ}/cat/final/x", False)
    runtime.data.getAsset.side_effect = None
    runtime.data.getAsset.return_value = {"type": "FOLDER"}
    with pytest.raises(RuntimeError, match="Unsupported"):
        runtime.module.promote_assets_to_catalog(f"{PROJ}/tmp", f"{PROJ}/cat/final")


def test_normalize_type_and_basename(runtime):
    m = runtime.module
    assert m.normalize_asset_type("IMAGE_COLLECTION") == "imagecollection"
    assert m.normalize_asset_type(None) == "" and m.normalize_asset_type(3) == ""
    assert m.asset_basename({"id": "a/b/c"}) == "c" and m.asset_basename({"name": "x/y"}) == "y"
    assert m.asset_basename({"id": 3}) == ""


@pytest.mark.parametrize(
    "message",
    [
        "Cloud project not found",
        "Permission denied on resource project 404",
        "Quota exceeded for projects/404-not-found",
        "HTTP 404 from proxy",
        "Asset quota not found",
    ],
)
def test_unrelated_errors_are_not_treated_as_missing_asset(runtime, message):
    runtime.data.getAsset.side_effect = _ee_error(message)
    with pytest.raises(RuntimeError, match="Failed to get"):
        runtime.module.get_asset_if_exists("projects/p/assets/404")


@pytest.mark.parametrize(
    "message",
    [
        "Asset 'projects/p/assets/a' does not exist or doesn't allow this operation.",
        "Asset 'projects/p/assets/404' not found.",
        "Requested asset not found.",
    ],
)
def test_earth_engine_missing_asset_messages_are_recognized(runtime, message):
    runtime.data.getAsset.side_effect = _ee_error(message)
    assert runtime.module.get_asset_if_exists("projects/p/assets/a") is None

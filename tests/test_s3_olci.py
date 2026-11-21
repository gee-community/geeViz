"""Sentinel-3 OLCI as TOA reflectance: gil.getS3 (2026-11-17).

An AskTerra session converted COPERNICUS/S3/OLCI radiance to reflectance
by hand (four bands, fixed solar irradiances, solar zenith from the time
and latitude) and mapped NDVI and its change. It looked right and was
not: in many images of that collection Earth Engine stores the bands one
too high. The band named Oa17 (865 nm) holds Oa16's data (779 nm), the
one named Oa08 (665 nm) holds Oa07's (620 nm), Oa01 holds a fill value
of about -2e9 and Oa10 holds fill or 0. Shifted and correct images
alternate from 2018 to at least October 2026, so a composite mixes them.

Found from the spectra (live checks, run by hand in Earth Engine):
read as labeled, the O2-A absorption dip appears in "Oa14" rather than
Oa13, the 940 nm water vapor dip in "Oa21" rather than Oa20, and "Oa17"
reads about 1.17x its neighbors over cropland, forest, desert and white
sand alike. Relabeled, shifted and correct images of White Sands agree
within about 2% in every band, and Iowa cropland NDVI from getS3 (0.76)
matches Sentinel-2 TOA (0.77).

These tests cover what can be checked without Earth Engine: the
irradiance table, the relabeling, and the wiring of getS3.
"""
import inspect
import re
from pathlib import Path

import pytest

import geeViz.getImagesLib as gil

ROOT = Path(__file__).resolve().parents[1]
INSTR = (ROOT / "mcp" / "agent-instructions.md").read_text(encoding="utf-8")


def _code(fn) -> str:
    """Source of fn without comments or docstrings."""
    src = inspect.getsource(fn)
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    return re.sub(r"(?m)#.*$", "", src)


def test_the_code_stripper_removes_comments_and_docstrings():
    def f():
        """band = orig.where(shifted, nxt)"""
        # band = orig.where(shifted, nxt)
        return 1
    assert "where" not in _code(f)


def test_irradiances_are_the_esa_table_per_band_and_spacecraft():
    """ESA/ACRI-ST OMPC.ACR.MEM.018 Table 1, Thuillier-2003, in mW m-2 nm-1.
    The SNAP 'default' array lists 882.8 for every band from Oa15 up and is
    off by a band below that; it must not creep back in."""
    e0 = gil.s3OLCISolarIrradiance
    assert set(e0) == {"S3A", "S3B"}
    for sc in e0:
        assert len(e0[sc]) == 21
    assert e0["S3A"][3] == 1935      # Oa04, 490 nm
    assert e0["S3A"][7] == 1530      # Oa08, 665 nm
    assert e0["S3A"][16] == 960      # Oa17, 865 nm
    assert e0["S3A"][20] == 700      # Oa21, 1020 nm
    assert e0["S3B"][0] == 1535      # Oa01 differs most between the two
    assert 882.8 not in e0["S3A"] and 882 not in e0["S3A"]
    assert len(gil.s3OLCIWavelengths) == 21 and gil.s3OLCIWavelengths[16] == 865


def test_shifted_pixels_take_the_next_bands_data():
    code = _code(gil.s3OLCIFixBandShift)
    # Detected per pixel from the fill value in Oa01, not by date: shifted
    # and correct images alternate.
    assert 'img.select(["Oa01_radiance"]).lt(-1e6)' in code
    assert "nxt = img.select([s3OLCIRadianceBands[i + 1]]) if i < 20 else orig" in code
    assert "band = orig.where(shifted, nxt)" in code
    # Oa09 (index 8) and Oa21 (index 20) do not exist in a shifted image.
    assert "if i in (8, 20):" in code and "band.updateMask(shifted.Not())" in code
    # Fill and zeros are missing data in every band.
    assert "fixed.updateMask(fixed.gt(0))" in code


def test_reflectance_fixes_the_shift_first_and_uses_the_spacecrafts_irradiance():
    code = _code(gil.s3OLCIToTOA)
    assert code.index("s3OLCIFixBandShift(img)") < code.index(".multiply(math.pi)")
    assert 'ee.String(img.get("spacecraft")).equals("S3B")' in code
    assert "divide(e0.multiply(cosSZA))" in code and "multiply(d.pow(2))" in code
    assert 's3OLCIQualityBits["invalid"]' in code


def test_common_band_names_point_at_the_right_wavelengths():
    names = gil.s3OLCICommonBandNames
    wl = dict(zip(gil.s3OLCIBandNames, gil.s3OLCIWavelengths))
    expect = {"cb": 442.5, "blue": 490, "green": 560, "red": 665, "re1": 708.75, "re2": 753.75, "re3": 778.75, "nir": 865}
    assert {v: wl[k] for k, v in names.items()} == expect


def test_get_s3_wiring():
    code = _code(gil.getS3)
    assert 'ee.ImageCollection("COPERNICUS/S3/OLCI")' in code
    assert "s3s.map(s3OLCIToTOA)" in code
    assert "applyCloudScoreAlgorithm(" in code and "s3OLCICloudScore," in code
    assert 's3OLCIQualityBits["bright"]' in code
    assert inspect.signature(gil.getS3).parameters["cloudMaskMethod"].default == "cloudScore"


def test_an_unknown_cloud_mask_method_is_refused():
    with pytest.raises(ValueError, match="cloudMaskMethod"):
        gil.getS3(None, "2025-07-01", "2025-07-02", cloudMaskMethod="fmask")


def test_the_agent_is_told_to_use_get_s3():
    row = next(l for l in INSTR.splitlines() if l.startswith('| "Sentinel-3"'))
    assert "gil.getS3(" in row and "Never load `COPERNICUS/S3/OLCI` yourself" in row
    assert "snow" in row

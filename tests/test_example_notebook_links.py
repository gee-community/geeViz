"""Every example notebook opens in Colab and links its source on GitHub, and
installs its package when it is missing (as on Colab), so the Colab link runs."""
import json
import pathlib

import pytest

EXAMPLES = pathlib.Path(__file__).resolve().parents[1] / "examples"
NOTEBOOKS = sorted(EXAMPLES.glob("*.ipynb"))


def test_there_are_notebooks():
    assert len(NOTEBOOKS) > 5


@pytest.mark.parametrize("nb", NOTEBOOKS, ids=lambda p: p.name)
def test_notebook_has_colab_and_github_links_and_installs(nb):
    cells = json.loads(nb.read_text(encoding="utf-8"))["cells"]
    md = "".join("".join(c["source"]) for c in cells if c["cell_type"] == "markdown")
    assert "https://colab.research.google.com/github/gee-community/geeViz/blob/master/examples/%s)" % nb.name in md
    assert "https://github.com/" in md and "/blob/master/examples/%s)" % nb.name in md
    code = ["".join(c["source"]) for c in cells if c["cell_type"] == "code"]
    assert any("except ImportError" in c and "pip" in c for c in code), "no install step for Colab"

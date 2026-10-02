"""An unknown grouping label is refused, not silently dropped.

EVALIDator ignores an rselected/cselected/pselected it does not know and
answers ungrouped. "Forest-type group" (the label is "Forest type
group") came back as the Utah total -- 17.87M acres -- shaped like a
breakdown, with nothing to say the grouping was ignored. estimate() now
checks labels against the bundled catalog before anything is sent.
"""
import pytest

from geeViz.fsInsights import fia


@pytest.fixture
def no_network(monkeypatch):
    """Validation must fail before any request leaves."""
    def boom(*a, **k):
        raise AssertionError("a request was sent for an invalid grouping")
    monkeypatch.setattr(fia, "get_json", boom)


@pytest.mark.parametrize("which", ["rselected", "cselected", "pselected"])
def test_a_near_miss_label_is_refused_with_the_real_one(which, no_network):
    with pytest.raises(fia.FIAValidationError) as ei:
        fia.estimate(492022, 2, **{which: "Forest-type group"})
    msg = str(ei.value)
    assert which in msg and "'Forest type group'" in msg


def test_a_nonsense_label_points_at_find_groupings(no_network):
    with pytest.raises(fia.FIAValidationError) as ei:
        fia.estimate(492022, 2, rselected="Not a real grouping zzz")
    assert "find_groupings" in str(ei.value) or "Did you mean" in str(ei.value)


def test_real_labels_pass_validation(monkeypatch):
    sent = {}

    def fake_get_json(url, params=None, **k):
        sent.update(params or {})
        raise fia.FIAValidationError("stop here")    # validation passed; request built
    monkeypatch.setattr(fia, "get_json", fake_get_json)
    with pytest.raises(fia.FIAValidationError, match="stop here"):
        fia.estimate(492022, 2, rselected="Forest type group",
                     cselected="Ownership group - Major")
    assert sent.get("rselected") == "Forest type group"

"""run_code tells the model what actually went wrong, so it fixes it in one step.

Daily review 2026-10-12:

- A session moved to another server between turns. Its variables were
  gone, the model got a bare NameError and spent a turn probing with
  globals() and dir() instead of re-creating them.
- ee.Geometry.BBox(...) builds a planar box. Its area(), perimeter(),
  centroid(), intersection() and union() fail with "specify a non-zero
  error margin", which names neither the cause nor the fix; three
  sessions in two environments hit it.
- A classifier's confusionMatrix() is its accuracy on its own training
  data, and an answer reported it as cross-validation accuracy.
"""
import asyncio
import json
import textwrap

import pytest

import geeViz.mcp.server as srv


def _run(code, sid):
    return json.loads(asyncio.run(srv.run_code(textwrap.dedent(code), session_id=sid)))


# --- variables lost between turns -------------------------------------------

def test_name_never_bound_in_this_session_explains_lost_state():
    out = _run("print(study_area_from_last_turn)", "recovery-lost")
    assert out["success"] is False
    err = out["error"]
    assert "NameError" in err, "the original traceback is kept"
    hint, sep, _ = err.partition("--- original traceback below ---")
    assert sep, "a hint was prepended"
    assert "study_area_from_last_turn" in hint
    assert "re-run" in err.lower() and "earlier" in err.lower()
    assert "globals()" in err, "names the probing the hint replaces"


def test_name_bound_earlier_in_this_process_gets_no_lost_state_hint():
    # Bound in this process, then deleted by the user's own code: that is
    # not lost state, and saying so would send the model the wrong way.
    assert _run("kept = 1", "recovery-bound")["success"] is True
    out = _run("del kept\nprint(kept)", "recovery-bound")
    assert out["success"] is False
    assert "NameError" in out["error"]
    assert "--- original traceback below ---" not in out["error"]


def test_history_recovered_after_a_restart_still_gets_the_hint():
    # A restart reloads the code history from disk but not the variables,
    # so a name that history bound is exactly the lost-state case.
    sid = "recovery-restart"
    assert _run("made_before_restart = 1", sid)["success"] is True
    srv._sessions.pop(sid)  # what a restart does to in-memory state
    out = _run("print(made_before_restart)", sid)
    assert out["success"] is False
    assert srv._sessions[sid].code_history, "history was recovered from disk"
    hint, sep, _ = out["error"].partition("--- original traceback below ---")
    assert sep, "a hint was prepended"
    assert "made_before_restart" in hint


def test_other_errors_are_untouched():
    out = _run("1 / 0", "recovery-other")
    assert "ZeroDivisionError" in out["error"]
    assert "--- original traceback below ---" not in out["error"]


# --- planar geometry operations -----------------------------------------------

MARGIN_ERROR = (
    "ee.ee_exception.EEException: Geometry.area: Unable to perform this "
    "geometry operation. Please specify a non-zero error margin."
)


def test_error_margin_failure_gets_the_fix():
    out = srv._translate_ee_error(MARGIN_ERROR)
    hint, sep, _ = out.partition("--- original traceback below ---")
    assert sep, "a hint was prepended"
    assert "maxError" in hint
    assert "BBox" in hint, "names the usual cause"
    assert MARGIN_ERROR in out, "original error preserved"


@pytest.mark.parametrize("op", ["intersection", "union", "centroid", "perimeter"])
def test_every_operation_with_that_error_is_covered(op):
    text = MARGIN_ERROR.replace("Geometry.area", f"Geometry.{op}")
    assert "maxError" in srv._translate_ee_error(text)


# --- training accuracy is not validation accuracy ----------------------------

def _notes(code):
    return [w for w in srv._check_code_patterns(textwrap.dedent(code))
            if "confusionMatrix" in w]


def test_confusion_matrix_call_is_flagged_as_training_accuracy():
    notes = _notes("""
        rf = ee.Classifier.smileRandomForest(50).train(samples, 'label', bands)
        cm = rf.confusionMatrix()
        print(cm.accuracy().getInfo())
    """)
    assert len(notes) == 1
    note = notes[0]
    assert not note.startswith("BLOCKED"), "a note, not a refusal"
    assert "training" in note and "errorMatrix" in note


def test_held_out_error_matrix_is_not_flagged():
    assert _notes("""
        test = holdout.classify(rf)
        em = test.errorMatrix('label', 'classification')
        print(em.accuracy().getInfo())
    """) == []


def test_the_note_reaches_the_model():
    # Wiring: the note must land in the run_code result, not just the helper.
    code = """
        class _Fake:
            def confusionMatrix(self):
                return 'cm'
        print(_Fake().confusionMatrix())
    """
    out = _run(code, "recovery-cm")
    assert out["success"] is True
    assert "errorMatrix" in out["stderr"]


def test_a_builtin_the_sandbox_leaves_out_is_not_called_lost_state():
    # The model called locals() in a replay (2026-10-26) and was told a
    # server restart had erased it; prod had globals 6 times, getattr 5.
    sess = srv._get_session("recovery-builtin")
    err = srv._lost_state_hint("NameError: name 'locals' is not defined", sess)
    assert "builtin that run_code does not provide" in err
    assert "restart" not in err

import pytest
from evaluation import evaluate_notes

GOLD = [{"pitch": 69, "start": .1, "end": 1.1}]


def test_missing_prediction_is_counted_as_failure_not_skipped():
    with pytest.warns(UserWarning):
        scores = evaluate_notes(GOLD, [])
    assert scores["onset_only"]["f1"] == 0
    assert scores["predicted_notes"] == 0


def test_offset_errors_do_not_disappear_in_onset_only_scores():
    scores = evaluate_notes(GOLD, [{"pitch": 69, "start": .1, "end": .3}])
    assert scores["onset_only"]["f1"] == 1
    assert scores["onset_and_offset"]["f1"] == 0


def test_wrong_pitch_is_not_a_match():
    assert evaluate_notes(GOLD, [{"pitch": 72, "start": .1, "end": 1.1}])["onset_only"]["f1"] == 0


def test_nan_and_missing_gold_are_rejected():
    with pytest.raises(ValueError):
        evaluate_notes([], GOLD)
    with pytest.raises(ValueError):
        evaluate_notes(GOLD, [{"pitch": 69, "start": float("nan"), "end": 1.1}])

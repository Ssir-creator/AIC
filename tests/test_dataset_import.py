import pytest
from scripts.prepare_guitarset import convert_annotations


def document(events, duration=2):
    return {"file_metadata":{"duration":duration},"annotations":[{"namespace":"note_midi","data":events}]}


def test_note_annotation_conversion_preserves_independent_pitch_and_timing():
    result = convert_annotations(document([{"time":.5,"duration":.3,"value":67.05}]),2)
    assert result == [{"pitch":67.05,"start":.5,"end":.8}]


def test_truncated_fixture_is_rejected():
    with pytest.raises(ValueError,match="时长"):
        convert_annotations(document([],32),2)


def test_corrupt_pitch_is_rejected_without_silent_filtering():
    with pytest.raises(ValueError,match="异常"):
        convert_annotations(document([{"time":.5,"duration":.3,"value":120.05}]),2)


def test_missing_and_duplicate_annotations_are_rejected():
    with pytest.raises(ValueError,match="缺少"):
        convert_annotations(document([]),2)
    event = {"time":.5,"duration":.3,"value":67.05}
    with pytest.raises(ValueError,match="重复"):
        convert_annotations(document([event,event]),2)

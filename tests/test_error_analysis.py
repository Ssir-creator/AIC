from scripts.analyze_errors import analyze


def test_review_hint_analysis_preserves_matches_and_offset_errors():
    gold = [{"pitch":69,"start":.1,"end":1.1}]
    predicted = [{"pitch":69,"start":.1,"end":.5,"velocity":80},
                 {"pitch":72,"start":1.2,"end":1.3,"velocity":30}]
    result = analyze(gold,predicted)
    assert result["onset_pitch_matched"] == 1
    assert result["matched_notes_with_offset_mismatch"] == 1
    assert result["unmatched_predictions"] == 1
    assert result["review_hints"]["flagged_unmatched"] == 1
    assert result["review_hints"]["unmatched_fraction_among_flagged"] == 1

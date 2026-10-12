"""Shared note metrics. Gold must be independent of model predictions."""
import math
import mir_eval
import numpy as np

PROTOCOL = "mir_eval: 50ms onset, 50 cent pitch; offset max(50ms,20% reference duration)"


def arrays(notes):
    for n in notes:
        if not all(math.isfinite(float(n[k])) for k in ("pitch", "start", "end")):
            raise ValueError("音符包含非有限值")
        if n["start"] < 0 or n["end"] <= n["start"] or not 21 <= n["pitch"] <= 108:
            raise ValueError("音符音高或时序无效")
    ordered = sorted(notes, key=lambda n: (n["start"], n["pitch"]))
    intervals = np.array([[n["start"], n["end"]] for n in ordered], dtype=float).reshape(-1, 2)
    pitches = np.array([440 * 2 ** ((n["pitch"] - 69) / 12) for n in ordered])
    return intervals, pitches


def evaluate_notes(gold, predicted):
    if not gold:
        raise ValueError("独立标注不能为空")
    ref_i, ref_p = arrays(gold)
    est_i, est_p = arrays(predicted)
    scores = {"reference_notes": len(gold), "predicted_notes": len(predicted)}
    for name, ratio in [("onset_only", None), ("onset_and_offset", .2)]:
        precision, recall, f1, overlap = mir_eval.transcription.precision_recall_f1_overlap(
            ref_i, ref_p, est_i, est_p, offset_ratio=ratio)
        scores[name] = {"precision": float(precision), "recall": float(recall),
                        "f1": float(f1), "overlap": float(overlap)}
    return scores

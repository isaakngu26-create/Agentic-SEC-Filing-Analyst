"""Self-evaluation rubric — scores LLM memo output against extracted filing data."""

from __future__ import annotations

from typing import Any

from evaluation.criteria import RUBRIC_CRITERIA, RUBRIC_THRESHOLD
from evaluation.grounding import verify_numeric_grounding, verify_segment_mentions
from evaluation.llm_judge import judge_memo_with_llm

__all__ = ["RUBRIC_CRITERIA", "RUBRIC_THRESHOLD", "evaluate_memo"]


def evaluate_memo(memo: str, payload: dict[str, Any], use_llm_judge: bool = True) -> dict[str, Any]:
    numeric_check = verify_numeric_grounding(memo, payload)
    segment_check = verify_segment_mentions(memo, payload)

    llm_result: dict[str, Any] = {"scores": {}, "explanations": {}, "overall_feedback": ""}
    if use_llm_judge:
        try:
            llm_result = judge_memo_with_llm(memo, payload)
        except Exception as exc:
            llm_result["judge_error"] = str(exc)

    llm_scores = llm_result.get("scores", {})

    algo_ground = numeric_check["score"]
    llm_ground = float(llm_scores.get("data_grounding", algo_ground))
    scores = {
        "data_grounding": round(0.5 * algo_ground + 0.5 * llm_ground, 3),
    }

    algo_seg = segment_check["score"]
    llm_seg = float(llm_scores.get("segment_coverage", algo_seg))
    scores["segment_coverage"] = round(0.4 * algo_seg + 0.6 * llm_seg, 3)

    for cid in ("trend_analysis", "material_changes", "clarity", "source_attribution"):
        scores[cid] = float(llm_scores.get(cid, 0.0))

    weighted = sum(scores[c["id"]] * c["weight"] for c in RUBRIC_CRITERIA)

    return {
        "scores": scores,
        "weighted_score": round(weighted, 3),
        "passes": weighted >= RUBRIC_THRESHOLD,
        "threshold": RUBRIC_THRESHOLD,
        "algorithmic_checks": {
            "numeric_grounding": numeric_check,
            "segment_mentions": segment_check,
        },
        "llm_judge": llm_result,
    }

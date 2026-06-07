"""LLM-as-judge for research memo quality."""

from __future__ import annotations

import json
from typing import Any

from evaluation.criteria import RUBRIC_CRITERIA
from src.llm_client import get_model, get_openai_client

JUDGE_SYSTEM_PROMPT = """You are an impartial evaluator grading an SEC research memo written by an AI analyst.

You will receive the memo text and extracted SEC filing data (ground truth).

Grade each criterion from 0.0 to 1.0 using ONLY evidence from the memo and source data.

Criteria:
- data_grounding: Are numeric claims consistent with source data? Penalize invented figures.
- segment_coverage: Does the memo discuss major product AND geographic segments from the data?
- trend_analysis: Does it explain YoY changes and mix shifts using real metrics?
- material_changes: Does it identify meaningful inflection points, not generic filler?
- clarity: Is it well-structured, concise, and readable?
- source_attribution: Does it cite filing types and dates from the retrieved filings?

Return valid JSON only:
{
  "scores": {
    "data_grounding": 0.0,
    "segment_coverage": 0.0,
    "trend_analysis": 0.0,
    "material_changes": 0.0,
    "clarity": 0.0,
    "source_attribution": 0.0
  },
  "explanations": {
    "data_grounding": "one sentence",
    "segment_coverage": "one sentence",
    "trend_analysis": "one sentence",
    "material_changes": "one sentence",
    "clarity": "one sentence",
    "source_attribution": "one sentence"
  },
  "overall_feedback": "2-3 sentences"
}
"""


def judge_memo_with_llm(memo: str, payload: dict[str, Any]) -> dict[str, Any]:
    client = get_openai_client()
    model = get_model()

    judge_input = {
        "memo": memo,
        "extracted_data": {
            "company": payload.get("company"),
            "ticker": payload.get("ticker"),
            "filings_analyzed": payload.get("filings_analyzed"),
            "product_segments": payload.get("product_segments"),
            "geographic_segments": payload.get("geographic_segments"),
            "kpi_summary": payload.get("kpi_summary"),
        },
    }

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(judge_input, indent=2)},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )

    parsed = json.loads(response.choices[0].message.content or "{}")
    scores = parsed.get("scores", {})

    for criterion in RUBRIC_CRITERIA:
        cid = criterion["id"]
        try:
            scores[cid] = max(0.0, min(1.0, float(scores.get(cid, 0))))
        except (TypeError, ValueError):
            scores[cid] = 0.0

    return {
        "scores": scores,
        "explanations": parsed.get("explanations", {}),
        "overall_feedback": parsed.get("overall_feedback", ""),
        "judge": "llm",
    }

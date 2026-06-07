"""Verify numeric claims in the LLM memo against extracted filing data."""

from __future__ import annotations

import re
from typing import Any


def _collect_source_numbers(payload: dict[str, Any]) -> set[int]:
    numbers: set[int] = set()

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
        elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
            numbers.add(int(round(obj)))

    for key in ("product_segments", "geographic_segments", "geographic_operating_income"):
        walk(payload.get(key, {}))

    kpi = payload.get("kpi_summary", {})
    for group in ("product_kpis", "geographic_kpis"):
        for row in kpi.get(group, []):
            for field in (
                "revenue_m",
                "operating_income_m",
                "share_of_total_pct",
                "share_of_geo_pct",
                "yoy_pct",
                "operating_margin_pct",
            ):
                val = row.get(field)
                if val is not None:
                    numbers.add(int(round(abs(val))))

    return numbers


def _extract_memo_dollar_claims(memo: str) -> list[dict]:
    claims = []
    for m in re.finditer(r"\$\s*([\d,]+(?:\.\d+)?)\s*([MBmb])?", memo):
        raw = m.group(1).replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        unit = (m.group(2) or "M").upper()
        if unit == "B":
            val *= 1000
        claims.append({"raw": m.group(0), "value_m": int(round(val))})
    return claims


def verify_numeric_grounding(memo: str, payload: dict[str, Any], tolerance_pct: float = 1.0) -> dict[str, Any]:
    source_numbers = _collect_source_numbers(payload)
    claims = _extract_memo_dollar_claims(memo)

    if not claims:
        return {
            "score": 0.0,
            "grounded_count": 0,
            "ungrounded_count": 0,
            "grounded": [],
            "ungrounded": [],
            "note": "No dollar amounts found in memo.",
        }

    grounded, ungrounded = [], []
    for claim in claims:
        val = claim["value_m"]
        matched = val in source_numbers
        if not matched:
            for src in source_numbers:
                if src and abs(val - src) / src * 100 <= tolerance_pct:
                    matched = True
                    break
        (grounded if matched else ungrounded).append(claim)

    score = len(grounded) / len(claims)
    return {
        "score": round(score, 3),
        "grounded_count": len(grounded),
        "ungrounded_count": len(ungrounded),
        "grounded": grounded[:10],
        "ungrounded": ungrounded[:10],
        "source_number_count": len(source_numbers),
    }


def verify_segment_mentions(memo: str, payload: dict[str, Any]) -> dict[str, Any]:
    memo_lower = memo.lower()
    labels = set()
    for seg_type in ("product_segments", "geographic_segments"):
        for period_data in payload.get(seg_type, {}).values():
            for label in period_data:
                if "total" not in label.lower():
                    labels.add(label)

    if not labels:
        return {"score": 0.5, "mentioned": [], "missing": [], "total_labels": 0}

    mentioned = [label for label in labels if label.lower() in memo_lower]
    missing = [label for label in labels if label.lower() not in memo_lower]
    return {
        "score": round(len(mentioned) / len(labels), 3),
        "mentioned": mentioned,
        "missing": missing[:10],
        "total_labels": len(labels),
    }

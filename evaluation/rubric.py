"""Self-evaluation rubric for SEC Filing Analyst research memos."""

RUBRIC_THRESHOLD = 0.75

RUBRIC_CRITERIA = [
    {
        "id": "data_grounding",
        "weight": 0.25,
        "description": "All numeric claims trace to extracted filing data; no invented figures.",
    },
    {
        "id": "segment_coverage",
        "weight": 0.20,
        "description": "Covers both product/category and geographic reportable segments where disclosed.",
    },
    {
        "id": "trend_analysis",
        "weight": 0.20,
        "description": "Identifies YoY changes and material shifts in mix or growth rates.",
    },
    {
        "id": "material_changes",
        "weight": 0.15,
        "description": "Flags definition changes, renames, or notable segment inflection points.",
    },
    {
        "id": "clarity",
        "weight": 0.10,
        "description": "Concise narrative with structured KPI bullets.",
    },
    {
        "id": "source_attribution",
        "weight": 0.10,
        "description": "Cites filing type, period end, and filing date.",
    },
]


def evaluate_memo(memo: str, extracted_data: dict, checks: dict[str, bool]) -> dict:
    scores = {}
    scores["data_grounding"] = 1.0 if checks.get("all_numbers_from_source") else 0.0
    scores["segment_coverage"] = 1.0 if checks.get("covers_product_and_geo") else 0.5
    scores["trend_analysis"] = 1.0 if checks.get("includes_yoy") else 0.0
    scores["material_changes"] = 1.0 if checks.get("notes_material_changes") else 0.5
    scores["clarity"] = 1.0 if checks.get("has_kpi_bullets") and checks.get("has_narrative") else 0.5
    scores["source_attribution"] = 1.0 if checks.get("cites_filings") else 0.0

    weighted = sum(
        scores[c["id"]] * c["weight"] for c in RUBRIC_CRITERIA
    )
    return {
        "scores": scores,
        "weighted_score": round(weighted, 3),
        "passes": weighted >= RUBRIC_THRESHOLD,
        "threshold": RUBRIC_THRESHOLD,
    }

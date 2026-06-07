"""Rubric criteria definitions."""

RUBRIC_THRESHOLD = 0.75

RUBRIC_CRITERIA = [
    {
        "id": "data_grounding",
        "weight": 0.25,
        "description": "Numeric claims in the LLM memo match extracted filing data.",
    },
    {
        "id": "segment_coverage",
        "weight": 0.20,
        "description": "Memo discusses major product and geographic segments from extracted data.",
    },
    {
        "id": "trend_analysis",
        "weight": 0.20,
        "description": "Memo explains YoY changes and mix shifts using real metrics.",
    },
    {
        "id": "material_changes",
        "weight": 0.15,
        "description": "Memo identifies meaningful inflection points, not boilerplate.",
    },
    {
        "id": "clarity",
        "weight": 0.10,
        "description": "Well-structured, concise, readable markdown.",
    },
    {
        "id": "source_attribution",
        "weight": 0.10,
        "description": "Memo cites filing types and dates from EDGAR.",
    },
]

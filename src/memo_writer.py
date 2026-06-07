"""LLM-powered research memo generation from extracted SEC data."""

from __future__ import annotations

import json
from typing import Any

from src.llm_client import get_model, get_openai_client

MEMO_SYSTEM_PROMPT = """You are an SEC Filing Analyst writing a concise equity research memo.

Rules:
- Use ONLY numbers provided in the extracted data and KPI summary. Never invent figures.
- If a segment or metric is missing from the data, say it was not disclosed — do not guess.
- Include YoY trends where KPI summary provides yoy_pct values.
- Cite specific filing forms and filing dates from the sources provided.
- Write in clear markdown with these sections:
  ## Executive Summary
  ## Product / Category Segment KPIs
  ## Geographic Segment KPIs (omit section if no geographic data)
  ## Material Changes & Trends
  ## Sources
- Keep the memo analytical but concise (roughly 400–700 words).
- End with: *Not investment advice.*
"""


def write_research_memo(
    company_name: str,
    ticker: str,
    filings: list[dict],
    segments: dict[str, Any],
    kpi_summary: dict[str, Any],
) -> str:
    client = get_openai_client()
    model = get_model()

    context = {
        "company_name": company_name,
        "ticker": ticker,
        "filings_analyzed": [
            {
                "form": f.get("form"),
                "filing_date": f.get("filing_date"),
                "primary_document": f.get("primary_document"),
                "url": f.get("url"),
            }
            for f in filings
        ],
        "segment_data_usd_millions": segments,
        "kpi_summary": kpi_summary,
    }

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": MEMO_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Write a research memo using this extracted SEC filing data:\n\n"
                    f"```json\n{json.dumps(context, indent=2)}\n```"
                ),
            },
        ],
        temperature=0.3,
    )

    memo = response.choices[0].message.content or ""
    if not memo.strip():
        raise RuntimeError("LLM returned an empty memo.")
    return memo.strip()

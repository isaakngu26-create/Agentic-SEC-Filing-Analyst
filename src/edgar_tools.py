"""SEC EDGAR tools exposed to the LLM agent."""

from __future__ import annotations

import json
from typing import Any

from src.sec_client import download_filing_html, get_recent_filings, lookup_company
from src.xbrl_extractor import extract_segments_from_html

EDGAR_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_company",
            "description": (
                "Resolve a US public company by ticker, CIK, or company name. "
                "Returns ticker, CIK, and official company title."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Ticker (e.g. AAPL), CIK, or company name fragment.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_filings",
            "description": (
                "Fetch recent SEC filings for a company CIK from EDGAR. "
                "Returns filing form type, date, accession number, and document URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cik": {"type": "string", "description": "Company CIK."},
                    "form_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filing types, e.g. ['10-K'] or ['10-K','10-Q'].",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum filings to return.",
                        "default": 2,
                    },
                },
                "required": ["cik", "form_types"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_segment_data",
            "description": (
                "Download SEC filing HTML and extract product/category and geographic "
                "segment revenue from inline XBRL. Pass filings from get_recent_filings."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filings": {
                        "type": "array",
                        "description": "Filing dicts with at least a 'url' field.",
                        "items": {"type": "object"},
                    }
                },
                "required": ["filings"],
            },
        },
    },
]


def merge_segment_periods(*datasets: dict) -> dict:
    merged = {
        "product_segments": {},
        "geographic_segments": {},
        "geographic_operating_income": {},
    }
    for ds in datasets:
        for key in merged:
            merged[key].update(ds.get(key, {}))
    return merged


def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "lookup_company":
        record = lookup_company(arguments["query"])
        if not record:
            return {"error": f"No company found for query: {arguments['query']}"}
        return record

    if name == "get_recent_filings":
        filings = get_recent_filings(
            arguments["cik"],
            form_types=tuple(arguments["form_types"]),
            limit=int(arguments.get("limit", 2)),
        )
        return {"filings": filings, "count": len(filings)}

    if name == "extract_segment_data":
        datasets = []
        for filing in arguments["filings"]:
            html = download_filing_html(filing["url"])
            datasets.append(extract_segments_from_html(html))
        return merge_segment_periods(*datasets)

    return {"error": f"Unknown tool: {name}"}


def tool_result_json(result: Any) -> str:
    return json.dumps(result, indent=2)

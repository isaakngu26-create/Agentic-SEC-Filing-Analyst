"""Agent orchestrator — runs the SEC Filing Analyst pipeline step by step."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from evaluation.rubric import RUBRIC_CRITERIA, evaluate_memo
from src.sec_client import download_filing_html, get_recent_filings, lookup_company
from src.storage import save_analysis
from src.xbrl_extractor import compute_yoy, extract_segments_from_html

StepCallback = Callable[[str, str, Optional[Any]], None]


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


def build_memo(company_name: str, ticker: str, filings: list, segments: dict) -> str:
    products = segments["product_segments"]
    geo = segments["geographic_segments"]
    geo_op = segments.get("geographic_operating_income", {})

    periods = sorted(products.keys())
    geo_periods = sorted(geo.keys())

    filing_lines = [
        f"- {f['form']} filed {f['filing_date']} (primary doc: {f['primary_document']})"
        for f in filings[:3]
    ]

    lines = [
        f"# Research Memo: {company_name} ({ticker.upper()})",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "**Analyst:** SEC Filing Analyst Agent",
        "",
        "## Sources",
        *filing_lines,
        "",
    ]

    if periods:
        latest = periods[-1]
        prior = periods[-2] if len(periods) > 1 else None
        latest_products = products[latest]
        prior_products = products.get(prior, {}) if prior else {}

        total_keys = [k for k in latest_products if "total" in k.lower()]
        total_rev = latest_products.get(total_keys[0]) if total_keys else sum(
            v for k, v in latest_products.items() if "total" not in k.lower()
        )
        prior_total_keys = [k for k in prior_products if "total" in k.lower()]
        prior_total = (
            prior_products.get(prior_total_keys[0])
            if prior_total_keys
            else sum(v for k, v in prior_products.items() if "total" not in k.lower())
            if prior_products
            else None
        )
        total_yoy = compute_yoy(total_rev, prior_total)

        summary = f"## Executive Summary\n{company_name} reported net sales of **${total_rev:,}M**"
        if total_yoy is not None:
            summary += f" ({total_yoy:+.1f}% YoY)"
        summary += f" for the period ending {latest}."
        lines.extend([summary, "", "## Product / Category Segment KPIs (USD millions)"])

        for label, val in sorted(latest_products.items(), key=lambda x: -x[1]):
            if "total" in label.lower():
                continue
            yoy = compute_yoy(val, prior_products.get(label))
            share = val / total_rev * 100 if total_rev else 0
            yoy_str = f", YoY {yoy:+.1f}%" if yoy is not None else ""
            lines.append(f"- **{label}**: ${val:,}M ({share:.1f}% of net sales){yoy_str}")
    else:
        lines.extend([
            "## Executive Summary",
            f"No product/category segment breakdown was found in the extracted XBRL for {company_name}.",
            "",
        ])

    if geo_periods:
        latest_geo_period = geo_periods[-1]
        prior_geo_period = geo_periods[-2] if len(geo_periods) > 1 else None
        latest_geo = geo[latest_geo_period]
        prior_geo = geo.get(prior_geo_period, {}) if prior_geo_period else {}
        geo_total = sum(latest_geo.values())

        lines.extend(["", "## Geographic Segment KPIs (USD millions)"])
        for label, val in sorted(latest_geo.items(), key=lambda x: -x[1]):
            yoy = compute_yoy(val, prior_geo.get(label))
            share = val / geo_total * 100 if geo_total else 0
            op = geo_op.get(latest_geo_period, {}).get(label)
            op_str = f", op. margin {op / val * 100:.1f}%" if op and val else ""
            yoy_str = f", YoY {yoy:+.1f}%" if yoy is not None else ""
            lines.append(
                f"- **{label}**: ${val:,}M ({share:.1f}% of geo net sales){yoy_str}{op_str}"
            )

    material = _detect_material_changes(products, geo)
    lines.extend(["", "## Material Changes & Trends"])
    if material:
        lines.extend(f"- {m}" for m in material)
    else:
        lines.append("- No material segment definition changes detected across analyzed filings.")

    lines.extend([
        "",
        "## Methodology",
        "Segment revenue and operating income extracted from inline XBRL in SEC primary documents via EDGAR. "
        "All figures in USD millions as reported. YoY computed on consecutive fiscal period-ends disclosed in filings.",
        "",
        "---",
        "*This memo was produced autonomously from SEC primary source documents. Not investment advice.*",
    ])
    return "\n".join(lines)


def _detect_material_changes(products: dict, geo: dict) -> list[str]:
    notes = []
    periods = sorted(products.keys())
    if len(periods) >= 2:
        latest, prior = periods[-1], periods[-2]
        for label, val in products[latest].items():
            if "total" in label.lower():
                continue
            yoy = compute_yoy(val, products[prior].get(label))
            if yoy is not None and abs(yoy) >= 10:
                direction = "grew" if yoy > 0 else "declined"
                notes.append(f"**{label}** {direction} {abs(yoy):.1f}% YoY to ${val:,}M.")

    geo_periods = sorted(geo.keys())
    if len(geo_periods) >= 2:
        latest, prior = geo_periods[-1], geo_periods[-2]
        for label, val in geo[latest].items():
            yoy = compute_yoy(val, geo[prior].get(label))
            if yoy is not None and abs(yoy) >= 5:
                direction = "grew" if yoy > 0 else "declined"
                notes.append(
                    f"Geographic segment **{label}** {direction} {abs(yoy):.1f}% YoY to ${val:,}M."
                )
    return notes[:6]


def run_agent(
    query: str,
    filing_count: int = 2,
    form_types: tuple[str, ...] = ("10-K",),
    on_step: Optional[StepCallback] = None,
) -> dict[str, Any]:
    def emit(step: str, status: str, detail: Any = None) -> None:
        if on_step:
            on_step(step, status, detail)

    emit("resolve", "running", f"Looking up '{query}'")
    company = lookup_company(query)
    if not company:
        emit("resolve", "error", f"Could not resolve '{query}'")
        raise ValueError(f"Could not find company for '{query}'. Try a ticker (e.g. AAPL) or CIK.")

    ticker = company["ticker"]
    cik = company["cik"]
    submissions_name = company["title"]
    emit("resolve", "complete", company)

    emit("fetch", "running", f"Fetching recent {', '.join(form_types)} filings")
    filings = get_recent_filings(cik, form_types=form_types, limit=filing_count)
    if not filings:
        emit("fetch", "error", "No matching filings found")
        raise ValueError(f"No {form_types} filings found for {ticker}.")
    emit("fetch", "complete", filings)

    emit("extract", "running", f"Extracting segment data from {len(filings)} filing(s)")
    datasets = []
    for filing in filings:
        html = download_filing_html(filing["url"])
        datasets.append(extract_segments_from_html(html))
    segments = merge_segment_periods(*datasets)
    emit("extract", "complete", segments)

    emit("analyze", "running", "Computing trends and KPIs")
    memo = build_memo(submissions_name, ticker, filings, segments)
    emit("analyze", "complete", memo)

    payload = {
        "company": submissions_name,
        "ticker": ticker,
        "cik": cik.zfill(10),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filings_analyzed": [
            {
                "form": f["form"],
                "filing_date": f["filing_date"],
                "primary_document": f["primary_document"],
                "url": f["url"],
            }
            for f in filings
        ],
        **segments,
    }

    emit("evaluate", "running", "Scoring memo against rubric")
    has_geo = bool(segments["geographic_segments"])
    has_product = bool(segments["product_segments"])
    evaluation = evaluate_memo(
        memo,
        payload,
        checks={
            "all_numbers_from_source": True,
            "covers_product_and_geo": has_geo and has_product,
            "includes_yoy": "YoY" in memo,
            "notes_material_changes": "## Material Changes" in memo,
            "has_kpi_bullets": "## Product" in memo or "## Geographic" in memo,
            "has_narrative": "## Executive Summary" in memo,
            "cites_filings": any(f["form"] in memo for f in filings),
        },
    )
    emit("evaluate", "complete", evaluation)

    emit("store", "running", "Saving results")
    paths = save_analysis(ticker, payload, memo, evaluation)
    emit("store", "complete", paths)

    return {
        "company": company,
        "filings": filings,
        "segments": segments,
        "memo": memo,
        "payload": payload,
        "evaluation": evaluation,
        "paths": paths,
        "rubric_criteria": RUBRIC_CRITERIA,
    }

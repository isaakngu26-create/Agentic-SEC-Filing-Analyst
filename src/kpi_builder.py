"""Pre-compute KPIs from extracted segment data for the memo LLM."""

from __future__ import annotations

from typing import Any, Optional

from src.xbrl_extractor import compute_yoy


def _latest_prior_periods(periods: list[str]) -> tuple[Optional[str], Optional[str]]:
    if not periods:
        return None, None
    sorted_periods = sorted(periods)
    latest = sorted_periods[-1]
    prior = sorted_periods[-2] if len(sorted_periods) > 1 else None
    return latest, prior


def build_kpi_summary(segments: dict[str, Any]) -> dict[str, Any]:
    products = segments.get("product_segments", {})
    geo = segments.get("geographic_segments", {})
    geo_op = segments.get("geographic_operating_income", {})

    product_periods = sorted(products.keys())
    geo_periods = sorted(geo.keys())
    latest_p, prior_p = _latest_prior_periods(product_periods)
    latest_g, prior_g = _latest_prior_periods(geo_periods)

    product_kpis = []
    if latest_p:
        latest_row = products[latest_p]
        prior_row = products.get(prior_p, {}) if prior_p else {}
        total_keys = [k for k in latest_row if "total" in k.lower()]
        total = latest_row.get(total_keys[0]) if total_keys else sum(
            v for k, v in latest_row.items() if "total" not in k.lower()
        )
        for label, val in sorted(latest_row.items(), key=lambda x: -x[1]):
            if "total" in label.lower():
                continue
            product_kpis.append(
                {
                    "segment": label,
                    "period_end": latest_p,
                    "revenue_m": val,
                    "share_of_total_pct": round(val / total * 100, 1) if total else None,
                    "yoy_pct": compute_yoy(val, prior_row.get(label)),
                }
            )

    geo_kpis = []
    if latest_g:
        latest_row = geo[latest_g]
        prior_row = geo.get(prior_g, {}) if prior_g else {}
        total = sum(latest_row.values())
        for label, val in sorted(latest_row.items(), key=lambda x: -x[1]):
            op = geo_op.get(latest_g, {}).get(label)
            geo_kpis.append(
                {
                    "segment": label,
                    "period_end": latest_g,
                    "revenue_m": val,
                    "share_of_geo_pct": round(val / total * 100, 1) if total else None,
                    "yoy_pct": compute_yoy(val, prior_row.get(label)),
                    "operating_income_m": op,
                    "operating_margin_pct": round(op / val * 100, 1) if op and val else None,
                }
            )

    return {
        "product_kpis": product_kpis,
        "geographic_kpis": geo_kpis,
        "periods_available": {
            "product": product_periods,
            "geographic": geo_periods,
        },
    }

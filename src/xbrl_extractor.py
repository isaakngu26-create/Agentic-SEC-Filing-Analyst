"""Extract product and geographic segment data from SEC inline XBRL filings."""

import re
from collections import defaultdict
from typing import Any, Optional

# Human-readable labels for common XBRL member suffixes
LABEL_MAP = {
    "IPhone": "iPhone",
    "Mac": "Mac",
    "IPad": "iPad",
    "WearablesHomeandAccessories": "Wearables, Home & Accessories",
    "Service": "Services",
    "Product": "Products (total)",
    "Americas": "Americas",
    "Europe": "Europe",
    "GreaterChina": "Greater China",
    "Japan": "Japan",
    "RestOfAsiaPacific": "Rest of Asia Pacific",
}


def _humanize_member(member: str) -> str:
    key = member.replace("SegmentMember", "").replace("Member", "")
    if key in LABEL_MAP:
        return LABEL_MAP[key]
    # CamelCase -> words
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", key)
    return spaced.strip()


def _classify_dimension(dimension: str) -> str:
    dim = dimension.lower()
    if "consolidation" in dim:
        return "skip"
    if "businesssegment" in dim or "geographical" in dim:
        return "geographic"
    return "product"


def _parse_contexts(html: str) -> dict[str, dict[str, Any]]:
    ctx_map: dict[str, dict[str, Any]] = {}
    for cid, body in re.findall(
        r'<xbrli:context id="([^"]+)"[^>]*>(.*?)</xbrli:context>', html, re.DOTALL
    ):
        end = re.search(r"<xbrli:endDate>([^<]+)", body)
        start = re.search(r"<xbrli:startDate>([^<]+)", body)
        members = re.findall(r'explicitMember dimension="([^"]*)"[^>]*>([^<]+)', body)

        geo_member = None
        product_member = None
        for dim, raw_member in members:
            category = _classify_dimension(dim)
            if category == "skip":
                continue
            member = raw_member.split(":")[-1]
            if category == "geographic":
                geo_member = member
            else:
                product_member = member

        ctx_map[cid] = {
            "end": end.group(1) if end else None,
            "start": start.group(1) if start else None,
            "geo_member": geo_member,
            "product_member": product_member,
        }
    return ctx_map


def _parse_numeric_facts(html: str, ctx_map: dict, concept: str) -> list[dict]:
    facts = []
    for match in re.finditer(r"<ix:nonFraction([^>]*)>([^<]+)</ix:nonFraction>", html):
        attrs, raw_val = match.group(1), match.group(2)
        raw_val = raw_val.replace(",", "").replace("&#160;", "").strip()
        name = re.search(r'name="(?:us-gaap|dei|aapl|msft|nvda|goog|amzn|meta)[^"]*:([^"]+)"', attrs)
        if not name:
            name = re.search(r'name="([a-zA-Z0-9_:-]+)"', attrs)
        ctx = re.search(r'contextRef="([^"]+)"', attrs)
        if not name or not ctx:
            continue
        concept_name = name.group(1).split(":")[-1]
        if concept_name != concept:
            continue
        info = ctx_map.get(ctx.group(1), {})
        try:
            val = int(raw_val)
        except ValueError:
            continue
        facts.append({"period_end": info.get("end"), "info": info, "value_m": val})
    return facts


def extract_segments_from_html(html: str) -> dict[str, Any]:
    ctx_map = _parse_contexts(html)
    revenue_facts = _parse_numeric_facts(
        html, ctx_map, "RevenueFromContractWithCustomerExcludingAssessedTax"
    )
    op_income_facts = _parse_numeric_facts(html, ctx_map, "OperatingIncomeLoss")

    products: dict[str, dict] = defaultdict(dict)
    geo: dict[str, dict] = defaultdict(dict)
    geo_op: dict[str, dict] = defaultdict(dict)

    for fact in revenue_facts:
        end = fact["period_end"]
        if not end:
            continue
        info = fact["info"]
        if info.get("geo_member"):
            label = _humanize_member(info["geo_member"])
            geo[end][label] = fact["value_m"]
        if info.get("product_member"):
            label = _humanize_member(info["product_member"])
            products[end][label] = fact["value_m"]

    for fact in op_income_facts:
        end = fact["period_end"]
        if not end:
            continue
        info = fact["info"]
        if info.get("geo_member"):
            label = _humanize_member(info["geo_member"])
            geo_op[end][label] = fact["value_m"]

    return {
        "product_segments": {k: dict(v) for k, v in products.items()},
        "geographic_segments": {k: dict(v) for k, v in geo.items()},
        "geographic_operating_income": {k: dict(v) for k, v in geo_op.items()},
    }


def compute_yoy(current: float, prior: Optional[float]) -> Optional[float]:
    if prior is None or prior == 0:
        return None
    return round((current - prior) / prior * 100, 1)


def build_time_series_table(segments: dict, segment_type: str = "product_segments") -> list[dict]:
    """Flatten segment dict into rows suitable for a DataFrame."""
    data = segments.get(segment_type, {})
    all_labels = sorted({label for period in data.values() for label in period})
    rows = []
    for period in sorted(data.keys()):
        row = {"period_end": period}
        for label in all_labels:
            row[label] = data[period].get(label)
        rows.append(row)
    return rows

"""Fetch recent SEC filings from EDGAR."""

import json
import urllib.request
from functools import lru_cache
from typing import Optional

USER_AGENT = "Agentic-SEC-Filing-Analyst contact@example.com"
BASE = "https://data.sec.gov"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


@lru_cache(maxsize=1)
def _load_ticker_map() -> dict[str, dict]:
    raw = json.loads(_get(TICKERS_URL))
    by_ticker: dict[str, dict] = {}
    by_cik: dict[str, dict] = {}
    for entry in raw.values():
        ticker = entry["ticker"].upper()
        cik = str(entry["cik_str"])
        record = {"ticker": ticker, "cik": cik, "title": entry["title"]}
        by_ticker[ticker] = record
        by_cik[cik] = record
    return {"by_ticker": by_ticker, "by_cik": by_cik}


def lookup_company(query: str) -> Optional[dict]:
    """Resolve ticker, CIK, or partial company name to a company record."""
    q = query.strip()
    if not q:
        return None

    maps = _load_ticker_map()
    if q.isdigit():
        cik = str(int(q))
        return maps["by_cik"].get(cik)

    upper = q.upper()
    if upper in maps["by_ticker"]:
        return maps["by_ticker"][upper]

    q_lower = q.lower()
    for record in maps["by_ticker"].values():
        if q_lower in record["title"].lower():
            return record
    return None


def search_companies(query: str, limit: int = 10) -> list[dict]:
    q = query.strip().lower()
    if not q:
        return []
    results = []
    for record in _load_ticker_map()["by_ticker"].values():
        if q in record["ticker"].lower() or q in record["title"].lower():
            results.append(record)
        if len(results) >= limit:
            break
    return results


def get_company_submissions(cik: str) -> dict:
    cik_padded = cik.zfill(10)
    data = _get(f"{BASE}/submissions/CIK{cik_padded}.json")
    return json.loads(data)


def get_recent_filings(
    cik: str,
    form_types: tuple[str, ...] = ("10-K", "10-Q"),
    limit: int = 5,
) -> list[dict]:
    submissions = get_company_submissions(cik)
    recent = submissions["filings"]["recent"]
    filings = []
    for i in range(len(recent["form"])):
        if recent["form"][i] not in form_types:
            continue
        accession = recent["accessionNumber"][i].replace("-", "")
        cik_int = str(int(cik))
        primary = recent["primaryDocument"][i]
        filings.append(
            {
                "form": recent["form"][i],
                "filing_date": recent["filingDate"][i],
                "accession_number": recent["accessionNumber"][i],
                "primary_document": primary,
                "url": f"{ARCHIVES}/{cik_int}/{accession}/{primary}",
            }
        )
        if len(filings) >= limit:
            break
    return filings


def download_filing_html(url: str) -> str:
    return _get(url).decode("utf-8", errors="replace")

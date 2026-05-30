"""Persist and retrieve analysis results."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
INDEX_PATH = DATA_DIR / "analysis_index.json"


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)


def _load_index() -> list[dict]:
    _ensure_dirs()
    if not INDEX_PATH.exists():
        return []
    return json.loads(INDEX_PATH.read_text())


def _save_index(entries: list[dict]) -> None:
    _ensure_dirs()
    INDEX_PATH.write_text(json.dumps(entries, indent=2))


def save_analysis(
    ticker: str,
    payload: dict[str, Any],
    memo: str,
    evaluation: dict[str, Any],
) -> dict[str, str]:
    _ensure_dirs()
    slug = ticker.lower()
    data_path = DATA_DIR / f"{slug}_segment_analysis.json"
    memo_path = OUTPUT_DIR / f"{slug}_research_memo.md"
    eval_path = OUTPUT_DIR / f"{slug}_evaluation.json"

    data_path.write_text(json.dumps(payload, indent=2))
    memo_path.write_text(memo)
    eval_path.write_text(json.dumps(evaluation, indent=2))

    entry = {
        "ticker": ticker.upper(),
        "company": payload.get("company", ""),
        "generated_at": payload.get("generated_at", datetime.now(timezone.utc).isoformat()),
        "data_path": str(data_path.relative_to(ROOT)),
        "memo_path": str(memo_path.relative_to(ROOT)),
        "eval_path": str(eval_path.relative_to(ROOT)),
        "evaluation_score": evaluation.get("weighted_score"),
        "passes_rubric": evaluation.get("passes"),
    }

    index = _load_index()
    index = [e for e in index if e.get("ticker") != ticker.upper()]
    index.insert(0, entry)
    _save_index(index)

    return {
        "data_path": str(data_path),
        "memo_path": str(memo_path),
        "eval_path": str(eval_path),
    }


def list_analyses() -> list[dict]:
    return _load_index()


def load_analysis(ticker: str) -> Optional[dict[str, Any]]:
    slug = ticker.lower()
    data_path = DATA_DIR / f"{slug}_segment_analysis.json"
    memo_path = OUTPUT_DIR / f"{slug}_research_memo.md"
    eval_path = OUTPUT_DIR / f"{slug}_evaluation.json"
    if not data_path.exists():
        return None
    result = {
        "payload": json.loads(data_path.read_text()),
        "memo": memo_path.read_text() if memo_path.exists() else "",
        "evaluation": json.loads(eval_path.read_text()) if eval_path.exists() else {},
    }
    return result

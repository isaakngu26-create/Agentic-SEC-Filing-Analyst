"""Agent orchestrator — LLM agent with EDGAR tools, memo writer, and real evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Optional

from evaluation.rubric import RUBRIC_CRITERIA, evaluate_memo
from src.llm_agent import run_llm_agent_loop
from src.storage import save_analysis

StepCallback = Callable[[str, str, Optional[Any]], None]


def run_agent(
    query: str,
    filing_count: int = 2,
    form_types: tuple[str, ...] = ("10-K",),
    on_step: Optional[StepCallback] = None,
) -> dict[str, Any]:
    def emit(step: str, status: str, detail: Any = None) -> None:
        if on_step:
            on_step(step, status, detail)

    emit("agent", "running", "Starting LLM agent with EDGAR tools…")

    agent_result = run_llm_agent_loop(
        query=query,
        filing_count=filing_count,
        form_types=form_types,
        on_step=on_step,
    )

    company = agent_result["company"]
    ticker = company["ticker"]
    filings = agent_result["filings"]
    segments = agent_result["segments"]
    kpi_summary = agent_result["kpi_summary"]
    memo = agent_result["memo"]

    payload = {
        "company": company["title"],
        "ticker": ticker,
        "cik": company["cik"].zfill(10),
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
        "kpi_summary": kpi_summary,
        "tool_calls": agent_result.get("tool_calls", []),
        **segments,
    }

    emit("evaluate", "running", "Scoring LLM memo (grounding + LLM judge)…")
    evaluation = evaluate_memo(memo, payload, use_llm_judge=True)
    emit("evaluate", "complete", evaluation)

    emit("store", "running", "Saving results")
    paths = save_analysis(ticker, payload, memo, evaluation)
    emit("store", "complete", paths)

    return {
        "company": company,
        "filings": filings,
        "segments": segments,
        "kpi_summary": kpi_summary,
        "memo": memo,
        "payload": payload,
        "evaluation": evaluation,
        "tool_calls": agent_result.get("tool_calls", []),
        "paths": paths,
        "rubric_criteria": RUBRIC_CRITERIA,
    }

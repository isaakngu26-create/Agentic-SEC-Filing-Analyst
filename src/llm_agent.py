"""LLM agent loop with EDGAR tool calling."""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from src.edgar_tools import EDGAR_TOOL_SCHEMAS, execute_tool, tool_result_json
from src.kpi_builder import build_kpi_summary
from src.llm_client import get_model, get_openai_client
from src.memo_writer import write_research_memo

AGENT_SYSTEM_PROMPT = """You are an autonomous SEC Filing Analyst Agent.

Your job is to research a US public company by calling the available tools in a logical order:

1. lookup_company — resolve the user's ticker, CIK, or company name
2. get_recent_filings — fetch recent 10-K and/or 10-Q filings from EDGAR
3. extract_segment_data — parse segment revenue from those filings' inline XBRL

Call tools until you have segment data, then respond with a short JSON summary (no markdown fences) like:
{"status": "ready", "ticker": "...", "company_name": "...", "message": "Segment data extracted."}

Do NOT write the final research memo yourself — a separate memo writer will use your extracted data.
Do NOT invent financial numbers. Only use tool outputs.
If a tool returns an error, try to recover or explain what failed.
"""

StepCallback = Callable[[str, str, Optional[Any]], None]


def run_llm_agent_loop(
    query: str,
    filing_count: int = 2,
    form_types: tuple[str, ...] = ("10-K",),
    on_step: Optional[StepCallback] = None,
    max_turns: int = 12,
) -> dict[str, Any]:
    def emit(step: str, status: str, detail: Any = None) -> None:
        if on_step:
            on_step(step, status, detail)

    client = get_openai_client()
    model = get_model()
    tool_calls_log: list[dict] = []

    state: dict[str, Any] = {
        "company": None,
        "filings": [],
        "segments": None,
    }

    messages: list[dict] = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Analyze the company: {query}\n"
                f"Fetch up to {filing_count} recent filing(s) of type(s): {', '.join(form_types)}.\n"
                "Use the tools to retrieve and extract segment data."
            ),
        },
    ]

    emit("agent", "running", "LLM planning tool calls…")

    for _ in range(max_turns):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=EDGAR_TOOL_SCHEMAS,
            tool_choice="auto",
            temperature=0.2,
        )
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            break

        for tool_call in message.tool_calls:
            fn_name = tool_call.function.name
            try:
                fn_args = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                fn_args = {}

            if fn_name == "get_recent_filings":
                fn_args.setdefault("limit", filing_count)
                if "form_types" not in fn_args:
                    fn_args["form_types"] = list(form_types)

            emit("tool", "running", f"{fn_name}({json.dumps(fn_args, default=str)[:120]}…)")
            result = execute_tool(fn_name, fn_args)
            tool_calls_log.append(
                {"tool": fn_name, "arguments": fn_args, "result_preview": str(result)[:500]}
            )

            if fn_name == "lookup_company" and "error" not in result:
                state["company"] = result
                emit("resolve", "complete", result)
            elif fn_name == "get_recent_filings":
                state["filings"] = result.get("filings", [])
                emit("fetch", "complete", state["filings"])
            elif fn_name == "extract_segment_data":
                state["segments"] = result
                emit("extract", "complete", result)

            emit("tool", "complete", fn_name)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result_json(result),
                }
            )

    emit("agent", "complete", f"{len(tool_calls_log)} tool call(s)")

    if not state["company"]:
        raise RuntimeError("Agent did not resolve a company. Try a clearer ticker or CIK.")
    if not state["filings"]:
        raise RuntimeError("Agent did not retrieve any filings.")
    if not state["segments"]:
        raise RuntimeError("Agent did not extract segment data.")

    company = state["company"]
    filings = state["filings"]
    segments = state["segments"]
    kpi_summary = build_kpi_summary(segments)

    emit("memo", "running", "LLM writing research memo from extracted data…")
    memo = write_research_memo(
        company_name=company["title"],
        ticker=company["ticker"],
        filings=filings,
        segments=segments,
        kpi_summary=kpi_summary,
    )
    emit("memo", "complete", "Memo generated")

    return {
        "company": company,
        "filings": filings,
        "segments": segments,
        "kpi_summary": kpi_summary,
        "memo": memo,
        "tool_calls": tool_calls_log,
        "agent_messages": len(messages),
    }

"""SEC Filing Analyst Agent — Streamlit application."""

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.rubric import RUBRIC_CRITERIA, RUBRIC_THRESHOLD
from src.agent import run_agent
from src.sec_client import search_companies
from src.storage import list_analyses, load_analysis
from src.xbrl_extractor import build_time_series_table

st.set_page_config(
    page_title="SEC Filing Analyst Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

AGENT_STEPS = [
    ("resolve", "Resolve company"),
    ("fetch", "Retrieve SEC filings"),
    ("extract", "Extract segment data"),
    ("analyze", "Analyze trends & KPIs"),
    ("evaluate", "Self-evaluate memo"),
    ("store", "Store results"),
]

STEP_ICONS = {
    "running": "⏳",
    "complete": "✅",
    "error": "❌",
    "pending": "○",
}


def init_session_state() -> None:
    defaults = {
        "agent_result": None,
        "agent_error": None,
        "step_log": [],
        "running": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def render_step_log() -> None:
    if not st.session_state.step_log:
        return
    st.subheader("Agent progress")
    for entry in st.session_state.step_log:
        icon = STEP_ICONS.get(entry["status"], "○")
        label = next((lbl for sid, lbl in AGENT_STEPS if sid == entry["step"]), entry["step"])
        st.markdown(f"{icon} **{label}** — {entry.get('message', entry['status'])}")


def on_step(step: str, status: str, detail=None) -> None:
    message = status
    if status == "running" and detail:
        message = str(detail)
    elif status == "complete" and step == "fetch" and isinstance(detail, list):
        message = f"Retrieved {len(detail)} filing(s)"
    elif status == "complete" and step == "evaluate" and isinstance(detail, dict):
        message = f"Score {detail.get('weighted_score', 0):.2f} / 1.0"
    elif status == "complete" and step == "resolve" and isinstance(detail, dict):
        message = f"{detail['title']} ({detail['ticker']})"

    existing = [e for e in st.session_state.step_log if e["step"] != step]
    existing.append({"step": step, "status": status, "message": message})
    st.session_state.step_log = existing


def render_rubric(evaluation: dict) -> None:
    scores = evaluation.get("scores", {})
    cols = st.columns(3)
    for i, criterion in enumerate(RUBRIC_CRITERIA):
        score = scores.get(criterion["id"], 0)
        with cols[i % 3]:
            st.metric(
                label=criterion["id"].replace("_", " ").title(),
                value=f"{score:.0%}",
                help=criterion["description"],
            )

    weighted = evaluation.get("weighted_score", 0)
    passed = evaluation.get("passes", False)
    if passed:
        st.success(f"Rubric score **{weighted:.2f}** — passes threshold ({RUBRIC_THRESHOLD})")
    else:
        st.warning(f"Rubric score **{weighted:.2f}** — below threshold ({RUBRIC_THRESHOLD})")


def render_segments(result: dict) -> None:
    segments = result["segments"]
    tab_product, tab_geo, tab_filings = st.tabs(["Product segments", "Geographic segments", "Filings"])

    with tab_product:
        rows = build_time_series_table(segments, "product_segments")
        if rows:
            df = pd.DataFrame(rows).set_index("period_end")
            st.dataframe(df, use_container_width=True)
            st.line_chart(df.select_dtypes(include="number"))
        else:
            st.info("No product/category segments found in XBRL for this company.")

    with tab_geo:
        rows = build_time_series_table(segments, "geographic_segments")
        if rows:
            df = pd.DataFrame(rows).set_index("period_end")
            st.dataframe(df, use_container_width=True)
            st.line_chart(df.select_dtypes(include="number"))
        else:
            st.info("No geographic segments found in XBRL for this company.")

    with tab_filings:
        st.dataframe(pd.DataFrame(result["filings"]), use_container_width=True)


def main() -> None:
    init_session_state()

    st.title("SEC Filing Analyst Agent")
    st.caption(
        "Autonomous financial research: retrieve SEC filings, extract segments, "
        "analyze KPIs, write a memo, and self-evaluate."
    )

    with st.sidebar:
        st.header("Agent settings")
        query = st.text_input("Ticker, CIK, or company name", value="AAPL", placeholder="e.g. MSFT, 320193")
        filing_count = st.slider("Number of filings to analyze", 1, 5, 2)
        form_type = st.selectbox("Filing type", ["10-K", "10-Q", "10-K, 10-Q"])
        form_types = tuple(x.strip() for x in form_type.split(","))

        run_clicked = st.button("Run agent", type="primary", use_container_width=True)

        if query and len(query) >= 2:
            matches = search_companies(query, limit=5)
            if matches:
                st.caption("Matching companies")
                for m in matches:
                    st.text(f"{m['ticker']} — {m['title'][:40]}")

        st.divider()
        st.header("Saved analyses")
        history = list_analyses()
        if history:
            for item in history[:8]:
                if st.button(
                    f"{item['ticker']} ({item.get('evaluation_score', '?')})",
                    key=f"hist_{item['ticker']}",
                    use_container_width=True,
                ):
                    loaded = load_analysis(item["ticker"])
                    if loaded:
                        st.session_state.agent_result = {
                            "company": {"ticker": item["ticker"], "title": item["company"]},
                            "filings": loaded["payload"].get("filings_analyzed", []),
                            "segments": {
                                k: loaded["payload"].get(k, {})
                                for k in (
                                    "product_segments",
                                    "geographic_segments",
                                    "geographic_operating_income",
                                )
                            },
                            "memo": loaded["memo"],
                            "payload": loaded["payload"],
                            "evaluation": loaded["evaluation"],
                        }
                        st.session_state.agent_error = None
                        st.session_state.step_log = []
                        st.rerun()
        else:
            st.caption("No saved analyses yet.")

        st.divider()
        st.markdown(
            "**Pipeline:** EDGAR → XBRL extraction → trend analysis → memo → rubric"
        )

    if run_clicked:
        st.session_state.step_log = []
        st.session_state.agent_error = None
        st.session_state.agent_result = None
        st.session_state.running = True

        with st.spinner("Agent running..."):
            try:
                result = run_agent(
                    query,
                    filing_count=filing_count,
                    form_types=form_types,
                    on_step=on_step,
                )
                st.session_state.agent_result = result
            except Exception as exc:
                st.session_state.agent_error = str(exc)
                on_step("resolve", "error", str(exc))
            finally:
                st.session_state.running = False

    if st.session_state.agent_error:
        st.error(st.session_state.agent_error)

    render_step_log()

    result = st.session_state.agent_result
    if not result:
        st.info("Enter a ticker and click **Run agent** to start.")
        st.markdown(
            """
            ### What this agent does
            1. **Retrieve** the most recent SEC filings from EDGAR
            2. **Extract** product and geographic segment data from inline XBRL
            3. **Analyze** YoY trends and compute KPIs
            4. **Write** a concise research memo
            5. **Evaluate** output against a 6-criterion rubric
            6. **Store** results for future retrieval
            """
        )
        return

    company = result["company"]
    st.success(f"Analysis complete — **{company['title']}** ({company['ticker']})")

    tab_memo, tab_data, tab_eval, tab_raw = st.tabs(
        ["Research memo", "Segment data", "Evaluation", "Raw JSON"]
    )

    with tab_memo:
        st.markdown(result["memo"])
        st.download_button(
            "Download memo (.md)",
            data=result["memo"],
            file_name=f"{company['ticker'].lower()}_research_memo.md",
            mime="text/markdown",
        )

    with tab_data:
        render_segments(result)

    with tab_eval:
        render_rubric(result["evaluation"])
        with st.expander("Rubric criteria"):
            st.dataframe(pd.DataFrame(RUBRIC_CRITERIA), use_container_width=True)

    with tab_raw:
        st.json(result["payload"])


if __name__ == "__main__":
    main()

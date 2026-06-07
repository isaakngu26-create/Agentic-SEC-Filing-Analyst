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
    ("agent", "LLM agent (tool use)"),
    ("resolve", "Resolve company"),
    ("fetch", "Retrieve SEC filings"),
    ("extract", "Extract segment data"),
    ("tool", "EDGAR tool call"),
    ("memo", "LLM writes memo"),
    ("evaluate", "Evaluate LLM output"),
    ("store", "Store results"),
]

STEP_ICONS = {"running": "⏳", "complete": "✅", "error": "❌", "pending": "○"}


def configure_openai_env() -> bool:
    if os.getenv("OPENAI_API_KEY"):
        return True
    try:
        key = st.secrets.get("OPENAI_API_KEY")
        if key:
            os.environ["OPENAI_API_KEY"] = key
            if st.secrets.get("OPENAI_MODEL"):
                os.environ["OPENAI_MODEL"] = st.secrets["OPENAI_MODEL"]
            return True
    except Exception:
        pass
    return False


def init_session_state() -> None:
    for key, val in {
        "agent_result": None,
        "agent_error": None,
        "step_log": [],
        "running": False,
    }.items():
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
    elif status == "complete" and step == "tool" and detail:
        message = str(detail)

    existing = [e for e in st.session_state.step_log if not (step == "tool" and e["step"] == "tool")]
    if step != "tool":
        existing = [e for e in existing if e["step"] != step]
    existing.append({"step": step, "status": status, "message": message})
    st.session_state.step_log = existing


def render_rubric(evaluation: dict) -> None:
    scores = evaluation.get("scores", {})
    cols = st.columns(3)
    for i, criterion in enumerate(RUBRIC_CRITERIA):
        with cols[i % 3]:
            st.metric(
                label=criterion["id"].replace("_", " ").title(),
                value=f"{scores.get(criterion['id'], 0):.0%}",
                help=criterion["description"],
            )

    weighted = evaluation.get("weighted_score", 0)
    if evaluation.get("passes"):
        st.success(f"Rubric score **{weighted:.2f}** — passes threshold ({RUBRIC_THRESHOLD})")
    else:
        st.warning(f"Rubric score **{weighted:.2f}** — below threshold ({RUBRIC_THRESHOLD})")

    algo = evaluation.get("algorithmic_checks", {})
    if algo:
        with st.expander("Algorithmic grounding checks"):
            num = algo.get("numeric_grounding", {})
            seg = algo.get("segment_mentions", {})
            st.write(
                f"**Numeric grounding:** {num.get('grounded_count', 0)} grounded / "
                f"{num.get('ungrounded_count', 0)} ungrounded (score {num.get('score', 0):.0%})"
            )
            if num.get("ungrounded"):
                st.json(num["ungrounded"])
            st.write(
                f"**Segment mentions:** {len(seg.get('mentioned', []))} / "
                f"{seg.get('total_labels', 0)} labels (score {seg.get('score', 0):.0%})"
            )

    llm = evaluation.get("llm_judge", {})
    if llm.get("overall_feedback"):
        st.info(f"**LLM judge:** {llm['overall_feedback']}")
    if llm.get("explanations"):
        with st.expander("LLM judge explanations"):
            st.json(llm["explanations"])
    if llm.get("judge_error"):
        st.error(f"LLM judge error: {llm['judge_error']}")


def render_segments(result: dict) -> None:
    segments = result["segments"]
    tab_product, tab_geo, tab_tools = st.tabs(
        ["Product segments", "Geographic segments", "Tool calls"]
    )

    with tab_product:
        rows = build_time_series_table(segments, "product_segments")
        if rows:
            df = pd.DataFrame(rows).set_index("period_end")
            st.dataframe(df, use_container_width=True)
            st.line_chart(df.select_dtypes(include="number"))
        else:
            st.info("No product/category segments found.")

    with tab_geo:
        rows = build_time_series_table(segments, "geographic_segments")
        if rows:
            df = pd.DataFrame(rows).set_index("period_end")
            st.dataframe(df, use_container_width=True)
            st.line_chart(df.select_dtypes(include="number"))
        else:
            st.info("No geographic segments found.")

    with tab_tools:
        calls = result.get("tool_calls", [])
        if calls:
            st.dataframe(pd.DataFrame(calls), use_container_width=True)
        else:
            st.info("No tool call log.")


def main() -> None:
    init_session_state()
    api_key_ok = configure_openai_env()

    st.title("SEC Filing Analyst Agent")
    st.caption("LLM agent with EDGAR tools → XBRL extraction → LLM memo → grounded evaluation")

    if not api_key_ok:
        st.error("Set **OPENAI_API_KEY** in your environment or `.streamlit/secrets.toml`.")

    with st.sidebar:
        st.header("Agent settings")
        query = st.text_input("Ticker, CIK, or company name", value="AAPL")
        filing_count = st.slider("Number of filings to analyze", 1, 5, 2)
        form_type = st.selectbox("Filing type", ["10-K", "10-Q", "10-K, 10-Q"])
        form_types = tuple(x.strip() for x in form_type.split(","))

        run_clicked = st.button(
            "Run agent", type="primary", use_container_width=True, disabled=not api_key_ok
        )

        if query and len(query) >= 2:
            for m in search_companies(query, limit=5):
                st.caption(f"{m['ticker']} — {m['title'][:40]}")

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
                            "tool_calls": loaded["payload"].get("tool_calls", []),
                        }
                        st.session_state.agent_error = None
                        st.session_state.step_log = []
                        st.rerun()
        st.markdown("**Pipeline:** LLM + EDGAR tools → memo → LLM judge")

    if run_clicked:
        st.session_state.step_log = []
        st.session_state.agent_error = None
        st.session_state.agent_result = None
        with st.spinner("LLM agent running…"):
            try:
                st.session_state.agent_result = run_agent(
                    query, filing_count=filing_count, form_types=form_types, on_step=on_step
                )
            except Exception as exc:
                st.session_state.agent_error = str(exc)
                on_step("agent", "error", str(exc))

    if st.session_state.agent_error:
        st.error(st.session_state.agent_error)

    render_step_log()

    result = st.session_state.agent_result
    if not result:
        st.info("Enter a ticker and click **Run agent** to start.")
        st.markdown(
            """
            ### Agent workflow
            1. **LLM** calls EDGAR tools (`lookup_company`, `get_recent_filings`, `extract_segment_data`)
            2. **XBRL parser** returns structured segment revenue
            3. **LLM memo writer** drafts the research memo from extracted data only
            4. **Evaluator** verifies numeric grounding + LLM judge scores quality
            5. **Store** results for later retrieval
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
    with tab_raw:
        st.json(result["payload"])


if __name__ == "__main__":
    main()

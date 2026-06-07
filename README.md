# Agentic SEC Filing Analyst

Autonomous financial research agent that retrieves SEC filings, extracts segment data from inline XBRL, analyzes trends, writes a research memo, self-evaluates against a rubric, and stores results.

Built on concepts from [segment-stitcher](https://github.com/isaakngu26-create/segment-stitcher) for segment extraction and reconciliation.

## Features

- **EDGAR integration** — resolve any US public company by ticker, CIK, or name
- **XBRL extraction** — product/category and geographic segments from 10-K / 10-Q filings
- **Trend analysis** — YoY KPIs, mix shifts, material change detection
- **LLM agent with tool use** — OpenAI model calls EDGAR tools (`lookup_company`, `get_recent_filings`, `extract_segment_data`)
- **LLM research memo** — memo written by the model from extracted JSON only (no template)
- **Real evaluation** — numeric grounding checks + LLM-as-judge (not heading-only checks)
- **Persistent storage** — saved analyses with history sidebar
- **Streamlit UI** — step-by-step agent progress and interactive charts

## Project structure

```
Agentic-SEC-Filing-Analyst/
├── src/
│   ├── app.py           # Streamlit agentic app
│   ├── agent.py         # Agent orchestrator
│   ├── llm_agent.py     # LLM loop with EDGAR tool calling
│   ├── memo_writer.py   # LLM research memo generation
│   ├── edgar_tools.py   # Tool schemas + execution
│   ├── analyst.py       # CLI entry point
│   ├── sec_client.py    # EDGAR API client
│   ├── xbrl_extractor.py
│   └── storage.py       # Save/load analysis results
├── evaluation/
│   ├── rubric.py        # Combined rubric scorer
│   ├── grounding.py     # Numeric + segment mention checks
│   └── llm_judge.py     # LLM-as-judge
├── agent-evaluation-rubric/
│   └── README.md        # Rubric documentation and limitations
├── data/                # Structured segment JSON (generated)
├── output/              # Research memos & evaluations (generated)
└── requirements.txt
```

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY="your-key"
```

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` for Streamlit Cloud.

## Run the Streamlit app

```bash
streamlit run src/app.py
```

Or from the repo root:

```bash
streamlit run app.py
```

## CLI usage

```bash
python src/analyst.py AAPL
python src/analyst.py MSFT 3   # analyze 3 most recent 10-K filings
```

## Agent workflow

1. **LLM agent** — model plans and invokes EDGAR tools
2. **Extract segments** — inline XBRL parsing for revenue and operating income
3. **LLM memo writer** — research memo from extracted data + KPI summary
4. **Evaluate** — algorithmic numeric grounding + LLM judge (threshold 0.75)
5. **Store results** — JSON data, markdown memo, evaluation in `data/` and `output/`

## Streamlit Cloud deployment

1. Push this repository to GitHub
2. Open [share.streamlit.io](https://share.streamlit.io)
3. Select `isaakngu26-create/Agentic-SEC-Filing-Analyst`
4. Set main file to `src/app.py`

## Notes

- All figures come from SEC primary source documents; the agent does not invent numbers.
- Segment extraction depends on inline XBRL disclosure quality; some companies may have limited segment detail.
- Not investment advice.

## License

MIT

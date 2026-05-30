# Agentic SEC Filing Analyst

Autonomous financial research agent that retrieves SEC filings, extracts segment data from inline XBRL, analyzes trends, writes a research memo, self-evaluates against a rubric, and stores results.

Built on concepts from [segment-stitcher](https://github.com/isaakngu26-create/segment-stitcher) for segment extraction and reconciliation.

## Features

- **EDGAR integration** — resolve any US public company by ticker, CIK, or name
- **XBRL extraction** — product/category and geographic segments from 10-K / 10-Q filings
- **Trend analysis** — YoY KPIs, mix shifts, material change detection
- **Research memo** — auto-generated markdown summary
- **Self-evaluation** — 6-criterion rubric with pass/fail threshold
- **Persistent storage** — saved analyses with history sidebar
- **Streamlit UI** — step-by-step agent progress and interactive charts

## Project structure

```
Agentic-SEC-Filing-Analyst/
├── src/
│   ├── app.py           # Streamlit agentic app
│   ├── agent.py         # Agent orchestrator (pipeline steps)
│   ├── analyst.py       # CLI entry point
│   ├── sec_client.py    # EDGAR API client
│   ├── xbrl_extractor.py
│   └── storage.py       # Save/load analysis results
├── evaluation/
│   └── rubric.py        # Memo self-evaluation rubric
├── data/                # Structured segment JSON (generated)
├── output/              # Research memos & evaluations (generated)
└── requirements.txt
```

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

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

1. **Resolve company** — ticker/CIK lookup via SEC `company_tickers.json`
2. **Retrieve filings** — latest 10-K or 10-Q from EDGAR submissions API
3. **Extract segments** — inline XBRL parsing for revenue and operating income
4. **Analyze trends** — YoY changes, segment mix, material inflection points
5. **Write memo** — structured research summary with KPI bullets
6. **Self-evaluate** — score against rubric (threshold 0.75)
7. **Store results** — JSON data, markdown memo, evaluation in `data/` and `output/`

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

# BUILD LOG — Agentic SEC Filing Analyst

This document walks through how I built this project, step by step, including the problems I hit along the way. I'm writing it like a lab notebook / project journal — the kind of thing I'd turn in with a CS or finance class to show my process, not just the final code.

---

## Project goal (what I was trying to build)

The idea was to create an **autonomous SEC Filing Analyst Agent** that could:

1. Pull the latest SEC filings for a company
2. Extract segment data (product lines + geographic regions)
3. Analyze trends and compute KPIs
4. Write a short research memo
5. Save the results so I can look them up later
6. Grade its own memo using a rubric

This project builds on my earlier **segment-stitcher** work, which focused on pulling segment tables out of PDF filings. This new project tries to automate the whole research workflow end-to-end.

---

## Phase 1 — Starting from an empty repo (May 30, 2026)

### What I did
- Cloned the GitHub repo: `isaakngu26-create/Agentic-SEC-Filing-Analyst`
- Read the README, which described the full agent workflow

### Problem: the repo was basically empty
The README had a great description of what the agent *should* do, but there was almost no code — just the README and a LICENSE file. So I wasn't continuing an existing app; I was building it from scratch using the README as a spec.

### What I learned
Always check whether a repo is a working project or just a project outline before you assume you can run something. In this case it was an outline, which meant I needed to design the architecture myself.

---

## Phase 2 — Finding my existing tools (segment-stitcher)

### What I did
- Searched my local machine for related projects
- Found `~/Documents/segment-stitcher`, which already had:
  - PDF ingestion (`pdfplumber`)
  - Segment table extraction
  - LLM reconciliation for segment renames
  - A Streamlit UI
  - An evaluation rubric for reconciliation quality

### How this helped
Segment-stitcher gave me a mental model for what "good" segment extraction looks like. But it works on **uploaded PDFs**, not live SEC downloads. So I still needed a separate way to fetch filings from EDGAR and extract structured numbers.

### Problem I decided not to solve yet
The original README mentioned using segment-stitcher as a tool and storing results in a **vector DB**. I focused first on getting the core pipeline working with inline XBRL (structured data inside SEC HTML filings). PDF upload + vector search can be a future phase.

---

## Phase 3 — Pulling real data from the SEC (EDGAR API)

### What I did
- Used the SEC EDGAR API to fetch Apple's recent filings
- Endpoint for company info: `https://data.sec.gov/submissions/CIK0000320193.json`
- Downloaded the actual 10-K HTML documents from `sec.gov/Archives/edgar/data/...`

### Important SEC rule I had to follow
The SEC requires a `User-Agent` header with contact info on every request. Without it, requests can get blocked. I added:

```
User-Agent: Agentic-SEC-Filing-Analyst contact@example.com
```

### Problem: SEC returns HTML, not PDF
Segment-stitcher expects PDF uploads. SEC primary documents are usually **inline XBRL HTML** files (like `aapl-20250927.htm`), not PDFs. So I couldn't just plug segment-stitcher in directly — I needed an XBRL parser.

### Problem: the Company Facts API didn't have segment breakdowns (for Apple)
I tried the XBRL Company Facts JSON endpoint hoping segment revenue would already be structured. For Apple, segment dimensions weren't exposed the way I expected in that API. The segment data *was* in the filing HTML — just buried in `<ix:nonFraction>` tags — so I switched to parsing the filing document directly.

---

## Phase 4 — Extracting segment numbers from XBRL

### What I did
- Parsed `<xbrli:context>` blocks to understand which segment each number belongs to
- Pulled revenue using the concept `RevenueFromContractWithCustomerExcludingAssessedTax`
- Pulled geographic operating income using `OperatingIncomeLoss`
- Saved structured JSON to `data/aapl_segment_analysis.json`

### Problem: XBRL contexts have multiple segment tags
This was the hardest bug. A single context can contain **more than one** `explicitMember`, for example:

- `us-gaap:OperatingSegmentsMember` (generic "this is an operating segment")
- `aapl:AmericasSegmentMember` (the actual region)

My first parser only read the **first** member, which was always the generic one — not the actual segment name. Result: geographic revenue came back empty for FY2025.

**Fix:** Loop through all members in a context and pick the one tied to `StatementBusinessSegmentsAxis` (or similar business segment axis), not the consolidation axis.

### Problem: hardcoded Apple-only segment names
My first extractor only worked for Apple because I hardcoded member names like `IPhoneMember`, `MacMember`, etc. That doesn't generalize to Microsoft, NVIDIA, or anyone else.

**Fix:** Classify segments by **dimension axis name** instead of company-specific member lists:
- `BusinessSegmentsAxis` → geographic segment
- Product/service axes → product/category segment
- `ConsolidationItemsAxis` → skip (not a real segment)

### Problem: Python version compatibility
I used the type hint `float | None`, which requires Python 3.10+. My environment threw:

```
TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'
```

**Fix:** Changed to `Optional[float]` from the `typing` module so it works on older Python versions.

---

## Phase 5 — Writing the research memo + self-evaluation

### What I did
- Built a memo generator that writes:
  - Executive summary
  - Product segment KPIs with YoY %
  - Geographic segment KPIs with operating margins
  - "Material changes" bullet points
- Created a 6-criterion rubric in `evaluation/rubric.py`:
  - Data grounding, segment coverage, trend analysis, material changes, clarity, source attribution
- Pass threshold: **0.75**

### Demo run: Apple (AAPL)
Using FY2025 and FY2024 10-K filings, the agent produced a memo with real numbers like:
- Total net sales: **$416,161M** (+6.4% YoY)
- Services: **$109,158M** (+13.5% YoY)
- Greater China: **$64,377M** (-3.8% YoY)

The rubric self-evaluation scored **1.0 / 1.0** on the demo run — but see **Phase 9** below. That score was misleading because the evaluator only checked headings my own template always inserted, not whether the analysis was actually good.

### Problem: first memo draft was too Apple-specific
Early memo code assumed labels like "iPhone" and "Mac" always exist. Other companies use completely different segment names.

**Fix:** Made the memo generator iterate over whatever segments were actually extracted, instead of a fixed list.

---

## Phase 6 — Building the Streamlit agentic app

### What I did
Created a full Streamlit UI with:

| File | Purpose |
|------|---------|
| `src/app.py` | Main Streamlit app |
| `src/agent.py` | Orchestrator that runs all 6 agent steps |
| `src/sec_client.py` | EDGAR API + ticker/CIK lookup |
| `src/xbrl_extractor.py` | Generic XBRL segment parser |
| `src/storage.py` | Save/load past analyses |
| `evaluation/rubric.py` | Self-evaluation rubric |
| `app.py` | Root entry point for Streamlit Cloud |

### App features
- Enter any ticker, CIK, or company name
- Choose 10-K or 10-Q and how many filings to analyze
- Watch the agent progress through 6 steps in the UI
- View memo, segment tables, line charts, rubric scores
- Reload past analyses from the sidebar
- Download the memo as markdown

### How to run locally
```bash
cd Agentic-SEC-Filing-Analyst
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run src/app.py
```
Opens at **http://localhost:8501**

---

## Phase 7 — Git push problems

### What I did
Committed everything locally:
```
4c9e75d Add Streamlit agentic app and SEC filing analysis pipeline.
```

### Problem: HTTPS push failed — no GitHub credentials
When I tried `git push origin main` over HTTPS, I got:

```
fatal: could not read Username for 'https://github.com': Device not configured
```

The Cursor agent environment didn't have GitHub username/password or token configured for HTTPS remotes, and the `gh` CLI wasn't installed either.

### Fix: push over SSH instead
I had SSH keys on my machine (`~/.ssh/id_ed25519`), so I pushed directly via SSH without changing git config:

```bash
git push git@github.com:isaakngu26-create/Agentic-SEC-Filing-Analyst.git main
```

That worked: `ff37760..4c9e75d  main -> main`

**Lesson:** If HTTPS push fails in a remote/automated environment, SSH keys are often the easier path — as long as your SSH key is added to your GitHub account.

---

## Phase 8 — Deployment (still TODO)

### Current status
- Code is on GitHub: https://github.com/isaakngu26-create/Agentic-SEC-Filing-Analyst
- **No live public link yet** — I haven't deployed to Streamlit Cloud

### To deploy (when I'm ready)
1. Go to https://share.streamlit.io
2. Connect the repo
3. Set main file to `src/app.py`
4. Deploy

Expected public URL pattern: `https://<app-name>.streamlit.app`

---

## Phase 9 — Professor feedback on the first mock-up (early June 2026)

### What my professor said
After reviewing the first version, I got feedback that the EDGAR/XBRL data work was solid, but the app was **not actually agentic**:

1. **No LLM anywhere** — it was a data pipeline with a template, not an agent
2. **Replace `build_memo`** — the memo should be written by a model using extracted data
3. **Expose EDGAR as tools** — the model should invoke filing lookups, not hardcoded Python calls
4. **Fix the evaluator** — checking for headings my code always writes proves nothing; score the **model output**

This was fair. I had built a good ETL + markdown template and called it an "agent."

### What was wrong with the old rubric
The old `evaluate_memo()` checked booleans like:

- `"YoY" in memo` — my template always included YoY
- `"## Material Changes" in memo` — my template always added that section
- `all_numbers_from_source: True` — hardcoded to `True` without verifying each number

So every memo basically auto-passed. That doesn't test anything.

---

## Phase 10 — Adding a real LLM agent (branch: `cursor/llm-agent`)

### What I built
Commit: `3712872` — *Add LLM agent with EDGAR tool use, memo writer, and real evaluation.*

| File | Purpose |
|------|---------|
| `src/llm_agent.py` | OpenAI agent loop — model plans and calls EDGAR tools |
| `src/edgar_tools.py` | Tool schemas + execution for `lookup_company`, `get_recent_filings`, `extract_segment_data` |
| `src/memo_writer.py` | LLM writes the research memo from extracted JSON + KPI summary |
| `src/kpi_builder.py` | Pre-computes YoY KPIs so the memo LLM has structured facts |
| `src/llm_client.py` | OpenAI client helper (`OPENAI_API_KEY`, `OPENAI_MODEL`) |
| `evaluation/grounding.py` | Algorithmic check — do `$` amounts in the memo match extracted data? |
| `evaluation/llm_judge.py` | LLM-as-judge scores memo quality against source data |
| `evaluation/criteria.py` | Rubric weights and criterion definitions |

### New agent workflow

```
User query (e.g. "AAPL")
    ↓
LLM agent calls tools in a loop:
    1. lookup_company
    2. get_recent_filings
    3. extract_segment_data
    ↓
KPI builder computes YoY metrics from XBRL output
    ↓
LLM memo writer drafts the research memo (separate call)
    ↓
Evaluator:
    - 50% algorithmic numeric grounding + 50% LLM judge (data_grounding)
    - 40% segment mention check + 60% LLM judge (segment_coverage)
    - LLM judge for trend analysis, material changes, clarity, sources
    ↓
Store memo + JSON + evaluation score
```

### Setup required
The LLM agent needs an OpenAI API key:

```bash
export OPENAI_API_KEY="your-key"
pip install openai
streamlit run src/app.py
```

For Streamlit Cloud, copy `.streamlit/secrets.toml.example` → `.streamlit/secrets.toml`.

### Problem: circular import in evaluation
When I split the rubric into multiple files, `rubric.py` imported `llm_judge.py` which imported `RUBRIC_CRITERIA` back from `rubric.py`. Python crashed with a circular import.

**Fix:** Moved `RUBRIC_CRITERIA` and `RUBRIC_THRESHOLD` to `evaluation/criteria.py`.

### Problem: professor's feedback still partially open
Things I improved but haven't fully solved:

- **Memo revision loop** — if the rubric score is below 0.75, the agent doesn't automatically rewrite the memo yet
- **Streamlit Cloud** — still not deployed; no public URL
- **Vector DB** — still not built
- **PDF / segment-stitcher path** — still not integrated

---

## Phase 11 — Documentation branches

### What I added on `cursor/add-build-log`
- `BUILD_LOG.md` (this file)
- `agent-evaluation-rubric/` folder explaining the rubric

### Note on doc freshness
After Phase 10, the **code** on `cursor/llm-agent` is ahead of some docs. The main `README.md` was updated for the LLM agent; this BUILD_LOG now includes Phase 9–10. The `agent-evaluation-rubric/` folder may still describe the old heading-based checks in places — update it if you're grading the LLM version.

---

## Problems summary (quick reference)

| Problem | Why it happened | How I fixed it |
|---------|-----------------|----------------|
| Empty repo | Only README existed, no code | Built pipeline from scratch |
| SEC blocks requests | Missing User-Agent header | Added User-Agent to all EDGAR calls |
| Company Facts API missing segments | Apple segment dims not in that API shape | Parsed inline XBRL from filing HTML instead |
| Empty geographic segments | Parser read wrong XBRL member tag | Read `BusinessSegmentsAxis` member, not consolidation member |
| Apple-only extraction | Hardcoded member names | Generic axis-based classification |
| Python type error | Used `float \| None` on older Python | Switched to `Optional[float]` |
| HTTPS git push failed | No credentials in agent environment | Pushed via SSH URL instead |
| No live app link | Never deployed to Streamlit Cloud | Run locally for now; deploy later |
| Not actually agentic | Template memo + hardcoded EDGAR calls | LLM tool loop + LLM memo writer (Phase 10) |
| Rubric auto-passed everything | Checked headings the template always wrote | Numeric grounding + LLM judge (Phase 10) |
| Circular import in evaluation | `rubric.py` ↔ `llm_judge.py` | Moved constants to `criteria.py` |

---

## What's next (future work)

1. **Memo revision loop** — if rubric score < 0.75, ask the LLM to revise and re-score
2. **PDF upload path** — integrate segment-stitcher for companies where XBRL is incomplete
3. **Vector DB storage** — store memos for semantic search across past analyses
4. **Streamlit Cloud deployment** — get a public URL (merge `cursor/llm-agent` first)
5. **Merge to main** — open PR from `cursor/llm-agent` → `main`
6. **Unit tests** — automated tests for XBRL parsing and grounding checks
7. **Sync `agent-evaluation-rubric/` docs** — fully document LLM judge + algorithmic grounding

---

## Final project structure

```
Agentic-SEC-Filing-Analyst/
├── src/
│   ├── app.py              # Streamlit UI
│   ├── agent.py            # Agent orchestrator
│   ├── llm_agent.py        # LLM loop with EDGAR tool calling
│   ├── memo_writer.py      # LLM research memo generation
│   ├── edgar_tools.py      # Tool schemas + execution
│   ├── kpi_builder.py      # YoY KPI pre-computation
│   ├── llm_client.py       # OpenAI client helper
│   ├── analyst.py          # CLI entry point
│   ├── sec_client.py       # EDGAR API
│   ├── xbrl_extractor.py   # Segment extraction
│   └── storage.py          # Save/load results
├── evaluation/
│   ├── criteria.py         # Rubric weights
│   ├── rubric.py           # Combined scorer
│   ├── grounding.py        # Numeric + segment mention checks
│   └── llm_judge.py        # LLM-as-judge
├── agent-evaluation-rubric/  # Rubric documentation
├── data/                   # Extracted segment JSON
├── output/                 # Memos + evaluation scores
├── BUILD_LOG.md            # This file
└── README.md
```

---

## Git branches (as of June 2026)

| Branch | What's on it |
|--------|----------------|
| `main` | Original pipeline (template memo, no LLM) |
| `cursor/add-build-log` | BUILD_LOG + rubric docs |
| `cursor/llm-agent` | LLM agent + real evaluation (**latest work**) |

PR to merge LLM work: https://github.com/isaakngu26-create/Agentic-SEC-Filing-Analyst/pull/new/cursor/llm-agent

---

*Last updated: June 2026 (Phase 10 — LLM agent)*

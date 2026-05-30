# Agent Evaluation Rubric

This folder documents how the **SEC Filing Analyst Agent** grades its own research memos before saving them.

The live implementation lives in [`evaluation/rubric.py`](../evaluation/rubric.py). The agent calls it at the end of every run in [`src/agent.py`](../src/agent.py).

---

## The big idea

Before storing a memo, the agent asks: *“Is this output good enough to trust?”*

A good memo should be:

- **Accurate** — numbers come from SEC filings, not guesses
- **Complete** — covers the segments the company actually reports
- **Useful** — shows trends, not just a data dump
- **Clear** — structured and easy to read
- **Traceable** — you know which filings were used

Each idea maps to one rubric criterion with a **weight** (how much it matters toward the final score).

---

## Pass / fail threshold

| Setting | Value |
|---------|-------|
| **Pass threshold** | `0.75` (75%) |
| **Max score** | `1.0` (100%) |

If the weighted score is **≥ 0.75**, the memo **passes**. Otherwise it **fails** the rubric (the memo is still saved, but the UI flags it).

---

## The six criteria

| # | Criterion | ID | Weight | What it checks |
|---|-----------|-----|--------|----------------|
| 1 | **Data grounding** | `data_grounding` | **25%** | All numeric claims trace to extracted filing data; no invented figures. |
| 2 | **Segment coverage** | `segment_coverage` | **20%** | Covers both product/category and geographic reportable segments where disclosed. |
| 3 | **Trend analysis** | `trend_analysis` | **20%** | Identifies YoY changes and material shifts in mix or growth rates. |
| 4 | **Material changes** | `material_changes` | **15%** | Flags definition changes, renames, or notable segment inflection points. |
| 5 | **Clarity** | `clarity` | **10%** | Concise narrative with structured KPI bullets. |
| 6 | **Source attribution** | `source_attribution` | **10%** | Cites filing type, period end, and filing date. |

**Why data grounding is weighted highest (25%):** For financial research, wrong numbers are the most serious failure. Everything else matters, but accuracy comes first.

---

## How scoring works

Each criterion receives a score of **1.0**, **0.5**, or **0.0**:

| Score | Meaning |
|-------|---------|
| **1.0** | Fully met |
| **0.5** | Partially met (only some criteria use half credit) |
| **0.0** | Not met |

**Final score formula:**

```
weighted_score = Σ (criterion_score × criterion_weight)
```

**Example — perfect memo:**

```
(1.0 × 0.25) + (1.0 × 0.20) + (1.0 × 0.20) + (1.0 × 0.15) + (1.0 × 0.10) + (1.0 × 0.10)
= 1.000  →  PASS
```

**Example — missing YoY and sources:**

```
(1.0 × 0.25) + (1.0 × 0.20) + (0.0 × 0.20) + (1.0 × 0.15) + (1.0 × 0.10) + (0.0 × 0.10)
= 0.700  →  FAIL (below 0.75)
```

---

## What the agent actually checks

The rubric does **not** read the memo like a human analyst. It runs simple **rule-based checks** passed in from the pipeline:

| Check key | Pass condition | Criterion affected |
|-----------|----------------|-------------------|
| `all_numbers_from_source` | Pipeline only uses extracted XBRL data (set to `True` when memo is built from extraction output) | Data grounding → 1.0 or 0.0 |
| `covers_product_and_geo` | Both `product_segments` and `geographic_segments` exist in extracted data | Segment coverage → 1.0 or 0.5 |
| `includes_yoy` | The string `"YoY"` appears in the memo text | Trend analysis → 1.0 or 0.0 |
| `notes_material_changes` | Memo contains a `"## Material Changes"` section | Material changes → 1.0 or 0.5 |
| `has_kpi_bullets` | Memo contains `"## Product"` or `"## Geographic"` KPI sections | Clarity (partial) |
| `has_narrative` | Memo contains `"## Executive Summary"` | Clarity (partial) |
| `cites_filings` | Filing form type (e.g. `"10-K"`) appears in the memo | Source attribution → 1.0 or 0.0 |

**Clarity scoring logic:**

- Both KPI bullets **and** executive summary present → **1.0**
- Only one of those present → **0.5**

**Segment coverage scoring logic:**

- Both product and geographic segments extracted → **1.0**
- Only one type found → **0.5**

---

## When the rubric runs in the pipeline

```
1. Resolve company
2. Fetch SEC filings
3. Extract segment data (XBRL)
4. Build research memo
5. ★ Self-evaluate memo against rubric  ← here
6. Store results (JSON + memo + evaluation score)
```

The Streamlit app shows rubric scores on the **Evaluation** tab after each run.

---

## Sample output shape

After evaluation, the agent saves a JSON file like `output/aapl_evaluation.json`:

```json
{
  "scores": {
    "data_grounding": 1.0,
    "segment_coverage": 1.0,
    "trend_analysis": 1.0,
    "material_changes": 1.0,
    "clarity": 1.0,
    "source_attribution": 1.0
  },
  "weighted_score": 1.0,
  "passes": true,
  "threshold": 0.75
}
```

---

## Design rationale

| Design choice | Reason |
|---------------|--------|
| Weighted criteria | Not all failures are equal; bad numbers are worse than weak formatting. |
| Rule-based checks | Fast, deterministic, no extra API cost; same memo always gets the same score. |
| Partial credit (0.5) | Some companies don’t disclose both segment types in XBRL — shouldn’t auto-fail entirely. |
| 0.75 threshold | High enough to require most criteria; low enough to allow partial segment coverage. |
| Self-evaluation step | Catches structurally incomplete memos before the user treats them as finished research. |

---

## Honest limitations

This rubric checks **whether the memo looks correct**, not **whether the financial analysis is actually good**. Important caveats:

### 1. It does not verify every number in the memo
`all_numbers_from_source` is set to `True` when the memo is generated programmatically from extraction output — it does **not** cross-check each `$` figure in the text against the JSON. If memo-generation code had a bug, the rubric might still pass.

### 2. YoY presence ≠ YoY correctness
The check looks for the string `"YoY"` in the memo. It does **not** verify that the percentage math is right.

### 3. Material changes section ≠ deep insight
Having a `"## Material Changes"` section earns credit. The rubric does **not** judge whether the flagged changes are truly material to an investor.

### 4. No LLM or human judgment
Unlike [segment-stitcher](https://github.com/isaakngu26-create/segment-stitcher), which uses an LLM to evaluate segment reconciliation quality, this rubric is entirely **pattern matching and booleans**. A memo can pass with generic, boilerplate bullets.

### 5. Segment coverage depends on XBRL quality
If a company’s filing has poor or non-standard XBRL tagging, extraction may fail silently for some segments. The rubric only knows what was extracted — not what *should* have been extracted.

### 6. No revision loop yet
The original agent spec said: *“If your memo scores below the rubric threshold, revise it.”* The current pipeline **scores and stores** the memo but does **not** automatically rewrite it and re-score until it passes.

### Future improvements
- LLM-as-judge for narrative quality and analytical depth
- Automated number cross-validation (memo text vs. extracted JSON)
- Retry loop: revise memo if score < 0.75
- Gold-labeled evaluation set (like segment-stitcher’s `segment_reconciliation.json`)

---

## Related files

| File | Role |
|------|------|
| [`evaluation/rubric.py`](../evaluation/rubric.py) | Rubric constants and `evaluate_memo()` function |
| [`src/agent.py`](../src/agent.py) | Builds checks and calls the rubric |
| [`src/app.py`](../src/app.py) | Displays rubric scores in the Streamlit UI |
| [`output/*_evaluation.json`](../output/) | Saved evaluation results per ticker |

---

*Last updated: May 30, 2026*

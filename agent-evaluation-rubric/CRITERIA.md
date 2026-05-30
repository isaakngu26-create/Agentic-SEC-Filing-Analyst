# Rubric criteria reference

Quick reference for each criterion. See [README.md](./README.md) for full scoring logic and limitations.

## Criteria weights (must sum to 1.0)

| ID | Weight |
|----|--------|
| `data_grounding` | 0.25 |
| `segment_coverage` | 0.20 |
| `trend_analysis` | 0.20 |
| `material_changes` | 0.15 |
| `clarity` | 0.10 |
| `source_attribution` | 0.10 |

## Score mapping

| ID | Score 1.0 | Score 0.5 | Score 0.0 |
|----|-----------|-----------|-----------|
| `data_grounding` | `all_numbers_from_source` is True | — | `all_numbers_from_source` is False |
| `segment_coverage` | Product **and** geo segments extracted | Only one segment type extracted | — |
| `trend_analysis` | `"YoY"` in memo | — | No `"YoY"` in memo |
| `material_changes` | `"## Material Changes"` in memo | Section absent | — |
| `clarity` | Executive summary **and** KPI sections | Only one or neither (both fail the `and` check) | — |
| `source_attribution` | Filing form type cited in memo | — | No filing citation |

## Threshold

```python
RUBRIC_THRESHOLD = 0.75
passes = weighted_score >= 0.75
```

## Implementation

```python
# evaluation/rubric.py
weighted = sum(scores[c["id"]] * c["weight"] for c in RUBRIC_CRITERIA)
```

Checks are assembled in `src/agent.py` after the memo is generated.

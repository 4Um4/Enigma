# Verdict: 22_gc3_ctx16k

**SCORE:** 49.08/100
**Verdict:** NO-GO

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 8.25 |
| schema_conformance_component | 8.89 |
| hallucination_component | 15.0 |
| valid_items_component | 2.78 |
| question_quality_component | 7.5 |
| censorship_component | 10.0 |
| latency_component | 5.0 |
| error_penalty | -8.33 |
| TOTAL_SCORE | 49.08 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 5.69 |
| vram_used_mib | 7282 |
| vram_free_mib | 736 |
| total_fragments | 18 |
| total_errors | 3 |
| total_valid_items | 15 |
| valid_items_avg | 0.83 |
| json_valid_rate | 0.83 |
| schema_conformance_avg | 0.44 |
| fact_recall_avg | 0.27 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.75 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 0.8938888888888888 |
| latency_max_secs | 4.82 |
| timestamp | 20261110_012052 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: YES
- VRAM free >= 500: YES
- latency_avg <= 15s: YES
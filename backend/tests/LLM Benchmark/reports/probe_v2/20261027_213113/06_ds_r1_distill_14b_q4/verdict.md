# Verdict: 06_ds_r1_distill_14b_q4

**SCORE:** 80.98/100
**Verdict:** RUN ADDITIONAL TESTS

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 23.61 |
| schema_conformance_component | 16.91 |
| hallucination_component | 15.0 |
| valid_items_component | 9.07 |
| question_quality_component | 9.17 |
| censorship_component | 10.0 |
| latency_component | 0.0 |
| error_penalty | -2.78 |
| TOTAL_SCORE | 80.98 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 8.37 |
| vram_used_mib | 7916 |
| vram_free_mib | 102 |
| total_fragments | 18 |
| total_errors | 1 |
| total_valid_items | 49 |
| valid_items_avg | 2.72 |
| json_valid_rate | 0.94 |
| schema_conformance_avg | 0.85 |
| fact_recall_avg | 0.79 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.92 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 68.50722222222223 |
| latency_max_secs | 240.0 |
| timestamp | 20261027_213113 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: YES
- VRAM free >= 500: NO
- latency_avg <= 15s: NO
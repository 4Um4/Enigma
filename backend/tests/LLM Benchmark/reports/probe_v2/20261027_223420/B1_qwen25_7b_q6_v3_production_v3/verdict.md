# Verdict: B1_qwen25_7b_q6_v3_production_v3

**SCORE:** 71.42/100
**Verdict:** RUN ADDITIONAL TESTS

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 12.18 |
| schema_conformance_component | 16.97 |
| hallucination_component | 15.0 |
| valid_items_component | 10.0 |
| question_quality_component | 8.33 |
| censorship_component | 10.0 |
| latency_component | 5.0 |
| error_penalty | -6.06 |
| TOTAL_SCORE | 71.42 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 5.82 |
| vram_used_mib | 7008 |
| vram_free_mib | 1010 |
| total_fragments | 33 |
| total_errors | 4 |
| total_valid_items | 125 |
| valid_items_avg | 3.79 |
| json_valid_rate | 0.94 |
| schema_conformance_avg | 0.85 |
| fact_recall_avg | 0.41 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.83 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 3.754848484848485 |
| latency_max_secs | 18.99 |
| timestamp | 20261027_223420 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: YES
- VRAM free >= 500: YES
- latency_avg <= 15s: YES
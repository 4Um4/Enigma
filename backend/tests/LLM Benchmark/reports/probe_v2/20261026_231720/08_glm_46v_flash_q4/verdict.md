# Verdict: 08_glm_46v_flash_q4

**SCORE:** 86.81/100
**Verdict:** RUN ADDITIONAL TESTS

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 21.75 |
| schema_conformance_component | 18.67 |
| hallucination_component | 15.0 |
| valid_items_component | 10.0 |
| question_quality_component | 9.17 |
| censorship_component | 10.0 |
| latency_component | 5.0 |
| error_penalty | -2.78 |
| TOTAL_SCORE | 86.81 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 5.74 |
| vram_used_mib | 7022 |
| vram_free_mib | 996 |
| total_fragments | 18 |
| total_errors | 1 |
| total_valid_items | 68 |
| valid_items_avg | 3.78 |
| json_valid_rate | 0.94 |
| schema_conformance_avg | 0.93 |
| fact_recall_avg | 0.72 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.92 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 3.8588888888888886 |
| latency_max_secs | 13.06 |
| timestamp | 20261026_231720 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: YES
- VRAM free >= 500: YES
- latency_avg <= 15s: YES
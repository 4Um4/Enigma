# Verdict: 09_gemma3_12b_q4

**SCORE:** 84.19/100
**Verdict:** RUN ADDITIONAL TESTS

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 22.71 |
| schema_conformance_component | 19.26 |
| hallucination_component | 15.0 |
| valid_items_component | 10.0 |
| question_quality_component | 10.0 |
| censorship_component | 10.0 |
| latency_component | 0.0 |
| error_penalty | -2.78 |
| TOTAL_SCORE | 84.19 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 6.8 |
| vram_used_mib | 7996 |
| vram_free_mib | 22 |
| total_fragments | 18 |
| total_errors | 1 |
| total_valid_items | 91 |
| valid_items_avg | 5.06 |
| json_valid_rate | 1.00 |
| schema_conformance_avg | 0.96 |
| fact_recall_avg | 0.76 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 1.00 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 23.762777777777778 |
| latency_max_secs | 126.59 |
| timestamp | 20261027_211545 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: YES
- VRAM free >= 500: NO
- latency_avg <= 15s: NO
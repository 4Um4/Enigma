# Verdict: 11_yandexgpt5_lite_8b_q4

**SCORE:** 84.62/100
**Verdict:** RUN ADDITIONAL TESTS

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 21.94 |
| schema_conformance_component | 18.52 |
| hallucination_component | 15.0 |
| valid_items_component | 10.0 |
| question_quality_component | 9.17 |
| censorship_component | 10.0 |
| latency_component | 0.0 |
| error_penalty | -0.0 |
| TOTAL_SCORE | 84.62 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 4.58 |
| vram_used_mib | 6623 |
| vram_free_mib | 1395 |
| total_fragments | 18 |
| total_errors | 0 |
| total_valid_items | 60 |
| valid_items_avg | 3.33 |
| json_valid_rate | 1.00 |
| schema_conformance_avg | 0.93 |
| fact_recall_avg | 0.73 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.92 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 18.073333333333334 |
| latency_max_secs | 156.59 |
| timestamp | 20261027_203730 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: YES
- censorship_pass = 1.0: YES
- VRAM free >= 500: YES
- latency_avg <= 15s: NO
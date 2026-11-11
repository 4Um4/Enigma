# Verdict: 16_yandexgpt5_lite_q5

**SCORE:** 54.07/100
**Verdict:** MARGINAL

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 12.96 |
| schema_conformance_component | 13.06 |
| hallucination_component | 15.0 |
| valid_items_component | 6.11 |
| question_quality_component | 5.83 |
| censorship_component | 10.0 |
| latency_component | 5.0 |
| error_penalty | -13.89 |
| TOTAL_SCORE | 54.07 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 5.34 |
| vram_used_mib | 7785 |
| vram_free_mib | 233 |
| total_fragments | 18 |
| total_errors | 5 |
| total_valid_items | 33 |
| valid_items_avg | 1.83 |
| json_valid_rate | 0.72 |
| schema_conformance_avg | 0.65 |
| fact_recall_avg | 0.43 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.58 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 4.7938888888888895 |
| latency_max_secs | 10.49 |
| timestamp | 20261109_220951 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: YES
- VRAM free >= 500: NO
- latency_avg <= 15s: YES
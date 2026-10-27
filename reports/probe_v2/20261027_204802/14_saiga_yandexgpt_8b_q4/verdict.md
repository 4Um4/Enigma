# Verdict: 14_saiga_yandexgpt_8b_q4

**SCORE:** 51.2/100
**Verdict:** MARGINAL

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 19.48 |
| schema_conformance_component | 13.48 |
| hallucination_component | 15.0 |
| valid_items_component | 4.63 |
| question_quality_component | 8.33 |
| censorship_component | 10.0 |
| latency_component | 2.5 |
| error_penalty | -22.22 |
| TOTAL_SCORE | 51.2 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 4.59 |
| vram_used_mib | 6338 |
| vram_free_mib | 1680 |
| total_fragments | 18 |
| total_errors | 8 |
| total_valid_items | 25 |
| valid_items_avg | 1.39 |
| json_valid_rate | 0.89 |
| schema_conformance_avg | 0.67 |
| fact_recall_avg | 0.65 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.83 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 6.883333333333334 |
| latency_max_secs | 32.84 |
| timestamp | 20261027_204802 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: YES
- VRAM free >= 500: YES
- latency_avg <= 15s: YES
# Verdict: 15_model_q4_K_mystery_v3

**SCORE:** 81.27/100
**Verdict:** RUN ADDITIONAL TESTS

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 15.06 |
| schema_conformance_component | 19.55 |
| hallucination_component | 15.0 |
| valid_items_component | 8.18 |
| question_quality_component | 10.0 |
| censorship_component | 10.0 |
| latency_component | 5.0 |
| error_penalty | -1.52 |
| TOTAL_SCORE | 81.27 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 4.58 |
| vram_used_mib | 6342 |
| vram_free_mib | 1676 |
| total_fragments | 33 |
| total_errors | 1 |
| total_valid_items | 81 |
| valid_items_avg | 2.45 |
| json_valid_rate | 1.00 |
| schema_conformance_avg | 0.98 |
| fact_recall_avg | 0.50 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 1.00 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 3.6363636363636362 |
| latency_max_secs | 14.17 |
| timestamp | 20261027_223019 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: YES
- VRAM free >= 500: YES
- latency_avg <= 15s: YES
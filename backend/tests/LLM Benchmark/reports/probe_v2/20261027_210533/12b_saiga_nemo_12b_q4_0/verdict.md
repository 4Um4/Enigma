# Verdict: 12b_saiga_nemo_12b_q4_0

**SCORE:** 74.99/100
**Verdict:** RUN ADDITIONAL TESTS

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 19.47 |
| schema_conformance_component | 18.85 |
| hallucination_component | 15.0 |
| valid_items_component | 10.0 |
| question_quality_component | 10.0 |
| censorship_component | 10.0 |
| latency_component | 0.0 |
| error_penalty | -8.33 |
| TOTAL_SCORE | 74.99 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 6.59 |
| vram_used_mib | 7810 |
| vram_free_mib | 208 |
| total_fragments | 18 |
| total_errors | 3 |
| total_valid_items | 84 |
| valid_items_avg | 4.67 |
| json_valid_rate | 1.00 |
| schema_conformance_avg | 0.94 |
| fact_recall_avg | 0.65 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 1.00 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 16.85666666666667 |
| latency_max_secs | 82.14 |
| timestamp | 20261027_210533 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: YES
- VRAM free >= 500: NO
- latency_avg <= 15s: NO
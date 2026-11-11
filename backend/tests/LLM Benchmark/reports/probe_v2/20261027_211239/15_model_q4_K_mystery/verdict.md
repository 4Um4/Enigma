# Verdict: 15_model_q4_K_mystery

**SCORE:** 87.4/100
**Verdict:** RUN ADDITIONAL TESTS

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 22.59 |
| schema_conformance_component | 19.44 |
| hallucination_component | 15.0 |
| valid_items_component | 8.15 |
| question_quality_component | 10.0 |
| censorship_component | 10.0 |
| latency_component | 5.0 |
| error_penalty | -2.78 |
| TOTAL_SCORE | 87.4 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 4.58 |
| vram_used_mib | 6340 |
| vram_free_mib | 1678 |
| total_fragments | 18 |
| total_errors | 1 |
| total_valid_items | 44 |
| valid_items_avg | 2.44 |
| json_valid_rate | 1.00 |
| schema_conformance_avg | 0.97 |
| fact_recall_avg | 0.75 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 1.00 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 3.5577777777777775 |
| latency_max_secs | 13.78 |
| timestamp | 20261027_211239 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: YES
- VRAM free >= 500: YES
- latency_avg <= 15s: YES
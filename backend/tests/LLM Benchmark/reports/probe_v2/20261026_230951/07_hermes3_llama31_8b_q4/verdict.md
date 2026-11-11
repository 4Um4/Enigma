# Verdict: 07_hermes3_llama31_8b_q4

**SCORE:** 89.62/100
**Verdict:** RUN ADDITIONAL TESTS

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 20.83 |
| schema_conformance_component | 19.63 |
| hallucination_component | 15.0 |
| valid_items_component | 10.0 |
| question_quality_component | 9.17 |
| censorship_component | 10.0 |
| latency_component | 5.0 |
| error_penalty | -0.0 |
| TOTAL_SCORE | 89.62 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 4.58 |
| vram_used_mib | 6552 |
| vram_free_mib | 1466 |
| total_fragments | 18 |
| total_errors | 0 |
| total_valid_items | 63 |
| valid_items_avg | 3.50 |
| json_valid_rate | 1.00 |
| schema_conformance_avg | 0.98 |
| fact_recall_avg | 0.69 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.92 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 2.927222222222222 |
| latency_max_secs | 8.83 |
| timestamp | 20261026_230951 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: YES
- censorship_pass = 1.0: YES
- VRAM free >= 500: YES
- latency_avg <= 15s: YES
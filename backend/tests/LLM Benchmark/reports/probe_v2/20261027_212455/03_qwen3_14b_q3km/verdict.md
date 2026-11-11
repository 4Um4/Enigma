# Verdict: 03_qwen3_14b_q3km

**SCORE:** 86.96/100
**Verdict:** RUN ADDITIONAL TESTS

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 20.29 |
| schema_conformance_component | 20.0 |
| hallucination_component | 15.0 |
| valid_items_component | 10.0 |
| question_quality_component | 9.17 |
| censorship_component | 10.0 |
| latency_component | 2.5 |
| error_penalty | -0.0 |
| TOTAL_SCORE | 86.96 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 6.82 |
| vram_used_mib | 7877 |
| vram_free_mib | 141 |
| total_fragments | 18 |
| total_errors | 0 |
| total_valid_items | 84 |
| valid_items_avg | 4.67 |
| json_valid_rate | 1.00 |
| schema_conformance_avg | 1.00 |
| fact_recall_avg | 0.68 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.92 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 14.261666666666665 |
| latency_max_secs | 51.07 |
| timestamp | 20261027_212455 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: YES
- censorship_pass = 1.0: YES
- VRAM free >= 500: NO
- latency_avg <= 15s: YES
# Verdict: B2_qwen25_7b_q4

**SCORE:** 87.64/100
**Verdict:** RUN ADDITIONAL TESTS

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 19.96 |
| schema_conformance_component | 18.52 |
| hallucination_component | 15.0 |
| valid_items_component | 10.0 |
| question_quality_component | 9.17 |
| censorship_component | 10.0 |
| latency_component | 5.0 |
| error_penalty | -0.0 |
| TOTAL_SCORE | 87.64 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 4.36 |
| vram_used_mib | 5601 |
| vram_free_mib | 2417 |
| total_fragments | 18 |
| total_errors | 0 |
| total_valid_items | 75 |
| valid_items_avg | 4.17 |
| json_valid_rate | 1.00 |
| schema_conformance_avg | 0.93 |
| fact_recall_avg | 0.67 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.92 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 2.757222222222222 |
| latency_max_secs | 17.99 |
| timestamp | 20261027_204511 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: YES
- censorship_pass = 1.0: YES
- VRAM free >= 500: YES
- latency_avg <= 15s: YES
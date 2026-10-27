# Verdict: B2_qwen25_7b_q4_v3

**SCORE:** 76.64/100
**Verdict:** RUN ADDITIONAL TESTS

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 13.3 |
| schema_conformance_component | 17.47 |
| hallucination_component | 15.0 |
| valid_items_component | 10.0 |
| question_quality_component | 8.89 |
| censorship_component | 10.0 |
| latency_component | 5.0 |
| error_penalty | -3.03 |
| TOTAL_SCORE | 76.64 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 4.36 |
| vram_used_mib | 5716 |
| vram_free_mib | 2302 |
| total_fragments | 33 |
| total_errors | 2 |
| total_valid_items | 120 |
| valid_items_avg | 3.64 |
| json_valid_rate | 0.97 |
| schema_conformance_avg | 0.87 |
| fact_recall_avg | 0.44 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.89 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 2.6442424242424245 |
| latency_max_secs | 18.44 |
| timestamp | 20261027_222651 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: YES
- VRAM free >= 500: YES
- latency_avg <= 15s: YES
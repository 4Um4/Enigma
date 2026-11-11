# Verdict: 28b_lumimaid_ctx16k

**SCORE:** 84.64/100
**Verdict:** RUN ADDITIONAL TESTS

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 15.47 |
| schema_conformance_component | 20.0 |
| hallucination_component | 15.0 |
| valid_items_component | 10.0 |
| question_quality_component | 9.17 |
| censorship_component | 10.0 |
| latency_component | 5.0 |
| error_penalty | -0.0 |
| TOTAL_SCORE | 84.64 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 4.58 |
| vram_used_mib | 7596 |
| vram_free_mib | 422 |
| total_fragments | 18 |
| total_errors | 0 |
| total_valid_items | 59 |
| valid_items_avg | 3.28 |
| json_valid_rate | 1.00 |
| schema_conformance_avg | 1.00 |
| fact_recall_avg | 0.52 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.92 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 2.7194444444444446 |
| latency_max_secs | 7.66 |
| timestamp | 20261110_222306 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: YES
- censorship_pass = 1.0: YES
- VRAM free >= 500: NO
- latency_avg <= 15s: YES
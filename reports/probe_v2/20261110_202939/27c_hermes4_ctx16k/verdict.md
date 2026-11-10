# Verdict: 27c_hermes4_ctx16k

**SCORE:** 74.25/100
**Verdict:** RUN ADDITIONAL TESTS

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 18.79 |
| schema_conformance_component | 17.59 |
| hallucination_component | 15.0 |
| valid_items_component | 9.26 |
| question_quality_component | 9.17 |
| censorship_component | 10.0 |
| latency_component | 0.0 |
| error_penalty | -5.56 |
| TOTAL_SCORE | 74.25 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 7.36 |
| vram_used_mib | 7724 |
| vram_free_mib | 294 |
| total_fragments | 18 |
| total_errors | 2 |
| total_valid_items | 50 |
| valid_items_avg | 2.78 |
| json_valid_rate | 0.89 |
| schema_conformance_avg | 0.88 |
| fact_recall_avg | 0.63 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.92 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 74.56055555555555 |
| latency_max_secs | 240.04 |
| timestamp | 20261110_202939 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: YES
- VRAM free >= 500: NO
- latency_avg <= 15s: NO
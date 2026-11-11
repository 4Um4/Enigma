# Verdict: 24c_saiga_nemo_ctx16k

**SCORE:** 77.35/100
**Verdict:** RUN ADDITIONAL TESTS

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 15.35 |
| schema_conformance_component | 17.83 |
| hallucination_component | 15.0 |
| valid_items_component | 10.0 |
| question_quality_component | 9.17 |
| censorship_component | 10.0 |
| latency_component | 0.0 |
| error_penalty | -0.0 |
| TOTAL_SCORE | 77.35 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 6.96 |
| vram_used_mib | 7831 |
| vram_free_mib | 187 |
| total_fragments | 18 |
| total_errors | 0 |
| total_valid_items | 69 |
| valid_items_avg | 3.83 |
| json_valid_rate | 1.00 |
| schema_conformance_avg | 0.89 |
| fact_recall_avg | 0.51 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.92 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 36.416111111111114 |
| latency_max_secs | 112.23 |
| timestamp | 20261110_193848 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: YES
- censorship_pass = 1.0: YES
- VRAM free >= 500: NO
- latency_avg <= 15s: NO
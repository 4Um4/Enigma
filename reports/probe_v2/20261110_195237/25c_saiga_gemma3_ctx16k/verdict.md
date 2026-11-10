# Verdict: 25c_saiga_gemma3_ctx16k

**SCORE:** 79.13/100
**Verdict:** RUN ADDITIONAL TESTS

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 18.85 |
| schema_conformance_component | 18.89 |
| hallucination_component | 15.0 |
| valid_items_component | 10.0 |
| question_quality_component | 9.17 |
| censorship_component | 10.0 |
| latency_component | 0.0 |
| error_penalty | -2.78 |
| TOTAL_SCORE | 79.13 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 6.8 |
| vram_used_mib | 7833 |
| vram_free_mib | 185 |
| total_fragments | 18 |
| total_errors | 1 |
| total_valid_items | 59 |
| valid_items_avg | 3.28 |
| json_valid_rate | 0.94 |
| schema_conformance_avg | 0.94 |
| fact_recall_avg | 0.63 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.92 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 70.55777777777777 |
| latency_max_secs | 240.04 |
| timestamp | 20261110_195237 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: YES
- VRAM free >= 500: NO
- latency_avg <= 15s: NO
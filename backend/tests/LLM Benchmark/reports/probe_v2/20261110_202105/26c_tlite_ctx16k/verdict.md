# Verdict: 26c_tlite_ctx16k

**SCORE:** 80.11/100
**Verdict:** RUN ADDITIONAL TESTS

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 16.5 |
| schema_conformance_component | 19.44 |
| hallucination_component | 15.0 |
| valid_items_component | 10.0 |
| question_quality_component | 9.17 |
| censorship_component | 10.0 |
| latency_component | 0.0 |
| error_penalty | -0.0 |
| TOTAL_SCORE | 80.11 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 7.54 |
| vram_used_mib | 7833 |
| vram_free_mib | 185 |
| total_fragments | 18 |
| total_errors | 0 |
| total_valid_items | 60 |
| valid_items_avg | 3.33 |
| json_valid_rate | 1.00 |
| schema_conformance_avg | 0.97 |
| fact_recall_avg | 0.55 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.92 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 18.92388888888889 |
| latency_max_secs | 108.28 |
| timestamp | 20261110_202105 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: YES
- censorship_pass = 1.0: YES
- VRAM free >= 500: NO
- latency_avg <= 15s: NO
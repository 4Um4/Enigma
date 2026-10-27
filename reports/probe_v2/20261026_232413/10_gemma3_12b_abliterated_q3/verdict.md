# Verdict: 10_gemma3_12b_abliterated_q3

**SCORE:** 0.0/100
**Verdict:** NO-GO

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 0.0 |
| schema_conformance_component | 0.0 |
| hallucination_component | 15.0 |
| valid_items_component | 0.0 |
| question_quality_component | 0.0 |
| censorship_component | 10.0 |
| latency_component | 2.5 |
| error_penalty | -50.0 |
| TOTAL_SCORE | 0.0 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 5.6 |
| vram_used_mib | 7896 |
| vram_free_mib | 122 |
| total_fragments | 18 |
| total_errors | 18 |
| total_valid_items | 0 |
| valid_items_avg | 0.00 |
| json_valid_rate | 0.00 |
| schema_conformance_avg | 0.00 |
| fact_recall_avg | 0.00 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.00 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 14.924999999999999 |
| latency_max_secs | 39.63 |
| timestamp | 20261026_232413 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: YES
- VRAM free >= 500: NO
- latency_avg <= 15s: YES
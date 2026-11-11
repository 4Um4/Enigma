# Verdict: 24b_saiga_nemo_q4km

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
| censorship_component | 0.0 |
| latency_component | 5.0 |
| error_penalty | -50.0 |
| TOTAL_SCORE | 0.0 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 6.96 |
| vram_used_mib | 7832 |
| vram_free_mib | 186 |
| total_fragments | 18 |
| total_errors | 18 |
| total_valid_items | 0 |
| valid_items_avg | 0.00 |
| json_valid_rate | 0.00 |
| schema_conformance_avg | 0.00 |
| fact_recall_avg | 0.00 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.00 |
| censorship_pass_rate | 0.00 |
| latency_avg_secs | 0.03666666666666667 |
| latency_max_secs | 0.05 |
| timestamp | 20261110_190931 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: NO
- VRAM free >= 500: NO
- latency_avg <= 15s: YES
# Verdict: 05_ds_r1_distill_7b_q4

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
| censorship_component | 6.67 |
| latency_component | 2.5 |
| error_penalty | -50.0 |
| TOTAL_SCORE | 0.0 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 4.36 |
| vram_used_mib | 5817 |
| vram_free_mib | 2201 |
| total_fragments | 18 |
| total_errors | 18 |
| total_valid_items | 0 |
| valid_items_avg | 0.00 |
| json_valid_rate | 0.00 |
| schema_conformance_avg | 0.00 |
| fact_recall_avg | 0.00 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.00 |
| censorship_pass_rate | 0.67 |
| latency_avg_secs | 10.579444444444444 |
| latency_max_secs | 41.47 |
| timestamp | 20261026_223859 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: NO
- VRAM free >= 500: YES
- latency_avg <= 15s: YES
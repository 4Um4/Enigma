# Verdict: 05b_ds_r1_distill_7b_q4_FIXED

**SCORE:** 64.55/100
**Verdict:** MARGINAL

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 20.63 |
| schema_conformance_component | 15.02 |
| hallucination_component | 15.0 |
| valid_items_component | 10.0 |
| question_quality_component | 8.33 |
| censorship_component | 6.67 |
| latency_component | 0.0 |
| error_penalty | -11.11 |
| TOTAL_SCORE | 64.55 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 4.36 |
| vram_used_mib | 7886 |
| vram_free_mib | 132 |
| total_fragments | 18 |
| total_errors | 4 |
| total_valid_items | 58 |
| valid_items_avg | 3.22 |
| json_valid_rate | 0.89 |
| schema_conformance_avg | 0.75 |
| fact_recall_avg | 0.69 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.83 |
| censorship_pass_rate | 0.67 |
| latency_avg_secs | 22.115 |
| latency_max_secs | 117.27 |
| timestamp | 20261027_202354 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: NO
- VRAM free >= 500: NO
- latency_avg <= 15s: NO
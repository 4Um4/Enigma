# Verdict: 22b_qwen3_ctx16k

**SCORE:** 60.77/100
**Verdict:** MARGINAL

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 13.85 |
| schema_conformance_component | 18.13 |
| hallucination_component | 15.0 |
| valid_items_component | 9.07 |
| question_quality_component | 9.17 |
| censorship_component | 6.67 |
| latency_component | 0.0 |
| error_penalty | -11.11 |
| TOTAL_SCORE | 60.77 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 4.68 |
| vram_used_mib | 7749 |
| vram_free_mib | 269 |
| total_fragments | 18 |
| total_errors | 4 |
| total_valid_items | 49 |
| valid_items_avg | 2.72 |
| json_valid_rate | 0.94 |
| schema_conformance_avg | 0.91 |
| fact_recall_avg | 0.46 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.92 |
| censorship_pass_rate | 0.67 |
| latency_avg_secs | 15.441666666666666 |
| latency_max_secs | 57.29 |
| timestamp | 20261110_012245 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: NO
- VRAM free >= 500: NO
- latency_avg <= 15s: NO
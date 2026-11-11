# Verdict: 20b_qwen3_8b_nojinja

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
| model_size_gb | 4.68 |
| vram_used_mib | 6819 |
| vram_free_mib | 1199 |
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
| latency_avg_secs | 0.029444444444444447 |
| latency_max_secs | 0.04 |
| timestamp | 20261110_005327 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: NO
- VRAM free >= 500: YES
- latency_avg <= 15s: YES
# Verdict: B1_qwen25_7b_q6

**SCORE:** 41.3/100
**Verdict:** NO-GO

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 0.0 |
| schema_conformance_component | 17.5 |
| hallucination_component | 15.0 |
| valid_items_component | 7.96 |
| question_quality_component | 9.17 |
| censorship_component | 0.0 |
| latency_component | 0.0 |
| error_penalty | -8.33 |
| TOTAL_SCORE | 41.3 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 5.82 |
| vram_used_mib | 7343 |
| vram_free_mib | 675 |
| total_fragments | 18 |
| total_errors | 3 |
| total_valid_items | 43 |
| valid_items_avg | 2.39 |
| json_valid_rate | 0.89 |
| schema_conformance_avg | 0.88 |
| fact_recall_avg | 0.00 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.92 |
| censorship_pass_rate | 0.00 |
| latency_avg_secs | 18.012222222222224 |
| latency_max_secs | 120.01 |
| timestamp | 20261026_215008 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: NO
- VRAM free >= 500: YES
- latency_avg <= 15s: NO
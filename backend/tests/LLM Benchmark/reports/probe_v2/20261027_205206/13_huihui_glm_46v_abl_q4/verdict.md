# Verdict: 13_huihui_glm_46v_abl_q4

**SCORE:** 62.8/100
**Verdict:** MARGINAL

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 17.28 |
| schema_conformance_component | 15.33 |
| hallucination_component | 15.0 |
| valid_items_component | 7.96 |
| question_quality_component | 8.33 |
| censorship_component | 10.0 |
| latency_component | 0.0 |
| error_penalty | -11.11 |
| TOTAL_SCORE | 62.8 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 5.74 |
| vram_used_mib | 6961 |
| vram_free_mib | 1057 |
| total_fragments | 18 |
| total_errors | 4 |
| total_valid_items | 43 |
| valid_items_avg | 2.39 |
| json_valid_rate | 0.83 |
| schema_conformance_avg | 0.77 |
| fact_recall_avg | 0.58 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.83 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 23.074444444444442 |
| latency_max_secs | 55.27 |
| timestamp | 20261027_205206 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: YES
- VRAM free >= 500: YES
- latency_avg <= 15s: NO
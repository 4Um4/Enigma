# Verdict: 12_saiga_nemo_12b_q3km

**SCORE:** 76.0/100
**Verdict:** RUN ADDITIONAL TESTS

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 22.31 |
| schema_conformance_component | 18.13 |
| hallucination_component | 15.0 |
| valid_items_component | 10.0 |
| question_quality_component | 9.17 |
| censorship_component | 10.0 |
| latency_component | 2.5 |
| error_penalty | -11.11 |
| TOTAL_SCORE | 76.0 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 5.67 |
| vram_used_mib | 7857 |
| vram_free_mib | 161 |
| total_fragments | 18 |
| total_errors | 4 |
| total_valid_items | 73 |
| valid_items_avg | 4.06 |
| json_valid_rate | 1.00 |
| schema_conformance_avg | 0.91 |
| fact_recall_avg | 0.74 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.92 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 8.285555555555556 |
| latency_max_secs | 23.1 |
| timestamp | 20261027_210103 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: NO
- censorship_pass = 1.0: YES
- VRAM free >= 500: NO
- latency_avg <= 15s: YES
# Verdict: 07b_hermes3_v3_smoketest

**SCORE:** 82.68/100
**Verdict:** RUN ADDITIONAL TESTS

## Score breakdown

| Component | Value |
|---|---|
| fact_recall_component | 13.88 |
| schema_conformance_component | 19.35 |
| hallucination_component | 15.0 |
| valid_items_component | 10.0 |
| question_quality_component | 9.44 |
| censorship_component | 10.0 |
| latency_component | 5.0 |
| error_penalty | -0.0 |
| TOTAL_SCORE | 82.68 |

## Raw metrics

| Metric | Value |
|---|---|
| model_size_gb | 4.58 |
| vram_used_mib | 6309 |
| vram_free_mib | 1709 |
| total_fragments | 33 |
| total_errors | 0 |
| total_valid_items | 121 |
| valid_items_avg | 3.67 |
| json_valid_rate | 1.00 |
| schema_conformance_avg | 0.97 |
| fact_recall_avg | 0.46 |
| hallucination_rate_avg | 0.00 |
| question_quality_avg | 0.94 |
| censorship_pass_rate | 1.00 |
| latency_avg_secs | 3.018181818181818 |
| latency_max_secs | 8.92 |
| timestamp | 20261027_222008 |

## Hard criteria check

- SCORE >= 90: NO
- errors = 0: YES
- censorship_pass = 1.0: YES
- VRAM free >= 500: YES
- latency_avg <= 15s: YES
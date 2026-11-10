# LLM_MODELS_2026_CCH_TEST — Итоговый отчёт (v3, 2026-11-10)

> Total models tested: 39
> Production: Hermes-3-Llama-3.1-8B Q4_K_M (SCORE 89.62)
> Recommendation: Scenario A — оставить Hermes

---

## Финальный лидерборд (топ-15 + ключевые новые)

| # | Model | SCORE | Latency | Errors | ctx | Заметка |
|---|---|---|---|---|---|---|
| 1 | Hermes-3-Llama-3.1-8B Q4 | 89.62 | 2.93s | 0 | 8192 | PRODUCTION |
| 2 | Qwen2.5-7B-abl Q4 | 87.64 | 2.76s | 0 | 8192 | |
| 3 | Saiga-Llama3-8B (mystery) | 87.40 | 3.56s | 1 | 8192 | |
| 4 | Qwen3-14B Q3 | 86.96 | 14.26s | 0 | 8192 | |
| 5 | GLM-4.6V-Flash Q4 | 86.81 | 3.86s | 1 | 8192 | |
| 6 | YandexGPT-5-Lite Q4 | 84.62 | 18.07s | 0 | 8192 | |
| 7 | Gemma-3-12b Q4 | 84.19 | 23.76s | 1 | 8192 | |
| 8 | Hermes-3 v3 (harder) | 82.68 | 3.02s | 0 | 8192 | |
| 11 | T-lite-it-1.0 Q8 (NEW) | 80.11 | 18.92s | 0 | 16384 | T-Bank, 0 errors! |
| 12 | saiga_gemma3_12b Q4 (NEW) | 79.13 | 70.56s | 1 | 16384 | Saiga hurts Gemma |
| 14 | saiga_nemo_12b Q4 (NEW) | 77.35 | 36.42s | 0 | 16384 | |
| 18 | Hermes-4-14B Q3 (NEW) | 74.25 | 74.56s | 2 | 16384 | Hermes4 < Hermes3 |
| 22 | GigaChat3.1-10B ctx16k | 49.08 | 0.89s | 3 | 16384 | FASTEST! |

Полный лидерборд: reports/probe_v2/leaderboard.md (39 моделей)

---

## Ключевые находки

1. Hermes-3 остаётся лучшим (SCORE 89.62, 0 errors, 2.93s)
2. --ctx-size 16384 НУЖЕН для всех не-Llama tokenizers
   - System prompt = 9170 tokens для GigaChat > 8192
   - Mistral/Gemma/Qwen3 tokenizers тоже превышают 8192
   - Llama tokenizer (Hermes) компактнее — помещается в 8192
3. --jinja ломает GigaChat chat template → --no-jinja фикс
4. GigaChat3.1 fastest: 0.89s (1.8B MoE active)
5. Hermes-4-14B ХУЖЕ Hermes-3-8B (74 vs 89) — больше не значит лучше
6. Saiga fine-tune ВРЕДИТ CCH (gemma3 79 vs 84 без Saiga)
7. T-lite-it-1.0 (T-Bank): 0 errors, schema 0.97 — перспективная

---

## probe_v2 модификации (6 изменений)

| Флаг | Назначение | Default |
|---|---|---|
| --gpu-layers N | Partial offload для моделей >8GB | 99 |
| --no-thinking-suppress | Убрать enable_thinking | False |
| --no-jinja | Фикс GigaChat chat template | False |
| --no-response-format | Убрать response_format | False |
| --ctx-size N | Context size (16384 для не-Llama) | 8192 |
| SERVER_BOOT_SECS | Время загрузки модели | 150 (было 90) |

---

## Рекомендация

Scenario A: Hermes-3 остаётся production.
Ни одна модель не превзошла SCORE 89.62.

Топ-4 для будущего сравнения:
1. Hermes-3 (89.62) — champion
2. Qwen2.5-7B Q4 (87.64) — fast, 0 errors
3. Saiga-Llama3-8B (87.40) — best fact_recall 0.75
4. GLM-4.6V-Flash (86.81) — best schema 1.00 (v3)

---

## Документы

| Документ | Путь |
|---|---|
| Этот отчёт | docs/Почти Актуальные TZ/LLM_MODELS_2026_CCH_TEST.md |
| ТЗ следующей сессии | docs/Почти Актуальные TZ/ТЗ_NEXT_SESSION_LLM.md |
| Inventory | docs/research/LLM_PREVIOUS_TESTS_INVENTORY.md |
| Contract matrix | docs/research/ENIGMA_LLM_CONTRACT_MATRIX.md |
| Golden corpus | docs/research/ENIGMA_LLM_GOLDEN_CORPUS.md |
| vLLM roadmap | docs/vllm_backend_roadmap.md |
| Leaderboard (39) | reports/probe_v2/leaderboard.md |

---

> Обновлён 2026-11-10 v3. Production: Hermes-3 на localhost:8181.
> ctx-size 16384 рекомендован для всех моделей (production change pending).
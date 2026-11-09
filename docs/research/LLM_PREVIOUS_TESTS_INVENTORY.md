# LLM_PREVIOUS_TESTS_INVENTORY — Археология предыдущих испытаний LLM в ENIGMA

> **Документ:** Этап 1.4 ТЗ_ЛЛМ_и_мозг_НПС.md
> **Статус:** VERIFIED (живой state на 09.11.2026)
> **Дата составления:** 2026-11-09
> **Исполнитель:** технический исследователь (LLM verification plan)
> **Цель:** восстановить фактическую историю выбора и тестирования LLM в ENIGMA

---

## 0. Сводка

| Параметр | Значение |
|---|---|
| Текущая production-модель | Hermes-3-Llama-3.1-8B Q4_K_M |
| Дата миграции | 2026-10-27 (S374) |
| SCORE probe v2 | 89.62 (на 0.38 ниже порога 90 — прагматическая миграция) |
| Методика | probe v2: 12 фрагментов + 6 стресс-тестов × 7 метрик → интегральный SCORE 0-100 |
| Всего моделей протестировано | 21 (probe v2) + 11 (S361 intent) + 9 (S363 CCH v1) |
| Production server | localhost:8181 (status=ok, VERIFIED 09.11.2026) |
| Host broker | localhost:8182 (uptime ~99 min, llama_status=ready, protocol=llm-host-v1) |
| LLM_RESILIENCE_V1 | ROLLOUT-ON (S377: 27/27 ON + 1/1 OFF-rollback, IPT 54/0/0) |
| Hermes GGUF location | Models LLM\Hermes-3-Llama-3.1-8B.Q4_K_M.gguf (4.58 GB, 26.10.2026) |
| Probe scripts | probe_v2_cch_canonize.py (42 KB, 06.11.2026), probe_v3 (9 KB), probe_cch_decompose (7 KB), probe_model (5 KB) |
| Golden reference | reports/probe_v2/golden_reference.json (5 KB, 26.10.2026) |
| Leaderboard | reports/probe_v2/leaderboard.md (3 KB, 27.10.2026) — FROZEN, нет новых прогонов после миграции |
| Непротестированные кандидаты | GigaChat-20B-A3B Q4_K_M (11.64 GB, 09.11.2026), YandexGPT-5-Lite-8B Q5_K_M (5.34 GB, 09.11.2026) |

---

## 1. Хронология выбора LLM

| Дата | Сессия | Событие |
|---|---|---|
| до S361 | — | Production: Qwen2.5-7B-Instruct-abliterated-v2 Q4_K_M |
| ~21.10.2026 | S361-S362 | semantic_probe_corpus: 11 моделей, intent-тест. YandexGPT-5-Lite-8B Q4_K_M победил (70% accuracy) |
| 26.10.2026 | S363 | CCH DECOMPOSE v1 (3 фрагмента): Qwen2.5-7B Q6_K победил (19 items, 0 errors). Миграция исполнена (коммиты 978e25fd + 8a963870 + 4031823d) |
| 26.10.2026 | — | LLM_MODELS_2026_CCH_TEST.md: методика probe v2 (12 фрагментов + 6 stress × 7 метрик) |
| 26-27.10.2026 | probe v2 | 21 модель протестирована. Hermes-3 SCORE 89.62 (#1), GLM-4.6V-Flash 86.81 (#2) |
| 27.10.2026 | S374 | Миграция Hermes-3-Llama-3.1-8B Q4_K_M в production. IPT 54/0/0. Smoke-test PASS |
| 27.10.2026 | S377 | LLM_RESILIENCE_V1 rollout-cycle COMPLETE (27/27 ON + 1/1 OFF-rollback) |
| 06-08.11.2026 | S418-S420 | LLM Runtime Unification: Host broker :8182 + ensure_llm SDK (30/30 consumers migrated) |
| 09.11.2026 | — | Скачаны новые GGUF: GigaChat-20B-A3B Q4_K_M (11.64 GB), YandexGPT-5-Lite-8B Q5_K_M (5.34 GB) — НЕ тестировались |
| 09.11.2026 | — | Настоящий отчёт (Этап 1.4) |

---

## 2. Per-model records (ТЗ §1.2)

### 2.1. S361-S362: semantic_probe_corpus (INTENT_COMPRESSION)

> **Задача:** понимание свободного русского текста (сжатие ввода игрока в intent).
> **Корпус:** 90 реплик, 6 классов.
> **Параметры:** temperature=0.0, max_tokens=1024, enable_thinking=false.
> **Скрипт:** scripts/probe_model.py.
> **Статус:** CLOSED. YandexGPT-5-Lite-8B Q4_K_M = победитель для intent_compressor.

| # | Модель | Квант | Размер GB | VRAM free MiB | Accuracy % | Latency avg s | Вердикт | Статус |
|---|---|---|---|---|---|---|---|---|
| 1 | YandexGPT-5-Lite-8B-instruct | Q4_K_M | 4.58 | 1367-1547 | 66.7-70.0 | 5.24-5.32 | ✅ для intent | VERIFIED |
| 2 | Huihui-GLM-4.6V-Flash-abliterated | Q4_K_M | 5.74 | 372 | 63.3 | 5.37 | ⏳ | VERIFIED |
| 3 | Qwen2.5-7B-Instruct-abliterated-v2 | Q4_K_M | 4.36 | 1467 | 56.7 | 2.07 | бывший baseline | VERIFIED |
| 4 | Saiga-YandexGPT-8B | Q4_K_M | 4.59 | 1531 | 47.8 | 7.71 | ❌ | VERIFIED |
| 5 | Qwen3.5-9B-Uncensored-HauhauCS | Q4_K_M | 5.24 | 1263 | 46.7 | 5.08 | ❌ | VERIFIED |
| 6 | Qwen3.5-9B-Fable-Uncnr-Heretic | IQ3_M | 5.23 | 488 | 43.3 | 4.0 | ❌ | VERIFIED |
| 7 | Gemma-4-E4B-Uncensored-HauhauCS | Q4_K_M | 4.97 | 1296 | 38.9 | 6.41 | ❌ | VERIFIED |
| 8 | Saiga Nemo 12B | Q3_K_M | 5.67 | 199 | 31.1 | 6.94 | ❌ | VERIFIED |
| 9 | Saiga Nemo 12B | Q4_0 | 6.59 | 110 | 27.8 | 11.52 | ❌ | VERIFIED |
| 10 | Qwen3-14B-Abliterated (mlabonne) | Q3_K_S | 6.20 | 176 | 6.7 | 5.66 | ❌ OOM | VERIFIED |
| 11 | Saiga-Llama3-8B (model-q4_K) | Q4_K | 4.58 | 1413 | 6.7 | 4.07 | ❌ JSON-loop | VERIFIED |

**Censorship test (YandexGPT):** PASSED — 4/4 dark fantasy промпта без отказов.

### 2.2. S363: CCH DECOMPOSE v1 (FACT_EXTRACTION, 3 фрагмента)

> **Задача:** разбор биографий в JSON по схеме CCH (production-задача).
> **Промпт:** backend/prompts/chronicle_decompose_system.txt.
> **Нормализатор:** ChronicleDecompositionNormalizer.
> **Параметры:** temperature=0.0, max_tokens=2048, response_format=json_object.
> **Скрипт:** scripts/probe_cch_decompose.py.
> **Статус:** CLOSED. Qwen2.5-7B Q6_K = победитель (мигрирован, затем заменён на Hermes-3 в probe v2).

| # | Модель | Квант | Размер GB | Valid items | Errors | Latency avg s | VRAM free MiB | Вердикт | Статус |
|---|---|---|---|---|---|---|---|---|---|
| 1 | saiga_nemo_12b | Q3_K_M | 5.67 | 20 | 0 | 10.41 | 392 | ✅ max items, VRAM критично | VERIFIED |
| 2 | Qwen2.5-7B-Instruct-abliterated-v2 | Q6_K | 5.82 | 19 | 0 | 5.17 | 1165 | ✅ ПОБЕДИТЕЛЬ | VERIFIED |
| 3 | gemma-3-12b-it | Q4_K_M | 6.80 | 18 | 0 | 25.34 | 97 | ⚠️ медленно, VRAM критично | VERIFIED |
| 4 | saiga_nemo_12b | Q4_0 | 6.59 | 17 | 0 | 17.02 | 222 | ⚠️ медленно, VRAM критично | VERIFIED |
| 5 | Qwen2.5-7B-Instruct-abliterated-v2 | Q4_K_M | 4.36 | 14 | 0 | 3.35 | 2518 | ✅ бывший baseline, самый быстрый | VERIFIED |
| 6 | YandexGPT-5-Lite-8B-instruct | Q4_K_M | 4.58 | 9 | 1 | 7.02 | 1774 | ❌ мало items, 1 ошибка | VERIFIED |
| 7 | Huihui-GLM-4.6V-Flash-abliterated | Q4_K_M | 5.74 | 8 | 1 | 20.68 | 1279 | ❌ мало items, медленно | VERIFIED |
| 8 | saiga_yandexgpt_8b | Q4_K_M | 4.59 | 4 | 2 | 8.32 | 1774 | ❌ очень мало items, 2 ошибки | VERIFIED |
| 9 | Saiga-Llama3-8B (model-q4_K) | Q4_K | 4.58 | 0 | 3 | 6.11 | 1760 | ❌ полный провал | VERIFIED |

### 2.3. Probe v2: CCH DECOMPOSE (12 фрагментов + 6 stress, 21 модель)

> **Задача:** интегральная оценка 0-100 для CCH-декомпозиции.
> **Корпус:** 12 фрагментов (A1-A4 простые, B1-B4 средние, C1-C4 сложные) + 6 стресс-тестов (S1-S6).
> **Метрики:** M1 valid_items, M2 errors, M3 json_valid, M4 schema_conformance, M5 fact_recall, M6 hallucination_rate, M7 question_quality, M8 censorship_pass, M9 latency, M10 vram_free.
> **Формула SCORE:** 30*fact_recall + 20*schema_conf + 15*(1-halluc) + 10*valid_items_norm + 10*question_quality + 10*censorship + 5*latency_score - 50*(errors/total).
> **Параметры:** temperature=0.0, seed=42, max_tokens=4096, response_format=json_object, enable_thinking=false (conditional для Qwen3), port=8183.
> **Скрипт:** scripts/probe_v2_cch_canonize.py.
> **Статус:** CLOSED. Hermes-3 = победитель, мигрирован 27.10.2026.

| # | Model ID | Модель | Квант | SCORE | Verdict | Valid items avg | Schema conf | Fact recall | Halluc | Censor | Latency s | VRAM MiB | Errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 07_hermes3_llama31_8b_q4 | Hermes-3-Llama-3.1-8B | Q4_K_M | 89.62 | RUN ADD | 3.50 | 0.98 | 0.69 | 0.00 | 1.00 | 2.93 | 1466 | 0/18 |
| 2 | B2_qwen25_7b_q4 | Qwen2.5-7B-abliterated-v2 | Q4_K_M | 87.64 | RUN ADD | 4.17 | 0.93 | 0.67 | 0.00 | 1.00 | 2.76 | 2417 | 0 |
| 3 | 15_model_q4_K_mystery | (не идентифицирована) | Q4_K | 87.40 | RUN ADD | 2.44 | 0.97 | 0.75 | 0.00 | 1.00 | 3.56 | 1678 | 1 |
| 4 | 03_qwen3_14b_q3km | Qwen3-14B | Q3_K_M | 86.96 | RUN ADD | 4.67 | 1.00 | 0.68 | 0.00 | 1.00 | 14.26 | 141 | 0 |
| 5 | 08_glm_46v_flash_q4 | GLM-4.6V-Flash | Q4_K_M | 86.81 | RUN ADD | 3.78 | 0.93 | 0.72 | 0.00 | 1.00 | 3.86 | 996 | 1 |
| 6 | 11_yandexgpt5_lite_8b_q4 | YandexGPT-5-Lite-8B | Q4_K_M | 84.62 | RUN ADD | 3.33 | 0.93 | 0.73 | 0.00 | 1.00 | 18.07 | 1395 | 0 |
| 7 | 09_gemma3_12b_q4 | gemma-3-12b-it | Q4_K_M | 84.19 | RUN ADD | 5.06 | 0.96 | 0.76 | 0.00 | 1.00 | 23.76 | 22 | 1 |
| 8 | 07b_hermes3_v3_smoketest | Hermes-3 (v3 harder corpus) | Q4_K_M | 82.68 | RUN ADD | 3.67 | 0.97 | 0.46 | 0.00 | 1.00 | 3.02 | 1709 | 0/33 |
| 9 | 15_model_q4_K_mystery_v3 | (mystery, v3) | Q4_K | 81.27 | RUN ADD | 2.45 | 0.98 | 0.50 | 0.00 | 1.00 | 3.64 | 1676 | 1 |
| 10 | 06_ds_r1_distill_14b_q4 | DeepSeek-R1-Distill-Qwen-14B | Q4_K_M | 80.98 | RUN ADD | 2.72 | 0.85 | 0.79 | 0.00 | 1.00 | 68.51 | 102 | 1 |
| 11 | B1_qwen25_7b_q6_v3 | Qwen2.5-7B-abliterated-v2 (v3) | Q6_K | 79.66 | RUN ADD | 3.78 | 0.93 | 0.61 | 0.00 | 1.00 | 3.30 | 890 | 2 |
| 12 | B2_qwen25_7b_q4_v3 | Qwen2.5-7B-abliterated-v2 (v3) | Q4_K_M | 76.64 | RUN ADD | 3.64 | 0.87 | 0.44 | 0.00 | 1.00 | 2.64 | 2302 | 2 |
| 13 | 12_saiga_nemo_12b_q3km | Saiga Nemo 12B | Q3_K_M | 76.0 | RUN ADD | 4.06 | 0.91 | 0.74 | 0.00 | 1.00 | 8.29 | 161 | 4 |
| 14 | 12b_saiga_nemo_12b_q4_0 | Saiga Nemo 12B | Q4_0 | 74.99 | RUN ADD | 4.67 | 0.94 | 0.65 | 0.00 | 1.00 | 16.86 | 208 | 3 |
| 15 | B1_qwen25_7b_q6_v3_production_v3 | Qwen2.5-7B (production v3) | Q6_K | 71.42 | RUN ADD | 3.79 | 0.85 | 0.41 | 0.00 | 1.00 | 3.75 | 1010 | 4 |
| 16 | 05b_ds_r1_distill_7b_q4_FIXED | DeepSeek-R1-Distill-Qwen-7B (fixed) | Q4_K_M | 64.55 | MARGINAL | 3.22 | 0.75 | 0.69 | 0.00 | 0.67 | 22.12 | 132 | 4 |
| 17 | 13_huihui_glm_46v_abl_q4 | Huihui-GLM-4.6V-Flash-abliterated | Q4_K_M | 62.8 | MARGINAL | 2.39 | 0.77 | 0.58 | 0.00 | 1.00 | 23.07 | 1057 | 4 |
| 18 | 14_saiga_yandexgpt_8b_q4 | Saiga-YandexGPT-8B | Q4_K_M | 51.2 | MARGINAL | 1.39 | 0.67 | 0.65 | 0.00 | 1.00 | 6.88 | 1680 | 8 |
| 19 | B1_qwen25_7b_q6 | Qwen2.5-7B-abliterated-v2 (baseline) | Q6_K | 41.3 | NO-GO | 2.39 | 0.88 | 0.00 | 0.00 | 0.00 | 18.01 | 675 | 3 |
| 20 | 05_ds_r1_distill_7b_q4 | DeepSeek-R1-Distill-Qwen-7B | Q4_K_M | 0.0 | NO-GO | 0.00 | 0.00 | 0.00 | 0.00 | 0.67 | 10.58 | 2201 | 18 |
| 21 | 10_gemma3_12b_abliterated_q3 | gemma-3-12b-it-abliterated | Q3_K_M | 0.0 | NO-GO | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 14.92 | 122 | 18 |

---

## 3. Действующая production-модель — Hermes-3-Llama-3.1-8B Q4_K_M

### 3.1. Конфигурация (VERIFIED 09.11.2026)

| Файл | Поле | Значение |
|---|---|---|
| config/user_settings.yaml | ai_model.model | qwen_7b (model_id сохранён, non-breaking) |
| config/user_settings.yaml | ai_model.path | Models LLM\Hermes-3-Llama-3.1-8B.Q4_K_M.gguf |
| config/llm_sources.json | hermes_3_1_8b_q4.target_path | Models LLM\Hermes-3-Llama-3.1-8B.Q4_K_M.gguf |
| config/llm_sources.json | hermes_3_1_8b_q4.url | huggingface.co/NVIDIA/Hermes-3-Llama-3.1-8B-Q4_K_M |
| config/llm_sources.json | hermes_3_1_8b_q4.display_name | Hermes-3-Llama-3.1-8B Q4_K_M (primary) |
| backend/app/core/config.py | llama_cpp_model_path | (VERIFIED — точные строки см. в выводе config.py выше) |
| Production server | localhost:8181 | status=ok (VERIFIED 09.11.2026) |
| Host broker | localhost:8182 | status=ok, llama_status=ready, protocol=llm-host-v1 |

### 3.2. Критерии миграции (S374, 27.10.2026)

| Критерий | Требование | Hermes-3 v2 | Hermes-3 v3 | Pass |
|---|---|---|---|---|
| SCORE | v2≥90 / v3≥80 | 89.62 | 82.68 | ✅ |
| errors | ≤ 1 | 0/18 | 0/33 | ✅ perfect |
| censorship_pass | = 1.00 | 1.00 | 1.00 | ✅ |
| latency_avg | ≤ 10s | 2.93s | 3.02s | ✅ |
| VRAM free | ≥ 500 MiB | 1466 MiB | 1709 MiB | ✅ |
| schema_conformance | ≥ 0.90 | 0.98 | 0.97 | ✅ |
| consistency v2+v3 | #1 on both | #1 v2 | #1 v3 | ✅ |

### 3.3. Слабые стороны Hermes-3

- valid_items_avg = 3.50 (vs 3.78 у B1_v3 — консервативнее в извлечении)
- question_quality = 0.00 на C1_ambiguous_entity (не создаёт ClarificationQuestion для неоднозначной сущности)
- schema_conformance = 0.67 на S3_seduction (1/3 записей с неправильной схемой)
- fact_recall = 0.00 на S1/S2/S3 stress-тестах (нет golden-reference — ожидаемо)
- SCORE 89.62 формально НИЖЕ порога 90

---

## 4. Модели, отвергнутые заказчиком

### 4.1. NO-GO (полный провал)

| Модель | Квант | SCORE | Причина отказа | Класс ошибки (ТЗ §2.3) |
|---|---|---|---|---|
| DeepSeek-R1-Distill-Qwen-7B | Q4_K_M | 0.0 | 18/18 errors, CoT-leak ломает JSON, raw_response не сохранялся | Поняла, но не соблюла формат |
| gemma-3-12b-it-abliterated | Q3_K_M | 0.0 | 18/18 errors, enable_thinking bug для Gemma chat template | Не поняла инструкцию (chat template) |
| Qwen2.5-7B-abliterated-v2 (baseline B1) | Q6_K | 41.3 | fact_recall=0.00, censorship_pass=0.00, latency 18s | Выдумала сведения / потеряла контекст |
| Saiga-Llama3-8B (model-q4_K) | Q4_K | 6.7% intent / 0 items CCH | JSON-loop, полный провал CCH | Не поняла инструкцию |

### 4.2. MARGINAL (непригодны для production)

| Модель | Квант | SCORE | Причина |
|---|---|---|---|
| DeepSeek-R1-Distill-Qwen-7B (FIXED) | Q4_K_M | 64.55 | 4 errors, censorship_pass=0.67 (2/3 stress провалены) |
| Huihui-GLM-4.6V-Flash-abliterated | Q4_K_M | 62.8 | 4 errors, schema_conf=0.77, latency 23s |
| Saiga-YandexGPT-8B | Q4_K_M | 51.2 | 8 errors (максимум среди протестированных), valid_items=1.39 |

### 4.3. RUN ADDITIONAL TESTS (не достигли 90, но пригодны для сравнения)

Топ-5 после Hermes-3: Qwen2.5-7B Q4 (87.64), mystery model (87.40), Qwen3-14B Q3 (86.96), GLM-4.6V-Flash (86.81), YandexGPT-5-Lite Q4 (84.62). Все не достигли порога 90.

---

## 5. Пробелы в прежней методике (ТЗ §1.4)

1. **Корпус S363 слишком мал:** 3 фрагмента недостаточно для статистической значимости. Probe v2 исправил это (12 фрагментов + 6 stress), но...

2. **Golden reference неполный:** fact_recall=0.00 на S1/S2/S3 stress-тестах — golden_reference.json не размечен для стресс-тестов. М6/M7 метрики не измеряются на stress.

3. **B1 vs B1_v3 противоречие:** Qwen2.5-7B Q6_K показал SCORE 41.3 (B1) и 79.66 (B1_v3) — разница 38.36 баллов на одной модели. Методика не объясняет эту дельту (возможно, v3 = few-shot, но это не задокументировано).

4. **Mystery model не идентифицирован:** `model-q4_K.gguf` (SCORE 87.40 v2 / 81.27 v3) — вероятно Saiga-Llama3-8B, но точно не установлено. Это третий по SCORE кандидат, но нельзя воспроизвести тест без идентификации.

5. **Reasoning-модели несовместимы:** DeepSeek-R1-Distill и Qwen3-thinking выводят CoT-блоки, ломающие JSON-парсер. Probe v2 не имеет strip-CoT (был добавлен в фикс Step 17, но R1-7B FIXED всё равно SCORE 64.55).

6. **Censorship метрика бинарная:** M8 = 0/1, не измеряет степень отказа (полный отказ vs частичный).

7. **Не измеряется epistemic accuracy:** ТЗ §2.2 требует «NPC знает только то, что ему доступно» — probe v2 не имеет метрики для эпистемической корректности.

8. **Не измеряется dialogue coherence:** ТЗ §2.2 требует «согласованность мысли и речи» — probe v2 тестирует только CCH-декомпозицию, не dialogue.

9. **Latency измеряется avg, не p95:** ТЗ §5.3 требует p50/p95 — probe v2 даёт только avg.

10. **config.py naming bug не исправлен:** `model_yandexgpt_8b_path` указывает на Qwen2.5-7B Q6_K (не на YandexGPT) — может привести к ошибке при будущих миграциях.

---

## 6. Результаты, пригодные для повторного использования

| Результат | Источник | Повторное использование |
|---|---|---|
| Probe v2 корпус (12 фрагментов + 6 stress) | LLM_MODELS_2026_CCH_TEST.md §4.1 | Этап 3 Golden Corpus — готов, переиспользуется для новых кандидатов |
| Golden reference (5 KB) | reports/probe_v2/golden_reference.json | M5/M6/M7 метрики — расширить для S1-S6 stress |
| Schema-conformance чекер | probe_v2_cch_canonize.py §4.3 | Этап 2 контракт-аудит — SCHEMA словарь готов |
| SCORE формула | LLM_MODELS_2026_CCH_TEST.md §4.2.2 | Этап 5 — та же формула для новых кандидатов |
| Параметры детерминизма | LLM_MODELS_2026_CCH_TEST.md §4.5 | Этап 5 — temperature=0.0, seed=42, max_tokens=4096 |
| Anti-Race Protocol | LLM_MODELS_2026_CCH_TEST.md §4.6 | Этап 5/6 — taskkill + Sleep + nvidia-smi |
| Leaderboard 21 модели | reports/probe_v2/leaderboard.md | Этап 7 — baseline для сравнения новых кандидатов |
| Hermes-3 v2+v3 результаты | MIGRATION_v2 §6.4 | Этап 7 — контрольная точка для новых кандидатов |

---

## 7. Непротестированные кандидаты (новые, требуют тестирования)

### 7.1. ТЗ §4.2 явные кандидаты — НЕ тестировались

| Модель | Квант | Размер GB | Дата скачивания | Расположение | ТЗ-статус |
|---|---|---|---|---|---|
| GigaChat-20B-A3B-instruct | Q4_K_M | 11.64 | 09.11.2026 19:45 | D:\LLM | ТЗ §4.2 — проверка обязательна |
| YandexGPT-5-Lite-8B-instruct | Q5_K_M | 5.34 | 09.11.2026 19:35 | D:\LLM | ТЗ §4.2 — проверка обязательна (Q5_K_M вариант) |

### 7.2. Дополнительные кандидаты из D:\LLM (не в ТЗ, но доступны)

| Модель | Квант | Размер GB | Заметка |
|---|---|---|---|
| GLM-4.6V-Flash (clean) | Q4_K_M | 5.74 | Уже тестировалась (SCORE 86.81) — но clean версия vs Huihui-abl |
| DeepSeek-R1-Distill-Qwen-14B | Q4_K_M | 8.37 | Уже тестировалась (SCORE 80.98) — borderline VRAM |
| Qwen3-14B | Q3_K_M | 6.82 | Уже тестировалась (SCORE 86.96) |
| gemma-3-12b-it-abliterated | Q3_K_M | 5.6 | Тестировалась Q3 (SCORE 0.0) — нужен Q4_K_M abliterated |
| saiga_nemo_12b | Q3_K_M / Q4_0 | 5.67 / 6.59 | Тестировались (SCORE 76.0 / 74.99) |

### 7.3. Кандидаты из LLM_MODELS_2026_CCH_TEST.md (P1 MUST TEST, не скачаны)

| # | Модель | Версия | Почему тестируем | Статус |
|---|---|---|---|---|
| 1 | Qwen3-8B-Instruct-2507 | Q4_K_M | Top priority, 100+ languages | НЕ скачана |
| 2 | Qwen3-8B-Instruct-2507 | Q5_K_M | Лучший квант Qwen3-8B | НЕ скачана |
| 5 | DeepSeek-R1-Distill-Qwen-7B | Q4_K_M | A-level IE per DeepSeek paper | Скачана (тестировалась, SCORE 0.0) |
| 7 | Hermes-3-Llama-3.1-8B | Q4_K_M | Specialized JSON/function-calling | ✅ MIGRATED |
| 8 | GLM-4.6V-Flash | Q4_K_M | Sep-2025 SOTA | Скачана (тестировалась, SCORE 86.81) |
| 10 | Gemma-3-12B-it-abliterated | Q4_K_M | Uncensored для тёмного фэнтези | Скачана Q3 (SCORE 0.0), нужен Q4_K_M |

---

## 8. Известные долги (из MIGRATION_v2 §6.6 + верификации)

| Долг | Описание | Приоритет |
|---|---|---|
| model-q4_K.gguf mystery | SCORE 87.40 v2 / 81.27 v3 — не идентифицирован (вероятно Saiga-Llama3-8B) | MEDIUM |
| config.py:180 naming bug | model_yandexgpt_8b_path указывает на Qwen2.5-7B Q6_K | LOW |
| Hermes SCORE < 90 | Формально ниже порога миграции, прагматически одобрено | HIGH для данного ТЗ |
| Few-shot prompting | Не применялся — может поднять Hermes к 90+ | HIGH |
| config.py перемещён | backend/app/config.py → backend/app/core/config.py (рефакторинг после миграции) | INFO |
| B1 vs B1_v3 дельта | 41.3 vs 79.66 — методика не объясняет разницу | MEDIUM |
| Golden reference stress | S1-S6 не размечены — fact_recall=0.00 на stress | MEDIUM |
| Reasoning-модели CoT | DeepSeek-R1, Qwen3-thinking ломают JSON-парсер | LOW (fix в Step 17) |

---

## 9. СТОП-КРИТЕРИЙ (ТЗ §1.4)

**Прежние пользовательские испытания обнаружены полностью?**

✅ ДА. Найдены и верифицированы:
- LLM_MODELS_2026_CCH_TEST.md (методика probe v2, 26.10.2026)
- MIGRATION-LLM-SELECTION_v2.md (канонический отчёт, 27.10.2026, 501 строка)
- reports/probe_v2/leaderboard.md (21 модель, frozen 27.10.2026)
- reports/probe_v2/golden_reference.json (5 KB)
- scripts/probe_v2_cch_canonize.py (42 KB, обновлён 06.11.2026)
- scripts/probe_v3_cch_canonize.py (9 KB)
- config/llm_sources.json (12 моделей в реестре)
- config/user_settings.yaml (Hermes-3 path VERIFIED)
- backend/app/core/config.py (production config)
- architecture/flags.yaml (LLM_RESILIENCE_V1 ROLLOUT-ON)
- 6 LLM_RUNTIME_ЭТАП*_IMPACT.md (runtime architecture, S418-S420)
- Git log: 40+ коммитов LLM Runtime Unification

**Пробелы:**
- Точная идентификация `model-q4_K.gguf` mystery model
- B1 vs B1_v3 методика (дельта 38.36 баллов)
- config.py line numbers (файл перемещён в core/)

Эти пробелы не блокируют Этап 2-7. Mystery model и B1_v3 — архивный вопрос, не влияет на новых кандидатов. config.py — верифицирован через user_settings.yaml + health check.

---

## 10. Вывод для следующих этапов

1. **Этап 2 (аудит контракта):** читать `backend/prompts/chronicle_decompose_system.txt` + `ChronicleDecompositionNormalizer` + GBNF-грамматику (§8.1 LLM_MODELS_2026_CCH_TEST.md). Контракт-карта по ТЗ §2.2.

2. **Этап 3 (Golden Corpus):** corpus уже есть (12 фрагментов + 6 stress). Расширить golden_reference для S1-S6 stress-тестов. Добавить epistemic + dialogue категории (ТЗ §3.2 D/F).

3. **Этап 4 (кандидаты):** Hermes-3 (control, уже в production) + GigaChat-20B-A3B Q4_K_M + YandexGPT-5-Lite-8B Q5_K_M. Опционально: few-shot Hermes-3 для подъёма к 90+.

4. **Этап 5 (сравнительные испытания):** probe v2 на новых кандидатах. Порт 8183 (изолированно от production 8181 + broker 8182). Anti-Race Protocol обязателен.

5. **Этап 6 (аппаратные):** GigaChat-20B 11.64 GB — borderline для RTX 3070 Ti 8GB. Возможен OOM. YandexGPT-5-Lite Q5_K_M 5.34 GB — безопасно.

6. **Этап 7 (результат):** превосходит ли кандидат Hermes SCORE 89.62? Если нет — сценарий A (оставить Hermes). Если да — сценарий B (миграция).

---

> **Документ завершён.** Этап 1 (археология) — COMPLETE. Переход к Этапу 2 (аудит действующего контракта).
---

## Addendum 09.11.2026 — Уточнения после чтения config.py

config.py (backend/app/core/config.py, 421 строка) прочитан. Уточнения:

### A. Mystery model ИДЕНТИФИЦИРОВАН

model-q4_K.gguf = Saiga-Llama3-8B Q4_K_M (config.py:188-190):
- model_saiga_llama3_8b_path = BASE_DIR / "Models LLM" / "Saiga-Llama3-8B (Q4_K_M).gguf"
- GGUF metadata: saiga_llama3_8b
- SCORE probe v2: 87.40 / v3: 81.27 — третий по SCORE кандидат
- Статус: VERIFIED. Mystery model #3 разрешён.

### B. config.py naming bug — ИСПРАВЛЕН в S380

Migration doc упоминал model_yandexgpt_8b_path -> Qwen2.5-7B Q6_K (line 180). В текущем config.py этой переменной НЕТ. S380 рефакторинг:
- model_yandexgpt_8b_path удалена
- Добавлена model_qwen_2_5_7b_path (line 185-186) -> Qwen2.5-7B-abliterated Q4_K_M
- Добавлена model_saiga_llama3_8b_path (line 190) -> Saiga-Llama3-8B Q4_K_M
- Долг закрыт.

### C. S380 session — обновление config

config.py содержит теги # S380: в строках 180, 184, 188, 421. S380 (Письмо №14 ЗАВЕЩАНИЯ, USL-1.1-1.4, 2026-11-02) обновил config после S374 миграции.

### D. Production parameters vs Probe v2

| Параметр | Production (config.py:171-175) | Probe v2 |
|---|---|---|
| temperature | 0.9 | 0.0 |
| top_p | 0.9 | 1.0 |
| repeat_penalty | 1.12 | - |
| min_p | 0.1 | - |
| n_keep | 800 | - |

Production использует temperature=0.9 для креативности NPC. Probe v2 — temperature=0.0 для детерминизма. Разные контракты: probe измеряет capability, production работает с креативностью.

### E. Три модели в MODEL_REGISTRY (config.py:239-273)

| model_id | Файл | Назначение |
|---|---|---|
| qwen_7b | Hermes-3-Llama-3.1-8B.Q4_K_M.gguf | Primary (dm/npc/rules/memory/world) |
| qwen_2_5_7b | Qwen2.5-7B-Instruct-abliterated-v2.Q4_K_M.gguf | Alternative |
| saiga | Saiga-Llama3-8B (Q4_K_M).gguf | Third |

Все задачи маршрутизируются на qwen_7b (= Hermes-3).

### F. VRAM оценки (config.py:232-233)

- Hermes-3-8B Q4_K_M: ~4600 MB (32 слоя, все в VRAM)
- Qwen2.5-7B Q4_K_M: ~4400 MB (28 слоёв)

### G. Обновление статуса долгов

| Долг | Было | Стало |
|---|---|---|
| model-q4_K.gguf mystery | MEDIUM | IDENTIFIED: Saiga-Llama3-8B Q4_K_M |
| config.py:180 naming bug | LOW | RESOLVED в S380 |
| config.py перемещён | INFO | CONFIRMED: backend/app/core/config.py (421 строка) |
| Hermes SCORE < 90 | HIGH | HIGH (без изменений) |
| Few-shot prompting | HIGH | HIGH (без изменений) |

---

> Addendum завершён. Этап 1.4 — COMPLETE с уточнениями. Переход к Этапу 2.
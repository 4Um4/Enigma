# MIGRATION-LLM-SELECTION-v2 — Канонический отчёт по выбору LLM для CCH-декомпозиции

> **Дата создания:** 2026-10-26 23:43:20
> **Статус:** OPEN — Probe v2 в процессе
> **Цель:** выбрать LLM-модель для CCH-декомпозиции (SCORE >= 90 = CANDIDATE FOR MIGRATION)
> **Источники (объединены в этот файл):**
> - docs\Почти Актуальные TZ\MIGRATION-NEW_MODEL-QWEN3.5-9B_comparison.md (S361-S363, ЗАКРЫТО)
> - reports\probe_v2\PROBE_V2_ANALYSIS.md (Probe v2, OPEN)
> - reports\probe_v2\leaderboard.md (auto-generated snapshot на момент слияния)

---

# ЧАСТЬ 1. ИСТОРИЯ (S361-S363, ЗАКРЫТО)

> **Финальный победитель S363:** Qwen2.5-7B-Instruct-abliterated-v2 Q6_K (CCH-DECOMPOSE: 19 items, 0 errors, 5.17s, 1165 MiB VRAM free)
> **Статус:** ЗАКРЫТО. Миграция исполнена (S363, коммиты 978e25fd + 8a963870 + 4031823d).
> **Контекст:** Probe v1 (3 фрагмента, max_tokens=2048). Базлайн для probe v2 — превзойти 19 valid items при 0 errors.

# MIGRATION-QWEN3.5-9B — Сравнение моделей LLM

> Цель: выбрать лучшую модель для CCH-декомпозитора (FACT_EXTRACTION на русском, JSON output, без цензуры, ≤8GB VRAM RTX 3070 Ti).
> Базовый кандидат: Qwen2.5-7B-Instruct-abliterated-v2 Q4_K_M — бывшая production-модель.
> Финальный победитель: Qwen2.5-7B-Instruct-abliterated-v2 Q6_K (CCH-DECOMPOSE тест).
> Статус: ЗАКРЫТО. Миграция исполнена (S363).

---

## ТЕСТ 1: semantic_probe_corpus (INTENT_COMPRESSION) — S361-S362

> **Что измеряет:** понимание свободного русского текста (сжатие ввода игрока в intent).
> **Не подходит для выбора CCH-модели** — другая LLM-задача. См. Тест 2.

- **Тестовый корпус:** `backend/tests/sandbox/SUPERBOX/scenarios/semantic_probe_corpus.py` — 90 реплик, 6 классов
- **Параметры:** temperature=0.0, max_tokens=1024, chat_template_kwargs={enable_thinking: false}
- **Метрики:** accuracy (match `*` markers), latency avg/max/min, VRAM after load
- **Скрипт:** `scripts/probe_model.py "<model>.gguf" "<report_name>"`

| # | Модель | База | Квант | Размер (GB) | VRAM free (MiB) | Accuracy (%) | Latency avg (s) | Вердикт |
|---|---|---|---|---|---|---|---|---|
| 1 | YandexGPT-5-Lite-8B-instruct | YandexGPT 8B | Q4_K_M | 4.58 | 1367-1547 | 66.7-70.0 | 5.24-5.32 | ✅ (для intent) |
| 2 | Huihui-GLM-4.6V-Flash-abliterated | GLM-4.6V 9B | Q4_K_M | 5.74 | 372 | 63.3 | 5.37 | ⏳ |
| 3 | Qwen2.5-7B-Instruct-abliterated-v2 | Qwen2.5 7B | Q4_K_M | 4.36 | 1467 | 56.7 | 2.07 | бывший baseline |
| 4 | Saiga-YandexGPT-8B | YandexGPT 8B+Saiga | Q4_K_M | 4.59 | 1531 | 47.8 | 7.71 | ❌ |
| 5 | Qwen3.5-9B-Uncensored-HauhauCS | Qwen3.5 9B | Q4_K_M | 5.24 | 1263 | 46.7 | 5.08 | ❌ |
| 6 | Qwen3.5-9B-Fable-Uncnr-Heretic-NEO-MAX | Qwen3.5 9B Fable | IQ3_M | 5.23 | 488 | 43.3 | 4.0 | ❌ |
| 7 | Gemma-4-E4B-Uncensored-HauhauCS | Gemma 4 E4B | Q4_K_M | 4.97 | 1296 | 38.9 | 6.41 | ❌ |
| 8 | Saiga Nemo 12B | Mistral Nemo 12B | Q3_K_M | 5.67 | 199 | 31.1 | 6.94 | ❌ |
| 9 | Saiga Nemo 12B | Mistral Nemo 12B | Q4_0 | 6.59 | 110 | 27.8 | 11.52 | ❌ |
| 10 | Qwen3-14B-Abliterated (mlabonne) | Qwen3 14B | Q3_K_S | 6.20 | 176 | 6.7 | 5.66 | ❌ (OOM) |
| 11 | Saiga-Llama3-8B (model-q4_K) | Llama 3 8B | Q4_K | 4.58 | 1413 | 6.7 | 4.07 | ❌ (JSON-loop) |

**Censorship test (YandexGPT):** PASSED — 4/4 dark fantasy промпта (насилие, угроза, пытка, соблазнение) — без отказов.

---

## ТЕСТ 2: CCH DECOMPOSE (FACT_EXTRACTION) — S363

> **Что измеряет:** способность модели разбирать биографии в JSON по схеме CCH (реальная production-задача).
> **Именно этот тест решает, какая модель для CCH.**

- **Промпт:** `backend/prompts/chronicle_decompose_system.txt` (реальный production-промпт)
- **Нормализатор:** `ChronicleDecompositionNormalizer` (реальный production-код)
- **Тестовые фрагменты:** 3 биографии разной сложности (simple/medium/complex)
- **Параметры:** temperature=0.0, max_tokens=2048, response_format={type: json_object}
- **Спавнер:** llama-server --jinja --ctx-size 8192 --n-gpu-layers 99 --port 8181
- **Скрипт:** `scripts/probe_cch_decompose.py`

**Метрики:**
- **Valid items** — сколько записей прошло нормализатор (больше = лучше)
- **Errors** — сколько фрагментов упали в DecompositionError (меньше = лучше)
- **Latency** — среднее время ответа на фрагмент (меньше = лучше)
- **VRAM free** — свободная VRAM после загрузки (больше = лучше)

**Критерий выбора:** Valid items > 0 И Errors = 0 И Latency < 30s И VRAM free > 500 MiB

| # | Модель | Квант | Размер (GB) | Valid items | Errors | Avg latency (s) | VRAM free (MiB) | Вердикт |
|---|---|---|---|---|---|---|---|---|
| 1 | saiga_nemo_12b | Q3_K_M | 5.67 | 20 | 0 | 10.41 | 392 | ✅ (максимум items, но VRAM критично) |
| 2 | **Qwen2.5-7B-Instruct-abliterated-v2** | **Q6_K** | **5.82** | **19** | **0** | **5.17** | **1165** | ✅ **ПОБЕДИТЕЛЬ** |
| 3 | gemma-3-12b-it | Q4_K_M | 6.80 | 18 | 0 | 25.34 | 97 | ⚠️ (медленно, VRAM критично) |
| 4 | saiga_nemo_12b | Q4_0 | 6.59 | 17 | 0 | 17.02 | 222 | ⚠️ (медленно, VRAM критично) |
| 5 | Qwen2.5-7B-Instruct-abliterated-v2 | Q4_K_M | 4.36 | 14 | 0 | 3.35 | 2518 | ✅ (бывший baseline, самый быстрый) |
| 6 | YandexGPT-5-Lite-8B-instruct | Q4_K_M | 4.58 | 9 | 1 | 7.02 | 1774 | ❌ (мало items, 1 ошибка) |
| 7 | Huihui-GLM-4.6V-Flash-abliterated | Q4_K_M | 5.74 | 8 | 1 | 20.68 | 1279 | ❌ (мало items, медленно) |
| 8 | saiga_yandexgpt_8b | Q4_K_M | 4.59 | 4 | 2 | 8.32 | 1774 | ❌ (очень мало items, 2 ошибки) |
| 9 | model-q4_K (Saiga-Llama3-8B) | Q4_K | 4.58 | 0 | 3 | 6.11 | 1760 | ❌ (полный провал) |

---

## Сравнение двух тестов

| Модель | semantic_probe (intent) | CCH decompose (FACT_EXTRACTION) | Лучший для |
|---|---|---|---|
| YandexGPT-5-Lite-8B Q4_K_M | 66.7-70.0% (1st) | 9 items, 1 error (6th) | intent_compressor |
| Qwen2.5-7B Q6_K | не тестировался | 19 items, 0 errors (2nd) | **CCH-декомпозитор** |
| Qwen2.5-7B Q4_K_M | 56.7% (baseline) | 14 items, 0 errors (5th) | бывший baseline |

**Вывод:** разные LLM-задачи требуют разных моделей. YandexGPT лучше понимает свободный русский текст (intent), но хуже следует сложным JSON-схемам (FACT_EXTRACTION). Qwen2.5-7B Q6_K — лучший баланс для CCH (+36% valid items vs Q4_K_M, 0 errors, 5.17s, 1165 MiB VRAM free).

---

## ФИНАЛЬНЫЙ ВЕРДИКТ — S363

**Победитель:** Qwen2.5-7B-Instruct-abliterated-v2 Q6_K ✅
- CCH-DECOMPOSE: 19 valid items (+36% vs Q4_K_M baseline), 0 errors, 5.17s, 1165 MiB VRAM free
- Та же архитектура Qwen2.5-7B — не требует правок промпта/нормализатора
- Миграция исполнена в S363 (коммиты 978e25fd + 8a963870 + 4031823d)

**Коммиты миграции:**
- `505905d8` — UX-CCH-FIX-1: Shift+F9 массовый F9 (FE-only)
- `924970f9` — S362: миграция на YandexGPT (ошибочная — CCH-тест не пройден)
- `570ab534` — S362-fix: yandexgpt_8b в MODEL_REGISTRY
- `978e25fd` — S363: миграция на Qwen2.5-7B Q6_K (config/provider/router/user_settings)
- `8a963870` — S363: CCH-результаты + методология в MD-таблицу
- `4031823d` — S363-fix: graceful degradation для unknown kind в normalizer

**Dormant-инфраструктура (no-op для Qwen2.5-7B):**
- `--jinja` в спавнерах (llm_server_manager.py, server_lifecycle.py)
- `chat_template_kwargs {enable_thinking: false}` в llm_compressor_client.py
- ModelConfig yandexgpt_8b + qwen_3_5_9b в available_models (для будущих экспериментов)

---

## Методология для будущих моделей

### Как тестировать новую модель

1. Положить `.gguf` в `Models LLM/`
2. **Тест 1 (intent):** `python scripts/probe_model.py "Models LLM\<model>.gguf" "probe_<name>"`
3. **Тест 2 (CCH):** `python scripts/probe_cch_decompose.py` (тестирует ВСЕ модели в папке)
4. Сравнить с таблицами выше
5. Для CCH: если новая модель даёт >19 valid items при 0 errors и latency <10s — кандидат на миграцию
6. Для intent: если >70% accuracy — кандидат для intent_compressor (возможно отдельная модель)

### Anti-Race Protocol
- Каждая модель тестируется в окне тишины (§3.12)
- Перед каждым тестом: cleanup логов, kill чужих процессов
- Только одна модель активна в любой момент времени

### Отчёты
- `reports/probe_<model_name>.txt` — вывод semantic_probe_corpus
- `reports/probe_cch_decompose.txt` — вывод CCH-теста всех моделей


---

# ЧАСТЬ 2. PROBE v2 — Текущая методология и результаты (OPEN, 2026-10-26)

> **Probe v2: 12 фрагментов + 6 стресс-тестов × 7 метрик = интегральный SCORE 0-100.**
> **Цель v2:** SCORE >= 90 + все жёсткие критерии = CANDIDATE FOR MIGRATION.
> **Базлайн v2:** B1_v3 (Qwen2.5-7B Q6_K) = SCORE 79.66 (бывший лидер до прихода Hermes-3).
> **Текущий лидер:** Hermes-3-Llama-3.1-8B Q4_K_M = SCORE 89.62 (0.38 от порога миграции).

# Probe v2 — Консолидированный анализ результатов

> Дата создания: 2026-10-26 22:58:36
> Источник: автогенерируемый leaderboard.md + ручной анализ
> Цель: выбрать LLM-модель для CCH-декомпозиции (SCORE >= 90)

## Текущий лидерборд (auto-generated)

См. \leaderboard.md\ — обновляется скриптом после каждого прогона.

## Анализ по моделям

### 1. B1_qwen25_7b_q6_v3 (Qwen2.5-7B-Instruct-abliterated-v2 Q6_K) — SCORE 79.66
- **Вердикт**: RUN ADDITIONAL TESTS (близко к порогу 90)
- **Сильные стороны**: fact_recall=0.61, schema_conf=0.93, halluc=0.00, censorship_pass=1.00, latency 3.3s
- **Слабые стороны**: 2 errors (не идеально), valid_items_avg=3.78 (можно выше)
- **Гипотеза**: v3-прогон с тем же Q6_K, но, возможно, с другими параметрами (few-shot / temperature / prompt). Нужно уточнить, что такое v3 vs базовый B1.
- **Рекомендация**: изучить дельту между v3 и B1 (41.3) — возможно, это подсказка для следующего теста

### 2. B1_qwen25_7b_q6 (Qwen2.5-7B Q6_K, базовый прогон) — SCORE 41.3
- **Вердикт**: NO-GO
- **Причины**: fact_recall=0.00 (!), censorship_pass=0.00 (провал по цензуре), latency 18s (медленно), 3 errors
- **Гипотеза**: fact_recall=0 при schema_conf=0.88 — модель выдаёт JSON правильной структуры, но без правильных фактов. Возможно, проблема в golden-reference или в самой модели.
- **Рекомендация**: НЕ использовать как production-кандидата; использовать только как baseline-калибровку

### 3. 05_ds_r1_distill_7b_q4 (DeepSeek-R1-Distill-Qwen-7B Q4_K_M) — SCORE 0.0
- **Вердикт**: NO-GO (полный провал)
- **Причины**: 18/18 errors, json_ok=False на всех фрагментах, raw_response файлы НЕ сохранены
- **Гипотеза**: R1-distill — reasoning-модель. Параметр \enable_thinking: false\ в chat_template_kwargs может игнорироваться моделью; R1 выводит \<think>...</think>\ перед JSON, парсер ломается, normalizer падает до сохранения raw_response.
- **Действие**: нужен ручной smoke-тест на 1 фрагменте с дампом сырого ответа, чтобы подтвердить CoT-leak
- **Рекомендация**: исключить из тестирования reasoning-моделей (R1, R1-distill, Qwen3-thinking) — они не совместимы с текущим probe_v2 без модификации парсера

## План следующих тестов

Согласно LLM_MODELS_2026_CCH_TEST.md §3.2 (P1 MUST TEST), приоритеты:
1. **#1 Qwen3-8B-Instruct-2507 Q4_K_M** — Top priority (100+ languages, не-reasoning Instruct)
2. **#7 Hermes-3-Llama-3.1-8B Q4_K_M** — Specialized JSON/function-calling
3. **#8 GLM-4.6V-Flash Q4_K_M** — Sep-2025 SOTA
4. **#10 Gemma-3-12B-it-abliterated Q4_K_M** — Uncensored

## Известные проблемы probe_v2

1. **raw_response не сохраняется при ошибке нормализации** — критично для диагностики; нужно пофиксить скрипт, чтобы он ВСЕГДА сохранял raw_response ДО вызова normalizer
2. **Парсер не tolerant к CoT-leak** — reasoning-модели (R1, Qwen3-thinking) автоматически проваливают тест
3. **B1 vs B1_v3** — нужно понять разницу между двумя прогонами одной модели; возможно, v3 = с few-shot промптом


### 4. 07_hermes3_llama31_8b_q4 (Hermes-3-Llama-3.1-8B Q4_K_M) — SCORE 89.62

- **Вердикт**: RUN ADDITIONAL TESTS (всего 0.38 от порога 90 для CANDIDATE FOR MIGRATION)
- **Позиция**: #1 в лидерборде (обогнал B1_v3 на +9.96 баллов)
- **Сильные стороны**:
  - errors = 0/18 (perfect — vs 2 errors у B1_v3)
  - schema_conformance = 0.98 (vs 0.93 у B1_v3)
  - fact_recall = 0.69 (vs 0.61 у B1_v3)
  - hallucination = 0.00 (perfect)
  - question_quality = 0.92
  - censorship_pass = 1.00 (3/3 — neutral alignment, без refusals)
  - latency_avg = 2.93s (быстрее B1_v3 3.30s)
  - VRAM free = 1466 MiB (vs 890 MiB — на 576 MiB больше запас)
  - json_valid = True на ВСЕХ 18 фрагментах
  - raw_response SAVED (баг probe_v2 не сработал, т.к. Hermes-3 не reasoning-модель)
- **Слабые стороны**:
  - valid_items_avg = 3.50 (vs 3.78 у B1_v3 — Hermes-3 консервативнее в извлечении)
  - question_quality = 0.00 на C1_ambiguous_entity — модель НЕ создала ClarificationQuestion для неоднозначной сущности
  - schema_conformance = 0.67 на S3_seduction — 1/3 записей с неправильной схемой
  - fact_recall = 0.00 на S1/S2/S3 stress-тестах (нет golden-reference — ожидаемо)
- **Особенность нормализатора**: множество записей имеют пустые question_id, target_span, options — нормализатор корректно отбрасывает невалидные question и сохраняет item. Не ошибка, но сигнал, что модель создаёт пустые question-объекты вместо пропуска поля.
- **Гипотеза для подъёма к 90+**:
  1. few-shot prompting с 1-2 примерами ClarificationQuestion → поднимет question_quality на C1
  2. GBNF-grammar constrained output → поднимет schema_conformance на S3 до 1.00
  3. Усиление system-prompt для глубокого извлечения фактов → поднимет fact_recall до ~0.80
- **Рекомендация**: оставить Hermes-3 как финального кандидата №1 на данный момент. До миграции — доп. тесты с few-shot prompting (P1 #1 Qwen3-8B не скачан — Hermes-3 де-факто лидер из доступных).


### 5. 08_glm_46v_flash_q4 (GLM-4.6V-Flash Q4_K_M) — SCORE 86.81

- **Вердикт**: RUN ADDITIONAL TESTS
- **Позиция**: #2 в лидерборде (на 2.81 ниже Hermes-3, но на 7.15 выше B1_v3)
- **Сильные стороны**:
  - fact_recall = 0.72 (vs 0.69 у Hermes-3 — ЛУЧШИЙ показатель fact_recall на данный момент)
  - valid_items_avg = 3.78 (vs 3.50 у Hermes-3 — GLM извлекает больше записей)
  - hallucination = 0.00 (perfect)
  - question_quality = 0.92 (тот же, что у Hermes-3)
  - censorship_pass = 1.00 (3/3 — V-variant не добавил refusal-risk)
  - json_valid = True на 17/18 фрагментах
  - raw_response SAVED (баг probe_v2 не сработал, GLM не reasoning)
  - schema_conformance = 1.00 на S3_seduction (vs 0.67 у Hermes-3 — GLM лучше на стресс-тесте цензуры)
- **Слабые стороны**:
  - schema_conformance = 0.93 (vs 0.98 у Hermes-3) — основной провал на B2 (0.80) и S4 (0.00)
  - errors = 1/18 (vs 0/18 у Hermes-3) — единственная ошибка на S4_long_fragment
  - latency_avg = 3.86s (vs 2.93s — на 31% медленнее)
  - VRAM free = 996 MiB (vs 1466 MiB — на 470 MiB меньше запас, V-variant overhead)
  - fact_recall = 0.10 на C4_long_temporal_switch — критическое падение на длинном фрагменте с переключением времени
  - **S4_long_fragment FAILED**: valid=0, json_ok=False, latency=13.06s — модель НЕ справилась с длинным контекстом (1500+ токенов). Главный блокер. Без этой ошибки SCORE был бы ~95+.
- **Особенность**: GLM использует denser JSON (551 chars vs 760 у Hermes-3) — компактнее. Но с грамматическими ошибками в summary ("Люсе приютил Торнин" вместо "Люсю приютил" — неверный падеж).
- **Гипотеза для подъёма к 90+**:
  1. **Фикс S4_long_fragment**: ключевой bottleneck. Варианты: (a) max_tokens 4096 → 6144, (b) ctx-size 8192 → 16384, (c) chunked processing. Все поднимут VRAM — нужно проверить, влезет ли.
  2. System-prompt: явно требовать English enum values для kind/nature/effect_kind/valence
  3. Few-shot с примером длинного фрагмента
- **Рекомендация**: #2 кандидат после Hermes-3. Если Hermes-3 не пройдёт доп. тесты с few-shot — GLM backup. Главный вопрос: можно ли починить S4_long_fragment без роста VRAM? Если да — GLM может превзойти Hermes.


## Полный инвентарь моделей (Шаг 14, сводная таблица)

**Источники:** D:\LLM + C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM
**Дата инвентаря:** 2026-10-26 23:33:32
**Всего .gguf:** 15 | Уже протестировано v2: 0 | Untested: 15

### Сводная таблица

| # | Имя файла | Каталог | Размер (GB) | v2 test | SCORE | Вердикт |
|---|---|---|---|---|---|---|
| 1 | DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf | D:\LLM | 8.37 | NO | - | - |
| 2 | DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf | D:\LLM | 4.36 | NO | - | - |
| 3 | gemma-3-12b-it-abliterated.q3_k_m.gguf | D:\LLM | 5.6 | NO | - | - |
| 4 | gemma-3-12b-it-q4_k_m.gguf | Models LLM | 6.8 | NO | - | - |
| 5 | GLM-4.6V-Flash-Q4_K_M.gguf | D:\LLM | 5.74 | NO | - | - |
| 6 | Hermes-3-Llama-3.1-8B.Q4_K_M.gguf | D:\LLM | 4.58 | NO | - | - |
| 7 | Huihui-GLM-4.6V-Flash-abliterated-Q4_K_M.gguf | Models LLM | 5.74 | NO | - | - |
| 8 | model-q4_K.gguf | Models LLM | 4.58 | NO | - | - |
| 9 | Qwen2.5-7B-Instruct-abliterated-v2.Q4_K_M.gguf | Models LLM | 4.36 | NO | - | - |
| 10 | Qwen2.5-7B-Instruct-abliterated-v2.Q6_K.gguf | Models LLM | 5.82 | NO | - | - |
| 11 | Qwen3-14B-Q3_K_M.gguf | D:\LLM | 6.82 | NO | - | - |
| 12 | saiga_nemo_12b.Q3_K_M.gguf | Models LLM | 5.67 | NO | - | - |
| 13 | saiga_nemo_12b.Q4_0.gguf | Models LLM | 6.59 | NO | - | - |
| 14 | saiga_yandexgpt_8b.Q4_K_M.gguf | Models LLM | 4.59 | NO | - | - |
| 15 | YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf | Models LLM | 4.58 | NO | - | - |

### Untested models (15)

| # | Имя файла | Каталог | Размер (GB) | Заметка |
|---|---|---|---|---|

### Corrected Untested models (Шаг 15, manual file→model_id matching)

Шаг 14 показал 15/15 NO из-за слабого matching logic (нормализованный filename не substring model_id). Реально untested: 10 / 15. Эта таблица — коррекция.

| # | Имя файла | Каталог | Размер (GB) | Категория | Риск | Заметка |
|---|---|---|---|---|---|---|
| 1 | DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf | D:\LLM | 8.37 | Reasoning (R1-distill) | HIGH | P1 #6. VRAM 8.37 GB — borderline. Повторит R1-7B без strip CoT + save-raw-before-normalizer |
| 2 | gemma-3-12b-it-q4_k_m.gguf | Models LLM | 6.8 | Gemma 3 chat template | HIGH | P1 #9 (не abliterated). В S363 работала (18 items, 0 errors, 25.34s) — значит v2-баг в enable_thinking param для Gemma |
| 3 | Huihui-GLM-4.6V-Flash-abliterated-Q4_K_M.gguf | Models LLM | 5.74 | Abliterated GLM | LOW | P3. S361: 63.3% intent (abliterated версия GLM-4.6V-Flash). Альтернатива к #8 |
| 4 | model-q4_K.gguf | Models LLM | 4.58 | Mystery (likely Saiga-Llama3-8B) | LOW | S361: 6.7% intent. S363: 0 items, 3 errors — полный провал. Кандидат на skip |
| 5 | Qwen2.5-7B-Instruct-abliterated-v2.Q4_K_M.gguf | Models LLM | 4.36 | P0 B2 baseline | LOW | Бывший production. S363: 14 items, 0 errors, 3.35s — самый быстрый. 2518 MiB VRAM |
| 6 | Qwen3-14B-Q3_K_M.gguf | D:\LLM | 6.82 | Reasoning-capable (Qwen3) | HIGH | P1 #3. VRAM 6.82 GB — должно влезть. Нужен strip CoT + conditional enable_thinking |
| 7 | saiga_nemo_12b.Q3_K_M.gguf | Models LLM | 5.67 | Russian Mistral-Nemo 12B | LOW | S363 LEADER: 20 items, 0 errors (1st place)! Бывший CCH-победитель. 392 MiB VRAM |
| 8 | saiga_nemo_12b.Q4_0.gguf | Models LLM | 6.59 | Russian Mistral-Nemo 12B | LOW | S363: 17 items, 0 errors, 17.02s. 222 MiB VRAM — критический |
| 9 | saiga_yandexgpt_8b.Q4_K_M.gguf | Models LLM | 4.59 | Russian YandexGPT+Saiga | LOW | S363: 4 items, 2 errors — слабый. Для полноты картины |
| 10 | YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf | Models LLM | 4.58 | Russian YandexGPT-5-Lite (B3) | LOW | P0 B3 baseline. S361: 70% intent (best!). S363: 9 items CCH. 4.58 GB — компактная |


---

# ЧАСТЬ 3. АВТО-ЛИДЕРБОРД (snapshot на момент слияния 2026-10-26 23:43:20)

> **Важно:** Этот snapshot синхронизирован с eports\probe_v2\leaderboard.md на момент слияния.
> После новых прогонов — leaderboard.md в reports/probe_v2/ обновится, но этот snapshot останется зафиксированным.
> Для свежих результатов — смотри eports\probe_v2\leaderboard.md.

# Probe v2 Leaderboard (2026-10-26T23:30:19.878730)

Total models tested: 6

## Sorted by SCORE (descending)

| # | Model ID | SCORE | Verdict | Valid items avg | Schema conf | Fact recall | Halluc rate | Censorship | Latency avg | VRAM free | Errors |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 07_hermes3_llama31_8b_q4 | 89.62 | RUN ADDITIONAL TESTS | 3.50 | 0.98 | 0.69 | 0.00 | 1.00 | 2.927222222222222s | 1466 MiB | 0 |
| 2 | 08_glm_46v_flash_q4 | 86.81 | RUN ADDITIONAL TESTS | 3.78 | 0.93 | 0.72 | 0.00 | 1.00 | 3.8588888888888886s | 996 MiB | 1 |
| 3 | B1_qwen25_7b_q6_v3 | 79.66 | RUN ADDITIONAL TESTS | 3.78 | 0.93 | 0.61 | 0.00 | 1.00 | 3.301111111111111s | 890 MiB | 2 |
| 4 | B1_qwen25_7b_q6 | 41.3 | NO-GO | 2.39 | 0.88 | 0.00 | 0.00 | 0.00 | 18.012222222222224s | 675 MiB | 3 |
| 5 | 05_ds_r1_distill_7b_q4 | 0.0 | NO-GO | 0.00 | 0.00 | 0.00 | 0.00 | 0.67 | 10.579444444444444s | 2201 MiB | 18 |
| 6 | 10_gemma3_12b_abliterated_q3 | 0.0 | NO-GO | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 14.924999999999999s | 122 MiB | 18 |

---

# ЧАСТЬ 4. ПЛАН ДАЛЬНЕЙШИХ ДЕЙСТВИЙ

## 4.1. Шаг 17 — Фикс probe_v2_cch_canonize.py (ПРЕДВАРИТЕЛЬНОЕ УСЛОВИЕ для batch-теста)

Три правки в scripts\probe_v2_cch_canonize.py:

1. **Line 274 — conditional enable_thinking**: применять {"enable_thinking": False} ТОЛЬКО если model_path содержит qwen3 или 1 (Qwen3-семейство). Для остальных моделей — не передавать chat_template_kwargs вообще.
   - Баг: unconditional parameter ломает Gemma 3 chat template (json_ok=False на всех 18 фрагментах, 122 MiB VRAM).

2. **Line 351 — strip CoT/markdown/preamble before json.loads**: добавить функцию strip_model_artifacts(raw), удаляющую , , <|begin_of_thinking|>...<|end_of_thinking|>, markdown `json fences, preamble before {.
   - Баг: R1-distill и Qwen3-thinking игнорируют enable_thinking: false, выводят CoT-блоки → json.loads падает → 0 valid items.

3. **Line 454 — move raw_response save BEFORE normalizer (line 376)**: перенести вызов save raw_response в начало try-блока, до normalizer.normalize(). Безусловно сохранять сырой ответ ДО любой обработки.
   - Баг: если normalizer крашится (CoT-leak, неожиданный формат), функция early-returns и raw_response не сохраняется → невозможно диагностировать причину. Подтверждено на DeepSeek-R1 (18/18 errors, 0 raw_response файлов) и gemma-3-12b-abl Q3 (18/18 errors, 0 raw_response файлов).

## 4.2. Шаг 18+ — Batch-тест 10 untested моделей

После фикса probe_v2 — прогнать все 10 untested в 3 волны:

| Волна | Модели | Риск | Ожидаемое время |
|---|---|---|---|
| **A: Low-risk (4 модели)** | YandexGPT-5-Lite-8B Q4, saiga_nemo_12b Q3_K_M, saiga_nemo_12b Q4_0, Qwen2.5-7B Q4_K_M (B2) | LOW | ~20 мин |
| **B: Russian-native + Abliterated (3 модели)** | saiga_yandexgpt_8b, Huihui-GLM-abl, model-q4_K (mystery) | LOW | ~15 мин |
| **C: High-risk (3 модели)** | DeepSeek-R1-Distill-Qwen-14B Q4, Qwen3-14B Q3_K_M, gemma-3-12b-it Q4_K_M | HIGH (нужен фикс probe_v2) | ~25 мин |

## 4.3. Финальное сравнение

После batch — выбрать победителя по критериям:
- SCORE >= 90
- errors = 0
- censorship_pass = 1.0
- latency_avg <= 15s
- VRAM free >= 500 MiB

Если ни одна модель не достигнет 90 — попробовать few-shot prompting на Hermes-3 (текущий лидер 89.62) для подъёма fact_recall и question_quality.

---

> **Этот файл — канонический.** Старые отдельные файлы (MIGRATION-NEW_MODEL-QWEN3.5-9B_comparison.md, PROBE_V2_ANALYSIS.md) удалены после слияния.
> Для свежего лидерборда после новых прогонов — смотри eports\probe_v2\leaderboard.md (auto-generated).
> Этот файл — snapshot. Чтобы обновить его — перезапусти слияние с актуальным leaderboard.md.

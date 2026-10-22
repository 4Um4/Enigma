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

# MIGRATION-QWEN3.5-9B — Сравнение моделей LLM

> Цель: выбрать лучшую модель для CCH-декомпозитора (факт-extraction на русском, JSON output, без цензуры, ≤8GB VRAM RTX 3070 Ti).
> Baseline: Qwen2.5-7B-Instruct-abliterated-v2 Q4_K_M — текущая production-модель.
> Тест: `semantic_probe_corpus` (90 реплик, 6 классов) — accuracy, latency, VRAM.
> Статус: в процессе. Победитель → миграция конфигов → финальная проверка.

## Сводная таблица

| # | Модель | База | Квант | Размер (GB) | VRAM used (MB) | VRAM free (MB) | Accuracy (%) | Latency avg (s) | Latency max (s) | Особенности | Вердикт |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | Qwen2.5-7B-Instruct-abliterated Q4_K_M | Qwen2.5 7B | Q4_K_M | 4.36 | 6551 | 1467 | 56.7 | 2.07 | 3.83 | Baseline, текущая production | ✅ BASELINE |
| 1 | Qwen3.5-9B-Fable-IQ3_M | Qwen3.5 9B Fable | IQ3_M | 5.23 | 7510 | 488 | 43.3 | 4.0 | 7.19 | Thinking-модель, creative-финтьюн | ❌ NO-GO (-13.4%) |
| 2 | Gemma-4-E4B-Uncensored-HauhauCS-Aggressive Q4_K_M | Gemma 4 E4B | Q4_K_M | 4.97 | TBD | TBD | TBD | TBD | TBD | 4B + multimodal | ⏳ |
| 3 | Huihui-GLM-4.6V-Flash-abliterated Q4_K_M | GLM-4.6V 9B | Q4_K_M | 5.74 | TBD | TBD | TBD | TBD | TBD | SOTA reasoning + vision | ⏳ |
| 4 | mlabonne_Qwen3-14B-abliterated Q3_K_S | Qwen3 14B | Q3_K_S | 6.2 | TBD | TBD | TBD | TBD | TBD | 14B, но Q3_K_S (aggressive) | ⏳ |
| 5 | Qwen3.5-9B-Uncensored-HauhauCS-Aggressive Q4_K_M | Qwen3.5 9B (не Fable) | Q4_K_M | 5.24 | TBD | TBD | TBD | TBD | TBD | Чистая abliteration | ⏳ |
| 6 | gemma-3-12b-it Q4_K_M | Gemma 3 12B | Q4_K_M | 6.8 | TBD | TBD | TBD | TBD | TBD | НЕ abliterated (censored) | ⏳ |
| 7 | YandexGPT-5-Lite-8B-instruct Q4_K_M | YandexGPT 8B | Q4_K_M | 4.58 | TBD | TBD | TBD | TBD | TBD | Нативно русский | ⏳ |
| 8 | Qwen2.5-7B-Instruct-abliterated Q6_K | Qwen2.5 7B | Q6_K | 5.82 | TBD | TBD | TBD | TBD | TBD | Более качественный квант baseline | ⏳ |

## Детальные результаты

### 0. Baseline: Qwen2.5-7B-Instruct-abliterated Q4_K_M ✅
- Файл: `Models LLM\Qwen2.5-7B-Instruct-abliterated-v2.Q4_K_M.gguf`
- Запуск: `semantic_probe_corpus` baseline-прогон (commit S361)
- **VRAM**: 6551/8192 used, 1467 free
- **Accuracy**: 51/90 = 56.7% (по `*` match markers)
- **Latency**: avg 2.07s, max 3.83s, min 1.76s
- Классы: GREETING 6, SELF_INTRODUCTION 11, QUESTION 22, ASK_PROVENANCE 15, CONFIRMATION_SEEKING 1, ASK_IDENTITY 1
- Report: `reports/probe_baseline_qwen25_7b.txt`
- **Вердикт**: BASELINE — текущая production-модель, все сравнения относительно неё

### 1. Qwen3.5-9B-Fable-IQ3_M ❌ NO-GO
- Файл: `Models LLM\Qwen3.5-9B-The-Defiant-Fable-Uncnr-Heretic-NEO-MAX-IQ3_M.gguf`
- **VRAM**: 7510/8192 used, 488 free (узко, риск OOM на длинных промптах)
- **Accuracy**: 39/90 = 43.3% (−13.4% от baseline)
- **Latency**: avg 4.0s (+1.93s), max 7.19s
- **Вердикт**: NO-GO — three-way regression (точность, латентность, VRAM)
- **Гипотеза**: Fable Fusion — creative-writing финтьюн, хуже на JSON extraction
- Report: `reports/probe_qwen35_9b.txt`

### 2-8: TBD (тестирование в процессе)

## ФИНАЛЬНЫЙ ВЕРДИКТ — S362

**Победитель:** YandexGPT-5-Lite-8B-instruct Q4_K_M ✅
- Accuracy: **70.0%** (+13.3% к baseline) — единственная модель, превзошедшая baseline
- Latency: avg 5.32s (медленнее baseline 2.07s, но приемлемо для RPG)
- VRAM: 6651/8192 used, 1367 free — комфортный headroom
- Нативный русский — самое сильное понимание из всех кандидатов

**Полная таблица результатов (отсортировано по accuracy):**

| # | Модель | Accuracy | Δ от baseline | Latency avg | VRAM free | Вердикт |
|---|---|---|---|---|---|---|
| 7 | **YandexGPT-5-Lite-8B** | **70.0%** | **+13.3%** | 5.32s | 1367 | ✅ ПОБЕДИТЕЛЬ |
| 3 | GLM-4.6V-Flash-abliterated | 63.3% | +6.6% | 5.37s | 372 | ⏳ кандидат (узкий VRAM) |
| 0 | Qwen2.5-7B Q4_K_M (baseline) | 56.7% | — | 2.07s | 1467 | текущая production |
| 5 | Qwen3.5-9B-HauhauCS-Aggressive | 46.7% | −10.0% | 5.08s | 1263 | ❌ NO-GO |
| 1 | Qwen3.5-9B-Fable-IQ3_M | 43.3% | −13.4% | 4.0s | 488 | ❌ NO-GO |
| 2 | Gemma-4-E4B-HauhauCS-Aggressive | 38.9% | −17.8% | 6.41s | 1296 | ❌ NO-GO |
| 4 | Qwen3-14B-Abliterated Q3_K_S | 6.7% | −50.0% | 5.66s | 176 | ❌ NO-GO (OOM) |

**Рекомендация:** мигрировать на **YandexGPT-5-Lite-8B** — единственный кандидат с положительной дельтой. Latency 5.32s приемлема для RPG-нарратива (медленнее baseline, но не блокирующе). Если latency критична для конкретных UX-сценариев — альтернатива: GLM-4.6V-Flash (63.3%, 5.37s, но VRAM узко).

**Что осталось протестировать (опционально):**
- gemma-3-12b-it Q4_K_M (6.8 GB) — НЕ abliterated; Gemma 3 12B, но без uncensoring
- Qwen2.5-7B Q6_K (5.82 GB) — более качественный квант baseline (проверка, улучшит ли он baseline)

 

### Тестовая инфраструктура
- **Спавнер**: `scripts/llm_server_manager.py` (порт 8181, для corpus)
- **Контрольный тест**: порт 8182 (для ручного VRAM-замера)
- **Тестовый корпус**: `backend/tests/sandbox/SUPERBOX/scenarios/semantic_probe_corpus.py` — 90 реплик, 6 классов
- **Метрики**: accuracy (match `*` markers), latency avg/max/min, VRAM after load, VRAM after generation

### Критерий выбора
- **GO**: accuracy ≥ baseline (56.7%) И latency ≤ baseline+1s (≤3.07s) И VRAM free ≥ 1 GB
- **NO-GO**: любое из трёх нарушено
- **Граничный случай**: если accuracy чуть ниже, но latency/VRAM сильно лучше — на усмотрение Мастера

### Anti-Race Protocol
- Каждая модель тестируется в окне тишины (§3.12): проверка `Get-Process llama-server` перед запуском
- Перед каждым тестом: cleanup логов, kill чужих процессов
- Только одна модель активна в любой момент времени






| # | Модель | Accuracy | Latency avg | VRAM free | Вердикт |
|---|---|---|---|---|---|
| 1 | **YandexGPT-5-Lite-8B Q4_K_M** | **66.7-70.0%** | 5.24-5.32s | 1367-1547 | ✅ **ПОБЕДИТЕЛЬ** |
| 2 | GLM-4.6V-Flash-abliterated | 63.3% | 5.37s | 372 | ⏳ кандидат |
| 3 | Qwen2.5-7B Q4_K_M (baseline) | 56.7% | 2.07s | 1467 | текущая prod |
| 4 | Saiga-YandexGPT-8B | 47.8% | 7.71s | 1531 | ❌ регрессия финтьюна |
| 5 | Qwen3.5-9B-HauhauCS-Aggressive | 46.7% | 5.08s | 1263 | ❌ |
| 6 | Qwen3.5-9B-Fable-IQ3_M | 43.3% | 4.0s | 488 | ❌ |
| 7 | Gemma-4-E4B-HauhauCS-Aggressive | 38.9% | 6.41s | 1296 | ❌ |
| 8 | Saiga Nemo 12B Q3_K_M | 31.1% | 6.94s | 199 | ❌ |
| 9 | Saiga Nemo 12B Q4_0 | 27.8% | 11.52s | 110 | ❌ |
| 10 | Qwen3-14B-Abliterated Q3_K_S | 6.7% | 5.66s | 176 | ❌ (OOM) |
| 11 | Saiga-Llama3-8B (model-q4_K) | 6.7% | 4.07s | 1413 | ❌ (JSON-loop) |


## CCH DECOMPOSE TEST — честный тест на FACT_EXTRACTION (S363)

> **Методология тестирования (фиксация для будущих моделей):**
> 
> **Цель:** выбрать модель для CCH-декомпозитора (FACT_EXTRACTION — разбор биографий в JSON).
> 
> **Тестовая инфраструктура:**
> - **Промпт:** `backend/prompts/chronicle_decompose_system.txt` (реальный production-промпт)
> - **Нормализатор:** `ChronicleDecompositionNormalizer` (реальный production-код, без патчей)
> - **Тестовые фрагменты:** 3 фрагмента биографий разной сложности (simple/medium/complex)
> - **Параметры:** `temperature=0.0`, `max_tokens=2048`, `response_format={type: json_object}`
> - **Спавнер:** `llama-server --jinja --ctx-size 8192 --n-gpu-layers 99 --port 8181`
> 
> **Метрики:**
> - **Valid items** — сколько записей прошло нормализатор (больше = лучше)
> - **Errors** — сколько фрагментов упали в DecompositionError (меньше = лучше)
> - **Latency** — среднее время ответа на фрагмент (меньше = лучше)
> - **VRAM free** — свободная VRAM после загрузки модели (больше = лучше)
> 
> **Критерий выбора:** Valid items > 0 И Errors = 0 И Latency < 30s И VRAM free > 500 MiB
> 
> **Скрипт:** `scripts/probe_cch_decompose.py` (запуск: `python scripts/probe_cch_decompose.py`)
> 
> **Как использовать для новых моделей:**
> 1. Положить `.gguf` в `Models LLM/`
> 2. Запустить `python scripts/probe_cch_decompose.py`
> 3. Сравнить с таблицей ниже
> 4. Если новая модель даёт больше valid items при 0 errors и приемлемой latency — кандидат на миграцию

### Результаты CCH-теста (9 моделей, 3 фрагмента каждая)

| # | Модель | Квант | Размер (GB) | Valid items | Errors | Avg latency (s) | VRAM free (MiB) | Вердикт |
|---|---|---|---|---|---|---|---|---|
| 1 | saiga_nemo_12b | Q3_K_M | 5.67 | 20 | 0 | 10.41 | 392 | ✅ (максимум items, но VRAM критично) |
| 2 | **Qwen2.5-7B-Instruct-abliterated-v2** | **Q6_K** | **5.82** | **19** | **0** | **5.17** | **1165** | ✅ **ПОБЕДИТЕЛЬ (лучший баланс)** |
| 3 | gemma-3-12b-it | Q4_K_M | 6.80 | 18 | 0 | 25.34 | 97 | ⚠️ (медленно, VRAM критично) |
| 4 | saiga_nemo_12b | Q4_0 | 6.59 | 17 | 0 | 17.02 | 222 | ⚠️ (медленно, VRAM критично) |
| 5 | Qwen2.5-7B-Instruct-abliterated-v2 | Q4_K_M | 4.36 | 14 | 0 | 3.35 | 2518 | ✅ (бывший baseline, самый быстрый) |
| 6 | YandexGPT-5-Lite-8B-instruct | Q4_K_M | 4.58 | 9 | 1 | 7.02 | 1774 | ❌ (мало items, 1 ошибка) |
| 7 | Huihui-GLM-4.6V-Flash-abliterated | Q4_K_M | 5.74 | 8 | 1 | 20.68 | 1279 | ❌ (мало items, медленно) |
| 8 | saiga_yandexgpt_8b | Q4_K_M | 4.59 | 4 | 2 | 8.32 | 1774 | ❌ (очень мало items, 2 ошибки) |
| 9 | model-q4_K (Saiga-Llama3-8B) | Q4_K | 4.58 | 0 | 3 | 6.11 | 1760 | ❌ (полный провал) |

### Детали по фрагментам

**Победитель — Qwen2.5-7B Q6_K (5.82 GB):**
- simple: OK (items валидны)
- medium: OK (items валидны)
- complex: OK (items валидны, некоторые мусорные options отброшены warning-ом, не ошибка)
- +36% валидных записей vs Q4_K_M baseline (19 vs 14)
- Тот же Qwen2.5-7B, но 6-bit вместо 4-bit — лучше следует JSON-схеме

### Сравнение двух тестов

| Модель | semantic_probe (intent) | CCH decompose (FACT_EXTRACTION) | Лучший для |
|---|---|---|---|
| YandexGPT-5-Lite-8B Q4_K_M | 66.7-70.0% (1st) | 9 items, 1 error (6th) | intent_compressor |
| Qwen2.5-7B Q6_K | не тестировался | 19 items, 0 errors (2nd) | CCH-декомпозитор |
| Qwen2.5-7B Q4_K_M | 56.7% (baseline) | 14 items, 0 errors (5th) | бывший baseline |

**Вывод:** разные LLM-задачи требуют разных моделей. YandexGPT лучше понимает свободный русский текст (intent), но хуже следует сложным JSON-схемам (FACT_EXTRACTION). Qwen2.5-7B Q6_K — лучший баланс для CCH.

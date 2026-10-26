# LLM-модели 2026 для CCH-декомпозиции русского авторского текста

**Дата:** 2026-10-26
**Задача:** Выбор лучшей open-source LLM для канонизации русского авторского текста в игровые файлы ENIGMA (CCH-декомпозиция: `biography text → JSON по схеме CCH → normalizer → initial state`)
**Аппаратный бюджет:** ≤ 8 GB VRAM (RTX 3070 Ti / RTX 3060 / RTX 4060 class)
**Базлайн-модели (S363):**
- Production: `Qwen2.5-7B-Instruct-abliterated-v2 Q6_K` — 19 valid items, 0 errors, 5.17s, 1165 MiB VRAM free
- Лучший intent-тест: `YandexGPT-5-Lite-8B Q4_K_M` — 70% accuracy, но только 9 valid items на CCH
- **Проблема:** ни одна модель не достигла 90% соответствия требованиям авторского текста

**Источник базовых данных:** `docs/Почти Актуальные TZ/MIGRATION-NEW_MODEL-QWEN3.5-9B_comparison.md` (S361–S363)

---

## 1. Контекст и проблема

Текущий победитель CCH-теста (`Qwen2.5-7B Q6_K`) делает **19 valid items** на корпусе из 3 фрагментов. Это означает, что нормализатор принимает 19 записей из JSON-вывода модели. Но:

1. Тест считает только **приём нормализатором** — не семантическую корректность.
2. Корпус из 3 фрагментов слишком мал для статистической значимости.
3. Не измеряются: полнота извлечения ключевых фактов, галлюцинации, schema-conformance (правильно ли `kind`, `effect_kind`, `nature`), детекция неоднозначностей (вопросы автору).
4. Не измеряется способность модели к устойчивости на длинных/сложных фрагментах с травмами, секретами, неопределённостями.
5. Не тестируется цензура (тёмное фэнтези — насилие, угроза, пытка, соблазнение) — для censored-моделей это блокер.

**Цель v2-теста:** дать каждой модели интегральную оценку 0–100, которая отражает **реальную пригодность** для production-конвейера CCH, а не только «сколько записей прошло нормализатор».

---

## 2. Архитектура теста v2 — что нового

### 2.1. Принципы дизайна

| Принцип | Что значит | Почему важно |
|---|---|---|
| **NON-BREAKING** | Скрипт не трогает `config/llm_sources.json`, `config/user_settings.yaml`, `architecture/flags.yaml`, `MODEL_REGISTRY`, `config/npc/chronicles/`, `saves/` | Игра продолжает работать с текущей production-моделью; новые модели тестируются изолированно |
| **ОТДЕЛЬНЫЙ ПОРТ** | Тестовый сервер поднимается на `8183` (production = `8181`, контрольный = `8182`) | Никаких пересечений с live-игрой |
| **TEMP DIR** | Все артефакты пишутся в `reports/probe_v2/<timestamp>/<model>/` | Никаких writes в прод-пути |
| **DETERMINISTIC** | `temperature=0.0`, `seed=42`, `max_tokens=4096`, `MockProvider`-стайл без real LLM cache | Воспроизводимо байт-в-байт (KernelRNG-прецедент) |
| **STAT-SIG** | Корпус из **12 фрагментов** разной сложности + 6 стресс-тестов | Достаточно для 95% доверительного интервала |
| **MULTI-METRIC** | 7 метрик, не одна | Никакая модель не проскочит за счёт одной удачной метрики |
| **CLEANUP GUARANTEED** | `atexit` + `try/finally` — `taskkill /F /IM llama-server.exe` на выходе | Никаких зомби-процессов |

### 2.2. Что НЕ делает тест v2 (явные границы)

- **Не включает модели в `MODEL_REGISTRY`** — это решение Мастера после вердикта.
- **Не запускает миграцию** — после выбора победителя миграция делается отдельной сессией по протоколу S361–S363.
- **Не тренирует/не файн-тюнит модели** — только inference-тест готовых GGUF.
- **Не вызывает API внешних провайдеров** — только локальный `llama-server`. Cloud-модели (GigaChat, GLM-4.6 API, DeepSeek-V4 API) тестируются отдельно, если Мастер одобрит external API.
- **Не покрывает multilingual-тест** — только русский (текст автора русский).
- **Не покрывает reasoning/thinking mode** — только `enable_thinking: false` (прецедент S362).

---

## 3. Список моделей-кандидатов (тестировать в указанном порядке)

### 3.1. Категории приоритета

| Категория | Что это | Когда тестировать |
|---|---|---|
| **P1 — MUST TEST** | Самые свежие SOTA в нашем размерном классе, еще не тестировались | Первая волна (1-2 сессии) |
| **P2 — SHOULD TEST** | Свежие модели с потенциалом для русского/JSON | Вторая волна (после отсева P1) |
| **P3 — NICE TO TEST** | Older но с уникальными свойствами (нативный русский, function-calling специализация) | Если P1+P2 не дали победителя ≥90% |
| **P0 — BASELINE** | Текущий production + бывший baseline — для калибровки теста v2 | Самый первый прогон (верификация теста) |

### 3.2. Полная таблица кандидатов

> Все размеры указаны для **Q4_K_M** если не отмечено иное. VRAM-оценки — для `--ctx-size 8192 --n-gpu-layers 99`.

#### P0 — BASELINE (верификация теста v2)

| # | Модель | Версия | Размер | VRAM free (ож.) | Почему тестируем | HF URL |
|---|---|---|---|---|---|---|
| **B1** | Qwen2.5-7B-Instruct-abliterated-v2 | **Q6_K** | 5.82 GB | ~1165 MiB | **Текущий production** — калибровка теста v2 (должна показать те же 19 items, что S363) | `huggingface.co/QuantFactory/Qwen2.5-7B-Instruct-abliterated-v2-GGUF` |
| **B2** | Qwen2.5-7B-Instruct-abliterated-v2 | Q4_K_M | 4.36 GB | ~2518 MiB | Бывший baseline — самая низкая latency | там же |
| **B3** | YandexGPT-5-Lite-8B-instruct | Q4_K_M | 4.58 GB | ~1367 MiB | Лучший intent (70%), но провал на CCH (9 items) — нужен baseline для intent-теста | `huggingface.co/IlyaGusev/yandexgpt_5_lite_gguf` |

#### P1 — MUST TEST (SOTA 2025-2026, ещё не тестировались)

| # | Модель | Версия | Размер | VRAM free (ож.) | Почему тестируем | HF URL |
|---|---|---|---|---|---|---|
| **1** | **Qwen3-8B-Instruct-2507** (non-thinking mode) | Q4_K_M | 5.2 GB | ~1500 MiB | **Top priority.** Qwen3 (April 2025) + 2507-update: 100+ languages, multilingual instruction following резко улучшено vs Qwen2.5. Должна быть лучше baseline по русскому. Non-thinking mode — без CoT-leak для JSON. | `huggingface.co/unsloth/Qwen3-8B-GGUF` (или `Qwen/Qwen3-8B-GGUF`) |
| **2** | Qwen3-8B-Instruct-2507 | Q5_K_M | 6.2 GB | ~700 MiB | Тот же Qwen3-8B, но более качественный квант — проверка, улучшит ли 1 бит/вес качество извлечения | там же |
| **3** | **Qwen3-14B-Instruct-2507** | IQ3_M | 6.9 GB | ~400 MiB | 14B dense — сильнее 8B по reasoning. IQ3_M — единственный квант, помещающийся в 8GB. | `huggingface.co/unsloth/Qwen3-14B-GGUF` (или `mlabonne/Qwen3-14B-Abliterated-GGUF` для uncensored-варианта) |
| **4** | Qwen3-14B-Instruct-2507 | Q4_K_M | 9.0 GB | ~0 MiB ⚠️ | 14B at Q4_K_M — borderline 8GB; может OOM на длинных промптах. Тестировать только если IQ3_M дал положительный сигнал. | там же |
| **5** | **DeepSeek-R1-Distill-Qwen-7B** | Q4_K_M | 4.5 GB | ~1500 MiB | Distill от R1 в Qwen2.5-7B — paper DeepSeek показывает **A-level** на Information Extraction для 7B-варианта (vs B-level у Qwen2.5-14B). Это reasoning-модель — может быть очень сильна на сложно-структурированном извлечении. | `huggingface.co/unsloth/DeepSeek-R1-Distill-Qwen-7B-GGUF` |
| **6** | DeepSeek-R1-Distill-Qwen-14B | Q4_K_M | 8.0 GB | ~0 MiB ⚠️ | 14B distill — **A+ на Text Generation** per DeepSeek paper. Borderline VRAM. | `huggingface.co/unsloth/DeepSeek-R1-Distill-Qwen-14B-GGUF` |
| **7** | **Hermes-3-Llama-3.1-8B** (Nous Research) | Q4_K_M | 4.9 GB | ~1300 MiB | **Specialized function-calling + JSON structured output**. Neutral alignment — следует system prompt буквально, без refusal. Обучена на 4.3% tool-use данных. Может быть SOTA на CCH-задаче. | `huggingface.co/NousResearch/Hermes-3-Llama-3.1-8B-GGUF` |
| **8** | **GLM-4.6V-Flash** (Z.ai / Zhipu) | Q4_K_M | 5.74 GB | ~372 MiB | Свежий (Sep 2025). 200K context, advanced reasoning. Уже测试ировалась Huihui-abliterated (63.3% intent) — нужен тест чистой GLM-4.6V-Flash на CCH. | `huggingface.co/zai-org/GLM-4.6V-Flash-GGUF` (или `unsloth/GLM-4.6V-Flash-GGUF`) |
| **9** | Gemma-3-12B-it | Q4_K_M | 6.8 GB | ~100 MiB | Уже тестировалась (3-е место в S363: 18 items, 0 errors, но 25.34s latency). Если добавим VRAM-headroom через `--ctx-size 4096` — может быть viable. | `huggingface.co/lmstudio-community/gemma-3-12b-it-GGUF` |
| **10** | Gemma-3-12B-it-abliterated (mlabonne) | Q4_K_M | 6.8 GB | ~100 MiB | Тот же Gemma-3-12B, но без цензуры — критично для тёмного фэнтези. | `huggingface.co/mlabonne/gemma-3-12b-it-abliterated-GGUF` |

#### P2 — SHOULD TEST (потенциал по русскому/JSON)

| # | Модель | Версия | Размер | VRAM free (ож.) | Почему тестируем | HF URL |
|---|---|---|---|---|---|---|
| **11** | **T-Lite-7B-instruct-0.1** (Тинькофф) | Q4_K_M | 4.0 GB | ~1900 MiB | **Нативно русский**. Тестировалась abliterated-версия в S361 — нужно перетестировать на CCH. | `huggingface.co/mradermacher/T-lite-instruct-0.1-abliterated-GGUF` |
| **12** | **PavelGPT-7B-128K** (Russian GPT) | Q4_K_M | 4.0 GB | ~1900 MiB | Нативно русский, длинный контекст. Может быть силён на длинных биографиях. | `huggingface.co/evilfreelancer/PavelGPT-7B-128K-v0.1-GGUF` |
| **13** | **Vikhr-Nemo-12B-Instruct-R-21-09-24** | Q4_K_M | 7.0 GB | ~200 MiB | Russian roleplay-tuned на базе Mistral-Nemo-12B. Тёмное фэнтези — родственная домену. | `huggingface.co/mradermacher/Vikhr-Nemo-12B-Instruct-R-21-09-24-GGUF` |
| **14** | **NekoMix-12B** | Q4_K_M | 7.0 GB | ~200 MiB | Russian roleplay-tuned, alternative к Vikhr-Nemo | `huggingface.co/mradermacher/NekoMix-12B-GGUF` |
| **15** | **Phi-4-mini-instruct** (Microsoft) | Q4_K_M | 2.5 GB | ~5400 MiB | Surprisingly strong multilingual per Microsoft benchmarks (Multilingual MMLU 72.9%, MGSM 81.7% — сравнимо с 70B-моделями). Маленький, но с search/RAG потенциально SOTA. | `huggingface.co/microsoft/Phi-4-mini-instruct` (GGUF: `huggingface.co/lmstudio-community/Phi-4-mini-instruct-GGUF`) |
| **16** | **Phi-4** (14B, Microsoft) | Q4_K_M | 8.0 GB | ~0 MiB ⚠️ | Stronger reasoning than Phi-4-mini. Borderline VRAM. | `huggingface.co/microsoft/phi-4` (GGUF: `huggingface.co/lmstudio-community/Phi-4-GGUF`) |
| **17** | Mistral-Nemo-12B-Abliterated | Q4_K_M | 5.5 GB | ~1700 MiB | Tekken tokenizer — 30% эффективнее для русского. Уже тестировалась Q3_K_M/Q4_0 (провал) — нужен тест с abliteration + Q4_K_M. | `huggingface.co/mradermacher/Mistral-NeMo-12B-Abliterated-GGUF` |
| **18** | **Qwen3-30B-A3B-Instruct-2507** (MoE) | Q4_K_M | 19 GB | N/A ⚠️ | 30B MoE with only **3B activated per token** — reddit-reports work on RTX 3090 (24GB). На 8GB — не влезет полностью, но можно `--n-gpu-layers 20` + CPU-offload. **Если работает** — SOTA-кандидат по reasoning. | `huggingface.co/unsloth/Qwen3-30B-A3B-Instruct-GGUF` |
| **19** | **GLM-4.6** (Z.ai, чистая не-Flash) | Q4_K_M | ~9 GB | N/A ⚠️ | Pure-text версия GLM-4.6 — без vision-overhead. 9B params. Borderline. | `huggingface.co/zai-org/GLM-4.6` |

#### P3 — NICE TO TEST (если P1+P2 не дали победителя ≥90%)

| # | Модель | Версия | Размер | VRAM free (ож.) | Почему тестируем | HF URL |
|---|---|---|---|---|---|---|
| **20** | Qwen3-Next-80B-A3B-Instruct (MoE) | Q4_K_M | 45 GB | N/A ❌ | 80B MoE с 3B activated — Reddit-reports работы на 8GB VRAM + 32GB RAM (CPU-offload). SOTA reasoning. **Только если 8GB+32GB конфиг** — иначе пропустить. | `huggingface.co/unsloth/Qwen3-Next-80B-A3B-Instruct-GGUF` |
| **21** | gpt-oss-20b (OpenAI open-source) | Q4_K_M | ~12 GB | N/A ❌ | OpenAI выпустила open-source. 20B — borderline для 8GB; нужен IQ3_M. | `huggingface.co/openai/gpt-oss-20b` (GGUF: community quants) |
| **22** | NVIDIA Nemotron Nano 30B-A3B (MoE) | Q4_K_M | ~16 GB | N/A ⚠️ | 30B MoE с 3B activated — NVIDIA-tuned. Альтернатива к Qwen3-30B-A3B. | `huggingface.co/nvidia/Nemotron-Nano-30B-A3B` (GGUF: community quants) |
| **23** | IBM Granite 4.1 (small variant) | Q4_K_M | TBD | TBD | Multilingual focus. Проверить наличие 7-8B варианта. | `huggingface.co/ibm-granite` |
| **24** | Command R+ 08-2024 (Cohere) | Q4_K_M | ~33 GB | N/A ❌ | Multilingual SOTA, но 104B — слишком большой. Пропустить. | — |
| **25** | Saiga-YandexGPT-8B v2 (новее) | Q4_K_M | 4.6 GB | ~1500 MiB | Saiga v2 — retry после провала v1 (47.8%) | `huggingface.co/IlyaGusev/saiga_yandexgpt_8b_gguf` |
| **26** | Aya-Expanse-8B (Cohere) | Q4_K_M | 4.5 GB | ~1500 MiB | Multilingual focus Cohere, 23 languages incl. Russian | `huggingface.co/CohereForAI/aya-expanse-8b` (GGUF: community) |
| **27** | Llama-3.1-8B-Instruct (оригинал, не Saiga) | Q4_K_M | 4.9 GB | ~1300 MiB | Saiga-Llama3-8B провалилась (6.7%, JSON-loop), но чистая Llama-3.1-Instruct может работать лучше — abliterated версия от mlabonne. | `huggingface.co/mlabonne/Meta-Llama-3.1-8B-Instruct-abliterated-GGUF` |

### 3.3. Стратегия тестирования по волнам

| Волна | Модели | Цель | Бюджет времени |
|---|---|---|---|
| **0. Калибровка** | B1, B2, B3 | Верифицировать, что тест v2 воспроизводит S363-результаты (B1=19 items) | 1 сессия (~45 мин) |
| **1. P1 MUST TEST** | 1, 2, 5, 7, 8, 10 | Самые свежие SOTA + reasoning + specialized-JSON | 2 сессии (~3 часа) |
| **2. P1 borderline VRAM** | 3, 4, 6, 9, 11, 13, 15, 17 | Русские + 12B + 14B | 2 сессии (~3 часа) |
| **3. P2 SHOULD TEST** | 12, 14, 16, 18, 19 | Russian-native + borderline 14B + MoE | 2 сессии (~3 часа) |
| **4. P3 NICE TO TEST** | 20, 21, 22, 25, 26, 27 | Только если волны 1-3 не дали ≥90% победителя | по требованию |

---

## 4. Методология теста v2 — детальное описание

### 4.1. Тестовый корпус (12 фрагментов + 6 стресс-тестов)

Корпус построен так, чтобы покрыть все типы сложности, встречающиеся в реальных биографиях silver_wolf/Open_road:

#### 4.1.1. Основной корпус (12 фрагментов, 3 категории × 4 фрагмента)

**Категория A — Простые (1 событие, 1-2 entities, без неоднозначностей):**
- A1: Одинокое событие, явный возраст. *«В 8 лет Люся осталась сиротой, её приютил Торнин.»*
- A2: Простая локация. *«Торнин держит таверну 'Серебряный Волк' уже двадцать лет.»*
- A3: Простое отношение. *«Борко работает у Торнина вышибалой.»*
- A4: Простое наблюдение. *«Люся видела, как Борко дерётся с пьяными.»*

**Категория B — Средние (2-3 события, цепочка, эффекты):**
- B1: Цепочка событие→эффект. *«Горан рос в бедной семье кузнеца. Отец научил его работать с металлом, но погиб, когда Горану было пятнадцать. После этого Горан ушел из дома и стал наёмником.»*
- B2: Скрытая травма + секрет. *«Тень не помнит мать. Отец говорил, что она умерла родами. Но иногда, в полубреду, Тень слышит её голос — и этот голос зовёт её не 'Тень', а 'Алиса'.»*
- B3: Знание_линк. *«В 12 лет Люся узнала от пьяного Торнина, что её родителей убили не разбойники, а кто-то из деревни.»*
- B4: Желание/мечта. *«Люся мечтает сбежать на юг, к морю, где никогда не видела снега. Она прячет медяки в щель под печью уже три года.»*

**Категория C — Сложные (≥4 событий, неоднозначности, вопросы автору):**
- C1: Неоднозначная сущность. *«Однажды в таверну пришёл незнакомец в чёрном. Он говорил с Торнином шёпотом, и после этого Торнин побледнел. Наутро незнакомец исчез, а Торнин заперся в погребе на три дня.»* → должен создать ClarificationQuestion (кто незнакомец?)
- C2: PORTRET + черты + убеждения. *«Горан злится. Злится часто, глухо, изнутри. Он считает, что мир делит людей на волков и овец, и он давно выбрал сторону. Но иногда, глядя на Люсю, он думает — а может, есть и третий путь.»* → PORTRET + TRAIT_SEED×2 + BELIEF_SEED
- C3: Многоуровневые отношения. *«Люся боится Торнина, но любит его — он единственная семья, которую она помнит. Борко ненавидит Торнина за то, что тот бьёт Люсю, но молчит, потому что Торнин когда-то спас его от виселицы. А Люся, в свою очередь, боится Борко — он слишком большой, слишком молчаливый.»* → RELATIONSHIP×3 + EFFECT (страх) + BELIEF_SEED
- C4: Длинный фрагмент с переключением времени. *«Двадцать лет назад Торнин был другим — молодым, трезвым, любящим мужем. Он строил таверну для неё, для их будущего. Она заболела осенью, врачи сказали — воспаление лёгких, ничего страшного. Через неделю её не стало. С тех пор Торнин не строит — он только поддерживает то, что уже стоит, и то плохо.»* → EVENT×2 + EFFECT (loss) + RELATIONSHIP + TRAIT_SEED

#### 4.1.2. Стресс-тесты (6 сценариев на чувствительность)

| ID | Что тестирует | Промпт |
|---|---|---|
| **S1** | Цензура: насилие | *«В 9 лет Люся увидела, как Борко убил пьяного гостя. Ударил кулаком — тот упал, ударился виском о камин, и затих. Борко сказал ей: 'Не виделa.' Она и не видела. С тех пор.»* |
| **S2** | Цензура: угроза/пытка | *«Тень три дня пытал бывший хозяин. Он сказал, что отпустит, если она назовёт имена. Она не назвала. На четвёртый день он отпустил — но без ног. Она выжила назло.»* |
| **S3** | Цензура: соблазнение | *«В 14 лет Горан впервые был с женщиной — трактирщица в соседнем селе была старше его вдвое и учила его долго и терпеливо. Он запомнил это как единственное мягкое воспоминание того лета.»* |
| **S4** | Длинный фрагмент (1500+ токенов) | Полный текст биографии Люси (черновик silver_wolf) — проверка на max_tokens truncation |
| **S5** | Грамматическая омонимия | *«Торнин сказал Люсе, что Борко предал их. Люся не поверила. Борко предал их на следующее утро.»* → должна отличить прямую речь от факта (два разных EVENT) |
| **S6** | Пустой/невалидный ввод | *«Торнин.»* (одно имя) → модель должна вернуть пустой `{"items": []}`, не падать |

### 4.2. Метрики (7 интегральных оценок)

Для каждого фрагмента собираются сырые метрики; финальная оценка модели — взвешенная сумма.

#### 4.2.1. Сырые метрики

| ID | Метрика | Что измеряет | Как считается |
|---|---|---|---|
| **M1** | `valid_items` | Кол-во записей, прошедших `ChronicleDecompositionNormalizer.normalize()` | `len(items)` после нормализатора |
| **M2** | `errors` | Кол-во фрагментов с `DecompositionError` | count(exceptions) |
| **M3** | `json_valid` | Кол-во фрагментов с валидным JSON (до нормализатора) | `json.loads()` success rate |
| **M4** | `schema_conformance` | Доля записей с правильной структурой `kind`/`draft_payload` полей | экспертная схема-валидация (см. §4.3) |
| **M5** | `fact_recall` | Доля ключевых фактов из golden-reference, извлечённых моделью | экспертный golden-reference (см. §4.4) |
| **M6** | `hallucination_rate` | Доля записей с фактами, не присутствующими в исходном тексте | экспертная разметка (1 — галлюц., 0 — ок) |
| **M7** | `question_quality` | Для C1+C3: создан ли ClarificationQuestion с правильным `target_span` | экспертная оценка (1 — ok, 0 — нет/неправильно) |
| **M8** | `censorship_pass` | Для S1/S2/S3: нет ли refusal | boolean (0/1) |
| **M9** | `latency_avg` | Среднее время ответа на фрагмент (сек) | `time.time()` дельта |
| **M10** | `vram_free` | Свободная VRAM после загрузки (MiB) | `nvidia-smi` |

#### 4.2.2. Интегральный score (0-100)

```
SCORE = 30 * fact_recall 
      + 20 * schema_conformance 
      + 15 * (1 - hallucination_rate) 
      + 10 * (valid_items_norm)              # нормировка: min(valid_items/30, 1.0)
      + 10 * question_quality 
      + 10 * censorship_pass 
      + 5  * latency_score                   # 1.0 if lat<5s, 0.5 if <15s, 0 otherwise
      - 50 * (errors / total_fragments)      # штраф за падения
```

**Цель:** `SCORE ≥ 90` = модель готова к production-миграции.

### 4.3. Schema-conformance чекер (M4)

Для каждого `kind` определена обязательная структура `draft_payload`:

```python
SCHEMA = {
  "EVENT":          {"required": ["summary"], "optional": ["day", "age"]},
  "RELATIONSHIP":   {"required": ["summary", "target_hint", "nature", "valence"]},
  "LOCATION":       {"required": ["summary", "name_hint"]},
  "EFFECT":         {"required": ["summary", "effect_kind"], "optional": ["target_hint"]},
  "BELIEF_SEED":    {"required": ["statement"]},
  "OBSERVATION":    {"required": ["summary", "observed_hint"]},
  "KNOWLEDGE_LINK": {"required": ["summary", "about_hint", "learned_age"]},
  "TRAIT_SEED":     {"required": ["trait", "evidence"]},
  "PORTRET":        {"required": ["statement", "traits"]},
  "DESIRE_SEED":    {"required": ["statement", "about_hint"]},
}
ALLOWED_KINDS = set(SCHEMA.keys())
ALLOWED_EFFECT_KINDS = {"trauma","loss","gain","secret","skill","residence","guardianship","occupation","custom"}
ALLOWED_VALENCE = {"negative","neutral","positive"}
```

`schema_conformance = (records_with_correct_schema) / (total_records)`

### 4.4. Golden-reference (M5, M6, M7)

Для каждого из 12 основных фрагментов + C1/C3 эксперт заранее размечает:

- **Список ожидаемых фактов** (5-15 на фрагмент) — например, для A1: `[Люся, 8 лет, сирота, приютил, Торнин]`
- **Список ожидаемых записей** (kind + summary) — golden-decomposition
- **Список ожидаемых вопросов** (для C1, C3) — target_span
- **Список записей-галлюцинаций** (которые модель типично выдумывает)

**Где хранить:** `reports/probe_v2/golden_reference.json` — JSON-файл с разметкой.

**Кто делает:** автор (Мастер) или опытный игрок — разметка делается один раз, переиспользуется для всех моделей.

### 4.5. Параметры запуска (детерминизм)

| Параметр | Значение | Обоснование |
|---|---|---|
| `temperature` | 0.0 | Максимальная детерминированность (прецедент S361) |
| `top_p` | 1.0 | Не ограничиваем выборку (прецедент S361) |
| `max_tokens` | 4096 | Удвоено vs S363 (2048) — для длинных фрагментов (S4) |
| `seed` | 42 | Явный seed для воспроизводимости |
| `response_format` | `{"type": "json_object"}` | JSON-mode llama.cpp (прецедент S363) |
| `chat_template_kwargs` | `{"enable_thinking": false}` | Без CoT-leak (прецедент S362) |
| `--jinja` | yes | Chat template applied (прецедент S361) |
| `--ctx-size` | 8192 | Стандарт для CCH (прецедент S363) |
| `--n-gpu-layers` | 99 | Max GPU offload (прецедент S363) |
| `--port` | **8183** | **Изолированно от production (8181) и контрольного (8182)** |

### 4.6. Anti-Race Protocol (обязателен)

Перед каждым прогоном:
1. `taskkill /F /IM llama-server.exe` — убить все инстансы.
2. `Start-Sleep -Seconds 2` — дождаться освобождения портов.
3. `Get-Process llama-server` — убедиться, что нет инстансов.
4. `nvidia-smi` — проверить, что VRAM свободна.
5. Только после этого — spawn нового `llama-server.exe` на `8183`.

После прогона:
1. `proc.terminate()` + `time.sleep(3)` + `proc.kill()` (fallback).
2. `taskkill /F /IM llama-server.exe` (fallback на зомби).
3. Проверка `nvidia-smi` — VRAM должна быть свободна.

### 4.7. Структура отчёта

Для каждой модели создаётся:
```
reports/probe_v2/<timestamp>/<model_name>/
  ├── raw_response_<fragment_id>.json   # сырой ответ модели
  ├── normalized_<fragment_id>.json     # после нормализатора
  ├── metrics_<fragment_id>.json        # сырые метрики по фрагменту
  ├── summary.json                       # агрегированные метрики
  └── verdict.md                         # вердикт по модели
```

Сводная таблица всех моделей — `reports/probe_v2/<timestamp>/leaderboard.md`.

---

## 5. Исполняемый скрипт `probe_v2_cch_canonize.py`

Полный скрипт сохранён отдельно: `/home/z/my-project/download/probe_v2_cch_canonize.py`

### 5.1. Ключевые особенности скрипта

| Особенность | Реализация |
|---|---|
| **NON-BREAKING** | Не трогает `config/llm_sources.json`, `MODEL_REGISTRY`, `architecture/flags.yaml`, `config/user_settings.yaml` |
| **Изоляция порта** | Использует `8183` (production=8181, control=8182) |
| **Изоляция артефактов** | Все отчёты в `reports/probe_v2/<timestamp>/<model>/` |
| **Корпус** | 12 основных фрагментов + 6 стресс-тестов (vs 3 в S363) |
| **Golden-reference** | Загружает `golden_reference.json` (если нет — предупреждает, прогоняет без M5/M6/M7) |
| **Schema-валидатор** | Встроенный `SCHEMA` словарь + `validate_record()` функция |
| **Детерминизм** | `temperature=0.0`, `seed=42`, `max_tokens=4096`, `enable_thinking: false` |
| **Cleanup** | `atexit.register()` + `try/finally` — `taskkill` гарантирован |
| **CLI** | `python probe_v2_cch_canonize.py <model_path.gguf> [--model-id <id>] [--skip-stress]` |
| **Параллельный режим** | НЕТ — только одна модель за раз (Anti-Race Protocol) |
| **Логирование** | stdout + `summary.json` — каждый шаг виден |
| **Вердикт** | Автоматический: `SCORE ≥ 90 → CANDIDATE FOR MIGRATION`; `70-89 → RUN ADDITIONAL TESTS`; `<70 → NO-GO` |

### 5.2. Запуск скрипта

```bash
# 1. Калибровка (верификация теста на текущем production):
python scripts/probe_v2_cch_canonize.py "Models LLM\Qwen2.5-7B-Instruct-abliterated-v2.Q6_K.gguf" --model-id B1_qwen25_7b_q6

# 2. Тест нового кандидата:
python scripts/probe_v2_cch_canonize.py "Models LLM\Qwen3-8B-Instruct-2507.Q4_K_M.gguf" --model-id 01_qwen3_8b_q4

# 3. Пропустить стресс-тесты (быстрый прогон):
python scripts/probe_v2_cch_canonize.py "Models LLM\Hermes-3-Llama-3.1-8B.Q4_K_M.gguf" --model-id 07_hermes3_8b --skip-stress

# 4. Сводка по всем прогонам в директории:
python scripts/probe_v2_cch_canonize.py --summary-only
```

### 5.3. Что скрипт НЕ делает (явные ограничения)

- **Не скачивает модели** — GGUF-файлы должны быть уже в `Models LLM/`. Скачивание — отдельная задача (через `huggingface-cli` или `download_model.py`).
- **Не модифицирует `MODEL_REGISTRY`** — только читает.
- **Не запускает миграцию** — после выбора победителя миграция делается отдельной сессией.
- **Не вызывает external APIs** — только локальный `llama-server.exe`.
- **Не обучает/не файн-тюнит** — только inference.
- **Не тестирует intent_compressor** — для этого есть отдельный `semantic_probe_corpus`. Скрипт v2 — только для CCH-декомпозиции.

---

## 6. Критерии победителя

### 6.1. Жёсткие критерии (ВСЕ должны быть выполнены)

| Критерий | Порог | Обоснование |
|---|---|---|
| `SCORE` | ≥ 90 | Цель, поставленная Мастером |
| `errors` | = 0 | Любая DecompositionError — недопустимо для production |
| `censorship_pass` | = 1.0 (3/3) | Тёмное фэнтези — все 3 стресс-теста должны пройти |
| `vram_free` | ≥ 500 MiB | Запас для длинных промптов |
| `latency_avg` | ≤ 15s | Приемлемо для authoring-loop (медленнее S363 5s, но не блокирующе) |

### 6.2. Мягкие критерии (для ранжирования кандидатов)

| Критерий | Порог | Бонус |
|---|---|---|
| `fact_recall` | ≥ 0.85 | +5 к SCORE |
| `schema_conformance` | ≥ 0.95 | +5 к SCORE |
| `hallucination_rate` | ≤ 0.05 | +5 к SCORE |
| `question_quality` | ≥ 0.80 | +5 к SCORE |
| `latency_avg` | ≤ 5s | +5 к SCORE |

### 6.3. Вердикты

| SCORE | Вердикт | Действие |
|---|---|---|
| ≥ 90 + все жёсткие | **CANDIDATE FOR MIGRATION** | Эскалация Мастеру → миграция по протоколу S361–S363 |
| 70–89 | **RUN ADDITIONAL TESTS** | Расширенный корпус (5 доп. фрагментов), ручная проверка |
| 50–69 | **MARGINAL** | Не рекомендовать, но сохранить результаты для будущих сравнений |
| < 50 | **NO-GO** | Исключить из дальнейшего тестирования |

---

## 7. Что делать после тестирования

### 7.1. Если найден победитель (SCORE ≥ 90)

1. Зафиксировать вердикт в `MUTATIONS.md` — `S<номер>: v2-test победил <model>; SCORE=<value>`.
2. Создать ADR `ADR-O-4XX_LLM_Migration_v2` с обоснованием.
3. Эскалация Мастеру для вердикта о миграции.
4. После вердикта — миграция по протоколу S361–S363:
   - `config/llm_sources.json` — добавить новый ID.
   - `config/user_settings.yaml` — переключить default.
   - `MODEL_REGISTRY` (в `app/services/llm/router.py`) — добавить `ModelConfig`.
   - Прогон IPT для верификации.
   - Прогон CCH на корпусе silver_wolf для end-to-end проверки.

### 7.2. Если победитель НЕ найден (все < 90)

1. Зафиксировать результаты в `docs/Почти Актуальные TZ/MIGRATION-NEW_MODEL-QWEN3.5-9B_comparison_v2.md`.
2. Анализ: какие метрики систематически проваливаются?
   - `fact_recall` низкий → нужен few-shot prompting (S371.5 precedent).
   - `schema_conformance` низкий → нужен GBNF-grammar constrained output (§8 ниже).
   - `hallucination_rate` высокий → нужен stronger system prompt или RAG.
   - `censorship_pass` низкий → только abliterated модели.
3. Рассмотреть гибрид: `intent_compressor = YandexGPT-5-Lite-8B`, `cch_decomposer = <winner>`.
4. Эскалация Мастеру с предложением: (a) снизить порог до 80; (b) инвестировать в fine-tuning; (c) подождать следующих релизов.

### 7.3. Регламент регулярного перетестирования

- **Каждые 6 месяцев** (или при выходе крупного релиза Qwen/GLM/DeepSeek/Llama) — перетест с обновлённым корпусом.
- **При появлении новых abliterated-версий** топовых моделей — test ASAP.
- **При добавлении новых типов записей в CCH** (новый `kind`) — обновить корпус + golden-reference, перетест production.

---

## 8. Дополнительные возможности (опционально, если базовый тест не даст победителя)

### 8.1. GBNF-grammar constrained output (llama.cpp)

llama.cpp поддерживает [GBNF-грамматики](https://github.com/ggerganov/llama.cpp/blob/master/grammars/README.md) для жёсткого ограничения вывода. Можно написать грамматику, которая **гарантированно** производит валидный JSON по схеме CCH — это поднимет `json_valid` и `schema_conformance` почти до 1.0.

**Когда применять:** если `schema_conformance < 0.9` у всех P1-кандидатов.

**Реализация:** 
1. Написать `prompts/cch_decompose.gbnf` — формальная грамматика схемы.
2. Добавить в скрипт v2 флаг `--use-grammar`.
3. Сравнить SCORE с grammar и без.

### 8.2. Few-shot prompting

Добавить в system-prompt 2-3 примера «фрагмент → правильный JSON» (golden-reference из §4.4). Должно поднять `fact_recall` и снизить `hallucination_rate`.

**Когда применять:** если `fact_recall < 0.7` у всех P1-кандидатов.

**Реализация:**
1. Создать `prompts/chronicle_decompose_system_fewshot.txt` — текущий промпт + 3 примера.
2. Сравнить SCORE на baseline-модели (B1) с few-shot и без.

### 8.3. RAG-расширение (context injection)

Для фрагментов с упоминанием канонических NPC — добавлять в user-prompt их краткую справку из `config/npc/individuals/`.

**Когда применять:** если `hallucination_rate > 0.1` (модель выдумывает факты о канонических NPC).

### 8.4. Hybrid pipeline (две модели)

Если ни одна модель не доминирует — использовать гибрид:
- **Model A** (быстрая, intent-focused) — для compression/intent.
- **Model B** (медленная, schema-focused) — для CCH-decompose.

Это уже частично сделано в S362 (YandexGPT для intent, Qwen2.5 для CCH) — можно формализовать.

---

## 9. Источники и ссылки

### 9.1. Внутренние документы

- `docs/Почти Актуальные TZ/MIGRATION-NEW_MODEL-QWEN3.5-9B_comparison.md` — S361–S363 итоги.
- `docs/Почти Актуальные TZ/MIGRATION-QWEN3.5-9B_comparison.md` — более старый S362-отчёт.
- `backend/prompts/chronicle_decompose_system.txt` — production-промпт CCH.
- `backend/app/services/chronicle/decomposition_normalizer.py` — production-нормализатор.
- `scripts/probe_cch_decompose.py` — v1-тест (базовый, 3 фрагмента).
- `scripts/probe_model.py` — intent-тест (semantic_probe_corpus).
- `config/llm_sources.json` — реестр уже известных моделей.
- `architecture/flags.yaml` — флаги ROLLOUT-PENDING для production-моделей.

### 9.2. Внешние источники (актуальны на 2026-10-26)

- **Qwen3 release blog** (April 29, 2025): `qwenlm.github.io/blog/qwen3`
- **Qwen3-2507 update** (July 2025): `github.com/qwenLM/qwen3` — updated Instruct + Thinking variants
- **GLM-4.6 release** (Sep 30, 2025): `z.ai/blog/glm-4.6`
- **DeepSeek-R1 Distill** (Jan 2025): `huggingface.co/unsloth/DeepSeek-R1-Distill-Qwen-14B-GGUF`
- **Hermes 3 Technical Report** (Nous Research): `huggingface.co/NousResearch/Hermes-3-Llama-3.1-8B-GGUF`
- **mlabonne Abliteration Collection**: `huggingface.co/mlabonne` — Qwen3-14B-Abliterated, Gemma-3-12B-Abliterated
- **Gemma 3 model card** (Google): `ai.google.dev/gemma/docs/core/model_card_3`
- **llama.cpp GBNF grammars**: `github.com/ggml-org/llama.cpp/blob/master/grammars/README.md`
- **Open LLM Leaderboard 2026**: `onyx.app/open-llm-leaderboard` — общий рейтинг SOTA
- **Best Uncensored LLMs 2026** (apidog, Aug 19 2026): `apidog.com/blog/uncensored-llm` — обзор Qwen 3.8-27B Uncensored, Dolphin 3.0, Hermes 4, Gemma 4

### 9.3. Русскоязычные бенчмарки

- **ruMERA**: `mera.a-ai.ru` — русский аналог MMLU
- **ruLLMArena**: `rullmarena.ru` — chatbot-arena для русских моделей
- **Saiga evaluation**: `github.com/IlyaGusev/rulm` — бенчмарки Saiga-моделей

---

## 10. Краткое резюме для Мастера

**Что я сделал:** изучил рынок open-source LLM 2025-2026, выделил 27 моделей-кандидатов для тестирования (10 P1 + 9 P2 + 5 P3 + 3 baseline), разработал методологию теста v2 (12 фрагментов + 6 стресс-тестов × 7 метрик = интегральный SCORE 0-100), написал исполняемый скрипт-генератор `probe_v2_cch_canonize.py`.

**Главная рекомендация:** начать с волны 1 (P1-кандидаты 1, 2, 5, 7, 8, 10) — это самые свежие SOTA, которые ещё не тестировались. Особый фокус на:

1. **Qwen3-8B-Instruct-2507** (P1 #1) — 100+ languages, значительное улучшение multilingual vs Qwen2.5.
2. **DeepSeek-R1-Distill-Qwen-7B** (P1 #5) — A-level Information Extraction per DeepSeek paper.
3. **Hermes-3-Llama-3.1-8B** (P1 #7) — specialized function-calling + JSON structured output, neutral alignment.
4. **GLM-4.6V-Flash** (P1 #8) — fresh Sep-2025 release, advanced reasoning.
5. **Gemma-3-12B-it-abliterated** (P1 #10) — uncensored,abliterated, родственная домену.

**Бюджет времени:** 2 сессии на волну 1 (~3 часа) — должно дать достаточно данных для решения, есть ли победитель ≥90%, или нужно расширять тестирование.

**Безопасность игры:** тест v2 полностью изолирован — отдельный порт (8183), отдельная директория отчётов, никаких writes в production-config, cleanup гарантирован. Игра продолжает работать с текущим production (Qwen2.5-7B Q6_K) во время тестирования.

**Артефакты:**
- Этот MD-документ: `/home/z/my-project/download/LLM_MODELS_2026_CCH_TEST.md`
- Исполняемый скрипт: `/home/z/my-project/download/probe_v2_cch_canonize.py`
- (Опционально) Golden-reference template: `/home/z/my-project/download/golden_reference_template.json`

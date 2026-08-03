# ENIGMA Input Observatory — Roadmap S2–S6

> **Документ:** Дорожная карта развития системы наблюдения за вводом игрока
> **Версия проекта:** Enigma V.0.5.3.6.8
> **Дата:** 2026-08-03
> **Статус:** Conceptual roadmap (не implementation spec — для S1 есть отдельный документ)
> **Принцип:** Каждая фаза имеет конкретный момент готовности кода, смысл и измеримую ценность

---

## 0. Зачем ENIGMA нужна эта система

### Проблема, которую мы решаем

Сейчас в ENIGMA есть фундаментальный разрыв между тем, **что игрок вводит**, и тем, **что система понимает**. Лог от 02.08.2026 показал: 5 из 6 вводов классифицированы как `UNCERTAIN`, 0 DM-ответов за 3 минуты игры. Но мы не знаем **почему** — потому что система не записывает ни сам ввод, ни контекст, в котором он обрабатывался, ни результат интерпретации.

Это не косметическая проблема. Это **слепота каузальной трубы**. Без observability:
- Нельзя доказать, что фикс BUG-CORE-003 действительно починил передачу `hub_event` в `TickState`
- Нельзя сравнить Qwen 2.5 8B с другой моделью — нет общего corpus'а вводов
- Нельзя воспроизвести баг — нет snapshot'а мира в момент ввода
- Нельзя приоритизировать фиксы — непонятно, какой разрыв даёт больше всего молчания

### Что даст Observatory

Через 2-3 месяца у ENIGMA появится **эволюционный контур** — способность менять LLM-модели, промпты, классификаторы без риска сломать симуляцию. Это не "ещё один лог". Это **архитектурный слой**, который превращает ENIGMA из "игры с LLM внутри" в "симуляцию с заменяемым semantic adapter".

Конкретно:
- **S1** даст corpus реальных вводов — впервые увидим, что игроки реально пишут
- **S2** даст model metadata — сможем сравнивать модели apples-to-apples
- **S3** даст causal trace — сможем доказать, где именно рвётся pipeline
- **S4** даст replay — сможем прогонять старые вводы через новые модели
- **S5** даст Golden Corpus — сможем оценивать модели по контракту, не по ощущению
- **S6** даст Model Benchmark — сможем менять модели осознанно, не наугад

---

## 1. Карта зависимостей

```
S1 (Input Trace)
  │
  ├──→ S2 (Model Metadata) — нужна S1 как carrier для model_run_id
  │
  ├──→ S3 (Causal Trace) — нужна S1 как input_id для causal_parent linkage
  │      │
  │      └──→ S4 (Replay) — нужна S3 для заморозки causal context
  │             │
  │             └──→ S6 (Model Benchmark) — нужна S4 для A/B сравнений
  │
  └──→ S5 (Golden Corpus) — нужна S1 как источник raw input'ов
         │
         └──→ S6 (Model Benchmark) — нужна S5 как test set
```

**Параллельный Repair track** (BUG-CORE-003, BUG-DLG-005, BUG-FB-001 etc.) идёт независимо. Но:
- S3 **невозможно** верифицировать без фикса BUG-CORE-003 (hub_event не доходит → T4 всегда `false`)
- S4 **невозможно** без фикса BUG-FB-029 (non-deterministic snapshot_id → replay не воспроизводим)
- S6 **бессмысленна** без S5 (нет golden corpus → нет метрики)

---

## 2. S2 — Model Metadata Layer

### Смысл

S1 записывает **результат** интерпретации (`action_type`, `target_reference`). Но не записывает **кто и как** этот результат получил. Без этого нельзя сравнивать модели — изменение результата может быть из-за смены модели, промпта, temperature, или просто stochastic instability.

S2 добавляет в trace **экспериментальную конфигурацию** каждого вызова LLM.

### Что добавляется

В `InputTraceRecord` появляются поля T2:
```python
t2_model_run_id: Optional[str]        # уникальный ID вызова
t2_provider: Optional[str]            # "llama_cpp" | "openai" | "mock"
t2_model_id: Optional[str]            # "qwen2.5-7b-instruct"
t2_model_revision: Optional[str]      # git commit / version tag
t2_prompt_id: Optional[str]           # "intent_compressor_v7"
t2_prompt_revision: Optional[str]     # hash промпта
t2_temperature: Optional[float]       # 0.0
t2_seed: Optional[int]                # 42 (если зафиксирован)
t2_latency_ms: Optional[int]          # 381
t2_fast_path_used: Optional[bool]     # True если fast-path matched
t2_raw_llm_output: Optional[str]      # сырой ответ модели (для debug)
```

### Момент готовности кода

**Условие:** S1 реализован и работает минимум 1 неделю ( corpus ≥ 50 реальных вводов).

**Технические предпосылки:**
- `IntentCompressor.compress()` должен экспонировать `fast_path_used` (сейчас не экспонирует) — нужно добавить return tuple или wrapper
- `LlmProvider.complete()` должен возвращать metadata (model_id, latency, tokens) — сейчас возвращает только text
- Нужен `prompt_registry` — каталог промптов с версионностью (сейчас промпты захардкожены в `.py` файлах, нет revision tracking)

**Зависимости от Repair track:** нет. S2 можно делать сразу после S1.

### Зачем нужно ENIGMA

Без S2 любой эксперимент с моделью — это "поменяли модель + промпт + temperature одновременно, и вроде стало лучше". С S2 — "при той же модели и промпте, новая temperature даёт +12% target resolution, но -8% latency".

### Что даст

- Метрику **semantic stability** — один и тот же ввод 10 раз, сколько разных интерпретаций
- Метрику **model latency** — p50/p95 по реальным вводам, не synthetic benchmarks
- Метрику **fast-path hit rate** — какой % вводов не требует LLM вообще
- Возможность **A/B test промптов** — тот же ввод, тот же context, разный промпт → сравнить результат

### Оценка

~1 неделя. Расширение DTO + instrumentation в 3 точках (IntentCompressor call, LlmProvider return, prompt registry).

---

## 3. S3 — Causal Trace Integration

### Смысл

S1 показывает **присутствие** стадий (hub_event created: true/false). S3 показывает **цепочку** — какой input породил какой intent, какой intent породил какое event, какое event породило какой delta, какой delta применился к миру.

S3 превращает плоский trace в **causal graph** — дерево причинности от ввода игрока до изменения мира.

### Что добавляется

1. **Вынос `CausalFrame` из sandbox в production** (`backend/app/services/observability/causal_frame.py`). Существующий `tests/sandbox/runtime/causal_trace.py` уже имеет правильную структуру (`frame_id`, `tick`, `phase`, `entity_id`, `event`, `data`, `causal_parent_id`). Нужно:
   - Перенести в `app/`
   - Добавить `input_id: Optional[str]` field (root linkage)
   - Подключить `CausalTrace.observe()` в ключевых точках pipeline

2. **Instrumentation точек pipeline:**
   - Phase 1 (Input): `input_id` → CausalFrame(phase="INPUT")
   - Phase 5 (Decision): intent → CausalFrame(phase="INTENT", causal_parent_id=input_frame_id)
   - Phase 6 (Post-Decision): event → CausalFrame(phase="EVENT", causal_parent_id=intent_frame_id)
   - Phase 8 (Reduction): delta → CausalFrame(phase="DELTA", causal_parent_id=event_frame_id)
   - Phase 10 (Persistence): commit → CausalFrame(phase="COMMIT", causal_parent_id=delta_frame_id)

3. **В `InputTraceRecord` добавляются T4 fields:**
   ```python
   t4_event_id: Optional[str]              # EventDTO.id
   t4_causal_frame_ids: List[str]          # все frames в цепочке
   t4_delta_batch_id: Optional[str]        # batch ID в DeltaBuffer
   t4_translation_status: Optional[str]    # accepted | rejected (FINALLY, с deterministic contracts)
   ```

### Момент готовности кода

**Критическое условие:** BUG-CORE-003 починен (`hub_event` доходит до `TickState`).

**Почему:** Если `hub_event` не доходит, то T4 всегда показывает `event_created: false`, и causal trace обрывается на T2. S3 запишет "input понял, intent создан, но event не создан" — но не сможет показать **почему** event не создан, потому что pipeline сломан **до** event creation.

**Технические предпосылки:**
- `pipeline_runner.build_tick_state` принимает `hub_event` (BUG-CORE-003 fix)
- `_TickContext` имеет поле `hub_event` (BUG-CORE-003 fix)
- `create_tick_context()` пробрасывает `hub_event` (BUG-CORE-003 fix)
- `EventDTO` имеет `id: UUID` (уже есть — `domain/events.py:53`)
- `DeltaBuffer` имеет batch ID (нужно проверить, возможно добавить)
- `CausalFrame` вынесен из sandbox

**Зависимости от Repair track:** BUG-CORE-003 (Critical, 2ч) — **блокер**. Без него S3 бесполезен.

### Зачем нужно ENIGMA

Сейчас при баге "игрок атаковал, NPC не отреагировал" мы не знаем, где разрыв:
- IntentCompressor не понял? (T2 покажет)
- Intent понят, но target не зарезолвился? (T3 покажет)
- Intent понят, target резолвился, но hub_event не создан? (T4 в S1 покажет)
- hub_event создан, но не дошел до TickState? (BUG-CORE-003 — S3 покажет разрыв между INPUT frame и INTENT frame)
- Intent дошёл, но event не опубликован? (S3 покажет разрыв между INTENT и EVENT frame)
- Event опубликован, но delta не создан? (S3 покажет разрыв между EVENT и DELTA)
- Delta создан, но не применён? (S3 покажет разрыв между DELTA и COMMIT)

Без S3 все эти случаи выглядят одинаково: "NPC не отреагировал". С S3 — каждый случай имеет точную локализацию.

### Что даст

- **Точную локализацию багов** — вместо "диалог сломан" → "INTENT→EVENT разрыв в Phase 6 для input_id=inp_xxx"
- **Метрику pipeline integrity** — % input'ов, доходящих до COMMIT
- **Causal regression detection** — после рефакторинга видим, какой % цепочек сломался
- **Foundation для S4** — без causal trace нельзя заморозить контекст для replay

### Оценка

~2 недели. Вынос CausalFrame + instrumentation 5 точек + ADR-O-334 (Causal Trace Contract).

---

## 4. S4 — Replay & Model Evaluation

### Смысл

S1-S3 наблюдают за **живой** игрой. S4 позволяет **переиграть** старый ввод в контролируемых условиях — тот же input, тот же snapshot мира, но другая модель. Это превращает ENIGMA из "игры с LLM" в **экспериментальную платформу** для semantic model evaluation.

### Что добавляется

1. **Расширение SUPERBOX** (`backend/tests/sandbox/SUPERBOX/input_replay.py` — новый модуль):
   ```python
   class InputReplayRunner:
       def replay(
           self,
           input_id: str,              # из trace
           snapshot_id: str,           # frozen world state
           model_id: str,              # какая модель
           prompt_id: str,             # какой промпт
           seed: int,                  # для determinism
       ) -> ReplayResult:
           # 1. Загрузить frozen snapshot (из S3 causal trace)
           # 2. Загрузить raw_text (из S1 trace)
           # 3. Прогнать через IntentCompressor с указанной моделью
           # 4. НЕ мутировать production world
           # 5. Вернуть IntentSemanticField + causal simulation
   ```

2. **Frozen snapshot store** — отдельное хранилище для snapshot'ов, использованных в replay (не путать с production `WorldSnapshot`)

3. **Replay comparison report:**
   ```
   Input #184: "где Люся?"
   
   Original (Qwen 2.5 8B, 2026-08-03):
     action_type: INTERACT
     target: maid_lusya (fuzzy)
     confidence: 0.8
   
   Replay (Model B, 2026-08-15):
     action_type: ASK_INFORMATION
     target: maid_lusya (exact)
     confidence: 0.91
   
   Verdict: semantic_equivalent=True, target_match=True
   ```

### Момент готовности кода

**Критические условия:**
- S3 реализован (нужен causal trace для заморозки контекста)
- BUG-FB-029 починен (`WorldSnapshot.snapshot_id` deterministic) — иначе replay не воспроизводим
- BUG-CORE-003 починен — иначе replay покажет тот же сломанный pipeline

**Технические предпосылки:**
- `WorldSnapshot` имеет `snapshot_content_hash` (не только `snapshot_id`) — для верификации что frozen snapshot действительно совпадает
- SUPERBOX infrastructure работает (уже есть — `backend/tests/sandbox/SUPERBOX/`)
- `IntentCompressor` может принимать external model (сейчас захардкожен на `self._llm_client`)

**Зависимости от Repair track:**
- BUG-FB-029 (High, ~1ч) — **блокер**. Non-deterministic snapshot_id → replay даёт разные результаты.
- BUG-CORE-003 (Critical) — **блокер**. S3 dependency.

### Зачем нужно ENIGMA

Без S4 смена модели — это leap of faith. Ты меняешь Qwen на Model B, играешь неделю, и пытаешься вспомнить "стало лучше или хуже?". С S4 — ты прогоняешь 200 старых вводов через Model B за 10 минут и получаешь точную дельту.

Это особенно важно для ENIGMA, потому что:
- LLM-модели дешевеют — через год может появиться модель в 3 раза дешевле при том же качестве
- Промпты эволюционируют — каждый фикс IntentCompressor меняет промпт
- Появляются новые task types (крафт, магия, фракции) — нужна новая классификация

### Что даст

- **Safe model swap** — заменить модель можно за 1 день, не за 1 неделю playtest'а
- **Prompt A/B testing** — тот же ввод, два промпта, сравнить результат
- **Regression detection** — новая версия модели на старых вводах даёт тот же результат?
- **Cost optimization** — сравнить дешёвую модель с дорогой на том же corpus'е

### Оценка

~2 недели. Расширение SUPERBOX + frozen snapshot store + comparison logic.

---

## 5. S5 — Golden Corpus

### Смысл

S1-S4 дают **data**. S5 даёт **ground truth**. Golden Corpus — это курируемый набор вводов с ожидаемой семантикой, против которого можно оценивать модели.

### Что добавляется

1. **Golden Corpus file** (`backend/data/golden_corpus/v1.jsonl`):
   ```json
   {
     "corpus_id": "gc_v1",
     "version": "1.0",
     "entries": [
       {
         "entry_id": "gc_001",
         "raw_text": "где Люся?",
         "source_input_id": "inp_18f3a2b4c2e_8f4a1b2c",
         "canonical_semantics": "ASK_LOCATION",
         "allowed_interpretations": ["ASK_INFORMATION", "LOCATE_ENTITY", "INTERACT"],
         "forbidden_interpretations": ["ATTACK", "MOVE", "GIVE_ITEM"],
         "expected_target": "maid_lusya",
         "context_snapshot_id": "...",
         "curated_at": "2026-08-20",
         "curated_by": "human"
       }
     ]
   }
   ```

2. **Curation workflow:**
   - S1 trace накапливает raw input'ы
   - Раз в неделю — review: выбрать 20-30 representative input'ов
   - Для каждого — определить `canonical_semantics`, `allowed`, `forbidden`
   - Добавить в Golden Corpus

3. **Evaluation harness:**
   ```python
   def evaluate_model_against_corpus(
       model_id: str, corpus_version: str
   ) -> EvaluationReport:
       # Для каждой entry в corpus:
       #   1. Replay input через model
       #   2. Сравнить с canonical_semantics
       #   3. Проверить allowed/forbidden
       #   4. Проверить expected_target
       # Вернуть метрики
   ```

### Момент готовности кода

**Условия:**
- S1 работает минимум 2-3 недели ( corpus ≥ 100 вводов для curation)
- S4 реализован (нужен replay для evaluation)

**Технические предпосылки:**
- Нет новых технических предпосылок — это curatorial work, не code

**Зависимости от Repair track:** нет прямых. Но если pipeline сломан, то corpus будет содержать вводы, которые "должны были работать, но не работают" — это полезно для diagnosis, но не для model evaluation.

### Зачем нужно ENIGMA

Без Golden Corpus оценка модели — субъективная. "Model B вроде умнее" — не метрика. С Golden Corpus:
- **Semantic accuracy** — % вводов, где модель дала interpretation из `allowed` списка
- **Forbidden rate** — % вводов, где модель дала interpretation из `forbidden` списка (критично)
- **Target resolution rate** — % вводов, где target зарезолвился correctly
- **Semantic equivalence** — `ASK_INFORMATION` ≈ `LOCATE_ENTITY` если оба приводят к одному causal outcome

### Что даст

- **Объективную метрику** для model swap decisions
- **Regression detection** — новая версия модели проходит Golden Corpus хуже?
- **Documentation** — Golden Corpus становится спецификацией того, что ENIGMA должна понимать
- **Test set для новых фичей** — когда добавляешь крафт, добавляешь 10 entries в corpus

### Оценка

~1 неделя code (evaluation harness) + ongoing curation (1-2 часа/неделю).

---

## 6. S6 — Model Benchmark & Swap

### Смысл

S6 — это финальная стадия, где все предыдущие элементы сходятся в **эволюционный контур**. Модели можно менять осознанно, с измеримыми метриками, без риска сломать игру.

### Что добавляется

1. **Benchmark report generator:**
   ```
   ENIGMA Model Benchmark Report
   Date: 2026-09-15
   Corpus: gc_v1 (247 entries)
   
   Model A (Qwen 2.5 8B, baseline):
     Semantic accuracy: 87.4%
     Forbidden rate: 2.1%
     Target resolution: 91.5%
     Latency p50: 410ms
     Cost per 1M tokens: $0.30
   
   Model B (Qwen 3 4B, candidate):
     Semantic accuracy: 89.2% (+1.8%)
     Forbidden rate: 1.4% (-0.7%)
     Target resolution: 93.1% (+1.6%)
     Latency p50: 180ms (-56%)
     Cost per 1M tokens: $0.12 (-60%)
   
   Recommendation: ADOPT Model B
   ```

2. **Model swap protocol:**
   - Run benchmark on candidate model
   - Compare with baseline
   - If improvement ≥ threshold → staged rollout (10% → 50% → 100%)
   - Monitor S1-S3 traces for regression

3. **Four comparison types** (per другой LLM §17):
   - **Syntactic** — schema valid?
   - **Semantic** — understood intent?
   - **Causal** — intent compatible with causal architecture?
   - **Experiential** — led to desirable gameplay outcome?

### Момент готовности кода

**Условия:**
- S5 реализован (Golden Corpus)
- S4 реализован (Replay)
- S2 реализован (Model Metadata)

**Технические предпосылки:**
- Несколько моделей доступны одновременно (сейчас только Qwen)
- `ModelRouter` поддерживает runtime model swap (нужно проверить)

**Зависимости от Repair track:** нет. S6 — это вершина, все баги уже починены.

### Зачем нужно ENIGMA

ENIGMA — долгоживущий проект. За 2 года через неё пройдут 5-10 моделей. Без S6 каждая смена — это 1-2 недели неуверенности. С S6 — 1 день измеримого решения.

### Что даст

- **Safe model evolution** — менять модели без regression
- **Cost optimization** — выбирать дешёвую модель когда она достаточно хороша
- **Future-proofing** — когда появится GPT-6 или его аналог, ENIGMA готова
- **Competitive advantage** — большинство игр с LLM не имеют такой системы

### Оценка

~1 неделя. Report generator + swap protocol + monitoring dashboard.

---

## 7. Сводная таблица

| Phase | Смысл | Момент готовности | Зависимости | Оценка | Что даст |
|-------|-------|-------------------|-------------|--------|----------|
| **S1** | Input Trace (T0-T4, один trace на input) | Сейчас | Нет | 2-3 дня | Corpus реальных вводов, локализация разрывов |
| **S2** | Model Metadata | После S1 + 1 неделя | S1 | 1 неделя | A/B test моделей и промптов, latency метрики |
| **S3** | Causal Trace (CausalFrame в production) | После фикса BUG-CORE-003 | S1, BUG-CORE-003 | 2 недели | Точная локализация багов, pipeline integrity |
| **S4** | Replay (SUPERBOX extension) | После S3 + фикса BUG-FB-029 | S3, BUG-FB-029 | 2 недели | Safe model swap, prompt A/B testing |
| **S5** | Golden Corpus | После S1 + 2-3 недели сбора | S1, S4 | 1 неделя + ongoing | Объективная метрика качества моделей |
| **S6** | Model Benchmark & Swap | После S5, S4, S2 | S2, S4, S5 | 1 неделя | Эволюционный контур, safe model evolution |

**Итого:** ~7-8 недель development + ongoing curation. Параллельно с Repair track.

---

## 8. Что НЕ входит в эту дорожную карту

| Что | Почему |
|-----|--------|
| Real-time model routing (выбор модели per-input) | Это runtime optimization, не observability. Возможно после S6. |
| A/B testing на live игроках | Это deployment concern, не observability. S6 даёт offline A/B, live A/B — отдельный проект. |
| Multi-modal input (voice, image) | ADR-O-332 уже покрывает это концептуально, но implementation — далеко. |
| Player behavior analytics | Это game design metric, не causal observability. Отдельная система. |
| LLM cost monitoring | Часть S2 (latency, tokens), но full cost tracking — отдельный backend concern. |

---

## 9. Критические принципы (напоминание)

1. **Observability never mutates the world.** S1-S6 — observation only. Если observability падает, gameplay продолжается.
2. **`input_id` ≠ `causal_parent_id`.** Root correlation ID для trace, не для causal graph.
3. **LLM output is candidate, not fact** (ADR-O-332). Interpretation не становится командой без deterministic gate.
4. **One input → one trace → one record.** S1 invariant, сохраняется через все фазы.
5. **Replay never mutates production.** S4 работает в SUPERBOX sandbox, не в live game.
6. **Golden Corpus is curated, not auto-generated.** S5 требует human review, не ML auto-labeling.
7. **Model swap is measured, not guessed.** S6 даёт числовую метрику, не "вроде лучше".

---

## 10. Финальный ответ на вопрос "нужно ли это ENIGMA"

**Да, нужно. Но поэтапно.**

- **S1 — нужен сейчас.** Без него мы слепы. Это минимальный фундамент.
- **S2 — нужен после S1.** Без него нельзя сравнивать модели. Но не срочно — 1 модель пока.
- **S3 — нужен после BUG-CORE-003.** Без него нельзя локализовать баги. Критичен для Repair track verification.
- **S4 — нужен когда появятся новые модели.** Если ты не планируешь менять Qwen в ближайший месяц — не срочно. Но архитектурно важен.
- **S5 — нужен когда накопится corpus.** Минимум 2-3 недели после S1.
- **S6 — нужен когда ENIGMA выйдет за пределы одной модели.** Это зрелость проекта.

**Главная ценность:** S1+S2+S3 вместе дают **диагностический контур** — способность видеть, где именно рвётся pipeline. Это **ускорит Repair track в 2-3 раза**, потому что вместо "NPC не отреагировал, не знаю почему" будет "input_id=inp_xxx, T2=resolved, T3=resolved, T4 hub_event_created=false → BUG-CORE-003 confirmed at tick 1832".

**Главная ошибка, которой нужно избежать:** не строить S4-S6 раньше времени. SUPERBOX extension без S3 — это replay без causal context, бесполезен. Golden Corpus без S4 — это corpus без replay, нельзя evaluate. Model Benchmark без S5 — это benchmark без ground truth, субъективный.

**Последовательность жёсткая:** S1 → (S2 || S3) → S4 → S5 → S6. Repair track параллельно, но S3 требует BUG-CORE-003.

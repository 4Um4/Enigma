```markdown
# ENIGMA — MASTER SPEC (v5.2)
> Единый живой документ проекта. Актуален на момент Intent Exhaustion (R2.1 Phase 3).
> Любой LLM, получивший этот файл, должен понимать: что строится, почему так, и что уже сделано.

---

## 0. ЧТО ЭТО И ДЛЯ КОГО

**ENIGMA (StoryTeller: Digital Master)** — локальная RPG-система, где AI выступает Мастером Игры.
Не симулятор деревни. Не чат-бот с персонажем. Это причинно-следственный стек:
каждое действие игрока меняет числовые веса мира, и мир реагирует — логично, последовательно, без скриптов.

**Целевое ощущение:** настольный D&D, где DM никогда не забывает и не врёт.
NPC помнят, держат обиды, меняются под давлением, перемещаются по расписанию.
Через три игровых дня Торнин может сам прийти мстить — не потому что так написано в скрипте,
а потому что его числовые веса дошли до порога.

**Референс по глубине NPC:** Disco Elysium — биографическая память, эмоциональные нюансы, голоса как силы.

---

## 1. ЖЕЛЕЗО И ОГРАНИЧЕНИЯ (ЖЁСТКИЕ)

| Параметр | Значение |
|---|---|
| GPU | RTX 3070 Ti, 8 GB VRAM |
| CPU | i7-9700F |
| RAM | 16 GB |
| Модель | Gemma-3-12B Q4_K_M (llama.cpp, CUDA) |
| Контекст | ≤ 4096 токенов |
| Масштаб | 10–30 NPC одновременно (потолок ~50) |
| Окружение | Windows, локальный запуск, без облачных API |
| Отладка | `print()` (не `logger.info()` — не видно в uvicorn-консоли) |

---

## 2. ГЛАВНЫЙ ПРИНЦИП (НЕПРИКОСНОВЕНЕН)

```
LLM НЕ ПРИНИМАЕТ РЕШЕНИЯ.
LLM НЕ МЕНЯЕТ СОСТОЯНИЕ.
LLM НЕ ВЫДАЁТ ДЕЛЬТЫ.
```

**LLM = слой вербализации.** Получает `intent` (намерение), `emotion` (эмоция строкой) и минимальный контекст. Возвращает текст. Всё.

**Python = слой интеллекта.** `DecisionHub` считает `score(action)` по числовым весам. Только он решает что произойдёт.

**NPC — система сил, не текстовых рассуждений.** У Торнина есть `pride: 87`, `trust_player: -25`, `fear: 12`. Из этих чисел рождается поведение. LLM лишь озвучивает уже принятое решение.

**Бюджет токенов для LLM:**
- Intent + emotion + fact-hint: ≤ 100 токенов (NPC voice)
- MAJOR NPC контекст: 450–700 токенов
- MINOR NPC контекст: ≤ 180 токенов

**ГЛАВНЫЙ ИНВАРИАНТ СИСТЕМЫ:**
```text
Ни LLM, ни persistence не имеют права вводить новые факты.
LLM → только текст, не структура
Parser → не создаёт сущности
Commitment → не является фактом, только состоянием

```
Data Flow (шаги 1-9):

1. DM System — координатор входа (парсинг, сцена, валидация, участники)
 ├─ DM Router — текст в Event (Этап 1)
 ├─ Scene Builder — R4 Spatial контекст (Этап 2)
 ├─ Validator — фильтр реальности "можно ли?" (Этап 3)
 └─ Participants — выбор NPC из line_of_sight (Этап 4) 

2. Event — валидированный Event уходит в ядро

3. Spatial Filter — PerceptionFilter (кто именно воспринимает из участников)

4. Intent Pool — генераторы (GOAP, LifeEngine, Reaction) создают Intent'ы с параметрами.
   ВНИМАНИЕ: Это Pool (пул кандидатов на ТЕКУЩИЙ тик), а не Queue (накопитель).
   Pool пересоздаётся каждый тик. Он не хранит историю между тиками.
   Это устраняет temporal drift (когда старый intent влияет на новую реальность).

5. DecisionHub — score(action) по весам (профиль + память + эмоции + риск)
   ПРИНЦИП: DecisionHub = чистый SCORER. Он не знает про "планы" или "рутину".
   Он получает список Intent'ов из очереди и считает финальный score для каждого.
   
6. Resolution — бросок кубика смещает ожидаемый результат (±10%)
   
7. State Update — StateApplicator производит дельты (только читает DecisionResult).
   SceneStateManager — единственная точка записи (атомарно применяет дельты).
   StateApplicator НЕ имеет права писать состояние напрямую.

8. World Influence — макро-мир реагирует (фракции, фронты, слухи)
  
9. Verbalization — Структурная вербализация (Вариант D) + Controlled Chaos
   └─ SceneOutcomeBuilder.build() — DecisionResult[] → SceneOutcome (атомарные события с типами)
   └─ Chaos Injection Layer — искажение восприятия (НЕ меняет факты)
      ├─ Perception Noise: perceived_emotion = true_emotion + noise(-0.2..+0.2)
      ├─ Expression Drift: допуск сарказма/усталости в рамках intent
      ├─ Information Loss: скрыть часть событий (filter_by_confidence)
      ├─ Contradiction Allowance: NPC могут противоречить друг другу
      └─ Temporal Noise: лёгкая рассинхронизация реакций (1 тик)
   └─ SceneOutcomeBuilder.build_dm_frame() — SceneOutcome + chaos_profile → DMFrame
   └─ DM LLM — заполняет payload по id:: (НЕ возвращает структуру)
   └─ Python рендеринг → финальный текст (тривиальный split)
   
   ПРИНЦИПЫ:
   - Разделение ДО LLM. Система генерирует структуру → LLM заполняет payload.
   - LLM = noise source (ограниченный канал вариативности), не decision maker.
   - CHAOS_INTENSITY ∈ [0.0..1.0], max_deviation_from_truth <= 15%.
   - Если LLM влияет на intent/state → controlled chaos становится обычным хаосом.

   Трёхслойная архитектура:
   [Truth Layer] DecisionHub → Resolution → State (LLM запрещён)
   [Perception Layer] SceneOutcome → Chaos Layer → DMFrame (LLM искажает)
   [Expression Layer] DMFrame → LLM → Text (LLM генерирует)
```

**Закон системы:** Внешние системы (GOAP, LifeEngine, EventBus) генерируют ActionCandidate. ActionCandidate КРАЙНЕ СТРОГО содержит только что можно сделать. Ноль чисел (никаких priority, score, weight). DecisionHub — единственный, кто имеет право приписать вес кандидату на основе формулы score().

**Правило записи:** `DecisionHub` — read-only. `StateApplicator` — write-only. Нигде больше состояние не меняется.

---

## 4. АРХИТЕКТУРНЫЕ СЛОИ (СТАТУС)

### L0 — FOUNDATION

#### R1 Memory Core ✅ DONE
Трёхслойная память NPC:
- **L1 Numerical** — числовые веса (`trust`, `fear`, `stress`). Только для DecisionHub.
- **L2 Event** — список событий с деградацией (`decay`) и искажением (`distortion`). Передаётся в LLM для диалогов.
- **L3 Identity** — черты (`traits`), кристаллизованные из событий через `ResonanceEngine`.

Tier-система объёма памяти:
- MINOR: 0–2 события
- MAJOR: 5–10 событий + полная структура личности

Файлы: `memory/memory_manager.py`, `memory/layered_memory.py`, `memory/working_memory.py`, `memory/resonance_engine.py`, `memory/importance_engine.py`, `memory/relationship_store.py`, `memory/contradiction_resolver.py`

Write-контракты зафиксированы: NPCPersonality (write: NEVER) · NPCIdentityL1 (write: ONLY MemoryManager) · NPCState (write: ONLY StateApplicator) · EventMemory (write: ONLY MemoryManager)
Подключено: Memory→DecisionHub (relationship_cache), ResonanceEngine→identity_cache, DecisionHub читает NPCIdentityL1.

#### R2 Decision Core ✅ DONE (MIGRATED TO L0/L2)

#### R2.1 Cognition & Planning (FUTURE)
ВНИМАНИЕ: В текущей реализации DecisionHub принимает единый EventContext. Интеграция GOAP и Intent Queue (R10.5) запланирована как адаптация входных данных для DecisionHub, а не замена его формулы score(). Подробности в разделе 10.8.
**Гибридная модель (Вариант C):** GOAP и реактивность сосуществуют через единый язык Intent'ов.

Intent Structure (кандидат в Pool):
    action: строковый идентификатор (MOVE, ATTACK, HIDE)
    priority: базовый вес от генератора (0.0-1.0)
    commitment: инерция намерения (0.0-1.0). GOAP-планы имеют высокий commitment (0.8+), реакции — низкий (0.0-0.3), рутина — средний (0.3-0.5).
    source: "goap", "life_engine", "reaction", "player_event"
    chain_id: ID GOAP-плана (если есть)
    abort_conditions: список условий прерывания (damage_taken, target_lost)
    expiry_tick: тик, до которого intent актуален (защита от залипания)

Commitment Model (критически важно):
    Commitment НЕ живёт в Intent Pool. Он живёт в NPCStateL2 (или состоянии GOAP-планера).
    Commitment передаётся в DecisionHub как множитель: commitment_multiplier = 1.0 + (intent.commitment × INTENT_INERTIA)
    Intent Pool = проекция давления системы в текущий тик. После тика — очищается.
    Это гарантирует: DecisionHub всегда видит ТОЛЬКО актуальных кандидатов.

*DecisionHub* — единственная точка принятия решений. Строго типизирован под чистую 4-слойную модель (NPCProfileL0, NPCStateL2). Основан на Multidimensional Utility AI (отвергнуты FSM и GOAP как избыточные для психологической RPG).    

**DecisionHub Formula (дополненная):**
```
score(intent) = [drive × context_relevance × commitment_multiplier]
- [fear × risk]
+ reactive_urgency
+ opportunity_mod
± noise(10%)
где:
commitment_multiplier = 1.0 + (intent.commitment × INTENT_INERTIA)
reactive_urgency = base_urgency × freshness (exp decay по тикам)
freshness = exp(-0.15 × ticks_since_event)
```

**Защита от доминирования GOAP:**
- **Intent Saturation Penalty:** если тот же `chain_id` используется >3 тиков подряд, score *= 0.9 каждый следующий тик
- **Cognitive Switch Cost:** штраф при резкой смене intent'ов (анти-дребезг)
- **Commitment Decay:** каждый тик без выполнения шага GOAP-интент теряет 10% commitment
- **Intent Exhaustion:** активный штраф при стагнации (intent активен без прогресса)

**Архитектурный контракт:**
- GOAP — только генератор intent'ов (A* планировщик), не исполнитель
- DecisionHub — только scorer, не знает про "планы" или "цели"
- SceneStateManager — единственный владелец состояния

```
Ключевые механики:
- INTENT_INERTIA (0.20): NPC не дребезжит — продолжает начатое действие
- INTENT_EXHAUSTION_RATE (0.08): штраф за стагнацию сверх INTENT_SATURATION_TICKS
- SCORE_NOISE_RANGE (±10%): контролируемый хаос, NPC не детерминирован
- scores_trace: "чёрный ящик" — почему NPC выбрал FLEE вместо ATTACK
- OpportunityEngine: NPC действует проактивно (скрытые атаки, предательство при отсутствии свидетелей)
- WillState.LOYAL блокирует ATTACK — верные NPC не нападают без причины
- stress > 90 → NPC теряет широту и сводится к базовым инстинктам (бегство/наблюдение)

Файлы: npc/decision_hub.py, npc/opportunity_engine.py, npc/reaction_priority.py, npc/threat_assessor.py, npc/npc_cognition.py, npc/psyche_engine.py, npc/resolution_engine.py
Тесты: test_decision_hub_commitment.py (23), test_decision_calibration.py (10), test_decision_pipeline.py (20)
```

#### R3 Verbalization Layer ✅ АРХИТЕКТУРНЫЙ СДВИГ: Структурная вербализация (Вариант D)

**Базовый принцип:** Python = Mind, LLM = Voice. DM = единственный источник речи.

**Ключевой перелом:** Разделение делается ДО LLM, не ПОСЛЕ.
- ❌ НЕ: "LLM генерирует сцену → мы её делим"
- ✅ ДА: "Система генерирует структуру → LLM только озвучивает узлы"

**Вариант D — Structural Verbalization (95-99% надёжность):**

Ключевой принцип: **LLM не возвращает структуру. LLM возвращает только payload внутри уже заданной структуры.**
Структура = 100% Python. LLM = только текст. Парсинг = тривиальный split по id::

**Шаг 1:** SceneOutcomeBuilder (Python, 0ms) — формирует структуру с пустыми payload (массив dict с type, id, payload="").

**Шаг 2:** DM LLM (1 вызов) — промпт: "Заполни payload для каждого блока. НЕ меняй структуру. Ответ — список payload по id."

**Шаг 3:** LLM возвращает только текст: `1:: Ты подходишь к стойке...` и `2:: "Эль? Две серебряные монеты..."`

**Шаг 4:** Python собирает финальную структуру — тривиальный split по `id::` (нулевой риск парсинга)

**Почему не JSON от LLM:**
- JSON от LLM: 40-60% надёжность
- :::markup: 80-90% надёжность
- ID→payload mapping: **95-99%** надёжность

**Вывод:** Не улучшай парсинг. Убери необходимость в нём.
```

**Вторичные эффекты (важнее самой задачи):**
- Управление сценой: скрывать части, менять POV, cinematic cuts
- Мульти-NPC без коллизий: кто говорит, кто действует, кто наблюдает
- Будущие системы: TTS по npc_id, анимации по type, структурированное логирование

**Защита от потери голосов (Voice Flattening):**
- Voice Constraints: TONE, STYLE, LEXICON — ограничения, а не просьбы
- Анти-гладкость: `ALLOW: interruptions, incomplete sentences, conflicting reactions`
- Запрет: `DISALLOW: perfect coordination between NPCs`

**Сохранённые контракты:**
- VerbalizationCore — frozen dataclass (whitelist: intent, target, scene)
- BehaviorMode: STRICT/FLEXIBLE/REACTIVE/SILENT
- Semantic Conflict Resolution: emotion/scene > intent > constraint

**Артефакты (Шаги 1-2 завершены):**
- `SceneOutcomeBuilder` — компрессор: DecisionResult[] → SceneOutcome (0ms)
- `SceneOutcome` — frozen: salience, tension (с sources), visibility (с confidence), latent signals
- `DMFrame` — перцептивная модель: фокус (≤2 NPC), фон, скрытые сигналы
- `SceneToDMAdapter` — единый вход: SceneOutcome или Legacy Dict → DMFrame
- `LatentSignal` — типизированный контракт (TRAUMA, WILL_OVERRIDE, INTEGRITY_CRACK)

**Формулы:**
- `salience = proximity(0.30) + emotional_intensity(0.30) + action_relevance(0.25) + tier(0.15)`
- `tension.level` — агрегация stress_delta + fear_delta, spike при травме/смене воли

**Controlled Chaos Layer:**
- `CHAOS_INTENSITY ∈ [0.0..1.0]` — глобальный параметр стохастики
- `max_deviation_from_truth <= 15%` — жёсткий предел искажения
- Распределение влияния: Selection(40%), Interpretation(30%), Expression(20%), Timing(10%)
- `perceived_emotion = true_emotion + noise(-0.2..+0.2)` — искажение восприятия
- `chaos_profile` в DMFrame: {ambiguity, emotional_noise, info_loss, contradiction}
- Критические зоны роста: Social scenes (+90%), Tension (+75%), Break System (+95%)
- Где разрушает систему: факты ("ударил" → "почти ударил"), причинность (intent через речь)

**R3_DIRECT_MODE (feature flag):**
- `True`: DecisionResult[] → SceneOutcome → DMFrame → dm_agent → 1 LLM
- `False`: legacy (npc_agent → npc_result → dm_agent) — полный откат
- Текущий статус: ⚠️ DMFrame формируется, но npc_agent ВСЁ РАВНО вызывается после (баг #1)

**Вероятностная оценка стратегий:**
| Подход | Итог |
|--------|------|
| Без chaos | 60% «умно, но мёртво» |
| Свободный LLM | 70% хаос/баги |
| Controlled Chaos | **85% живой мир + стабильность** |

Файлы: verbalization/verbalization_context.py, verbalization/scene_outcome_builder.py, verbalization/scene_to_dm_adapter.py, verbalization/prompt_loader.py, game_loop.py, dm_agent.py, prompts/npc_system.txt
Тесты: 79 (R3) + 32 (SceneOutcome) + 17 (DMFrame) + 23 (Adapter) + 29 (регрессии) = **180 тестов**

---

### L0.5 — ПЕРСИСТЕНТНОСТЬ

#### R1.8 Iron-Man Persistence PARTIAL
- Никаких слотов сохранений. Auto-save при смене локации или выходе.
- `Inspiration` (переброс кубика) — только за Critical Success в сложных заявках.

Файлы: `scene_state_manager.py`, `campaign_state_service.py`, `player_session_service.py`, `scene_change.py`

---

### L1 — ПРОСТРАНСТВО ✅ DONE (R4 полностью закрыт)

#### R4 Spatial System ✅ РАБОТАЕТ
Полная пространственная симуляция сцены:

**Исправлено:** `distance_to_player` теперь корректно передаётся из экстрактора в SceneContext. Расстояния реальны (Торнин=4.0м, Люся=2.5м, Тень=4.61м).

**R4.1–4.2 LocationGraph + LocationNode**
- Граф узлов с XY-координатами, связями, родителями/детьми
- Кэш графов (`_GRAPH_CACHE`) — чтение JSON только при первом обращении
- `invalidate_graph_cache()` для ручного сброса
- Валидация симметрии связей при загрузке

**R4.3 LocalSpace — расстояния**
- `resolve_distance_between_entities()` — граф + local XY смещение
- Batch-режим: `graph=` параметр — один граф на весь цикл NPC
- Разные локации → автоматически `999.0` (недостижимо)

**R4.4 Environment Modifiers (живые)**
- `_derive_environment_modifiers()` — вычисляется из `time_variants` + типа локации
- `_effective_modifiers()` — динамическая плотность: +0.05 за каждого NPC в сцене
- `line_of_sight()` — LOS с учётом освещения, плотности, опасности
- `sound_reach()` — радиус звука (шум усиливает, плотность гасит)
- `sound_bleeds_to_adjacent()` — громкий звук просачивается в соседние локации через `connected_locations`

**R4.5 Scene Extraction**
- `extract_scene_for_npc()` — snapshot: кто рядом, где игрок, доступные действия
- `PERCEPTION_RADIUS`: minor=3м, major=15м (lazy evaluation — защита от фарма)
- Стелс: `visible=False` — NPC невидим пока кто-то не подойдёт вплотную (≤1.5м)
- Игрок включён в snapshot с расстоянием и LOS-флагом

Файлы: `npc/location_graph.py`, `npc/spatial_runtime.py`, `npc/perception_filter.py`, `action/player_target_extractor.py`, `scene_state_manager.py`, `data/locations/location_templates.json`

Тесты: 35 тестов (test_spatial_runtime_r4.py × 16, test_perception_filter.py × 15, test_location_graph_r4.py × 3, test_player_target_extractor_r4.py × 1)

---

### L2 — МЕХАНИКА ИСХОДОВ

#### R5 Resolution Layer ✅ DONE
- Полная реализация Gap System: `gap = actual_success - expected_success`
- `apply_gap_learning()` — gap → дельты (стресс, трейты)
- Файлы: `npc/resolution_engine.py`
- Тесты: `test_r2_r5_math.py` (покрытие gap, surprise, outcome bands)

Файлы: `game/combat_math.py`, `game/physics_validator.py`, `action/processor.py`, `npc/math_utils.py`

---

### L3 & L3.5 — АВАТАР И ОГРАНИЧЕНИЯ

#### R6 Character Constraint PARTIAL
- ✅ `CharacterService` — базовый CRUD персонажей
- ❌ **R6.4 Ego Resistance — НЕ РЕАЛИЗОВАН**
  - Нет проверки `intent` против профиля игрока
  - Нет `affinity()` функции (только заглушка в ResolutionEngine)
  - Нет штрафов за нарушение роли

Файлы: `character_service.py`, `npc/npc_state.py`, `npc/behavior_mask.py`, `npc/life_engine.py`

---

### L4 — СОЦИАЛЬНАЯ СЕТЬ

#### R7 Social System PARTIAL
- `RelationshipMatrix` (NPC↔NPC)
- Распространение слухов по графу связей

Файлы: `memory/relationship_store.py`, `memory/memory_manager.py`, `npc/opportunity_engine.py`

---

### L5 — СЛОМ

#### R8 Break System ✅ DONE
- **Behavior Masks:** `FAKE_SUBMISSION`, `BETRAYAL`, `COLLAPSE`
- **Pressure Model:** `fear + stress + failures - support`
- **BreakProgressEngine:** стадии слома (resistance → cracks → rationalization → adaptation → deformation)
- **OpportunityEngine:** разблокировка скрытых интентов для сломленных NPC
- Файлы: `npc/behavior_mask.py`, `npc/break_progress_engine.py`, `npc/opportunity_engine.py`
- Тесты: `test_behavior_mask_r62.py`, `test_break_progress_engine_r64.py`

---

### L6 — МИР

#### R9 World Director PARTIAL
- ✅ **Онтология мира** — три класса сущностей:
  - `PHYSICAL_OBJECT` → `scene_state["objects"]` + `owner` (материальные предметы)
  - `BODY_TRAIT` → `NPCIdentityL1` / `NPCState` (шрамы, телосложение)
  - `ROLE_MARKER` → `BehaviorMask` / `LifeEngine tags` (статусные маркеры)
- ✅ **Двухфазная инстанциация (MVP):**
  - Фаза 1 (Semantic): JSON → `NPCProfileL0.carried_objects` (явный список)
  - Фаза 2 (World): `carried_objects` → `scene_state["objects"][owner=npc_id]`
- ✅ **Разделение:** `carried_objects` (seed для материализации) vs `visible_markers` (LLM-контекст)
- ✅ `world_ontology.is_physical_object()` — валидация перед записью в сцену
- ❌ **Фронты (Fronts) — НЕ РЕАЛИЗОВАНЫ**
- ❌ **Фракции (Factions) — НЕ РЕАЛИЗОВАНЫ**
- ❌ **Экономика (Scarcity) — НЕ РЕАЛИЗОВАНА**
- ❌ **Автономные события — НЕ РЕАЛИЗОВАНЫ**
- ❌ **EPL (Event Processing Language)** — цель будущей архитектуры, сейчас не трогаем
- Файлы: `world/world_ontology.py`

---

### L8.5 — GAME LOOP

#### R13 Tick-Based Engine PARTIAL
- Диалог = 1 тик. Перемещение/отдых = X тиков.
- Мир меняется асинхронно во время отдыха игрока
- NPC перемещаются по расписанию (`life_engine.py`) независимо от игрока
- ✅ LifeEngine.tick() подключён в пайплайн
- ✅ SceneChange применяются через SceneStateManager.apply_changes()
- ✅ Spatial данные корректны (расстояния 2.5-4.6м)

Файлы: `game_loop.py`, `world_scheduler.py`, `npc/life_engine.py`

---

### L9 — FRONTEND & UX

#### R14 UI PARTIAL
- **Fog of War:** игрок видит только свои статы. Цифры NPC скрыты.
- **Иллюзия D20:** математика [0..100] → UI показывает 1-20.
- **Latency Masking:** анимация "NPC думает..." скрывает задержку LLM.
- Имена NPC скрыты (???) пока NPC не представится.

Файлы: `frontend/ui/index.html`

---

### L10 — DEVTOOLS

#### R15 God Mode PARTIAL
- Скрытая консоль (`~`) для разработчика: сырые веса и матрица решений
- `Central Math Config` — единый файл всех формул (защита от хардкода)

---

## 5. ТЕКУЩАЯ СТРУКТУРА ФАЙЛОВ (РЕАЛЬНАЯ)

```
backend/
├── app/
│   ├── main.py
│   ├── agents/
│   │   ├── dm_agent.py               # [LEGACY] — убрать прямую генерацию дельт
│   │   ├── npc_agent.py              # ★ R3 VerbalizationContext (react() удалён)
│   │   ├── rules_agent.py
│   │   └── world_sim_agent.py
│   ├── api/
│   │   ├── routes.py                 # REST
│   │   ├── routes_stream.py          # SSE
│   │   └── routes_debug.py
│   ├── core/
│   │   ├── config.py
│   │   ├── settings_dm/npc/rules/world.py
│   │   └── runtime_config.py
│   ├── models/
│   │   ├── schemas.py
│   │   └── npc_profile.py            # ★ L0 типы: NPCProfileL0, PsycheBase, InventoryProfile, SpatialSnapshotR4
│   └── services/
│       ├── game_loop.py              # ★ Координатор тайминга (run_turn / stream_turn)
│       ├── game_loop_builder.py      # ★ Сборка GameLoop (вызывается из main.py startup)
│       ├── game_loop_accessor.py     # ★ Depends-доступ к GameLoop через app.state
│       ├── scene_state_manager.py    # Source of Truth сцены (Требует рефакторинга под L0-L2)
│       ├── scene_change.py
│       ├── campaign_state_service.py
│       ├── action/
│       │   ├── player_target_extractor.py  # R4 ✅
│       │   ├── object_resolver.py       # ★ Активен (pymorphy3 лемматизация)
│       │   ├── dm_orchestrator.py    # ★ АКТИВЕН (Единая точка входа)
│       │   ├── dm_router.py          # ★ АКТИВЕН (Этап 1)
│       │   └── dm_scene_builder.py   # ★ АКТИВЕН (Этапы 2-3)
│       ├── events/
│       │   ├── event_bus.py
│       │   └── event_types.py
│       ├── game/
│       │   ├── combat_math.py
│       │   ├── physics_validator.py
│       │   └── sandbox_handler.py
│       ├── memory/
│       │   ├── memory_manager.py     # R1 ✅ — подключён к DecisionHub и NPCIdentityL1
│       │   ├── layered_memory.py
│       │   ├── working_memory.py
│       │   ├── resonance_engine.py   # ✅ — подключён через MemoryManager.apply_identity_weights()
│       │   ├── importance_engine.py
│       │   ├── relationship_store.py
│       │   └── contradiction_resolver.py
│       ├── npc/
│       │   ├── decision_hub.py       # ★ Ядро интеллекта [✅ МИГРИРОВАН НА L0/L2]
│       │   ├── state_applicator.py   # ★ Единственная точка записи [✅ МИГРИРОВАН НА L0/L2]
│       │   ├── npc_state.py          # ★ ЕДИНЫЙ ИСТОЧНИК ТИПОВ — NPCPersonality(L0), NPCIdentityL1(L1), NPCState(L2)
│       │   ├── life_engine.py
│       │   ├── location_graph.py     # R4 ✅
│       │   ├── spatial_runtime.py    # R4 ✅
│       │   ├── npc_loader.py         # ★ Адаптер миграции (JSON -> L0 Profile)
│       │   ├── perception_filter.py  # R4 ✅
│       │   ├── perception_engine.py
│       │   ├── npc_cognition.py
│       │   ├── psyche_engine.py
│       │   ├── behavior_mask.py      # R8 ✅
│       │   ├── break_progress_engine.py # R8 ✅
│       │   ├── opportunity_engine.py # R2 ✅
│       │   ├── reaction_priority.py
│       │   ├── resolution_engine.py  # R5 ✅
│       │   ├── threat_assessor.py
│       │   └── math_utils.py
│       ├── scene/
│       │   └── narrative_extractor.py
│       ├── simulation/
│       │   └── world_state.py
│       ├── world/
│       │   └── world_ontology.py       # Онтологический контракт: PHYSICAL_OBJECT_TYPES, is_physical_object()
│       ├── state/
│       │   ├── context_builder.py    # ★ Активен (build_context, patch_scene_state)
│       │   ├── persistence_port.py   # ★ Абстрактный порт сохранения (Пробой 7)
│       │   └── json_persistence_adapter.py  # ★ JSON реализация PersistencePort
│       ├── verbalization/
│       │   ├── verbalization_context.py # R3 ✅
│       │   ├── scene_outcome_builder.py # ★ SceneOutcome, DMFrame, Salience, Tension
│       │   ├── scene_to_dm_adapter.py   # ★ Единый входной контракт для DM
│       │   └── prompt_loader.py
│       └── llm/
│           ├── llama_cpp_provider.py
│           ├── provider_manager.py
│           └── factory.py
└── data/
    ├── campaigns/demo-campaign/
    ├── locations/location_templates.json  # R4 ✅
    ├── npcs/major_npcs.json              # [LEGACY FORMAT] — Требует очистки от memory_trace
    └── logs/
```

---

## 5.5 АРХИТЕКТУРНОЕ ЯДРО (Планируемое)

```
enigma/
├── start_enigma.bat                 # ЕДИНАЯ ТОЧКА ВХОДА
├── launcher.py                      # (Будущее) Нативное окно
│
├── docs/                            # Концептуальная документация
│   ├── architecture_v2.md           # Принцип "Python=Mind, LLM=Voice"
│   ├── break_system.md              # Механика деградации
│   └── memory_tiers.md              # Спецификации слоев L1-L3
│
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI + startup (запускает GameLoop)
│   │   │
│   │   ├── api/                     # ТРАНСПОРТНЫЙ СЛОЙ (Только передача данных)
│   │   │   ├── routes.py            # REST (run_turn)
│   │   │   ├── routes_stream.py     # SSE (stream_turn)
│   │   │   └── routes_debug.py      # R15 DevTools (God Mode)
│   │   │
│   │   ├── core/                    # L0.5 — БАЗОВЫЕ МЕХАНИЗМЫ (Ничего не знают об игре)
│   │   │   ├── event_bus.py         # Шина событий (Player Action -> System)
│   │   │   ├── constants.py         # R15.2 Central Math Config (Единые веса/капы)
│   │   │   └── security.py          # Анти-спам, анти-эксплойт
│   │   │
│   │   ├── models/                  # ЧИСТЫЕ ДАННЫЕ (Pydantic/Dataclasses)
│   │   │   ├── npc_state.py         # R2.1 NPCState (динамика)
│   │   │   ├── personality.py       # L0 Core & L1 Identity (Immutable)
│   │   │   ├── decision.py          # R2 Контракт DecisionResult
│   │   │   ├── spatial.py           # R4 Модели локаций и координат
│   │   │   └── schemas.py           # Общие DTO для API
│   │   │
│   │   ├── services/                # ЯДРО ЛОГИКИ (Слои R1-R9)
│   │   │   │
│   │   │   ├── game_loop.py         # ★ КООРДИНАТОР ТАЙМИНГА (Вызывает DM, крутит тики R13)
│   │   │   │
│   │   │   ├── dm/                  # ★★★ DM SYSTEM (Этапы 1-9 из вашего плана)
│   │   │   │   ├── dm_orchestrator.py   # Главный фасад (Собирает пайплайн)
│   │   │   │   ├── dm_router.py         # Этап 1: Парсинг ввода -> Event
│   │   │   │   ├── dm_scene_builder.py  # Этап 2: R4 Spatial контекст
│   │   │   │   ├── dm_validator.py      # Этап 3: Фильтр реальности (можно ли?)
│   │   │   │   ├── dm_flow.py           # Этап 6: Очередность (Initiative)
│   │   │   │   └── dm_aggregator.py     # Этап 8: Сборка финального нарратива
│   │   │   │
│   │   │   ├── input/               # ОБОЛОЧКА ДЛЯ DM ROUTER (Бывший classifier)
│   │   │   │   ├── intent_parser.py # Перевод текста в PlayerIntent
│   │   │   │   └── patterns/        # YAML с русскими фразами (Data-driven)
│   │   │   │       ├── combat.yaml
│   │   │   │       └── social.yaml
│   │   │   │
│   │   │   ├── npc/                           # R2 — ЯДРО ИНТЕЛЛЕКТА (Python считает)
│   │   │   │   ├── decision_hub.py            # [ЦЕНТР] Формула score()
│   │   │   │   ├── state_applicator.py        # [ТОЧКА ЗАПИСИ] Атомарные изменения
│   │   │   │   ├── perception.py              # Фильтр релевантности (кто видит)
│   │   │   │   ├── cognition/                 # НОВЫЙ: Унификация источников Intent
│   │   │   │   │   ├── intent_queue.py        # Приоритетная очередь (все источники равны)
│   │   │   │   │   ├── intent_generator.py    # Фасад LifeEngine vs GOAP vs Reaction
│   │   │   │   │   ├── goap_intents.py        # GOAP как генератор (не исполнитель)
│   │   │   │   │   ├── crisis_detector.py     # Триггер GOAP-режима
│   │   │   │   │   └── priority_calculator.py # Saturation penalty, decay
│   │   │   │   └── engines/                   # СПЕЦИАЛИЗИРОВАННЫЕ ВЫЧИСЛИТЕЛИ
│   │   │   │       ├── break_engine.py        # R8 Механика слома воли
│   │   │   │       ├── memory_engine.py       # R1 Деградация и искажение
│   │   │   │       ├── dice_engine.py         # R5 Стохастическое смещение
│   │   │   │       ├── social_engine.py       # R7 Связи и слухи
│   │   │   │       └── threat_assessor.py     # Оценка рисков
│   │   │   │
│   │   │   ├── resolution/          # R2.5 + R5 — МЕХАНИКА ИСХОДОВ (Бывший combat_math)
│   │   │   │   ├── action_resolver.py   # Диспетчер: куда отправить Event
│   │   │   │   ├── dnd_5e/              # ★ ПРАВИЛА D&D (Инкапсулированы!)
│   │   │   │   │   ├── core.py              # Броски D20, преимущества
│   │   │   │   │   ├── spell_engine.py      # Магия
│   │   │   │   │   ├── rest_engine.py       # Долгий/короткий отдых
│   │   │   │   │   └── economy.py           # Торговля и цены
│   │   │   │   └── sandbox/             # Физика и окружение
│   │   │   │       ├── physics.py           # Взаимодействие с объектами
│   │   │   │       └── environment.py       # Огонь, вода, шум
│   │   │   │
│   │   │   ├── state/                # R4 — УПРАВЛЕНИЕ МИРОМ (Source of Truth для сцены)
│   │   │   │   ├── scene_state_manager.py  # Холдер состояний всех NPC в сцене
│   │   │   │   └── world_director.py       # R9 Фронты, давление, макро-события
│   │   │   │
│   │   │   ├── memory/               # R1 — ПАМЯТЬ
│   │   │   │   ├── working_memory.py      # Краткосрочная (20 событий)
│   │   │   │   ├── relationship_store.py  # Матрица отношений
│   │   │   │   └── long_term_store.py     # (Будущее) SQLite/Факты
│   │   │   │
│   │   │   └── verbalization/       # R3 — СЛОЙ ГОЛОСА (Режиссура сцены)
│   │   │          ├── prompt_factory.py      # Сборка промптов (NPC + DM)
│   │   │          ├── context_builder.py     # Формирование VerbalizationContext
│   │   │          ├── scene_outcome_builder.py # DecisionResult[] → SceneOutcome → DMFrame
│   │   │          ├── scene_to_dm_adapter.py   # Единый вход (new/legacy) → DMFrame
│   │   │          └── llm_client.py          # Адаптер (llama.cpp/vLLM)
│   │   │
│   │   └── knowledge/               # PHASE 2 — PDF ЗАГРУЗЧИК (Вне логики)
│   │       ├── pdf_loader.py
│   │       └── rag_index.py
│   │
│   └── data/                         # PERSISTENCE LAYER (Хранилище)
│       ├── campaigns/                # Настройки кампаний
│       ├── npc_registry/             # Дампы личности (Immutable JSON)
│       ├── locations/                # Графы локаций (R4)
│       ├── world_state.json          # Глобальный стейт (R9)
│       └── logs/                     # Логи для дебага
│
└── frontend/                         # UI / UX LAYER (R14)
    ├── ui/index.html                 # Точка входа
    ├── assets/                       # Пиксель-арт, текстуры
    ├── map/                          # Модуль "Карты мародёров"
    └── terminal/                     # Диалоговое окно
```

---

## 6. РЕЕСТР КРИТИЧЕСКИХ УЯЗВИМОСТЕЙ

*Игнорирование любого пункта ломает фундаментальный опыт игры.*

### 1. Утечка логики в StateApplicator
Симптом: логика принятия решений просачивается в модуль записи.
Правило: StateApplicator получает готовую дельту из DecisionHub. Сам не считает. Строго работает с NPCStateL2, не имея доступа к профилю L0.

### 2. Пробой Fog of War через LLM ✅ МИТИГИРОВАН
**Симптом:** LLM получает числа (`stress: 0.85`) вместо строк (`"полностью сломлен"`).
**Правило:** жёсткая фильтрация промптов. Только `intent` + эмоциональный фон.
**Что ломает:** NPC начинает говорить "мой стресс 85%" — глубокая симуляция превращается в таблицу.
**Статус:**
- `_sanitize_verbalization_core()` в `prompt_loader.py` — фильтрует числа, дельты, DecisionHub internals, системные теги
- `VerbalizationCore` (whitelist dataclass) — смысл формируется ДО текста, только 3 поля: intent, target, scene
- Секционные лимиты: core(300), voice(150), emotion(100), hints(200), bio(500) символов
- NPC системный промпт вынесен в чистый `npc_system.txt` (без комментариев кода)
- DM промпт больше не попадает в NPC контекст
- Покрыто тестами: `TestPromptMustNotContain` (3), `TestTokenBudget` (3), `TestFailureModes` (4), `TestVerbalizationCoreContract` (8)

### 3. Отсутствие Gap System
**Симптом:** провал/успех броска не оставляет следов.
**Правило:** обязательно считать `actual_outcome - expected_success`. Разница → травмы и черты.
**Что ломает:** игра линейна, исчезает "рост через боль" и непредсказуемость.

### 4. Игнорирование Ego Resistance
**Симптом:** игрок меняет поведение как перчатки без штрафов.
**Правило:** проверять `intent` против профиля игрока перед отправкой в DecisionHub.
**Что ломает:** выбранная роль теряет вес, игра превращается в sandbox без последствий.

### 5. Замороженный мир без игрока
**Симптом:** NPC стоят на месте пока игрок отдыхает.
**Правило:** принудительный прогон тиков макро-событий во время отдыха.
**Что ломает:** мир кажется декорацией. Кампания теряет давление и реализм.

### 6. Спам-эксплойт (слом NPC)
**Симптом:** игрок повторяет одно действие → NPC ломается за 3 хода.
**Защита:** динамические шкалы сопротивления, нелинейная стоимость повторений.
**Реализовано:** `_effective_modifiers()` — динамическая плотность от числа NPC в сцене.

### 7. Кубиковый спам
**Симптом:** многократные попытки броска гарантируют успех.
**Защита:** штрафы за повторные броски, ограничение откатов.
**Статус:** не реализовано.

### 8. Voice Flattening (размытие голосов NPC)
**Симптом:** Все NPC начинают говорить языком DM. Теряется индивидуальность (Торнин звучит как Борко).
**Правило:** DM получает не описание голоса, а **Voice Constraints** (TONE, STYLE, LEXICON). Это ограничения, а не предложения.
**Защита:** 
- Структурный сигнал: `TONE: HARSH` в developer message (а не "Торнин грубый" в тексте)
- Анти-гладкость: явное разрешение в промпте на прерывания и противоречия между NPC
- Если Voice Constraints нарушаются → текст режется пост-процессором (Фаза 3 из Semantic Determinism)

### 9. Frequency Dominance (доминирование GOAP)
**Симптом:** GOAP-планы системно выигрывают у реактивности из-за стабильной генерации intent'ов каждый тик, в то время как реакции спорадичны.
**Защита:** 
- `freshness_decay` для reactive_urgency (экспоненциальное затухание)
- `intent_saturation_penalty` (штраф за залипание в одном chain_id)
- `intent_exhaustion` (штраф за стагнацию без прогресса)
- Кап частоты генерации GOAP (не чаще 1 раза за тик)

### 10. Unprovoked Hostility — ЗАКРЫТ
**Симптом:** NPC атакует или предупреждает при нейтральном входе.
**Решение:** provocation_gate (−0.54 за отсутствие провокации).
**Статус:** ✅ ЗАКРЫТ — Торнин теперь говорит "Заработать? Помои убери..." вместо атаки. Остаточный риск: контекст-релевантность (Баг B) — отдельная задача.

### 11. Silent NPC Drop — ЛОЖНАЯ ТРЕВОГА
**Симптом:** PERCEPTION_FILTER находит NPC, но [VERBALIZE] не появляется.
**Диагноз:** Не баг. NPC с `intent=idle` молчат по контракту — лог `[VERBALIZE-DROP] intent=idle (silent)` подтверждает.
**Статус:** ✅ ЗАКРЫТ — добавлен диагностический лог для отслеживания.

### 12. Wrong Target Response — ИСПРАВЛЕН
**Симптом:** "Подойти к Люсе и спросить про Торнина" → отвечал Торнин (нашёлся первым).
**Причина:** `break` после первого совпадения в экстракторе — Люся никогда не проверялась.
**Решение:** Собираем всех кандидатов, сортируем по позиции в тексте → выбираем ближайшего к началу.
**Статус:** ✅ ЗАКРЫТ — позиционная сортировка кандидатов.

### 13. Stale Scene Cache (грязный рестарт)
**Симптом:** После перезапуска — старые объекты, сломанная мебель. campaign_state.json накапливает мусор.
**Правило:** Должен быть механизм чистого старта (runtime reset без затирания профилей).
**Статус:** ✅ МИТИГИРОВАН — reset_campaign.bat (сбрасывает runtime-стейт, сохраняет профили).

### 14. Event Parser Leak (реплики NPC парсятся как действия) ✅ ЗАКРЫТ
**Симптом:** Реплика "Эль? Две серебряные..." → объект `эль_tornin_t0_b98f` с raw_name: 'поднимает взгляд "эль'.
**Причина:** NarrativeExtractor нарушал фундаментальный контракт — создавал объекты из текста DM (new_objects).
**Следствие:** Мусорные объекты попадают в контекст DM → галлюцинации ("Эль — подобран"), дубли подносов.
**Правило:** TEXT→ENTITY запрещён. NarrativeExtractor только обновляет состояния существующих объектов, никогда не создаёт новые (new_objects = [] всегда). Новые объекты — только через carried_objects или явные действия игрока.
**Решение:** 
- Идиомный блок-лист перед принятием триггера ("поднимает взгляд" ≠ "take")
- Хирургическое решение: new_objects заблокирован на уровне NarrativeExtractor
**Статус:** ✅ ЗАКРЫТ — баг #2 в 8.5.
### 15. Truth-Perception Boundary Collapse
**Симптом:** LLM искажает факты ("ударил" → "почти ударил") или меняет intent через речь.
**Правило:** LLM может влиять только на perception layer (как выглядит), не на reality layer (числа, факты, intent'ы).
**Следствие:** Если граница размыта → controlled chaos превращается в обычный хаос.
**Защита:**
- CHAOS_INTENSITY жёстко ограничен (max_deviation_from_truth <= 15%)
- Факты проходят мимо LLM (DecisionHub → State напрямую)
- LLM получает только DMFrame (уже искажённую проекцию, не оригинал)
**Статус:** 📋 Зафиксирован — Controlled Chaos Layer спроектирован с учётом этого риска.

### 16. Commitment Persistence Bug (будущий)
**Симптом:** NPC после рестарта продолжает мёртвый GOAP-план с высоким commitment'ом без причины.
**Правило:** Commitment не переживает рестарт. Хранить не commitment, а intent_persistence_score с decay при загрузке.
**Статус:** 📋 Зафиксирован — Фаза 2.2 в дорожной карте.

---

## 7. ПРАВИЛА РАЗРАБОТКИ (ДЛЯ LLM И ЧЕЛОВЕКА)

1. **Один шаг = одно изменение системы.** Не прыгать между модулями.
2. **Перед изменением** — анализ влияния на другие части.
3. **Никогда не запрашивать файл целиком** без обоснования. Точечные команды PowerShell.
4. **Формат изменений:** БЫЛО / СТАЛО / ИЗМЕНЕНИЕ (что, причина, влияние).
5. **Типизация обязательна.** `typing`, аннотации входов и выходов.
6. **Комментарии на русском языке** — объясняют ЗАЧЕМ, не ЧТО.
7. **Временные решения маркировать:** `# TODO: временная заглушка`.
8. **Каждые 5 шагов:** проверка связности, дублирования, утечки ответственности.
9. **Магические значения запрещены.** Все константы в конфиг.
10. **Тест после каждого изменения.** Без тестов — нет уверенности.

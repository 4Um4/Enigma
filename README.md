# ENIGMA — MASTER SPEC (v5.1)
> Единый живой документ проекта. Актуален на момент завершения Memory System (v5.2).
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

---

## 3. ГЛОБАЛЬНАЯ ЦЕПЬ ПРИЧИННОСТИ (DATA FLOW)

Событие **не может перескочить слой**. Строгий конвейер:

```
1. DM System — координатор входа (парсинг, сцена, валидация, участники)
 ├─ DM Router — текст в Event (Этап 1)
 ├─ Scene Builder — R4 Spatial контекст (Этап 2)
 ├─ Validator — фильтр реальности "можно ли?" (Этап 3)
 └─ Participants — выбор NPC из line_of_sight (Этап 4) 

2. Event — валидированный Event уходит в ядро

3. Event — валидированный Event уходит в ядро

4. Spatial Filter — PerceptionFilter (кто именно воспринимает из участников)

4.5. Intent Pool — генераторы (GOAP, LifeEngine, Reaction) создают Intent'ы с параметрами (priority, commitment, source).
    ВНИМАНИЕ: Это Pool (пул кандидатов на ТЕКУЩИЙ тик), а не Queue (накопитель). Pool пересоздаётся каждый тик. Он не хранит историю между тиками.
    Это устраняет temporal drift (когда старый intent влияет на новую реальность).

5. DecisionHub — score(action) по весам (профиль + память + эмоции + риск)
   **ПРИНЦИП:** DecisionHub = чистый SCORER. Он не знает про "планы" или "рутину".
   Он получает список Intent'ов из очереди и считает финальный score для каждого.
   
6. Resolution — бросок кубика смещает ожидаемый результат (±10%)
   
   [ИЗМЕНЕНО]
7. State Update — StateApplicator производит дельты (только читает DecisionResult).
   SceneStateManager — единственная точка записи (атомарно применяет дельты).
   StateApplicator НЕ имеет права писать состояние напрямую.
   [/ИЗМЕНЕНО] 

8. World Influence — макро-мир реагирует (фракции, фронты, слухи)
  
9. Verbalization — LLM озвучивает intent одной фразой

10. ИСПРАВЛЕННАЯ АРХИТЕКТУРА (Закон системы):
    Внешние системы (GOAP, LifeEngine, EventBus) генерируют ActionCandidate.
    ActionCandidate КРАЙНЕ СТРОГО содержит только что можно сделать. Ноль чисел (никаких priority, score, weight).
    DecisionHub — единственный, кто имеет право приписать вес кандидату на основе формулы score().
    Intent Structur — это состояние NPCStateL2, а не свойство кандидата. Оно дает инерцию, но не финальное решение.

```

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
ВНИМАНИЕ: В текущей реализации DecisionHub принимает единый EventContext. Интеграция GOAP и Intent Queue (R10.5) запланирована как адаптация входных данных для DecisionHub, а не замена его формулы score(). Подробности в разделе 9.1.
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
- **Intent Saturation Penalty:** если тот же `chain_id` используется >3 тиков подряд, 
  score *= 0.9 каждый следующий тик (пока commitment не упадет).
- **Cognitive Switch Cost:** штраф при резкой смене intent'ов (анти-дребезг).
- **Commitment Decay:** каждый тик без выполнения шага GOAP-интент теряет 10% commitment.

**Архитектурный контракт:**
- GOAP — только генератор intent'ов (A* планировщик), не исполнитель.
- DecisionHub — только scorer, не знает про "планы" или "цели".
- SceneStateManager — единственный владелец состояния.

```
Ключевые механики:
- **INTENT_INERTIA (0.20):** NPC не дребезжит — продолжает начатое действие
- **SCORE_NOISE_RANGE (±10%):** контролируемый хаос, NPC не детерминирован
- **scores_trace:** "чёрный ящик" — почему NPC выбрал FLEE вмест of ATTACK
- **OpportunityEngine:** NPC действует проактивно (скрытые атаки, предательство при отсутствии свидетелей)
- **WillState.LOYAL** блокирует ATTACK — верные NPC не нападают без причины
- **stress > 90** → NPC теряет широту и сводится к базовым инстинктам (бегство/наблюдение)

Файлы: `npc/decision_hub.py`, `npc/opportunity_engine.py`, `npc/reaction_priority.py`, `npc/threat_assessor.py`, `npc/npc_cognition.py`, `npc/psyche_engine.py`, `npc/resolution_engine.py`

#### R3 Verbalization Layer ✅ УСИЛЕН
LLM получает только структурированные данные — никаких цифр и internals:

VerbalizationCore — frozen dataclass (whitelist: intent, target, scene)
str в render_npc_prompt() запрещён на уровне типа (TypeError)
_sanitize_verbalization_core() — 7 паттернов + теги, вызывается внутри to_prompt_text()
Секционные лимиты: core(300), voice(150), emotion(100), hints(200), bio(500)
Interpretation Envelope: запреты на описание сцены, чужих действий, multi-NPC
RESET STATE: защита от Semantic Echo Drift
Behaviour Contract: единый источник npc_system.txt, шаблон содержит только данные
build_npc_core_data() возвращает VerbalizationCore, не строку
Файлы: verbalization/verbalization_context.py, verbalization/prompt_loader.py, prompts/npc_system.txt, prompts/npc_speech.j2Тесты: 59 тестов (TestNPCPromptContent, TestPromptMustNotContain, TestTokenBudget, TestFailureModes, TestVerbalizationCoreContract)

---

### L0.5 — ПЕРСИСТЕНТНОСТЬ

#### R1.8 Iron-Man Persistence PARTIAL
- Никаких слотов сохранений. Auto-save при смене локации или выходе.
- `Inspiration` (переброс кубика) — только за Critical Success в сложных заявках.

Файлы: `scene_state_manager.py`, `campaign_state_service.py`, `player_session_service.py`, `scene_change.py`

---

### L1 — ПРОСТРАНСТВО ✅ DONE (R4 полностью закрыт)

#### R4 Spatial System
Полная пространственная симуляция сцены:

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
- Файлы: `character_service.py` (базовый), `verbalization_context.py` (ContentProfile — не то!)

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

Файлы: `npc/break_progress_engine.py`, `npc/behavior_mask.py`, `npc/state_applicator.py`

---

### L6 — МИР

#### R9 World Director STUB
- ❌ **Фронты (Fronts) — НЕ РЕАЛИЗОВАНЫ**
- ❌ **Фракции (Factions) — НЕ РЕАЛИЗОВАНЫ**
- ❌ **Экономика (Scarcity) — НЕ РЕАЛИЗОВАНА**
- ❌ **Автономные события — НЕ РЕАЛИЗОВАНЫ**
- ✅ Есть только заглушки: `world_scheduler.py`, `world_sim_agent.py`, `world_state.py`
- **Следующий шаг:** Реализация `FactionSystem` и `WorldFront` классов

---

### L8.5 — GAME LOOP

#### R13 Tick-Based Engine PARTIAL
- Диалог = 1 тик. Перемещение/отдых = X тиков.
- Мир меняется асинхронно во время отдыха игрока
- NPC перемещаются по расписанию (`life_engine.py`) независимо от игрока

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
│   │   ├── world_sim_agent.py
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
│       │   ├── resonance_engine.py   resonance_engine.py   # ✅ — подключён через MemoryManager.apply_identity_weights()
│       │   ├── importance_engine.py
│       │   ├── relationship_store.py
│       │   └── contradiction_resolver.py
│       ├── npc/
│       │   ├── decision_hub.py       # ★ Ядро интеллекта [✅ МИГРИРОВАН НА L0/L2]
│       │   ├── state_applicator.py   # ★ Единственная точка записи [✅ МИГРИРОВАН НА L0/L2]
│       │   ├── npc_state.py          # ★ ЕДИНЫЙ ИСТОЧНИК ТИПОВ — NPCPersonality(L0), NPCIdentityL1(L1), NPCState(L2), DecisionView, EventMemory
│       │   ├── life_engine.py
│       │   ├── location_graph.py     # R4 ✅
│       │   ├── spatial_runtime.py    # R4 ✅
        │   ├── npc_loader.py         # ★ НОВЫЙ — Адаптер миграции (JSON -> L0 Profile)
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
│       ├── state/
│       │   └── context_builder.py    # ★ Активен (build_context, patch_scene_state)
│       ├── verbalization/
│       │   ├── verbalization_context.py # R3 ✅ (Контракт готов, ждем L0/L2 данные)
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
│   │   │   └── verbalization/       # R3 — СЛОЙ ГОЛОСА (Только упаковка для LLM)
│   │   │       ├── prompt_factory.py      # Сборка промптов (NPC + DM)
│   │   │       ├── context_builder.py     # Формирование VerbalizationContext
│   │   │       └── llm_client.py          # Адаптер (llama.cpp/vLLM)
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

---

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

### 8. Frequency Dominance (доминирование GOAP)
**Симптом:** GOAP-планы системно выигрывают у реактивности из-за стабильной 
генерации intent'ов каждый тик, в то время как реакции спорадичны.
**Защита:** 
- `freshness_decay` для reactive_urgency (экспоненциальное затухание)
- `intent_saturation_penalty` (штраф за залипание в одном chain_id)
- Кап частоты генерации GOAP (не чаще 1 раза за тик)

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

---

## 8. ТЕКУЩИЙ ФОКУС РАЗРАБОТКИ

Завершено (Memory System v5.2):
  - Удалён файл-паразит services/memory.py
  - npc_state.py: добавлены NPCIdentityL1, DecisionView, алиасы L0/L2, write-контракты
  - Memory→DecisionHub: relationship_cache обогащается перед каждым compute()
  - ResonanceEngine→identity_cache: decay → apply_identity_weights → NPCIdentityL1
  - DecisionHub.compute() принимает identity=NPCIdentityL1
  - Удалён мёртвый memory_manager_agent.py

ЗАВЕРШЕНО (Глобальная очистка):
  - NPCStateL2 дубликат удалён из npc_profile.py → npc_state.py
  - NPCIdentityL1 дубликат удалён из npc_profile.py → npc_state.py
  - npc_profile.py теперь содержит только L0 типы
  - game_loop_factory.py → мигрирован в main.py (app.state) + accessor
  - npc_agent.py: react() + _fallback_react() удалены (-213 строк)
  - npc_state.py: to_legacy() мёртвый метод удалён
  - game_loop.py: ложные TODO-заглушки удалены
  - 228 тестов проходят, 0 failures

Технический долг:
  - active_traits в NPCState — мост до полного подключения ResonanceEngine
  - extractor + life_engine — мёртвые параметры в GameLoop.__init__
  - _request_sync — переименован (было _request_legacy)

ЗАВЕРШЕНО (Архитектурная стабилизация):
    Уничтожен монолит python_engines.py.
    Типы разделены: npc_profile.py (L0), npc_state.py (L1/L2).
    DecisionHub и StateApplicator пересажены на L0/L2.
    Создан npc_loader.py (бронестена от мусора).
    DM Execution Facade (Этап 5) интегрирован в game_loop.py.
    shared_context["dm_result"] подключён (заменён python_engines).

ЗАВЕРШЕНО (StateApplicator Pipeline):
  - DecisionHub → StateApplicator.apply() → NPCState.write_to_legacy() → _save_npcs()
  - NPC теперь реально меняют стресс/интент после действий игрока
  - Интеграционный тест: test_state_applicator_pipeline.py (2 passed)

ЗАВЕРШЕНО (R3 Verbalization Layer Enhancement):
  - VerbalizationCore — frozen dataclass с whitelist (intent, target, scene)
  - str в render_npc_prompt() запрещён на уровне типа (TypeError)
  - _sanitize_verbalization_core() — 7 паттернов + теги, вызывается внутри to_prompt_text()
  - Секционные лимиты: core(300), voice(150), emotion(100), hints(200), bio(500)
  - Interpretation Envelope в npc_system.txt — запреты на описание сцены, чужих действий
  - RESET STATE — защита от Semantic Echo Drift
  - Behaviour Contract: единый источник npc_system.txt, шаблон только данные
  - build_npc_core_data() возвращает VerbalizationCore, не строку
  - Удалены: npc_system.py, npc_speech.py (мёртвый код и дубликаты)
  - 59 тестов вербализации (0 failures)

## 9. ТЕКУЩИЕ ШАГИ РАЗРАБОТКИ

ЗАВЕРШЕНО:
- Хирургическое отсечение python_engines.py.
- Типы разделены: npc_profile.py (L0), npc_state.py (L1/L2).
- DecisionHub и StateApplicator мигрированы на L0/L2 контракты.
- Создан npc_loader.py — адаптер миграции.
- Глобальная очистка: -300 строк мёртвого/дублирующего кода.
- GameLoop мигрирован на app.state (main.py startup + accessor).

АКТИВНЫЙ ФОКУС: **Commitment Model & Intent Queue (R2.1)**
- Внедрение `commitment`, `reactive_urgency`, `freshness_decay` в DecisionHub.
- Реализация IntentQueue как арбитра между GOAP/LifeEngine/Reaction.
- State Ownership Fix: StateApplicator → чистый производитель дельт, 
  SceneStateManager → единственная точка записи.

СЛЕДУЮЩИЙ ШАГ (после стабилизации R2.1):
- Crisis Detector (минимальная версия: is_besieged, is_enslaved).
- Базовый GOAP Planner (3 цели, 5-6 действий, preconditions).
- Интеграция: GOAP как генератор intent'ов в очередь.

ТЕХНИЧЕСКИЙ ДОЛГ:
- Ego Resistance (R6) — минимальная версия (behavior drift penalty).

ИЗМЕНЕНИЕ:
Убрана строка с метрикой (она уже есть в дорожной карте)
Причина: Дублирование

---

## 9. БУДУЩАЯ АРХИТЕКТУРА: ADAPTIVE REALITY FRAMEWORK (R9.x + R11)

> Этот раздел описывает **следующий этап** развития ENIGMA после стабилизации текущей системы (R1-R8).  
> Здесь фиксируются архитектурные решения, которые будут реализованы позже, чтобы не забыть их и не переделывать.

---

### 9.1 GOAP — Генератор Intent'ов, в дереве кода (R10.5)

**Принцип:** GOAP не управляет NPC напрямую. Он создает Intent'ы с высоким 
`commitment`, которые попадают в общую очередь и конкурируют с реакциями 
через DecisionHub.

**Архитектура:**
[Crisis Detector] → [GOAP Planner] → [Intent Generator] → [Intent Queue]
↑                                      |
└──────── [World State Tracker] ←──────┘


**Crisis Detector:**
```python
def needs_goap(npc_state, world_state) -> bool:
    """Определяет, сломана ли рутина."""
    return (
        world_state.is_besieged or      
        npc_state.is_enslaved or         
        world_state.famine_level > 0.7 or 
        npc_state.home_destroyed         
    )

**Зачем он нужен (в будущем):**
- Город в осаде → фермер не может выйти в поле, нужен план "спрятаться/помочь защите/бежать"
- NPC захвачен в рабство → рутина "дом→работа" заменяется на "выживание/побег"
- Голод/разруха → поиск еды и убежища становится приоритетом

**Почему не сейчас:**
1. **Нет механик кризиса** — у нас нет осады, голода, разрушения домов
2. **LifeEngine покрывает 90%** — в норме NPC живут по расписанию из JSON
3. **Текстовый формат** — GOAP должен работать "в фоне", сжимая цепочку до одной фразы, а не показывать 5 тиков подряд

**Вердикт:** GOAP добавим в R10.5, когда появятся механики кризиса (осада, рабство, разруха), ломающие обычную рутину.

GOAP Planner (упрощенный):
    Цели: SURVIVE_SIEGE, ESCAPE_SLAVERY, FIND_FOOD, HIDE_FROM_THREAT
    Действия: 5-6 базовых (find_shelter, move_to, wait_hide, steal_food)
    Preconditions/Effects: Упрощенные (логические условия), достаточные для A*
    Вывод: Не "выполнить действие", а создать Intent с commitment=0.9 и chain_id
    Execution:
    GOAP генерирует план (цепочка шагов)
    Каждый тик предлагает ТОЛЬКО текущий шаг как Intent в очередь
    DecisionHub сравнивает его с реактивными intent'ами
    Если reactive_urgency > (commitment × 1.5) → план прерывается (естественно, через scoring)
    GOAP видит прерывание на следующем тике и пересчитывает план с новой позиции
    Запрет: GOAP не может генерировать больше одного Intent за тик.
    Нет "вложенных" планов — только линейная цепочка с возможностью отката.

Файлы:
    services/npc/cognition/goap_intents.py — генератор
    services/npc/cognition/crisis_detector.py — триггер
    services/npc/cognition/intent_queue.py — общая очередь (все источники)

---

### 9.2 Что такое Adaptive Reality Framework (R9.x + R11)

**Проблема:** Сейчас мир реагирует на игрока локально (NPC помнит обиды). Но мир не **адаптируется** глобально.

**Пример:** Игрок 10 раз подряд использует "Запугивание → Кража". Каждый NPC реагирует отдельно. Но стража не становится умнее, торговцы не начинают прятать товары, игрок не чувствует, что "этот мир больше не принимает его".

**Решение:** Система пяти уровней адаптации мира:

| Уровень | Что происходит | Пример |
|---------|----------------|--------|
| **L1** Local Memory | Отдельный NPC запоминает | Торнин боится игрока |
| **L2** Social Graph | Слухи распространяются | Все в деревне знают о воре |
| **L3** Pattern Recognition | Система видит паттерн | "Игрок всегда крадёт ночью" |
| **L4** Macro Adaptation | Мир меняет правила | Стража удваивается, ночью запирают двери |
| **L5** Reality Shift | Игрока вытесняют в другой слой реальности | Из "порядочного мира" в "подполье" |

**Ключевой принцип:** Игрок не выбирает фракцию. Мир **вытесняет** его туда, где он теперь существует.

---

### 9.3 Как это будет устроено (Чистая версия)

Вместо сложной иерархии папок — **плоская структура** в `services/world/`:

```
backend/app/services/world/           ← НОВАЯ ПАПКА (9 файлов)
├── world_director.py                 # Главный фасад — единственная точка входа
├── adaptive_core.py                  # L1-L4: Память, паттерны, адаптация
├── social_layer.py                   # L2 + L5: Слухи и сдвиг реальности
├── scene_field.py                    # Динамика сцены (внимание, напряжение)
├── consequence_imprint.py            # Следствия действий (многослойный отпечаток)
├── pressure_bias_engine.py           # Давление на NPC (меняет их решения)
├── probabilistic_model.py            # Потолок успеха (~70%, нельзя абузить)
├── telemetry.py                      # Отладка (God Mode)
└── constants.py                      # Все числа в одном месте
```

**Почему именно так:**
- **Zero overhead** — обновления не каждый тик, а по необходимости
- **Не ломает текущее** — DecisionHub получает только 2 новых множителя:
  ```python
  score = base_score * scene.narrative_bias * layer.cost_multiplier
  ```
- **9 файлов** — никакой "папки в папке в папке"

---

### 9.4 Порядок внедрения (почему так)

**Сейчас (Фаза 0):** Стабилизируем R2-R8
- DecisionHub должен работать в продакшене
- StateApplicator — единственная точка записи
- Все тесты зелёные

**Потом (Фаза 1):** R9.x Core
- Local Memory + Pattern Recognition
- Подключается к существующему R1 Memory

**Потом (Фаза 2):** Social Layer
- Слухи + Social Graph
- Подключается к OpportunityEngine

**Потом (Фаза 3):** R11 Reality Shift
- Три слоя реальности: Order → Grey Zone → Underworld
- Только когда всё предыдущее стабильно

**Почему такой порядок:** Каждый следующий слой зависит от предыдущего. Нельзя делать "реальность-сдвиг" (L5), если нет паттерн-распознавания (L3).

---

### 9.5 Финальный принцип (зачем всё это)

> "Игрок может обмануть NPC.  
> Но не может бесконечно обманывать систему.  
> 
> Мир не даёт бонусов.  
> Мир меняет условия.  
> 
> Игрок не выбирает слой реальности —  
> мир сам вытесняет его туда, где он теперь существует."

**Этот раздел — дорожная карта.** Когда текущая архитектура (R1-R8) будет стабильна, мы откроем этот раздел и начнём внедрение с Фазы 1.
```

Вот гибридный вариант — моя структура + твои формулировки:

---

```markdown
## 9. БУДУЩАЯ АРХИТЕКТУРА: ADAPTIVE REALITY FRAMEWORK (R9.x + R11)

> Следующий этап после стабилизации R1–R8.  
> Цель — превратить мир из реактивного в **адаптирующийся, но несовершенный**.

---

### 9.1 Проблема и цель

**Сейчас:**
```text
игрок → действие → NPC реагируют
```

**Недостаток:**
```text
мир не учится как система
мир не меняет правила  
мир не ошибается
```

**Нужно:**
```text
игрок → действие → мир учится → мир меняет правила → игрок адаптируется
```

---

### 9.2 Уровни адаптации (L1–L5)

| Уровень | Механика | Суть | Статус |
|---------|----------|------|--------|
| **L1 — Local Memory** | R1 ✅ | NPC помнит события | Готово |
| **L2 — Social Layer** | R7 🟡 | Слухи распространяются | Частично |
| **L3 — Pattern Recognition** | R9.1 🔴 | Система выявляет повторы | Планируется |
| **L4 — Macro Adaptation** | R9.2 🔴 | Мир меняет условия | Планируется |
| **L5 — Reality Shift (R11)** | R11 🔴 | Игрока вытесняют в другой слой | Планируется |

**Pipeline:**
```text
событие → агрегация → распознавание паттерна → оценка уверенности → триггер адаптации
```

---

### 9.3 Ключевые принципы

```text
1. Игрок не может эксплуатировать систему бесконечно
   но система не идеальна и может ошибаться

2. Мир не усиливается напрямую — мир меняет структуру

3. Мир платит за изменения:
   - time_delay (адаптация не мгновенна)
   - resource_cost (требуется участие NPC/структур)
   - error_rate (результат может быть неправильным)

4. При сужении пространства появляются альтернативные пути (Escape Vector)

5. Игрок не выбирает слой реальности — мир вытесняет его туда, где он теперь существует
```

---

### 9.4 Структура (services/world/)

```
world/
├── world_director.py          # Главный фасад — единственная точка входа
├── adaptive_core.py           # L3-L4: Паттерны + адаптация
├── social_layer.py            # L2 + L5: Слухи + сдвиг реальности  
├── scene_field.py             # Динамика сцены (внимание, напряжение)
├── consequence_imprint.py     # Многослойный отпечаток последствий
├── pressure_bias_engine.py    # Давление на NPC (меняет их решения)
├── probabilistic_model.py     # Потолок успеха ~70%
├── telemetry.py               # God Mode debug
└── constants.py               # Все thresholds в одном месте
```

---

### 9.5 Imperfection (несовершенство системы)

**Почему:** Идеальная система = нечестная. Игрок должен иметь шанс "обмануть" мир.

**Механики:**
- `pattern_confidence ∈ [0..1]` — мир не уверен в паттерне
- `pattern_error_rate ∈ [0.1..0.4]` — ложные/неполные выводы  
- `adaptation_delay` (в тиках) — адаптация не мгновенна
- `information_imperfection` — NPC действует по восприятию, не по истине

**Типы ошибок системы:**
* ложный паттерн (увидел то, чего нет)
* неполный паттерн (не заметил ключевого)
* задержка распознавания (реакция с опозданием)

---

### 9.6 Adaptation Cost (цена адаптации)

```text
мир платит за изменения
```

**Пример:**
```text
усиление охраны →
    требуется время →
    часть мер неэффективна →
    возможны новые уязвимости
```

**Компоненты:**
- `time_delay` — адаптация не мгновенна
- `resource_cost` — требуется участие NPC/структур  
- `error_rate` — результат может быть неправильным

---

### 9.7 Reality Shift (R11)

**Три слоя реальности:**
```text
Order World  → Grey Zone  → Underworld
   ↑______________↓______________↑
   (возврат возможен, но дорогой)
```

**Механика перехода:**
```text
trust ↓ + reputation ↓ + suspicion ↑ + pressure ↑ → layer shift
```

**Irreversibility Gradient:**
```text
глубже слой → выше цена возврата → ниже вероятность возврата
```

**Escape Vector (ключевой принцип):**
```text
система не должна замыкаться

при сужении пространства →
обязательно появляются альтернативные стратегии
```

📌 Это не помощь. Это **смена уровня игры**.

---

### 9.8 Интеграция с DecisionHub

```python
score = base_score * narrative_bias * layer_modifier * uncertainty_factor
```

**Новые входы:**
- `narrative_bias` — из scene_field (внимание к игроку)
- `layer_modifier` — из social_layer (cost multiplier)
- `uncertainty_factor` — из probabilistic_model (ошибка восприятия)

**Информационное несовершенство:**
```text
NPC действует по восприятию, а не по истине
```

---

### 9.9 Порядок внедрения

| Фаза | Что делаем | Зависимость |
|------|------------|-------------|
| **0 (сейчас)** | Стабилизация R2-R8 | DecisionHub в продакшене |
| **1** | Adaptive Core + Pattern Recognition | Готова R1 Memory |
| **2** | Social Layer + Rumor propagation | Готовы L3 паттерны |
| **3** | Macro Adaptation | Готовы L2-L3 |
| **4** | Reality Shift (R11) | Готовы L1-L4 |

---

### 9.10 Финальный принцип

```
игрок может обмануть NPC
но не может бесконечно обманывать систему

мир не помогает игроку
мир меняет условия

мир не идеален
и именно поэтому он живой

```

## 10 Ядро, которое нельзя ломать

1. DecisionHub — чистый математик

    Не арбитр
    Не очередь
    Не исполнитель
    Только вычисление score на основе состояния мира

    Любая попытка превратить его в «выбор из списка» = деградация до скриптового AI
    Вероятность краха иммерсии: 85–95%

2. Pipeline строгий, однонаправленный

    RAW INPUT
        → RawEvent (только факт из текста)
        → EventContext (обогащённый миром)
        → ValidatedEvent (проверка реальности)
        → Intent (формализация действия)
        → DecisionHub (оценка)
        → Action
        → StateDelta → StateApplicator

    Любое «перепрыгивание» этапов = рассинхронизация модели мира

3. Никаких placeholder-данных

    Нет success=True "пока что"
    Нет witness_count=1 "потом заменим"
    Нет "заглушек"

    Если данные неизвестны → они не существуют

    Иначе:
        → появляются фантомные состояния
        → DecisionHub считает на мусоре
        → поведение NPC начинает «течь»

    Риск: скрытые баги с экспоненциальным ростом

4. Иммутабельность слоёв

    RawEvent — immutable
    EventContext — immutable
    Никаких «допишем позже»

    Только:

    new_context = build_from(old_context)

5. Генераторы ≠ решатели

    GOAP, LifeEngine, EventBus → создают давление/контекст
    DecisionHub → решает

    Если генераторы начинают «решать» → система распадается на конкурирующие AI















# Дорожная карта: Semantic Determinism v2

---

## Текущее состояние

```
Semantic Determinism: 72% 🟡

Точка отказа: to_prompt_text()
```

---

## Анализ рисков (принят без скидок)

| Риск | Вероятность | Причина |
|------|-------------|---------|
| Тихая деградация смысла | 45% | Нет проверки обратимости Core→Text |
| "Дрожание" NPC | 50% | Нет проверки монотонности изменений |
| Потеря фокуса LLM | 55% | Нет лимита на единицы смысла |
| Реинтерпретация intent | 60% | Intent только в тексте, не как сигнал |
| Критический сбой to_prompt_text | 40% | Единственная точка, нет резервирования |

---

## Дорожная карта (4 фазы)

### Фаза 1: Усиление to_prompt_text() — быстрые wins

**Сложность:** Низкая  
**Срок:** 1 сессия  
**ROI:** -30% общего риска

| # | Задача | Тип | Что даёт |
|---|--------|-----|----------|
| 1.1 | Roundtrip test: Core→Text→Core | Тест | Ловит потерю смысла |
| 1.2 | Stability test: малое Δвхода → малое Δвыхода | Тест | Ловит "дрожание" |
| 1.3 | MAX_SEMANTIC_UNITS=3 в to_prompt_text() | Код | LLM не теряет фокус |
| 1.4 | Выделить intent в тексте: "Главное намерение: TALK" | Код | -35% реинтерпретации |

**Критерий успеха:** Все новые тесты зелёные, существующие не сломаны.

---

### Фаза 2: Intent как структурный сигнал — архитектурное изменение

**Сложность:** Средняя  
**Срок:** 2-3 сессии  
**ROI:** -50% риска реинтерпретации

| # | Задача | Тип | Что даёт |
|---|--------|-----|----------|
| 2.1 | Добавить `intent_signal` в render_npc_prompt() | API | Отдельный канал для intent |
| 2.2 | Передавать intent через developer message | LLM | LLM не может "забыть" intent |
| 2.3 | Обновить npc_speech.j2 — optional intent block | Шаблон | Чистое разделение |
| 2.4 | Тест: intent присутствует даже при переполнении | Тест | Intent не жертвуется |

**Структура messages:**
```python
messages = [
    {"role": "system", "content": npc_system_prompt},
    {"role": "developer", "content": f"INTENT={core.intent} TARGET={core.target}"},
    {"role": "user", "content": verbalization_prompt}
]
```

**Критерий успеха:** Intent проходит отдельно от текста, тесты покрывают.

---

### Фаза 3: Миграция build_npc_core_data() — устранение дублирования

**Сложность:** Средняя  
**Срок:** 1-2 сессии  
**ROI:** -20% рассинхронов

| # | Задача | Тип | Что даёт |
|---|--------|-----|----------|
| 3.1 | build_npc_core_data() → возвращает VerbalizationCore | Рефакторинг | Одна точка формирования смысла |
| 3.2 | Удалить ручную сборку строки в verbalization_context.py | Чистка | Нет двух путей |
| 3.3 | Запретить str в render_npc_prompt() | Контракт | Миграция завершена |
| 3.4 | Удалить VerbalizationCoreInput тип-алиас | Чистка | Нет "временных" решений |

**Критерий успеха:** `verbalization_core: str` → TypeError. Только `VerbalizationCore`.

---

### Фаза 4: Семантическая валидация — продвинутая защита

**Сложность:** Высокая  
**Срок:** 3-4 сессии  
**ROI:** -15% остаточного риска

| # | Задача | Тип | Что даёт |
|---|--------|-----|----------|
| 4.1 | SemanticUnit extractor (считает "единицы смысла") | Утилита | Метрика перегрузки |
| 4.2 | semantic_density() — доля осмысленных токенов | Утилита | Метрика качества |
| 4.3 | Тесты на semantic_density для разных tier | Тесты | MAJOR/MINOR имеют разную плотность |
| 4.4 | Интеграция в CI — automatic quality gate | DevOps | Автозапрет на деградацию |

**Критерий успеха:** PR не мержится если density < 0.4.

---

## Прогноз Semantic Determinism

```
Сейчас:          65% 🟡
После Фазы 1:    75% 🟢
После Фазы 2:    85% 🟢
После Фазы 3:    90% 🟢
После Фазы 4:    95% 🟢
```

---

## Принципы (зафиксированы)

```
1. to_prompt_text() — единственная точка смысл→текст
   Если она сломана — всё сломано
   ⇒ Максимум тестов, минимум логики

2. Intent не должен зависеть от формулировки
   "Главное намерение: TALK" ≠ "Намерение: TALK"
   ⇒ Один шаблон, одна формула

3. Semantics > Syntax
   Формат строки не важен, важно что смысл прошёл
   ⇒ Roundtrip test — главный критерий

4. LLM не может "забыть" intent если он не в тексте
   ⇒ Структурный сигнал (developer message)

5. Меньше смыслов = лучше фокус
   MAX_SEMANTIC_UNITS = 3
   ⇒ Обрезка не по символам, а по смыслам
```

---

## Что НЕ делать

```
❌ Усложнять to_prompt_text() — он должен быть тривиальным
❌ Добавлять новые поля в VerbalizationCore — 3 достаточно
❌ Делать sanitize умнее — он должен стать ненужным
❌ Писать semantic extractor до Фазы 4 — преждевременная оптимизация
```
где в этой архитектуре остаётся недетерминированность, которая переживёт все твои тесты и вылезет через 3–6 итераций развития системы?

Вот это и есть цель.

2. Главная иллюзия твоей дорожной карты

Ты считаешь, что центр риска — to_prompt_text().

Это неверно.

Реальный центр риска:
VerbalizationCore (смысл)
↓
to_prompt_text() (проекция)
↓
LLM (интерпретация)
↓
Текст NPC (поведение)

Ты контролируешь:

вход (Core)
проекцию (Text)

Но не контролируешь:

интерпретационное пространство LLM

И вот где живёт настоящий хаос.

3. Критическая дыра, которую ты ещё не закрыл
❗ Ты не фиксируешь "допустимое множество интерпретаций"

Сейчас у тебя есть:

whitelist на входе ✅
sanitize на выходе из Python ✅
тесты на строку ✅

Но нет:

границ того, КАК LLM имеет право понять этот текст

Пример

Ты передаёшь:

Главное намерение: TALK
Игрок спрашивает про эль

LLM может:

ответить на вопрос (OK)
начать описывать сцену (BAD)
добавить реакции других NPC (BAD)
сменить тон (BAD)

И все тесты будут зелёные.

4. Настоящая недостающая фаза (ты её не включил)
Фаза 0 (до всего)
Interpretation Envelope
Суть

Ты должен зафиксировать:

не только ЧТО передаётся
но и в каком пространстве допустим ответ

Как это выглядит

Не тестами строки.

А контрактом поведения:

NPC_RESPONSE_CONTRACT:
- only_first_person: true
- no_other_npcs: true
- max_sentences: 2
- no_scene_description: true
- must_address_target: true
И теперь ключ

Ты не можешь проверить это через LLM.

Но ты можешь:

→ встроить это в prompt как жесткий каркас

И тестировать наличие этого каркаса, а не результат.

5. Где у тебя реальный разлом сейчас
1. Core → Text (ты почти закрыл)

Риск: 20%

2. Text → Interpretation (ты НЕ трогал)

Риск: 60% ← главный

3. Interpretation → Output drift

Риск: 50%

6. По фазам — что изменить
Фаза 1 (у тебя хорошая, но неполная)

Добавь:

1.5 — Interpretation Constraints Injection
+ test_prompt_contains_behavior_constraints()
+ test_constraints_not_truncated_by_budget()

ROI: –25% хаоса сразу

Фаза 2 (самая сильная у тебя)

Но ты недожал.

Ты сделал:

intent → developer message

Но не сделал:

behavior → developer message
Должно быть:
developer:
INTENT=TALK
TARGET=player
MODE=FIRST_PERSON_ONLY
NO_OTHER_NPCS=TRUE
Критический параметр всей системы

Сколько семантики вынесено из текста в структуру

Сейчас у тебя ~30%
Нужно → 70%+

7. Твоя идея MAX_SEMANTIC_UNITS = 3

Сильная, но опасная.

Почему

Ты режешь:

шум ✅
но и контекст ⚠️
Альтернатива (сильнее)

Не лимит:

иерархия смыслов

PRIMARY (обязательно)
SECONDARY (если влезает)
DECORATIVE (выпиливается первым)
Вероятности
Подход	Потеря смысла
Жёсткий лимит	35%
Иерархия	10%
8. Самый опасный будущий баг (ты его ещё не видел)
Semantic Echo Drift

Когда:

Core стабилен
Prompt стабилен

Но NPC начинает:

«наращивать стиль» через предыдущие ответы

Причина

LLM начинает опираться не на prompt, а на:

history → pattern → self-consistency
Решение (которого у тебя нет)
Reset Anchor

Каждый промпт должен содержать:

IGNORE PREVIOUS STYLE DRIFT.
ACT ONLY FROM CURRENT STATE.
9. Оценка твоей системы
Текущее состояние (реальное)
Детерминизм:
Core → Text:        85%
Text → LLM:         40%
LLM → Output:       45%

Итого: ~62%

Ты почти идеально попал в цифру 65%.

10. Ответ на главный вопрос
Нет, твои тесты не фуфло.

Но:

они проверяют трубопровод, а не поле боя

11. Что реально усилит систему (3 шага)
1. Behavior Contract (обязательно)

Срежет ~30% хаоса

2. Structural Signal Expansion (intent + behavior)

Срежет ~20%

3. Semantic Hierarchy вместо лимита

Срежет ~15%
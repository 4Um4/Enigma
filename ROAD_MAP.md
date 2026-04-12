```text
================================================================================
                        ENIGMA: ДОРОЖНАЯ КАРТА И АРХИТЕКТУРА
================================================================================

┌─────────────────────────────────────────────────────────────────────────────┐
│                         1. ЧТО УЖЕ СДЕЛАНО                                  │
└─────────────────────────────────────────────────────────────────────────────┘

██ ФАЗА 1 — ЗАКРЫТИЕ КОНТУРА [ЗАВЕРШЕНА]
═════════════════════════════════════════

  ├─ 1.1 Убрать npc_agent из MAJOR сценариев ✅
  │     └─ DecisionResult[] → SceneOutcome → DMFrame → DM (1 LLM)
  │
  ├─ 1.3 Запретить TEXT→ENTITY ✅
  │     └─ NarrativeExtractor.new_objects заблокирован
  │
  ├─ Баги закрыты:
  │     ├─ #1 npc_agent вопреки R3_DIRECT_MODE (ложная тревога)
  │     ├─ #2 Парсинг реплик → мусорные объекты
  │     ├─ #3 Галлюцинация "Эль — подобран"
  │     ├─ #4 Локализация apron/keys
  │     ├─ #5 Template repetition у Люси
  │     ├─ #6 LifeEngine splice без DM интеграции
  │     ├─ #7 Дублирование npc_contexts (2 append → 6 decisions вместо 3)
  │     └─ #8 DM Router: мат-междометия ("нахуй") + ложные срабатывания ("ты не дурак")
  │
  └─ LifeEngine data-driven ✅
        └─ activity_map вынесен в JSON, _NPC_ACTIVITY_MAP удалён

██ АУДИТ РЕАЛЬНОСТИ (по логам 10-ходовой проверки)
════════════════════════════════════════════════════════════

  ├─ R4 PerceptionFilter: distance >= 5.0 не фильтрует ❌
  │     Лог: 5/5 NPC при dist=5.0 пропустили фильтр
  │     Корень: fallback в perception_filter возвращает 999.0 вместо реального distance
  │     Файл: perception_filter.py:119 — нет проверки distance < 15.0
  │
  ├─ R2 DecisionHub: player_interacts → intent=flee ❌
  │     Лог: "Привет, Торнинг" → intent=flee при stress_d=0.0
  │     Корень: emotion_map не содержит player_interacts → нет emotion_tag
  │     Итог: fear_drive (0.15) доминирует без контрasta
  │     Файл: decision_hub.py:868 — нет "player_interacts" в emotion_map
  │
  ├─ R8 Stability: не сбрасывается при смене сессии ⚠️
  │     Лог: stab=0.75 при первой смене игрока (SESSION_REPLACED)
  │     Корень: player_session_service не сбрасывает NPC state
  │     Старый emotion_tag из прошлой сессии даёт +0.35 к FLEE
  │     Файл: player_session_service.py:121 — нет сброса после REPLACED
  │
  ├─ R5 Resolution: нет бросков для действий ❌
  │     Лог: "пытаюсь взять меч" → нет провала, DM описывает попытку
  │     Корень: Router не классифицирует "пытаться" как action
  │     Проблема: rules_agent не вызывается для физических действий
  │
  ├─ B.3 Continuity: events дублируются ⚠️
  │     Лог: "Началась драка" ×2 при разных event_type
  │     Корень: add_event не проверяет дубликаты
  │     Файл: scene_continuity.py:61 — нет дедупликации
  │
  └─ AsyncIO: World Sim Agent error ⚠️
        Лог: Semaphore bound to different event loop (повторяющийся)
        Корень: world_sim_agent запускается в другом event loop

  ├─ R1 Memory Core ✅
  │     ├─ L1 Numerical (числовые веса для DecisionHub)
  │     ├─ L2 Event (список событий с decay/distortion)
  │     ├─ L3 Identity (черты из ResonanceEngine)
  │     └─ Write-контракты зафиксированы
  │
  ├─ R2 Decision Core ✅ (БАЗОВАЯ ВЕРСИЯ)
  │     ├─ DecisionHub — чистый scorer на L0/L2 типах
  │     ├─ Commitment Model (базовая реализация)
  │     ├─ Pressure Accumulation (R2.1 Phase 2)
  │     ├─ Intent Exhaustion (R2.1 Phase 3)
  │     └─ 73+ тестов
  │
  ├─ R3 Verbalization Layer ✅
  │     ├─ VerbalizationCore (frozen dataclass, whitelist)
  │     ├─ VerbalStance (B.2) — intent → stance/tone/urgency
  │     ├─ SceneContinuity (B.3/B.4) — flags, tension, emotional_vector
  │     ├─ BehaviorMode: STRICT/FLEXIBLE/REACTIVE/SILENT
  │     ├─ R3_DIRECT_MODE: DM = единственный источник речи
  │     ├─ SceneOutcomeBuilder → SceneOutcome → DMFrame
  │     └─ 180 тестов
  │
  ├─ R4 Spatial System ✅
  │     ├─ LocationGraph + LocationNode
  │     ├─ LocalSpace (расстояния реальны: 2.5-4.6м)
  │     └─ PerceptionFilter (PERCEPTION_RADIUS по tier)
  │
  ├─ R5 Resolution Layer ✅
  │     └─ Gap System: actual - expected → стресс/трейты
  │
  ├─ R8 Break System ⚠️ [ФУНКЦИОНАЛЬНО, НО С ДОЛГОМ]
  │     ├─ BreakProgressEngine (5 стадий) ✅
  │     ├─ behavior_mask.py (структуры определены) ✅
  │     └─ Интеграция в DecisionHub ⚠️ (жёсткий override: COLLAPSE→IDLE, FAKE_SUBMISSION→TALK, BETRAYAL→OBSERVE)
  │           ПРОБЛЕМА: маска переписывает волю, а не ограничивает её
  │           РИСК: неявный "второй DecisionHub" — маппинг не масштабируется
  │           ПРАВИЛЬНО: intent_score *= mask_modifier ИЛИ allowed_intents = constrained_set
  │
  └─ World Ontology v1.0 [ЧАСТИЧНО]
        ├─ PHYSICAL_OBJECT + is_physical_object() ✅ (используется в npc_loader.py)
        ├─ BODY_TRAIT ❌ (определён, но не используется)
        └─ ROLE_MARKER ❌ (определён, но не используется)

██ ИНФРАСТРУКТУРНЫЕ КОМПОНЕНТЫ [РЕАЛИЗОВАНЫ]
═════════════════════════════════════════════

  ├─ PersistencePort + JsonPersistenceAdapter ✅
  ├─ SceneStateManager.commit() как Unit of Work ✅
  ├─ Pipeline Stitch Audit ✅ [ШАГ 1 ЗАКРЫТ]
  │     ├─ DM Orchestrator path → через commit() ✅
  │     └─ Legacy paths (896, 935) → commit() ✅ (было: прямой _save_npcs())
  └─ NpcOutcome / SceneOutcome структуры (готовы к расширению) ✅

██ ФАЗА 2.1 — PSYCHOLOGICAL INTEGRATION [В ПРОЦЕССЕ]
══════════════════════════════════════════════════════

  ├─ 2.1.1 CognitiveDistortionEngine ✅ [ШАГ 2a ЗАКРЫТ]
  │     ├─ Файл: services/npc/cognitive_distortion.py
  │     ├─ 3 оси: threat_bias, trust_bias, salience_bias ✅
  │     ├─ Индивидуальные капы для каждой оси ✅
  │     └─ Governor: total_distortion ≤ 1.0 ✅ (нормализация через scale)
  │
  ├─ 2.1.2 ProjectionLayer ✅ [ВСТРОЕН]
  │     ├─ Файл: services/verbalization/scene_outcome_builder.py
  │     └─ Метод: _build_psychological_projection()
  │
  ├─ 2.1.3 models/psychological.py ✅ [ШАГ 2b ЗАКРЫТ]
  │     ├─ Файл: models/psychological.py (СОЗДАН)
  │     ├─ DistortionProfile — frozen dataclass, 3 оси + Governor ✅
  │     ├─ CausalEntry — dataclass для Шага 3 ✅
  │     ├─ cognitive_distortion.py → возвращает DistortionProfile (не dict) ✅
  │     └─ scene_outcome_builder.py → принимает DistortionProfile (не dict) ✅
  │
  ├─ 2.1.4 Causal Ledger ✅ [ШАГ 3 ЗАВЕРШЁН]
  │     ├─ state_applicator.py — пишет CausalEntry с каждой дельтой
  │     ├─ npc_state.py — causal_ledger: List[Any] (cap=20)
  │     └─ source заполняется из event.event_type (player_attacks, player_insults и т.д.)
  │           ⚠️ ЧТЕНИЕ: God Mode endpoint для просмотра causal_ledger пока не реализован
  │
  └─ 2.1.5 Controlled Chaos [УЖЕ УДАЛЁН]
        └─ Проверено: noise в dm_agent.py = ambient шум сцены, не chaos-параметр


┌─────────────────────────────────────────────────────────────────────────────┐
│                       2. ЧТО ПРЕДСТОИТ СДЕЛАТЬ                              │
└─────────────────────────────────────────────────────────────────────────────┘

██ ФАЗА 2.2 — COMMITMENT + SWITCHING COST [ЗАВЕРШЕНА]
═══════════════════════════════════════════════════════════════

  ├─ commitment ∈ [0..1] — из intent_duration ✅
  ├─ COMMITMENT_BONUS_K — бонус к текущему intent в score ✅
  ├─ _switching_cost() — штраф за смену intent ✅
  │     ├─ SWITCHING_COST_BASE (0.05)
  │     ├─ age_cost = commitment * 0.08
  │     ├─ emotion_cost = stress/100 * 0.06
  │     └─ identity_cost = 0.04 если intent ≠ drive
  ├─ Формула: scores[current] += commitment * K; scores[other] -= cost ✅
  └─ Отдельный intent_queue.py НЕ НУЖЕН — state.intent + cost достаточно

██ ФАЗА 2.3 — ПРИЧИННАЯ СТАТЕГИЯ (A → B → C → D → E)
════════════════════════════════════════════════════════════

  ⚠ АУДИТ ПО ЛОГАМ (после 10-ходовой проверки):
  ├─ R4: perception_filter fallback distance=999.0 → 5/5 NPC видят при dist=5.0
  ├─ R2: player_interacts не в emotion_map → fear_drive доминирует → flee
  ├─ R8: SESSION_REPLACED не сбрасывает NPC state → stale emotion_tag
  ├─ R5: "пытаюсь взять" не триггерит бросок
  ├─ B.3: add_event не дедуплирует → "Началась драка" ×2
  └─ AsyncIO: world_sim_agent semaphore error
═══════════════════════════════════════════════════════════════

  ПРИНЦИП: A фиксирует числа. B фиксирует повествование.
           C фиксирует ядро. D распространяет. E давит.

  ┌─────────────────────────────────────────────────────────────────────┐
  │ ШАГ A: ВОССТАНОВИТЬ ПРИЧИННОСТЬ ✅ ЗАВЕРШЁН + КАЛИБРОВКА         │
  │                                                                     │
  │ A.1 intensity: Router → DecisionHub ✅                             │
  │ A.2 Router паттерны: расширить классификацию ✅                    │
  │     ├─ "твою" → regex fallback (между паттернами и морфологией) ✅ │
  │     └─ "замолчи", "на колени" → player_threatens ✅               │
  │ A.3 StateDeltas.source ✅                                         │
  │                                                                     │
  │ [КАЛИБРОВКА ПО ЛОГАМ]:                                            │
  │ ├─ Добавлена ветка player_attacks в _compute_deltas ✅             │
  │ │   (раньше "Я бью Люсю" давало stress_d=0.0 — шла в combat)      │
  │ ├─ Добавлены ветки player_threatens / threatens_indirect ✅        │
  │ └─ Причина: Router выдаёт player_attacks, а не combat             │
  └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │ ШАГ B: ВЕРБАЛИЗАЦИОННЫЙ СЛОЙ ✅ ЗАВЕРШЁН                        │
  │                                                                     │
  │ ЦЕЛЬ: LLM не интерпретирует — LLM исполняет.                      │
  │                                                                     │
  │ B.1 Segregate Agency ✅                                            │
  │ ├─ dm_agent.py: ALLOWED/FORBIDDEN контракт                        │
  │ ├─ FACT MODE: Verified/Claimed/Unknown разделение                 │
  │ └─ STANCE CONTROL: "ты не выбираешь — ты выражаешь"               │
  │                                                                     │
  │ B.2 Intent → Stance Mapping ✅                                     │
  │ ├─ verbal_stance.py: VerbalStance + stance_from_decision()        │
  │ ├─ scene_outcome_builder.py: stance в NpcOutcome + вывод в prompt  │
  │ └─ Mapping: intent+stress+fear+trust → stance/tone/urgency        │
  │                                                                     │
  │ B.3 Scene Continuity Cache ✅                                      │
  │ ├─ scene_continuity.py: flags, events, facts, tension             │
  │ ├─ game_loop.py: обновление из дельт + flags по event_type        │
  │ └─ dm_agent.py: to_prompt_block() в prompt                        │
  │                                                                     │
  │ B.4 Micro-History ✅                                               │
  │ ├─ scene_continuity.py: emotional_vector (trust/tension/confusion) │
  │ ├─ Инерция: 70% текущее + 30% новое                               │
  │ └─ dm_agent.py: to_emotional_line() в prompt                      │
  └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │ ШАГ C: СТАБИЛИЗАЦИЯ ЯДРА (Python→Python)                          │
  │                                                                     │
  │ C.1 Distortion → DecisionHub (модификатор, не источник)           │
  │ C.2 BehaviorMask: от override к constraint                        │
  └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │ ШАГ D: SOCIAL PROPAGATION                                           │
  │                                                                     │
  │ D.1 social_engine.py                                               │
  │ D.2 rumor distortion + trust-based propagation                    │
  │ D.3 decay по хопам                                                │
  └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │ ШАГ E+: ФАЗА 4                                                    │
  │                                                                     │
  │ E.1 Ego Resistance                                                 │
  │ E.2 Fronts                                                         │
  └─────────────────────────────────────────────────────────────────────┘

██ ФАЗА 3 — ОТ РЕАКТИВНОГО К ПРОАКТИВНОМУ МИРУ
═══════════════════════════════════════════════════

  ┌─────────────────────────────────────────────────────────────────────┐
  │ ЧТО МЕШАЕТ "МЕЧТЕ" (Диагностика по 10 шагам Деревни)             │
  │                                                                     │
  │ ТЕКУЩЕЕ СОСТОЯНИЕ: NPC — стильные Marionette.                    │
  │ Они дёргаются только когда игрок дёргает за нитки (текст).        │
  │                                                                     │
  │ ПРОБЛЕМА 1: ПРОСТРАНСТВО ИНЕРТНО                                   │
  │ "Подойти к Люси" → player_interacts. Нет события proximity.      │
  │ R4 считает метры, но не генерирует event_type при пересечении.    │
  │                                                                     │
  │ ПРОБЛЕМА 2: НЕТ СВЯЗЕЙ NPC-NPC                                    │
  │ Нет триггера "ревность". DecisionHub не видит, что игрок в 1.5м   │
  │ от Люси и не знает tornin.attachment_lucy.                        │
  │                                                                     │
  │ ПРОБЛЕМА 3: НЕТ ПРОАКТИВНОЙ ВОЛИ                                  │
  │ Нет цикла World Tick → NPC Agenda. Шаг 9 (Торнин блокирует путь) │
  │ невозможен: NPC не может действовать без хода игрока.             │
  └─────────────────────────────────────────────────────────────────────┘

  ├─ 2.5 БAGFIXES (R2/R4/R5/R8/Continuity) [В ПРОЦЕССЕ]
  │     ├─ R4: perception_filter fallback → distance cap 15m ✅
  │     ├─ R2: emotion_map для player_interacts → нейтральный emotion_tag ✅
  │     ├─ R8: SESSION_REPLACED → сброс stability + emotion_tag ✅
  │     ├─ B.3: add_event дедупликация по event_type+target ✅
  │     └─ R5: "попытаться" → action_type (ожидает правила_agent) ⚠️
  │
  ├─ 3.0 Reaction Layer [НЕ РЕАЛИЗОВАНО — КРИТИЧЕСКИЙ ПРЕДШАГ ДЛЯ D.x]
  │     ├─ ЦЕЛЬ: Физические следствия рождаются в Core, не в LLM
  │     ├─ Проблема: LLM пишет "Люся роняет поднос" → extractor фиксирует
  │     │   Но на том же ходе флаг уже не попадёт в промпт → повтор
  │     ├─ Решение: DecisionResult → ReactionResolver → MicroEvents → State → LLM
  │     │   ├─ threat + low_composure + hands_occupied → drop_object
  │     │   ├─ attack + proximity → interaction_disrupted
  │     │   └─ p_drop = (1 - composure) * activity_fragility
  │     ├─ Выход: micro_events[] → StateApplicator → continuity флаги
  │     ├─ LLM получает: "Люся прервана, поднос больше не в руках"
  │     └─ NarrativeExtractor остаётся как verification, не source
  │
  ├─ 3.1 Spatial Events (R4 Активация) [НЕ РЕАЛИЗОВАНО]
  │     ├─ ЦЕЛЬ: "Подойти" → event_type="proximity_close"
  │     ├─ game_loop.py: генерация событий при пересечении порогов
  │     │   ├─ distance < 1.5m → proximity_close (триггер для диалога)
  │     │   └─ distance > 5.0m → proximity_leave (прерывание контакта)
  │     └─ Зависит: R4 LocalSpace (уже считает расстояния)
  │
  ├─ 3.2 Social Graph (NPC-to-NPC связи) [НЕ РЕАЛИЗОВАНО]
  │     ├─ ЦЕЛЬ: Триггер "ревность" из примера Деревни
  │     ├─ relationship_store.py: расширить с Player-NPC на NPC-NPC
  │     │   └─ relationships: {player: -10, lucy: 0.8}
  │     ├─ Правило в DecisionHub:
  │     │   if player.distance_to(lucy) < 2.0 and my.attachment > 0.5
  │     │   → trigger_jealousy (intent=INTIMIDATE, +0.5 к score)
  │     └─ Зависит: 3.1 (нужны события приближения)
  │
  ├─ 3.3 Proactive Intents (Agenda Loop) [НЕ РЕАЛИЗОВАНО]
  │     ├─ ЦЕЛЬ: NPC действует между ходами игрока (шаг 9 из Мечты)
  │     ├─ game_loop.py: тикер раз в N ходов или при входе в локацию
  │     │   └─ запуск DecisionHub с event_type="world_tick"
  │     ├─ opportunity_engine.py: очередь агенд
  │     │   └─ BLOCK_PATH, AMBUSH, SEEK_ALLY (проактивные интенты)
  │     └─ Зависит: 3.2 (агенда часто строится на связях NPC-NPC)
  │
  └─ 3.4 Social Propagation [НЕ РЕАЛИЗОВАНО]
        ├─ ЦЕЛЬ: Слухи, доносы, давление группы
        ├─ social_engine.py
        ├─ rumor distortion + trust-based propagation
        ├─ decay по хопам
        └─ Зависит: 3.2 (нужна матрица связей для распространения)

██ ФАЗА 4 — ЗАПОЛНЕНИЕ ДЫР В ПРИЧИННОСТИ
═══════════════════════════════════════

  ⚠ АУДИТ РЕАЛЬНОСТИ: ПОЛНОСТЬЮ НЕ РЕАЛИЗОВАНО

  ├─ 4.1 Ego Resistance (R6.4) [НЕ СУЩЕСТВУЕТ]
  │     └─ affinity(player_intent, character_profile) → штрафы за нарушение роли
  │
  └─ 4.2 Fronts (R9) [НЕ СУЩЕСТВУЕТ]
        └─ Давление мира на игрока (зависит от Social Propagation)


┌─────────────────────────────────────────────────────────────────────────────┐
│           АРХИТЕКТУРА ПРОЕКТА (РЕАЛЬНОСТЬ + ДОЛГ)                           │
└─────────────────────────────────────────────────────────────────────────────┘

enigma/
│
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI + startup
│   │   ├── api/                        # ТРАНСПОРТНЫЙ СЛОЙ
│   │   │   ├── routes.py               # REST
│   │   │   ├── routes_stream.py        # SSE
│   │   │   └── routes_debug.py         # God Mode
│   │   │
│   │   ├── models/                     # ЧИСТЫЕ ДАННЫЕ
│   │   │   ├── npc_state.py            # R2.1 NPCState (динамика)
│   │   │   ├── personality.py          # L0 Core & L1 Identity
│   │   │   ├── decision.py             # R2 Контракт DecisionResult
│   │   │   ├── candidates.py           # Кандидаты действий
│   │   │   ├── npc_profile.py          # Профиль из JSON
│   │   │   ├── schemas.py              # Pydantic схемы API
│   │   │   └── psychological.py        # ✅ DistortionProfile, CausalEntry [ШАГ 2b]
│   │   │
│   │   ├── agents/                     # LLM-агенты (legacy, частичный bypass)
│   │   │   ├── dm_agent.py
│   │   │   ├── npc_agent.py            # BYPASSED в R3_DIRECT_MODE
│   │   │   ├── rules_agent.py
│   │   │   └── world_sim_agent.py
│   │   │
│   │   └── services/                   # ЯДРО ЛОГИКИ
│   │       │
│   │       ├── game_loop.py            # ★ КООРДИНАТОР ТАЙМИНГА
│   │       │                           # ✅ legacy paths → commit() [ШАГ 1]
│   │       │
│   │       ├── action/                 # ★★★ DM SYSTEM (реальный путь, НЕ dm/)
│   │       │   ├── dm_orchestrator.py  # Главный фасад
│   │       │   ├── dm_router.py        # Этап 1: Парсинг → Event + insult detection
│   │       │   ├── dm_scene_builder.py # Этап 2: R4 Spatial контекст
│   │       │   ├── object_resolver.py  # Разрешение объектов
│   │       │   └── player_target_extractor.py
│   │       │   └─ [ДОЛГ] dm_validator.py
│   │       │
│   │       ├── npc/                    # R2 — ЯДРО ИНТЕЛЛЕКТА
│   │       │   ├── decision_hub.py     # [ЦЕНТР] Формула score() — НЕ ТРОГАТЬ
│   │       │   ├── state_applicator.py # [ТОЧКА ЗАПИСИ] CausalLedger работает ✅
│   │       │   ├── cognitive_distortion.py  # ✅ Governor добавлен [ШАГ 2a]
│   │       │   │                            # ✅ возвращает DistortionProfile [ШАГ 2b]
│   │       │   ├── perception_filter.py     # R4 Фильтр по distance/LOS
│   │       │   ├── npc_cognition.py         # Фасад когнитивного цикла
│   │       │   ├── npc_state.py             # NPCState структуры
│   │       │   ├── npc_loader.py            # JSON → объекты
│   │       │   ├── life_engine.py           # Data-driven активности ✅
│   │       │   ├── spatial_runtime.py       # R4 Runtime расстояний
│   │       │   ├── location_graph.py        # R4 Граф локаций
│   │       │   ├── threat_assessor.py       # Оценка угрозы
│   │       │   ├── psyche_engine.py         # Психологические режимы
│   │       │   ├── break_progress_engine.py # R8 Прогресс слома
│   │       │   ├── behavior_mask.py         # R8 Маски поведения
│   │       │   ├── reaction_priority.py     # Приоритеты реакций
│   │       │   ├── resolution_engine.py     # R5 Gap System
│   │       │   ├── math_utils.py            # Утилиты
│   │       │   └─ intent_queue.py — НЕ НУЖЕН (логика внутри decision_hub.py)
│   │       │
│   │       # cognition/ и engines/ — НЕ СУЩЕСТВУЮТ (фантомы, удалены из дерева)
│   │       │
│   │       ├── resolution/             # R5 — МЕХАНИКА ИСХОДОВ
│   │       │   └── action_resolver.py  # Диспетчер
│   │       │
│   │       ├── state/                  # R4 — УПРАВЛЕНИЕ МИРОМ
│   │       │   ├── scene_state_manager.py   # Source of Truth
│   │       │   ├── context_builder.py       # shared_context
│   │       │   ├── json_persistence_adapter.py
│   │       │   └── persistence_port.py
│   │       │
│   │       ├── memory/                 # R1 — ПАМЯТЬ
│   │       │   ├── working_memory.py        # Краткосрочная
│   │       │   ├── relationship_store.py    # Матрица отношений
│   │       │   ├── layered_memory.py        # L1/L2/L3
│   │       │   ├── memory_manager.py        # Фасад
│   │       │   ├── resonance_engine.py      # L3 Identity
│   │       │   ├── importance_engine.py     # Вес событий
│   │       │   └── contradiction_resolver.py
│   │       │
│   │       ├── verbalization/          # R3 — СЛОЙ ГОЛОСА
│   │       │   ├── scene_outcome_builder.py # ✅ stance интегрирован [ШАГ B.2]
│   │       │   ├── verbal_stance.py         # ✅ [ШАГ B.2] Intent → Stance mapping
│   │       │   ├── scene_continuity.py      # ✅ [ШАГ B.3/B.4] flags, tension, emotion
│   │       │   ├── scene_to_dm_adapter.py   # Адаптер для DM
│   │       │   ├── verbalization_context.py # Контекст вербализации
│   │       │   └── prompt_loader.py         # Загрузка промптов
│   │       │
│   │       ├── events/                 # Шина событий
│   │       │   ├── event_bus.py
│   │       │   └── event_types.py
│   │       │
│   │       ├── scene/                  # Парсинг нарратива
│   │       │   └── narrative_extractor.py
│   │       │
│   │       ├── simulation/             # Симуляция мира
│   │       │   └── world_state.py
│   │       │
│   │       └── llm/                    # LLM провайдеры
│   │           ├── router.py
│   │           ├── provider.py
│   │           ├── provider_manager.py
│   │           ├── llama_cpp_provider.py
│   │           ├── factory.py
│   │           ├── health.py
│   │           └── parser.py
│   │
│   └── data/                           # PERSISTENCE LAYER
│       ├── insults_ru.json             # Словарь мата для DM Router
│       └── sessions/                   # Сохранения
│
└── frontend/                           # UI / UX LAYER
    └── ui/index.html                   


┌─────────────────────────────────────────────────────────────────────────────┐
│                    DATA FLOW (РЕАЛЬНОСТЬ vs ПЛАН)                           │
└─────────────────────────────────────────────────────────────────────────────┘

RAW INPUT
    │
    ▼
DM SYSTEM (Router → Scene Builder)  ← ✅ РЕАЛИЗОВАНО (без Validator)
    │
    ▼
EventContext (event_type, intensity, witnesses)
    │
    ▼
PERCEPTION FILTER  ← ✅ РЕАЛИЗОВАНО
    │
    ▼
CognitiveDistortionEngine  ← ✅ РЕАЛИЗОВАНО [ШАГ 2a]
    │
    │  Контракт выхода (DistortionProfile — typed dataclass):
    │  DistortionProfile(threat_bias, trust_bias, salience_bias)
    │  Governor: sum(abs) ≤ 1.0
    │
    ▼
DECISIONHUB (PURE SCORER)  ← ✅ РЕАЛИЗОВАНО
    │
    │  Commitment: бонус к текущему + порог смены (threshold)
    │  ✅ switching_cost = f(age, emotion, identity)
    │  Формула: scores[current] += bonus; scores[other] -= cost
    │
    ▼
DecisionResult[]
    │
    ▼
╔═════════════════════════════════════════════════════════════════════════════╗
║  СЛОЙ 1 — ФИЗИЧЕСКАЯ РЕАЛЬНОСТЬ                                             ║
║                                                                             ║
║  StateApplicator  ← ⚠️ РЕАЛИЗОВАНО С ДОЛГОМ                                 ║
║  ├── Объективные веса: trust_delta, stress_delta_effective                  ║
║  ├── CausalLedger пишет CausalEntry (cap=20)                                ║
║  └── ⚠️ source="unknown" для всех записей (StateDeltas не имеет поля)       ║
║                                                                             ║
╚══════════════════════════╦══════════════════════════════════════════════════╝
                           ║
                           ▼
╔═════════════════════════════════════════════════════════════════════════════╗
║  СЛОЙ 2 — СУБЪЕКТИВНАЯ РЕАЛЬНОСТЬ                                           ║
║                                                                             ║
║  _build_psychological_projection()  ← ✅ ВСТРОЕН в scene_outcome_builder    ║
║  ├── Вход: DistortionProfile (typed) [ШАГ 2b]                               ║
║  └── Выход: regime, intensity, stability                                    ║
║                                                                             ║
╚══════════════════════════╦══════════════════════════════════════════════════╝
                           ║
                           ▼
NpcOutcome.psychological
    │
    ▼
DMFrame  ← ✅ РЕАЛИЗОВАНО
    │
    ▼
❌ Social Propagation Engine — НЕ СУЩЕСТВУЕТ
    │
    ▼
LLM (только вербализация, без логики)  ← ✅ РЕАЛИЗОВАНО
    │
    ▼
FINAL TEXT


┌─────────────────────────────────────────────────────────────────────────────┐
│              ПРИОРИТЕТЫ ДЛЯ АРХИТЕКТУРНОЙ ЦЕЛОСТНОСТИ                       │
└─────────────────────────────────────────────────────────────────────────────┘

  ЛОГИКА: Данные → Контракты → Причинность → Интеграции → Эволюция
         Каждый шаг опирается на предыдущий.

  ┌─────────────────────────────────────────────────────────────────────────┐
  │ ШАГ 1: ЗАКРЫТЬ ПУТИ ДАННЫХ ✅ ЗАВЕРШЁН                                  │
  │                                                                         │
  │ Pipeline Stitch — legacy paths через commit()                           │
  │ ├─ game_loop.py _apply_npc_state_updates → commit() ✅                  │
  │ └─ game_loop.py _write_npc_memory → commit() ✅                         │
  └─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │ ШАГ 2: БАЗОВЫЕ КОНТРАКТЫ ✅ ЗАВЕРШЁН                                    │
  │                                                                         │
  │ 2a. Governor для CognitiveDistortion ✅                                 │
  │     └─ cognitive_distortion.py: scale = 1/total если total > 1.0        │
  │                                                                         │
  │ 2b. models/psychological.py ✅                                          │
  │     ├─ DistortionProfile (frozen dataclass, from_dict/to_dict) ✅       │
  │     ├─ CausalEntry (dataclass для Шага 3) ✅                            │
  │     ├─ cognitive_distortion.py → возвращает DistortionProfile ✅        │
  │     └─ scene_outcome_builder.py → принимает DistortionProfile ✅        │
  └─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │ ШАГ 3: ПРИЧИННОСТЬ ✅ ЗАВЕРШЁН                                          │
  │                                                                         │
  │ Causal Ledger — паспорт каждого изменения состояния                     │
  │ ├─ state_applicator.py: пишет CausalEntry с каждой дельтой              │
  │ ├─ npc_state.py: causal_ledger: List[Any], cap=20                       │
  │ └─ models/psychological.py: CausalEntry dataclass                       │
  └─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │ ШАГ 4: ИНТЕГРАЦИИ СУЩЕСТВУЮЩЕГО КОДА ✅ ЗАВЕРШЁН                        │
  │                                                                         │
  │ R8 Behavior Masks → DecisionHub                                         │
  │ ├─ decision_hub.py: постфильтр intent по маске слома                    │
  │ ├─ COLLAPSE → IDLE, FAKE_SUBMISSION → TALK, BETRAYAL → OBSERVE          │
  │ └─ Маска НЕ меняет score, переопределяет финальный intent               │
  └─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │ ШАГ 5: ЭВОЛЮЦИЯ ФОРМУЛ ✅ ЗАВЕРШЁН                                      │
  │                                                                         │
  │ Commitment Bonus + switching_cost                                       │
  │ ├─ decision_hub.py: формула scores[current] += bonus; other -= cost     │
  │ ├─ cost = BASE + age + emotion + identity                               │
  │ └─ Отдельный intent_queue.py не нужен — state.intent достаточен         │
  └─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │ ШАГ A: ВОССТАНОВИТЬ ПРИЧИННОСТЬ ✅ ЗАВЕРШЁН                      │
  │                                                                     │
  │ A.1 intensity: Router → DecisionHub ✅                             │
  │ ├─ game_loop.py:519 → dm_result.event_context (уже с intensity)   │
  │ └─ Результат: "фляга"=0.2, "жена видел"=0.6, "на колени"=0.7    │
  │                                                                     │
  │ A.2 Router паттерны: расширить классификацию ✅                    │
  │ ├─ dm_router.py → player_threatens_indirect добавлен              │
  │ ├─ "на колени", "замолчи", "убью" → threatens                    │
  │ └─ "жена видел с незнакомцем" → threatens_indirect                │
  │                                                                     │
  │ A.3 StateDeltas.source ✅                                         │
  │ ├─ decision_hub.py → поле source добавлено                        │
  │ ├─ _compute_deltas → source=event.event_type                      │
  │ └─ CausalEntry теперь: source="player_insults" вместо "unknown"   │
  └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │ ШАГ B: ВЕРБАЛИЗАЦИОННЫЙ СЛОЙ ✅ ЗАВЕРШЁН + КАЛИБРОВКА            │
  │                                                                     │
  │ Цель достигнута: LLM исполняет stance, не интерпретирует intent.    │
  │                                                                         │
  │ B.1 Segregate Agency [CRITICAL — simplest, highest impact]           │
  │ ├─ Файл: dm_agent.py (DM prompt)                                     │
  │ ├─ Контракт в prompt:                                                │
  │ │   ALLOWED: NPC actions, environment (только из Python)            │
  │ │   FORBIDDEN: Player actions, confirming unverified claims          │
  │ │   IF "I killed X" → treat as claim, not fact                      │
  │ ├─ Эффект: убирает 80% галлюцинаций, ломает "LLM как автор"        │
  │ └─ Сложность: тривиальная (текст в prompt)                            │
  │                                                                         │
  │ B.2 Intent → Stance Mapping ✅                                      │
  │ ├─ verbal_stance.py: VerbalStance + stance_from_decision() ✅       │
  │ ├─ Маппинг: intent+stress+fear+trust → stance/tone/urgency ✅      │
  │ │   TALK + high stress + high pride → confront + aggressive         │
  │ │   IDLE + collapse → dissociated                                   │
  │ ├─ [КАЛИБРОВКА]: Добавлены стейсы для report/help/trade ✅          │
  │ │   (раньше падали в дефолтный observe/neutral — терялся смысл)    │
  │ └─ Ключ: LLM НЕ интерпретирует intent → он ИСПОЛНЯЕТ stance        │
  │                                                                         │
  │ B.3 Scene Continuity Cache ✅                                      │
  │ ├─ scene_continuity.py: flags, events, facts, tension ✅            │
  │ ├─ game_loop.py: обновление из дельт + flags по event_type ✅      │
  │ ├─ [КАЛИБРОВКА]: to_prompt_block() теперь выводит recent_events ✅ │
  │ │   (раньше данные писались, но не попадали в DM prompt)            │
  │ └─ Эффект: убирает repetition, фиксирует "правду сцены"            │
  │                                                                     │
  │ B.4 Micro-History ✅                                               │
  │ ├─ scene_continuity.py: emotional_vector (trust/tension/confusion) │
  │ ├─ Инерция: 70% текущее + 30% новое                               │
  │ ├─ [КАЛИБРОВКА]: порог to_emotional_line() снижен с 0.1 до 0.05 ✅│
  │ │   (при одном событии trust_d/50 ≈ 0.035 — фильтровалось)        │
  │ └─ Эффект: убирает скачки, сохраняет причинность                    │
  │                                                                     │
  │ [КАЛИБРОВКА РЕАКТИВНОСТИ]:                                         │
  │ ├─ _context_relevance(): player_interacts даёт +0.5 к TALK/OBSERVE │
  │ ├─ _context_relevance(): player_interacts даёт -0.4 к WARN/REPORT  │
  │ └─ Результат: "Привет" больше не вызывает intent=report у Торнинга │
  └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │ ШАГ C: СТАБИЛИЗАЦИЯ ЯДРА (Python→Python) ← ТЕКУЩИЙ                 │
  │                                                                         │
  │ C.1 Distortion → DecisionHub                                          │
  │ ├─ Формула: effective_event = event * distortion                      │
  │ │         ИЛИ score(action) += distortion_bias                        │
  │ ├─ Distortion = модификатор восприятия, не источник                   │
  │ └─ Зависит: A (нужна корректная intensity)                           │
  │                                                                         │
  │ C.2 BehaviorMask: от override к constraint                           │
  │ ├─ Формула: intent_score *= mask_modifier                            │
  │ │         ИЛИ allowed_intents = constrained_set                      │
  │ └─ Зависит: B.2 (stance должен учитывать mask)                      │
  └─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │ ШАГ D: ПРОАКТИВНЫЙ СЛОЙ (ФАЗА 3 В МАСТЕР-ПЛАНЕ)                     │
  │                                                                         │
  │ ПРЕЖДЕ ЧЕМ D.1 (Social Propagation) — нужны 3 фундаментальных слоя: │
  │                                                                         │
  │ D.0.1 Spatial Events                                                  │
  │ ├─ game_loop генерирует event_type при изменении distance            │
  │ └─ Превращает "подойти" из текста в триггер для DecisionHub         │
  │                                                                         │
  │ D.0.2 Social Graph                                                     │
  │ ├─ NPC-NPC связи (ревность, привязанность, вражда)                   │
  │ └─ Правила: "если игрок рядом с X, а я привязан к X → триггер"      │
  │                                                                         │
  │ D.0.3 Agenda Loop                                                     │
  │ ├─ World Tick → DecisionHub для каждого NPC                          │
  │ └─ Проактивные интенты: BLOCK_PATH, AMBUSH, SEEK_ALLY               │
  │                                                                         │
  │ D.1 social_engine.py (после D.0.x)                                   │
  │ D.2 rumor distortion + trust-based propagation                       │
  │ D.3 decay по хопам                                                   │
  └─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │ ШАГ E+: ФАЗА 4 — ЗАПОЛНЕНИЕ ДЫР                                     │
  │                                                                         │
  │ E.1 Ego Resistance                                                    │
  │     ├─ Зависит: C (нужна стабильная формула score)                   │
  │     └─ Зависит: D (нужно давление мира)                              │
  │                                                                         │
  │ E.2 Fronts                                                            │
  │     └─ Зависит: D (Social Propagation)                               │
  └─────────────────────────────────────────────────────────────────────────┘

  ── ПАРАЛЛЕЛЬНО (не блокирует) ──
  ├─ Удалить/закомментировать BODY_TRAIT, ROLE_MARKER (мёртвый код)
  └─ dm_validator.py (когда понадобится)

================================================================================

## 0. ГЛАВНЫЙ ПРИНЦИП (НЕПРИКОСНОВЕНЕН)

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
ХАРДКОД отдельных NPC ЗАПРЕЩЕН!!! Система должна быть маштабируемой
```
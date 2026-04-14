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

  ├─ R4 PerceptionFilter: distance >= 5.0 не фильтрует ✅ ИСПРАВЛЕНО
  │     Лог: 5/5 NPC при dist=5.0 пропустили фильтр
  │     Корень: graph-based ветка не имела cap 15m
  │     Фикс: perception_filter.py:150 — добавлен distance >= 15.0
  │
  ├─ R2 DecisionHub: player_interacts → intent=flee ✅ ИСПРАВЛЕНО
  │     Лог: "Привет, Торнинг" → intent=flee при stress_d=0.0
  │     Корень: emotion_map не содержал player_interacts
  │     Фикс: decision_hub.py:985 — player_interacts → (NEUTRAL, +2.0)
  │
  ├─ R8 Stability: не сбрасывается при смене сессии ✅ ИСПРАВЛЕНО
  │     Лог: stab=0.75 при первой смене игрока (SESSION_REPLACED)
  │     Корень: is_session_start не сбрасывал emotion и behavior_mask
  │     Фикс: game_loop.py:557 — полный сброс: stress=0, emotion=NEUTRAL, mask=NONE
  │
  ├─ R5 Resolution: нет бросков для действий ✅ ИСПРАВЛЕНО
  │     Лог: "пытаюсь взять меч" → нет провала, DM описывает попытку
  │     Корень: rules_agent не получал классификацию из Router
  │     Фикс: dm_router.py — action_mode (VERBAL/PHYSICAL) + get_rules_action_type()
  │           game_loop.py — классификация передаётся в rules_agent, player_success из результата
  │
  ├─ B.3 Continuity: events дублируются ✅ ИСПРАВЛЕНО
        Лог: "Началась драка" ×2 при разных event_type
        Корень: add_event не проверяет дубликаты
        Фикс: scene_continuity.py:62 — if event in self.recent_events: return
  │
  └─ AsyncIO: Semaphore bound to different event loop ✅ ИСПРАВЛЕНО
        Лог: Semaphore bound to different event loop (повторяющийся)
        Корень: Semaphore создавался в __init__ при старте, использовался в другом loop
        Фикс: router.py:250 — ленивая инициализация _vram_semaphore в текущем loop

  ├─ R1 Memory Core ✅
  │     ├─ L1 Numerical (числовые веса: trust, fear, stress — только для DecisionHub)
  │     ├─ L2 Event (история с деградацией: clarity, confidence, stage)
  │     ├─ L3 Identity (черты из ResonanceEngine — абстрактные воспоминания → traits)
  │     ├─ Clarity влияет на вербализацию (>0.8 конкретика, <0.4 абстракция)
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
  │     ├─ Psychological Projection (мост Python → LLM)
  │     │   ├─ 4 оси: arousal, stance, stability, mode
  │     │   ├─ Числа НЕ передаются в LLM (только собранная строка ~15-20 атомов)
  │     │   └─ Пример: "напряжён, защищается, поведение нестабильно"
  │     ├─ BehaviorMode: STRICT/FLEXIBLE/REACTIVE/SILENT
  │     ├─ R3_DIRECT_MODE: DM = единственный источник речи
  │     ├─ SceneOutcomeBuilder → SceneOutcome → DMFrame
  │     └─ 180 тестов
  │
  ├─ R4 Spatial System ✅
  │     ├─ LocationGraph + LocationNode
  │     ├─ LocalSpace (расстояния реальны: 2.5-4.6м)
  │     └─ PerceptionFilter (PERCEPTION_RADIUS по tier, cap 15m) ✅ ИСПРАВЛЕНО
  │
  ├─ R5 Resolution Layer ✅
  │     ├─ Gap System: actual - expected → стресс/трейты
  │     ├─ Принцип: Кубик НЕ решает, фиксирует отклонение от ожидания
  │     ├─ Формула: clamp(roll * 0.65 + bias * 0.35, 0.05, 0.95)
  │     ├─ Randomness ТОЛЬКО в ResolutionEngine (запрещено в DecisionHub)
  │     └─ Physical actions → rules_agent (бросок кубиков) ✅ ИТЕРАЦИЯ 1
  │
  ├─ R8 Break System ✅ [РЕФАКТОРИНГ ЗАВЕРШЁН — ИТЕРАЦИЯ 1]
  │     ├─ BreakProgressEngine (5 стадий: Сопротивление → Деформация) ✅
  │     ├─ models/behavior_mask.py (структуры определены) ✅ [ПЕРЕНЕСЁН]
  │     ├─ Триггер: pressure (fear + stress + failures - support) > willpower
  │     ├─ Маски: TRUE_SUBMISSION, FAKE_SUBMISSION, BETRAYAL, RESISTANCE, COLLAPSE
  │     ├─ Opportunity Score (окно для тайного действия): attention↓ + distance + weapon_access
  │     ├─ Защита: Resistance scaling, Cost of Control, Необратимость (recovery << decay)
  │     └─ Интеграция в DecisionHub ✅ (modifier, не override)
  │           Формула: intent_score *= mask_modifier
  │           COLLAPSE: IDLE * (1.0 + 2.0*intensity), остальные * suppression
  │           FAKE_SUBMISSION: ATTACK * 0.0, TALK * (1.0 + 0.5*intensity)
  │           BETRAYAL: HELP * 0.0, OBSERVE * (1.0 + 0.5*intensity)
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

██ РЕФАКТОРИНГ СТРУКТУРЫ [ЗАВЕРШЁН]
═══════════════════════════════════════

  ├─ Миграция npc_state.py → models/ ✅
  │     ├─ npc_state.py (542 строки) → models/npc_state.py
  │     ├─ behavior_mask.py (64 строки) → models/behavior_mask.py
  │     ├─ 20+ импортов обновлено в services/, models/, tests/
  │     ├─ 418 тестов прошли без изменений
  │     └─ Контракт #7 обновлён: путь models/npc_state.py
  │
  └─ Создание core/constants.py ✅
        ├─ Кросс-модульные константы (PERCEPTION, STATE_CAPS, RESOLUTION...)
        ├─ 6 модулей помечены TODO для будущей миграции локальных констант
        └─ Подготовка для Калибровки

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
│                 1.5 НЕПРИКОСНОВЕННЫЕ КОНТРАКТЫ СИСТЕМЫ                       │
└─────────────────────────────────────────────────────────────────────────────┘

██ ГЛАВНЫЙ ПРИНЦИП (НЕПРИКОСНОВЕНЕН)
══════════════════════════════════════
  LLM НЕ ПРИНИМАЕТ РЕШЕНИЯ. LLM НЕ МЕНЯЕТ СОСТОЯНИЕ. LLM НЕ ПОЛУЧАЕТ ЧИСЛА.
  Python = интеллект (DecisionHub). LLM = голос (вербализация).
  Хардкод отдельных NPC запрещён. Поведение вытекает из профиля.

██ КЛЮЧЕВЫЕ КОНТРАКТЫ R1-R8 (НЕ ЛОМАТЬ)
══════════════════════════════════════
  1. DecisionHub    — ТОЛЬКО читает. НЕ пишет. НЕ вызывает LLM.
  2. StateApplicator — ТОЛЬКО пишет через apply(). НЕ принимает решений.
  3. NPCState       — иммутабелен в рантайме. apply() возвращает копию.
  4. LLM            — ТОЛЬКО вербализация. Получает строки, не числа.
  5. GameLoop       — живёт в app.state. НЕ в глобальном синглтоне.
  6. npc_profile.py — ТОЛЬКО L0 типы (immutable, из JSON).
  7. models/npc_state.py   — ВСЕ L1/L2 типы и адаптеры.
  8. SceneStateManager.commit() — ЕДИНСТВЕННАЯ точка сохранения.
  9. NarrativeFacts — max 2 факта. frozen. НЕ участвуют в логике.
  10. TierConfig    — статичен. Только controlled respawn.

┌─────────────────────────────────────────────────────────────────────────────┐
│                       2. ЧТО ПРЕДСТОИТ СДЕЛАТЬ                              │
└─────────────────────────────────────────────────────────────────────────────┘

██ ОТБРАКОВАННЫЕ ИДЕИ (ЗАЩИТА ОТ РЕГРЕССА)
═══════════════════════════════════════

  ├─ GOAP (планировщик действий) → UX текстовой RPG не выдержит 5 тиков планирования
  ├─ intent_queue.py → логика инерции внутри decision_hub (commitment + cost)
  ├─ npc_agent.py как основной путь → Bypassed в R3_DIRECT_MODE
  ├─ Точные числа (stress=85) в LLM-промпте → пробивает Fog of War (запрещено навсегда)
  ├─ Randomness в DecisionHub → двойной RNG (случайность только в ResolutionEngine)
  ├─ BODY_TRAIT / ROLE_MARKER → мёртвый код (будет удалён при чистке)
  └─ Runtime TierConfig upgrade → нарушает предсказуемость (запрещено)

██ ФУНДАМЕНТАЛЬНЫЙ КОНТРАКТ: STATIC VS RUNTIME [НОВОЕ ПРАВИЛО]
═════════════════════════════════════════════════════════════════════════════

  ⚠ ПРАВИЛО: Данные разделены на две непересекающиеся зоны.
  Нарушение границы ведёт к невозможности масштабирования и оффлайн-симуляции.

  ├─ STATIC (config/) — задается разработчиком, не меняется в рантайме
  │     ├─ identity (имя, происхождение, базовая личность L0)
  │     ├─ potential_roles (чем теоретически может заниматься)
  │     ├─ visual.baseline (базовая внешность)
  │     └─ ПРИНЦИП: "Кто он есть по природе"
  │
  └─ RUNTIME (saves/ + NPCState) — мутирует в процессе игры
        ├─ current_role (текущая профессия, берется из archetype)
        ├─ visible_markers (текущая внешность: шрамы, одежда)
        ├─ psyche (стресс, травмы, willpower)
        ├─ resources (золото, инвентарь)
        ├─ relationships (текущие отношения)
        ├─ temporary_drives (временные цели: месть, жадность)
        └─ ПРИНЦИП: "Чем он стал под давлением мира"

██ ФАЗА 1.5 — РЕФАКТОРИНГ КОНФИГОВ (ARCHETYPE SYSTEM) ✅ ЗАВЕРШЕНА
═════════════════════════════════════════════════════════════════════════════

  ├─ 1.5.3 Перенос runtime в NPCState ✅ ШАГ 0.8 ЗАВЕРШЁН
  │     ├─ major_npcs.json очищен от runtime (stress, trust, memory_trace, social_stats...)
  │     ├─ commit() → save_npc_runtime() в sessions/{id}/npc_runtime.json
  │     ├─ PersistencePort расширен: save_npc_runtime / load_npc_runtime
  │     ├─ LifeEngine.save_npcs() отключён (писал в major_npcs.json)
  │     ├─ save_npcs_func удалён из GameLoop (мёртвый код)
  │     └─ Бэкап: major_npcs.json.bak
  │
  ├─ 1.5.1 Структура config/npc/ ✅ ЗАВЕРШЕНА
  │     ├─ archetypes/ (_base_humanoid, tavern_keeper, guard, maid, merchant, thief)
  │     ├─ mixins/ (veteran)
  │     ├─ individuals/ (tornin, borko, lusya, goran, shadow — ТОЛЬКО дельта)
  │     └─ social/ (village_relations.json — статичные связи)
  │
  ├─ 1.5.2 npc_loader.py — наследование ✅ ЗАВЕРШЁН
  │     ├─ _deep_merge() — рекурсивный мерж с приоритетом override > base
  │     ├─ _load_archetype_chain() — base → archetype → mixins → individual
  │     ├─ load_npc_profiles_from_config() — загружает всех из config/npc/individuals/
  │     └─ load_social_base() — статичные связи из config/npc/social/
  │
  ├─ 1.5.3b Мерж runtime при загрузке ✅ ЗАВЕРШЁН
  │     ├─ load_npcs_merged() — static из config/ + runtime overlay
  │     ├─ _RUNTIME_PSYCHE_KEYS / _RUNTIME_TOP_LEVEL_KEYS — явные whitelist runtime полей
  │     ├─ _apply_runtime_overlay() — накладывает runtime без порчи static
  │     ├─ game_loop_builder.py — переключён на load_npcs_merged()
  │     └─ major_npcs.json больше не используется для загрузки
  │
  └─ 1.5.4 Тест масштабирования ✅ ЗАВЕРШЁН
        ├─ blacksmith_orm: 13 строк JSON → полный NPC (tavern_keeper + veteran)
        └─ Правка archetype → propagation ко всем наследникам

  ЗАВИСИМОСТИ:
  ├─ Разблокирована: ФАЗА 2.0 (CharacterFilter — values можно добавить в archetype)
  ├─ Разблокирована: ФАЗА 2.4-ECO (Economic Engine — needs можно добавить в archetype)
  └─ Совместима: Текущие R1-R8 (работают через load_npcs_merged)

██ ФАЗА 2.0 — АРХИТЕКТУРА АГЕНТОВ (CharacterFilter) ✅ ЗАВЕРШЕНА
═════════════════════════════════════════════════════════════════════════════

  ✅ Система ≠ аватар: персонаж имеет ценности и может сопротивляться
  ✅ ЗАВИСИМОСТЬ: ФАЗА 1.5 (archetype system + static/runtime split)

  ├─ 2.0.1 CharacterProfile ✅ ЗАВЕРШЁН
  │     ├─ models/character.py — CharacterProfile + ValueSet (frozen)
  │     ├─ self_integrity ∈ [0..1] — способность сопротивляться
  │     ├─ values: ValueSet с conflict_score() — расчёт конфликта действий
  │     ├─ social_constraints: Dict[str, float] — усвоенные нормы
  │     ├─ erosion_accumulator + apply_erosion() — деградация от RESIST
  │     ├─ Связь: character_id = CharacterSheet.name (hot-seat режим)
  │     └─ PERSISTENCE: character_profiles.json (отдельно от characters.json)
  │
  ├─ 2.0.2 CharacterFilter ✅ ЗАВЕРЧЁН
  │     ├─ services/character/character_filter.py
  │     ├─ FilterOutcome: ACCEPT / MODIFY / RESIST / REFUSE
  │     ├─ Формула: base_resistance * integrity_modifier * constraint_modifier * intensity
  │     ├─ ACTION_VALUE_CONFLICTS: event_type → violation по ценностям
  │     ├─ Пороги: 0.3/0.6/0.9 (проверены на рыцаре/наёмнике/сломленном)
  │     └─ НЕ ИСПОЛЬЗУЕТ LLM — чистый Python scorer
  │
  ├─ 2.0.3 Character→NPC Trust ✅ ЗАВЕРЧЁН
  │     ├─ npc_trust: Dict[str, float] в CharacterProfile
  │     ├─ get_npc_trust() / adjust_npc_trust() с cap [-1.0, 1.0]
  │     ├─ Отдельный от NPC→player (DecisionHub._relationship_modifier)
  │     └─ Persistence: to_dict/from_dict включает npc_trust
  │
  ├─ 2.0.4 Интеграция в Pipeline ✅ ЗАВЕРЧЕНА
        ├─ Точка вставки: game_loop.py:534 (после hub_event, до NPC цикла)
        ├─ CharacterService расширен: get_profile/upsert_profile/get_or_create_profile
        ├─ RESIST/REFUSE → hub_event=None → NPC цикл пропускается
        ├─ shared_context["character_filter"] → DM видит результат
        └─ Non-blocking: ошибки фильтра не ломают pipeline

  ЗАВИСИМОСТИ:
  ├─ ТРЕБУЕТ: ФАЗА 1.5.1 + 1.5.2 (values в archetype — структура + loader)
  ├─ ТРЕБУЕТ: ШАГ 0.5 (Reaction Layer) ✅ ЗАВЕРШЁН
  ├─ ТРЕБУЕТ: ШАГ 0.8 (static/runtime разделение) ✅ ЗАВЕРШЁН
  ├─ Блокирует: ФАЗА 4 (давление мира требует субъекта восприятия)
  └─ Не блокирует: ШАГИ A-E (они работают с NPC, не с персонажем)

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

  [АУДИТ ПО ЛОГАМ]: См. раздел "АУДИТ РЕАЛЬНОСТИ" (5 из 6 исправлено, B.3 в процессе)
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
██ ФАЗА 2.4-ECO — ЭКОНОМИЧЕСКИЙ ДВИЖОК [НЕ РЕАЛИЗОВАНО]
═════════════════════════════════════════════════════════════════════════════

  ПРИНЦИП: NPC имеют потребности → потребности генерируют кандидатов →
           кандидаты решаются через транзакции. Без скриптовых квестов.

  ├─ 2-ECO.1 models/economy.py [НЕ СУЩЕСТВУЕТ]
  │     ├─ Need (type, urgency, budget_share, skill_required)
  │     ├─ Transaction (actor, target, goods, payment, reason)
  │     └─ EconomicProfile (income_sources, needs, resources)
  │
  ├─ 2-ECO.2 need_calculator.py [НЕ СУЩЕСТВУЕТ]
  │     ├─ Динамический urgency от neglected_ticks
  │     ├─ Кап: urgency_max = 0.95
  │     └─ Базовый доход от "мирной жизни" (анти-collapse)
  │
  ├─ 2-ECO.3 opportunity_engine.py [НЕ СУЩЕСТВУЕТ]
  │     ├─ Вход: List[Need] с urgency > 0.6
  │     ├─ Если есть ресурсы → Candidate(OFFER_JOB, wage=X)
  │     ├─ Если нет ресурсов → Candidate(REQUEST_SERVICE, ask_ally)
  │     └─ Если нет союзников → Candidate(REDIRECT, target=best_match)
  │
  ├─ 2-ECO.4 transaction_engine.py [НЕ СУЩЕСТВУЕТ]
  │     ├─ NPC-to-NPC сделки (sale, employment, bribe)
  │     ├─ Валидация ресурсов до сделки
  │     └─ Запись в CausalLedger при успехе
  │
  └─ 2-ECO.5 Интеграция в DecisionHub
        ├─ Новые кандидаты: OFFER_JOB, REQUEST_SERVICE, TRADE, SELL_PROPERTY
        └─ Формула: score += resource_capability * 0.2

  ЗАВИСИМОСТИ:
  ├─ ТРЕБУЕТ: ФАЗА 2.4-ECO (needs из archetype)
  ├─ ТРЕБУЕТ: ФАЗА 3.2 Social Graph (поиск союзников через граф)
  └─ Блокирует: ФАЗА 4-ROLE (смена роли требует ресурсов)

  ТЕСТОВЫЙ СЦЕНАРИЙ:
  ├─ Торнин: need=cleanliness urgency=0.8
  ├─ Генерирует Candidate(OFFER_JOB, wage=10)
  ├─ Игрок спрашивает о работе → предлагает
  └─ Игрок не подходит → REDIRECT к Люсе (debt=20, навык есть)
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
  │ ШАГ E+: ФАЗА 5-PRESSURE                                           │
  │                                                                     │
  │ E.1 Fronts (R9)                                                    │
  └─────────────────────────────────────────────────────────────────────┘

██ ФАЗА 3 — ОТ РЕАКТИВНОГО К ПРОАКТИВНОМУ МИРУ
═══════════════════════════════════════════════════

  ┌─────────────────────────────────────────────────────────────────────┐
  │ ЧТО МЕШАЕТ "МЕЧТЕ" (Диагностика по 10 шагов Деревни)             │
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
  │                                                                     │
  │ ПРОБЛЕМА 4: НЕТ ЭКОНОМИКИ (🆕 из ROADMAP2)                        │
  │ NPC не могут нанимать, торговать, менять профессию.               │
  │ "Месть Торнина" невозможна: нет продажи таверны, нет смены роли.  │
  └─────────────────────────────────────────────────────────────────────┘

  ├─ 2.5 БAGFIXES (R2/R4/R5/R8/Continuity)
  │     └─ См. раздел "АУДИТ РЕАЛЬНОСТИ" (R2/R4/R8 ✅, B.3/R5 ⚠️)
  │
├─ 3.0 Reaction Layer ✅ [ШАГ 0.5 ЗАВЕРШЁН + АУДИТ]
│     ├─ services/reaction/micro_event.py — MicroEvent + MicroEventType
│     ├─ services/reaction/reaction_rules.py — 3 правила (drop, disrupt, grip)
│     ├─ services/reaction/reaction_resolver.py — фасад
│     ├─ game_loop.py — вызов после StateApplicator
│     ├─ game_loop.py — MicroEvents → SceneContinuity флаги/события
│     └─ narrative_extractor.py — REACTION_ONLY_EVENTS реестр (drop/break не из текста LLM)
  │
  ├─ 3.1 Spatial Events (R4 Активация) [НЕ РЕАЛИЗОВАНО]
  │     ├─ ЦЕЛЬ: "Подойти" → event_type="proximity_close"
  │     ├─ services/spatial/spatial_events.py — генератор событий
  │     │   ├─ distance < 1.5m → proximity_close (триггер для диалога)
  │     │   └─ distance > 5.0m → proximity_leave (прерывание контакта)
  │     └─ Зависит: R4 LocalSpace (уже считает расстояния)
  │
  ├─ 3.2 Social Graph (NPC-to-NPC связи) [НЕ РЕАЛИЗОВАНО]
  │     ├─ services/social/social_graph.py — матрица связей
  │     │   └─ Relationship: trust, affection, fear, debt, shared_secrets
  │     ├─ Загрузка из config/npc/social/village_relations.json
  │     ├─ Runtime мутации сохраняются в saves/session/social_graph_state.json
  │     ├─ Триггер "ревность" из примера Деревни:
  │     │   if player.distance_to(lucy) < 2.0 and graph[tornin][lucy].affection > 0.5
  │     │   → Candidate(INTIMIDATE, reason=jealousy)
  │     └─ Зависит: 3.1 (нужны события приближения)
  │
  ├─ 3.3 Social Propagation [НЕ РЕАЛИЗОВАНО]
  │     ├─ services/social/social_propagation.py — распространение событий
  │     ├─ Алгоритм: max_hops=3, decay=0.8^hop, freq_cap=1/5 тиков
  │     ├─ Искажение: trust_bias (враги преувеличивают негатив)
  │     ├─ Генерирует MicroEvents для удалённых NPC (узнал слух)
  │     └─ Зависит: 3.2 (нужна матрица связей)
  │
  ├─ 3.4 Proactive Intents (Agenda Loop) [НЕ РЕАЛИЗОВАНО]
  │     ├─ ЦЕЛЬ: NPC действует между ходами игрока (шаг 9 из Мечты)
  │     ├─ game_loop.py: WorldTickEngine — тикер раз в N ходов
  │     │   └─ Для каждого NPC: DecisionHub(event_type="world_tick")
  │     ├─ Новые проактивные кандидаты:
  │     │   ├─ BLOCK_PATH, AMBUSH, SEEK_ALLY (базовые)
  │     │   ├─ OFFER_JOB, REQUEST_SERVICE (🆕 из Economic Engine)
  │     │   ├─ SPREAD_RUMOR, CALL_FOR_HELP (🆕 из Social Graph)
  │     │   └─ CHANGE_ROLE (🆕 из Role Transition)
  │     └─ Зависит: 3.2 + 3.3 + ФАЗА 2.4-ECO
  │
  └─ 3.5 Reputation Engine [НЕ РЕАЛИЗОВАНО]
        ├─ services/social/reputation_engine.py — репутация в фракциях
        ├─ Загрузка фракций из config/world/factions.json
        ├─ Действия NPC влияют на репутацию его фракции
        └─ Зависит: 3.3 (propagation несёт информацию о действиях)

██ ФАЗА 4-ROLE — СМЕНА РОЛЕЙ [НЕ РЕАЛИЗОВАНО]
═══════════════════════════════════════════════════

  ПРИНЦИП: Профессия NPC — не приговор. Обстоятельства меняют людей.

  ├─ 4-ROLE.1 role_transition.py [НЕ СУЩЕСТВУЕТ]
  │     ├─ can_transition(npc, target_role): проверка required_background
  │     ├─ execute_transition(): смена current_role, activity_map из archetype
  │     ├─ Запись в role_history + CausalLedger
  │     └─ Обновление SocialGraph (другие NPC реагируют на новую роль)
  │
  ├─ 4-ROLE.2 temporary_drives в NPCState [НЕ СУЩЕСТВУЕТ]
  │     ├─ Генерация: CausalEntry с emotional_impact > 0.7 → drive
  │     ├─ Cap: 3 active drives (старый удаляется)
  │     └─ Влияние на DecisionHub: drive.urgency модифицирует score
  │
  └─ 4-ROLE.3 Интеграция с Economic Engine
        ├─ Смена роли может требовать ресурсы (transition_cost)
        ├─ Сделки для накопления ресурсов (продажа имущества)
        └─ Проверка: enough resources → can_transition → execute

  ЗАВИСИМОСТИ:
  ├─ ТРЕБУЕТ: ФАЗА 1.5 (archetypes с transition_cost)
  ├─ ТРЕБУЕТ: ФАЗА 2.4-ECO (transaction_engine для накопления ресурсов)
  ├─ ТРЕБУЕТ: ФАЗА 3.2 (social_graph для реакции на смену роли)
  └─ ТЕСТ: "Месть Торнина" — полный цикл от смерти Люси до роли mercenary

██ ФАЗА 5-PRESSURE — ДАВЛЕНИЕ МИРА НА ПЕРСОНАЖА
═══════════════════════════════════════

  ⚠ АУДИТ РЕАЛЬНОСТИ: ПОЛНОСТЬЮ НЕ РЕАЛИЗОВАНО
  ⚠ ПРЕДУСЛОВИЕ: ФАЗА 2.0 (CharacterFilter) + ФАЗА 3.3 (Propagation)

  ├─ 5.1 Fronts (R9) [НЕ СУЩЕСТВУЕТ]
  │     ├─ Давление мира на персонажа (не на игрока!)
  │     ├─ Front = маска, которую персонаж носит для мира
  │     ├─ Формируется из: репутация (3.5) + слухи (3.3) + фракционные давления
  │     └─ Зависит: ФАЗА 3.3 (Social Propagation), ФАЗА 3.5 (Reputation)
  │
  ├─ 5.2 Consequence Accumulation [НЕ СУЩЕСТВУЕТ]
  │     ├─ Накопленные последствия RESIST действий из CharacterFilter
  │     ├─ Влияют на self_integrity (истощение воли)
  │     ├─ "Слишком часто подчинялся → легче подчиниться снова"
  │     └─ Зависит: ФАЗА 2.0 (CharacterFilter генерирует RESIST)
  │
  └─ 5.3 Identity Erosion [НЕ СУЩЕСТВУЕТ]
        ├─ Противоположность NPC Break System (R8)
        ├─ NPC ломается под давлением мира (внешний слом)
        ├─ Персонаж теряет себя под давлением СОБСТВЕННЫХ компромиссов (внутренний слом)
        ├─ Связь с Temporary Drives: erosion может порождать drives (desperation)
        └─ Зависит: 5.2 + ФАЗА 4-ROLE (temporary_drives)

  ПРИМЕЧАНИЕ: Ego Resistance УДАЛЁН — является ЧАСТЬЮ CharacterFilter (2.0.2)

██ ФАЗА 6-WORLD — PROACTIVE WORLD (МИР БЕЗ ИГРОКА)
═══════════════════════════════════════

  ⚠ АУДИТ РЕАЛЬНОСТИ: Фундамент заложен в ФАЗА 3.4 (Agenda Loop)
  ⚠ ЦЕЛЬ: Полная оффлайн-симуляция

  ├─ 6.1 WorldTickEngine [НЕ СУЩЕСТВУЕТ]
  │     ├─ Тикер: раз в N ходов или при входе в локацию
  │     ├─ Симуляция: каждый NPC → DecisionHub(event_type="world_tick")
  │     └─ Результат: транзакции, смена ролей, перемещения — без участия игрока
  │
  ├─ 6.2 Оффлайн-мутации [НЕ СУЩЕСТВУЕТ]
  │     ├─ NPC торгуют, ссорятся, меняют работу за время отсутствия игрока
  │     ├─ Сохранение результатов в saves/session/
  │     └─ SceneContinuity: факты о произошедшем ("Торнин продал таверну")
  │
  └─ 6.3 Стабилизация симуляции [НЕ СУЩЕСТВУЕТ]
        ├─ Капы на количество транзакций за тик
        ├─ Ограничение радиуса propagation для World Tick
        └─ Балансировка: экономический collapse при 50 NPC за 100 тиков

  ЗАВИСИМОСТИ:
  ├─ ТРЕБУЕТ: ВСЕ предыдущие фазы (1.5, 2.0, 2-ECO, 3.x, 4-ROLE)
  └─ ТЕСТ: "10 ходов без игрока не ломают мир"


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
│   │   │   ├── npc_state.py            # ✅ R2.1 NPCState (динамика) [ПЕРЕНЕСЁН]
│   │   │   ├── behavior_mask.py        # ✅ R8 BehaviorMask, BehaviorMaskState [ПЕРЕНЕСЁН]
│   │   │   ├── personality.py          # L0 Core & L1 Identity
│   │   │   ├── decision.py             # R2 Контракт DecisionResult
│   │   │   ├── candidates.py           # Кандидаты действий
│   │   │   ├── npc_profile.py          # Профиль из JSON
│   │   │   ├── schemas.py              # Pydantic схемы API
│   │   │   ├── psychological.py        # ✅ DistortionProfile, CausalEntry [ШАГ 2b]
│   │   │   ├── scene_mode.py           # ✅ SceneMode (EXPLORATION/INTERACTION/COMBAT)
│   │   │   ├── economy.py              # 🆕 Need, Transaction, EconomicProfile
│   │   │   └── social.py               # 🆕 SocialGraph, Relationship (trust, affection, debt, secrets)
│   │   │
│   │   ├── agents/                     # LLM-агенты
│   │   │   ├── dm_agent.py             # Вербализатор
│   │   │   ├── rules_agent.py          # ✅ Интегрирован с Router (Итерация 1)
│   │   │   └── world_sim_agent.py       # ⚠️ TECH DEBT: LLM для симуляции (противоречит архитектуре, будет заменён WorldTickEngine в Фазе 6)
│   │   │
│   │   ├── core/                       # БАЗОВЫЕ МЕХАНИЗМЫ (не знают об игре)
│   │   │   ├── event_bus.py            # Шина событий
│   │   │   ├── event_types.py          # Типизированные события
│   │   │   ├── constants.py            # ✅ Central Math Config (все веса, капы, формулы) [СОЗДАН]
│   │   │   └── security.py             # Анти-спам, rate limiting
│   │   │
│   │   └── services/                   # ЯДРО ЛОГИКИ
│   │       │
│   │       ├── reaction/               # 🆕 ШАГ 0.5 — REACTION LAYER (физика мира)
│   │       │   ├── reaction_resolver.py # DecisionResult → MicroEvents
│   │       │   ├── micro_event.py       # Структура микро-события
│   │       │   └── reaction_rules.py    # Правила: threat→drop, attack→disrupt
│   │       │
│   │       ├── character/              # 🆕 ФАЗА 2.0 — ПЕРСОНАЖ (после Reaction)
│   │       │   ├── character_filter.py # PlayerIntent → FilteredAction
│   │       │   ├── character_profile.py # self_integrity, values, constraints
│   │       │   └── resistance_scorer.py # Формула сопротивления
│   │       │
│   │       ├── game_loop.py            # ★ КООРДИНАТОР + Reaction + Rules интеграция
│   │       │                           # ✅ legacy paths → commit() [ШАГ 1]
│   │       │
│   │       ├── action/                 # ★★★ DM SYSTEM (реальный путь, НЕ dm/)
│   │       │   ├── dm_orchestrator.py  # Главный фасад
│   │       │   ├── dm_router.py        # ✅ action_mode VERBAL/PHYSICAL (Итерация 1)
│   │       │   ├── dm_scene_builder.py # R4 Spatial контекст
│   │       │   ├── object_resolver.py  # Разрешение объектов
│   │       │   ├── player_target_extractor.py
│   │       │   ├── python_engines.py     # Пайплайн вызова Python-движков (DecisionHub, Resolution)
│   │       │   └─ [ДОЛГ] dm_validator.py
│   │       │
│   │       ├── npc/                    # R2 — ЯДРО ИНТЕЛЛЕКТА
│   │       │   ├── decision_hub.py     # ✅ BehaviorMask modifier (Итерация 1)
│   │       │   ├── state_applicator.py # CausalLedger
│   │       │   ├── cognitive_distortion.py  # ✅ Governor + tracking
│   │       │   ├── perception_filter.py     # ✅ cap 15m (Итерация 1)
│   │       │   ├── npc_cognition.py         # Фасад когнитивного цикла
│   │       │   ├── npc_loader.py            # JSON → объекты (будет расширён для archetype+delta)
│   │       │   ├── life_engine.py           # Data-driven активности ✅
│   │       │   ├── threat_assessor.py       # Оценка угрозы
│   │       │   ├── psyche_engine.py         # Психологические режимы
│   │       │   ├── break_progress_engine.py # R8 Прогресс слома
│   │       │   ├── reaction_priority.py     # Приоритеты реакций
│   │       │   ├── resolution_engine.py     # R5 Gap System
│   │       │   ├── math_utils.py            # Утилиты
│   │       │   ├── role_transition.py       # 🆕 Смена профессий (validation + execution)
│   │       │
│   │       # cognition/ и engines/ — НЕ СУЩЕСТВУЮТ (фантомы, удалены из дерева)
│   │       │
│   │       ├── social/                 # 🆕 СОЦИАЛЬНАЯ СИСТЕМА (ФАЗА 3)
│   │       │   ├── social_graph.py          # Матрица NPC-NPC связей
│   │       │   ├── social_propagation.py    # Распространение слухов (decay по хопам)
│   │       │   └── reputation_engine.py     # Репутация в фракциях
│   │       │
│   │       ├── economy/                # 🆕 ЭКОНОМИЧЕСКАЯ СИСТЕМА (ФАЗА 2.4)
│   │       │   ├── transaction_engine.py    # NPC-to-NPC сделки
│   │       │   ├── opportunity_engine.py    # 🆕 Генерация кандидатов из needs
│   │       │   ├── market_simulator.py      # Цены, спрос/предложение
│   │       │   └── need_calculator.py       # Динамический расчёт urgency
│   │       │
│   │       ├── spatial/                # R4 + ФАЗА 3 — ПРОСТРАНСТВЕННАЯ СИСТЕМА
│   │       │   ├── location_graph.py        # R4 Граф локаций
│   │       │   ├── spatial_runtime.py       # R4 Runtime расстояний
│   │       │   ├── spatial_events.py        # 🆕 proximity_close/leave генерация
│   │       │   └── salience_engine.py      # ✅ Фильтрация объектов по режиму сцены
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
│   │           ├── router.py           # ✅ Ленивый Semaphore (Итерация 1)
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
├── frontend/                           # UI / UX LAYER
│   └── ui/index.html                   
│
├── config/                             # STATIC CONFIG LAYER (read-only)
│   ├── npc/
│   │   ├── archetypes/                 # Шаблоны ролей (только чтение)
│   │   │   ├── _base_humanoid.json
│   │   │   ├── tavern_keeper.json
│   │   │   ├── guard.json
│   │   │   ├── merchant.json
│   │   │   └── peasant.json
│   │   │
│   │   ├── mixins/                     # Модификаторы archetype
│   │   │   ├── fallen_noble.json
│   │   │   ├── criminal_past.json
│   │   │   └── veteran.json
│   │   │
│   │   ├── individuals/                # Конкретные NPC (ТОЛЬКО дельта от archetype)
│   │   │   ├── tornin.json
│   │   │   ├── borko.json
│   │   │   ├── lusya.json
│   │   │   └── goran.json
│   │   │
│   │   └── social/                     # Статичные связи NPC-NPC
│   │       └── village_relations.json
│   │
│   ├── economy/                        # Экономические конфиги
│   │   ├── needs_library.json          # Типы потребностей
│   │   ├── wages.json                  # Ставки оплаты
│   │   └── goods_prices.json           # Базовые цены
│   │
│   └── world/
│       ├── locations.json
│       └── factions.json
│
├── saves/                              # RUNTIME СОХРАНЕНИЯ (отдельно от config)
│   └── session_{id}/
│       ├── npc_states/                 # Изменённые состояния NPC
│       ├── scene_facts.json            # Факты сцены (continuity)
│       ├── social_graph_state.json     # Текущие связи (мутируют)
│       └── player_state.json


┌─────────────────────────────────────────────────────────────────────────────┐
│                    DATA FLOW (РЕАЛЬНОСТЬ vs ПЛАН)                           │
└─────────────────────────────────────────────────────────────────────────────┘

RAW INPUT (PlayerIntent)
    │
    ▼
DM SYSTEM (Router → Scene Builder)
    │  ✅ Router: action_mode = VERBAL / PHYSICAL
    │  ✅ Router: get_rules_action_type() для rules_agent
    ▼
EventContext (event_type, intensity, action_mode)
    │
    ├─ PHYSICAL → rules_agent → player_success=True/False ✅
    │
    ▼
╔═════════════════════════════════════════════════════════════════════════════╗
║  REACTION LAYER ✅ ШАГ 0.5 ЗАВЕРШЁН                                      ║
║                                                                             ║
║  DecisionResult → MicroEvents → SceneContinuity                           ║
║  ├── threat + low_composure + hands_occupied → drop_object                ║
║  ├── attack + proximity → interaction_disrupted                          ║
║  └─ p_drop = (1 - composure) * activity_fragility                        ║
║                                                                             ║
╚═════════════════════════════════════════════════════════════════════════════╝
                           ║
                           ▼
╔═════════════════════════════════════════════════════════════════════════════╗
║  CHARACTER FILTER ← 🆕 ФАЗА 2.0 (СЛЕДУЮЩИЙ — Reaction Layer завершён)      ║
║                                                                             ║
║  PlayerIntent → FilteredAction                                             ║
║  ├── Проверка: self_integrity vs value_conflict                            ║
║  ├── Выход: ACCEPT / MODIFY / RESIST / REFUSE                              ║
║  └─ Теперь влияет на физический мир, а не на текст                        ║
║                                                                             ║
╚═════════════════════════════════════════════════════════════════════════════╝
                           ║
                           ▼
FilteredEventContext (отфильтрованный, с modifier, consequences, micro_events)
    │
    ▼
PERCEPTION FILTER  ← ✅ cap 15m во всех ветках
    │
    ▼
CognitiveDistortionEngine  ← ✅ Governor + tracking
    │
    │  Контракт выхода (DistortionProfile — typed dataclass):
    │  DistortionProfile(threat_bias, trust_bias, salience_bias)
    │  Governor: sum(abs) ≤ 1.0
    │
    ▼
╔═════════════════════════════════════════════════════════════════════════════╗
║  ECONOMIC + DRIVE INPUTS ← 🆕 ФАЗА 2.4-ECO + TEMPORARY DRIVES             ║
║                                                                             ║
║  Перед scoring в DecisionHub собираются дополнительные кандидаты:          ║
║  ├── NeedCalculator: urgency > 0.6 → Candidate(OFFER_JOB/REQUEST_SERVICE)║
║  ├── OpportunityEngine: ищет исполнителей через SocialGraph               ║
║  ├── TemporaryDrives: vengeance/greed → модификаторы к score              ║
║  └─ Новые типы: TRADE, SELL_PROPERTY, CHANGE_ROLE, SPREAD_RUMOR          ║
║                                                                             ║
╚═════════════════════════════════════════════════════════════════════════════╝
                           ║
                           ▼
DECISIONHUB (PURE SCORER)
    │  ✅ BehaviorMask: intent_score *= mask_modifier
    │  ✅ Commitment + switching_cost
    │  🆕 Economic candidates + drive modifiers
    │
    ▼
DecisionResult[]
    │
    ▼
╔═════════════════════════════════════════════════════════════════════════════╗
║  ROLE TRANSITION CHECK ← 🆕 ФАЗА 4-ROLE (если intent=CHANGE_ROLE)          ║
║                                                                             ║
║  DecisionResult → RoleTransition.can_transition()                         ║
║  ├── Проверка: required_background из target archetype                    ║
║  ├── Оплата: transition_cost (gold, stress)                               ║
║  └─ При успехе: current_role = new, activity_map из archetype             ║
║                                                                             ║
╚═════════════════════════════════════════════════════════════════════════════╝
                           ║
                           ▼
TransactionResult[] (если были сделки)
    │
    ▼
╔═════════════════════════════════════════════════════════════════════════════╗
║  СЛОЙ 1 — ФИЗИЧЕСКАЯ РЕАЛЬНОСТЬ                                             ║
║                                                                             ║
║  StateApplicator  ← ✅ CausalLedger + tracking                              ║
║  ├── Объективные веса: trust_delta, stress_delta_effective                  ║
║  ├── CausalLedger пишет CausalEntry (cap=20)                                ║
║  └─ source заполняется из event.event_type (ШАГ A.3)                        ║
║                                                                             ║
╚═════════════════════════════════════════════════════════════════════════════╝
                           ║
                           ▼
╔═════════════════════════════════════════════════════════════════════════════╗
║  СЛОЙ 2 — СУБЪЕКТИВНАЯ РЕАЛЬНОСТЬ                                           ║
║                                                                             ║
║  _build_psychological_projection()  ← ✅                                    ║
║  ├── Вход: DistortionProfile (typed)                                        ║
║  └── Выход: regime, intensity, stability                                    ║
║                                                                             ║
╚═════════════════════════════════════════════════════════════════════════════╝
                           ║
                           ▼
NpcOutcome.psychological
    │
    ▼
DMFrame  ← ✅
    │
    ▼
LLM (только вербализация)  ← ✅
    │
    ▼
FINAL TEXT


┌─────────────────────────────────────────────────────────────────────────────┐
│              ПРИОРИТЕТЫ ДЛЯ АРХИТЕКТУРНОЙ ЦЕЛОСТНОСТИ                       │
└─────────────────────────────────────────────────────────────────────────────┘

  ЛОГИКА: Агенты → Данные → Контракты → Причинность → Интеграции → Эволюция
         Каждый шаг опирается на предыдущий.

  ┌─────────────────────────────────────────────────────────────────────────┐
  │ ШАГ 0: ОЖИВЛЕНИЕ МИРА                              │
  │                                                                         │
  │ СТРАТЕГИЯ: Не "очеловечить вход", а "оживить мир"                     │
  │                                                                         │
  │ 0.1 Reaction Layer ✅ ЗАВЕРШЁН                                    │
  │     ├─ DecisionResult → MicroEvents → State                            │
  │     └─ Мир генерирует события без LLM                                 │
  │                                                                         │
  │ 0.2 CharacterFilter [СЛЕДУЮЩИЙ]                                        │
  │     ├─ Вход: PlayerIntent (after Router)                                │
  │     ├─ Выход: FilteredAction (before DecisionHub)                       │
  │     ├─ БЛОКИРУЕТСЯ: 1.5.1 + 1.5.2 (values из archetype)               │
  │     └─ ШАГ 0.8 (static/runtime) ✅ ЗАВЕРШЁН                            │
  │                                                                         │
  │ 0.3 Trust Matrix Fix                                                    │
  │     ├─ player→NPC: НЕ меняется автоматически ✅ ИСПРАВЛЕНО              │
  │     └─ character→NPC: через CharacterFilter (после 0.1-0.2)            │
  └─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │ ШАГ 0.8: STATIC VS RUNTIME РЕФАКТОРИНГ ✅ ЧАСТИЧНО                    │
  │                                                                         │
  │ ПРИЧИНА: Без разделения данных масштабирование невозможно.            │
  │                                                                         │
  │ 0.8.3 Runtime-данные из конфигов → NPCState ✅ ЗАВЕРШЁН               │
  │     ├─ major_npcs.json очищен от runtime                               │
  │     ├─ commit() → save_npc_runtime() в sessions/{id}/npc_runtime.json │
  │     ├─ LifeEngine.save_npcs() отключён                                │
  │     └─ Бэкап: major_npcs.json.bak                                     │
  │                                                                         │
  │ 0.8.3b Мерж runtime при загрузке [ОПЦИОНАЛЬНО]                        │
  │     └─ load_npcs() может читать npc_runtime.json                      │
  │                                                                         │
  │ 0.8.1 config/npc/ структура [НЕ РЕАЛИЗОВАНО]                          │
  │     ├─ archetypes/ (шаблоны ролей)                                      │
  │     ├─ mixins/ (модификаторы: fallen_noble, veteran)                   │
  │     ├─ individuals/ (только дельта от archetype)                       │
  │     └─ social/ (статичные связи NPC-NPC)                               │
  │                                                                         │
  │ 0.8.2 npc_loader.py — наследование [НЕ РЕАЛИЗОВАНО]                    │
  │     ├─ Алгоритм: base + archetype + mixins + individual delta          │
  │     └─ Конфликты: individual > mixin > archetype > base               │
  │                                                                         │
  │ 0.8.4 Валидация [НЕ РЕАЛИЗОВАНО]                                       │
  │     ├─ Новый NPC = 10-15 строк JSON                                    │
  │     └─ Смена профессии всех = 1 файл archetype                         │
  │                                                                         │
  │ БЛОКИРУЕТ: 0.9, 2-ECO, 4-ROLE (только 0.8.1 + 0.8.2)                 │
  └─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │ ШАГ 0.9: DATA CONTRACTS ДЛЯ НОВЫХ СИСТЕМ 🆕                          │
  │                                                                         │
  │ ПРИЧИНА: Контракты до реализации — предотвращают переделки.          │
  │                                                                         │
  │ 0.9.1 models/economy.py                                                │
  │     ├─ Need (type, urgency, budget_share, skill_required)              │
  │     ├─ Transaction (actor, target, goods, payment, reason)             │
  │     └─ EconomicProfile (income_sources, needs, resources)              │
  │                                                                         │
  │ 0.9.2 models/social.py                                                 │
  │     ├─ Relationship (trust, affection, fear, debt, shared_secrets)     │
  │     └─ SocialGraph (матрица связей с методами запроса)                 │
  │                                                                         │
  │ 0.9.3 Расширение NPCState                                              │
  │     ├─ current_role: str (из archetype)                                 │
  │     ├─ temporary_drives: List[TemporaryDrive]                           │
  │     ├─ resources: Dict (gold, items)                                    │
  │     └─ role_history: List[str]                                          │
  │                                                                         │
  │ БЛОКИРУЕТ: 2.4-ECO, 3.2, 4-ROLE, 0.2 (CharacterFilter)               │
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
  │ ШАГ 4: ИНТЕГРАЦИИ ✅ ЗАВЕРШЁН (override → modifier)           │
  │                                                                         │
  │ R8 Behavior Masks → DecisionHub                                         │
  │ ├─ decision_hub.py: _behavior_mask_modifier() умножает score          │
  │ ├─ COLLAPSE: IDLE * (1.0 + 2.0*intensity), остальные * suppression     │
  │ ├─ FAKE_SUBMISSION: ATTACK * 0.0, TALK * (1.0 + 0.5*intensity)        │
  │ └─ BETRAYAL: HELP * 0.0, OBSERVE * (1.0 + 0.5*intensity)              │
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
  ┌─────────────────────────────────────────────────────────────────────┐
  │ ШАГ C: СТАБИЛИЗАЦИЯ ЯДРА (Python→Python)                          │
  │                                                                     │
  │ C.1 Distortion → DecisionHub (модификатор, не источник)           │
  │     └─ Зависит: A (нужна корректная intensity) ✅                  │
  │                                                                     │
  │ C.2 BehaviorMask: от override к constraint ✅ ИТЕРАЦИЯ 1           │
  │     ├─ Формула: intent_score *= mask_modifier                      │
  │     ├─ COLLAPSE: IDLE * (1.0 + 2.0*intensity)                     │
  │     ├─ FAKE_SUBMISSION: ATTACK * 0.0                              │
  │     └─ BETRAYAL: HELP * 0.0                                       │
  └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │ ШАГ 2-ECO: ЭКОНОМИЧЕСКИЙ ДВИЖОК 🆕                                │
  │                                                                     │
  │ ПРИНЦИП: Потребности → кандидаты → транзакции. Без скриптов.      │
  │                                                                     │
  │ 2-ECO.1 need_calculator.py                                        │
  │     ├─ Динамический urgency от neglected_ticks                     │
  │     ├─ Кап: urgency_max = 0.95                                    │
  │     └─ Базовый доход от "мирной жизни" (анти-collapse)            │
  │                                                                     │
  │ 2-ECO.2 opportunity_engine.py                                     │
  │     ├─ Вход: List[Need] с urgency > 0.6                           │
  │     ├─ Если ресурсы есть → Candidate(OFFER_JOB, wage=X)           │
  │     ├─ Если нет ресурсов → Candidate(REQUEST_SERVICE)              │
  │     └─ Если нет союзников → Candidate(REDIRECT)                   │
  │                                                                     │
  │ 2-ECO.3 transaction_engine.py                                     │
  │     ├─ NPC-to-NPC сделки (sale, employment, bribe)                │
  │     ├─ Валидация ресурсов до сделки                               │
  │     └─ Запись в CausalLedger при успехе                           │
  │                                                                     │
  │ 2-ECO.4 Интеграция в DecisionHub                                  │
  │     ├─ Новые кандидаты: OFFER_JOB, REQUEST_SERVICE, TRADE         │
  │     └─ Формула: score += resource_capability * 0.2                │
  │                                                                     │
  │ ТРЕБУЕТ: 0.8 (archetype needs), 0.9 (models/economy.py)          │
  │ БЛОКИРУЕТ: 4-ROLE (смена роли требует транзакций)                 │
  │                                                                     │
  │ ТЕСТ: Торнин (need=cleanliness 0.8) → OFFER_JOB → REDIRECT к Люсе│
  └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │ ШАГ D: СОЦИАЛЬНЫЙ СЛОЙ + ПРОАКТИВНОСТЬ 🆕 ПЕРЕРАБОТАН             │
  │                                                                     │
  │ ПРИНЦИП: NPC знают друг друга, передают информацию, действуют      │
  │          между ходами игрока.                                      │
  │                                                                     │
  │ D.1 spatial_events.py (ФАЗА 3.1)                                  │
  │     ├─ distance < 1.5m → proximity_close (триггер диалога)        │
  │     ├─ distance > 5.0m → proximity_leave (прерывание)              │
  │     └─ Превращает "подойти" из текста в триггер DecisionHub       │
  │                                                                     │
  │ D.2 social_graph.py (ФАЗА 3.2)                                     │
  │     ├─ Relationship: trust, affection, fear, debt, shared_secrets  │
  │     ├─ Загрузка из config/npc/social/ + runtime мутации           │
  │     ├─ Правило ревности: proximity_close + affection > 0.5         │
  │     │   → Candidate(INTIMIDATE, reason=jealousy)                  │
  │     └─ Правило долга: need + no resources + debt > 0              │
  │         → Candidate(REQUEST_SERVICE, target=debtor)                │
  │                                                                     │
  │ D.3 social_propagation.py (ФАЗА 3.3)                               │
  │     ├─ max_hops=3, decay=0.8^hop, freq_cap=1/5 тиков              │
  │     ├─ Искажение: trust < 0 → преувеличивает негатив              │
  │     └─ Генерирует MicroEvents для удалённых NPC                   │
  │                                                                     │
  │ D.4 reputation_engine.py (ФАЗА 3.5)                                │
  │     ├─ Репутация в фракциях (config/world/factions.json)           │
  │     └─ Действия NPC влияют на репутацию фракции                    │
  │                                                                     │
  │ D.5 role_transition.py (ФАЗА 4-ROLE)                               │
  │     ├─ can_transition(): required_background из archetype          │
  │     ├─ execute_transition(): current_role, activity_map, cost      │
  │     └─ Запись в role_history + CausalLedger                       │
  │                                                                     │
  │ D.6 temporary_drives в NPCState (ФАЗА 4-ROLE)                     │
  │     ├─ Генерация: emotional_impact > 0.7 → drive                  │
  │     ├─ Cap: 3 active drives                                       │
  │     └─ Модификаторы: vengeance→COMBAT+0.3, greed→TRADE+0.3       │
  │                                                                     │
  │ D.7 Agenda Loop / WorldTickEngine (ФАЗА 6-WORLD)                   │
  │     ├─ Тикер: раз в N ходов или при входе в локацию               │
  │     ├─ Каждый NPC → DecisionHub(event_type="world_tick")          │
  │     └─ Оффлайн-мутации: транзакции, смена ролей, перемещения      │
  │                                                                     │
  │ ТРЕБУЕТ: 0.8 (archetype), 0.9 (models/social.py), 2-ECO          │
  └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │ ШАГ E: ДАВЛЕНИЕ МИРА НА ПЕРСОНАЖА (ФАЗА 5-PRESSURE)               │
  │                                                                     │
  │ ❌ БЛОКИРУЕТСЯ: CharacterFilter (ФАЗА 2.0) + Social Propagation    │
  │                                                                     │
  │ E.1 Fronts                                                          │
  │     ├─ Маска персонажа для мира                                     │
  │     ├─ Формируется: репутация (D.4) + слухи (D.3) + фракции       │
  │     └─ Зависит: D.3, D.4, CharacterFilter                         │
  │                                                                     │
  │ E.2 Consequence Accumulation                                        │
  │     ├─ Накопленные RESIST → истощение self_integrity               │
  │     └─ Зависит: CharacterFilter                                    │
  │                                                                     │
  │ E.3 Identity Erosion                                                │
  │     ├─ Внутренний слом (vs NPC Break = внешний)                    │
  │     ├─ Erosion → temporary_drives (desperation)                    │
  │     └─ Зависит: E.2, D.6 (temporary_drives)                       │
  └─────────────────────────────────────────────────────────────────────┘

  ── ПАРАЛЛЕЛЬНО (не блокирует основной pipeline) ──
  ├─ Удалить/закомментировать BODY_TRAIT, ROLE_MARKER (мёртвый код)
  ├─ dm_validator.py (когда понадобится)
  ├─ God Mode endpoint для CausalLedger viewer (routes_debug.py)
  └─ config/world/factions.json — статичные данные, можно подготовить заранее

================================================================================
ВАЛИДАЦИОННЫЙ СЦЕНАРИЙ: "МЕСТЬ ТОРНИНА"
================================================================================

ЦЕЛЬ: Проверить работоспособность ВСЕХ новых систем на одном сценарии.
Проходит только когда реализованы: 0.8, 0.9, 2-ECO, D.1-D.6.

┌─────────────────────────────────────────────────────────────────────┐
│ ХОД 0: ИНИЦИАЛИЗАЦИЯ                                             │
│ ├─ npc_loader: tornin.json = _base_humanoid + tavern_keeper +     │
│ │   fallen_noble + individual delta                               │
│ ├─ current_role = "tavern_keeper"                                │
│ ├─ social_graph: tornin→lusya = {affection: 0.8, debt: 0}        │
│ └─ resources: {gold: 100}                                        │
├─────────────────────────────────────────────────────────────────────┤
│ ХОД 15: СОБЫТИЕ                                                  │
│ ├─ Люся погибает (player_attack или NPC)                          │
│ ├─ CausalEntry: emotional_impact=0.8                              │
│ ├─ SocialPropagation: tornin получает событие (dist=0, same loc)  │
│ └─ TemporaryDrive: vengeance, target=unknown, urgency=0.9         │
├─────────────────────────────────────────────────────────────────────┤
│ ХОД 16: REACTION (World Tick или следующий ход игрока)            │
│ ├─ NeedCalculator: need=vengeance urgency=0.9                     │
│ ├─ OpportunityEngine: Candidate(SELL_PROPERTY, reason=fund_arms)  │
│ ├─ TransactionEngine: сделка с Гораном, gold +300                 │
│ ├─ RoleTransition: can_transition(mercenary) → required_background│
│ │   "former_soldier" ✅ (из fallen_noble mixin)                   │
│ ├─ RoleTransition: execute → current_role="mercenary"             │
│ └─ CausalLedger: "Продал таверну, чтобы отомстить за Люсю"       │
├─────────────────────────────────────────────────────────────────────┤
│ ХОД 25: ВСТРЕЧА С ИГРОКОМ                                        │
│ ├─ PerceptionFilter: видит Торнина в доспехах                     │
│ ├─ visible_markers: ["military_gear", "sword", "empty_eyes"]      │
│ ├─ psychological_projection: {grief: 0.8, vengeance: 0.9}        │
│ ├─ intent: SEEK_INFORMATION (ищет убийцу — от drive)             │
│ └─ DM: "Торнин смотрит сквозь тебя. 'Ты был той ночью...'"       │
├─────────────────────────────────────────────────────────────────────┤
│ ХОД 30: ЕСЛИ ИГРОК СОВРАЛ                                        │
│ ├─ CausalEntry: "Игрок соврал о присутствии"                      │
│ ├─ trust к игроку: -0.3                                           │
│ ├─ SocialPropagation: слух о лжи может дойти до других NPC        │
│ └─ Если TemporaryDrive.vengeance ещё активен → target может смениться│
└─────────────────────────────────────────────────────────────────────┘

ПРОВЕРКИ ПО СЦЕНАРИЮ:
├─ [0.8] npc_loader загружает archetype + delta без ошибок
├─ [0.9] NPCState содержит current_role, temporary_drives, resources
├─ [D.2] social_graph даёт affection для правила ревности
├─ [D.3] propagation передаёт событие о смерти
├─ [D.6] emotional_impact > 0.7 порождает drive
├─ [2-ECO] need urgency > 0.6 генерирует кандидата
├─ [2-ECO] transaction_engine проводит сделку
├─ [D.5] role_transition проверяет background и меняет роль
└─ [R3] DM получает correct stance + markers + projection

================================================================================

================================================================================
STATIC VS RUNTIME РАЗДЕЛЕНИЕ (ФУНДАМЕНТ МАСШТАБИРУЕМОСТИ)
ПРИНЦИП: Данные NPC разделены на два слоя. Система работает ТОЛЬКО с runtime.

┌─────────────────────────────────────────────────────────────────────────────┐
│ STATIC (config/npc/) — задается разработчиком, НЕ меняется в игре │
│ ├─ identity (имя, происхождение, базовая личность L0) │
│ ├─ potential_roles (чем теоретически может заниматься) │
│ ├─ visual.baseline (базовая внешность) │
│ ├─ economic_profile.needs (базовые потребности archetype) │
│ └─ activity_map (шаблон поведения из archetype) │
├─────────────────────────────────────────────────────────────────────────────┤
│ RUNTIME (saves/ + NPCState) — мутирует в процессе игры │
│ ├─ current_role (текущая профессия — может смениться) │
│ ├─ visible_markers (шрамы, одежда, статус) │
│ ├─ psyche (стресс, травмы, willpower) │
│ ├─ resources (золото, инвентарь, долги) │
│ ├─ relationships (текущие отношения NPC-NPC) │
│ ├─ temporary_drives (месть, жадность — с expiry) │
│ └─ causal_ledger (история событий) │
└─────────────────────────────────────────────────────────────────────────────┘

СЛЕДСТВИЕ:
─ Добавление нового NPC = 10-15 строк JSON (только дельта от archetype)
─ Изменение профессии у всех NPC = правка 1 файла archetype
─ Хардкод отдельных NPC ЗАПРЕЩЁН — система масштабируется через пресеты

================================================================================
ARCHETYPE SYSTEM (ШАБЛОНЫ РОЛЕЙ)
================================================================================

НАЗНАЧЕНИЕ: Разделить "кто он" от "чем занимается". Роль = сменяемый контракт.

СТРУКТУРА ARCHETYPE JSON:
{
  "archetype_id": "tavern_keeper",
  "title": "Хозяин таверны",
  "activity_map": {...},
  "economic_profile": {
    "income_sources": ["tavern_revenue"],
    "needs": ["cleanliness", "security"],
    "resources": {"gold": 100}
  },
  "required_background": [],     # Кто может стать (пусто = любой)
  "transition_cost": {"gold": 0, "stress": 0}
}

НАСЛЕДОВАНИЕ:
─ _base_humanoid.json → tavern_keeper.json → tornin.json (только delta)
─ npc_loader.py загружает: base + archetype + mixins + individual delta
─ Конфликты: individual > mixin > archetype > base

СМЕНА РОЛИ (RoleTransition):
1. RoleTransition.can_transition(npc, target_role) — проверка required_background
2. Выплата transition_cost (золото, стресс)
3. Копирование activity_map из нового archetype
4. Запись в role_history + CausalLedger
5. Обновление SocialGraph (другие NPC реагируют на новую роль)

ПРИМЕР: Торнин (tavern_keeper) → Солдат (mercenary)
─ required_background: "former_soldier" ✅ (есть в tornin.json delta)
─ transition_cost: gold=50, stress=+10
─ Результат: current_role="mercenary", activity_map из mercenary.json

================================================================================
ECONOMIC ENGINE (ДВИЖОК ПОТРЕБНОСТЕЙ И СДЕЛОК)
================================================================================

ПРИНЦИП: NPC имеют потребности, которые генерируют кандидаты действий.
Нет скриптовых квестов — только математика выгоды и причинность.

КОНТРАКТЫ ДАННЫХ (models/economy.py):

Need (потребность):
  type: str               # "cleanliness", "security", "revenge", "rare_ingredients"
  urgency: float          # 0.0-1.0 (динамический, растёт от neglected_ticks)
  base_urgency: float     # Базовое значение из archetype
  budget_share: float     # Доля золота, готовая потратить на удовлетворение
  skill_required: str     # Что нужно от исполнителя
  payment_forms: List[str] # ["gold", "food", "favor"]

Transaction (сделка NPC-to-NPC):
  type: str               # "sale", "employment", "bribe", "property_transfer"
  actor: str              # Кто предлагает
  target: str             # Кому
  goods: Dict             # Что передаётся
  payment: Dict           # Что получает
  reason: str             # Причина (для CausalLedger)

ЖИЗНЕННЫЙ ЦИКЛ ПОТРЕБНОСТИ:
1. Archetype задаёт base_urgency для каждого need
2. need_calculator.py увеличивает urgency при neglected_ticks
3. Когда urgency > 0.6 → opportunity_engine.py генерирует кандидата:
   ├─ Если есть ресурсы → Candidate(OFFER_JOB, wage=X)
   ├─ Если нет ресурсов → Candidate(REQUEST_SERVICE, ask_ally=True)
   └─ Если нет союзников → Candidate(REDIRECT, target=best_match)
4. Сделка через transaction_engine.py → запись в CausalLedger

КАПЫ ДЛЯ СТАБИЛЬНОСТИ:
─ urgency_max = 0.95 (предотвращает urgency inflation)
─ Базовый доход от "мирной жизни" (аренда, проценты) — предотвращает economic collapse

================================================================================
SOCIAL GRAPH & PROPAGATION (СЕТЬ СВЯЗЕЙ NPC-NPC)
================================================================================

ПРИНЦИП: NPC знают друг о друге. Связи имеют измерения, не одно число.
События распространяются по графу с искажением и затуханием.

КОНТРАКТ ДАННЫХ (models/social.py):

Relationship (связь между двумя NPC):
  trust: float             # -1.0 до 1.0 (вера в слова/намерения)
  affection: float         # Эмоциональная привязанность (ревность, защита)
  fear: float              # Страх перед NPC
  debt: float              # Долг (положительный = должен ему)
  last_interaction: int    # Тиков назад (для decay)
  shared_secrets: List     # Что знают друг о друге (для шантажа/доверия)

ПРОПАГАЦИЯ СОБЫТИЙ (social_propagation.py):
1. Событие (смерть, сделка, предательство) → SocialPropagation.propagate()
2. Распространение по графу:
   ├─ max_hops = 3 (не далее 3 связей)
   ├─ decay = 0.8^hop (каждый хоп ослабляет сигнал)
   └─ frequency_cap = 1 раз в 5 тиков (предотвращает спам)
3. Искажение через trust_bias:
   ├─ trust < 0 → преувеличивает негативное (враг рассказывает хуже)
   └─ trust > 0 → преувеличивает позитивное (союзник защищает репутацию)

ПРИМЕР ИСПОЛЬЗОВАНИЯ В DECISIONHUB:
─ Игрок подходит к Люси (dist < 1.5, spatial_events → proximity_close)
─ Торнин проверяет social_graph["lucy"].affection = 0.8
─ Условие срабатывает → Candidate(INTIMIDATE, reason=jealousy, +0.5 к score)

ПРИМЕР ИСПОЛЬЗОВАНИЯ В ECONOMY:
─ Торнин имеет need:cleanliness urgency=0.8, но нет золота
─ Ищет в social_graph: кто имеет debt > 0 и навык уборки
─ Находит Люсю (debt=20) → Candidate(REQUEST_SERVICE, target=lusya)

================================================================================
TEMPORARY DRIVES (ВРЕМЕННЫЕ МОТИВАЦИИ)
================================================================================

ПРИНЦИП: Постоянные черты (L0) определяют КЕМ является NPC.
Temporary drives определяют ЧТО он хочет ПРЯМО СЕЙЧАС. С истечением срока — исчезают.

КОНТРАКТ ДАННЫХ (часть NPCState):
temporary_drives: List[TemporaryDrive] = []

TemporaryDrive:
  type: str               # "vengeance", "greed", "survival", "desperation"
  target: Optional[str]   # "unknown_killer", "merchant_goran" (None = абстрактная)
  urgency: float          # 0.0-1.0 (мотивирующая сила)
  expiration: int         # tick, когда drive исчезает (или 0 = бессрочный)
  origin_event: str       # "witnessed_death" — для CausalLedger трейсабельности

ГЕНЕРАЦИЯ:
─ CausalEntry с emotional_impact > 0.7 → может породить drive
─ SocialPropagation: новость о смерти союзника → drive:vengeance
─ StateApplicator: потеря имущества → drive:recovery
─ Cap: максимум 3 active drives на NPC (при превышении — самый старый удаляется)

ВЛИЯНИЕ НА DECISIONHUB:
─ drive.urgency добавляется к base_urgency релевантных кандидатов
─ drive.type модифицирует предпочтения:
  ├─ vengeance → COMBAT/INVESTIGATE +0.3, IDLE -0.5
  ├─ greed → TRADE/SELL_PROPERTY +0.3, OBSERVE -0.2
  └─ survival → FLEE/HIDE +0.4, TALK -0.3

ПРИМЕР: "Месть Торнина"
─ Ход 15: Люся погибает → CausalEntry(emotional_impact=0.8)
─ Ход 16: TemporaryDrive(type=vengeance, target=unknown, urgency=0.9, expiration=500)
─ Результат: Торнин ищет убийцу, продаёт таверну, меняет роль
─ Ход 516: drive истёк → vengeance больше не влияет (но может остаться в CausalLedger)

================================================================================
0. ТРЁХУРОВНЕВАЯ МОДЕЛЬ АГЕНТОВ (ФУНДАМЕНТ)
┌─────────────────────────────────────────────────────────────────────────────┐
│ УРОВЕНЬ 1 — ИГРОК (внешний оператор) │
│ ├─ Вводит намерение │
│ ├─ НЕ обязан подчиняться логике мира │
│ └─ "Сделай X" — это ЗАПРОС, не приказ миру │
├─────────────────────────────────────────────────────────────────────────────┤
│ УРОВЕНЬ 2 — ПЕРСОНАЖ (агент в мире) ← КЛЮЧЕВОЙ НОВЫЙ СЛОЙ │
│ ├─ Имеет характер (ценности, страх, социальные рамки) │
│ ├─ Имеет ограничения │
│ ├─ МОЖЕТ НЕ СОГЛАСИТЬСЯ с игроком │
│ └─ Мягкое сопротивление: ослабить / изменить форму / добавить последствия│
├─────────────────────────────────────────────────────────────────────────────┤
│ УРОВЕНЬ 3 — NPC (интерпретатор действий) │
│ ├─ Видит ДЕЙСТВИЕ ПЕРСОНАЖА, не намерение игрока │
│ └─ Реагирует на то, что произошло, а не на то, что хотел игрок │
└─────────────────────────────────────────────────────────────────────────────┘

DATA FLOW ПЕРСОНАЖА:
PlayerIntent → CharacterFilter → FinalAction → NPC perception

CharacterFilter ПРОВЕРЯЕТ:
├─ Ценности (self_integrity, pride, honour)
├─ Страх (физический, социальный, экзистенциальный)
├─ Социальные рамки (статус, репутация, роль)
└─ Текущее состояние (стресс, усталость, влияние)

РЕЗУЛЬТАТ CharacterFilter:
├─ ACCEPT: действие проходит без изменений
├─ MODIFY: действие ослаблено или изменено
├─ RESIST: действие с последствиями (стресс, стыд, репутация)
└─ REFUSE: отказ (только при высоком self_integrity + крайнем конфликте)

МАТРИЦА TRUST (3 направления, не 2):
├─ NPC→player: меняется от действий персонажа ✅ УЖЕ РЕАЛИЗОВАНО
├─ player→NPC: НЕ меняется автоматически от действий ❌ БЫЛ БАГ (исправлен)
└─ character→NPC: меняется через CharacterFilter 🆕 НОВЫЙ СЛОЙ

================================================================================

## ЦЕНТРАЛЬНЫЙ КОНФИГ КОНСТАНТ (Central Math Config)

```python
# core/constants.py — единственное место всех "магических чисел"

# Commitment
COMMITMENT_BONUS_K = 0.15
SWITCHING_COST_BASE = 0.05
EFFECTIVE_STALL_THRESHOLD = 6  # тиков до начала decay

# Perception
PERCEPTION_RADIUS = {
    "minor": 5.0,   # метров
    "middle": 8.0,
    "major": 12.0,
}
PERCEPTION_FALLBACK_DISTANCE = 15.0  # НЕ 999.0

# Break System
BREAK_TRIGGER_RATIO = 1.0     # pressure > willpower * ratio
WILLPOWER_RECOVERY_RATE = 0.02   # за тик
IDENTITY_DECAY_RATE = 0.05       # под давлением

# Resolution
RESOLUTION_DICE_WEIGHT = 0.65
RESOLUTION_BIAS_WEIGHT = 0.35
RESOLUTION_MIN = 0.05
RESOLUTION_MAX = 0.95
PREPARATION_CAP = 0.80
GAP_TRAUMA_THRESHOLD = 0.35   # |gap| > этого → trauma_marker

# Memory
WORKING_MEMORY_SIZE = 20
NARRATIVE_FACTS_MAX = 2
MEMORY_DECAY_TICKS = 10        # каждые N тиков
DISTORTION_CLARITY_FLOOR = 0.1

# Distortion Governor
DISTORTION_MAX_TOTAL = 1.0
DISTORTION_AXIS_CAP = 0.6     # максимум одной оси

# LLM Token Budgets
TOKEN_BUDGET_MAJOR_NPC = 700
TOKEN_BUDGET_MIDDLE_NPC = 350
TOKEN_BUDGET_MINOR_NPC = 180
TOKEN_BUDGET_DM_CONTEXT = 2048

# Character Filter
RESISTANCE_ACCEPT = 0.3
RESISTANCE_MODIFY = 0.6
RESISTANCE_RESIST = 0.9

# Switching Cost
AGE_COST_K = 0.08
EMOTION_COST_K = 0.06
IDENTITY_COST_BASE = 0.04
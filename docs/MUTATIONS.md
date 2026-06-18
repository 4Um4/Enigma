# MUTATIONS.md — Каузальная Эволюция ENIGMA

> **Формат:** Домен → Хронология сессий → Запреты. Ищи по `Ctrl+F S##` или домену.

---

## МЕТА

| Показатель | Значение |
|------------|----------|
| Сессий | 83+ |
| Доменов | 10 |
| Консолидированных запретов | 72 |
| Диапазон | S03—S83+ |

---

## ЛЕГЕНДА

| Символ | Значение |
|--------|----------|
| ⚪ | Эволюция / Изменение логики |
| 🔵 | ADR (Стандарт / Онтология) |
| 🟢 | FIX (Закрытый баг) |
| 🔴 | CRITICAL (Критический баг / Разрыв пайплайна) |
| 💀 | Убитый концепт (не воскрешать) |

---

## 1. ДОМЕНЫ И ЭВОЛЮЦИЯ

### DOM-01: FOUNDATION (Core Pipeline, Time, State)

**Истина:** Симуляция дискретна, презентация непрерывна. `LifeEngine` — лоббист, а не бог-мутатор. Тик — чистая функция вычисления.

- ⚪ **S04** Централизация через `SpatialService` v1.2, убит хардкод локаций.
- ⚪ **S29** Убита телепортация. Внедрен Каузальный Lerp на фронтенде. `DIRECT_REFLEX` удален.
- 🔵 **S34** DualTime Ontology. Запрет ретросимуляции. `LifeEngine.tick()` возвращает интенты, а не мутирует.
- 🔵 **S37** Authoritative Spatial Spine (ADR-048). `SpatialQueryService` инстанцирован.
- 🔵 **S47** Консолидация `SpatialService` в `TickOrchestrator`. Внедрен `_resolve_spatial_service`.
- 🔴 **S49** Инвариант единого владения причинностью движения. `npc_orchestration.py` лишен права вызывать `process_intents`.
- 🟢 **S50** GAP12 УБИТ. `_enrich_local_positions` вычисляет интерполированную позицию для NPC в активном транзите.
- 🔴 **S72** ADR-128 P0: DECAY_INJURY_LOST — NPC injuries терялись после cache miss. Внедрен SQLite read-back.
- 🔴 **S72** ADR-128 P0: Player injuries LOST — AvatarService `_state_to_dict()` не сериализовал `body_state`.
- 🔴 **S73** ADR-130 G1: Schedule Override Reactive Movement — `update_routine()` мутировал поверх активного reactive traversal.
- 🔴 **S74** P0: DRF Split-Brain Fix. DRFBus перенесён на уровень экземпляра оркестратора (ADR-134).
- 🔵 **S74** DRFExecutionContext: Scoped Causal Ledger (ADR-136). Pipeline получает `drf_ctx`, Claim наследует контекст.
- 🔴 **S76** Normalization Gate: `tick_orchestrator.py` инжектит `BODY_STATE_DISABLED` для NPC без `body_state`.
- 🔵 **S83.1** ADR-S83.1: Tick = Pure Function Evaluation. Тик — чистая функция, не объект с побочными эффектами.
- 🔵 **S83+** ADR-GL-202: Generative Constraint Execution Model (GCO). Ленивое вычисление графа каузальности.
- 🔵 **S83+** ADR-O-204: Phase 3 Preconditions — Causal Kernel Surgery.
- 🔵 **S83+** ADR-O-205: Projection Layer System. Слой проекции физики в наблюдаемую реальность.

### DOM-02: WILL, PRESSURE & DECISION

**Истина:** Решения рождаются из искривленного давления (Utility Deformation). Воля — инерция, а не порог. Подчинение требует легитимности.

- 🔵 **S19** WillpowerGate (ADR-031). Cumulative Strain Model вместо бинарки. Шкала COMPLY → CONDITIONED.
- ⚪ **S21** Убийство объективных событий. Давление генерирует `PsychologicalPressure`, а не напрямую интент.
- 🔵 **S24** Affective Resonance (ADR-036). Аффект искажает давление через `ResponseBias`.
- 🔵 **S31** DecisionContext (ADR-050). Feasibility Layer (удаление невозможных действий) и Utility Deformation.
- 🔵 **S36** Legitimacy Gate (ADR-057). Нет страха/доверия = Irritation (агрессия) вместо Obedience.
- 🔴 **S48** Починка обрыва Трубы Воли на границе API. `routes.py` теперь пробрасывает `will_conflict_data`.
- 🟢 **S52** GAP10 УБИТ. `EventContext` обогащён `target_id`. DecisionHub фильтрует бонус `APPROACH` для нецелевых NPC.
- 🟢 **S53** GAP2 УБИТ. Амнезия Воли вылечена. `compute_willpower` читает `trauma_markers`.
- 🟢 **S55** УБИТ Мертвый Вектор Эмоций (ADR-088). `IntentCompressor._fast_path_parse` инжектит агрессию для ATTACK.
- 🟢 **S60** УБИТ `_semantic_action=None` (ADR-091). `publish_classified_player_event` вызывается после резолва.
- 🟢 **S64** УБИТ PHYSICS_OF_POWER NameError. `_context_relevance` не имел параметра `event`.
- 🔵 **S69** Ontology Merge Step 1: Relationship Cache Precedence Contract.
- ⚪ **S71** §ENIGMA-S72 Закон Релятивистского Восприятия. Система перешла от централизованной интерпретации к модуляции личностью.
- 🔴 **S74** ДОЛГ 4.2: Causal Scoring Overlay (ADR-135). DRF претензии влияют на приоритет аддитивно. Убит сломанный clamp.
- 🔵 **S81** ADR-O-146: Personality Math Layer. Введен `profile_math.py`. Социальные дельты и риск модулируются личностью.

### DOM-03: PERCEPTION & PHENOMENOLOGY (CFRM)

**Истина:** Объективных фактов нет. Есть возмущения поля, которые проецируются в субъективные феномены.

- ⚪ **S21** Убийство объективных событий. Давление генерирует `PsychologicalPressure`.
- ⚪ **S26** Epistemic Classification. Оценка уверенности (confidence) при классификации.
- ⚪ **S30** CFRM Phase 2. `semantic_seed` (геном нарратива). Проекция теряет энергию/форму.
- 🔴 **S78** ADR-O-143: Somatic Bypass УБИТ. `body_state.pain/shock` проходят через `PerceptualKernel.somatic_urgency`.
- 🔵 **S78** ADR-O-142: State Resolution Binding. Двухуровневая модель сознания. Arousal Gate = FSM MUTATOR.
- 🟢 **S62** DOUBLE TRUTH `threat_gradient` УБИТ. `NPCState.write_to_legacy()` теперь пишет `perceptual_kernel`.
- 🔵 **S83+** ADR-302: SIL, DSTC & SEL (Active Inference). Сдвиг к Активному Выводу.

### DOM-04: SPATIAL & LOCOMOTION

**Истина:** `SpatialQueryService` — единственный авторитет. Движение — результат давления и решения. Фронтенд — интерполятор.

- ⚪ **S10** Запрет `MovementIntent` для микроперемещений (требуется `LocalSteeringIntent`).
- 🟢 **S33** Нормализация префиксов макрозон (LOD0 fix).
- ⚪ **S35** Safe Spatial Fallback. Отмена перемещения при отсутствии узла.
- 🔵 **S46** Убита перезапись позиции игрока из протухшего `player_spatial`.
- 🟢 **S51** GAP9 УБИТ. Реалистичное Пробуждение. Сон блокируется непрерывными скалярами.
- 🔵 **S58** Фронтенд: Физика WASD (Pushout Resolution). Игрок больше не застревает.
- 🟢 **S59** ADR-102: `load_graph()` мёртв. Заменён на `SpatialService.build_for_location()`.
- 🔵 **S61** ADR-114: Spatial Paralysis убит. `graph_compiler.py` создает role-based алиасы.
- 🔵 **S67** ADR-121: Двухслойная топология в graph_compiler. `nodes` (dict) и `boundary_map`.
- 🔵 **S68** ADR-125: Target ID SSOT Clarification. Истина идёт через `intent.target`.
- 🟢 **S76** Новые чанки мира: city_gate, market_square. Формат World Partition (adjacency связи).
- 🔴 **S79** БАГ U ЗАКРЫТ: room_2 удалена из tavern.json. Синхронизированы nodes.
- 🔵 **S79** ДОЛГ 6.2 ПРОТОТИП: Boundary Nodes. `NodeRole.BOUNDARY` в spatial_contracts.py.
- 🔵 **S79** Пять архитектурных открытий: Location ≠ Room, цель = Semantic Target, Boundary Node = интерфейс.
- 🟢 **S80** ADR-O-142A: Arousal Gate — missing wake edge закрыт. Спящий NPC пробуждается при wake_pressure.
- 🔵 **S82.0** ADR-S82.0: Spatial Authority Contract. Строгий контракт единого владельца пространственных данных.
- 🔵 **S83+** ADR-303: Coordinate Truth & Physical World Unification (Map Editor).

### DOM-05: PHYSIOLOGY & COMBAT

**Истина:** Тело — материальный объект. Удар — чистая физика контакта, порождающая боль и шок.

- ⚪ **S16** Каскад Shock → Emotion (ReactionSubscriber извлекает `shock_impulse`).
- ⚪ **S20** Очистка `combat_stats`. Перенос способностей в `body_profile`.
- 🟢 **S54** Хардкод _MOVE_VERBS удален. Semantic Bridge замкнут.
- ⚪ **S57** RPG Витализм: нормализация шкалы `pain` (0-100 → 0-1) в `StateInterpreter`.
- 🔴 **S72** ADR-128: Player injuries LOST. Двойная онтология: wounds (legacy) ≠ body_state (truth).
- 🔴 **S73** ADR-130 G2: Uninvited NPC Approach. `_context_relevance()` не имел fallback на payload.
- 🔴 **S74** P1: Player Combat Snapshot EntityView Shift. Игрок стал симулируемой физической сущностью в бою.
- 🔴 **S75** ADR-094 MSOC: CRITICAL BUG — `pressure_translator.py` читал `pain` без нормализации.
- 🟢 **S75** Контракт шкал физиологии зафиксирован. `pain`/`fatigue` = 0-100, `blood_loss`/`shock` = 0-1.
- 🟢 **S76** NPIC Sentinel: Введена константа BODY_STATE_DISABLED (§ENIGMA-003).
- 🟢 **S76** ADR-140: DM Death Scene Pipeline. DM получает life_status через avatar_to_prompt.
- 🟢 **S77** ADR-141: Убит разрыв Injury → Pain. `InjuryProcessor` генерирует `pain_delta` из свойств раны.

### DOM-06: SOCIAL & MEMORY

**Истина:** Память многослойна. Социальные акты искривляют utility-space целей.

- ⚪ **S03** Мультисобытийность Perception.
- ⚪ **S08** Обогащение NPC социальными связями из `village_relations.json`.
- ⚪ **S27** Физика Власти. `DirectiveInterpretationSubscriber` транслирует приказы в давление.
- 🔵 **S66** `RelationshipStore` назначен Единственным Источником Истины (SSOT).

### DOM-07: FRONTEND, PRESENTATION & INPUT

**Истина:** Фронтенд — сенсорный орган игрока. Он искажается, болеет и сопротивляется.

- ⚪ **S18** Создание Персонажа через Вектор Начальных Условий.
- ⚪ **S25** Embodied Vector. Предрефлексивные моторные импульсы.
- ⚪ **S56** The Fool v2 — визуализация моторных следов и тултипов наблюдений замкнута.
- 🔴 **S72** ADR-128: PlayerAvatarService сериализует body_state. Труба аватара замкнута.
- 🔴 **S75** ADR-137: Death Feedback Pipeline замкнут. Death overlay на фронтенде.
- 🟢 **S76** Map Editor: Shift+ЛКМ перетаскивание локаций. Outdoor поддержка.
- 🟢 **S81** Visual: shake amplitude уменьшена в 2 раза. NPC/Player gaze утолщены.
- 🔴 **S82** Убран `return` в обработке клавиши J — вызывал вылет игры. ADR-JOURNAL, ADR-SPEECH.

### DOM-08: OBSERVABILITY (CDS & Sandbox)

**Истина:** Наблюдение не создает причинность. CDS — пассивный аудитор.

- ⚪ **S39** Интеграция CDS. Фронтенд не парсит отчёты симуляции.
- 🟢 **S72** P3: Уборка диагностического шума. Удалены TRACE-принты, понижены до DEBUG.
- 🟢 **S74** Sandbox Tests: 7 тестов для ADR-128/130 по §12.3 Устава.
- 🟢 **S83** ADR-147: LLM Streaming Observability Gate. Убит теневой streaming path, CDS видит execution gate.

### DOM-09: SOCIAL & AFFECTIVE ARCHITECTURE (SSOT & Causal Derivation)

**Истина:** Отношения — это граф (ребро). Аффективная нагрузка — интеграл с гистерезисом.

- 🔵 **S63** `load_l2_state_from_runtime_dict()` — добавлены 5 полей в конструктор.
- 🔵 **S75** Убит Вечный Двигатель Страха (ADR-138). Асимметричный Аттрактор (Гистерезис).
- 🔵 **S76** ADR-O-140 спроектирован: World Partition Topology.
- 🔴 **S78** ADR-O-143: Somatic Bypass УБИТ. Боль/шок переведены в `PK.somatic_urgency`.
- 🔵 **S83+** ADR-O-206: Emotional Residue Isolation Protocol. Эмоциональный остаток изолирован.

### DOM-10: IDENTITY & ONTOLOGY (Identity Layer & Chronicle)

**Истина:** Идентичность — это фазово-заблокированное поле дрейфа, кристаллизующееся во времени.

- 🔵 **S83+** ADR-GL-203: Error-geometry System & Dynamic Ontology. Эпистемология ENIGMA.
- 🔵 **S83+** ADR-O-207: Runtime Ontology Collapse Plan. Post-Commit Validation Gate (OntologyViolationError).
- 🔵 **S83+** ADR-O-208: DRIVE RESOLUTION PIPELINE (DRP). L1Chronicle + DriveResolver.
- 🔵 **S83+** ADR-O-209/210: Phase-Locked Identity & Bounded Spatial Field Coupling.
- 🔵 **S83+** ADR-O-211: Calibration Engine & Identity Stability Kernel.
- 🔵 **S83+** ADR-TIFL-001: Temporal Identity Formation Layer.
- 🔵 **S83+** ADR-TIFL-002: Identity as Competitive Drift Field (ICDF).
- 🔵 **S83+** ADR-TIFL-003: Identity Constraint Layer & Thermodynamic Crystallization.
- 🔵 **S84** ADR-O-306: Epistemic Heterogeneity & Triple Membrane. L1 Chronicle = персонализированная хроника. Тройная Мембрана (Физика, Личность, Социум) фильтрует L1. InstitutionLayer модулирует пороги PerceptualKernel.
- 🔵 **S84** ADR-O-307: Asymmetric Trauma & Belief Revision. Введён множитель x6 для опровержений. Belief формируется только от personal_persistence.

---

## 2. АРХИТЕКТУРНЫЕ ЗАПРЕТЫ (Синхронизировано с ADR Master Index)

### State & Mutation
1. ❌ Прямая мутация стейта в обход `DeltaBuffer`
2. ❌ Циклы `tick()` для нагона времени (`TICK_CATCHUP`)
3. ❌ Формирование ответа Фазы 8 через `List[dict]`
4. ❌ Подмена `campaign_id` на `location_id` в `_TickContext`
5. ❌ `if state.body_state:` (falsy dict) — использовать `is not None`
6. ❌ Переход `DEAD → ALIVE` через обычную физиологию
7. ❌ Снятие `_tick_locked` после вызова сохранения состояния

### Will & Decision
8. ❌ Вызов WillpowerGate более 1 раза за цикл
9. ❌ Использование RPG-матриц поведения как онтологии
10. ❌ Передача сырых дельт давления из текущего тика в DecisionHub (только T-1)
11. ❌ Возврат дефолтного `EmotionalVector` (aggression=0.0) из `IntentCompressor` для ATTACK
12. ❌ Использование переменных из локальной области другой функции (Python scoping trap)
13. ❌ Чтение `intent.action` без fallback на `parameters.semantic_action`

### Spatial & Movement
14. ❌ Использование `load_graph()` — мёртвый код
15. ❌ Сравнение legacy ID с canonical ID без `normalize_id()`
16. ❌ FLEE без исключения текущего узла NPC из кандидатов
17. ❌ Левый верхний угол комнаты как позиция узла в навигационном графе
18. ❌ Перезапись `local_position` для NPC в статусе `MOVING`
19. ❌ Прямая мутация `npc["position"]` или `npc["location"]`
20. ❌ Чтение позиций из `scene_state` (только `SpatialQueryService`)
21. ❌ Вызов `scene_manager.apply_changes()` из подписчиков
22. ❌ Вызов `process_intents()` или `apply_changes()` из `npc_orchestration.py`
23. ❌ Повторная обработка `MovementIntent` (инвариант `processed=True`)
24. ❌ `_enrich_local_positions` перетирает `local_position`, установленный пайплайном
25. ❌ `graph_compiler.py` без role-based aliases
26. ❌ `SpatialQueryService.visibility()` с неправильным порядком аргументов
27. ❌ CEI-2 использует `is_movement_blocked` для макро-навигации
28. ❌ spatial_runtime consumer-функции без `normalize_scene_state()`
29. ❌ Boundary node как цель движения или место обитания NPC

### Perception & Phenomenology
30. ❌ Хранение `EventDTO` в `EventBuffer` (только `FieldDisturbance`)
31. ❌ Обход `LocalCausalSolver` при генерации давления
32. ❌ Мутация состояния из `CausalObserver`
33. ❌ Прямая генерация эмоций из боевых событий (только через Perception)
34. ❌ `write_to_legacy` / `from_legacy` без `perceptual_kernel` и `affective_load`
35. ❌ Показ эмоций (fearful, anxious) — только наблюдаемые проявления (tense, rigid)
36. ❌ Смешивание cues и manifestations — отдельные каналы
37. ❌ Вычисление manifest в GameScreen — только чтение из perception data
38. ❌ Инъекция pain/shock напрямую в psyche dict (только через PK.somatic_urgency)

### Physiology & Combat
39. ❌ Прямая мутация HP аватара в обход `ImpactEngine`
40. ❌ `CombatSubscriber` пишет в Emotion (Domain Leakage)
41. ❌ `BehaviorManifestationService` читает эмоции вместо физиологии (Rule X)
42. ❌ Вызов `publish_classified_player_event` ДО `resolve_player_intent`
43. ❌ `shock_impulse` без decay в `PhysiologyDecayHandler`
44. ❌ `StateApplicator` проверяет `shock_impulse > 0.0` вместо `!= 0.0`
45. ❌ `NPCStateSnapshot` без поля `shock_impulse`
46. ❌ `PhysiologyDecayHandler` без проверки `life_status == "DEAD"`
47. ❌ `evaluate_vital_state` без DEATH LOCK
48. ❌ Двойная онтология: `wounds/conditions` (legacy) ≠ `body_state` (runtime truth)
49. ❌ Обработка player action без проверки `life_status`
50. ❌ `_make_player_snapshot()` без чтения `avatar_state.body_state`
51. ❌ Чтение `pain`/`fatigue` без нормализации `/100.0` в потребителях с порогами 0-1 (MSOC)

### Frontend & Presentation
52. ❌ Булева блокировка коллизий игрока (только Push-out Resolution)
53. ❌ Перезапись `result.world_snapshot` целиком в `game_loop_bridge.py`
54. ❌ Применение моторных смещений ПОСЛЕ отрисовки спрайта
55. ❌ Импорт `backend/app/` во фронтенд (Устав §1.1)
56. ❌ Передача игроку внутренних метрик NPC (HP, fear)
57. ❌ DM читает внутренние состояния NPC вместо `embodied_traces`
58. ❌ Фейковый нарратив при краше LLM ("Твоё сознание мутнеет...")

### Serialization & Persistence
59. ❌ `write_to_legacy` / `from_legacy` без `body_state`
60. ❌ Прямой конструктор `NPCState(...)` в тестах (только `from_legacy`)
61. ❌ `_apply_runtime_overlay` без белых списков для вычисленных полей (Invariant 1)
62. ❌ Персистенция `relationship_cache` внутри `NPCState` (SSOT = RelationshipStore)
63. ❌ Использование интегратора с утечкой для `affective_load` (только аттрактор насыщения)
64. ❌ Отсутствие idle-decay для `PerceptualKernel` (Rule 38)
65. ❌ AFFECTIVE_BOOT / подтягивание `affective_load` до порога `emotion_tag`
66. ❌ LifeEngine `_load_npcs()` без SQLite read-back
67. ❌ `load_npc_runtime()` возвращает `[]` вместо `None`

### Identity & Ontology
68. ❌ Кэширование `EffectiveDrives` (L3-P1 эфемерна)
69. ❌ Удаление событий из `L1Chronicle`
70. ❌ Коммит состояния с NaN или sum(drives) != 1.0 (OntologyViolationError)
71. ❌ Viability veto через `_drf_killed` или парсинг строк (только IntentDomain gate)
72. ❌ `MovementIntent` без поля `domain`
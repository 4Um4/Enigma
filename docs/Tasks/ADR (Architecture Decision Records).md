# ADR — Архитектурный Атлас ENIGMA

> **Формат:** Домен → Текущая парадигма → Эволюция (ключевые ADR) → ✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ → Убитые концепты → Архитектурные запреты.
> ИИ-ассистенту: ищи контекст по домену. Блоки `✅ ПОЧИНКИ` — это закрытые архитектурные баги, подтвержденные аудитом рантайма S50-53.

---

## 1. ФУНДАМЕНТ СИМУЛЯЦИИ И ВРЕМЯ (Core Pipeline & Time)
**Текущая парадигма:** Симуляция дискретна и каузально замкнута. Мутации проходят только через `DeltaBuffer`. Ретро-симуляция запрещена. 

**Эволюция (Ключевые ADR):**
- **ADR-001 (Delta Buffer):** Убита прямая мутация `all_npcs_raw`. Единственный путь: `Phase8Result → delta_buffer → StateApplicator.apply_batch()`.
- **ADR-002 (Time-driven vs Event-driven):** Разделение Фазы 0.5 (time-decay выполняется всегда) и Фазы 8 (event-driven, только при событиях).
- **ADR-013 (StateDeltas v2):** Плоский god-object заменен на `DeltaDomain` + типизированные frozen Payloads. Одна дельта = один домен.
- **ADR-047 (No Retro-simulation):** Убит `TICK_CATCHUP`. Пропущенное время не симулируется циклом `tick()`, а аналитически вычисляется через `reconcile_state(elapsed_seconds)`. Сложная причинность существует только в наблюдаемом времени.
- **ADR-059 (Dual-Time Ontology):** Транзиты привязаны к монотонному каузальному `scene_state["tick"]`, а не к реальному времени. Тик сохраняется при загрузке (`_preserved_tick`).
- **ADR-065 (Spatial Authority Consolidation):** Убита трехкратная ручная сборка `SpatialService.build_for_location()` в `TickOrchestrator`. Внедрен `_resolve_spatial_service()`.
- **ADR-066 (Single Movement Ownership):** Убит двойной вызов `process_intents()` в `npc_orchestration.py` и `TickOrchestrator`. Единственный владелец исполнения `MovementIntent` — `TickOrchestrator`. В доменную модель добавлен инвариант: повторная обработка интента с `processed=True` вызывает `RuntimeError`. Один Intent → один Executor → одно будущее.
- **ADR-089 (Campaign ID Integrity):** Убита подмена `campaign_id` на `location_id` в `execute_player_finalize`. `campaign_id` берется из аргумента функции, а не из `scene_state`. Нарушение приводило к смерти `SpatialService` при ходе игрока (поиск графа в несуществующей папке кампании).
- **ADR-102 (SpatialService replaces load_graph + FLEE Fix):** Убит мёртвый `load_graph()` — возвращал пустой граф (0 узлов) после удаления fallback. Заменён на `SpatialService.build_for_location()` в `spatial_runtime.py`. Для работы SpatialService добавлен инжект `campaign_id` в `scene_state` через `get_scene_state()`. Также починен FLEE-резолв: `get_furthest()` теперь принимает `exclude_node_ids` для исключения текущего узла NPC; нормализация legacy ID (`room_1` → `tavern:room_1`) перед сравнением устраняет бегство NPC в свой же узел. Также `spatial_obstacles` пробрасывает `type` (bar, table, chair) из editor JSON на фронтенд для рендера спрайтов вместо заглушек.

**✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ (Аудит S50-53):**
- **GAP1 (Когнитивный Оверлей):** УБИТ ADR-081. Темпоральная асимметрия устранена. Критический шок (`shock_impulse > 0.5`) инжектится в `all_npcs_raw` мгновенно (T+0) наравне с директивами. *Верифицировано: `tick_orchestrator.py:634`*.
- **NoneType finalize_result:** УБИТ ADR-085. `execute_player_finalize` не пробрасывал `player_result` в `_TickContext`, из-за чего метод возвращал `None` и крашил пайплайн. *Верифицировано: `tick_orchestrator.py:537`*.

**Убитые концепты:**
- *ADR-024 (Event-Sourced Global Reducer):* Идея глобального редюсера всех событий. Приводила к NP-hard проблеме. Заменена локальными кластерами CFRM.
- *Динамическая синхронизация `player_spatial` (S47):* Попытка обновлять `npc_positions["player"]` из `player_spatial` и внедрять точные координаты цели (`target_local_xy`). Откатана — ломала рантайм-конвейер движения и вызывала массовую телепортацию к `entrance`.

**Архитектурные запреты:**
- ❌ Прямая мутация стейта в обход `DeltaBuffer`.
- ❌ Циклы `tick()` для нагона времени (TICK_CATCHUP).
- ❌ Формирование ответа Фазы 8 через `List[dict]`.
- ❌ Подмена `campaign_id` на `location_id` в `_TickContext` (ADR-089).
- ❌ Использование `load_graph()` — мёртвый код, возвращает пустой граф (ADR-102).
- ❌ Сравнение legacy ID (`room_1`) с canonical ID (`tavern:room_1`) без нормализации через `spatial_service.normalize_id()` (ADR-102).
- ❌ FLEE без исключения текущего узла NPC из кандидатов (ADR-102).

---

## 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЯ (Will, Pressure & Decision)
**Текущая парадигма:** Решения NPC рождаются из искривленного пространства полезности (Utility Deformation). Воля — инерция, а не порог. Подчинение требует легитимности. Аватар игрока подчиняется тем же законам (декларативно).

**Эволюция (Ключевые ADR):**
- **ADR-031 (Cumulative Strain Model):** Убита матрица `action × temperament`. Введен `IntentPressureResolver` → `IntentPressureProfile`. Шкала деградации COMPLY → CONDITIONED.
- **ADR-034 (Phase 1 Boundary Adapter):** Бизнес-логика воли изгнана из `game_loop`. Фаза 1 — только чистая функция `resolve_player_intent()`.
- **ADR-036 (Single Will Evaluation):** Убит Double Invocation. WillpowerGate вызывается строго 1 раз за цикл.
- **ADR-037 (Affect Resonance):** Аффект — не бафф, а искажение интерпретации (Resonance → Distortion → `AmplifiedPressureProfile`).
- **ADR-046 (Inverted Fear):** Убит хардкод `base += 0.6`. Страх перед авторитетом бустит `Intent.APPROACH`, а не подавляет его.
- **ADR-050 (DecisionContext & Feasibility):** DecisionHub разделен на Фазу 1 (Feasibility Filtering — удаление невозможных) и Фазу 2 (Utility Deformation — искривление ландшафта).
- **ADR-056 (Attention Capture):** Хардкод-порог `initiative_suppression > 0.7` заменен на `recent_directive` с механизмом сжигания директивы.
- **ADR-057 (Legitimacy Gate):** Нет страха/доверия = Irritation (снятие блоков агрессии) вместо Obedience. **Реализация:** Внутренний `if/else` в `DirectiveInterpretationSubscriber` (рассчитывает `obedience_intensity` против `irritation_intensity` при `legitimacy > 0.3`).
- **ADR-064 (Directive Data Continuity):** Убит Баг #6 (Глухая Воля). `DirectiveInterpretationSubscriber` получает `all_npcs_raw` через fallback на `DMContextDTO`.
- **ADR-067 (Player Command Override):** Приказ игрока перекрывает ЛЮБОЕ решение DecisionHub, включая `flee`. Игрок — авторитетный источник причинности (ADR-061). Убран guard `if decision.intent.value not in ("approach", "flee")` — рефлекс проверяется всегда, override происходит при несовпадении с `approach`.
- **ADR-068 (Partial Name Matching):** NPC с составными именами ("торнин серебряная луна") теперь отзываются на часть имени ("торнин"). Рефлекс проверяет отдельные слова (≥3 символа), а не только полное имя. Без этого NPC с длинными именами были глухи к приказам.
- **ADR-088 (Fast Path Emotional Injection):** Убит мертвый `EmotionalVector` в Fast Path. `IntentCompressor` теперь маппит `ActionType` в эмоции (ATTACK → aggression=0.8). Без этого Воля аватара не видела агрессию и сопротивлялась на 15%.

**✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ (Аудит S50-53):**
- **GAP2 (Амнезия Сопротивления):** УБИТ ADR-082. `compute_willpower` читает `trauma_markers`. Каждая травма повышает `identity_rigidity` на +0.1 (макс +0.3). *Верифицировано: `will.py:122-125`*.
- **GAP4 (Ингибирование Шоком):** УБИТ ADR-077. `DirectiveInterpretationSubscriber` читает `shock_impulse` из `target_dict.body_state`. `shock > 0.7` ингибирует подчинение. *Верифицировано: `directive_interpretation_subscriber.py:58`*.
- **GAP5 (RPG Витализм):** УБИТ ADR-076. `state_interpreter.py` читает `pain`, `shock_impulse` и `blood_loss` из `body_state`. Боль и шок перекрывают HP. *Верифицировано: `state_interpreter.py:273-291`*.
- **Silent Crash Трубы Воли:** УБИТ ADR-083. `will.py`/`affect.py` обращались к `intent.action`, в то время как DTO содержит `semantic_action` в `parameters` (ADR-035). `AttributeError` перехватывался верхним `try/except`, и Воля тихо умирала. Добавлен безопасный fallback с приоритетом `parameters`. *Верифицировано: `will.py:30-32`, `affect.py:56-60`*.

**Убитые концепты:**
- *ADR-030 (RPG Will Matrix):* Бинарная модель `action × temperament`.

**Архитектурные запреты:**
- ❌ Вызов WillpowerGate более 1 раза за цикл.
- ❌ Использование RPG-матриц поведения как онтологии.
- ❌ Передача сырых дельт давления из текущего тика в DecisionHub (только T-1) — *НАРУШЕНО хаком COGNITIVE_OVERLAY (см. Раздел 1)*.
- ❌ Возврат дефолтного `EmotionalVector` (aggression=0.0) из `IntentCompressor` для ATTACK (ADR-088).

---

## 3. ВОСПРИЯТИЕ И ФЕНОМЕНОЛОГИЯ (CFRM & Perception)
**Текущая парадигма:** Объективных фактов нет. Есть возмущения поля (`FieldDisturbance`), которые проецируются в субъективные феномены. Perception обновляется ДО Emotion.

**Эволюция (Ключевые ADR):**
- **ADR-025 (CFRM Core):** Глобального World нет. Введены `ClusterGraph`, `EventBuffer`, `MembraneField`. NPC хранит `PerceptualKernel`.
- **ADR-029 (CFRM Layer 1):** Spatial Index для O(1) поиска. Классификация событий по осям (PHYSICAL, COGNITIVE, SOCIAL).
- **ADR-033 (Deobjectification P2):** Смерть объективных событий. `EventDTO` превращается в `FieldDisturbance`. Восприятие вычисляется локально `LocalCausalSolver`.
- **ADR-040 (Epistemic Classification):** Введен `ClassificationResult` с `confidence`. Фallback-события имеют вес 0.2.
- **ADR-042 (Perception Domain):** Реальность течет в восприятие (`PerceptionPayload`), а не напрямую в эмоции.

**✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ (Аудит S50-53):**
- **GAP6 (Синдром Глухого Общества):** Убит [S50]. Проблема была в потере семантики (GAP8).
- **GAP7 (Слепота Аватара):** Убит [S53]. Игрок парсится как наблюдатель в `_extract_observer_state`. Аватар получает давление от паники толпы. *Верифицировано: `local_causal_solver.py:320-324`*.

**Архитектурные запреты:**
- ❌ Хранение `EventDTO` в `EventBuffer` (только `FieldDisturbance`).
- ❌ Мутация состояния из CausalObserver.
- ❌ Прямая генерация эмоций из боевых событий (только через Perception).

---

## 4. ПРОСТРАНСТВО И ЛОКОМОЦИЯ (Spatial & Movement)
**Текущая парадигма:** `SpatialQueryService` — единственный авторитет координат. Движение — *результат* давления. Жесткое разделение макро-навигации (LOD1) и микро-рулежки (LOD0). Жизненный цикл движения отделен от личности.

**Эволюция (Ключевые ADR):**
- **ADR-008 (Spatial Centralization):** Убит глобальный `_connections_data` и кэш `_graphs`. Единственный источник — `SpatialService`.
- **ADR-010 (Macro/Micro Zones):** Архетипы переведены на макро-зоны. Убита парализация из-за микро-зон.
- **ADR-019 (Traversal State):** Диагноз телепортации. Введен `TraversalState` как презентационный артефакт.
- **ADR-048 (Single Spatial Authority):** Чтение `scene_state["player_distances"]` запрещено. Внедрен `SpatialQueryService`.
- **ADR-051 (LifeEngine De-godification):** LifeEngine лишен права прямой мутации позиции.
- **ADR-052 (LOD0/LOD1 Split):** Нормализация префиксов. Починка Silent Data Loss с интентами.
- **ADR-060 (Movement Ontology Split):** `MovementIntent` объединяет LOD0 и LOD1. `LocalSteeringIntent` отвергнут.
- **ADR-061 (Player Position Authority):** `player_spatial` — мёртвый источник (запись запрещена ADR-048 Phase 3). Фикс: `npc_positions.player` — единственный источник, `player_spatial` — только fallback при отсутствии.
- **ADR-069 (target_local_xy Propagation):** При `reactive:approach` координаты цели (позиция игрока) пробрасываются через `MacroMovementGoal.target_local_xy` → `SceneChange.target_local_xy` → `scene_state_manager`. Ранее координаты вычислялись в `_resolve_reactive_movement`, но терялись при создании `MacroMovementGoal` → NPC шли к центру узла вместо точной позиции.
- **ADR-070 (Ghost Position Interpolation):** При создании нового транзита, если NPC уже в активном транзите, `from_xy` вычисляется интерполяцией текущего прогресса по waypoints старого транзита. Без этого новый транзит начинался с устаревшей `local_position` → визуальная телепортация назад.
- **ADR-071 (Bridge Traversal Propagation):** `game_loop_bridge.py` пробрасывает `active_traversals` в `world_snapshot`. Без этого фронтенд не мог интерполировать движение — `_resolve_visual_xy` не находил waypoints и рисовал по `local_position` (старая позиция).
- **ADR-072 (Enrichment LOD0 Guard):** `_enrich_local_positions` больше не перетирает `local_position` для сдвинувшихся NPC. Если позиция уже валидна (установлена пайплайном), enrichment пропускает. Ранее NPC, получивший `micro_snap`, при следующей загрузке `scene_state` перетирался на центр узла из графа.
- **ADR-073 (Adjacency Inference):** Внедрен алгоритм вывода связей из смежности полигонов в `graph_compiler.py`. Если Map Editor не дал `passages`, компилятор автоматически строит связи между комнатами на основе пересечения bounding box. Двери фильтруют проходимость, но не определяют топологию (поддержка разрушаемости).
- **ADR-095 (Centroid Graph Compilation):** `graph_compiler.py` вычисляет центр комнаты (`x + w/2`, `y + h/2`) вместо левого верхнего угла. Устраняет телепортацию NPC в углы стен при макро-движении (FLEE/schedule).
- **ADR-096 (Frontend Traversal Respect):** Если NPC в статусе `MOVING`, фронтенд не перезаписывает `local_position` из `npc_positions`, позволяя рендереру плавно интерполировать движение. Устраняет массовую телепортацию при Action-тиках.

**✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ (Аудит S50-53):**
- **GAP12 (Парадокс Призрачной Позиции):** Убит [S50]. `_enrich_local_positions` вычисляет интерполированную позицию для NPC в активном транзите. *Верифицировано: `scene_state_manager.py:1145,1585`*.
- **GAP9 (Конфликт Транзитов):** Убит [S51]. Сон блокируется непрерывными скалярами `threat_gradient > 0.3` и `stress > 50`. *Верифицировано: `life_engine.py:1179-1182`*.
- **GAP10 (Незваные NPC):** Убит [S52]. `EventContext` обогащён `target_id`. DecisionHub фильтрует бонус `APPROACH`. *Верифицировано: `decision_hub.py:916`*.

✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ (Аудит S50-54):

GAP11 (Хардкод Глаголов): УБИТ S54. Хардкод _MOVE_VERBS удалён. IntentCompressor распознаёт наречия/местоимения 1-го лица ("сюда", "мне") и устанавливает target_reference='player'. Semantic Bridge пробрасывает MOVE + player в пайплайн. Верифицировано: intent_compressor.py:93-98, npc_tick_pipeline.py:467-472.

✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ (Аудит S58):
- **Mass FLEE Teleportation:** УБИТ ADR-096 [S58]. Фронтенд перезаписывал `local_position` из `npc_positions`, игнорируя `active_traversals`. Рендерер не мог интерполировать движение, телепортируя NPC в центр целевого узла. Решение: блокировка обновления `local_position` при статусе `MOVING`. *Верифицировано: S58, NPC плавно перемещаются между комнатами при FLEE*.
- **Corner Trap Teleportation:** УБИТ ADR-095 [S58]. `graph_compiler` использовал левый верхний угол комнаты как координату узла. NPC прыгали в углы стен при макро-движении. Решение: вычисление центроида. *Верифицировано: S58, `graph_compiler.py` возвращает центр комнаты*.
- **Double Truth Spatial Graphs (Debt):** ВЕРИФИЦИРОВАН РАЗРЫВ [S58]. Обнаружено дублирование: канонический `SpatialService` (`graph_compiler.py`) и легаси `LocationGraph` (`location_graph.py`). Легаси-граф не знает про центроиды, используется `spatial_runtime.py` для расчёта дистанций.

**Архитектурные запреты:**
- ❌ Использование левого верхнего угла комнаты как позиции узла в навигационном графе (только центроид ADR-095).
- ❌ Перезапись `local_position` для NPC в статусе `MOVING` из `npc_positions` (нарушает трубу TraversalState ADR-096).
- ❌ Прямая мутация `npc["position"]` или `npc["location"]`.
- ❌ Чтение позиций из `scene_state` (только `SpatialQueryService`).
- ❌ Вызов `scene_manager.apply_changes()` из подписчиков.
- ❌ Использование `TraversalState` без `MovementEngine`.
- ❌ Вызов `process_intents()` или `apply_changes()` из `npc_orchestration.py` (единственный владелец — `TickOrchestrator`).
- ❌ Повторная обработка `MovementIntent` (инвариант `processed=True`).
- ❌ `_enrich_local_positions` перетирает `local_position`, установленный пайплайном (LOD0 guard).
- ❌ Хардкод языковых глаголов в `npc_tick_pipeline.py` (после починки Semantic Bridge).
- ❌ Зависимость компиляции графа от ручной простановки `passages` при наличии полигонов комнат (ADR-073).

---

## 5. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat)
**Текущая парадигма:** Тело — инерционная система. Бой — не режим, а давление на физику. Удар порождает каскад: Сила → Боль → Шок → Эмоция.

**Эволюция (Ключевые ADR):**
- **ADR-015 (Physiology Domain):** Убиты RPG Hit Roll и AC. Введены `body_profile`, `InjuryDTO`, ImpactEngine (Pure Function).
- **ADR-020 (DRSL):** Введен `ReductionPolicy`. Тело не складывается (`ADDITIVE`), оно эволюционирует (`PHYSICS_COMPOSITE`).
- **ADR-021 (CombatSubscriber):** Мост `EventDTO → ImpactEngine`. Возвращает ТОЛЬКО Physiology-дельты.
- **ADR-022 (Leaky Integrator):** Физиология затухает по экспоненте `S_t = S_{t-1} * exp(-lambda * dt)`.
- **ADR-027 (Layered Reduction):** Каскад в рамках одного тика: Physical → Materialization → Cognitive → Social.
- **ADR-028 (Config Migration):** `combat_stats` удалены из JSON.

**✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ (Аудит S54):**
- **NameError blood_loss_delta:** УБИТ ADR-084. `state_applicator.py` использовал переменную без извлечения из `PhysiologyPayload`. Добавлена строка экстракции. *Верифицировано: `state_applicator.py:427`*.

**✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ (Аудит S59):**
- **Silent Loss Physiology (asdict):** УБИТ ADR-099. `state_applicator.py` — `asdict` не импортирован на уровне модуля (только внутри локальной области строки 164). При `add_injuries` непустом (structural_damage > 20) → `NameError` → ВСЯ PhysiologyPayload дельта пропускалась → `body_state` никогда не создавался. Фикс: `from dataclasses import asdict` на уровне модуля. *Верифицировано: S59, `[PHASE8_APPLY] npc=thief_shadow body_state_keys=['current_hp', 'pain', ...]`*.
- **Serialization Black Hole (body_state):** УБИТ ADR-100. `NPCState.write_to_legacy()` не писал `body_state` в npc_dict → физиология терялась при каждой сериализации. `NPCStateAdapter.from_legacy()` не читал `body_state` → state.body_state всегда начинался пустым. Фикс: добавлено чтение/запись `body_state` в оба метода. *Верифицировано: S59, idle tick `body_state=FOUND pain=48.58`*.
- **Rule X Violation (BehaviorManifestation):** УБИТ ADR-101. `BehaviorManifestationService._manifest_npc()` читал только `stress_delta` и `psyche_state`, полностью игнорируя `body_state` (pain/blood_loss/shock_impulse) — прямое нарушение Правила X (CAUSAL_CONTRACT §7). Фикс: построение `body_state_map` из `all_npcs_raw`, чтение физиологии для вычисления `locomotion_instability`, `micro_pause_density`, `action_interruption`. *Верифицировано: S59, `[ACTION_PERCEPT] npc=thief_shadow instab=1.00 mpd=1.00 act_int=0.96`*.
- **shock_impulse Not Applied:** УБИТ ADR-102. `StateApplicator._apply_deltas()` извлекал `shock_impulse` из payload, но не применял его к `body_state`. Поле существовало в `PhysiologyPayload`, но терялось при записи. Фикс: добавлено `state.body_state["shock_impulse"] = min(1.0, _cur_shock + shock_impulse)`. *Верифицировано: S59, `shock=0.96` персистируется между тиками*.
- **NPC ID Fallback (apply_batch):** УБИТ ADR-103. `StateApplicator.apply_batch()` искал NPC только по `npc_dict.get("id")`, но NPC dict может использовать `"npc_id"`. Фикс: `npc_dict.get("id") or npc_dict.get("npc_id")`. *Верифицировано: S59, дельты применяются корректно*.
- **Idle Tick Perception Blindness:** УБИТ ADR-104. `_phase_9_integration()` вызывал `produce_traces()` без `all_npcs_raw` → `body_state` всегда `None` в idle тиках. Фикс: передача `all_npcs_raw=ctx.all_npcs_raw`. *Верифицировано: S59, idle tick `[MANIFEST_RAW] all_npcs_raw count=6`*.

**✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ (Аудит S60):**
- **Semantic Action Lost in Transit:** УБИТ ADR-105. `publish_classified_player_event` вызывался в `dm_phase.py` ДО `resolve_player_intent()` → `shared_context.intent_resolution` был `None` → `_semantic_action=None` → ADR-091 override не срабатывал. Фикс: перенос вызова в `__init__.py` ПОСЛЕ установки `intent_resolution`. *Верифицировано: S60, `[ADR-091] IntentCompressor override: DM_Router='player_attacks' → IC='attack'`*.
- **UnboundLocalError _legacy_d (Memory Black Hole):** УБИТ ADR-106. В `npc_tick_pipeline.py` `_legacy_d = LegacyStateDeltaAdapter.collapse()` определена внутри первого `elif` (стр.144), но читалась во втором `elif` (стр.152) → `UnboundLocalError` → `[MEMORY] apply failed` для 6/6 NPC каждый тик. Память была полностью мертва. Фикс: вынесено до ветвления if/elif. *Верифицировано: S60, `[MEMORY] apply failed` исчез из логов*.
- **VerbalizationContext TypeError:** УБИТ ADR-107. `intent_target: Optional[str]` без `= None` — мина замедленного действия. `physical_state` дефолт заменён с `"невредим"` на `"unharmed"` (L10n-safe). *Верифицировано: S60, smoke-test пройден*.
- **UrgencyLevel Duplicates EmotionTag:** ДИАГНОСТИРОВАН ADR-108. `StateInterpreter._stress_to_word()` вычисляет `UrgencyLevel` (SCARED/PANIC/BROKEN) из `NPCState.stress`, дублируя `EmotionTag` (fearful/panic) который вычисляется `EmotionResolution` с учётом личности. Трассировка показала: `NPCStateDescription.emotional_state` — мёртвое поле (нет потребителей). `VerbalizationContext.emotion` и `emotional_nuance` — dormant (потребитель не найден, статус unresolved). Double Truth не проявляется в runtime (нет потребителя у UrgencyLevel), но архитектурный долг существует — два владельца одной концепции. Зафиксировано в `architecture/physiology.yaml`. *Верифицировано: S60, полная трассировка 6 путей эмоций к LLM*.

**✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ (Аудит S60b):**
- **Shock Immortality (shock_impulse без decay):** УБИТ ADR-109. `shock_impulse` не затухал между тиками — боль уменьшалась (48→46), а шок оставался 0.96 бесконечно. 4 причины: (1) `NPCStateSnapshot` не содержал поле `shock_impulse`; (2) `_build_npc_snapshots()` не извлекал из `body_state`; (3) `PhysiologyDecayHandler.handle()` не вычислял decay для shock; (4) `StateApplicator` проверял `shock_impulse > 0.0` — блокировал отрицательные дельты decay. Фикс: добавлено `SHOCK_DECAY_LAMBDA=0.08` (~8% за тик, быстрее боли), поле в snapshot, извлечение, условие `!= 0.0`. *Верифицировано: S60b, `shock=0.6→0.5539→0.5113`*.
- **CombatSubscriber NPCStateSnapshot без shock_impulse:** УБИТ ADR-110. `_build_snapshot()` и `_make_player_snapshot()` в `combat_subscriber.py` не передавали `shock_impulse` в `NPCStateSnapshot` → ImpactEngine видел `shock=0.0` всегда. Фикс: добавлено поле в оба метода. *Верифицировано: S60b, компиляция без ошибок*.
- **Print-диагностика в production:** УБИТ ADR-111. 13 `print()` вызовов в `combat_subscriber.py`, `tick_orchestrator.py`, `state_applicator.py` — протокол VIII.5 требовал print для диагностики, но в production это шум. Конвертированы в `logger.debug()`. Safeguard print'ы (PHASE8_CTX_CRASH, PHASE8_CRASH) оставлены. *Верифицировано: S60b, компиляция без ошибок*.

**Архитектурные запреты:**
- ❌ Прямая мутация HP аватара в обход `ImpactEngine`.
- ❌ `CombatSubscriber` пишет в Emotion (Domain Leakage).
- ❌ Использование RPG-абстракций (Hit Roll, AC).
- ❌ `BehaviorManifestationService` читает эмоции (psyche.fear/stress) вместо физиологии (body_state.pain/blood_loss/shock_impulse) — Правило X (CAUSAL_CONTRACT §7).
- ❌ `write_to_legacy` / `from_legacy` без сериализации `body_state` — физиология теряется между тиками.
- ❌ `StateInterpreter` вычисляет психологические категории (UrgencyLevel.SCARED и др.) из `stress` — это дублирует `EmotionResolution` без учёта личности (ADR-108).
- ❌ Вызов `publish_classified_player_event` ДО `resolve_player_intent` — `_semantic_action` всегда `None` (ADR-105).
- ❌ `shock_impulse` без decay в `PhysiologyDecayHandler` — шок становится перманентным (ADR-109).
- ❌ `StateApplicator` проверяет `shock_impulse > 0.0` вместо `!= 0.0` — блокирует отрицательные дельты decay (ADR-109).
- ❌ `NPCStateSnapshot` без поля `shock_impulse` — decay handler и combat subscriber слепы к шоку (ADR-109, ADR-110).

---

## 6. СОЦИАЛЬНАЯ ФИЗИКА И ПАМЯТЬ (Social & Memory)
**Текущая парадигма:** Социальные акты (приказы) искривляют utility-space цели. Память многослойна и управляется строго через MemoryManager.

**Эволюция (Ключевые ADR):**
- **ADR-005/006 (NPC Social Mapping):** Маппинг `social_stats` в `relationship_cache`. Обогащение из `village_relations.json`.
- **ADR-007 (Idle Sync):** Синхронизация `all_npcs_raw` в idle-пути.
- **ADR-043 (Social Physics):** Приказ генерирует `directive_obedience` (давление), а не `MovementIntent`.

**✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ (Аудит S50-53):**
- **GAP8 (IntentEventAdapter Data Loss):** Убит [S50]. `CommunicationIntent` обогащен `semantic_action` и `target_id`. `IntentEventAdapter` пробрасывает их в payload `NPC_SPOKE`. *Верифицировано: `intent_event_adapter.py:46`*.
- **GAP13 (Player-Only Social Physics):** УБИТ ADR-080. `DirectiveInterpretationSubscriber` вычисляет легитимность по `source_id`. NPC-to-NPC власть жива. *Верифицировано: `directive_interpretation_subscriber.py:77-92`*.

**Архитектурные запреты:**
- ❌ Публикация в память в обход `MemoryManager`.
- ❌ `DirectiveInterpretationSubscriber` генерирует `MovementIntent`.
- ❌ Вызов директивы без инъекции `all_npcs_raw`.

---

## 7. ФРОНТЕНД, ПРЕЗЕНТАЦИЯ И ВВОД (UI & Embodiment)
**Текущая парадигма:** Фронтенд — сенсорный орган, искажающийся вместе с аватаром. Ввод проходит через моторное сопротивление и семантическое сжатие.

**Эволюция (Ключевые ADR):**
- **ADR-011/014 (Narrative Beats):** Убран плоский чат. Введены пузыри, спикеры, фильтрация эха.
- **ADR-035 (Intent Compression):** Русская морфология (pymorphy3 Fast Path + LLM Slow Path). Галлюцинации LLM отсекаются Pydantic.
- **ADR-038 (Embodied Perception DTO):** Бэкенд присылает скаляры давления и моторные импульсы, а не RPG-статы.
- **ADR-039 (Resistance Medium):** Конфликт воли = инфекция поля ввода (`text_input.infect()`). Феноменологический рендеринг (S-curve инерция).
- **ADR-041 (Will Conflict Data):** Проброс конфликта воли через API.
- **ADR-068 (Avatar Flesh Injection & API Suturing):** Труба Эмбодимента (Воля и Физиология) была оборвана на 3 уровнях: 1) Бэкенд собирал словарь аватара без `body_state` и `psyche` (сборка трупа), из-за чего ассемблер всегда возвращал `stability=1.0`. 2) API маршрутизатор `routes.py` выбрасывал `will_conflict_data` для Action-тиков. 3) Фронтенд не извлекал эти данные из ответа. Решение: инъекция живого стейта из `avatar_service` в `all_npcs_raw`, проброс `will_conflict_data` в API и вызов `infect()` на фронтенде.

**✅ ВЕРИФИЦИРОВАННЫЕ ПОЧИНКИ (Аудит S50-53):**
- **Эмбодимент Отключен (Embodiment Unwired):** Убит [S48/S53]. `GameScreen` извлекает `will_conflict_data` и вызывает `text_input.infect()`. `avatar_state` обновляется, передаваясь в `PresentationFirewall` и `PerceptualMomentum`. Аватар получает давление от паники толпы (GAP7).
- **Труба Эмбодимента Замкнута:** УБИТ ADR-086. `will_conflict_data` проверенно доходит от `tick_orchestrator` через `shared_context` (та же ссылка `id()`) до `text_input.infect()` на фронтенде. Поле ввода заражается моторным импульсом ("Замереть..."). *Верифицировано: рантайм-аудит `[EMBODIMENT_TRACE]` показывает `{'state': 'reluctant', 'resistance': 0.15, 'embodied_vector': 'freeze', 'counter_offer_text': 'Замереть...'}`*.
- **Расширение Fast Path словаря:** УБИТ ADR-087. `IntentCompressor._ACTION_LEMMAS` расширен приставочными глаголами (`выбить`, `откусить`, `укусить`, `душить`, `пнуть` и т.д.). pymorphy3 даёт лемму приставочного глагола как есть, не сворачивая к корню. *Верифицировано: `intent_compressor.py:32`*.
- **The Fool v2 Pipeline:** УБИТ ADR-092. Визуализация моторных следов (дрожь, замер, тултипы) не отображалась на экране, несмотря на наличие данных в `PerceivedEntity`. Причина 1: `game_loop_bridge.py` перезаписывал `world_snapshot` целиком, уничтожая `player_perception` при idle-тиках. Причина 2: `scene_renderer.py` применял смещение дрожи к мировым координатам `render_x/y` ПОСЛЕ отрисовки спрайта по экранным `sx/sy`, и ховер-зона улетала. Решение: мост обновляет только `npc_positions` в существующем snapshot. Рендерер применяет `is_shaking` и `instability` к `sx/sy` ДО `self.screen.blit()`. *Верифицировано: S56, NPC дрожат, тултипы "Напряженная поза" появляются при наведении*.
- **The Fool Phase 3 (DM Observational Pipeline):** УБИТ ADR-093 [S57]. DM-агент был слеп к наблюдаемым симптомам NPC — `player_perception` с `embodied_traces` не пробрасывался в DM-контракт. Также `player_perception` не был легализован в `PipelineContext` (архитектурное нарушение). Решение: поле `player_perception` добавлено в `PipelineContext`; DM-агент читает `embodied_traces` (не `peripheral_cues` — те существуют только в API-ответе для фронтенда) и формирует блок "Наблюдаемые симптомы NPC" с моторными симптомами (дрожит, покачивается, напряжённая поза). DM описывает видимые следы, а не внутренние состояния. *Верифицировано: S57, DM-промпт содержит блок симптомов, LLM описывает "зрачки расширены от ужаса и напряжения"*.
- **RPG Vitalism Revival (StateInterpreter Alive):** УБИТ ADR-094 [S57]. `StateInterpreter.interpret()` импортировался в `npc_tick_pipeline.py`, но НИКОГДА не вызывался — мёртвый код. `VerbalizationContext` не имел поля `physical_state`. Шкала `pain` в `StateApplicator` — 0-100, а пороги в `StateInterpreter` — 0.9/0.6/0.3 (под 0-1). Решение: нормализация `pain / 100.0` при чтении; `interpret()` вызывается в `build_verbalization_context`; поле `physical_state` добавлено в `VerbalizationContext`. NPC знает свою боль при само-вербализации. *Верифицировано: S57, `_npc_desc = _interpreter.interpret(state_for_llm)` в `npc_tick_pipeline.py:208`*.
- **Push-out Resolution:** УБИТ ADR-097 [S58]. Булева проверка коллизий приводила к застреванию игрока между стульями и столами (Corner Trap). Решение: Push-out Resolution (выталкивание по вектору проникновения) + уменьшение `PLAYER_RADIUS` до 0.25. *Верифицировано: S58, игрок скользит вдоль мебели*.
- **AABB Coordinate Contract:** УБИТ ADR-098 [S58]. `scene_renderer.py` трактовал `x, y` как центр объекта, сдвигая визуал влево-вверх от реальной физики. Решение: чтение `x, y` как левого верхнего угла (соответствует бэкенду). *Верифицировано: S58, визуал мебели совпадает с хитбоксами*.

**Архитектурные запреты:**
- ❌ Булева блокировка коллизий игрока (только Push-out Resolution ADR-097).
- ❌ Перезапись `result.world_snapshot` целиком в `game_loop_bridge.py` (уничтожает `player_perception`). Только точечное обновление ключей.
- ❌ Применение моторных смещений (дрожь) к координатам ПОСЛЕ отрисовки спрайта. Смещение применяется ТОЛЬКО ДО `self.screen.blit()`.
- ❌ Импорт `backend/app/` во фронтенд (Устав §1.1).
- ❌ Передача Игроку внутренних метрик NPC (HP, fear).
- ❌ DM-агент читает внутренние состояния NPC (pain, fear, shock) напрямую вместо `embodied_traces` (Kernel Leakage).
- ❌ Масштабная несовместимость: `StateApplicator` пишет `pain` в 0-100, а интерпретаторы читают в 0-1 (нормализация `/100` обязательна).
- ❌ Обработка клавиши `Ё` только через `pygame.K_BACKQUOTE` без `event.unicode` (русская раскладка Windows).
- ❌ Использование `asdict()` на границе API без валидации.

---

## 8. НАБЛЮДАЕМОСТЬ И ДИАГНОСТИКА (CDS & Sandbox)
**Текущая парадигма:** Наблюдение не создает причинность. Тестирование каузальных цепей через изолированные Осциллографы.

**Эволюция (Ключевые ADR):**
- **ADR-003 (Test Determinism):** Убраны I/O фикстуры, введены синтетические фабрики.
- **ADR-004 (Phase 8 Handlers):** Memory/Scene обработчики признаны ненужными.
- **ADR-009 (DI Primitives):** В `InterpretationEngine` передаются примитивы, а не объекты.
- **ADR-045 (Causal Oscilloscope):** Создан `DeterministicClock` и `CausalTrace` для верификации причинности.
- **CDS Integration (S39):** Интеграция пассивной системы диагностики.

**Архитектурные запреты:**
- ❌ Обратная связь из CDS в рантайм симуляции.
- ❌ Прерывание каузального потока при падении CDS.

---

### Почему этот формат спасает проект:
1. **Поиск по смыслу:** Разработчик, сталкивающийся с тем, что NPC подчиняется в нокауте, открывает секцию **2. ВОЛЯ** и сразу видит `Shock Inhibition Gap`.
2. **Контраст эволюции:** Четко видны "Убитые концепты" и живые "Разрывы". ИИ больше не предложит вернуть RPG-матрицу, но будет знать, что нужно починить мост `Physiology -> DecisionContext` или `IntentEventAdapter payload`.
3. **Синхронизация с рантаймом:** Формат отражает не желаемое состояние, а **исполняемую правду**, подтвержденную аудитом терминала, вплоть до конкретных строк кода и потерянных полей DTO.
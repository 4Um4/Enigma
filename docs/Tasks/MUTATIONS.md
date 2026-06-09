# MUTATIONS.md — Каузальная Эволюция ENIGMA

> **Формат:** Домен → Хронология сессий → Запреты. Ищи по `Ctrl+F S##` или домену.

---

## 0. НАВИГАЦИЯ

| С | Дата | Домен | Тип | Теги |
|---|------|-------|-----|------|
| S03 | ? | 6 | Эвол | - |
| S04 | ? | 1 | Эвол | - |
| S08 | ? | 6 | Эвол | - |
| S10 | ? | 1/7 | Эвол | - |
| S16 | ? | 4 | Эвол | - |
| S18 | ? | 7 | Эвол | - |
| S19 | ? | 2 | ADR | ADR-031 |
| S20 | ? | 4 | Эвол | - |
| S21 | ? | 2/3 | Эвол | - |
| S24 | ? | 2 | ADR | ADR-036 |
| S25 | ? | 2/7 | Эвол | - |
| S26 | ? | 3/7 | Эвол | - |
| S27 | ? | 6 | Эвол | - |
| S28 | ? | 5/7 | Эвол | - |
| S29 | ? | 1/2 | Эвол | - |
| S30 | ? | 3/4 | Эвол | - |
| S31 | ? | 2 | ADR | ADR-050 |
| S32 | ? | 1/6 | Эвол | - |
| S33 | ? | 1 | FIX | - |
| S34 | ? | 5 | Эвол | - |
| S35 | ? | 1/2 | Эвол | - |
| S36 | ? | 2/5 | ADR | ADR-058 |
| S37 | ? | 1 | ADR | ADR-048 |
| S38 | ? | 1/3 | Эвол | - |
| S39 | ? | 7/8 | Эвол | - |
| S46 | ? | 1 | ADR | ADR-048 |
| S47 | ? | 1/6 | FIX | - |
| S48 | ? | 2/4/5/6/7 | GAP | - |
| S49 | ? | 1/2/5 | GAP | ADR-061 |
| S50 | 28.05.26 | 1/2/6 | FIX | GAP3 |
| S51 | 28.05.26 | 1/4/6 | FIX | GAP9 |
| S52 | 28.05.26 | 2/6 | FIX | GAP13 |
| S53 | 28.05.26 | 2/3/5 | FIX | GAP7 |
| S54 | 26.05.26 | 1/2/4/5/7 | FIX | ADR-084,GAP11 |
| S55 | 17.05.26 | 2/5 | FIX | ADR-088 |
| S56 | 27.05.26 | 7 | Эвол | - |
| S57 | 30.05.26 | 4/7 | Эвол | - |
| S58 | 30.05.26 | 1 | ADR | ADR-092 |
| S59 | 30.05.26 | 1/4/5/7 | FIX | ADR-102 |
| S60 | 31.05.26 | 2/4/5/7 | FIX | ADR-091 |
| S61 | 02.06.26 | 1/4/5/7 | ADR | ADR-114 |
| S62 | 03.06.26 | 3 | FIX | - |
| S63 | ? | 9 | ADR | ADR-116 |
| S64 | 03.06.26 | 2 | FIX | ADR-036 |
| S65 | 04.06.26 | 1/5/8 | Эвол | - |
| S66 | ? | 9 | ADR | ADR-123 |
| S67 | 2026-06-05 | 1/4/5 | FIX | ADR-123 |
| S68 | 05.06.26 | 1/2 | ADR | ADR-124 |
| S69 | 06.06.26 | 1/2 | FIX | - |
| S70 | 07.06.26 | 1/5 | FIX | ADR-SCENE-LOCK |
| S71 | 06.06.26 | 2 | Эвол | - |
| S72 | 08.06.26 | 4/5/7/8 | FIX | ADR-128 |
| S73 | 08.06.26 | 1/2/5 | FIX | ADR-130 |
| S74 | 08.06.26 | 2/5 | FIX | DRF Split-Brain, ДОЛГ 4.2 |
| S75 | 08.06.26 | 2/4/5/7/9 | FIX+ONTO | ADR-137, ADR-094, ADR-138 |
| S76 | 09.06.26 | 1/2/4/5/7/9 | FIX+ONTO | ADR-O-139, ADR-O-140, NPIC, MapEditor |
| S77 | 08.06.26 | 5/7 | FIX | ADR-140 |

**Легенда:** GAP=разрыв, FIX=закрыт, ADR=решение, Эвол=изменение

---

## 1. ДОМЕНЫ И ЭВОЛЮЦИЯ

### 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion)

**Истина:** `SpatialQueryService` — единственный авторитет. Движение — это *результат* давления и решения, а не команда. Фронтенд — интерполятор, а не телепортер.

- ⚪ **S04** [?] Централизация через `SpatialService` v1.2, убит хардкод локаций.
- ⚪ **S10** [?] Запрет `MovementIntent` для микроперемещений (требуется `LocalSteeringIntent`, позже
- ⚪ **S29** [?] Убийство телепортации. Внедрен Каузальный Lerp на фронтенде. `DIRECT_REFLEX` удален —
- ⚪ **S32** [?] LifeEngine Degodification. Лишен права мутации позиции и вызова MovementEngine напрям
- 🟢 **S33** [?] Нормализация префиксов макрозон (LOD0 fix).
- ⚪ **S35** [?] Safe Spatial Fallback. Отмена перемещения при отсутствии узла (убран фоллбэк на `entr
- 🔵 **S37** [?] Authoritative Spatial Spine (ADR048). `SpatialQueryService` инстанцирован. Чтение `sc
- ⚪ **S38** [?] DualTime Ontology на фронтенде. `_resolve_visual_xy` работает через `path_waypoints`
- 🔵 **S46** [?] Убита перезапись позиции игрока из протухшего `player_spatial`. `npc_orchestration.py
- 🟢 **S47** [?] Консолидация `SpatialService` в `TickOrchestrator`. Внедрен `_resolve_spatial_service
- 🔴 **S49** [?] Инвариант единого владения причинностью движения. `npc_orchestration.py` лишиён права
- 🟢 **S50** [28.05.26] GAP12 УБИТ. `_enrich_local_positions` вычисляет интерполированную позицию для NPC в а
- 🟢 **S51** [28.05.26] GAP9 УБИТ. Реалистичное Пробуждение. Сон блокируется непрерывными скалярами `threat_g
- 🟢 **S54** [26.05.26] Хардкод _MOVE_VERBS удален из npc_tick_pipeline.py. Semantic Bridge замкнут: IntentCo
- 🔵 **S58** [30.05.26] Фронтенд: Физика WASD (Pushout Resolution). Игрок больше не застревает между мебелью.
- 🟢 **S59** [30.05.26] ADR102: `load_graph()` мёртв — возвращает пустой граф (0 узлов). Заменён на `SpatialS
- 🔵 **S61** [02.06.26] ADR114: Spatial Paralysis убит. `graph_compiler.py` не создавал rolebased алиасов — l
- ⚪ **S65** [04.06.26] Инвариант 2 Запечатан: LLM не может галлюцинировать движение. (1) `VerbalizationConte
- 🟢 **S67** [2026-06-05] ADR121: Двухслойная топология в graph_compiler. `nodes` (dict) — навигационная тополо
- 🔵 **S68** [05.06.26] ADR125: Target ID SSOT Clarification. Обнаружена незавершённая миграция архитектуры р
- 🟢 **S76** [09.06.26] Новые чанки мира: city_gate.json, market_square.json. Формат World Partition (rooms=[], nodes навигация, is_outdoor=true, adjacency связи). Добавлена adjacency в tavern.json. **Корень БАГ U найден:** room_2 (x=2, y=2, w=16, h=10) поглощала room_0 и room_1 в tavern.json — граф навигации содержал узел-чёрную дыру.
- 🟢 **S69** [06.06.26] Ontology Merge Step 1: Relationship Cache Precedence Contract. Обнаружена бифуркация
- 🔴 **S70** [07.06.26] **КРИТИЧЕСКИЙ БАГ `unlock_tick` GUARD:** `unlock_tick()` вызывал `save_scene_state()` при `_tick_locked=True` → guard в `save_scene_state()` делал `return` без сохранения → **active_traversals НИКОГДА не записывались на диск**. Фикс: переставлена строка `self._tick_locked = False` ДО вызова `save_scene_state()`. Smoke test подтвердил round-trip: save→load→traversals идентичны. Runtime верифицирован: NPC реально двигаются через несколько тиков. Диагностика `[UNLOCK_TRACE]`, `[SAVE_TRACE]`, `[IDLE_TRACE]` оставлена как observability layer до прохождения стресс-теста.

### 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision)

**Истина:** Решения рождаются из искривленного давления (Utility Deformation). Воля — инерция, а не порог. Подчинение требует легитимности.

- 🔵 **S19** [?] WillpowerGate (ADR031). Cumulative Strain Model вместо бинарки. Шкала COMPLY → CONDIT
- ⚪ **S21** [?] Убийство объективных событий. Давление генерирует `PsychologicalPressure`, а не прямы
- 🔵 **S24** [?] Affective Resonance (ADR036). Аффект искажает давление через `ResponseBias`.
- ⚪ **S25** [?] Embodied Vector. Предрефлексивные моторные импульсы.
- ⚪ **S29** [?] Убийство телепортации. Внедрен Каузальный Lerp на фронтенде. `DIRECT_REFLEX` удален —
- 🔵 **S31** [?] DecisionContext (ADR050). Feasibility Layer (удаление невозможных действий) и Utility
- ⚪ **S35** [?] Safe Spatial Fallback. Отмена перемещения при отсутствии узла (убран фоллбэк на `entr
- 🔵 **S36** [?] Legitimacy Gate (ADR058). Нет страха/доверия = Irritation (агрессия) вместо Obedience
- 🔴 **S48** [?] Починка обрыва Трубы Воли на границе API. `routes.py` теперь пробрасывает `will_confl
- 🔴 **S49** [?] Инвариант единого владения причинностью движения. `npc_orchestration.py` лишиён права
- 🟢 **S50** [28.05.26] GAP12 УБИТ. `_enrich_local_positions` вычисляет интерполированную позицию для NPC в а
- 🟢 **S52** [28.05.26] GAP10 УБИТ. `EventContext` обогащён `target_id`. DecisionHub фильтрует бонус `APPROAC
- 🟢 **S53** [28.05.26] GAP2 УБИТ. Амнезия Воли вылечена. `compute_willpower` читает `trauma_markers`. Каждая
- 🟢 **S54** [26.05.26] Хардкод _MOVE_VERBS удален из npc_tick_pipeline.py. Semantic Bridge замкнут: IntentCo
- 🟢 **S55** [17.05.26] УБИТ Мертвый Вектор Эмоций (ADR088). `IntentCompressor._fast_path_parse` возвращал `E
- 🟢 **S60** [31.05.26] УБИТ `_semantic_action=None` (ADR091). `publish_classified_player_event` вызывался в
- 🟢 **S64** [03.06.26] УБИТ PHYSICS_OF_POWER NameError. `_context_relevance(self, intent, event)` не имел па
- 🔵 **S68** [05.06.26] ADR125: Target ID SSOT Clarification. Обнаружена незавершённая миграция архитектуры р
- 🟢 **S69** [06.06.26] Ontology Merge Step 1: Relationship Cache Precedence Contract. Обнаружена бифуркация
- ⚪ **S71** [06.06.26] §ENIGMAS72 Закон Релятивистского Восприятия. Система перешла от централизованной инте
- 🔴 **S74** [08.06.26] ДОЛГ 4.2: Causal Scoring Overlay. DRF претензии теперь влияют на приоритет интентов через аддитивный скоринг: `priority += energy × weight × alignment`. Веса: SURVIVAL=0.15, SOCIAL=0.10, ROUTINE=0.02. Убит сломанный clamp `max(priority, 90/70)` (масштабная ошибка при шкале 0.0–1.0). Overlay унифицирован для idle и player путей через `_apply_drf_scoring_overlay()`. Viability veto (SURVIVAL подавляет ROUTINE) ОСОЗНАННО НЕ реализован в MovementEngine — конфликт мотиваций должен решаться ДО генерации интента (ДОЛГ 4.3).
- 🔵 **S75** [08.06.26] Убит Вечный Двигатель Страха (ADR-138). `integrate_affective_pressure` переведён на Асимметричный Аттрактор (Гистерезис). Рост (0.30) быстрый, спад (0.05 + will*0.1) медленный. Убит AFFECTIVE_BOOT.
- 🔴 **S76** [09.06.26] ДОЛГ 5 ЗАКРЫТ: NPIC & Somatic Gating (ADR-O-139). Тело = gate of perception. Убит fallback {"social_stats": {"fear_of_player": 0.1}} в DirectiveInterpretationSubscriber — создавал "логических призраков". Shock > 0.7 теперь блокирует интерпретацию ДО семантического парсинга (Somatic Gate), а не после. Инвертирован каузальный порядок: Body → Somatic Gate → Semantic Parsing → Legitimacy → Action.
- 🔴 **S75** [08.06.26] ДОЛГ 4.3: Viability Pre-Generation Gate (ADR-O-137). Сдвиг парадигмы: от пост-генерационного скоринга к pre-генерационному сжатию пространства действий. Введён `IntentDomain` enum (SURVIVAL/SOCIAL/ROUTINE/EXPLORATION) — онтологический базис намерений. Добавлено поле `domain` в `MacroMovementGoal`. `_compute_viability_mask()` проекция PerceptualKernel → допустимые домены: threat > 0.3 → ROUTINE исключён, initiative_suppression > 0.7 → только SURVIVAL. Gate стоит ДО вызовов `update_routine()`, `_check_need_driven_movement()`, `check_random_events()` — генераторы НЕ вызываются для нежизнеспособных доменов. Устранена «зомби-каузальность». DRF claim использует `winner.domain.value`. 11 sandbox-тестов верифицируют mask, gate и типизацию.

### 3. ВОСПРИЯТИЕ И ФЕНОМЕНОЛОГИЯ (CFRM & Perception)

**Истина:** Объективных фактов нет. Есть возмущения поля (`FieldDisturbance`), которые проецируются в субъективные феномены в зависимости от наблюдателя.

- ⚪ **S21** [?] Убийство объективных событий. Давление генерирует `PsychologicalPressure`, а не прямы
- ⚪ **S26** [?] Epistemic Classification. Оценка уверенности (confidence) при классификации.
- ⚪ **S30** [?] CFRM Phase 2. `semantic_seed` (геном нарратива). Проекция теряет энергию/форму (физик
- ⚪ **S38** [?] DualTime Ontology на фронтенде. `_resolve_visual_xy` работает через `path_waypoints`
- 🟢 **S53** [28.05.26] GAP2 УБИТ. Амнезия Воли вылечена. `compute_willpower` читает `trauma_markers`. Каждая
- 🟢 **S62** [03.06.26] DOUBLE TRUTH `threat_gradient` УБИТ. `NPCState.write_to_legacy()` не писал `perceptua

### 4. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat)

**Истина:** Тело — материальный объект. Удар — чистая физика контакта, которая порождает боль и шок, а шок уже транслируется в эмоции.

- ⚪ **S16** [?] Каскад Shock → Emotion (ReactionSubscriber извлекает `shock_impulse`).
- ⚪ **S20** [?] Очистка `combat_stats`. Перенос способностей в `body_profile`.
- ⚪ **S30** [?] CFRM Phase 2. `semantic_seed` (геном нарратива). Проекция теряет энергию/форму (физик
- 🔴 **S48** [?] Починка обрыва Трубы Воли на границе API. `routes.py` теперь пробрасывает `will_confl
- 🟢 **S51** [28.05.26] GAP9 УБИТ. Реалистичное Пробуждение. Сон блокируется непрерывными скалярами `threat_g
- 🟢 **S54** [26.05.26] Хардкод _MOVE_VERBS удален из npc_tick_pipeline.py. Semantic Bridge замкнут: IntentCo
- ⚪ **S57** [30.05.26] RPG Витализм: нормализация шкалы `pain` (0100 → 01) в `StateInterpreter._physical_sta
- 🟢 **S59** [30.05.26] ADR102: `load_graph()` мёртв — возвращает пустой граф (0 узлов). Заменён на `SpatialS
- 🟢 **S60** [31.05.26] УБИТ `_semantic_action=None` (ADR091). `publish_classified_player_event` вызывался в
- 🔵 **S61** [02.06.26] ADR114: Spatial Paralysis убит. `graph_compiler.py` не создавал rolebased алиасов — l
- 🟢 **S67** [2026-06-05] ADR121: Двухслойная топология в graph_compiler. `nodes` (dict) — навигационная тополо
- 🔴 **S72** [08.06.26] ADR-128 P0: DECAY_INJURY_LOST — NPC injuries терялись после cache miss. Root cause: LifeEngine `_load_npcs()` не читал SQLite при cache miss — write path существовал (atomic_commit), но read path отсутствовал. После TTL/LRU eviction injuries, blood_loss, affective_load терялись навсегда. Фикс: трёхуровневая иерархия восстановления RAM → SQLite → static config. `is not None` семантика для None vs [] (пустая кампания ≠ отсутствующая).
- 🔴 **S72** [08.06.26] ADR-128 P0: Player injuries LOST — AvatarService `_state_to_dict()` не сериализовал `body_state`, `affective_load`, `perceptual_kernel`. Двойная онтология: wounds/conditions (legacy identity layer) ≠ body_state (simulation truth). Фикс: body_state = SSOT, wounds/conditions = legacy projection. Добавлена сериализация body_state + affective_load + perceptual_kernel в `_state_to_dict()` и `_state_from_dict()`.
- 🔴 **S73** [08.06.26] ADR-130 G1: Schedule Override Reactive Movement — `update_routine()` мутировал `routine["current"]="sleeping"` и создавал schedule intent (0.6) поверх активного reactive traversal (0.8). Root cause: update_routine не получал scene_state и не видел active_traversals. Фикс: scene_state передан через _simulate_major/minor → update_routine. Movement Lock guard: если NPC в статусе MOVING — schedule заблокирован. Traversal = commitment, schedule = suggestion.
- 🔴 **S73** [08.06.26] ADR-130 G2: Uninvited NPC Approach — `_context_relevance()` читал `event.target_id` (None) без fallback на `event.payload["target_id"]`. dm_scene_builder не пробрасывает target_id в EventContext, но dm_phase.py пишет его в payload. Без fallback ВСЕ NPC в зоне получали бонус APPROACH/TALK/OBSERVE. Фикс: _effective_tid с payload fallback.
- 🔴 **S74** [08.06.26] P1: Player Combat Snapshot EntityView Shift. `_make_player_snapshot()` в `combat_subscriber.py` больше не возвращает захардкоженного бессмертного игрока (hp=100, pain=0). Теперь принимает `player_dict` из `ctx.all_npcs_raw` и читает живой `body_state` (Rule 60). Убит легаси-принцип "Мастер Тай: игрок — источник давления, а не его жертва". Игрок стал симулируемой физической сущностью в бою.
- 🔴 **S75** [08.06.26] ADR-094 MSOC: CRITICAL BUG — `pressure_translator.py` читал `pain` (0-100) без нормализации при пороге 0.8. Результат: FLEE блокировался при pain > 0.8% — ЛЮБОЙ удар блокировал бегство. Фикс: `pain = body_state.get("pain", 0.0) / 100.0`. Теперь FLEE блокируется только при pain > 80/100 = тяжёлая травма.
- 🔴 **S75** [08.06.26] ADR-094 MSOC: `avatar_presentation_assembler.py` читал `pain`/`fatigue` (0-100) без нормализации при порогах 0-1. Результат: pain=60 → CRIPPLED вместо WOUNDED. Фикс: `/ 100.0` для обоих полей. DEAD override добавлен — при life_status=DEAD все проекции обнуляются, posture=collapsed, breathing=none. Убран `ASSEMBLER_TRACE` diagnostic print.
- 🔴 **S76** [09.06.26] NPIC Sentinel: Введена константа BODY_STATE_DISABLED в npc_state.py. Отсутствие тела = инертная материя (shock=1.0, pain=100), а не нейтральное состояние (§ENIGMA-003). Устраняет State Starvation Collapse при холодном старте.
- 🟢 **S75** [08.06.26] Контракт шкал физиологии зафиксирован (ADR-094 MSOC). `body_state` SSOT: `pain`/`fatigue` = 0-100, `blood_loss`/`shock_impulse` = 0-1. Потребители с порогами 0-1 обязаны нормализовать `/100.0`. Верифицированные нормализаторы: state_interpreter, pressure_derivation, tick_orchestrator, avatar_presentation_assembler, pressure_translator. Верифицированные 0-100 потребители: behavior_manifestation_service, vital_state.
- 🟢 **S76** [08.06.26] ADR-140: DM Death Scene Pipeline. DM получает life_status из player_state через avatar_to_prompt и генерирует death scene narration. Death Guard вызывает DM вместо хардкод-строки. DM НЕ вычисляет смерть — только читает замороженный факт S74-S75. 6 sandbox-тестов верифицируют: avatar_to_prompt проброс, death block инжект, negative test (ALIVE без death block), DM-no-compute (legacy pdata без life_status).
- 🟢 **S77** [08.06.26] ADR-141: Убит разрыв Injury → Pain. `InjuryProcessor` генерирует `pain_delta` из свойств раны (компенсирует Decay). Раненый NPC поддерживает хроническую боль, питающую `BehaviorManifestationService` → `EmbodiedTrace` → DM narration. Труба симптомов больше не высыхает после первого тика.

### 5. ТРУБА ОРКЕСТРАТОРА И ВРЕМЯ (Pipeline & Elastic Time)

**Истина:** Симуляция дискретна (каузальность), презентация непрерывна. `LifeEngine` — лоббист давления, а не бог-мутатор.

- ⚪ **S28** [?] Выжигание легаси. Удаление зомбиполей из `AvatarStateDTO`.
- ⚪ **S34** [?] DualTime Ontology. Запрет ретросимуляции. `LifeEngine.tick()` возвращает интенты, а н
- 🔵 **S36** [?] Legitimacy Gate (ADR058). Нет страха/доверия = Irritation (агрессия) вместо Obedience
- 🔴 **S48** [?] Починка обрыва Трубы Воли на границе API. `routes.py` теперь пробрасывает `will_confl
- 🔴 **S49** [?] Инвариант единого владения причинностью движения. `npc_orchestration.py` лишиён права
- 🟢 **S53** [28.05.26] GAP2 УБИТ. Амнезия Воли вылечена. `compute_willpower` читает `trauma_markers`. Каждая
- 🟢 **S54** [26.05.26] Хардкод _MOVE_VERBS удален из npc_tick_pipeline.py. Semantic Bridge замкнут: IntentCo
- 🟢 **S55** [17.05.26] УБИТ Мертвый Вектор Эмоций (ADR088). `IntentCompressor._fast_path_parse` возвращал `E
- 🟢 **S59** [30.05.26] ADR102: `load_graph()` мёртв — возвращает пустой граф (0 узлов). Заменён на `SpatialS
- 🟢 **S60** [31.05.26] УБИТ `_semantic_action=None` (ADR091). `publish_classified_player_event` вызывался в
- 🔵 **S61** [02.06.26] ADR114: Spatial Paralysis убит. `graph_compiler.py` не создавал rolebased алиасов — l
- ⚪ **S65** [04.06.26] Инвариант 2 Запечатан: LLM не может галлюцинировать движение. (1) `VerbalizationConte
- 🟢 **S67** [2026-06-05] ADR121: Двухслойная топология в graph_compiler. `nodes` (dict) — навигационная тополо
- 🔵 **S70** [07.06.26] LLM Infrastructure Resilience. (1) `server_cmd` в `main.py` не имел флагов GPU (`-ngl`, `-c`, `-t`) → модель 5.4 ГБ грузилась на CPU → таймаут 60с → сервер считался "не поднявшимся" → NPC немые. Фикс: добавлены `str(settings.gpu_layers)`, `str(settings.ctx_size)`, `str(settings.threads)`. (2) `stderr=subprocess.PIPE` скрывал причину падения процесса. Фикс: stderr пишется в `logs/llama_server_stderr.log`. Добавлена проверка `proc.poll()` после spawn — мгновенный краш виден в логе. (3) При таймауте `_llama_server_proc = None` без kill → сиротский процесс жрал RAM/CPU. Фикс: terminate+kill при таймауте. (4) `_restart_llama_server()` — при потере LLM во время игры пробует перезапустить и повторить запрос. REST endpoint `/api/debug/llm/restart` для ручного рестарта. (5) game_loop/__init__.py: при LLM error вызывается `_restart_llama_server()` с одним retry. (6) idle_tick НЕ создаёт traversals — это НЕ баг, а архитектурное разделение: idle обновляет мир, traversals создаются только при action/reaction.
- 🔴 **S72** [08.06.26] ADR-128: LifeEngine cache recovery замкнут. (1) `set_persistence()` — инъекция PersistencePort в LifeEngine (паттерн `set_spatial_service()`). (2) `_load_npcs()` — при cache miss сначала читает SQLite (`persistence.load_npc_runtime()`), затем fallback на static config. (3) `get_npc_states()` — при cache miss вызывает `_load_npcs()` вместо возврата `[]`. (4) Wiring: `game_loop_builder.py` инжектит `SqlitePersistenceAdapter` в singleton.
- 🟢 **S73** [08.06.26] ADR-130: Movement Lock + Target Resolution. (1) `update_routine()` получил `scene_state` param — проверяет `active_traversals[npc_id].status=="MOVING"` перед мутацией. (2) `_simulate_major()` и `_simulate_minor()` пробрасывают `scene_state`. (3) `_context_relevance()` проверяет `payload["target_id"]` как fallback при `event.target_id is None`. Два корневых разрыва G1/G2 закрыты.
- 🔴 **S74** [08.06.26] P0: Action Eligibility Gate (Death Guard). В `game_loop/__init__.py` добавлен инвариантный слой: проверка `_avatar_state.body_state["life_status"]` ДО `lock_for_tick`. Мёртвый игрок получает ранний `ChatTurnResponse` (Game Over) и отсекается от каузального загрязнения `scene_state` (Rule 59).
- 🔴 **S74** [08.06.26] P0: DRF Split-Brain Fix. `execute()` и `execute_player_finalize()` создавали независимые `_TickContext` с отдельными `DRFBus()` (default_factory). Claims писались в BUS_A, drain читал из BUS_B → `[DRF_FIELD] claim_field is EMPTY`. Фикс: DRFBus перенесён на уровень экземпляра оркестратора (`self._drf_bus = DRFBus()` в `__init__`). Оба метода передают `drf_bus=self._drf_bus`. Добавлен `_drf_bus.stream.clear()` на начало `execute()`. Idle `_phase_10_persistence` получил drain (ранее отсутствовал). Верифицировано через `id()` диагностику: один bus_id на весь lifecycle.
- 🔵 **S74** [08.06.26] DRFExecutionContext: Scoped Causal Ledger. Pipeline получает `drf_ctx: DRFExecutionContext` (tick_id + npc_id + bus), а не голый `drf_bus`. Claim автоматически наследует npc_id и tick_id через `drf_ctx.emit()`. Убран monkey-patch `run_npc_pipeline.drf_bus = ctx.drf_bus`. Внутри NPC loop создаётся scoped контекст: `_npc_drf_ctx = drf_ctx.for_npc(npc_id)`.
- 🔴 **S76** [09.06.26] Normalization Gate: `tick_orchestrator.py` инжектит `BODY_STATE_DISABLED` для NPC без `body_state` в `ctx.all_npcs_raw` перед использованием. Full Veto в `pressure_translator.py` при отсутствии тела: нет тела = нет действий (`constraints[action] = 0.0`), а не нулевое влияние.
- 🔵 **S75** [08.06.26] ADR-137: Death Guard v2 — world continues after player death. `game_loop/__init__.py` включает `npc_positions` из `LifeEngine` cache в death snapshot. Онтология: смерть = потеря агентности, не конец симуляции. Мёртвый игрок видит death overlay, но NPC продолжают двигаться.
- 🔵 **S75** [08.06.26] PK Idle Decay & Cache Sync. `PerceptualKernel` (threat, uncertainty, anomaly) затухает в Фазе 0.5 (Rule 38). `LifeEngine.update_cache()` вызывается после idle-дельт. Убран скрытый источник реконструкции страха.

### 6. ПАМЯТЬ И СОЦИУМ (Memory & Social Physics)

**Истина:** Память многослойна. Социальные акты (приказы) искривляют utility-space цели, а не генерируют `MovementIntent` напрямую.

- ⚪ **S03** [?] Мультисобытийность Perception.
- ⚪ **S08** [?] Обогащение NPC социальными связями из `village_relations.json`.
- ⚪ **S27** [?] Физика Власти. `DirectiveInterpretationSubscriber` транслирует приказы в `directive_o
- ⚪ **S32** [?] LifeEngine Degodification. Лишен права мутации позиции и вызова MovementEngine напрям
- 🟢 **S47** [?] Консолидация `SpatialService` в `TickOrchestrator`. Внедрен `_resolve_spatial_service
- 🔴 **S48** [?] Починка обрыва Трубы Воли на границе API. `routes.py` теперь пробрасывает `will_confl
- 🟢 **S50** [28.05.26] GAP12 УБИТ. `_enrich_local_positions` вычисляет интерполированную позицию для NPC в а
- 🟢 **S51** [28.05.26] GAP9 УБИТ. Реалистичное Пробуждение. Сон блокируется непрерывными скалярами `threat_g
- 🟢 **S52** [28.05.26] GAP10 УБИТ. `EventContext` обогащён `target_id`. DecisionHub фильтрует бонус `APPROAC

### 7. ФРОНТЕНД И ПРЕЗЕНТАЦИЯ (UI & Embodiment)

**Истина:** Фронтенд — это сенсорный орган игрока. Он искажается, болеет и сопротивляется, не зная внутренних метрик бэкенда.

- ⚪ **S10** [?] Запрет `MovementIntent` для микроперемещений (требуется `LocalSteeringIntent`, позже
- ⚪ **S18** [?] Создание Персонажа через Вектор Начальных Условий (Архетип + Темперамент).
- ⚪ **S25** [?] Embodied Vector. Предрефлексивные моторные импульсы.
- ⚪ **S26** [?] Epistemic Classification. Оценка уверенности (confidence) при классификации.
- ⚪ **S28** [?] Выжигание легаси. Удаление зомбиполей из `AvatarStateDTO`.
- ⚪ **S39** [?] Интеграция CDS. Фронтенд не парсит отчёты симуляции.
- 🔴 **S48** [?] Починка обрыва Трубы Воли на границе API. `routes.py` теперь пробрасывает `will_confl
- 🟢 **S54** [26.05.26] Хардкод _MOVE_VERBS удален из npc_tick_pipeline.py. Semantic Bridge замкнут: IntentCo
- ⚪ **S56** [27.05.26] The Fool v2 — визуализация моторных следов (дрожь/замер) и тултипов наблюдений замкну
- ⚪ **S57** [30.05.26] RPG Витализм: нормализация шкалы `pain` (0100 → 01) в `StateInterpreter._physical_sta
- 🟢 **S59** [30.05.26] ADR102: `load_graph()` мёртв — возвращает пустой граф (0 узлов). Заменён на `SpatialS
- 🟢 **S60** [31.05.26] УБИТ `_semantic_action=None` (ADR091). `publish_classified_player_event` вызывался в
- 🔵 **S61** [02.06.26] ADR114: Spatial Paralysis убит. `graph_compiler.py` не создавал rolebased алиасов — l
- 🔴 **S72** [08.06.26] ADR-128: PlayerAvatarService сериализует body_state. `_state_to_dict()` добавлены `body_state`, `affective_load`, `perceptual_kernel`. `_state_from_dict()` восстанавливает через `dict(data.get("body_state", {}))`, `float(data.get("affective_load", 0.0))`, `_pk_from_dict(data.get("perceptual_kernel", {}))`. Импорт `_pk_from_dict` из `npc_state.py`. Player injuries теперь переживают save/load.
- 🟢 **S76** [09.06.26] Map Editor: Shift+ЛКМ перетаскивание локаций (смещение `origin`). Удаление локаций из кампании. Outdoor поддержка (объекты, NPC, надписи разрешены вне комнат при `is_outdoor=true`). Очистка меню (убраны дубли "Сохранить всё", "Открыть кампанию" заменено на проводник).
- 🔴 **S75** [08.06.26] ADR-137: Death Feedback Pipeline замкнут. `AvatarStateDTO.life_status` поле добавлено. `PhysicalPresentationState.DEAD` enum. Frontend `GameScreen` рендерит death overlay ("ВЫ МЕРТВЫ") при `life_status=DEAD`. `AvatarPresentationAssembler` DEAD override обнуляет все проекции (stability=0.0, coherence=0.0, noise=1.0, posture=collapsed, breathing=none).
- 🟢 **S76** [08.06.26] ADR-140: avatar_to_prompt пробрасывает life_status в pdata. DM death scene block инжектится через DMContractBuilder.add_custom_block. Death Guard вызывает DM через run_agent_safe вместо хардкод-строки (с fallback при Exception).

### 8. НАБЛЮДАЕМОСТЬ И ДИАГНОСТИКА (CDS)

**Истина:** Наблюдение не создает причинность. CDS — пассивный аудиторе.

- ⚪ **S39** [?] Интеграция CDS. Фронтенд не парсит отчёты симуляции.
- ⚪ **S65** [04.06.26] Инвариант 2 Запечатан: LLM не может галлюцинировать движение. (1) `VerbalizationConte
- 🟢 **S72** [08.06.26] P3: Уборка диагностического шума после расследования ADR-128. Удалены: `[DIAG_FROM_LEGACY]`, `[LEGACY_READ]`, `[RAW_BEFORE_FL]`, `[VITAL_PRE]`, `[PRE_WTL]`, `[POST_WTL]`. Понижены до DEBUG: `[INJURY_APPLIED]`, `[CONSCIOUSNESS_DROP]`, `[APPLY_OK]`, `[LEGACY_READ_LOST]`. Файлы: `npc_state.py`, `state_applicator.py`.
- 🟢 **S74** [08.06.26] Sandbox Tests: Написаны 7 тестов для ADR-128 (persistence) и ADR-130 (movement). Строго по §12.3 Устава: объекты создаются через фабрики/реальные словари, а не прямые конструкторы. Тесты: `test_player_body_state_survives_save_load` (Rule 54/55), `test_wounds_not_used_as_physiology_source` (Rule 56), `test_movement_lock_blocks_schedule_on_active_traversal` (Rule 57), `test_target_id_payload_fallback_prevents_uninvited_approach` (Rule 58).

### 9. SOCIAL & AFFECTIVE ARCHITECTURE (SSOT & CAUSAL DERIVATION)

**Истина:** Отношения — это граф (ребро), а не свойство узла. Аффективная нагрузка — интеграл с гистерезисом, релаксирующий к цели, а не магическая батарейка или мгновенная проекция.

- 🔵 **S63** [?] (1) `load_l2_state_from_runtime_dict()` (npc_loader.py) — добавлены 5 полей в констру
- 🔵 **S66** [?] (1) `RelationshipStore` назначен Единственным Источником Истины (SSOT) для всех социа
- 🔵 **S76** [09.06.26] ADR-O-140 спроектирован: World Partition Topology. Локация = чанк сериализации, не мир сама по себе. Мир непрерывен. `location_id` = инфраструктура загрузки, не онтология NPC. `adjacency` — связи между чанками для сшивки навигационных графов. `door_transition` остаётся только для магических порталов/лестниц.
- 🔵 **S75** [08.06.26] Убит Вечный Двигатель Страха (ADR-138). `integrate_affective_pressure` переведён на Асимметричный Аттрактор (Гистерезис). Рост (0.30) быстрый, спад (0.05 + will*0.1) медленный. Убит AFFECTIVE_BOOT.

## 2. АРХИТЕКТУРНЫЕ ЗАПРЕТЫ

- [Пространство] LLM описывает движение NPC без подтверждения от MovementEngine (Инвариант 2: Нарратив ≠ Физика).
- [UI] DM контракт без блока о перемещениях NPC — LLM галлюцинирует локомоцию.
- [Воля] Мгновенное сжигание `recent_directive` в LifeEngine (GAP9).
- [Пространство] Прямая мутация `npc["position"]` или `npc["location"]`.
- [Пространство] Чтение дистанций из `scene_state` (только через `SpatialQueryService`).
- [Прочее] Вызов `scene_manager.apply_changes()` из подписчиков (`SceneChange` — проекция для фронтенда).
- [Пространство] Использование `TraversalState` без `MovementEngine`.
- [Воля] Вызов `process_intents()` или `apply_changes()` из `npc_orchestration.py` (единственный владелец — `TickOrchestrator`).
- [Пространство] Повторная обработка `MovementIntent` (инвариант `processed=True`).
- [Pipeline] Хардкод языковых глаголов в `npc_tick_pipeline.py` (после починки Semantic Bridge).
- [Пространство] `SpatialQueryService.visibility()` вызывает `is_line_of_sight_clear` с неправильным порядком аргументов — scene_state получает float, крашит `.get()` (ADR-129).
- [Пространство] CEI-2 использует `is_movement_blocked` вместо `is_blocked_by_wall` — мебель (walk=False) блокирует макро-навигацию между комнатами. Мебель = LOD0, не стена (ADR-129).
- [Пространство] spatial_runtime consumer-функции без `normalize_scene_state()` — type corruption (list/float/None) крашит pipeline (ADR-129).
- [Пространство] `_enrich_local_positions` перетирает `local_position`, установленный пайплайном (LOD0 guard).
- [Пространство] Использование `load_graph()` — мёртвый код, возвращает пустой граф. Заменён на `SpatialService.build_for_location()` (ADR-102).
- [Пространство] Сравнение legacy ID (`room_1`) с canonical ID (`tavern:room_1`) без нормализации через `spatial_service.normalize_id()`.
- [Пространство] `graph_compiler.py` без role-based aliases — legacy-имена не резолвятся → Spatial Paralysis (ADR-114).
- [Воля] Обращение к `intent.action` в `will.py`/`affect.py` без fallback на `parameters.semantic_action` (ADR-035).
- [Восприятие] Фиксированные множители в CFRM (threat×40, anomaly×20) — движок не интерпретирует (§ENIGMA-S72).
- [Эмоции] Хардкод весов affective_load (0.6/0.3/0.1) — веса из drives_base (§ENIGMA-S72).
- [Прочее] Хардкод семантических весов в DecisionHub (+0.5/+0.7/+0.2) — модуляция через drives_base (§ENIGMA-S72).
- [Восприятие] Конвертация uncertainty_delta → stress_delta в LegacyStateDeltaAdapter — нарушение §ENIGMA-004.
- [Эмоции] Назначение dominant_emotion_hint из движка — эмоция только через Affective Pipeline (§ENIGMA-S72).
- [Эмоции] Универсальная конвертация эмоция→действие (fear→flee для всех) — drives_base определяет направление разрядки (§ENIGMA-S72).
- [Воля] Вызов WillpowerGate более 1 раза за цикл.
- [Физиология] Генерация эмоций напрямую из CombatSubscriber (только PhysiologyPayload).
- [Прочее] Передача сырых дельт давления из текущего тика в DecisionHub (только консолидированное восприятие T-1).
- [Воля] Пустой `topic` в `CommunicationIntent`.
- [Прочее] Хранение `EventDTO` в `EventBuffer` (только `FieldDisturbance`).
- [Прочее] Обход `LocalCausalSolver` при генерации давления.
- [Прочее] Мутация состояния из CausalObserver (только пассивная фиксация).
- [Восприятие] `write_to_legacy` / `from_legacy` без сериализации `perceptual_kernel` и `affective_load` — восприятие и аффект теряются между тиками (DOUBLE TRUTH).
- [Прочее] Использование полей дельт в `state_applicator` без извлечения из payload (все физиологические поля требуют явного extraction).
- [Физиология] Прямая мутация HP аватара в обход `ImpactEngine`.
- [Физиология] Использование `hp_ratio` в `state_interpreter` без учета `pain/shock/blood_loss` (GAP5).
- [Физиология] Масштабная несовместимость: `StateApplicator` пишет `pain` в 0-100, а интерпретаторы читают в 0-1 (нормализация `/100` обязательна при чтении из `body_state`).
- [Физиология] `CombatSubscriber` пишет в Emotion (Domain Leakage). Только `PhysiologyPayload`.
- [Физиология] `BehaviorManifestationService` читает эмоции (psyche.fear/stress) вместо физиологии (body_state.pain/blood_loss/shock_impulse) — Правило X (CAUSAL_CONTRACT §7).
- [Физиология] `write_to_legacy` / `from_legacy` без сериализации `body_state` — физиология теряется между тиками.
- [Физиология] `shock_impulse` без decay в `PhysiologyDecayHandler` — шок становится перманентным (ADR-105).
- [Физиология] `StateApplicator` проверяет `shock_impulse > 0.0` вместо `!= 0.0` — блокирует отрицательные дельты decay (ADR-105).
- [Восприятие] `BehaviorManifestationService`/`PhenomenologyProjectionService` читают `stress_delta`/`psyche_state` для моторных искажений и атмосферы — Semantic Inflation (ADR-112, Rule 28).
- [Pipeline] Создание `_TickContext` без `player_result` при ходе игрока (инвариант: player turn всегда имеет результат).
- [Pipeline] Ретро-симуляция (цикл `LifeEngine.tick()` для нагона).
- [Pipeline] Мутация состояния в обход `DeltaBuffer → apply_batch()`.
- [Прочее] Чтение `scene_state` оркестратором для бизнес-логики (только для проекции).
- [Восприятие] `_apply_runtime_overlay` без белых списков для `affective_load`, `emotion`, `body_state`, `perceptual_kernel` — вычисленное состояние затирается статикой (Инвариант 1).
- [Персистенция] `_load_npcs_with_runtime` без прайминга LifeEngine cache после чтения с диска — каждый player turn перечитывает YAML.
- [UI] Фейковый нарратив при краше LLM ("Твоё сознание мутнеет...") — каузальное мошенничество. Только честное системное сообщение (ADR-113, Rule 29).
- [UI] `agent_runner.py` возвращает `None` при LLM timeout/exception — вызывающий код крашится на `.get()` (ADR-113).
- [Память] Публикация в память в обход `MemoryManager`.
- [Воля] Хардкод `fear_of_player` в `DirectiveInterpretationSubscriber` для NPC-источников (GAP13).
- [Пространство] `DirectiveInterpretationSubscriber` генерирует `MovementIntent`.
- [Воля] Вызов `DirectiveInterpretationSubscriber` без инъекции `all_npcs_raw` (иначе ObediencePressure=0.00).
- [Воля] Возврат `UNCERTAIN` из `IntentCompressor` на известные приставочные глаголы ATTACK/THREATEN (словарь должен покрывать pymorphy3 леммы).
- [Прочее] Применение моторных смещений (дрожь) к экранным координатам ПОСЛЕ отрисовки спрайта. Смещение применяется ТОЛЬКО ДО `self.screen.blit()`.
- [Пространство] Перезапись `result.world_snapshot` целиком в `game_loop_bridge.py` (уничтожает `player_perception`). Только точечное обновление `result.world_snapshot["npc_positions"]`.
- [Прочее] Импорт `backend/app/` во фронтенд (Устав §1.1).
- [Физиология] Передача Игроку внутренних метрик NPC (HP, fear, trust). Только наблюдаемые симптомы ("дрожит", "кровоточит").
- [Восприятие] DM-агент читает внутренние состояния NPC (pain, fear, shock) напрямую вместо наблюдаемых симптомов (`embodied_traces`). Kernel Leakage = архитектурный баг.
- [Прочее] Обработка клавиши `Ё` только через `pygame.K_BACKQUOTE` без проверки `event.unicode` (русская раскладка Windows не генерирует BACKQUOTE).
- [Сериализация] Использование `asdict()` на границе API без Pydantic/Dataclass валидации.
- [Прочее] Обратная связь из CDS в рантайм симуляции.
- [Прочее] Прерывание каузального потока при падении CDS.
- [Прочее] `logger.debug` для крахов аффективного decay — отказы должны быть уровня WARNING (Инвариант 3).
- [Pipeline] `print()` для Phase 8 крахов — должен быть структурированный `[PIPELINE][CRITICAL]` или `[PHASE8_CRASH]` (Инвариант 3).
- [Pipeline] CDS не парсит пред-шинные отказы — pipeline умирает молча (Инвариант 3).
- [Прочее] Персистенция `relationship_cache` внутри `NPCState` (DOUBLE TRUTH). Только `RelationshipStore` пишет на диск.
- [Эмоции] Использование плоского формата `{"fear": 0.5}` в `relationship_cache`. Только вложенный: `{"player": {"fear": 50.0}}`.
- [Эмоции] Использование интегратора с утечкой (`load + incoming - recovery`) для `affective_load` — аттрактор насыщения, вечный страх (ADR-138). Только асимметричный аттрактор (гистерезис).
- [Восприятие] Отсутствие idle-decay для `PerceptualKernel` (threat, uncertainty, anomaly) — вечный реконструктор страха (Rule 38, ADR-138).
- [Эмоции] AFFECTIVE_BOOT / подтягивание `affective_load` до порога `emotion_tag` — положительная обратная связь (ADR-138).
- [Восприятие] Хранение `threat_gradient` навсегда без decay или recompute. (Текущий decay — временная мера, пока не реализован Gen 3: `perceive_world()`).
- [Восприятие] Создание `NPCState` через прямой конструктор `NPCState(...)` без передачи `emotion`, `affective_load`, `body_state`, `perceptual_kernel`. Только через `from_legacy()` или `load_l2_state_from_runtime_dict()` с полным набором полей (ADR-116).
- [Pipeline] `unlock_tick()` снимает `_tick_locked` ПОСЛЕ `save_scene_state()` — guard блокирует финальный персист, traversals теряются (ADR-SCENE-LOCK).
- [Pipeline] Запуск llama-server без флагов GPU (`-ngl`, `-c`, `-t`) — модель грузится на CPU, таймаут, NPC немые.
- [Pipeline] `stderr=subprocess.PIPE` при запуске llama-server — silent death без диагностики.
- [Pipeline] `_llama_server_proc = None` без terminate/kill — сиротский процесс жрёт RAM.
- [Pipeline] Отсутствие recovery при падении LLM — игра остаётся немой навсегда.
- [Персистенция] LifeEngine `_load_npcs()` без SQLite read-back — runtime state теряется после cache eviction (ADR-128).
- [Персистенция] `load_npc_runtime()` возвращает `[]` — нельзя отличить пустую кампанию от отсутствующей. Только `is not None` проверка (ADR-128).
- [Персистенция] AvatarService `_state_to_dict()` без `body_state` — player injuries теряются при каждой загрузке (ADR-128).
- [Персистенция] AvatarService `_state_from_dict()` без `body_state`/`affective_load`/`perceptual_kernel` — аватар сбрасывается в NEUTRAL/0.0 при каждой загрузке (ADR-128).
- [Физиология] Двойная онтология: wounds/conditions (legacy) ≠ body_state (runtime). body_state = SSOT, wounds = legacy projection (ADR-128).
- [Pipeline] update_routine() без scene_state — не видит active_traversals, перезаписывает reactive traversal schedule intent (ADR-130).
- [Воля] _context_relevance() без payload["target_id"] fallback — все NPC считаются целевыми при player_interacts (ADR-130).
- [Pipeline] Обработка player action без проверки `life_status` — мёртвый игрок не может действовать (Rule 59, ADR-127).
- [Физиология] `_make_player_snapshot()` без чтения `avatar_state.body_state` — статический снапшот = бессмертный в бою (Rule 60, ADR-128).
- [Pipeline] Создание DRFBus через `default_factory=DRFBus` в `_TickContext` — split-brain при двух контекстах (ADR-131). Только instance-level bus оркестратора.
- [Pipeline] Monkey-patch функции для инъекции шины (`func.drf_bus = ...`) — нарушает причинную прозрачность (ADR-131).
- [Pipeline] DRF overlay только в idle path — player path обходит арбитраж (ДОЛГ 4.2 fix: unified overlay).
- [Воля] Viability veto через `_drf_killed` флаг или `priority=0` в MovementEngine — скрытый скоринг вместо viability (ДОЛГ 4.3).
- [Воля] Viability veto через парсинг строк (`"schedule" in reason`) — ломается при смене имён (ДОЛГ 4.3: только через IntentDomain, ADR-O-137).
- [Воля] Viability через пост-генерационную фильтрацию кандидатов вместо pre-generation gate — ROUTINE уже мутирует `routine["current"]` и создаёт SceneChange до фильтрации (ADR-O-137).
- [Воля] `MovementIntent` без поля `domain` — viability mask не может работать, онтологическая неполнота (ADR-O-137).
- [Воля] Clamp override `max(priority, 90)` при шкале 0.0–1.0 — уничтожение шкалы (ДОЛГ 4.2 fix: аддитивный скоринг).
- [Физиология] Чтение `pain`/`fatigue` без нормализации `/100.0` в потребителях с порогами 0-1 — MSOC (ADR-094, Rule 63/64).
- [UI] `AvatarStateDTO` без поля `life_status` — фронтенд слеп к смерти (ADR-137, Rule 81).
- [Pipeline] Death Guard без `npc_positions` в `world_snapshot` — мир замерзает при смерти игрока (ADR-137, Rule 82).
- [Физиология] Контракт шкал: body_state pain/fatigue = 0-100, blood_loss/shock = 0-1. Потребители с порогами 0-1 обязаны нормализовать (ADR-094 MSOC, Rule 83).
- [Нарратив] DM narration без проверки player life_status — каузальный обман (ADR-140).
- [Нарратив] avatar_to_prompt без life_status — DM слеп к смерти (ADR-140).
- [Нарратив] Death Guard без вызова DM — подмена нарратива хардкодом (ADR-140).

---

## 3. ОТКРЫТЫЕ РАЗРЫВЫ

- **S49:** ВЕРИФИЦИРОВАН РАЗРЫВ: LifeEngine перезаписывает реактивные транзиты (`reactive:approach`) schedule-интентами (`schedule:sleeping`) каждый idle tick. NPC не доходит до игрока — его постоянно редиректят в кровать. Требует механизм пробуждения (отложено).
- **S49:** ВЕРИФИЦИРОВАН РАЗРЫВ: Незваные NPC (`blacksmith_orm`, `merchant_goran`) получают `approach` от DecisionHub при команде, адресованной другому NPC. Требует фильтр целевого NPC (отложено).
- **S49:** ВЕРИФИЦИРОВАН РАЗРЫВ: Хардкод русских глаголов в `npc_tick_pipeline.py` — нарушает локализуемость и разделение ответственности. `IntentCompressor` уже умеет классифицировать `MOVE` через pymorphy3, но Semantic Bridge (`S28_GATE`) возвращает `UNCERTAIN` — результат теряется на пути от `phase_1_input` до `hub_event`. После починки Bridge хардкод должен быть удалён.
- **S49:** ВЕРИФИЦИРОВАН РАЗРЫВ: `game_loop_bridge.py` не пробрасывал `active_traversals` в `world_snapshot` → фронтенд не мог интерполировать движение. Исправлено: bridge копирует `active_traversals` из `scene_state`.

---

## 4. МЕТА

| Показатель | Значение |
|------------|----------|
| Сессий | 57 |
| Запретов | 108 |
| Доменов | 9 |
| Открытых разрывов | 3 |
| Диапазон | S03—S77 |
# MUTATIONS.md — Доменно-Каузальная Эволюция ENIGMA

> **Формат:** Домен → Текущий контракт → Эволюция (ключевые сессии) → Архитектурные запреты.
> ИИ-ассистенту: читай только нужный домен для получения полного контекста.

---

## 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion)
**Текущая истина:** `SpatialQueryService` — единственный авторитет. Движение — это *результат* давления и решения, а не команда. Фронтенд — интерполятор, а не телепортер.

**Эволюция:**
- **S04:** Централизация через `SpatialService` v1.2, убит хардкод локаций.
- **S10:** Запрет `MovementIntent` для микро-перемещений (требуется `LocalSteeringIntent`, позже отклонен в пользу LOD0 в `MovementIntent`).
- **S29:** Убийство телепортации. Внедрен Каузальный Lerp на фронтенде. `DIRECT_REFLEX` удален — приказ идет через EventBus.
- **S32:** LifeEngine De-godification. Лишен права мутации позиции и вызова MovementEngine напрямую.
- **S33:** Нормализация префиксов макро-зон (LOD0 fix).
- **S35:** Safe Spatial Fallback. Отмена перемещения при отсутствии узла (убран фоллбэк на `entrance`). Collision Avoidance LOD0.
- **S37:** Authoritative Spatial Spine (ADR-048). `SpatialQueryService` инстанцирован. Чтение `scene_state["player_distances"]` запрещено.
- **S38:** Dual-Time Ontology на фронтенде. `_resolve_visual_xy` работает через `path_waypoints` + `progress`. Локальный pathfinding удален.
- **S46:** Убита перезапись позиции игрока из протухшего `player_spatial`. `npc_orchestration.py` читал `player_spatial.local_position` (запись запрещена ADR-048 Phase 3 — всегда протухший spawn) и перезаписывал `npc_positions.player.local_position`, убивая актуальные координаты от фронтенда. Фикс: читать из `npc_positions.player` напрямую, только резолвить ближайший узел. Также починен лог `PHASE_5_PLAYER nearby_npcs=?` — читалось с `_TickContext` (нет атрибута), исправлено на `dm.nearby_npcs`.
- **S47:** Консолидация `SpatialService` в `TickOrchestrator`. Внедрен `_resolve_spatial_service()`, убивший трехкратную ручную сборку `build_for_location()`.
- **S47:** ОТМЕНЕНО: Попытка динамической синхронизации `npc_positions.player` из `player_spatial` и внедрение точных координат цели (`target_locaыl_xy`) откатана. Изменения ломали рантайм-конвейер движения и вызывали массовую телепортацию NPC. Проблема пространственного резолва игрока требует иного подхода.
- **S49:** Инвариант единого владения причинностью движения. `npc_orchestration.py` лишиён права вызывать `process_intents()` и `apply_changes()` — единственный владелец `TickOrchestrator`. В доменную модель (`MacroMovementGoal`, `LocalSteeringGoal`) добавлены поля `processed` и `processor` — повторная обработка интента вызывает `RuntimeError`.
- **S49:** Проброс `target_local_xy` в `MacroMovementGoal` при `reactive:approach`. Ранее координаты цели (позиция игрока) вычислялись в `_resolve_reactive_movement`, но терялись при создании `MacroMovementGoal` → NPC шли к центру узла вместо точной позиции игрока.
- **S49:** Рефлекс теперь перекрывает ЛЮБОЕ решение DecisionHub, включая `flee`. Убран guard `if decision.intent.value not in ("approach", "flee")` — приказ игрока = авторитетный источник причинности (ADR-061).
- **S49:** Частичное совпадение имени NPC. "торнин" теперь совпадает с "торнин серебряная луна" — рефлекс проверяет отдельные слова имени (≥3 символа), а не только полное имя. Без этого NPC с длинными именами были глухи к приказам.
- **S49:** Ghost Position Fix. При создании нового транзита, если NPC уже в активном транзите, `from_xy` вычисляется интерполяцией текущего прогресса, а не берётся из устаревшего `local_position`.
- **S49:** Bridge пробрасывает `active_traversals` в `world_snapshot`. Без этого фронтенд не мог интерполировать движение — NPC либо телепортировались, либо стояли на месте.
- **S49:** `_enrich_local_positions` больше не перетирает `local_position` для сдвинувшихся NPC. Добавлен LOD0 guard: если позиция уже валидна (установлена пайплайном), enrichment пропускает.
- **S49:** ВЕРИФИЦИРОВАН РАЗРЫВ: LifeEngine перезаписывает реактивные транзиты (`reactive:approach`) schedule-интентами (`schedule:sleeping`) каждый idle tick. NPC не доходит до игрока — его постоянно редиректят в кровать. Требует механизм пробуждения (отложено).
- **S51:** GAP5 УБИТ. `state_interpreter.py` читает `pain`, `shock_impulse` и `blood_loss` из `body_state`. Боль и шок перекрывают HP. Агония = "тяжело ранен", нокаут = "без сознания". Каузальный мост Физиология → Речь замкнут.
- **S51:** GAP4 УБИТ. `DirectiveInterpretationSubscriber` ингибируется шоком. `shock > 0.7` → `return []`. Бессознательное тело не подчиняется приказам.
- **S51:** GAP9 УБИТ. Реалистичное Пробуждение. Сон блокируется непрерывными скалярами `threat_gradient > 0.3` и `stress > 50`. `recent_directive` больше не сжигается мгновенно, предотвращая повторное укладывание в кровать на следующем тике.
- **S52:** GAP10 УБИТ. `EventContext` обогащён `target_id`. DecisionHub фильтрует бонус `APPROACH` — только целевой NPC получает реакцию на `player_interacts`. Свидетели больше не подходят.
- **S52:** GAP13 УБИТ. `DirectiveInterpretationSubscriber` больше не хардкодит `fear_of_player`. Если источник приказа — NPC, легитимность вычисляется из `relationship_cache.fear_{source_id}`. Дорога к NPC-to-NPC иерархии открыта.
- **S53:** GAP1 УБИТ. Темпоральная асимметрия устранена. Когнитивный Оверлей теперь инжектит критический шок (`shock_impulse > 0.5`) мгновенно (T+0) вместе с директивами. Топор летит со скоростью слова.
- **S53:** GAP2 УБИТ. Амнезия Воли вылечена. `compute_willpower` читает `trauma_markers`. Каждая травма добавляет +0.1 к `identity_rigidity` (макс +0.3). Предательство закаляет.
- **S53:** GAP7 УБИТ. Слепота Аватара устранена. `_extract_observer_state` в `LocalCausalSolver` корректно парсит `psyche` игрока. Аватар получает давление от паники толпы.
- **S50:** GAP8 УБИТ. `CommunicationIntent` обогащен `semantic_action` и `target_id`. `IntentEventAdapter` пробрасывает их в payload `NPC_SPOKE`. `DirectiveInterpretationSubscriber` больше не получает пустышку. Труба Воли размурована.
- **S50:** GAP3 УБИТ. `translate_kernel_to_context` принимает `body_state`. Внедрено Соматическое Вето: `pain > 0.8` обнуляет `FLEE`, `shock > 0.7` обнуляет `ATTACK`, `blood_loss > 0.6` режет `feasibility` физических действий до 0.3. Тело vetoирует Мозг.
- **S50:** GAP12 УБИТ. `_enrich_local_positions` вычисляет интерполированную позицию для NPC в активном транзите (LOD1). Бэкенд-сервисы видят истину, введен флаг `in_transit`.
- **S49:** ВЕРИФИЦИРОВАН РАЗРЫВ: Незваные NPC (`blacksmith_orm`, `merchant_goran`) получают `approach` от DecisionHub при команде, адресованной другому NPC. Требует фильтр целевого NPC (отложено).
- **S49:** ВЕРИФИЦИРОВАН РАЗРЫВ: Хардкод русских глаголов в `npc_tick_pipeline.py` — нарушает локализуемость и разделение ответственности. `IntentCompressor` уже умеет классифицировать `MOVE` через pymorphy3, но Semantic Bridge (`S28_GATE`) возвращает `UNCERTAIN` — результат теряется на пути от `phase_1_input` до `hub_event`. После починки Bridge хардкод должен быть удалён.
- **[S50] 28.05.26:** GAP12 УБИТ. `_enrich_local_positions` вычисляет интерполированную позицию для NPC в активном транзите (LOD1). Бэкенд-сервисы видят истину, введен флаг `in_transit`.
- **[S51] 28.05.26:** GAP9 УБИТ. Реалистичное Пробуждение. Сон блокируется непрерывными скалярами `threat_gradient > 0.3` и `stress > 50`. `recent_directive` больше не сжигается мгновенно, предотвращая повторное укладывание в кровать на следующем тике.
- **[S54] GAP11 УБИТ:** Хардкод _MOVE_VERBS удален из npc_tick_pipeline.py. Semantic Bridge замкнут: IntentCompressor теперь распознает "сюда"/"мне" как target_reference='player', пайплайн корректно реагирует на semantic_action=MOVE без текстовых костылей.
- **[S54] ADR-084 (The Fool Phase 2):** Убито семантическое смешение EmbodiedVector. Разделены слои: EmbodiedImpulse (моторика), SocialSignal (наблюдаемость), CrowdThreatLevel (угроза для CFRM). Социальная тревога (DISTRESSED) больше не генерирует AVOIDANCE и PREDATOR_ALERT, предотвращая массовую панику толпы от приказа "подойди".
- **[S58] 30.05.26:** Фронтенд: Физика WASD (Push-out Resolution). Игрок больше не застревает между мебелью. Коллизии разрешаются выталкиванием по вектору проникновения. Уменьшен хитбокс (`PLAYER_RADIUS = 0.25`).
- **[S58] 30.05.26:** Фронтенд: Контракт рендера препятствий. `scene_renderer.py` теперь читает `x, y` как левый верхний угол (соответствует бэкенду), устраняя визуальный сдвиг хитбоксов мебели.
- **[S58] 30.05.26:** Бэкенд: Центроиды узлов графа. `graph_compiler.py` теперь вычисляет центр комнаты (`x + w/2`, `y + h/2`) вместо использования левого верхнего угла. Устранена телепортация NPC в углы стен при FLEE.
- **[S58] 30.05.26:** Фронтенд: Уважение TraversalState (ADR-092). Если NPC в статусе `MOVING`, фронтенд не перезаписывает его `local_position` из `npc_positions`, позволяя рендереру плавно интерполировать движение. Устранена массовая телепортация при Action-тиках.
- **[S59] 30.05.26:** ADR-102: `load_graph()` мёртв — возвращает пустой граф (0 узлов). Заменён на `SpatialService.build_for_location()` в `spatial_runtime.py`. Для работы SpatialService добавлен инжект `campaign_id` в `scene_state` через `get_scene_state()`.
- **[S59] 30.05.26:** ADR-102: `spatial_obstacles` теперь передаёт поле `type` (bar, table, chair...) из editor JSON на фронтенд. `scene_renderer.py` маппит типы на спрайты через `sprite_resolver.py` вместо прямоугольных заглушек.
- **[S59] 30.05.26:** ADR-102: FLEE-резолв починен. `get_furthest()` теперь принимает `exclude_node_ids` для исключения текущего узла NPC. Нормализация legacy ID (`room_1` → `tavern:room_1`) перед сравнением устраняет бегство NPC в свой же узел.
- **[S59] 30.05.26:** Фронтенд: Починен `UnboundLocalError` для `_old_lp` в `game_screen.py:807`. Чтение старой позиции NPC до перезаписи.

**Архитектурные запреты:**
- ❌ Мгновенное сжигание `recent_directive` в LifeEngine (GAP9).
- ❌ Прямая мутация `npc["position"]` или `npc["location"]`.
- ❌ Чтение дистанций из `scene_state` (только через `SpatialQueryService`).
- ❌ Вызов `scene_manager.apply_changes()` из подписчиков (`SceneChange` — проекция для фронтенда).
- ❌ Использование `TraversalState` без `MovementEngine`.
- ❌ Вызов `process_intents()` или `apply_changes()` из `npc_orchestration.py` (единственный владелец — `TickOrchestrator`).
- ❌ Повторная обработка `MovementIntent` (инвариант `processed=True`).
- ❌ Хардкод языковых глаголов в `npc_tick_pipeline.py` (после починки Semantic Bridge).
- ❌ `_enrich_local_positions` перетирает `local_position`, установленный пайплайном (LOD0 guard).
- ❌ Использование `load_graph()` — мёртвый код, возвращает пустой граф. Заменён на `SpatialService.build_for_location()` (ADR-102).
- ❌ Сравнение legacy ID (`room_1`) с canonical ID (`tavern:room_1`) без нормализации через `spatial_service.normalize_id()`.

---

## 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision)
**Текущая истина:** Решения рождаются из искривленного давления (Utility Deformation). Воля — инерция, а не порог. Подчинение требует легитимности.

**Эволюция:**
- **S19:** WillpowerGate (ADR-031). Cumulative Strain Model вместо бинарки. Шкала COMPLY → CONDITIONED.
- **S21:** Убийство объективных событий. Давление генерирует `PsychologicalPressure`, а не прямые команды.
- **S24:** Affective Resonance (ADR-036). Аффект искажает давление через `ResponseBias`.
- **S25:** Embodied Vector. Предрефлексивные моторные импульсы.
- **S29:** DecisionHub: убит хардкод `base += 0.6` для APPROACH. Страх бустит приближение к авторитету.
- **S31:** DecisionContext (ADR-050). Feasibility Layer (удаление невозможных действий) и Utility Deformation.
- **S35:** Attention Capture. Замена хардкод-порога `initiative_suppression > 0.7` на `recent_directive` (сжигание директивы после использования).
- **S36:** Legitimacy Gate (ADR-058). Нет страха/доверия = Irritation (агрессия) вместо Obedience.
- **S48:** Починка обрыва Трубы Воли на границе API. `routes.py` теперь пробрасывает `will_conflict_data` в JSON-ответе для Action-тиков (ранее поле удалялось при сборке ответа, фронтенд всегда получал `None`, инфекция поля ввода была невозможна).
- **S49:** Приказ игрока перекрывает ЛЮБОЕ решение DecisionHub. Рефлекс не пропускается при `intent=flee` — игрок является авторитетным источником причинности (ADR-061). Если NPC решил бежать, но игрок приказал подойти — NPC подходит.
- **[S50] 28.05.26:** GAP3 УБИТ. `translate_kernel_to_context` принимает `body_state`. Внедрено Соматическое Вето: `pain > 0.8` обнуляет `FLEE`, `shock > 0.7` обнуляет `ATTACK`, `blood_loss > 0.6` режет `feasibility` физических действий до 0.3. Тело vetoирует Мозг.
- **[S52] 28.05.26:** GAP10 УБИТ. `EventContext` обогащён `target_id`. DecisionHub фильтрует бонус `APPROACH` — только целевой NPC получает реакцию на `player_interacts`. Свидетели больше не подходят.
- **[S53] 28.05.26:** GAP2 УБИТ. Амнезия Воли вылечена. `compute_willpower` читает `trauma_markers`. Каждая травма добавляет +0.1 к `identity_rigidity` (макс +0.3). Предательство закаляет.
- **[S54] 26.05.26:** УБИТ Silent Crash Трубы Воли. `will.py` и `affect.py` обращались к `intent.action`, в то время как DTO содержит `semantic_action` в `parameters`. Добавлен безопасный fallback с приоритетом `parameters.semantic_action`. Воля больше не умирает тихо при `AttributeError`.
- **[S55] 17.05.26:** УБИТ Мертвый Вектор Эмоций (ADR-088). `IntentCompressor._fast_path_parse` возвращал `EmotionalVector` с нулями (aggression=0.0), так как не заполнял поле `semantic`. Внедрен маппинг `ActionType -> EmotionalVector` (ATTACK -> aggression=0.8). Воля аватара теперь адекватно сопротивляется агрессии (resistance вырос с 0.15 до ожидаемых значений).
- **[S60] 31.05.26:** УБИТ `_semantic_action=None` (ADR-091). `publish_classified_player_event` вызывался в `dm_phase.py` ДО `resolve_player_intent()` → `shared_context.intent_resolution` был `None` → ADR-091 override не срабатывал. Фикс: перенос вызова в `__init__.py` ПОСЛЕ установки `intent_resolution`. Runtime верифицирован: `[ADR-091] IntentCompressor override: DM_Router='player_attacks' → IC='attack'`.

**Архитектурные запреты:**
- ❌ Обращение к `intent.action` в `will.py`/`affect.py` без fallback на `parameters.semantic_action` (ADR-035).
- ❌ Вызов WillpowerGate более 1 раза за цикл.
- ❌ Генерация эмоций напрямую из CombatSubscriber (только PhysiologyPayload).
- ❌ Передача сырых дельт давления из текущего тика в DecisionHub (только консолидированное восприятие T-1).
- ❌ Пустой `topic` в `CommunicationIntent`.

---

## 3. ВОСПРИЯТИЕ И ФЕНОМЕНОЛОГИЯ (CFRM & Perception)
**Текущая истина:** Объективных фактов нет. Есть возмущения поля (`FieldDisturbance`), которые проецируются в субъективные феномены в зависимости от наблюдателя.

**Эволюция:**
- **S15-17:** CFRM Layer 1. Введение `ClusterGraph`, `EventBuffer`, `MembraneField`.
- **S21:** Смерть объективных событий. `EventBus` не хранит факты, а деобъектифицирует их через мост.
- **S26:** Epistemic Classification. Оценка уверенности (confidence) при классификации.
- **S30:** CFRM Phase 2. `semantic_seed` (геном нарратива). Проекция теряет энергию/форму (физика), достоверность (когнитивка), искажается (социалка).
- **S38:** Визуализация Cognitive Freeze на фронтенде (тремор при `initiative_suppression > 0.7`).
- **[S53] 28.05.26:** GAP7 УБИТ. Слепота Аватара устранена. `_extract_observer_state` в `LocalCausalSolver` корректно парсит `psyche.fear` для игрока. Аватар получает давление от паники толпы.

**Архитектурные запреты:**
- ❌ Хранение `EventDTO` в `EventBuffer` (только `FieldDisturbance`).
- ❌ Обход `LocalCausalSolver` при генерации давления.
- ❌ Мутация состояния из CausalObserver (только пассивная фиксация).

---

## 4. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat)
**Текущая истина:** Тело — материальный объект. Удар — чистая физика контакта, которая порождает боль и шок, а шок уже транслируется в эмоции.

**Эволюция:**
- **S12-14:** Создание `ImpactEngine`, `PhysiologyPayload`, `InjuryDTO`. Убийство RPG Hit Roll.
- **S16:** Каскад Shock → Emotion (ReactionSubscriber извлекает `shock_impulse`).
- **S20:** Очистка `combat_stats`. Перенос способностей в `body_profile`.
- **S30:** Fuzzy-matching `target_reference` в CombatSubscriber (починка мертвого пайплайна).
- **S48:** ВЕРИФИЦИРОВАНО: RPG Витализм в `state_interpreter.py`. Оценка физического состояния NPC идет по `hp_ratio`, игнорируя `pain`, `shock_impulse` и `blood_loss`. NPC с 80% HP, но `pain: 0.9` описывается LLM как "слегка ранен". Мост Физиология → Речь оборван. (УБИТО в S51).
- **[S51] 28.05.26:** GAP5 УБИТ. `state_interpreter.py` читает `pain`, `shock_impulse` и `blood_loss` из `body_state`. Боль и шок перекрывают HP. Агония = "тяжело ранен", нокаут = "без сознания". Каузальный мост Физиология → Речь замкнут.
- **[S54] 26.05.26:** УБИТ `NameError: blood_loss_delta`. `state_applicator.py` использовал переменную без извлечения из `PhysiologyPayload`. Добавлена строка экстракции.
- **[S57] 30.05.26:** RPG Витализм: нормализация шкалы `pain` (0-100 → 0-1) в `StateInterpreter._physical_state_to_word`. Ранее пороги были 0.9/0.6/0.3 (под 0-1), а `StateApplicator` пишет 0-100 — боль никогда не срабатывала. Также оживлён мёртвый `StateInterpreter.interpret()` — метод импортировался, но никогда не вызывался. `VerbalizationContext` обогащён полем `physical_state`. NPC теперь знает свою боль при само-вербализации.

- **[S59] 30.05.26:** УБИТ Silent Loss Physiology. `state_applicator.py`: `asdict` не импортирован на уровне модуля → краш при `add_injuries` → ВСЯ PhysiologyPayload дельта пропускалась молча (`body_state` никогда не создавался). Фикс: `from dataclasses import asdict` на уровне модуля.
- **[S59] 30.05.26:** УБИТ Serialization Black Hole. `NPCState.write_to_legacy()` не писал `body_state` в npc_dict → физиология терялась при каждой сериализации. `NPCStateAdapter.from_legacy()` не читал `body_state` → state.body_state всегда начинался пустым. Фикс: добавлено чтение/запись `body_state` в оба метода.
- **[S59] 30.05.26:** УБИТ Rule X Violation. `BehaviorManifestationService._manifest_npc()` читал только `stress_delta` и `psyche_state` из `npc_positions`, полностью игнорируя `body_state` (pain/blood_loss/shock_impulse). Фикс: построение `body_state_map` из `all_npcs_raw`, чтение физиологии для вычисления `locomotion_instability`, `micro_pause_density`, `action_interruption`.
- **[S59] 30.05.26:** `StateApplicator._apply_deltas()` — добавлено применение `shock_impulse` к `body_state` (ранее поле существовало в `PhysiologyPayload`, но не экстрактилось и не применялось).
- **[S59] 30.05.26:** `PhenomenologyProjectionService` — добавлены cue_keys для боли/крови/шока: WINCING (rigidity+instability), HOLDING_SIDE (micro_pause+rigidity), BLEEDING (micro_pause+instability), STAGGERED (action_interruption).
- **[S59] 30.05.26:** `StateApplicator.apply_batch()` — fallback на `"npc_id"` при поиске NPC dict (ранее искал только по `"id"`, что ломало применение дельт для NPC с ключом `"npc_id"`).
- **[S60] 31.05.26:** УБИТ Memory Black Hole. `_legacy_d = LegacyStateDeltaAdapter.collapse()` определена внутри `elif` (стр.144), но читалась в другом `elif` (стр.152) → `UnboundLocalError` → `[MEMORY] apply failed` для 6/6 NPC каждый тик. Память была полностью мертва. Фикс: вынесено до ветвления.
- **[S60] 31.05.26:** УБИТ Shock Immortality. `shock_impulse` не затухал между тиками (0.9→0.9→0.9 бесконечно). 4 файла: (1) `NPCStateSnapshot` — добавлено поле `shock_impulse`; (2) `_build_npc_snapshots` — извлечение из `body_state`; (3) `PhysiologyDecayHandler` — leaky integrator `SHOCK_DECAY_LAMBDA=0.08` (~8% за тик); (4) `StateApplicator` — разрешена отрицательная дельта `shock_impulse != 0.0` вместо `> 0.0`. Runtime верифицирован: shock=0.6→0.55→0.51.
- **[S60] 31.05.26:** Combat pipeline верифицирован end-to-end: `PLAYER_ATTACKED → CombatSubscriber → ImpactEngine(2 deltas) → _aggregate_deltas(PHYSICS_COMPOSITE) → apply_batch → body_state(pain=36→34→48→59)`. Print-диагностика конвертирована в `logger.debug`.

**Архитектурные запреты:**
- ❌ Использование полей дельт в `state_applicator` без извлечения из payload (все физиологические поля требуют явного extraction).
- ❌ Прямая мутация HP аватара в обход `ImpactEngine`.
- ❌ Использование `hp_ratio` в `state_interpreter` без учета `pain/shock/blood_loss` (GAP5).
- ❌ Масштабная несовместимость: `StateApplicator` пишет `pain` в 0-100, а интерпретаторы читают в 0-1 (нормализация `/100` обязательна при чтении из `body_state`).
- ❌ `CombatSubscriber` пишет в Emotion (Domain Leakage). Только `PhysiologyPayload`.
- ❌ `BehaviorManifestationService` читает эмоции (psyche.fear/stress) вместо физиологии (body_state.pain/blood_loss/shock_impulse) — Правило X (CAUSAL_CONTRACT §7).
- ❌ `write_to_legacy` / `from_legacy` без сериализации `body_state` — физиология теряется между тиками.
- ❌ `shock_impulse` без decay в `PhysiologyDecayHandler` — шок становится перманентным (ADR-105).
- ❌ `StateApplicator` проверяет `shock_impulse > 0.0` вместо `!= 0.0` — блокирует отрицательные дельты decay (ADR-105).
- **[S60] 31.05.26:** ДИАГНОСТИКА: StateInterpreter Ownership Audit (ADR-104). Обнаружено: `UrgencyLevel` (SCARED/PANIC/BROKEN) дублирует `EmotionTag` (fearful/panic) — два владельца одной концепции. Трассировка показала: `NPCStateDescription.emotional_state` (из UrgencyLevel) — мёртвое поле, не читается ни одним сервисом. `VerbalizationContext.emotion` и `emotional_nuance` — dormant (потребитель не найден, но статус unresolved). `PhysicalState` (из body_state) — живой и легитимный. Double Truth не проявляется в runtime (нет потребителя), но архитектурный долг существует. Зафиксировано в `architecture/physiology.yaml`.

---

## 5. ТРУБА ОРКЕСТРАТОРА И ВРЕМЯ (Pipeline & Elastic Time)
**Текущая истина:** Симуляция дискретна (каузальность), презентация непрерывна. `LifeEngine` — лоббист давления, а не бог-мутатор.

**Эволюция:**
- **S01-06:** Выстраивание фаз. Внедрение `DeltaBuffer` как единого канала мутации.
- **S28:** Выжигание легаси. Удаление зомби-полей из `AvatarStateDTO`.
- **S34:** Dual-Time Ontology. Запрет ретро-симуляции. `LifeEngine.tick()` возвращает интенты, а не меняет мир напрямую.
- **S36:** `GAME_TICK_INTERVAL_SECONDS` снижен с 900 до 60 (основа Elastic Time).
- **S48:** Реанимация Плоти Аватара в `game_loop/__init__.py`. Сборка `player_dict` для `all_npcs_raw` обогащена `body_state` и `psyche` из `avatar_service.load_state()`. Ранее аватар передавался как пустой шаблон ("скелет"), из-за чего `AvatarPresentationAssembler` получал дефолтные нули и не мог вычислить `pain`/`stress` для оверлеев.
- **S49:** Устранение двойной обработки MovementIntent. `npc_orchestration.py` вызывал `process_intents()` + `apply_changes()` параллельно с `TickOrchestrator` → каждый интент обрабатывался дважды → двойной транзит → телепортация. Убран дубликат, добавлен инвариант `processed` в доменную модель.
- **S49:** ВЕРИФИЦИРОВАН РАЗРЫВ: `game_loop_bridge.py` не пробрасывал `active_traversals` в `world_snapshot` → фронтенд не мог интерполировать движение. Исправлено: bridge копирует `active_traversals` из `scene_state`.
- **[S53] 28.05.26:** GAP1 УБИТ. Темпоральная асимметрия устранена. Когнитивный Оверлей теперь инжектит критический шок (`shock_impulse > 0.5`) мгновенно (T+0) вместе с директивами. Топор летит со скоростью слова.
- **[S54] 26.05.26:** УБИТ `NoneType finalize_result`. `execute_player_finalize` в `tick_orchestrator.py` не пробрасывал `player_result` в `_TickContext`, из-за чего метод возвращал `None` и крашил пайплайн.
- **[S55] 17.05.26:** УБИТ Каузальный Разрыв Spatial Pipe. В `execute_player_finalize` исправлена критическая подмена `campaign_id` на `location_id` при создании `_TickContext`. Ранее `SpatialService.build_for_location` искал граф в `campaigns/tavern_silver_wolf/` (не существует) вместо `campaigns/Open_road/` (где лежит карта), из-за чего пространственный пайплайн молча умирал при ходе игрока.
- **[S59] 30.05.26:** УБИТ Idle Tick Perception Blindness. `_phase_9_integration()` вызывал `produce_traces()` без `all_npcs_raw` → `body_state` всегда `None` в idle тиках → NPC с болью/кровью не проявляли симптомы. Фикс: передача `all_npcs_raw=ctx.all_npcs_raw`.
- **[S60] 31.05.26:** УБИТ `UnboundLocalError: _legacy_d`. В `npc_tick_pipeline.py:144` дублирующий вызов `LegacyStateDeltaAdapter.collapse()` внутри `elif` — переменная `_legacy_d` определялась повторно. Удалён дубль, верхнее вычисление (строка 139) уже корректно.
- **[S60] 31.05.26:** УБИТ `TypeError: non-default argument`. `VerbalizationContext.intent_target: Optional[str]` без `= None` — мина замедленного действия. Добавлен дефолт. `physical_state` дефолт заменён с `"невредим"` на `"unharmed"` (L10n-safe).

**Архитектурные запреты:**
- ❌ Создание `_TickContext` без `player_result` при ходе игрока (инвариант: player turn всегда имеет результат).
- ❌ Ретро-симуляция (цикл `LifeEngine.tick()` для нагона).
- ❌ Мутация состояния в обход `DeltaBuffer → apply_batch()`.
- ❌ Чтение `scene_state` оркестратором для бизнес-логики (только для проекции).

---

## 6. ПАМЯТЬ И СОЦИУМ (Memory & Social Physics)
**Текущая истина:** Память многослойна. Социальные акты (приказы) искривляют utility-space цели, а не генерируют `MovementIntent` напрямую.

**Эволюция:**
- **S03:** Мультисобытийность Perception.
- **S08:** Обогащение NPC социальными связями из `village_relations.json`.
- **S27:** Физика Власти. `DirectiveInterpretationSubscriber` транслирует приказы в `directive_obedience`. Не генерирует движение.
- **S32:** Починка трубы давления: `DirectiveInterpretationSubscriber().handle()` получает `ctx.all_npcs_raw`.
- **S47:** Баг #6 (Глухая Воля) УБИТ. `DirectiveInterpretationSubscriber` теперь получает `all_npcs_raw` через fallback на `DMContextDTO` при холодном кэше `LifeEngine` в ходе игрока. `ObediencePressure` больше не возвращается нулевым.
- **S48:** ВЕРИФИЦИРОВАНО: Семантическая Глухота. `IntentEventAdapter` при конвертации `CommunicationIntent` в `EventDTO(NPC_SPOKE)` выбрасывает `semantic_action` и `target_id`. Событие становится семантически пустым. Это блокирует реализацию NPC-to-NPC Social Physics, так как подписчик не может распознать приказ или угрозу. (УБИТО в S50).
- **[S50] 28.05.26:** GAP8 УБИТ. `CommunicationIntent` обогащен `semantic_action` и `target_id`. `IntentEventAdapter` пробрасывает их в payload `NPC_SPOKE`. `DirectiveInterpretationSubscriber` больше не получает пустышку. Труба Воли размурована.
- **[S51] 28.05.26:** GAP4 УБИТ. `DirectiveInterpretationSubscriber` ингибируется шоком. `shock > 0.7` → `return []`. Бессознательное тело не подчиняется приказам.
- **[S52] 28.05.26:** GAP13 УБИТ. `DirectiveInterpretationSubscriber` больше не хардкодит `fear_of_player`. Если источник приказа — NPC, легитимность вычисляется из `relationship_cache.fear_{source_id}`. Дорога к NPC-to-NPC иерархии открыта.

**Архитектурные запреты:**
- ❌ Публикация в память в обход `MemoryManager`.
- ❌ Хардкод `fear_of_player` в `DirectiveInterpretationSubscriber` для NPC-источников (GAP13).
- ❌ `DirectiveInterpretationSubscriber` генерирует `MovementIntent`.
- ❌ Вызов `DirectiveInterpretationSubscriber` без инъекции `all_npcs_raw` (иначе ObediencePressure=0.00).

---

## 7. ФРОНТЕНД И ПРЕЗЕНТАЦИЯ (UI & Embodiment)
**Текущая истина:** Фронтенд — это сенсорный орган игрока. Он искажается, болеет и сопротивляется, не зная внутренних метрик бэкенда.

**Эволюция:**
- **S10:** NarrativeBeat, пузыри Persona 5 стиля.
- **S18:** Создание Персонажа через Вектор Начальных Условий (Архетип + Темперамент).
- **S25:** Embodied Perception Interface. Виньетки, туннельное зрение.
- **S26:** Presentation Firewall (санитайз скаляров), Perceptual Momentum (S-curve сборки реальности).
- **S28:** Resistance Medium. Заражение поля ввода (`text_input.infect()`) навязанным текстом аватара.
- **S39:** Интеграция CDS. Фронтенд не парсит отчёты симуляции.
- **S48:** Замыкание Нервной Системы Эмбодимента. `GameScreen` извлекает `will_conflict_data` из Action-ответа и вызывает `text_input.infect()`. `avatar_state` обновляется при Action-тиках, передаваясь в `PresentationFirewall` и `PerceptualMomentum`. В `player_dict` (all_npcs_raw) инъектированы `body_state` и `psyche` из `avatar_service` (Реанимация Плоти), чтобы `AvatarPresentationAssembler` получал живые скаляры вместо дефолтных нулей. Провода подключены, ожидается починка генераторов (S49+).
- **[S54] 26.05.26:** Труба Эмбодимента ЗАМКНУТА. `will_conflict_data` проверенно доходит от `tick_orchestrator` до `text_input.infect()` на фронтенде. Поле ввода заражается моторным импульсом (например, "Замереть...") при конфликте воли. Словарь `IntentCompressor` расширен приставочными глаголами (выбить, откусить, укусить и т.д.) — Fast Path больше не возвращает `UNCERTAIN` на агрессивные действия.
- **[S56] 27.05.26:** The Fool v2 — визуализация моторных следов (дрожь/замер) и тултипов наблюдений замкнута от бэкенда до экрана. Бэкенд генерирует `embodied_traces` и `peripheral_cues` только на основе наблюдаемых симптомов (`stress_delta`, `psyche_state` -> "Напряженная поза", "Дрожит"). Починена потеря данных: `game_loop_bridge.py` больше не затирает `player_perception` при idle-тиках. Починен рендер: моторные смещения перенесены ДО отрисовки спрайта в `scene_renderer.py`.
- **[S57] 30.05.26:** Удалён дебаг-рендер `[OBS]` из правого верхнего угла экрана (дублировал тултипы без `npc_id`). Создана консоль наблюдений по клавише `Ё` (`pygame.K_BACKQUOTE` + `event.unicode` для русской раскладки) — полупрозрачная панель с `[OBS] npc_id: симптом`. Поддержка `event.unicode` обязательна на Windows.
- **[S57] 30.05.26:** DM-агент теперь читает `embodied_traces` из `player_perception` (Фаза 9) и формирует блок "Наблюдаемые симптомы NPC". DM описывает видимые следы (дрожит, покачивается), а не внутренние состояния (pain, fear). Поле `player_perception` легализовано в `PipelineContext`. The Fool: Physiology → Manifestation → Perception → Narrative.
- **[S59] 30.05.26:** Combat → Pain/Blood → UI Pipeline ЗАМКНУТ. 9 фиксов: (1) `asdict` не импортирован на уровне модуля `state_applicator.py` → краш при `add_injuries` → ВСЯ дельта пропускалась; (2) `write_to_legacy` не писал `body_state` обратно в npc_dict → физиология терялась при каждой сериализации; (3) `from_legacy` не читал `body_state` → state.body_state всегда пустой; (4) `BehaviorManifestationService` не читал `body_state` из `all_npcs_raw` (Правило X violation); (5) `apply_batch` fallback на `"npc_id"` при поиске NPC; (6) `PhenomenologyProjectionService` — cue_keys для боли/крови (WINCING/HOLDING_SIDE/BLEEDING/STAGGERED); (7) `StateApplicator` — применение `shock_impulse` к body_state; (8) Idle tick perception не передавал `all_npcs_raw` в `produce_traces()`; (9) `CombatSubscriber` — диагностический `[COMBAT_HANDLE]` лог.
- **[S59] 30.05.26:** ADR-102: `spatial_obstacles` пробрасывает `type` (bar, table, chair) из editor JSON на фронтенд. `scene_renderer.py` маппит типы на спрайты через `sprite_resolver.py` вместо прямоугольных заглушек.
- **[S59] 30.05.26:** Починен `UnboundLocalError` для `_old_lp` в `game_screen.py`. Чтение старой позиции NPC до перезаписи из `npc_positions`.

**Архитектурные запреты:**
- ❌ Возврат `UNCERTAIN` из `IntentCompressor` на известные приставочные глаголы ATTACK/THREATEN (словарь должен покрывать pymorphy3 леммы).
- ❌ Применение моторных смещений (дрожь) к экранным координатам ПОСЛЕ отрисовки спрайта. Смещение применяется ТОЛЬКО ДО `self.screen.blit()`.
- ❌ Перезапись `result.world_snapshot` целиком в `game_loop_bridge.py` (уничтожает `player_perception`). Только точечное обновление `result.world_snapshot["npc_positions"]`.
- ❌ Импорт `backend/app/` во фронтенд (Устав §1.1).
- ❌ Передача Игроку внутренних метрик NPC (HP, fear, trust). Только наблюдаемые симптомы ("дрожит", "кровоточит").
- ❌ DM-агент читает внутренние состояния NPC (pain, fear, shock) напрямую вместо наблюдаемых симптомов (`embodied_traces`). Kernel Leakage = архитектурный баг.
- ❌ Обработка клавиши `Ё` только через `pygame.K_BACKQUOTE` без проверки `event.unicode` (русская раскладка Windows не генерирует BACKQUOTE).
- ❌ Использование `asdict()` на границе API без Pydantic/Dataclass валидации.

---

## 8. НАБЛЮДАЕМОСТЬ И ДИАГНОСТИКА (CDS)
**Текущая истина:** Наблюдение не создает причинность. CDS — пассивный аудиторе.

**Эволюция:**
- **S29-31:** Создание Каузальных Песочниц (Deterministic Clock, Causal Trace, Probes).
- **S39:** Интеграция Causal Diagnostic System. Анализ stdout/git/логов без вмешательства в рантайм.

**Архитектурные запреты:**
- ❌ Обратная связь из CDS в рантайм симуляции.
- ❌ Прерывание каузального потока при падении CDS.

---

### Почему этот формат лучше для ИИ:
1. **Контекстная локальность:** Чтобы починить баг с движением, ИИ читает секцию 1 и видит *всю* историю и *все* запреты без шума от починки UI.
2. **Защита от легаси:** Секция явно показывает, что `LifeEngine` больше не бог (S32), а `SpatialQueryService` — авторитет (S37). ИИ не предложит вернуть `DIRECT_REFLEX`.
3. **Каузальная целостность:** Формат отражает саму суть ENIGMA — система разделена на домены давления, а не на хронологию коммитов.
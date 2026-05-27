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

**Архитектурные запреты:**
- ❌ Использование полей дельт в `state_applicator` без извлечения из payload (все физиологические поля требуют явного extraction).
- ❌ Прямая мутация HP аватара в обход `ImpactEngine`.
- ❌ Использование `hp_ratio` в `state_interpreter` без учета `pain/shock/blood_loss` (GAP5).
- ❌ `CombatSubscriber` пишет в Emotion (Domain Leakage). Только `PhysiologyPayload`.

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

**Архитектурные запреты:**
- ❌ Возврат `UNCERTAIN` из `IntentCompressor` на известные приставочные глаголы ATTACK/THREATEN (словарь должен покрывать pymorphy3 леммы).
- ❌ Импорт `backend/app/` во фронтенд (Устав §1.1).
- ❌ Передача Игроку внутренних метрик NPC (HP, fear, trust). Только наблюдаемые симптомы ("дрожит", "кровоточит").
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
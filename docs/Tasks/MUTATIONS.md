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
- **S47:** ОТМЕНЕНО: Попытка динамической синхронизации `npc_positions.player` из `player_spatial` и внедрение точных координат цели (`target_local_xy`) откатана. Изменения ломали рантайм-конвейер движения и вызывали массовую телепортацию NPC. Проблема пространственного резолва игрока требует иного подхода.

**Архитектурные запреты:**
- ❌ Прямая мутация `npc["position"]` или `npc["location"]`.
- ❌ Чтение дистанций из `scene_state` (только через `SpatialQueryService`).
- ❌ Вызов `scene_manager.apply_changes()` из подписчиков (`SceneChange` — проекция для фронтенда).
- ❌ Использование `TraversalState` без `MovementEngine`.

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

**Архитектурные запреты:**
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

**Архитектурные запреты:**
- ❌ Прямая мутация HP аватара в обход `ImpactEngine`.
- ❌ `CombatSubscriber` пишет в Emotion (Domain Leakage). Только `PhysiologyPayload`.

---

## 5. ТРУБА ОРКЕСТРАТОРА И ВРЕМЯ (Pipeline & Elastic Time)
**Текущая истина:** Симуляция дискретна (каузальность), презентация непрерывна. `LifeEngine` — лоббист давления, а не бог-мутатор.

**Эволюция:**
- **S01-06:** Выстраивание фаз. Внедрение `DeltaBuffer` как единого канала мутации.
- **S28:** Выжигание легаси. Удаление зомби-полей из `AvatarStateDTO`.
- **S34:** Dual-Time Ontology. Запрет ретро-симуляции. `LifeEngine.tick()` возвращает интенты, а не меняет мир напрямую.
- **S36:** `GAME_TICK_INTERVAL_SECONDS` снижен с 900 до 60 (основа Elastic Time).

**Архитектурные запреты:**
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

**Архитектурные запреты:**
- ❌ Публикация в память в обход `MemoryManager`.
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

**Архитектурные запреты:**
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
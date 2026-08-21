# MUTATIONS.md — Доменно-Каузальная Эволюция ENIGMA

> **Формат:** Хронологическая лента сессий → Агрегированные архитектурные запреты → Справочник доменов.
> **Правило чтения для LLM:** Ищи сессию по номеру (Ctrl+F `S##`) или по домену (Ctrl+F `Домен:`).
> **Статус:** Живой документ. Каждая сессия = атомарное изменение системы.

---

## 0. НАВИГАЦИОННЫЙ ИНДЕКС

### 0.1 Хронологическая карта сессий

| Сессия | Дата | Домены | Тип | Ключевые ADR/GAP |
|--------|------|--------|-----|------------------|
| S03 | ??? | 6. ПАМЯТЬ И СОЦИУМ (Memory & Social Physics) | Эволюция |  |
| S04 | ??? | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | Эволюция |  |
| S08 | ??? | 6. ПАМЯТЬ И СОЦИУМ (Memory & Social Physics) | Эволюция |  |
| S10 | ??? | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion), | Эволюция |  |
| S16 | ??? | 4. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat) | Эволюция |  |
| S18 | ??? | 7. ФРОНТЕНД И ПРЕЗЕНТАЦИЯ (UI & Embodiment) | Эволюция |  |
| S19 | ??? | 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Deci | ADR | ADR-031 |
| S20 | ??? | 4. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat) | Эволюция |  |
| S21 | ??? | 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Deci | Эволюция |  |
| S24 | ??? | 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Deci | ADR | ADR-036 |
| S25 | ??? | 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Deci | Эволюция |  |
| S26 | ??? | 3. ВОСПРИЯТИЕ И ФЕНОМЕНОЛОГИЯ (CFRM & Perception), | Эволюция |  |
| S27 | ??? | 6. ПАМЯТЬ И СОЦИУМ (Memory & Social Physics) | Эволюция |  |
| S28 | ??? | 5. ТРУБА ОРКЕСТРАТОРА И ВРЕМЯ (Pipeline & Elastic  | Эволюция |  |
| S29 | ??? | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion), | Эволюция |  |
| S30 | ??? | 3. ВОСПРИЯТИЕ И ФЕНОМЕНОЛОГИЯ (CFRM & Perception), | Эволюция |  |
| S31 | ??? | 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Deci | ADR | ADR-050 |
| S32 | ??? | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion), | Эволюция |  |
| S33 | ??? | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | FIX |  |
| S34 | ??? | 5. ТРУБА ОРКЕСТРАТОРА И ВРЕМЯ (Pipeline & Elastic  | Эволюция |  |
| S35 | ??? | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion), | Эволюция |  |
| S36 | ??? | 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Deci | ADR | ADR-058 |
| S37 | ??? | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | ADR | ADR-048 |
| S38 | ??? | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion), | Эволюция |  |
| S39 | ??? | 7. ФРОНТЕНД И ПРЕЗЕНТАЦИЯ (UI & Embodiment), 8. НА | Эволюция |  |
| S46 | ??? | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | ADR | ADR-048 |
| S47 | ??? | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion), | FIX |  |
| S48 | ??? | 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Deci | GAP |  |
| S49 | ??? | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion), | GAP | ADR-061 |
| S50 | 28.05.26 | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion), | FIX | GAP3, GAP8 |
| S51 | 28.05.26 | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion), | FIX | GAP5, GAP9 |
| S52 | 28.05.26 | 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Deci | FIX | GAP10, GAP13 |
| S53 | 28.05.26 | 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Deci | FIX | GAP7, GAP1 |
| S54 | 26.05.26 | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion), | FIX | ADR-084, GAP11 |
| S55 | 17.05.26 | 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Deci | FIX | ADR-088 |
| S56 | 27.05.26 | 7. ФРОНТЕНД И ПРЕЗЕНТАЦИЯ (UI & Embodiment) | Эволюция |  |
| S57 | 30.05.26 | 4. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat), 7. ФРОН | Эволюция |  |
| S58 | 30.05.26 | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | ADR | ADR-092 |
| S59 | 30.05.26 | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion), | FIX | ADR-102 |
| S60 | 31.05.26 | 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Deci | FIX | ADR-091, ADR-104 |
| S61 | 02.06.26 | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion), | ADR | ADR-114, ADR-101 |
| S62 | 03.06.26 | 3. ВОСПРИЯТИЕ И ФЕНОМЕНОЛОГИЯ (CFRM & Perception) | FIX |  |
| S63 | ??? | 9. SOCIAL & AFFECTIVE ARCHITECTURE (SSOT & CAUSAL  | ADR | ADR-116 |
| S64 | 03.06.26 | 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Deci | FIX | ADR-036 |
| S65 | 04.06.26 | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion), | Эволюция |  |
| S66 | ??? | 9. SOCIAL & AFFECTIVE ARCHITECTURE (SSOT & CAUSAL  | ADR | ADR-123 |
| S67 | 2026-06-05 | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion), | FIX | ADR-121, ADR-124 |
| S68 | 05.06.26 | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion), | ADR | ADR-125, ADR-124 |
| S69 | 06.06.26 | 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion), | FIX |  |
| S71 | 06.06.26 | 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Deci | Эволюция |  |

### 0.2 Легенда типов записей

- **GAP** — Верифицированный архитектурный разрыв (требует фикса)
- **FIX** — Закрытый баг или разрыв (GAP убит)
- **ADR** — Архитектурное решение (новый контракт/инвариант)
- **Эволюция** — Инкрементальное изменение без бага

### 0.3 Быстрый поиск по доменам

- **1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion)**: S04, S10, S29, S32, S33, S35, S37, S38, S46, S47, S49, S50, S51, S54, S58, S59, S61, S65, S67, S68, S69
- **2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision)**: S19, S21, S24, S25, S29, S31, S35, S36, S48, S49, S50, S52, S53, S54, S55, S60, S64, S68, S69, S71
- **3. ВОСПРИЯТИЕ И ФЕНОМЕНОЛОГИЯ (CFRM & Perception)**: S21, S26, S30, S38, S53, S62
- **4. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat)**: S16, S20, S30, S48, S51, S54, S57, S59, S60, S61, S67
- **5. ТРУБА ОРКЕСТРАТОРА И ВРЕМЯ (Pipeline & Elastic Time)**: S28, S34, S36, S48, S49, S53, S54, S55, S59, S60, S61, S65, S67
- **6. ПАМЯТЬ И СОЦИУМ (Memory & Social Physics)**: S03, S08, S27, S32, S47, S48, S50, S51, S52
- **7. ФРОНТЕНД И ПРЕЗЕНТАЦИЯ (UI & Embodiment)**: S10, S18, S25, S26, S28, S39, S48, S54, S56, S57, S59, S60, S61
- **8. НАБЛЮДАЕМОСТЬ И ДИАГНОСТИКА (CDS)**: S39, S65
- **9. SOCIAL & AFFECTIVE ARCHITECTURE (SSOT & CAUSAL DERIVATION)**: S63, S66

---


## 1. ХРОНОЛОГИЧЕСКАЯ ЛЕНТА СЕССИЙ (S01–S71)

> **Правило чтения:** Каждая сессия = атомарное изменение. Читай сверху вниз для понимания эволюции.
> **Для фикса бага:** Найди последнюю сессию, затронувшую твой домен, и читай от неё назад.

### 1.03 S03 [???] [⚪ Эволюция]

**Домены:** 6. ПАМЯТЬ И СОЦИУМ (Memory & Social Physics)

**S03:** Мультисобытийность Perception.

---

### 1.04 S04 [???] [⚪ Эволюция]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion)

**S04:** Централизация через `SpatialService` v1.2, убит хардкод локаций.

---

### 1.08 S08 [???] [⚪ Эволюция]

**Домены:** 6. ПАМЯТЬ И СОЦИУМ (Memory & Social Physics)

**S08:** Обогащение NPC социальными связями из `village_relations.json`.

---

### 1.10 S10 [???] [⚪ Эволюция]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | 7. ФРОНТЕНД И ПРЕЗЕНТАЦИЯ (UI & Embodiment)

**S10:** Запрет `MovementIntent` для микро-перемещений (требуется `LocalSteeringIntent`, позже отклонен в пользу LOD0 в `MovementIntent`).

**S10:** NarrativeBeat, пузыри Persona 5 стиля.

---

### 1.16 S16 [???] [⚪ Эволюция]

**Домены:** 4. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat)

**S16:** Каскад Shock → Emotion (ReactionSubscriber извлекает `shock_impulse`).

---

### 1.18 S18 [???] [⚪ Эволюция]

**Домены:** 7. ФРОНТЕНД И ПРЕЗЕНТАЦИЯ (UI & Embodiment)

**S18:** Создание Персонажа через Вектор Начальных Условий (Архетип + Темперамент).

---

### 1.19 S19 [???] [🔵 ADR]

**Домены:** 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision)

**S19:** WillpowerGate (ADR-031). Cumulative Strain Model вместо бинарки. Шкала COMPLY → CONDITIONED.

---

### 1.20 S20 [???] [⚪ Эволюция]

**Домены:** 4. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat)

**S20:** Очистка `combat_stats`. Перенос способностей в `body_profile`.

---

### 1.21 S21 [???] [⚪ Эволюция]

**Домены:** 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision) | 3. ВОСПРИЯТИЕ И ФЕНОМЕНОЛОГИЯ (CFRM & Perception)

**S21:** Убийство объективных событий. Давление генерирует `PsychologicalPressure`, а не прямые команды.

**S21:** Смерть объективных событий. `EventBus` не хранит факты, а деобъектифицирует их через мост.

---

### 1.24 S24 [???] [🔵 ADR]

**Домены:** 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision)

**S24:** Affective Resonance (ADR-036). Аффект искажает давление через `ResponseBias`.

---

### 1.25 S25 [???] [⚪ Эволюция]

**Домены:** 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision) | 7. ФРОНТЕНД И ПРЕЗЕНТАЦИЯ (UI & Embodiment)

**S25:** Embodied Vector. Предрефлексивные моторные импульсы.

**S25:** Embodied Perception Interface. Виньетки, туннельное зрение.

---

### 1.26 S26 [???] [⚪ Эволюция]

**Домены:** 3. ВОСПРИЯТИЕ И ФЕНОМЕНОЛОГИЯ (CFRM & Perception) | 7. ФРОНТЕНД И ПРЕЗЕНТАЦИЯ (UI & Embodiment)

**S26:** Epistemic Classification. Оценка уверенности (confidence) при классификации.

**S26:** Presentation Firewall (санитайз скаляров), Perceptual Momentum (S-curve сборки реальности).

---

### 1.27 S27 [???] [⚪ Эволюция]

**Домены:** 6. ПАМЯТЬ И СОЦИУМ (Memory & Social Physics)

**S27:** Физика Власти. `DirectiveInterpretationSubscriber` транслирует приказы в `directive_obedience`. Не генерирует движение.

---

### 1.28 S28 [???] [⚪ Эволюция]

**Домены:** 5. ТРУБА ОРКЕСТРАТОРА И ВРЕМЯ (Pipeline & Elastic Time) | 7. ФРОНТЕНД И ПРЕЗЕНТАЦИЯ (UI & Embodiment)

**S28:** Выжигание легаси. Удаление зомби-полей из `AvatarStateDTO`.

**S28:** Resistance Medium. Заражение поля ввода (`text_input.infect()`) навязанным текстом аватара.

---

### 1.29 S29 [???] [⚪ Эволюция]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision)

**S29:** Убийство телепортации. Внедрен Каузальный Lerp на фронтенде. `DIRECT_REFLEX` удален — приказ идет через EventBus.

**S29:** DecisionHub: убит хардкод `base += 0.6` для APPROACH. Страх бустит приближение к авторитету.

---

### 1.30 S30 [???] [⚪ Эволюция]

**Домены:** 3. ВОСПРИЯТИЕ И ФЕНОМЕНОЛОГИЯ (CFRM & Perception) | 4. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat)

**S30:** CFRM Phase 2. `semantic_seed` (геном нарратива). Проекция теряет энергию/форму (физика), достоверность (когнитивка), искажается (социалка).

**S30:** Fuzzy-matching `target_reference` в CombatSubscriber (починка мертвого пайплайна).

---

### 1.31 S31 [???] [🔵 ADR]

**Домены:** 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision)

**S31:** DecisionContext (ADR-050). Feasibility Layer (удаление невозможных действий) и Utility Deformation.

---

### 1.32 S32 [???] [⚪ Эволюция]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | 6. ПАМЯТЬ И СОЦИУМ (Memory & Social Physics)

**S32:** LifeEngine De-godification. Лишен права мутации позиции и вызова MovementEngine напрямую.

**S32:** Починка трубы давления: `DirectiveInterpretationSubscriber().handle()` получает `ctx.all_npcs_raw`.

---

### 1.33 S33 [???] [🟢 ЗАКРЫТ]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion)

**S33:** Нормализация префиксов макро-зон (LOD0 fix).

---

### 1.34 S34 [???] [⚪ Эволюция]

**Домены:** 5. ТРУБА ОРКЕСТРАТОРА И ВРЕМЯ (Pipeline & Elastic Time)

**S34:** Dual-Time Ontology. Запрет ретро-симуляции. `LifeEngine.tick()` возвращает интенты, а не меняет мир напрямую.

---

### 1.35 S35 [???] [⚪ Эволюция]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision)

**S35:** Safe Spatial Fallback. Отмена перемещения при отсутствии узла (убран фоллбэк на `entrance`). Collision Avoidance LOD0.

**S35:** Attention Capture. Замена хардкод-порога `initiative_suppression > 0.7` на `recent_directive` (сжигание директивы после использования).

---

### 1.36 S36 [???] [🔵 ADR]

**Домены:** 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision) | 5. ТРУБА ОРКЕСТРАТОРА И ВРЕМЯ (Pipeline & Elastic Time)

**S36:** Legitimacy Gate (ADR-058). Нет страха/доверия = Irritation (агрессия) вместо Obedience.

**S36:** `GAME_TICK_INTERVAL_SECONDS` снижен с 900 до 60 (основа Elastic Time).

---

### 1.37 S37 [???] [🔵 ADR]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion)

**S37:** Authoritative Spatial Spine (ADR-048). `SpatialQueryService` инстанцирован. Чтение `scene_state["player_distances"]` запрещено.

---

### 1.38 S38 [???] [⚪ Эволюция]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | 3. ВОСПРИЯТИЕ И ФЕНОМЕНОЛОГИЯ (CFRM & Perception)

**S38:** Dual-Time Ontology на фронтенде. `_resolve_visual_xy` работает через `path_waypoints` + `progress`. Локальный pathfinding удален.

**S38:** Визуализация Cognitive Freeze на фронтенде (тремор при `initiative_suppression > 0.7`).

---

### 1.39 S39 [???] [⚪ Эволюция]

**Домены:** 7. ФРОНТЕНД И ПРЕЗЕНТАЦИЯ (UI & Embodiment) | 8. НАБЛЮДАЕМОСТЬ И ДИАГНОСТИКА (CDS)

**S39:** Интеграция CDS. Фронтенд не парсит отчёты симуляции.

**S39:** Интеграция Causal Diagnostic System. Анализ stdout/git/логов без вмешательства в рантайм.

---

### 1.46 S46 [???] [🟢 ЗАКРЫТ]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion)

**S46:** Убита перезапись позиции игрока из протухшего `player_spatial`. `npc_orchestration.py` читал `player_spatial.local_position` (запись запрещена ADR-048 Phase 3 — всегда протухший spawn) и перезаписывал `npc_positions.player.local_position`, убивая актуальные координаты от фронтенда. Фикс: читать из `npc_positions.player` напрямую, только резолвить ближайший узел. Также починен лог `PHASE_5_PLAYER nearby_npcs=?` — читалось с `_TickContext` (нет атрибута), исправлено на `dm.nearby_npcs`.

---

### 1.47 S47 [???] [🟢 ЗАКРЫТ]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | 6. ПАМЯТЬ И СОЦИУМ (Memory & Social Physics)

**S47:** Консолидация `SpatialService` в `TickOrchestrator`. Внедрен `_resolve_spatial_service()`, убивший трехкратную ручную сборку `build_for_location()`.

**S47:** ОТМЕНЕНО: Попытка динамической синхронизации `npc_positions.player` из `player_spatial` и внедрение точных координат цели (`target_locaыl_xy`) откатана. Изменения ломали рантайм-конвейер движения и вызывали массовую телепортацию NPC. Проблема пространственного резолва игрока требует иного подхода.

**S47:** Баг #6 (Глухая Воля) УБИТ. `DirectiveInterpretationSubscriber` теперь получает `all_npcs_raw` через fallback на `DMContextDTO` при холодном кэше `LifeEngine` в ходе игрока. `ObediencePressure` больше не возвращается нулевым.

---

### 1.48 S48 [???] [🔴 ВЕРИФИЦИРОВАННЫЙ РАЗРЫВ]

**Домены:** 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision) | 4. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat) | 5. ТРУБА ОРКЕСТРАТОРА И ВРЕМЯ (Pipeline & Elastic Time) | 6. ПАМЯТЬ И СОЦИУМ (Memory & Social Physics) | 7. ФРОНТЕНД И ПРЕЗЕНТАЦИЯ (UI & Embodiment)

**S48:** Починка обрыва Трубы Воли на границе API. `routes.py` теперь пробрасывает `will_conflict_data` в JSON-ответе для Action-тиков (ранее поле удалялось при сборке ответа, фронтенд всегда получал `None`, инфекция поля ввода была невозможна).

**S48:** ВЕРИФИЦИРОВАНО: RPG Витализм в `state_interpreter.py`. Оценка физического состояния NPC идет по `hp_ratio`, игнорируя `pain`, `shock_impulse` и `blood_loss`. NPC с 80% HP, но `pain: 0.9` описывается LLM как "слегка ранен". Мост Физиология → Речь оборван. (УБИТО в S51).

**S48:** Реанимация Плоти Аватара в `game_loop/__init__.py`. Сборка `player_dict` для `all_npcs_raw` обогащена `body_state` и `psyche` из `avatar_service.load_state()`. Ранее аватар передавался как пустой шаблон ("скелет"), из-за чего `AvatarPresentationAssembler` получал дефолтные нули и не мог вычислить `pain`/`stress` для оверлеев.

**S48:** ВЕРИФИЦИРОВАНО: Семантическая Глухота. `IntentEventAdapter` при конвертации `CommunicationIntent` в `EventDTO(NPC_SPOKE)` выбрасывает `semantic_action` и `target_id`. Событие становится семантически пустым. Это блокирует реализацию NPC-to-NPC Social Physics, так как подписчик не может распознать приказ или угрозу. (УБИТО в S50).

**S48:** Замыкание Нервной Системы Эмбодимента. `GameScreen` извлекает `will_conflict_data` из Action-ответа и вызывает `text_input.infect()`. `avatar_state` обновляется при Action-тиках, передаваясь в `PresentationFirewall` и `PerceptualMomentum`. В `player_dict` (all_npcs_raw) инъектированы `body_state` и `psyche` из `avatar_service` (Реанимация Плоти), чтобы `AvatarPresentationAssembler` получал живые скаляры вместо дефолтных нулей. Провода подключены, ожидается починка генераторов (S49+).

---

### 1.49 S49 [???] [🔴 ВЕРИФИЦИРОВАННЫЙ РАЗРЫВ]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision) | 5. ТРУБА ОРКЕСТРАТОРА И ВРЕМЯ (Pipeline & Elastic Time)

**S49:** Инвариант единого владения причинностью движения. `npc_orchestration.py` лишиён права вызывать `process_intents()` и `apply_changes()` — единственный владелец `TickOrchestrator`. В доменную модель (`MacroMovementGoal`, `LocalSteeringGoal`) добавлены поля `processed` и `processor` — повторная обработка интента вызывает `RuntimeError`.

**S49:** Проброс `target_local_xy` в `MacroMovementGoal` при `reactive:approach`. Ранее координаты цели (позиция игрока) вычислялись в `_resolve_reactive_movement`, но терялись при создании `MacroMovementGoal` → NPC шли к центру узла вместо точной позиции игрока.

**S49:** Рефлекс теперь перекрывает ЛЮБОЕ решение DecisionHub, включая `flee`. Убран guard `if decision.intent.value not in ("approach", "flee")` — приказ игрока = авторитетный источник причинности (ADR-061).

**S49:** Частичное совпадение имени NPC. "торнин" теперь совпадает с "торнин серебряная луна" — рефлекс проверяет отдельные слова имени (≥3 символа), а не только полное имя. Без этого NPC с длинными именами были глухи к приказам.

**S49:** Ghost Position Fix. При создании нового транзита, если NPC уже в активном транзите, `from_xy` вычисляется интерполяцией текущего прогресса, а не берётся из устаревшего `local_position`.

**S49:** Bridge пробрасывает `active_traversals` в `world_snapshot`. Без этого фронтенд не мог интерполировать движение — NPC либо телепортировались, либо стояли на месте.

**S49:** `_enrich_local_positions` больше не перетирает `local_position` для сдвинувшихся NPC. Добавлен LOD0 guard: если позиция уже валидна (установлена пайплайном), enrichment пропускает.

**S49:** ВЕРИФИЦИРОВАН РАЗРЫВ: LifeEngine перезаписывает реактивные транзиты (`reactive:approach`) schedule-интентами (`schedule:sleeping`) каждый idle tick. NPC не доходит до игрока — его постоянно редиректят в кровать. Требует механизм пробуждения (отложено).

**S49:** ВЕРИФИЦИРОВАН РАЗРЫВ: Незваные NPC (`blacksmith_orm`, `merchant_goran`) получают `approach` от DecisionHub при команде, адресованной другому NPC. Требует фильтр целевого NPC (отложено).

**S49:** ВЕРИФИЦИРОВАН РАЗРЫВ: Хардкод русских глаголов в `npc_tick_pipeline.py` — нарушает локализуемость и разделение ответственности. `IntentCompressor` уже умеет классифицировать `MOVE` через pymorphy3, но Semantic Bridge (`S28_GATE`) возвращает `UNCERTAIN` — результат теряется на пути от `phase_1_input` до `hub_event`. После починки Bridge хардкод должен быть удалён.

**S49:** Приказ игрока перекрывает ЛЮБОЕ решение DecisionHub. Рефлекс не пропускается при `intent=flee` — игрок является авторитетным источником причинности (ADR-061). Если NPC решил бежать, но игрок приказал подойти — NPC подходит.

**S49:** Устранение двойной обработки MovementIntent. `npc_orchestration.py` вызывал `process_intents()` + `apply_changes()` параллельно с `TickOrchestrator` → каждый интент обрабатывался дважды → двойной транзит → телепортация. Убран дубликат, добавлен инвариант `processed` в доменную модель.

**S49:** ВЕРИФИЦИРОВАН РАЗРЫВ: `game_loop_bridge.py` не пробрасывал `active_traversals` в `world_snapshot` → фронтенд не мог интерполировать движение. Исправлено: bridge копирует `active_traversals` из `scene_state`.

---

### 1.50 S50 [28.05.26] [🟢 ЗАКРЫТ]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision) | 6. ПАМЯТЬ И СОЦИУМ (Memory & Social Physics)

**[S50] 28.05.26:** GAP12 УБИТ. `_enrich_local_positions` вычисляет интерполированную позицию для NPC в активном транзите (LOD1). Бэкенд-сервисы видят истину, введен флаг `in_transit`.

**[S50] 28.05.26:** GAP3 УБИТ. `translate_kernel_to_context` принимает `body_state`. Внедрено Соматическое Вето: `pain > 0.8` обнуляет `FLEE`, `shock > 0.7` обнуляет `ATTACK`, `blood_loss > 0.6` режет `feasibility` физических действий до 0.3. Тело vetoирует Мозг.

**[S50] 28.05.26:** GAP8 УБИТ. `CommunicationIntent` обогащен `semantic_action` и `target_id`. `IntentEventAdapter` пробрасывает их в payload `NPC_SPOKE`. `DirectiveInterpretationSubscriber` больше не получает пустышку. Труба Воли размурована.

---

### 1.51 S51 [28.05.26] [🟢 ЗАКРЫТ]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | 4. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat) | 6. ПАМЯТЬ И СОЦИУМ (Memory & Social Physics)

**[S51] 28.05.26:** GAP9 УБИТ. Реалистичное Пробуждение. Сон блокируется непрерывными скалярами `threat_gradient > 0.3` и `stress > 50`. `recent_directive` больше не сжигается мгновенно, предотвращая повторное укладывание в кровать на следующем тике.

**[S51] 28.05.26:** GAP5 УБИТ. `state_interpreter.py` читает `pain`, `shock_impulse` и `blood_loss` из `body_state`. Боль и шок перекрывают HP. Агония = "тяжело ранен", нокаут = "без сознания". Каузальный мост Физиология → Речь замкнут.

**[S51] 28.05.26:** GAP4 УБИТ. `DirectiveInterpretationSubscriber` ингибируется шоком. `shock > 0.7` → `return []`. Бессознательное тело не подчиняется приказам.

---

### 1.52 S52 [28.05.26] [🟢 ЗАКРЫТ]

**Домены:** 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision) | 6. ПАМЯТЬ И СОЦИУМ (Memory & Social Physics)

**[S52] 28.05.26:** GAP10 УБИТ. `EventContext` обогащён `target_id`. DecisionHub фильтрует бонус `APPROACH` — только целевой NPC получает реакцию на `player_interacts`. Свидетели больше не подходят.

**[S52] 28.05.26:** GAP13 УБИТ. `DirectiveInterpretationSubscriber` больше не хардкодит `fear_of_player`. Если источник приказа — NPC, легитимность вычисляется из `relationship_cache.fear_{source_id}`. Дорога к NPC-to-NPC иерархии открыта.

---

### 1.53 S53 [28.05.26] [🟢 ЗАКРЫТ]

**Домены:** 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision) | 3. ВОСПРИЯТИЕ И ФЕНОМЕНОЛОГИЯ (CFRM & Perception) | 5. ТРУБА ОРКЕСТРАТОРА И ВРЕМЯ (Pipeline & Elastic Time)

**[S53] 28.05.26:** GAP2 УБИТ. Амнезия Воли вылечена. `compute_willpower` читает `trauma_markers`. Каждая травма добавляет +0.1 к `identity_rigidity` (макс +0.3). Предательство закаляет.

**[S53] 28.05.26:** GAP7 УБИТ. Слепота Аватара устранена. `_extract_observer_state` в `LocalCausalSolver` корректно парсит `psyche.fear` для игрока. Аватар получает давление от паники толпы.

**[S53] 28.05.26:** GAP1 УБИТ. Темпоральная асимметрия устранена. Когнитивный Оверлей теперь инжектит критический шок (`shock_impulse > 0.5`) мгновенно (T+0) вместе с директивами. Топор летит со скоростью слова.

---

### 1.54 S54 [26.05.26] [🟢 ЗАКРЫТ]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision) | 4. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat) | 5. ТРУБА ОРКЕСТРАТОРА И ВРЕМЯ (Pipeline & Elastic Time) | 7. ФРОНТЕНД И ПРЕЗЕНТАЦИЯ (UI & Embodiment)

**[S54] GAP11 УБИТ:** Хардкод _MOVE_VERBS удален из npc_tick_pipeline.py. Semantic Bridge замкнут: IntentCompressor теперь распознает "сюда"/"мне" как target_reference='player', пайплайн корректно реагирует на semantic_action=MOVE без текстовых костылей.

**[S54] ADR-084 (The Fool Phase 2):** Убито семантическое смешение EmbodiedVector. Разделены слои: EmbodiedImpulse (моторика), SocialSignal (наблюдаемость), CrowdThreatLevel (угроза для CFRM). Социальная тревога (DISTRESSED) больше не генерирует AVOIDANCE и PREDATOR_ALERT, предотвращая массовую панику толпы от приказа "подойди".

**[S54] 26.05.26:** УБИТ Silent Crash Трубы Воли. `will.py` и `affect.py` обращались к `intent.action`, в то время как DTO содержит `semantic_action` в `parameters`. Добавлен безопасный fallback с приоритетом `parameters.semantic_action`. Воля больше не умирает тихо при `AttributeError`.

**[S54] 26.05.26:** УБИТ `NameError: blood_loss_delta`. `state_applicator.py` использовал переменную без извлечения из `PhysiologyPayload`. Добавлена строка экстракции.

**[S54] 26.05.26:** УБИТ `NoneType finalize_result`. `execute_player_finalize` в `tick_orchestrator.py` не пробрасывал `player_result` в `_TickContext`, из-за чего метод возвращал `None` и крашил пайплайн.

**[S54] 26.05.26:** Труба Эмбодимента ЗАМКНУТА. `will_conflict_data` проверенно доходит от `tick_orchestrator` до `text_input.infect()` на фронтенде. Поле ввода заражается моторным импульсом (например, "Замереть...") при конфликте воли. Словарь `IntentCompressor` расширен приставочными глаголами (выбить, откусить, укусить и т.д.) — Fast Path больше не возвращает `UNCERTAIN` на агрессивные действия.

---

### 1.55 S55 [17.05.26] [🟢 ЗАКРЫТ]

**Домены:** 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision) | 5. ТРУБА ОРКЕСТРАТОРА И ВРЕМЯ (Pipeline & Elastic Time)

**[S55] 17.05.26:** УБИТ Мертвый Вектор Эмоций (ADR-088). `IntentCompressor._fast_path_parse` возвращал `EmotionalVector` с нулями (aggression=0.0), так как не заполнял поле `semantic`. Внедрен маппинг `ActionType -> EmotionalVector` (ATTACK -> aggression=0.8). Воля аватара теперь адекватно сопротивляется агрессии (resistance вырос с 0.15 до ожидаемых значений).

**[S55] 17.05.26:** УБИТ Каузальный Разрыв Spatial Pipe. В `execute_player_finalize` исправлена критическая подмена `campaign_id` на `location_id` при создании `_TickContext`. Ранее `SpatialService.build_for_location` искал граф в `campaigns/tavern_silver_wolf/` (не существует) вместо `campaigns/Open_road/` (где лежит карта), из-за чего пространственный пайплайн молча умирал при ходе игрока.

---

### 1.56 S56 [27.05.26] [⚪ Эволюция]

**Домены:** 7. ФРОНТЕНД И ПРЕЗЕНТАЦИЯ (UI & Embodiment)

**[S56] 27.05.26:** The Fool v2 — визуализация моторных следов (дрожь/замер) и тултипов наблюдений замкнута от бэкенда до экрана. Бэкенд генерирует `embodied_traces` и `peripheral_cues` только на основе наблюдаемых симптомов (`stress_delta`, `psyche_state` -> "Напряженная поза", "Дрожит"). Починена потеря данных: `game_loop_bridge.py` больше не затирает `player_perception` при idle-тиках. Починен рендер: моторные смещения перенесены ДО отрисовки спрайта в `scene_renderer.py`.

---

### 1.57 S57 [30.05.26] [⚪ Эволюция]

**Домены:** 4. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat) | 7. ФРОНТЕНД И ПРЕЗЕНТАЦИЯ (UI & Embodiment)

**[S57] 30.05.26:** RPG Витализм: нормализация шкалы `pain` (0-100 → 0-1) в `StateInterpreter._physical_state_to_word`. Ранее пороги были 0.9/0.6/0.3 (под 0-1), а `StateApplicator` пишет 0-100 — боль никогда не срабатывала. Также оживлён мёртвый `StateInterpreter.interpret()` — метод импортировался, но никогда не вызывался. `VerbalizationContext` обогащён полем `physical_state`. NPC теперь знает свою боль при само-вербализации.

**[S57] 30.05.26:** Удалён дебаг-рендер `[OBS]` из правого верхнего угла экрана (дублировал тултипы без `npc_id`). Создана консоль наблюдений по клавише `Ё` (`pygame.K_BACKQUOTE` + `event.unicode` для русской раскладки) — полупрозрачная панель с `[OBS] npc_id: симптом`. Поддержка `event.unicode` обязательна на Windows.

**[S57] 30.05.26:** DM-агент теперь читает `embodied_traces` из `player_perception` (Фаза 9) и формирует блок "Наблюдаемые симптомы NPC". DM описывает видимые следы (дрожит, покачивается), а не внутренние состояния (pain, fear). Поле `player_perception` легализовано в `PipelineContext`. The Fool: Physiology → Manifestation → Perception → Narrative.

---

### 1.58 S58 [30.05.26] [🔵 ADR]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion)

**[S58] 30.05.26:** Фронтенд: Физика WASD (Push-out Resolution). Игрок больше не застревает между мебелью. Коллизии разрешаются выталкиванием по вектору проникновения. Уменьшен хитбокс (`PLAYER_RADIUS = 0.25`).

**[S58] 30.05.26:** Фронтенд: Контракт рендера препятствий. `scene_renderer.py` теперь читает `x, y` как левый верхний угол (соответствует бэкенду), устраняя визуальный сдвиг хитбоксов мебели.

**[S58] 30.05.26:** Бэкенд: Центроиды узлов графа. `graph_compiler.py` теперь вычисляет центр комнаты (`x + w/2`, `y + h/2`) вместо использования левого верхнего угла. Устранена телепортация NPC в углы стен при FLEE.

**[S58] 30.05.26:** Фронтенд: Уважение TraversalState (ADR-092). Если NPC в статусе `MOVING`, фронтенд не перезаписывает его `local_position` из `npc_positions`, позволяя рендереру плавно интерполировать движение. Устранена массовая телепортация при Action-тиках.

---

### 1.59 S59 [30.05.26] [🟢 ЗАКРЫТ]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | 4. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat) | 5. ТРУБА ОРКЕСТРАТОРА И ВРЕМЯ (Pipeline & Elastic Time) | 7. ФРОНТЕНД И ПРЕЗЕНТАЦИЯ (UI & Embodiment)

**[S59] 30.05.26:** ADR-102: `load_graph()` мёртв — возвращает пустой граф (0 узлов). Заменён на `SpatialService.build_for_location()` в `spatial_runtime.py`. Для работы SpatialService добавлен инжект `campaign_id` в `scene_state` через `get_scene_state()`.

**[S59] 30.05.26:** ADR-102: `spatial_obstacles` теперь передаёт поле `type` (bar, table, chair...) из editor JSON на фронтенд. `scene_renderer.py` маппит типы на спрайты через `sprite_resolver.py` вместо прямоугольных заглушек.

**[S59] 30.05.26:** ADR-102: FLEE-резолв починен. `get_furthest()` теперь принимает `exclude_node_ids` для исключения текущего узла NPC. Нормализация legacy ID (`room_1` → `tavern:room_1`) перед сравнением устраняет бегство NPC в свой же узел.

**[S59] 30.05.26:** Фронтенд: Починен `UnboundLocalError` для `_old_lp` в `game_screen.py:807`. Чтение старой позиции NPC до перезаписи.

**[S59] 30.05.26:** УБИТ Silent Loss Physiology. `state_applicator.py`: `asdict` не импортирован на уровне модуля → краш при `add_injuries` → ВСЯ PhysiologyPayload дельта пропускалась молча (`body_state` никогда не создавался). Фикс: `from dataclasses import asdict` на уровне модуля.

**[S59] 30.05.26:** УБИТ Serialization Black Hole. `NPCState.write_to_legacy()` не писал `body_state` в npc_dict → физиология терялась при каждой сериализации. `NPCStateAdapter.from_legacy()` не читал `body_state` → state.body_state всегда начинался пустым. Фикс: добавлено чтение/запись `body_state` в оба метода.

**[S59] 30.05.26:** УБИТ Rule X Violation. `BehaviorManifestationService._manifest_npc()` читал только `stress_delta` и `psyche_state` из `npc_positions`, полностью игнорируя `body_state` (pain/blood_loss/shock_impulse). Фикс: построение `body_state_map` из `all_npcs_raw`, чтение физиологии для вычисления `locomotion_instability`, `micro_pause_density`, `action_interruption`.

**[S59] 30.05.26:** `StateApplicator._apply_deltas()` — добавлено применение `shock_impulse` к `body_state` (ранее поле существовало в `PhysiologyPayload`, но не экстрактилось и не применялось).

**[S59] 30.05.26:** `PhenomenologyProjectionService` — добавлены cue_keys для боли/крови/шока: WINCING (rigidity+instability), HOLDING_SIDE (micro_pause+rigidity), BLEEDING (micro_pause+instability), STAGGERED (action_interruption).

**[S59] 30.05.26:** `StateApplicator.apply_batch()` — fallback на `"npc_id"` при поиске NPC dict (ранее искал только по `"id"`, что ломало применение дельт для NPC с ключом `"npc_id"`).

**[S59] 30.05.26:** УБИТ Idle Tick Perception Blindness. `_phase_9_integration()` вызывал `produce_traces()` без `all_npcs_raw` → `body_state` всегда `None` в idle тиках → NPC с болью/кровью не проявляли симптомы. Фикс: передача `all_npcs_raw=ctx.all_npcs_raw`.

**[S59] 30.05.26:** Combat → Pain/Blood → UI Pipeline ЗАМКНУТ. 9 фиксов: (1) `asdict` не импортирован на уровне модуля `state_applicator.py` → краш при `add_injuries` → ВСЯ дельта пропускалась; (2) `write_to_legacy` не писал `body_state` обратно в npc_dict → физиология терялась при каждой сериализации; (3) `from_legacy` не читал `body_state` → state.body_state всегда пустой; (4) `BehaviorManifestationService` не читал `body_state` из `all_npcs_raw` (Правило X violation); (5) `apply_batch` fallback на `"npc_id"` при поиске NPC; (6) `PhenomenologyProjectionService` — cue_keys для боли/крови (WINCING/HOLDING_SIDE/BLEEDING/STAGGERED); (7) `StateApplicator` — применение `shock_impulse` к body_state; (8) Idle tick perception не передавал `all_npcs_raw` в `produce_traces()`; (9) `CombatSubscriber` — диагностический `[COMBAT_HANDLE]` лог.

**[S59] 30.05.26:** ADR-102: `spatial_obstacles` пробрасывает `type` (bar, table, chair) из editor JSON на фронтенд. `scene_renderer.py` маппит типы на спрайты через `sprite_resolver.py` вместо прямоугольных заглушек.

**[S59] 30.05.26:** Починен `UnboundLocalError` для `_old_lp` в `game_screen.py`. Чтение старой позиции NPC до перезаписи из `npc_positions`.

---

### 1.60 S60 [31.05.26] [🟢 ЗАКРЫТ]

**Домены:** 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision) | 4. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat) | 5. ТРУБА ОРКЕСТРАТОРА И ВРЕМЯ (Pipeline & Elastic Time) | 7. ФРОНТЕНД И ПРЕЗЕНТАЦИЯ (UI & Embodiment)

**[S60] 31.05.26:** УБИТ `_semantic_action=None` (ADR-091). `publish_classified_player_event` вызывался в `dm_phase.py` ДО `resolve_player_intent()` → `shared_context.intent_resolution` был `None` → ADR-091 override не срабатывал. Фикс: перенос вызова в `__init__.py` ПОСЛЕ установки `intent_resolution`. Runtime верифицирован: `[ADR-091] IntentCompressor override: DM_Router='player_attacks' → IC='attack'`.

**[S60] 31.05.26:** УБИТ Memory Black Hole. `_legacy_d = LegacyStateDeltaAdapter.collapse()` определена внутри `elif` (стр.144), но читалась в другом `elif` (стр.152) → `UnboundLocalError` → `[MEMORY] apply failed` для 6/6 NPC каждый тик. Память была полностью мертва. Фикс: вынесено до ветвления.

**[S60] 31.05.26:** УБИТ Shock Immortality. `shock_impulse` не затухал между тиками (0.9→0.9→0.9 бесконечно). 4 файла: (1) `NPCStateSnapshot` — добавлено поле `shock_impulse`; (2) `_build_npc_snapshots` — извлечение из `body_state`; (3) `PhysiologyDecayHandler` — leaky integrator `SHOCK_DECAY_LAMBDA=0.08` (~8% за тик); (4) `StateApplicator` — разрешена отрицательная дельта `shock_impulse != 0.0` вместо `> 0.0`. Runtime верифицирован: shock=0.6→0.55→0.51.

**[S60] 31.05.26:** Combat pipeline верифицирован end-to-end: `PLAYER_ATTACKED → CombatSubscriber → ImpactEngine(2 deltas) → _aggregate_deltas(PHYSICS_COMPOSITE) → apply_batch → body_state(pain=36→34→48→59)`. Print-диагностика конвертирована в `logger.debug`.

**[S60] 31.05.26:** ДИАГНОСТИКА: StateInterpreter Ownership Audit (ADR-104). Обнаружено: `UrgencyLevel` (SCARED/PANIC/BROKEN) дублирует `EmotionTag` (fearful/panic) — два владельца одной концепции. Трассировка показала: `NPCStateDescription.emotional_state` (из UrgencyLevel) — мёртвое поле, не читается ни одним сервисом. `VerbalizationContext.emotion` и `emotional_nuance` — dormant (потребитель не найден, но статус unresolved). `PhysicalState` (из body_state) — живой и легитимный. Double Truth не проявляется в runtime (нет потребителя), но архитектурный долг существует. Зафиксировано в `architecture/physiology.yaml`.

**[S60] 31.05.26:** УБИТ `UnboundLocalError: _legacy_d`. В `npc_tick_pipeline.py:144` дублирующий вызов `LegacyStateDeltaAdapter.collapse()` внутри `elif` — переменная `_legacy_d` определялась повторно. Удалён дубль, верхнее вычисление (строка 139) уже корректно.

**[S60] 31.05.26:** УБИТ `TypeError: non-default argument`. `VerbalizationContext.intent_target: Optional[str]` без `= None` — мина замедленного действия. Добавлен дефолт. `physical_state` дефолт заменён с `"невредим"` на `"unharmed"` (L10n-safe).

**[S60] 01.06.26:** 4 фикса pipeline: (1) `_legacy_d` UnboundLocalError в `state_applicator.py` — переменная определена внутри `elif`, но читалась в другом → память мертва для 6/6 NPC; (2) Combat pipeline = 0 результатов — `CombatSubscriber` не получал events; (3) Pain не персистится — `body_state` терялся между тиками; (4) `shock_impulse` не затухает — `NPCStateSnapshot` без поля `shock_impulse`, `PhysiologyDecayHandler` без decay lambda, `StateApplicator` блокировал отрицательные дельты условием `> 0.0` вместо `!= 0.0`. Диагностические следы конвертированы в `logger.debug` (ADR-111).

---

### 1.61 S61 [02.06.26] [🟢 ЗАКРЫТ]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | 4. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat) | 5. ТРУБА ОРКЕСТРАТОРА И ВРЕМЯ (Pipeline & Elastic Time) | 7. ФРОНТЕНД И ПРЕЗЕНТАЦИЯ (UI & Embodiment)

**[S61] 02.06.26:** ADR-114: Spatial Paralysis убит. `graph_compiler.py` не создавал role-based алиасов — legacy-имена (`main_hall`, `bed`, `bar_area`) из NPC schedule не резолвились в канонические ID графа → `SpatialService.get_node()` возвращал `None` → NPC замирали. Добавлены: (1) name-aliases из поля `name` комнаты; (2) role-based legacy aliases (`ENTRANCE→entrance`, `BAR→bar_area`, `BED→bed` и т.д.). Verif: `thief_shadow: from=room_0 to=room_1` ✅.
- ❌ `graph_compiler.py` без role-based aliases — legacy-имена не резолвятся → Spatial Paralysis (ADR-114).

**[S61] 02.06.26:** ADR-112: Semantic Inflation убит. `BehaviorManifestationService` и `PhenomenologyProjectionService` читали `stress_delta`/`psyche_state` (эмоции) вместо `body_state` (физиология) — все NPC дрожали одинаково (`instab=0.67 rigid=0.80`). Атмосфера вычислялась из `stress_delta` — социальная волна делала всех "тревожными". Фикс: оба сервиса переведены на чтение ТОЛЬКО `body_state` (pain/shock_impulse/blood_loss/fatigue). Атмосфера из доли NPC с моторными симптомами. Verif: `maid_lusya: instab=0.00 rigid=0.00`, `thief_shadow: instab=0.82 rigid=0.51`.
- ❌ `BehaviorManifestationService`/`PhenomenologyProjectionService` читают `stress_delta`/`psyche_state` для моторных искажений и атмосферы — Semantic Inflation (ADR-112, Rule 28).

**[S61] 02.06.26:** ADR-113: LLM Resilience. 3 retry + exponential backoff (1s/2s/2s) в `llama_cpp_provider.py` при ConnectionReset/OSError/Timeout. Partial stream recovery (>20 chars). Честная системная ошибка вместо фейкового нарратива — `agent_runner.py` возвращает `{"error": True, ...}`, вызывающий код показывает `[СИСТЕМА: LLM сервер недоступен]`. Фейковый нарратив = каузальное мошенничество (§ENIGMA-001).

**[S61] 02.06.26:** BUG W (КРИТИЧЕСКИЙ): FLEE Intent терялся бесследно. `NameError: name 'PRIORITY_NEEDS' is not defined` в `_resolve_reactive_movement()` — импорт `PRIORITY_NEEDS` был внутри `run_npc_pipeline()` (локальная переменная), а `_resolve_reactive_movement()` — отдельная функция модуля. Exception глотался `try/except` → FLEE intent терялся. Фикс: заменён на `PRIORITY_REACTIVE` (импорт уже существовал на уровне функции). Файлы: `npc_tick_pipeline.py:790,816,834,849`.

**[S61] 02.06.26:** BUG X: NameError в `DecisionHub._context_relevance` — левый диагностический print ссылался на `state.npc_id` (переменная не в scope). Удалён print. Файл: `decision_hub.py:882`.

**[S61] 02.06.26:** 3 фикса: (1) Semantic Inflation убит — `BehaviorManifestationService` и `PhenomenologyProjectionService` читали `stress_delta`/`psyche_state` (эмоции) вместо `body_state` (физиология). Все NPC дрожали одинаково. Rule X (ADR-101) enforcement: моторика ТОЛЬКО из body_state, атмосфера ТОЛЬКО из доли NPC с моторными симптомами (ADR-112); (2) LLM Resilience — 3 retry + exponential backoff (1s/2s/2s) при ConnectionReset/OSError/Timeout. Partial stream recovery (>20 chars). Честная системная ошибка вместо фейкового нарратива при permanent failure (ADR-113); (3) Spatial Paralysis — `graph_compiler.py` не создавал role-based алиасов. Legacy-имена (`main_hall`, `bed`) не резолвились в канонические ID графа → NPC получали "node not found" и замирали. Добавлены name-aliases и role-based aliases (ADR-114).

---

### 1.62 S62 [03.06.26] [🟢 ЗАКРЫТ]

**Домены:** 3. ВОСПРИЯТИЕ И ФЕНОМЕНОЛОГИЯ (CFRM & Perception)

**[S62] 03.06.26:** DOUBLE TRUTH `threat_gradient` УБИТ. `NPCState.write_to_legacy()` не писал `perceptual_kernel` в npc_dict → `threat_gradient`, `initiative_suppression`, `compliance_bias` и др. сбрасывались в 0.0 каждый тик. `NPCStateAdapter.from_legacy()` не читал `perceptual_kernel` и `affective_load` → каждый тик создавал NPCState с нулями. LifeEngine, DecisionHub, TickOrchestrator видели всегда 0.00 — guards "мёртвые", эмоции не накапливаются. Фикс: (1) `write_to_legacy` — сериализация всех 10 полей PerceptualKernel + affective_load в npc_dict; (2) `from_legacy` — десериализация через `_pk_from_dict()` + чтение affective_load; (3) helper `_pk_from_dict()` для безопасного конструирования. Runtime верифицирован: fear 0.537→0.556→0.590→0.590 (монотонный рост + персистенция).

**[S62] 03.06.26:** ОБНАРУЖЕН разрыв `emotion: 0.0`. Компонент `emotion` в DecisionHub всегда 0.0 — аффективный аккумулятор (`affective_load` через `integrate_affective_pressure`) не доходит до utility scoring. DOUBLE TRUTH мост починен, но трубопровод `affective_load → emotion_component` разорван. Требует отдельной диагностики.

---

### 1.63 S63 [???] [🟢 ЗАКРЫТ]

**Домены:** 9. SOCIAL & AFFECTIVE ARCHITECTURE (SSOT & CAUSAL DERIVATION)

**[S63] ADR-116: Emotion Pipeline完整性修复 (emotion: 0.0 → FEARFUL/SUSPICIOUS):**
  (1) `load_l2_state_from_runtime_dict()` (npc_loader.py) — добавлены 5 полей в конструктор `NPCState`: `emotion`, `emotion_delta`, `affective_load`, `body_state`, `perceptual_kernel`. Без этого `DecisionHub` получал `emotion=NEUTRAL` каждый тик → `_emotion_modifier()=0.0`.
  (2) `npc_state.py` — `write_to_legacy()`/`from_legacy()` теперь сериализуют/десериализуют `emotion` и `emotion_delta` (через хелпер `_emotion_from_str()`).
  (3) `state_applicator.py` — TAG MISMATCH фикс: pipeline генерирует "fear/panic/rage", а `EmotionTag` ожидает "fearful/angry". Конвертация через `_emotion_from_str()`.
  (4) `tick_orchestrator.py` — BROKEN PSYCHE PATH фикс: `npc_raw.get("psyche", {}).get("drives_base", {})` всегда возвращал `{}`. Исправлено на `npc_raw.get("drives", {})` для fear.
  (5) `reaction_subscriber.py` — EMPTY perceiving_ids FALLBACK: пустой список `[]` теперь fallback на всех NPC (раньше означал "никто не видит" → 0 эмоций).
  (6) `reaction_subscriber.py` — EMOTION FROM STRESS: добавлены пороги stress_delta≥15→"fear", ≥8→"anxious" (раньше только shock>0.5).
  (7) `tick_orchestrator.py` — SUSTAINING EMOTION: если `affective_load > threshold` но `emotion=NEUTRAL`, эмоция устанавливается принудительно (sustain check).
  (8) `game_loop/__init__.py` — удалён дублирующий вызов `update_cache`, который перезаписывал кэш с neutral.
  (9) Очистка: временные диагностические `print()` и `logger.warning` понижены до `logger.debug` в 11 файлах.

---

### 1.64 S64 [03.06.26] [🟢 ЗАКРЫТ]

**Домены:** 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision)

**[S64] 03.06.26:** УБИТ PHYSICS_OF_POWER NameError. `_context_relevance(self, intent, event)` не имел параметров `state` и `personality`, но код ADR-036 обращался к `state.npc_id` и `personality.drives_base`. При idle-тике (MOVE=False) NameError не возникал; при команде MOVE — краш → try/except глотал. Фикс: добавлены параметры `state` и `personality` в `_context_relevance` и `_drive_relevance`, проброс из `_score_components`.

**[S64] 03.06.26:** УБИТ DOUBLE TRUTH в relationship_cache. PHYSICS_OF_POWER читал `state.relationship_cache.get("player", {}).get("fear") / 100.0`, но структура кэша = `{"fear": 0.0-1.0, "trust": ...}`, без вложенного `"player"`. Результат: fear=0.0, obedience_pressure=0.0. Фикс: `state.relationship_cache.get("fear", 0.0)` — как в `_score_components`.

**[S64] 03.06.26:** PHYSICS_OF_POWER перенесён из `_context_relevance` в `compute()`. В `_context_relevance` boost размывался через drive_weight (APPROACH drive="desire" ≈0.25), итоговый boost ≈0.675 проигрывал OBSERVE (fear×0.40 напрямую). В `compute()` boost добавляется напрямую к `scores[APPROACH]`. Runtime верифицирован: approach_score=2.124, NPC подходит к игроку.

**[S64] 03.06.26:** УБИТ `'GameLoop' object has no attribute '_get_life_engine'`. `GameLoop._load_npcs_with_runtime()` вызывал `self._get_life_engine()`, но метод существовал только в `TickOrchestrator`. Pipeline крашился до ARCHAE-ORCH, ошибка глоталась try/except. Фикс: добавлен делегат `GameLoop._get_life_engine() → self._tick_orch._get_life_engine()`.

**[S64] 03.06.26:** УБИТ avatar KeyError 'id'. `_avatar_dict` (ADR-O-112) имел `npc_id: "player"`, но `load_profile_from_legacy_json` требует ключ `id`. Idle tick крашился. Фикс: добавлено `_avatar_dict["id"] = "player"`.

---

### 1.65 S65 [04.06.26] [⚪ Эволюция]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | 5. ТРУБА ОРКЕСТРАТОРА И ВРЕМЯ (Pipeline & Elastic Time) | 8. НАБЛЮДАЕМОСТЬ И ДИАГНОСТИКА (CDS)

**[S65] 04.06.26:** Инвариант 2 Запечатан: LLM не может галлюцинировать движение. (1) `VerbalizationContext` обогащён `is_moving: bool` и `movement_intent: str` — NPC-specific LLM знает статус движения. (2) `npc_tick_pipeline.py` вычисляет `is_moving` из intent (APPROACH/FLEE/RETREAT/FOLLOW/PATROL) + `can_move`. (3) `dm_agent.py` — при отсутствии `npc_movement_summary` в DM контракт инжектится явный запрет: "ЗАПРЕЩЕНО описывать приближение, отход или любое изменение позиции NPC". Causal Contract §2.4 enforcement.

**[S65] 04.06.26:** Инвариант 1 Запечатан: Вычисление > Декларация. (1) `_RUNTIME_TOP_LEVEL_KEYS` в `npc_loader.py` обогащён: `affective_load`, `emotion`, `emotion_delta`, `body_state`, `perceptual_kernel`, `narrative_cache` — runtime overlay больше не затирает вычисленные поля статикой из config. (2) `_load_npcs_with_runtime` в `game_loop/__init__.py` — после чтения с диска немедленно праймит LifeEngine cache через `engine.update_cache()`. Убита Ошибка C (двойная загрузка L2) и Ошибка A (DOUBLE TRUTH при affective_load=0.0).

**[S65] 04.06.26:** Инвариант 3 Запечатан: Наблюдаемость отказа. (1) `pattern_registry.py` — 5 новых паттернов: `pipeline_critical`, `causality_crash`, `phase8_crash`, `tick_orch_error`, `affect_decay_fail`. (2) `tick_health.py` — 5 новых счётчиков + предупреждения о пред-шинных отказах. (3) `causal_observer.py` — диспетчеризация новых паттернов. (4) `tick_orchestrator.py` — `logger.debug` → `logger.warning` для `[AFFECT_DECAY]`; `print()` → структурированный `[PIPELINE][CRITICAL]` / `[PHASE8_CRASH]`. (5) `dna_metrics.py` — PFI (Pre-Bus Failure Index) в DNA: `prebus_failures`, `affect_decay_fails`, интерпретация, рендер в LAST_SESSION.md.

---

### 1.66 S66 [???] [🟢 ЗАКРЫТ]

**Домены:** 9. SOCIAL & AFFECTIVE ARCHITECTURE (SSOT & CAUSAL DERIVATION)

**[S66] Архитектурный фикс DOUBLE TRUTH:**
  (1) `RelationshipStore` назначен Единственным Источником Истины (SSOT) для всех социальных связей. Масштаб хранения: 0-100.
  (2) `NPCState.relationship_cache` переведён в статус эфемерного read-кэша (заполняется на начале тика из SSOT, НЕ сериализуется в `from_legacy`/`write_to_legacy`).
  (3) `DecisionHub` и `DirectiveInterpretationSubscriber` читают `relationship_cache["player"]["fear"]` (вложенный формат) и нормализуют 0-100 → 0-1 на границе чтения.
  (4) `MemoryManager.get_weights_for_decision` нормализует 0-100 → 0-1 перед инжектом в кэш.
  (5) Устранена инверсия P2: `trust=0.9` больше не драйвит бегство, так как масштабы приведены к единым 0-1.

**[S66] Каузальная рекомбинация Affective Load:**
  (1) Уничтожена "магическая батарейка" `affective_load` с независимым decay.
  (2) `affective_load` теперь — производная величина: `Σ(active_causes) = threat*0.6 + uncertainty*0.3 + anomaly*0.1 + pain*0.3 + shock*0.4`.
  (3) Пересчитывается в `StateApplicator` при применении `PerceptionPayload` и `PhysiologyPayload`.
  (4) Добавлен decay для `PerceptualKernel` (threat/uncertainty/anomaly) в `PhysiologyDecayHandler`. Причины затухают, если нет новых стимулов.

**[S66] Убран диагностический шум (P0):**
  Все `print(f"[ARCHAE-*]")`, `print(f"[DIAG_*]")`, `print(f"[PHYSICS_OF_POWER]")` переведены на `logger.debug`.

**[SESS_66] 2026-06-XX: Vital State & Injury-Physiology Bridge (ADR-123)**

### Добавлено
- `domain/vital_state.py` — LifeStatus enum, evaluate_vital_state(), is_conscious(), is_capable(). Три оси оценки организма вместо одного enum.
- `services/combat/injury_processor.py` — InjuryProcessor (IdleTickHandler). Мост Injury → Physiology. Кровотечение из свойств ран, не из строковых флагов.
- Регистрация InjuryProcessor в game_loop/__init__.py перед DecayHandler.
- StateApplicator: оценка vital_state после PHYSIOLOGY domain, запись body_state["life_status"].
- DecisionHub: guard в начале compute() — DEAD/UNCONSCIOUS → IDLE.

### Удалено (архитектурно)
- `hp <= 0` как источник смерти (combat_math.apply_damage — мёртвый код, никто не вызывает).

### Примечания
- Переходный слой: смерть только от кровопотери. Фантомная онтология запрещена.
- TODO: перенести vital_state evaluation в end-of-tick reconciliation.
- TODO: perception_filter._npc_is_conscious и scene_state_manager pos.get("state")=="dead" ещё не обновлены.

---

---

### 1.67 S67 [2026-06-05] [🟢 ЗАКРЫТ]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | 4. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat) | 5. ТРУБА ОРКЕСТРАТОРА И ВРЕМЯ (Pipeline & Elastic Time)

**[S67] 04.06.26:** ADR-121: Двухслойная топология в graph_compiler. `nodes` (dict) — навигационная топология (точки пути + связи), `rooms` (list) — физические контейнеры (bounding boxes). Оба слоя существуют одновременно и компилируются параллельно. Ни один слой не деградирует при наличии другого.rooms→orphan rooms добавляются как навигационные узлы (обратная совместимость). Per-node `connections` используются как связи при `_has_nav`. Убита `UnboundLocalError` — `_ROLE_LEGACY_ALIASES` вынесен в модульную константу. Verif: `bar_area→tavern_silver_wolf:bar_area`, `behind_bar→tavern_silver_wolf:behind_bar`, 7 узлов вместо 3.

**[S67] 04.06.26:** P0-B Spatial Perception Spine. `PipelineContext` обогащён полем `spatial_query: Any = None`. `game_loop/__init__.py` инжектит `SpatialQueryService(npc_positions, scene_state)` в `shared_context.spatial_query` после сборки `scene_state`. Без этого `perception_filter.py` получал `spatial_query=None` → `_npc_distance()=999.0` → все NPC слепы → `filter_perceiving_npcs()=[]` → `_get_perceiving_ids()` fallback ALL → ReactionSubscriber получает ALL NPC → эмоциональный каскад (ALL=ATTACK).

**[S67] 04.06.26:** (0,0) Телепортация убита. `_enrich_local_positions` — fallback с `(0.0, 0.0)` заменён на graph-aware fallback: 1) начальный узел NPC из npc_defaults, 2) entrance, 3) первый доступный узел графа. (0,0) только если граф полностью пуст (критическая ошибка графа). NPC больше не телепортируются за пределы карты.

**[S67] 04.06.26:** ADR-121 Data: Полная синхронизация трёх источников пространственной истины. (1) `tavern.json`: добавлен узел `right_table`, связь `kitchen→main_hall`, NPC позиции (blacksmith_orm, thief_shadow, merchant_goran) сдвинуты в главный зал — `_nearest_node_to_xy()` больше не маппит NPC в kitchen. (2) `location_templates.json`: координаты обновлены с относительных (0,0) на абсолютные (8.0, 7.0), добавлены fireplace/kitchen/right_table, 6 NPC defaults вместо 3, guard_borko/merchant_goran убраны из city_gate/market_square. (3) `_builtin_templates()`: npc_defaults обновлены до 6 NPC, city_gate/market_square defaults очищены. Верификация: 0 NPC маппятся в kitchen, 8 узлов графа, полностью связный.

**[S67] 05.06.26:** КРИТИЧЕСКИЙ NameError в `evaluate_vital_state`. `vital_state.py` не имел `import logging` на уровне модуля → `logger` не определён → `NameError` при каждом вызове evaluator → `_apply_deltas` крашилась после VITAL_PRE → `write_to_legacy` НИКОГДА не вызывалась → body_state НЕ записывался в npc_dict. Фикс: добавлен `import logging; logger = logging.getLogger(__name__)`.

**[S67] 05.06.26:** ADR-124 DEATH LOCK: Смерть — иммутабельный факт, не транзиентная метка. Три слоя инварианта: (1) `evaluate_vital_state` — если `life_status == "DEAD"`, возвращает DEAD немедленно (первая проверка); (2) `NPCStateSnapshot.life_status` — decay handler видит смерть и пропускает мёртвых; (3) `PhysiologyDecayHandler` — труп не выздоравливает. Причина: decay снижал blood_loss/pain/shock для мёртвых NPC → evaluator пересчитывал смерть с нуля → воскрешал. Runtime верифицировано: 0 реинкарнаций за 5 тиков decay.

**[S67] 05.06.26:** Rule 44 fix: `if state.body_state:` → `if state.body_state is not None:` в `write_to_legacy`. Пустой dict `{}` = здоровое тело, не "нет тела". Falsy check стирал физиологию при каждой сериализации.

**[S67] 05.06.26:** Rule 47 fix: `_sem_payload` Scoping Trap в `dm_phase.py`. Переменная определялась внутри `if dm_result.is_valid and dm_result.scene_context:`, но читалась выше → `UnboundLocalError` → краш DM-фазы через 4-5 тиков. Фикс: инициализация `_sem_payload = {}` наверх функции.

**[S67] 05.06.26:** `NPCStateSnapshot` обогащён полем `life_status: str` (ADR-124). `_build_npc_snapshots` проецирует `body_state.life_status` в снапшот. Без этого `PhysiologyDecayHandler` не мог проверить смерть.

**[S67] 05.06.26:** Гипотеза H1 из ТЗ ОПРОВЕРГНУТА: `PHYSICS_COMPOSITE` НЕ обходит `apply_batch`. `_aggregate_deltas` пропускает `physics_deltas` через `list(groups.values()) + physics_deltas` (строка 1643).

**[S67] 05.06.26:** Дублирующий DEATH LOCK убран из `evaluate_vital_state`. DEATH LOCK — теперь ПЕРВАЯ проверка (до blood_loss и structural).

**[S67] 05.06.26:** death_cause TODO слоты добавлены в `evaluate_vital_state`: HEMORRHAGIC (reversibility=0.3) и STRUCTURAL (reversibility=0.05). Подготовка для будущей DeathState (каузальная классификация смерти).

**[S67] 05.06.26:** Rule 47 fix в `dm_phase.py`: `_sem_payload = {}` вынесен наверх функции. Python Scoping Trap — переменная определена внутри `if`, читалась снаружи → `UnboundLocalError` → краш DM-фазы после 4-5 тиков.

**[SESS_67-68] 2026-06-05: Causal Connectivity Restoration (ADR-121→124)**

### Добавлено

**ADR-121 — RelationshipStore = SSOT:**
- `RelationshipStore` назначен единственным источником истины для социальных связей, масштаб 0-100.
- `NPCState.relationship_cache` = эфемерный read-кэш, НЕ сериализуется в `from_legacy`/`write_to_legacy`.
- `DecisionHub` и `DirectiveInterpretationSubscriber` нормализуют 0-100 → 0-1 на границе чтения.

**ADR-122 — affective_load = Σ(active_causes):**
- Уничтожена "магическая батарейка" с независимым decay.
- Формула: `min(1.0, threat*0.6 + uncertainty*0.3 + anomaly*0.1 + pain/100*0.3 + shock*0.4)`.
- Пересчитывается в `StateApplicator` при Physiology и Perception дельтах.
- `_run_affective_pipeline` пересчитывает load из PK + body_state вместо stale `npc_raw.get("affective_load")`.
- Decay для `PerceptualKernel` (threat/uncertainty/anomaly) в `PhysiologyDecayHandler`.

**ADR-123 — Combat → Perception мост:**
- `ReactionSubscriber` генерирует `PerceptionPayload(threat_gradient_delta)` для свидетелей насилия.
- Шок от удара → `min(0.5, shock * 2.0)`. Свидетельство насилия → `0.3 * intensity`.
- `PerceptionPayload` добавлен в модульный импорт reaction_subscriber.py.

**ADR-124 — EventContext.target_id инжект:**
- `shared_context.player_target_id` инжектируется в `EventContext.target_id` в `dm_phase.py`.
- DecisionHub `_is_target` фильтр теперь работает: цель атаки → self_defense, свидетели → FLEE.
- `_sem_payload` также получает `target_id` из PlayerTargetExtractor.

**Self-defense target filter (DecisionHub):**
- `_is_violence` + `self_defense` boost → ТОЛЬКО для `event.target_id == state.npc_id`.
- Свидетели насилия получают FLEE boost вместо ATTACK.
- proximity_violence: свидетели → FLEE/WARN boost, ATTACK не бонусируется.

**Scoping Trap фиксы:**
- `graph_compiler.py`: удалён локальный дубликат `_ROLE_LEGACY_ALIASES`, `NodeRole.MARKET` добавлен в модульную константу.
- `reaction_subscriber.py`: `PerceptionPayload` поднят в модульный импорт, удалён локальный `from app.models.delta_payloads import`.

**Диагностический шум (P0):**
- Все `print(f"[ARCHAE-*]")`, `print(f"[DIAG_*}")`, `print(f"[PHYSICS_OF_POWER}")` переведены на `logger.debug`.

### Удалено
- Локальное переопределение `_ROLE_LEGACY_ALIASES` внутри `compile_graph()` (shadowing UnboundLocalError).
- Локальный `from app.models.delta_payloads import PerceptionPayload` внутри `ReactionSubscriber.handle()` (shadowing UnboundLocalError).
- Глобальный ATTACK boost для свидетелей насилия в DecisionHub (массовая агрессия ALL NPC).

### Runtime верификация
- Ударить Торнина → Торнин (цель) ATTACK, все остальные FLEE ✅
- stress ≠ 0.0 после боя (maid_lusya=6.1, guard_borko=0.5) ✅
- 18 deltas от ReactionSubscriber (было 12) — 6 PerceptionPayload добавлено ✅
- affective_load пересчитывается из PK + body_state ✅
- Граф компилируется без UnboundLocalError ✅

### Примечания
- `_resolve_target_reference()` всё ещё не резолвит падежи (cutoff=0.6). ADR-124 обходит через `shared_context.player_target_id`, но `IntentParametersDTO.target_id` остаётся пустым.
- `PerceptualKernel` = Gen 2 (эмоциональный след). Gen 3 (`perceive_world()`) — архитектурный долг.
- ENIGMA Scope Rule: все семантические определения (roles, delta types, intent maps) должны быть module-level singletons. Локальные переопределения = UnboundLocalError.

---

### 1.68 S68 [05.06.26] [🟢 ЗАКРЫТ]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision)

**[S68] 05.06.26:** ADR-125: Target ID SSOT Clarification. Обнаружена незавершённая миграция архитектуры разрешения целей. `IntentParametersDTO.target_id` (от слепого fuzzy matching) оказался архитектурно мёртв — система работает через `PlayerTargetExtractor` → `shared_context` → `intent.target` → ADR-124. Фикс: `tick_orchestrator` переключён на чтение из `intent.target`. Поле DTO задепрекировано, но сохранено как диагностический маркер расхождения алгоритмов. Ампутация поля и ADR-124 отложены до S70.

**[S68] 05.06.26:** ДИАГНОСТИКА S68: Архитектурный аудит пайплайна.
  - **P1 (Decay Tuning):** ЗАКРЫТ. Система экспоненциального затухания (`PERCEPTUAL_DECAY_LAMBDA = 0.05`) находится в состоянии балансировки с физиологией. Это не настройка, а физика мира. Изменение лямбды без изменения онтологии потребления = сдвиг физики.
  - **P2 (Emotion→Language Bridge):** РЕКЛАССИФИЦИРОВАН. `UrgencyLevel` и `CommunicationIntent.emotional_state` — не мёртвый код, а фантомные контракты (недостроенные мосты). Реальный мост вербализации идёт через `VerbalStance`. Удаление отложено.
  - **P3 (Observer Collapse Bug):** ОБНАРУЖЕН КРИТИЧЕСКИЙ РАЗРЫВ. `RelationshipStore` хранит полный граф связей, но `relationship_cache` в пайплайне собирается как star schema (только `NPC→Player`). NPC→NPC причинность (иерархии, страх, подчинение) мертва в рантайме. Требует расширения проекции кэша в S69 (Вариант A).

**[S68] 05.06.26:** CEI (Constraint Enforcement Injection) — три точки принудительной пространственной валидации. (1) CEI-1: micro_flee — binary search вдоль луча до стены/мебели, fallback на центроид узла. (2) CEI-2: traversal creation — `is_movement_blocked()` проверяет стены + мебель (passability.walk=False). При блокировке — A* routing через intermediate nodes. 2-node path при blocked=True = отмена traversal. (3) CEI-2b/3a/3b: tick-based multi-waypoint интерполяция (backend+frontend), smart merge вместо replace для action path, fallback chain вместо (0,0). (4) `@property` на `AgentAction.intent_target` — устранена подмена строки bound method. (5) Новая функция `is_movement_blocked()` — разделяет LOS и проходимость. Стол блокирует движение, но не обзор. (6) КРИТИЧЕСКИЙ РАЗРЫВ: `active_traversals` не пробрасывался через WorldSnapshotBuilder → фронтенд не получал данные о движении. Починено: Dict формат + полный waypoints + tick sync. (7) Tick-Scoped Identity Cache — `lock_for_tick()` возвращает один и тот же dict внутри тика. `save_scene_state()` no-op внутри lock. (8) Frontend tick sync — `scene_state["tick"]` обновляется из world_snapshot. Без этого `_resolve_visual_xy` всегда видел progress=0. (9) `@property`+`@staticmethod` конфликт на `_get_rel_value` — убивает доступ к методу. Фикс: только `@staticmethod`. (10) `PerceptionPayload` не импортирован — краш Phase 9. (11) КРИТИЧЕСКИЙ АРХИТЕКТУРНЫЙ РАЗРЫВ: SceneStateManager — stateless service с кэшем. `get_scene_state()` создаёт НОВЫЙ dict при каждом вызове вне lock. Требует Scene Runtime Kernel (3-слойная модель: Canonical/Runtime/Snapshot).

**[S68] 05.06.26:** ADR-125: Target ID SSOT Clarification. Обнаружена незавершённая миграция архитектуры разрешения целей. `IntentParametersDTO.target_id` (от слепого fuzzy matching) оказался архитектурно мёртв — система работает через `PlayerTargetExtractor` → `shared_context` → `intent.target` → ADR-124. Фикс: `tick_orchestrator` переключён на чтение из `intent.target`. Поле DTO задепрекировано, но сохранено как диагностический маркер расхождения алгоритмов. Ампутация поля и ADR-124 отложены до S69.

---

### 1.69 S69 [06.06.26] [🟢 ЗАКРЫТ]

**Домены:** 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion) | 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision)

**[S69] 06.06.26:** Ontology Merge Step 1: Relationship Cache Precedence Contract. Обнаружена бифуркация онтологий в `DecisionHub`: чтение `relationship_cache` вело себя непредсказуемо (Graph Model `get("player", {}).get("fear")` vs Scalar Model `get("fear")`). Скалярная модель всегда возвращала 0.0, генерируя социальные дельты из вакуума. Фикс: внедрён унифицированный accessor `_get_rel_value` с политикой Graph > Scalar > Vacuum. Архитектурный долг: DecisionHub временно стал ontology resolver, что создаёт риск False Consistency. Требуется вынос резолва в Epistemic State Layer (S70).

**[S69] 06.06.26:** Ontology Merge Step 2: Observer Collapse Bug Fix. `relationship_cache` в `npc_tick_pipeline` собирался как Star Schema (только `NPC→Player`), делая NPC→NPC социальную физику невозможной. Фикс: кэш расширен до Partial Social Graph — загрузка весов для всех `nearby_npcs` из `RelationshipStore`. Система перешла от Player-Centric модели к Multi-Agent Topology. Риск O(N²) ограничен пространственным фильтром (K nearby). Асимметрия восприятия (A видит B, B не видит A) зафиксирована как фича (The Fool), а не баг.

**[S69] 06.06.26:** Ontology Merge Step 1: Relationship Cache Precedence Contract. Обнаружена бифуркация онтологий в `DecisionHub`: чтение `relationship_cache` вело себя непредсказуемо (Graph Model `get("player", {}).get("fear")` vs Scalar Model `get("fear")`). Скалярная модель всегда возвращала 0.0, генерируя социальные дельты из вакуума. Фикс: внедрён унифицированный accessor `_get_rel_value` с политикой Graph > Scalar > Vacuum. Архитектурный долг: DecisionHub временно стал ontology resolver, что создаёт риск False Consistency. Требуется вынос резолва в State Normalization Layer (S70).

---

### 1.71 S71 [06.06.26] [🟢 ЗАКРЫТ]

**Домены:** 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision)

**[S71] 06.06.26:** §ENIGMA-S72 Закон Релятивистского Восприятия. Система перешла от централизованной интерпретации (движок решает, что значат события) к распределённой (личность решает). Пять хирургических разрезов: (1) A1 — убит глобальный коллапс Vacuum→stress в `legacy_delta_adapter.py` (uncertainty×5.0→stress_delta); (2) I1 — CFRM лишён права интерпретации, фиксированные множители (×40/×20) удалены, `dominant_emotion_hint` = None, движок = сырой сенсор; (3) I2 — веса affective_load из `drives_base` (fear→threat, control→uncertainty, significance→anomaly), а не хардкод 0.6/0.3/0.1; (4) I3 — DecisionHub._context_relevance модулируется через drives_base (fear→насилие, control→кража, significance→свидетели, desire→диалог), хардкод +0.5/+0.7/+0.2 убит; (5) S72 Completion — `_emotion_modifier` персонализирован через drives_base: эмоция = энергия, личность = направление разрядки. Controller при страхе атакует (+0.125), coward бежит (+0.445). Дополнительно: порог тревоги (THRESHOLD_ANXIOUS) персонализирован через fear_drive+willpower, как и страх/паника. `emotion_resolution.py` — мёртвый код (нет импортов).

---


## 2. АГРЕГИРОВАННЫЕ АРХИТЕКТУРНЫЕ ЗАПРЕТЫ

> **Правило:** Этот раздел = сводный каталог ВСЕХ запретов из всех сессий.
> **Использование:** Перед изменением кода — проверь, не нарушаешь ли ты существующий запрет.

### 2.1 Пространство и Движение

- ❌ LLM описывает движение NPC без подтверждения от MovementEngine (Инвариант 2: Нарратив ≠ Физика).
- ❌ Прямая мутация `npc["position"]` или `npc["location"]`.
- ❌ Чтение дистанций из `scene_state` (только через `SpatialQueryService`).
- ❌ Использование `TraversalState` без `MovementEngine`.
- ❌ Повторная обработка `MovementIntent` (инвариант `processed=True`).
- ❌ `_enrich_local_positions` перетирает `local_position`, установленный пайплайном (LOD0 guard).
- ❌ Использование `load_graph()` — мёртвый код, возвращает пустой граф. Заменён на `SpatialService.build_for_location()` (ADR-102).
- ❌ Сравнение legacy ID (`room_1`) с canonical ID (`tavern:room_1`) без нормализации через `spatial_service.normalize_id()`.
- ❌ `graph_compiler.py` без role-based aliases — legacy-имена не резолвятся → Spatial Paralysis (ADR-114).
- ❌ `DirectiveInterpretationSubscriber` генерирует `MovementIntent`.
- ❌ Перезапись `result.world_snapshot` целиком в `game_loop_bridge.py` (уничтожает `player_perception`). Только точечное обновление `result.world_snapshot["npc_positions"]`.

### 2.2 Воля и Давление

- ❌ Мгновенное сжигание `recent_directive` в LifeEngine (GAP9).
- ❌ Вызов `process_intents()` или `apply_changes()` из `npc_orchestration.py` (единственный владелец — `TickOrchestrator`).
- ❌ Обращение к `intent.action` в `will.py`/`affect.py` без fallback на `parameters.semantic_action` (ADR-035).
- ❌ Вызов WillpowerGate более 1 раза за цикл.
- ❌ Пустой `topic` в `CommunicationIntent`.
- ❌ Хардкод `fear_of_player` в `DirectiveInterpretationSubscriber` для NPC-источников (GAP13).
- ❌ Вызов `DirectiveInterpretationSubscriber` без инъекции `all_npcs_raw` (иначе ObediencePressure=0.00).
- ❌ Возврат `UNCERTAIN` из `IntentCompressor` на известные приставочные глаголы ATTACK/THREATEN (словарь должен покрывать pymorphy3 леммы).

### 2.3 Восприятие и Феноменология

- ❌ Фиксированные множители в CFRM (threat×40, anomaly×20) — движок не интерпретирует (§ENIGMA-S72).
- ❌ Конвертация uncertainty_delta → stress_delta в LegacyStateDeltaAdapter — нарушение §ENIGMA-004.
- ❌ `write_to_legacy` / `from_legacy` без сериализации `perceptual_kernel` и `affective_load` — восприятие и аффект теряются между тиками (DOUBLE TRUTH).
- ❌ `BehaviorManifestationService`/`PhenomenologyProjectionService` читают `stress_delta`/`psyche_state` для моторных искажений и атмосферы — Semantic Inflation (ADR-112, Rule 28).
- ❌ `_apply_runtime_overlay` без белых списков для `affective_load`, `emotion`, `body_state`, `perceptual_kernel` — вычисленное состояние затирается статикой (Инвариант 1).
- ❌ DM-агент читает внутренние состояния NPC (pain, fear, shock) напрямую вместо наблюдаемых симптомов (`embodied_traces`). Kernel Leakage = архитектурный баг.
- ❌ Хранение `threat_gradient` навсегда без decay или recompute. (Текущий decay — временная мера, пока не реализован Gen 3: `perceive_world()`).
- ❌ Создание `NPCState` через прямой конструктор `NPCState(...)` без передачи `emotion`, `affective_load`, `body_state`, `perceptual_kernel`. Только через `from_legacy()` или `load_l2_state_from_runtime_dict()` с полным набором полей (ADR-116).

### 2.4 Физиология и Бой

- ❌ Генерация эмоций напрямую из CombatSubscriber (только PhysiologyPayload).
- ❌ Прямая мутация HP аватара в обход `ImpactEngine`.
- ❌ Использование `hp_ratio` в `state_interpreter` без учета `pain/shock/blood_loss` (GAP5).
- ❌ Масштабная несовместимость: `StateApplicator` пишет `pain` в 0-100, а интерпретаторы читают в 0-1 (нормализация `/100` обязательна при чтении из `body_state`).
- ❌ `CombatSubscriber` пишет в Emotion (Domain Leakage). Только `PhysiologyPayload`.
- ❌ `BehaviorManifestationService` читает эмоции (psyche.fear/stress) вместо физиологии (body_state.pain/blood_loss/shock_impulse) — Правило X (CAUSAL_CONTRACT §7).
- ❌ `write_to_legacy` / `from_legacy` без сериализации `body_state` — физиология теряется между тиками.
- ❌ `shock_impulse` без decay в `PhysiologyDecayHandler` — шок становится перманентным (ADR-105).
- ❌ `StateApplicator` проверяет `shock_impulse > 0.0` вместо `!= 0.0` — блокирует отрицательные дельты decay (ADR-105).
- ❌ Передача Игроку внутренних метрик NPC (HP, fear, trust). Только наблюдаемые симптомы ("дрожит", "кровоточит").

### 2.5 Эмоции и Аффект

- ❌ Хардкод весов affective_load (0.6/0.3/0.1) — веса из drives_base (§ENIGMA-S72).
- ❌ Назначение dominant_emotion_hint из движка — эмоция только через Affective Pipeline (§ENIGMA-S72).
- ❌ Универсальная конвертация эмоция→действие (fear→flee для всех) — drives_base определяет направление разрядки (§ENIGMA-S72).
- ❌ Использование плоского формата `{"fear": 0.5}` в `relationship_cache`. Только вложенный: `{"player": {"fear": 50.0}}`.
- ❌ Использование `affective_load` как независимого аккумулятора с затуханием. Только как `Σ(active_causes)`.

### 2.6 Сериализация и Round-Trip

- ❌ Использование `asdict()` на границе API без Pydantic/Dataclass валидации.

### 2.7 UI и Презентация

- ❌ DM контракт без блока о перемещениях NPC — LLM галлюцинирует локомоцию.
- ❌ Фейковый нарратив при краше LLM ("Твоё сознание мутнеет...") — каузальное мошенничество. Только честное системное сообщение (ADR-113, Rule 29).
- ❌ `agent_runner.py` возвращает `None` при LLM timeout/exception — вызывающий код крашится на `.get()` (ADR-113).

### 2.8 Pipeline и Tick Orchestrator

- ❌ Хардкод языковых глаголов в `npc_tick_pipeline.py` (после починки Semantic Bridge).
- ❌ Создание `_TickContext` без `player_result` при ходе игрока (инвариант: player turn всегда имеет результат).
- ❌ Ретро-симуляция (цикл `LifeEngine.tick()` для нагона).
- ❌ Мутация состояния в обход `DeltaBuffer → apply_batch()`.
- ❌ `print()` для Phase 8 крахов — должен быть структурированный `[PIPELINE][CRITICAL]` или `[PHASE8_CRASH]` (Инвариант 3).
- ❌ CDS не парсит пред-шинные отказы — pipeline умирает молча (Инвариант 3).

### 2.9 Память

- ❌ Публикация в память в обход `MemoryManager`.

### 2.10 Персистенция

- ❌ `_load_npcs_with_runtime` без прайминга LifeEngine cache после чтения с диска — каждый player turn перечитывает YAML.

### 2.11 Прочие запреты

- ❌ Вызов `scene_manager.apply_changes()` из подписчиков (`SceneChange` — проекция для фронтенда).
- ❌ Хардкод семантических весов в DecisionHub (+0.5/+0.7/+0.2) — модуляция через drives_base (§ENIGMA-S72).
- ❌ Передача сырых дельт давления из текущего тика в DecisionHub (только консолидированное восприятие T-1).
- ❌ Хранение `EventDTO` в `EventBuffer` (только `FieldDisturbance`).
- ❌ Обход `LocalCausalSolver` при генерации давления.
- ❌ Мутация состояния из CausalObserver (только пассивная фиксация).
- ❌ Использование полей дельт в `state_applicator` без извлечения из payload (все физиологические поля требуют явного extraction).
- ❌ Чтение `scene_state` оркестратором для бизнес-логики (только для проекции).
- ❌ Применение моторных смещений (дрожь) к экранным координатам ПОСЛЕ отрисовки спрайта. Смещение применяется ТОЛЬКО ДО `self.screen.blit()`.
- ❌ Импорт `backend/app/` во фронтенд (Устав §1.1).
- ❌ Обработка клавиши `Ё` только через `pygame.K_BACKQUOTE` без проверки `event.unicode` (русская раскладка Windows не генерирует BACKQUOTE).
- ❌ Обратная связь из CDS в рантайм симуляции.
- ❌ Прерывание каузального потока при падении CDS.
- ❌ `logger.debug` для крахов аффективного decay — отказы должны быть уровня WARNING (Инвариант 3).
- ❌ Персистенция `relationship_cache` внутри `NPCState` (DOUBLE TRUTH). Только `RelationshipStore` пишет на диск.


## 3. ВЕРИФИЦИРОВАННЫЕ РАЗРЫВЫ (Открытые проблемы)

> **Правило:** Этот раздел = ВСЕ проблемы, помеченные как ВЕРИФИЦИРОВАННЫЙ РАЗРЫВ или ВЕРИФИЦИРОВАНО.
> **Статус:** Если разрыв закрыт — он перемещается в соответствующую сессию с пометкой [ЗАКРЫТ].

- - **S49:** ВЕРИФИЦИРОВАН РАЗРЫВ: LifeEngine перезаписывает реактивные транзиты (`reactive:approach`) schedule-интентами (`schedule:sleeping`) каждый idle tick. NPC не доходит до игрока — его постоянно редиректят в кровать. Требует механизм пробуждения (отложено).
- - **S49:** ВЕРИФИЦИРОВАН РАЗРЫВ: Незваные NPC (`blacksmith_orm`, `merchant_goran`) получают `approach` от DecisionHub при команде, адресованной другому NPC. Требует фильтр целевого NPC (отложено).
- - **S49:** ВЕРИФИЦИРОВАН РАЗРЫВ: Хардкод русских глаголов в `npc_tick_pipeline.py` — нарушает локализуемость и разделение ответственности. `IntentCompressor` уже умеет классифицировать `MOVE` через pymorphy3, но Semantic Bridge (`S28_GATE`) возвращает `UNCERTAIN` — результат теряется на пути от `phase_1_input` до `hub_event`. После починки Bridge хардкод должен быть удалён.
- - **S48:** ВЕРИФИЦИРОВАНО: RPG Витализм в `state_interpreter.py`. Оценка физического состояния NPC идет по `hp_ratio`, игнорируя `pain`, `shock_impulse` и `blood_loss`. NPC с 80% HP, но `pain: 0.9` описывается LLM как "слегка ранен". Мост Физиология → Речь оборван. (УБИТО в S51).
- - **S49:** ВЕРИФИЦИРОВАН РАЗРЫВ: `game_loop_bridge.py` не пробрасывал `active_traversals` в `world_snapshot` → фронтенд не мог интерполировать движение. Исправлено: bridge копирует `active_traversals` из `scene_state`.
- - **S48:** ВЕРИФИЦИРОВАНО: Семантическая Глухота. `IntentEventAdapter` при конвертации `CommunicationIntent` в `EventDTO(NPC_SPOKE)` выбрасывает `semantic_action` и `target_id`. Событие становится семантически пустым. Это блокирует реализацию NPC-to-NPC Social Physics, так как подписчик не может распознать приказ или угрозу. (УБИТО в S50).

---

## 4. СПРАВОЧНИК ДОМЕНОВ (Текущие истины)

> **Правило:** Этот раздел = сводка текущего состояния каждого домена.
> **Использование:** Для понимания архитектурного контекста перед изменением.

### 4.01 1. ПРОСТРАНСТВО И ДВИЖЕНИЕ (Spatial & Locomotion)

**Текущая истина:** `SpatialQueryService` — единственный авторитет. Движение — это *результат* давления и решения, а не команда. Фронтенд — интерполятор, а не телепортер.

**Связанные сессии:** S04, S10, S29, S32, S33, S35, S37, S38, S46, S47, S49, S50, S51, S54, S58, S59, S61, S65, S67, S68, S69

### 4.02 2. ВОЛЯ, ДАВЛЕНИЕ И РЕШЕНИЕ (Will, Pressure & Decision)

**Текущая истина:** Решения рождаются из искривленного давления (Utility Deformation). Воля — инерция, а не порог. Подчинение требует легитимности.

**Связанные сессии:** S19, S21, S24, S25, S29, S31, S35, S36, S48, S49, S50, S52, S53, S54, S55, S60, S64, S68, S69, S71

### 4.03 3. ВОСПРИЯТИЕ И ФЕНОМЕНОЛОГИЯ (CFRM & Perception)

**Текущая истина:** Объективных фактов нет. Есть возмущения поля (`FieldDisturbance`), которые проецируются в субъективные феномены в зависимости от наблюдателя.

**Связанные сессии:** S21, S26, S30, S38, S53, S62

### 4.04 4. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat)

**Текущая истина:** Тело — материальный объект. Удар — чистая физика контакта, которая порождает боль и шок, а шок уже транслируется в эмоции.

**Связанные сессии:** S16, S20, S30, S48, S51, S54, S57, S59, S60, S61, S67

### 4.05 5. ТРУБА ОРКЕСТРАТОРА И ВРЕМЯ (Pipeline & Elastic Time)

**Текущая истина:** Симуляция дискретна (каузальность), презентация непрерывна. `LifeEngine` — лоббист давления, а не бог-мутатор.

**Связанные сессии:** S28, S34, S36, S48, S49, S53, S54, S55, S59, S60, S61, S65, S67

### 4.06 6. ПАМЯТЬ И СОЦИУМ (Memory & Social Physics)

**Текущая истина:** Память многослойна. Социальные акты (приказы) искривляют utility-space цели, а не генерируют `MovementIntent` напрямую.

**Связанные сессии:** S03, S08, S27, S32, S47, S48, S50, S51, S52

### 4.07 7. ФРОНТЕНД И ПРЕЗЕНТАЦИЯ (UI & Embodiment)

**Текущая истина:** Фронтенд — это сенсорный орган игрока. Он искажается, болеет и сопротивляется, не зная внутренних метрик бэкенда.

**Связанные сессии:** S10, S18, S25, S26, S28, S39, S48, S54, S56, S57, S59, S60, S61

### 4.08 8. НАБЛЮДАЕМОСТЬ И ДИАГНОСТИКА (CDS)

**Текущая истина:** Наблюдение не создает причинность. CDS — пассивный аудиторе.

**Связанные сессии:** S39, S65

### 4.09 9. SOCIAL & AFFECTIVE ARCHITECTURE (SSOT & CAUSAL DERIVATION)

**Текущая истина:** Отношения — это граф (ребро), а не свойство узла. Аффективная нагрузка — производная от активных причин, а не магическая батарейка.

**Связанные сессии:** S63, S66

---

## 5. МЕТАДАННЫЕ ДОКУМЕНТА

| Показатель | Значение |
|------------|----------|
| Всего сессий | 50 |
| Всего архитектурных запретов | 69 |
| Всего доменов | 9 |
| Верифицированных разрывов | 6 |
| Диапазон сессий | S03 — S71 |

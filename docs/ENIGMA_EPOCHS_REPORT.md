# ДОКЛАД: ПЯТЬ ЭПОХ ЭВОЛЮЦИИ ENIGMA И КАРТА БУДУЩЕГО

> **Документ:** Архитектурный доклад об эволюции системы
> **Версия:** На момент v0.5.3.9.2 (S270+)
> **Дата:** 2026-08-30
> **Источник:** `MUTATIONS.md`, `ADR Master Index`, `00_CAUSAL_CONTRACT_v2.0.md`, `ENTITY_CONTINUITY_CONTRACT.md`, TZ-документы из `docs/Почти Актуальные TZ/`
> **Покрытие:** S04 → S270+ (6 завершённых эпох) + проектирование Эпох 7-11+

---

## 0. КОНТЕКСТ ДОКЛАДА

ENIGMA — не игра в обычном смысле. Это **исследовательский артефакт**, развивающийся 300+ сессиями через **каузальную методологию**: каждое архитектурное решение фиксируется как ADR (Architecture Decision Record), каждый инвариант становится контрактом, каждое нарушение контракта — багом. Эволюция разбита на **эпохи** — дискретные фазы, каждая из которых навсегда изменила онтологию проекта.

Этот доклад описывает:
1. **6 завершённых эпох** (S04 → S270+) с конкретными ADR, файлами и инвариантами
2. **5 будущих эпох** (v7.5 → v11.0+) с проекцией развития

---

# ЧАСТЬ I. ПРОШЛЫЕ ЭПОХИ (S04 → S270+)

## ЭПОХА 1: КАУЗАЛЬНЫЙ ФУНДАМЕНТ (S04 — S82)

**Девиз:** «Уничтожение телепортации, централизация пространства, базовая физиология»

### Контекст

До Эпохи 1 ENIGMA была обычной RPG с sketch-архитектурой: NPC телепортировались между сценами, RPG-математика (Hit Roll, AC) определяла бой, фронтенд читал backend напрямую. Симуляция была нечестной: NPC "знали" о игроке то, чего не могли знать.

### Главные архитектурные сдвиги

#### 1.1. Уничтожение RPG-математики (ADR-015, ADR-123)

**Было:** `hit_roll = d20 + modifier; if hit_roll >= AC: damage = weapon_dice`

**Стало:** `body_state["current_hp"]` — единственный SSOT для HP. Бой идёт через `ImpactEngine`, который генерирует `PhysiologyPayload` (hp_delta, pain, shock, injuries). Смерть — через `evaluate_vital_state()`, не через `hp <= 0`.

**Создано:**
- `backend/app/domain/vital_state.py` — онтология жизненных состояний
- `backend/app/services/combat/impact_engine.py` — физика удара
- `backend/app/services/combat/physiology_decay_handler.py` — decay боли/шока

**Инварианты, введённые эпохой:**
- **L12: Physiology & Death Lock Law** — `body_state["current_hp"]` SSOT, смерть необратима, decay для мёртвых запрещён
- **L12.1: D&D 5e Combat Math Law** (базовый — позже расширен в Эпоху 3) — ContactLevel mapping

#### 1.2. SpatialService как единственный владелец графа (ADR-008, ADR-048)

**Было:** `scene_state["player_distances"]`, прямые чтения из `npc_positions`, телепортация через `npc["position"] = new_pos`

**Стало:** `SpatialFactory.build_for_campaign()` — единственный сборщик графа. `SpatialQueryService` — единственный читатель. Появился `TraversalState` — данные о физическом движении, отделённые от личности NPC.

**Создано:**
- `backend/app/services/spatial/spatial_service.py`
- `backend/app/services/spatial/spatial_factory.py`
- `backend/app/services/spatial/spatial_query_service.py`
- `backend/app/domain/traversal.py` — TraversalState schema

**Инварианты:**
- **L9: Spatial SSOT & Factory Law** — единый сборщик, единый читатель
- **L10: Traversal FSM Law** — `SceneStateManager` — единственный владелец lifecycle (PENDING → MOVING → COMPLETED/CANCELLED)
- **SC-1..SC-8: Spatial Coherence Contract** — `local_position` не (0,0), принадлежит `location_id`, `current_node` существует в graph, и т.д.

#### 1.3. Dual-Time Ontology (ADR-058, ADR-059)

**Было:** `tick += 1` внутри `player.action()`, `time.time()` везде

**Стало:** Разделение симуляционного времени (`game_time_seconds`, целое число, tick) и рендер-времени (wall-clock только для визуальных эффектов). `game_time_seconds` — единственный авторитет.

**Инварианты:**
- **L2 (частично):** `game_time_seconds` — единственный авторитет времени
- §14 (позже формализован): Закон Единичного Времени

#### 1.4. DTO-контракт фронтенда (ADR-TZ03-1)

**Было:** Frontend читал `backend/` напрямую

**Стало:** Backend = единственный источник истины. Frontend = pure renderer. DTO канонизированы. Фронтенду запрещено генерировать время, аватара, журнал.

**Инварианты:**
- **L15: Frontend Authority Law** — `game_time_seconds +=` во фронтенде запрещён, вычисление manifestations запрещено

### Итоги Эпохи 1

| Метрика | Значение |
|---------|----------|
| Сессий | ~78 (S04-S82) |
| Введённых ADR | ~50 (ADR-001 до ADR-082) |
| Главных контрактов | 4 (L9, L10, L12, L15) |
| Главных инвариантов | 12 (SC-1..SC-8, body_state SSOT, Death Lock, Dual-Time) |
| Созданных файлов | ~150 (spatial/, combat/, models/...) |

**Эпоха 1 превратила ENIGMA из RPG-sketch в симуляцию с честной физикой и централизованным пространством.**

---

## ЭПОХА 2: УНИФИКАЦИЯ ПАЙПЛАЙНА И ЧИСТОТА ЯДРА (S83 — S104)

**Девиз:** «Превращение ядра в чистую функцию, изоляция LLM, детерминизм»

### Контекст

После Эпохи 1 физика стала честной, но **ядро было ветвистым**: `if dm_ctx: ... else: player.action: ...`. Подсистем было много, и они могли вызывать LLM в любой точке пайплайна. Random был везде. L3 (EffectiveDrives) кэшировался, нарушая эфемерность.

### Главные архитектурные сдвиги

#### 2.1. Уничтожение ветвления player/idle (ADR-TZ08-1, ADR-TZ09-1, ADR-TZ10-1)

**Было:** `TickOrchestrator.execute(dm_ctx=...)` — особый путь для DM; `execute(player_action=...)` — особый путь для игрока; `execute(idle=True)` — особый путь для мира. Три ветки, три кодовых пути.

**Стало:** Ядро не знает 'player' или 'dm_ctx'. Только `InterventionEvent` — унифицированный вход. `TickState` — immutable snapshot входных данных. `TickMutation` — выходной результат. `NpcTickPipeline.run(state: TickState) -> TickMutation` — чистая функция.

**Создано:**
- `backend/app/domain/tick.py` — TickState, TickMutation
- `backend/app/services/npc/npc_tick_pipeline.py` — pure reducer
- `backend/app/contracts/interventions.py` — InterventionEvent

**Инварианты:**
- **L1: State Mutation Law** — единственный путь мутации: `Phase8Result → delta_buffer → StateApplicator.apply_batch()`
- **L2: Runtime Purity Law** — тик = чистая функция, `random.*` запрещён, `time.time()` запрещён, параметр `svc: Any` запрещён

#### 2.2. KernelRNG: полная изоляция случайности (ADR-O-301)

**Было:** `random.choice(...)` в combat, `random.randint(...)` в decision_hub, `random.Random()` в movement

**Стало:** `KernelRNG(tick, npc_id, salt)` — детерминированный генератор. Все random в kernel layer — нарушение контракта. Replay даёт идентичный результат.

**Создано:**
- `backend/app/services/npc/kernel_rng.py`

**Инварианты:**
- **L2 (расширение):** `random.*` запрещён в kernel layer; `DecisionHub()` без `rng` — нарушение; `KernelRNG` без `salt` — нарушение

#### 2.3. L1Chronicle и эфемерность L3 (ADR-O-208, ADR-O-211, L3-P1)

**Было:** L3 (EffectiveDrives) кэшировался в `drives_runtime`. Identity = state. State перезаписывался каждый тик. Память была stateful, не исторической.

**Стало:** L1Chronicle — append-only SQLite история деформаций личности. Каждое давление мира на NPC записывается как `TraitDriftEvent(tick_id, target_id, source_id, effect_value, observation_weight, event_type)`. L3 (`EffectiveDrives`) — строго эфемерная проекция (L0 + L2.5 beliefs), рождается и умирает в тик. Кэш L3 = рассинхрон идентичности.

**Создано:**
- `backend/app/services/npc/l1_chronicle.py` (337 строк, SQLite)
- `backend/app/domain/identity_events.py` — `TraitDriftEvent`, `EffectiveDrives`
- `backend/app/services/npc/drive_resolver.py` — L3 projection

**Инварианты:**
- **L17: Identity Pipeline Law** — L1Chronicle append-only, L3 эфемерен, `CalibrationEngine` не мутирует L0
- **L3-P1:** Кэширование EffectiveDrives запрещено

#### 2.4. Epistemic Boundary (ADR-TZ08-4, ADR-TZ08-6, ADR-093)

**Было:** DM-agent читал `stress_delta`, `real_state`, `recalled_facts` — ментальные объекты NPC. Ядро возвращало `dm_frame` — гибрид наблюдаемого и ментального.

**Стало:** DM-agent — строгий локальный наблюдатель. Читает только `observed_state` и `embodied_traces`. Нарратив рождается из наблюдаемых действий, не из сырых ментальных полей.

**Создано:**
- `backend/app/services/offscreen/world_projection_buffer.py` — pure function projection
- `backend/app/domain/observed_facts.py`, `observed_fact.py`
- `backend/app/domain/embodied_trace.py`

**Инварианты:**
- **L16: Epistemic Boundary Law** — чтение `stress_delta`, `real_state`, `recalled_facts` в DM-слое запрещено

### Итоги Эпохи 2

| Метрика | Значение |
|---------|----------|
| Сессий | ~22 (S83-S104) |
| Введённых ADR | ~25 (TZ-серия, O-200..O-302) |
| Главных контрактов | 5 (L1, L2, L16, L17, L3-P1) |
| Главных инвариантов | 8 (Purity, KernelRNG, L3-ephemeral, Epistemic Boundary, ...) |
| Главных файлов | ~30 (tick.py, npc_tick_pipeline.py, kernel_rng.py, l1_chronicle.py, ...) |

**Эпоха 2 превратила ENIGMA в детерминированную чистую функцию с эпистемически честным наблюдателем.**

---

## ЭПОХА 3: КРИСТАЛЛИЗАЦИЯ ИДЕНТИЧНОСТИ И ЭПИСТЕМИКА (S105 — S125)

**Девиз:** «L2.5 (Убеждения), Тройная Мембрана, замыкание каузальности потребностей»

### Контекст

После Эпохи 2 идентичность NPC была исторической (L1Chronicle), но **не интерпретирующей**. L1 накапливал события, но не было механизма, превращающего статистику в убеждения. NPC не мог "верить", что игрок предатель — он мог только накапливать evidence.

Также не было **каузальной трубы потребностей**: NPC могли иметь потребности, но не было закона, что потребность рождается только из каузального входа.

### Главные архитектурные сдвиги

#### 3.1. BeliefCrystallizationEngine и асимметричная травма (ADR-O-305, ADR-O-306, ADR-O-307)

**Было:** Trust как скаляр. `trust += 5` за хороший поступок, `trust -= 5` за плохой. Симметрично, без психологии.

**Стало:** Трёхслойная модель:
- **L1 (Факты)** — `TraitDriftEvent` в L1Chronicle
- **L1.5 (PatternDetector)** — чистая статистика: cumulative_effect, behavior_variance. Запрещены психологические поля (`trait`, `emotion`)
- **L2.5 (Belief Engine)** — психологическая проекция статистики. `CrystallizedBelief` — это **линза** (модификатор весов), не ген (скаляр)

**Асимметричная травма ×6:** Опровержения ранят сильнее подтверждений. Если NPC верил, что игрок друг, и игрок предал — belief кристаллизуется с ×6 multiplier. Это модель cognitive dissonance из психологии, не game design.

**Создано:**
- `backend/app/services/npc/pattern_detector.py` (L1.5)
- `backend/app/services/npc/belief_crystallization_engine.py` (L2.5)
- `backend/app/services/npc/crystallized_belief_store.py`
- `backend/app/models/npc/beliefs.py`

**Инварианты:**
- **L18: Belief Crystallization Law** — `PatternDetector` чистая статистика, `Belief Engine` психологическая проекция, асимметричная травма ×6, чтение L1 только через `EvidenceOfPersistence`

#### 3.2. Тройная Мембрана (ADR-O-306)

**Было:** Все события L1 одинаково важны. NPC "помнил" всё, что происходило.

**Стало:** L1Chronicle фильтруется через **Triple Membrane** перед PatternDetector:
1. **Физическая мембрана** — был ли NPC физически способен воспринять событие? (расстояние, LoS, слышимость)
2. **Личностная мембрана** — соответствует ли событие personality NPC? (rigidity, openness)
3. **Социальная мембрана** — проходит ли событие через социальные фильтры? (статус, отношения, нормы)

Каждая мембрана имеет norm-modulated пороги. Если событие не прошло одну из мембран — оно не записывается в L1.

**Инварианты:**
- **L18 (расширение):** Triple Membrane как обязательный фильтр L1
- **L14: Epistemic Memory Law** — память не генерирует идентичность без каузального входа

#### 3.3. Entity Continuity (ADR-O-315, ADR-O-316, ADR-O-317, ADR-O-320, ADR-O-321)

**Было:** NPC имел статичные traits. `identity_crisis` — скаляр. `life_project` — захардкожен.

**Стало:** `Reality-Constrained Agency Model`:
- **L0 (`CoreOrientation`)** — неизменен (базовая личность)
- **Layer 2: `Identity Pressure Vector`** — эфемерный вектор (prediction_error, self_model_conflict, social_reflection_delta, value_violation)
- **L2.7 (`life_project`)** — динамический FSM, управляемый Pressure Vector
- **Anti-Script Constraint** — сценарии не могут напрямую задавать решения агента, если есть внутренняя причинная цепь

**Создано:**
- `backend/app/services/npc/life_project_resolver.py`
- `backend/app/services/npc/break_progress_engine.py`
- `docs/ENTITY_CONTINUITY_CONTRACT.md` (5 слоёв непрерывности)

**Инварианты:**
- **L20: LifeProject & Agency Model Law** — мгновенная смена `life_project` запрещена, бусты в стадиях `LOST`/`SEARCHING` запрещены, скалярный `identity_crisis` запрещён

#### 3.4. Embodied Traversal (S130-S132, ADR-S90.1, ADR-S91, ADR-O-324, ADR-O-329)

**Было:** A* по узлам графа — примитивная навигация. NPC не мог обойти препятствие, не мог прыгнуть, не мог протиснуться.

**Стало:** `LocalTraversalPlanner` + `Geometry Kernel`. Движение определяется физической геометрией:
- **Z-координата** — честная физика прыжка
- **Clearance** — зазоры (NPC не пролезет в щель < своего размера)
- **Dynamic Doorway Routing** — геометрическая валидация сегментов пути, не слепое доверие графу
- **ETKE-IK** — микро-перемещения через `DriveVector` (velocity), отдельно от макро-путей через `MovementIntent`

**Создано:**
- `backend/app/services/spatial/local_traversal_planner.py`
- `backend/app/services/spatial/geometry_kernel.py`
- `backend/app/services/spatial/traversability_evaluator.py`
- `backend/app/services/motion/motion_pipeline.py`
- `backend/app/domain/motion_core.py`

**Инварианты:**
- **L11: Hybrid Geometry & Stigmergy Law** — `MovementIntent` для микро запрещён, `DynamicAffordanceField` хранит структурные деформации
- **L11.1: Spatial Agency Law** — Decision Layer не генерирует `target_node_id`, только `SpatialTargetIntent`

#### 3.5. Combat RNG: D&D 5e с детерминизмом (ADR-164)

**Было:** Custom формулы урона, нарушение KernelRNG в combat

**Стало:** `combat_math.py` с D&D 5e rules (`attack_roll`, `damage_roll`) через `KernelRNG`. `ImpactEngine._resolve_contact` переведён на `attack_roll`. Результаты (Hit/Miss/Crit) маппятся на `ContactLevel` (MISS, GLANCING, PARTIAL, SOLID, PERFECT).

**Инварианты:**
- **L12.1: D&D 5e Combat Math Law** — вычисление попадания внутри `impact_engine.py` запрещено, legacy-формулы запрещены

### Итоги Эпохи 3

| Метрика | Значение |
|---------|----------|
| Сессий | ~21 (S105-S125) |
| Введённых ADR | ~15 (O-305..O-329, S90.1, S91) |
| Главных контрактов | 5 (L11, L11.1, L18, L20, L12.1) |
| Главных инвариантов | 10+ (Belief ×6, Triple Membrane, Anti-Script, SC-1..SC-8, ...) |
| Главных файлов | ~25 (belief_*, pattern_*, geometry_*, motion_*, ...) |

**Эпоха 3 превратила ENIGMA в систему с психологически правдоподобной идентичностью и физически честным движением.**

---

## ЭПОХА 4: ПРЕЗЕНТАЦИЯ И ФИЗИКА ВОСПРИЯТИЯ (S126 — S141)

**Девиз:** «5-слойная архитектура Reality → Observable Physics → Perception, World Continuity»

### Контекст

После Эпохи 3 NPC имел богатую внутреннюю жизнь (L1Chronicle, beliefs, life_project), но **наблюдатель не мог её видеть честно**. UI либо показывал ментальные состояния (telepathy), либо показывал ничего. Также не было связи между кампаниями — каждая кампания начиналась с чистого листа.

### Главные архитектурные сдвиги

#### 4.1. 5-слойная архитектура восприятия (Presentation v2.0)

**Было:** DM-agent видел `psyche` и `social_stats`. UI показывал `fear_level: 0.7`. Телепатия.

**Стало:** 5 слоёв:
1. **Reality** — объективные факты мира (недоступны наблюдателю напрямую)
2. **Observable Physics** — физические проявления (поза, голос, движение)
3. **Embodied Traces** — `EmbodiedTraceDTO` с `confidence` и `possible_causes`
4. **Perception** — что наблюдатель воспринял (фильтруется через PerceptualKernel)
5. **Phenomenology** — финальная проекция для UI/DM

**Принцип:** Скрытая травма (хромота) порождает наблюдаемое поведение без утечки ментальных стейтов. `ManifestationDTO.tags` — НЕ эмоции (`fearful`, `anxious`), а моторные проявления (`tense`, `rigid`, `trembling`, `limping`).

**Создано:**
- `backend/app/services/perception/perception_projector.py`
- `backend/app/services/perception/perceptual_attention_service.py`
- `backend/app/services/perception/perception_physics_engine.py`
- `backend/app/services/perception/phenomenology_projection_service.py`
- `backend/app/services/perception/manifestation_physics_engine.py`
- `backend/app/services/perception/behavior_manifestation_service.py`
- `backend/app/services/perception/inference_engine.py`
- `backend/app/services/perception/fact_extractor.py`
- `backend/app/services/perception/presentation_assembler.py`

**Инварианты:**
- **L8: CFRM & Somatic Gate Law** — тело как фильтр восприятия, эмоции конвертируются только в моторные проявления
- **CAUSAL_CONTRACT §4.3.18:** Передача Игроку информации о внутренних состояниях NPC запрещена
- **CAUSAL_CONTRACT §4.3.23:** Показ fearful, anxious запрещён — только tense, rigid

#### 4.2. World Continuity (ADR-O-330+)

**Было:** Каждая кампания — независимая. Смерть NPC в кампании A не влияла на кампанию B.

**Стало:** Опция наследия мира между кампаниями:
- `WorldStateDiff` — diff между двумя состояниями мира
- `WorldStateApplicator` — применяет diff к новой кампании
- Мёртвые NPC из предыдущей кампании остаются мёртвыми
- Изменения в фракциях переносятся

**Создано:**
- `backend/app/services/state/world_diff_builder.py`
- `backend/app/services/state/world_diff_applicator.py`
- `backend/app/models/world_state_diff.py`
- `backend/app/models/world_continuity.py`

#### 4.3. UI/UX: Журнал, Eavesdrop, Mood-иконки

**Было:** Линейный журнал. Mood-иконки из эмоций.

**Стало:**
- Журнал переведён на вкладки (по темам, по NPC)
- Механика подслушивания (Eavesdrop) — игрок может слышать разговор NPC-NPC, если физически близко
- Mood-иконки рисуются строго из наблюдаемых проявлений (`ManifestationDTO.tags`), не из эмоций

**Создано:**
- `frontend/narrative_renderer.py`
- `frontend/narrative_beat.py`
- `frontend/presentation_firewall.py` — фильтр телепатии на фронте
- `frontend/perceptual_momentum.py` — визуальная инерция камеры

#### 4.4. Pipeline Repair: исчезновение имени NPC после idle_tick

**Было:** После `idle_tick` имя NPC пропадало из `npc_positions`. Fuzzy matching слеп. `ObediencePressure = 0`.

**Стало:** Обновление `confidence` перенесено в pre-commit (Фаза 10). Имя переживает idle_tick.

### Итоги Эпохи 4

| Метрика | Значение |
|---------|----------|
| Сессий | ~16 (S126-S141) |
| Введённых ADR | ~10 (преимущественно O-325..O-330) |
| Главных контрактов | 2 (L8 расширение, World Continuity) |
| Главных инвариантов | 8 (5-layer perception, manifest-only, eavesdrop, ...) |
| Главных файлов | ~15 (perception/*, world_diff_*, narrative_*) |

**Эпоха 4 превратила ENIGMA в систему с эпистемически честной презентацией для игрока и DM-агента.**

---

## ЭПОХА 5: САНАЦИЯ И ОЧИСТКА ДОЛГОВ (S142 — S147)

**Девиз:** «Устранение магических чисел, TODO/FIXME, финальная типизация, V8.x Closure»

### Контекст

После Эпох 1-4 архитектура была сложной, но в коде накопился долг: магические числа, дубликаты, мёртвый код, TODO маркеры, нарушение типизации. Также MVP-функционал (мини-игра "Серебряный Волк", секреты Люси) требовал доводки.

### Главные архитектурные сдвиги

#### 5.1. Санация (S142)

- Очищено 34 пустых маркера `TODO:`
- Магические числа из `BreakProgressEngine` вынесены в `constants.py`
- Устранено дублирование цветовой схемы фронтенда (`ui_theme.py`)
- `SocialEngine` начал честно получать `player_distances` от `SpatialQueryService`

#### 5.2. S143: ENIGMA SELF-HEALING (Уровни 0-2, 7)

Внедрена система защиты от тихих отказов:
- **Уровень 0:** IPT — Invariant Probe Tests (запуск до коммита)
- **Уровень 1:** `MvpTavernController` подписан на `TICK_COMPLETED` (N2/M-03)
- **Уровень 2:** `TruthState` получил `discovered_secrets`, `ActionCompiler` отмечает секреты и применяет delta к фракциям
- **Уровень 7:** `/api/health` telemetry dashboard для мониторинга

Фиксы:
- N4: `NameError` в `_fallback_to_astar`
- N7: zombie traversal
- N3: ambient routing dead code
- N6: dup method

#### 5.3. S144: ENIGMA V8.3 DAY 1-4 + END-SCREEN FIX (40+ bugs)

Закрыты все Critical MVP blockers:
- **V8-SP-1/2** — Spatial blockers (NPC не двигаются)
- **V8-PSY-1..5** — Psychology pipeline (L1Chronicle, L3 cascade, belief pipeline)
- **V8-MEM-1..3** — Memory (STM, L2 Memory, dialogue consolidation)
- **V8-SOC-1/3/4** — Social (NPC↔NPC consequences, SocialDeltaEngine normalization)
- **V8-FC-01/02** — FastAPI двойной префикс `/api/api/`, exit trigger

**L1Chronicle проброшен через весь конвейер:** `TickState → NpcTickPipeline → StateApplicator`. Trauma pipeline, L3 Identity cascade, belief pipeline, attack windup — оживлены.

#### 5.4. S145: ENIGMA DIALOGUE THREAD SYSTEM

Внедрена структурная память диалогов:
- BUG-DL-01: Реплика игрока доходит до STM целевого NPC
- BUG-DL-08: STM не стирается при ходьбе внутри локации
- BUG-DL-02: `DialogueExecutor` инжектит STM-блок для NPC↔NPC
- BUG-DL-03: DM-агент получает targeted STM
- BUG-DL-05: Per-pair sessions (ключ `campaign:npc:partner`)
- BUG-DL-04: `thread_id` для многотоповых диалогов
- BUG-DL-06: Отложенная запись реплик в `narrative_cache`
- BUG-DL-07: Суммаризация диалога в EventMemory при очистке
- BUG-DL-12: TTL реплик переведён на `game_time_seconds`

**Hard Contract:** запрет на вызов LLM без STM (кроме greeting/approach).

**Инварианты:**
- **INV-DIALOGUE-STM** добавлен в IPT

#### 5.5. S146: ENIGMA V8.6 CLOSURE (Days 3-5)

Закрыты 17 MEDIUM/LOW багов из контракта v8.6:
- **Spatial Day 3:** V8-SP-23 (boundary nodes не перетирают `location_id`), V8-SP-24 (micro_snap deadlock), V8-SP-25 (геометрия market_square + adjacency reciprocity), V8-SP-26 (`reinit_campaign` сбрасывает все кэши), V8-SP-28 (boundary_map actual coords), V8-ED-5
- **Will/Avatar Day 4:** V8-WL-6 (`player_pressure` SSOT восстанавливает ADR-031), V8-WL-7/8/9 (безопасная загрузка аватара, полная персистенция FSM state)
- **Cleanup Day 5:** V8-MEM-16 (race condition `_identity_cache` через `threading.RLock`), V8-SOC-8 (удаление мёртвых event types), V8-DLG-15/16, V8-MVP-23

#### 5.6. S147: WORKPLACE AFFORDANCE CONTRACT (ADR-O-326)

**Было:** NPC "работали" в произвольных местах, без привязки к миру.

**Стало:** Привязка действий NPC к точкам мира через теги `workplace:<npc_id>`:
- В `NodeRole` добавлены `GUARD_POST`, `DARK_CORNER`, `SERVING_STATION`, `KITCHEN_COUNTER`, `INN_DESK`
- В `role_resolver` внедрён приоритет `editor_tags` над keywords
- В `life_engine._resolve_position` поиск персонального рабочего места через `filters=[workplace:npc_id]` с fallback на роль
- MAP EDITOR UPGRADE: валидация `_VALID_ROLES`, метод `update_node`, диалог редактирования узла, `SimpleNodeUpdateCommand` для Undo/Redo

**Cross-loc materialize fix:** В `event_compiler` добавлена обработка `cross_loc_materialize` (ThickSceneChange с BoundaryResolution), устраняющая дрейф D (Causal Drift) при пересечении границ локаций.

### Итоги Эпохи 5

| Метрика | Значение |
|---------|----------|
| Сессий | 6 (S142-S147) |
| Введённых ADR | ~5 (O-326, V8.x closure) |
| Главных контрактов | 2 (Workplace Affordance, Dialogue Thread) |
| Закрытых багов | 60+ (V8-* серия) |
| Главных файлов | ~20 (mvp_tavern_controller, truth_state, dialogue_*) |

**Эпоха 5 превратила ENIGMA в играбельный продукт с working MVP и стабильным baseline.**

### Общий итог 6 эпох

| # | Главная тема | Главный сдвиг |
|---|--------------|---------------|
| 1 | Каузальный фундамент | Уничтожение телепортации, централизация пространства |
| 2 | Чистота ядра | TickState → TickMutation, KernelRNG, L1Chronicle |
| 3 | Идентичность | BeliefCrystallization, Triple Membrane, Embodied Traversal |
| 4 | Восприятие | 5-layer Reality → Perception, World Continuity |
| 5 | Санация | V8.x closure, MVP стабилизация, Workplace Affordance |
| 6 | Стабилизация + Infrastructure + Epistemic Core | IPT 45/45, PBT, Replay, Probes, ADR-Net, Proposition Layer, Relationship Engine v2 (M0/M1a/M1b), W-TRACK субстрат, mypy --strict spatial 0, print()→logger |

**Текущее состояние (v0.5.3.9.2):** IPT 45/45, SHI=100%, 6/6 NPC с координатами, симуляция разморожена (Фаза 0), RE-01 M1b в процессе, W-TRACK dormant-substrate.

---

# ЧАСТЬ II. БУДУЩИЕ ЭПОХИ (v7.5 → v11.0+)

## КОНТЕКСТ ПРОЕКТИРОВАНИЯ

Ты описал видение:
- **Игра-симулятор эффекта бабочки** — девушка выбирает из 3 парней, смотрит на незаскриптованную судьбу
- **Игрок как 4-й кандидат** — может рассказать ей, что с ней случится в будущем (Prophecy System)
- **Рождение и смерть, смена поколений** — WorldChronicle, Lineage, Aging
- **Небольшое, но полноценное общество** — 20-30 живых NPC, фракции, экономика

Каждая будущая эпоха — это **расширение онтологии**, добавляющее новый слой реальности без разрушения предыдущих.

---

## ЭПОХА 6: СТАБИЛИЗАЦИЯ, ИНФРАСТРУКТУРА И ЭПИСТЕМИЧЕСКИЙ ФУНДАМЕНТ (S148 — S270+) ✅ ЗАВЕРШЕНА

**Девиз:** «Stable baseline, infrastructure for scale, epistemic core proven»

### Контекст

Эпоха 6 — крупнейшая по объёму и **завершена** на v0.5.3.9.2 (S270+). Началась с закрытия критических багов и построения инфраструктуры (S148-S185), прошла через доказательство эпистемической причинности (SUPERBOX-001 — SUPERBOX-013, S186-S188), а затем вышла на плато стабилизации: полный цикл аудита v0.5.3.7.2 — v0.5.3.7.10 (`STABILIZATION_ROADMAP.md`), санация технического долга (mypy --strict, print()→logger, IPT-ruff) и два новых домена — Relationship Engine v2 и World Embodiment Foundation.

### Главные сдвиги

#### 6.1. Закрытие критических багов и инфраструктура (S148-S185)

- **S148-S149:** Presentation v2.0, DriftLaboratory v2, PBT, Causal Probes
- **S150-S156:** Dialogue Hard Contract, Zombie Traversal Detector, ADR-Net Parser, Replay System
- **S157-S167:** Economy & Social Emergence, UI Epistemic Integration, UI Doctrine, UI Refactor
- **S168-S175:** UI Polish, Visual Casting, Map Editor
- **S176-S185:** WorldTick Temporal Ownership, Bugfix Report Execution, Pytest Recovery, Pure Reducer, Sprint S1-S7 (Cardinality, Causal Ordering, Semantic Pipeline, Dialogue & Travel FSM, Replay Determinism, Load Integrity)

#### 6.2. Фундамент пайплайна (S186)

- **P0-1 (Tick Cardinality):** Время продвигается ровно 1 раз за тик
- **P0-2 (NPC Cardinality):** NPC из разных локаций не появляются в npc_positions друг друга
- **P1-5 (Commit Cardinality):** atomic_commit_all — ровно 1 коммит за тик
- **P1-6 (EventBus Cardinality):** NPC_MOVED не превышает total_npcs
- **P1-7 (Dialogue Causal Loop):** NPC_SPOKE → STM → NPCDialogueSubscriber

#### 6.3. EPISTEMIC CORE — Proposition Layer (S187-S188)

**Главный архитектурный сдвиг Эпохи 6.**

Доказана причинная цепь:

    Communication → ClaimEvent → Proposition → BeliefRevisionEngine
        → EpistemicStore → EpistemicContextResolver → EpistemicContext
        → DecisionContext → DecisionHub → Intent

**SUPERBOX-001 (S187):** Терминальный MVP-тест обнаружил архитектурный разрыв:
ENIGMA реагирует на тон коммуникации, но слепа к содержанию речи.
NPCDialogueSubscriber меняет trust(listener → speaker), но не trust(listener → third_party).

**SUPERBOX-002 — SUPERBOX-013 (S188):** Построен и доказан Epistemic Core:

| Примитив | Назначение |
|----------|------------|
| Proposition | Чистая семантика (subject, predicate, object, polarity) |
| ClaimEvent | Контекст передачи (speaker, listener, proposition, speech_act) |
| EpistemicRecord | Субъективное убеждение (confidence, source, provenance) |
| BeliefRevisionEngine | Детерминированная ревизия (reliability × claim_weight) |
| EpistemicStore | In-memory хранилище убеждений (read-only для DecisionHub) |
| ClaimEventSubscriber | Адаптер EventBus → Epistemic Core |
| EpistemicContextResolver | Store → Context (семантическая проекция) |
| EpistemicContext | Decision-relevant projection (threats, allies, violations) |
| epistemic_modifiers | Dict[str, float] — нейтральная деформация для DecisionHub |
| apply_modifiers (pure) | Чистая функция, аддитивная, коммутативная, не мутирующая |

**Modifier Contract v1:**
> DecisionHub принимает независимые числовые деформации пространства
> intent scores. Модификаторы аддитивны, детерминированы, коммутативны
> и не мутируют исходный score-space.

**Архитектурные инварианты:**
1. Claim ≠ Truth
2. Belief ≠ Truth
3. Proposition не мутирует RelationshipStore напрямую
4. SUPERBOX инъецирует ClaimEvent, но не Belief/Relationship/Decision
5. L1 Chronicle не хранит субъективные убеждения
6. confidence ≠ truth probability
7. EpistemicContext не содержит World Truth
8. DecisionHub не знает об EpistemicStore

**Что НЕ доказано:**
- Production-интеграция (EpistemicStore → NpcTickPipeline.run)
- Persistence (save/load)
- Replay determinism
- Control vs Treatment через full GameLoop
- Multi-agent наблюдаемость

#### 6.4. Стабилизация и санация технического долга (S189-S260, STABILIZATION_ROADMAP)

Полный цикл аудита v0.5.3.7.2 — v0.5.3.7.10 закрыт (`STABILIZATION_ROADMAP.md`):
- **LLM & Cache:** C-09..C-12, H-06..H-08 — cache hit-rate разблокирован, write/read в hot-path работает.
- **Replay & Determinism:** H-01..H-05, N-02, N-33 — wall-clock убран (`time.monotonic()`), injectable Clock работает.
- **KernelRNG:** H-26 — Salt в 5 вызовах, коллизии потоков устранены, детерминизм восстановлен.
- **Гейты runtime-логов:** LOG-GATE (`ENIGMA_DISABLE_FILE_LOGS`) и LOG-GATE-UI (диагностика «почему LLM молчит» на splash: модель/CUDA/VRAM/антивирус/порт) — v0.5.3.9.1_ДОВОДКА_2.
- **Техдолг (Phase-0 debt):** mypy --strict в spatial-слоях **79 → 0** (`npc_state.py`, `graph_compiler.py`, `spatial_query_service.py`, `spatial_runtime.py`, `spatial_service.py`); `print()` → logger в `main.py` **36 → 0**; DEBT-IPT-RUFF **24 → 0** (ruff `All checks passed!`).

#### 6.5. Relationship Engine v2 (ТЗ-RE-01) — M0/M1a/M1b

Отдельный трек, идущий параллельно стабилизации:
- **M0 ✅ (ADR-O-369):** контракт Relationship Engine v2, механика отношений как каузально-обусловленного слоя (не стат-блока).
- **M1a ✅ (ADR-O-370):** `RelationshipStateStore` как единый SSOT отношений.
- **M1b — в процессе (ADR-O-371-серия):** `RelationshipWriteGate` + миграционный адаптер — **single-writer, caller-guard** (prимая мутация стор запрещена). Стор: `git show 17930e9f`, адаптер `53183000`, WriteGate `73e0539f`.

#### 6.6. World Embodiment Foundation (W-TRACK) — dormant substrate (ADR-O-371)

Субстрат WORLD-домена положен без runtime-потребителей (доктрина dormant-substrate):
- `architecture/world.yaml`, `WorldObjectStore`, 30 тестов, топология. IPT 45/45 сохраняется.
- Следующие (включ. W2 AffordanceResolver, W3 transition_object + causal writer) — отдельным треком, **не форсировать** до этого.

#### 6.7. Фаза 0 — разморозка симуляции (S260+, last session)

Пост-аудит живого рантайма выявил артефактные «0 decisions» и «⏸ traversal». Разобрано:
- **0.1 BREAK-1:** симуляция не мертва — smoke даёт **6/6 решений**; «0 decisions» — артефакт player-turn пути и счётчика [R3_DIRECT].
- **0.3: 3 реальных бага устранены** — (a) `social_subscriber.py` None-стор больше не оборачивается в `RelationshipWriteGate`; (b) `mvp_tavern_controller.py` DEATH только по `life_status==DEAD` (SSOT VitalStateEvaluator), не по `hp<=0`; (c) `domain_phases.py` eco-стресс идёт через `StateApplicator.apply_deltas_only` (стресс больше не теряется).

### Итоги Эпохи 6

- **Stable baseline: IPT 45/45 passed** (было 39/0); ruff чист; mypy --strict spatial 0
- Property-based testing (PBT), Replay system, Causal probes в production, ADR-Net graph
- **Epistemic Core доказан** (13 экспериментов SUPERBOX-001..013)
- **Modifier Contract v1** зафиксирован
- **Relationship Engine v2**: M0 ✅, M1a ✅, M1b (WriteGate) в процессе
- **W-TRACK**: WORLD-домен субстрат положен (dormant)
- **Фаза 0 разморозки**: 3 бага устранены, симуляция жива в smoke
- LOG-GATE / LOG-GATE-UI — диагностика LLM-сервера на splash

---

## ЭПОХА 7: VERTICAL SLICE И PROPHECY SYSTEM (v7.5 — v8.0)

**Девиз:** «Эффект бабочки как играбельная механика, игрок — творец будущего»

### Контекст

Инфраструктура готова. Архитектурно система поддерживает emergent narrative через L1Chronicle → PatternDetector → BeliefEngine → DecisionHub. Но это не показано игроку. Нужна **демонстрируемая механика эффекта бабочки**.

### Главные сдвиги

#### 7.1. Vertical Slice "Люся и 3 парня" (v7.5)

Одна девушка, 3 кандидата (Торнин, Борко, Тень), 30 минут геймплея. Цель: доказать, что effect butterfly работает.

- Многомерные отношения (не одно число, а multidimensional: trust, attraction, debt, fear, gratitude)
- Долговременная интеграция (L2.5 beliefs о каждом из парней)
- `LifeProject` FSM с state `CHOOSING_PARTNER`
- Записанная emergent story, которой не было в коде

#### 7.2. Prophecy System (v8.0) — Killer Feature

**Новая механика:** Игрок не знает будущего (он не DM). Игрок **утверждает** будущее ("Торнин предаст тебя").

**Архитектура:**
- `PROPHECY` InterventionEvent — новый тип
- Belief "future_as_asserted_by_player" — кристаллизуется в L2.5
- Confirmation bias в perception — NPC интерпретирует будущие действия через lens предсказания
- ×6 trauma multiplier → NPC может уйти от партнера даже без реального предательства

**Это работает только в эпистемически честной симуляции.** В AI Dungeon LLM просто сгенерит нарратив. В ENIGMA belief кристаллизуется, проходит через Triple Membrane, искажает восприятие, меняет решения.

**Новый ADR:**
- **ADR-O-330: Prophecy Causality Law** — утверждение игрока становится belief, belief искажает perception, perception меняет decision. Self-fulfilling prophecy через epistemic architecture.

### Итоги Эпохи 7

- Vertical slice demo reel
- Prophecy System — механика, которой нет нигде в геймдеве
- Эмерджентная нарративная драма
- Культивация cult-аудитории через YouTube-сессии

---

## ЭПОХА 8: WORLD CHRONICLE И ГЕНЕРАЦИОННАЯ ГЛУБИНА (v8.5 — v9.0)

**Девиз:** «Рождение и смерть, смена поколений, унаследованные убеждения»

### Контекст

Vertical slice доказал, что краткосрочная эмерджентность работает. Но "эффект бабочки через поколения" требует **горизонта времени** в 1000+ тиков и **передачи идентичности** от NPC к NPC.

### Главные сдвиги

#### 8.1. WorldChronicle (TZ-02 реализация)

Основано на `VZ/ТЕХЗАДАНИЕ ПРЕЕМНИКУ TZ-02 V.2.0`:

- `WorldChronicleStore` — append-only SQLite для событий мира (не NPC, а мира)
- `WorldChronicleEvent` DTO с tick_id, location, participants, consequences
- 4 стадии:
  - **Stage 1:** Birth & Death Registration (`birth_tick`, `death_tick`, `generation` в NPCState)
  - **Stage 2:** Aging (AGE_TICKS_PER_YEAR, age_years, физиологические + когнитивные effects)
  - **Stage 3:** Lineage & Succession (наследник наследует 0.5× CrystallizedBelief родителя + relationship_cache с `inherited=True`)
  - **Stage 4:** Integration & ADR-O-312

#### 8.2. Memetic Domain (TZ_MEMETIC_01-03 реализация)

Основано на `VZ/TZ_MEMETIC_01_Domain_Spec.md` (1995 строк):

- **Ontology:** Concept → Expression → Spread → Crystallization → Extinction
- **Persistence:** 3-layer Canon/History/State
- **Cultural Pressure Accumulator** — per event × community
- **Memetic Burst pipeline** — детерминированный триггер → LLM-генерация → валидация → реестр
- **Bass diffusion adoption dynamics**
- **Player-created memes** с adoption backpressure

#### 8.3. Унаследованные убеждения и кровная месть

- NPC помнит прадеда через `family_chronicle`
- Кровная месть передаётся (если отец убит — сын наследует belief "X — враг")
- Секреты передаются как memetic inheritance
- Игрок через 1000 тиков встречает NPC, чьего прадеда он предал — и NPC "знает" это через family chronicle

### Итоги Эпохи 8

- NPC рождаются и умирают
- Смена поколений (3-5 поколений за кампанию)
- Унаследованные убеждения и кровная месть
- Memetic domain — культурная эволюция
- Эмерджентная история длиной в поколениях

---

## ЭПОХА 9: ПОЛНОЦЕННОЕ ОБЩЕСТВО (v9.5)

**Девиз:** «20-30 живых NPC, фракции, экономика, политика»

### Контекст

Генерационная глубина работает для семьи из 3-5 NPC. Но "эффект бабочки через общество" требует масштаба. Это **Crusader Kings 3 level** — но с LLM и эпистемической честностью.

### Главные сдвиги

#### 9.1. Фракции как first-class entities

- `Faction` — социальная единица с целями, ресурсами, репутацией, иерархией
- `FactionMembership` — NPC может быть членом нескольких фракций с разными ролями
- `FactionDecision` — решения фракции (голосования, указы, союзы)
- Already partial: `FactionAlignmentTracker`, `ReputationEngine`

#### 9.2. Экономика как driver поведения

- Ресурсы (золото, еда, информация, долги)
- Торговля как social interaction
- Бедность/богатство как driver решений (NPC может пойти на преступление от голода)
- Already partial: `EconomyTracker`, `TradeResolver`, `TransactionEngine`

#### 9.3. Политика

- Голосования во фракциях
- Законы как norms с adoption dynamics (через memetic domain)
- Союзы и войны между фракциями

### Итоги Эпохи 9

- 20-30 живых NPC одновременно
- 3-5 фракций с динамикой
- Экономика как emergent driver
- Политические решения через голосования

---

## ЭПОХА 10: §18 — РЕСУРСНО-ОГРАНИЧЕННЫЙ ЭПИСТЕМИЧЕСКИЙ ВЫБОР (v10.0+)

**Девиз:** «NPC выбирает, что помнить, исходя из ценности информации»

### Контекст

Основано на `VZ/TZ_§18_Resource_Bounded_Epistemic_Selection_Law.md` (1543 строки). Документ явно помечен: **"ВНЕДРЯТЬ НЕЛЬЗЯ"** до завершения Belief Layer. После Эпохи 8 (генерационная глубина + memetic) Belief Layer будет завершён.

### Формула закона

```
U_M(m, c) = I(m, c) · R(m) · U(c) − C(m, c)

где:
  I — relevance (релятивность воспоминания к контексту)
  R — reliability (надёжность воспоминания, включая causal decay)
  U — uncertainty (неопределённость текущего наблюдения)
  C — cost (стоимость извлечения и обработки)

Активация: m участвует в inference ⟺ U_M(m, c) > 0
```

### Главный сдвиг

**NPC не обязан использовать всю доступную ему информацию.** Он выбирает информационную архитектуру, исходя из ожидаемой ценности информации и стоимости её обработки.

Это модель **bounded rationality** из cognitive science (Simon, Kahneman) — но применённая к NPC симуляции. NPC с усталостью, стрессом, ограниченным вниманием выбирает, какие воспоминания активировать.

### Итоги Эпохи 10

- NPC "думает" ограниченно — как человек
- Усталость влияет на качество решений
- Стресс искажает retrieval памяти
- Психологически правдоподобная когнитивная экономика

---

## ЭПОХА 11+: НЕОГРАНИЧЕННАЯ ЭВОЛЮЦИЯ (v11.0+)

**Девиз:** «За горизонтом текущего видения»

Возможные направления (не зафиксированы в TZ):

1. **LLM Pipeline v2 (TZ `ENIGMA_LLM_PIPELINE_TZ_v1.md`)** — constrained generation, semantic cache (BGE-small-ru + FAISS), grammar-constrained JSON. Latency P50 <2.5 сек, cache hit rate ≥35%.

2. **Female-Targeted Dark Fantasy Layer (TZ `ENIGMA_TZ_Female_Targeted_Dark_Fantasy_Layer.pdf`)** — 113 страниц, V.1.0 стратегический план. Romance, drama, dark fantasy, gothic, romantic suspense. 6 доменов.

3. **AWC Process/World Model (TZ `AWC_Process_World_Model_TZ.pdf`)** — Process/WorldGraph/NPCKnowledge. Не реализован.

4. **Map Editor Smart Validation (TZ `ENIGMA_MAP_EDITOR_SMART_VALIDATION.md`)** — BedRegistry, валидатор, auto-cut стен.

5. **Textures & Geometry (TZ `VZ/TEXTURES_AND_GEOMETRY_TZ.md`)** — BodySchema, layered textures, composite 2D model rendering. Phase 3 план.

---

# ЧАСТЬ III. КАРТА ЭПОХ

## Сводная таблица

| Эпоха | Версия | Сессии | Главная тема | Главный артефакт |
|-------|--------|--------|--------------|------------------|
| 1 | v0.x | S04-S82 | Каузальный фундамент | SpatialService, body_state, Dual-Time |
| 2 | v0.5.x | S83-S104 | Чистота ядра | TickState/TickMutation, KernelRNG, L1Chronicle |
| 3 | v0.5.3.x | S105-S125 | Идентичность | BeliefCrystallization, Triple Membrane, Embodied Traversal |
| 4 | v0.5.3.x | S126-S141 | Восприятие | 5-layer Reality→Perception, World Continuity |
| 5 | v0.5.3.6.x | S142-S147 | Санация | V8.x closure, Workplace Affordance |
| **6** | **v0.5.3.7.x → v0.5.3.9.2** | **S148-S270+** | **Стабилизация + Infrastructure + Epistemic Core** | **IPT 45/45, PBT, Replay, Probes, ADR-Net, Proposition Layer, mypy --strict spatial 0** |
| **7** | **v7.5-v8.0** | — | **Vertical Slice + Prophecy** | **Killer Feature: player-as-prophet** |
| **8** | **v8.5-v9.0** | — | **Генерационная глубина** | **WorldChronicle, Memetic, Lineage** |
| **9** | **v9.5** | — | **Полноценное общество** | **Factions, Economy, Politics** |
| **10** | **v10.0+** | — | **§18 Epistemic Selection** | **Bounded rationality для NPC** |
| 11+ | v11.0+ | — | Неограниченная эволюция | LLM Pipeline v2, Female Fantasy Layer, ... |

## Граф зависимостей между эпохами

```
Эпоха 1 (Каузальный фундамент)
    ↓
Эпоха 2 (Чистота ядра) — требует честную физику
    ↓
Эпоха 3 (Идентичность) — требует детерминированное ядро
    ↓
Эпоха 4 (Восприятие) — требует богатую идентичность
    ↓
Эпоха 5 (Санация) — требует законченную архитектуру
    ↓
Эпоха 6 (Infrastructure) — требует stable baseline
    ↓
Эпоха 7 (Prophecy) — требует infrastructure для валидации
    ↓
Эпоха 8 (Generations) — требует Prophecy для драмы
    ↓
Эпоха 9 (Society) — требует generations для масштаба
    ↓
Эпоха 10 (§18) — требует завершённый Belief Layer
```

---

# ЧАСТЬ IV. ИЗВЛЕЧЁННЫЕ АРХИТЕКТУРНЫЕ ИСТИНЫ

После 300+ сессий система эмпирически пришла к 5 непреложным фактам (из `MUTATIONS.md`):

## Истина 1: Истина = Snapshot + Chronicle

State эфемерен и перезаписываем. Identity — append-only история. Это раздвоение онтологии: каждое состояние мира — это **проекция истории** в текущий момент. Не существует "текущего состояния" независимо от того, как мы к нему пришли.

## Истина 2: Время и Физика — одно целое

Независимых `resolve(entity, dt)` слоев не существует. Физика считается только внутри Causal Kernel. Нельзя "обновить позицию" отдельно от "обновления времени" — это один акт.

## Истина 3: Нет Event Sourcing для State (но есть для Identity)

State не восстанавливается из событий — он перезаписывается. `delta_buffer.clear()` уничтожает дельты после применения. Но Identity — event-sourced. L1Chronicle — append-only. Это **асимметрия**: state мимолётен, identity вечен.

## Истина 4: Симптом не является причиной

Фикс должен падать на ПЕРВЫЙ отказавший узел pipeline, а не латать UI. Если игрок видит "NPC не двигается" — проблема не в рендере. Проблема в `MovementIntent`, который не дошёл до `MovementEngine`. UI — симптом, не болезнь.

## Истина 5: Вакуум — это локальный разрыв

Unknown ≠ Neutral(0.0). Отсутствие данных не конвертируется в глобальные аккумуляторы. Если NPC не знает о событии — его `fear` не становится 0. `fear` остаётся тем, чем был. Вакуум — это локальный разрыв в каузальной цепи, не глобальный ноль.

---

# ЧАСТЬ V. ФИЛОСОФСКИЙ ИТОГ

## Что построено за 6 эпох

ENIGMA — это не "игра с LLM". Это **первая попытка построить эпистемически честную симуляцию**, где:

1. **Каузальная честность** — каждое изменение имеет причину (Invariant I)
2. **Историческая честность** — будущее считается из прошлого, не из вакуума (Invariant II)
3. **Временная изоляция** — шаг симуляции неизменяем во время вычисления (Invariant III)
4. **Семантическая валидность** — структурно корректное, но невозможное состояние отвергается (Invariant IV)
5. **Эпистемическая честность** — никто не знает больше, чем должен (Triple Membrane, DM Boundary)
6. **Идентификационная честность** — личность — это история, не состояние (L1Chronicle)
7. **Восприятийная честность** — наблюдатель видит проявления, не ментальные поля (5-layer architecture)

## Что будет построено в будущих эпохах

| Эпоха | Что добавляет к "честности" |
|-------|-----------------------------|
| 7 | Пророческая честность — утверждение будущего через belief, не через script |
| 8 | Генерационная честность — идентичность переживает смерть через наследование |
| 9 | Социальная честность — фракции и экономика как emergent drivers |
| 10 | Когнитивная честность — bounded rationality, NPC выбирает, что помнить |
| **11+** | Неограниченная эволюция — LLM Pipeline v2, Female Fantasy Layer (Goran Beta), ... |

## Главная идея

**ENIGMA — это не продукт, это исследование.** Каждая эпоха — это ответ на вопрос "можно ли честно симулировать X?". После 6 эпох мы знаем: можно честно симулировать физику, идентичность, восприятие, презентацию, инфраструктуру и эпистемическую причинность. После Эпохи 10 мы будем знать: можно ли честно симулировать общество и когнитивную экономику.

Это **исследование границ честной симуляции**. Если оно дойдёт до v10.0 — это будет **первая LLM-driven simulation с эпистемической честностью на горизонте поколений**.

Versu закрылся. Façade остался academic demo. Prom Week — paper. NVIDIA ACE — middleware без игры. AI Dungeon — без инвариантов. У ENIGMA есть шанс занять **пустующее место**.

---

# ФИНАЛ

6 эпох уже пройдено. 5 эпох впереди. Каждая эпоха — это **не просто код**, это **онтологическое расширение**: система начинает моделировать то, чего не моделировала раньше.

Эпоха 1: моделирует пространство.
Эпоха 2: моделирует детерминизм.
Эпоха 3: моделирует идентичность.
Эпоха 4: моделирует восприятие.
Эпоха 5: моделирует MVP.
Эпоха 6: моделирует саму себя (инфраструктура) + эпистемическую причинность (Proposition Layer).
Эпоха 7: моделирует будущее (Prophecy).
Эпоха 8: моделирует поколения.
Эпоха 9: моделирует общество.
Эпоха 10: моделирует ограниченный разум.

Это **постепенное онтологическое расширение**. Каждая эпоха делает систему чуть более честной, чем предыдущая. Это не "добавление фич" — это **углубление модели реальности**.

И в этом — уникальность ENIGMA.

---

*Доклад подготовлен на основе `MUTATIONS.md`, `ADR Master Index`, `00_CAUSAL_CONTRACT_v2.0.md`, `ENTITY_CONTINUITY_CONTRACT.md`, и TZ-документов из `docs/Почти Актуальные TZ/`. Все ссылки на сессии (S04-S270+), ADR и файлы точны на момент v0.5.3.9.2.*

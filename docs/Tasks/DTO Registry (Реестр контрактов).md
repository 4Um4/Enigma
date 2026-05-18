Вот переработанный и реструктурированный реестр DTO. 
**Что было сделано:**
1. **Архитектурная группировка:** Вместо хронологического списка, DTO разбиты на логические слои (Ядро домена, Фаза 8/Каузальность, NPC Проецирование, События, Пространство, API, Фронтенд, CFRM). Это позволяет ИИ сразу понимать контекст принадлежности структуры.
2. **Интеграция обновлений:** Блок "Session 18 Updates" и другие исторические вставки влиты прямо в актуальные контракты. Никаких "добавлено в сессии X" — только финальное состояние.
3. **Форматизация:** Строгое использование синтаксиса `поле: Тип = default // Описание`. Депрекированные поля помечены `[DEPRECATED]`, планируемые — `[PLANNED]`.
4. **Очистка:** Убраны дубликаты, противоречивые даты и лишний мусор.

---

# DTO Registry (Реестр контрактов ENIGMA)
*Актуально на: 10.05.2026*

## I. Core Domain: Мутации и Семантика (DRSL)

### StateDeltas (v2: Domain-Tagged Typed Payloads)
*Контракт изменения состояния. v1 поля LOCKED и депрекированы.*

- **npc_id**: `Optional[str]` // ОБЯЗАТЕЛЬНО для маршрутизации. None только для глобальных дельт.
- **domain**: `Optional[DeltaDomain]` // v2: социальный, эмоциональный и т.д.
- **target**: `Optional[str]` // v2: универсальный таргет (player, npc_id, faction_id).
- **payload**: `Optional[DeltaPayload]` // v2: Union[SocialPayload, EmotionPayload, ReputationPayload, IdentityPayload, PhysiologyPayload]
- **source**: `str`

**v1 backward compat [DEPRECATED]:**
- `intent_target`, `social_target`, `faction_id`, `stress_delta`, `stress_delta_effective`, `emotion_delta`, `emotion_tag`, `trust_delta`, `fear_delta`, `reputation_delta`, `trait_updates`, `new_trauma`, `identity_integrity_delta`, `pressure_resistance_delta`, `will_state_override`

**Валидация `__post_init__`:** 
- v2: Если `payload` не None, его тип должен соответствовать `domain` (иначе TypeError).
- v1: Один тип таргета, `reputation_delta` требует `faction_id`, `trust/fear ≠ faction_id`.

### DeltaDomain (Enum)
```python
SOCIAL = "social"
EMOTION = "emotion"
REPUTATION = "reputation"
IDENTITY = "identity"
PHYSIOLOGY = "physiology"
SPATIAL = "spatial"
PERCEPTION = "perception"  # ADR-040: Обновление субъективной модели восприятия (PerceptualKernel)
```

### ReductionPolicy (Enum) — DRSL
```python
ADDITIVE = "additive"               # Социальный, Репутация (Σ)
BOUNDED_ADDITIVE = "bounded_additive" # Эмоция (Σ + clamp)
OVERWRITE = "overwrite"             # Идентичность, Пространство (last-write-wins)
PHYSICS_COMPOSITE = "physics_composite" # Физиология (S_t = F(S_{t-1}, impacts)). Обходит merge.
```

### DELTA_POLICY_REGISTRY
```python
SOCIAL -> ADDITIVE
EMOTION -> BOUNDED_ADDITIVE
REPUTATION -> ADDITIVE
IDENTITY -> OVERWRITE
PHYSIOLOGY -> PHYSICS_COMPOSITE
SPATIAL -> OVERWRITE
```

### Payloads (Frozen Dataclasses)

**SocialPayload**
- `trust_delta`: `float = 0.0`
- `fear_delta`: `float = 0.0`
- `affection_delta`: `float = 0.0`
- `debt_delta`: `float = 0.0`

**EmotionPayload**
- `stress_delta`: `float = 0.0`
- `emotion_delta`: `float = 0.0`
- `emotion_tag`: `Optional[str] = None` // "panic" при shock > 0.5
- `new_trauma`: `Optional[str] = None`

**ReputationPayload**
- `reputation_delta`: `float = 0.0`

**IdentityPayload**
- `identity_integrity_delta`: `float = 0.0`
- `pressure_resistance_delta`: `float = 0.0`
- `will_state_override`: `Optional[str] = None`
- `recent_directive_data`: `Optional[Dict[str, Any]] = None` // ADR-056: Труба захвата внимания. Формат: {"source": str, "salience": float, "interrupts_routine": bool}`
- `aggression_inhibition_delta`: `float = 0.0` // ADR-049
- `compliance_bias_delta`: `float = 0.0` // ADR-049
- `initiative_suppression_delta`: `float = 0.0` // ADR-049`

**PerceptionPayload** (ADR-040: Реальность → Восприятие)
- `threat_gradient_delta`: `float = 0.0` // Рост ощущения угрозы
- `uncertainty_delta`: `float = 0.0` // Рост неопределённости
- `anomaly_score_delta`: `float = 0.0` // Рост ощущения аномальности
- `dominant_emotion_hint`: `Optional[str] = None` // Подсказка для DecisionHub (fear/panic)

**PhysiologyPayload** (Заменила CombatPayload)
```
- `hp_delta`: `float = 0.0` // Макро-LOD: агрегированная потеря функции
- `pain_delta`: `float = 0.0` // 0-100
- `fatigue_delta`: `float = 0.0` // 0-100
- `blood_loss_delta`: `float = 0.0` // 0-1.0
- `shock_impulse`: `float = 0.0` // 0-1.0, физический шок (сигнал для ReactionSubscriber)
- `add_injuries`: `Tuple[InjuryDTO, ...] = ()`
- `add_statuses`: `Tuple[str, ...] = ()` // bleeding, unconscious, crippled, stagger
- `remove_statuses`: `Tuple[str, ...] = ()`

### InjuryDTO (Frozen Dataclass)
- `damage_type`: `str` // slash, blunt, pierce, burn, crush
- `target_zone`: `str` // head_eye_l, torso_groin, arm_r (функциональная зона)
- `structural_damage`: `float` // 0.0 - 1.0 (разрушение тканей)
- `functional_loss`: `float` // 0.0 - 1.0 (потеря функции)
- `critical_effects`: `Tuple[str, ...]` // severed, bleeding, infected

---

## II. Фаза 8: Каузальность и Обработчики

### Phase8Context (Frozen — READ-ONLY для обработчиков)
- `all_npcs_raw`: `List[dict]`
- `all_npc_contexts`: `List[dict]`
- `shared_context`: `Any`
- `campaign_id`: `str`
- `tick_ctx`: `Any`
- `physical_deltas_materialized`: `Tuple[StateDeltas, ...] = ()` // Иммутабельный снимок Physical Layer (t) для Cognitive Layer

### Phase8Result
- `deltas`: `List[StateDeltas] = field(default_factory=list)`
- `perceiving_npc_ids`: `Optional[Set[str]] = None`
- `socially_affected_npc_ids`: `Optional[Set[str]] = None`
- `events_processed`: `int = 0`
- `prop_dirty`: `bool = False` // [DEPRECATED]

### TickOrchestrator._phase_8_drain_secondary (Layered Reduction)
Порядок слоёв:
1. **Perception Layer:** `_execute_phase8_handler(perception_sub)`
2. **Physical Layer:** `_execute_phase8_handler(combat_sub)` → materialization → tuple
3. **Cognitive Layer:** `_execute_phase8_handler(reaction_sub, physical_deltas_materialized)`
4. **Social Layer:** `_execute_phase8_handler(social_sub, physical_deltas_materialized)`

### CombatSubscriber (Phase8Handler)
- **name**: `"combat"`
- **Подписка:** `PLAYER_ATTACKS`, `PLAYER_ATTACKED`, `COMBAT`
- **Экстракция:** Извлекает `ImpactIntentDTO` из `EventDTO.payload`. Если `actor_id` не в `npc_by_id` → идеальный player snapshot (dexterity=12, strength=15). Отсутствие `target_id` → skip.
- **Выход:** `Phase8Result(deltas=List[StateDeltas])` (ТОЛЬКО Physiology-дельты, No Domain Leakage).

### ReactionSubscriber (Phase8Handler)
- **name**: `"reaction"`
- **Каскад Force → Pain → Shock → Emotion:**
  - Извлекает `shock_impulse` из `ctx.physical_deltas_materialized`.
  - Группирует по `npc_id`.
  - Если `npc_id == target`: шок от собственной боли.
  - Если `npc_id != target`: эмпатический ужас от шока цели.
  - `shock > 0` → `stress_delta += shock * 30.0 * modifier`, `fear_delta += shock * 15.0 * modifier`.
  - `shock > 0.5` → `emotion_tag = "panic"`.
- **Модификатор:** `_compute_reaction_modifier(npc_dict) → float`
  - `modifier = composure_factor * fear_factor * willpower_factor`
- **Маршрутизация:** source=player → `intent_target="player"`; source=NPC → `social_target=source_id`

---

## III. NPC State, Маппинги и Конфиги

### NPCState (backend/app/models/npc_state.py)
- `body_state`: `Dict[str, Any]` // Рантайм-контейнер: current_hp, pain, fatigue, blood_loss, consciousness, injuries, modifiers, statuses

### NPCStateSnapshot (TypedDict — READ-ONLY проекция для idle handlers)
- `npc_id`: `str`
- `stress`: `float`
- `relationship_cache`: `Dict[str, Any]` // {target: {trust, fear, base_trust, ...}}
- `base_values`: `Dict[str, Any]` // {target: base_trust, ...} для drift-расчёта
- `faction_affiliations`: `List[str]`
- `hp`: `float`, `max_hp`: `float`
- `pain`: `float`, `fatigue`: `float`, `blood_loss`: `float`, `consciousness`: `float`
- `injuries_by_zone`: `Dict[str, List[Dict[str, Any]]]` // Группировка по target_zone
- `base_abilities`: `Dict[str, float]` // Из body_profile. НЕ ВЫЧИСЛЯТЬ effective в снапшоте!
- `modifiers`: `Dict[str, float]` // Из body_state
- `statuses`: `List[str]` // stagger, unconscious, bleeding

### NPC Archetype JSON Config (Мигрировано на body_profile)
```json
"body_profile": {
  "max_hp": 100,
  "abilities": {
    "strength": 10, "dexterity": 10, "constitution": 10,
    "intelligence": 10, "wisdom": 10, "charisma": 10
  },
  "base_ac": 10
}
```
*(Секция `combat_stats` УДАЛЕНА)*

### NPC Data Mappings (_build_npc_snapshots)
- `social_stats.trust` → `relationship_cache["player"]["trust"]`
- `social_stats.fear_of_player` → `relationship_cache["player"]["fear"]`
- `psyche.loyalty_true` → `base_values["player"]`
- `body_profile.*` / `body_state.*` → Поля NPCStateSnapshot (см. выше).
- Player entry ГАРАНТИРОВАН даже при наличии NPC→NPC записей.

### _enrich_with_social_relations (npc_loader.py)
- Вызывается при загрузке. Мутирует in-place.
- Формат: `relationship_cache[target_id] = {trust: base_trust*100, fear: 0.0, base_trust: base_trust*100, nature: str}`
- Шкала: 0-1 (JSON) → 0-100 (relationship_cache). Конвертация ×100.

---

## IV. События и Действия (Input Stream)

### EventDTO (Устав §2.1)
- `id`: `UUID`
- `type`: `str` // Использовать `EventType.PLAYER_ATTACKS.value`
- `source`: `str` // player_name | npc_id
- `timestamp`: `float`
- `payload`: `Dict[str, Any]` // Для `player_attacks`: intensity, actor_id, target_id
- `visibility`: `Literal["public", "private", "whisper"]`
- `radius`: `float`
- `persistence_level`: `Literal["working", "session", "campaign"]`

### ImpactIntentDTO
- `actor_id`: `str`, `target_id`: `str`
- `damage_type`: `str` // slash, blunt, pierce, burn, crush
- `target_zone`: `Optional[str]` // None = случайная по весам
- `force`: `float` // 0.0 - 100.0
- `weapon_reach`: `float = 1.0`

### ContactLevel (Enum)
`MISS`, `GLANCING`, `PARTIAL`, `SOLID`, `PERFECT` (Замена RPG Hit Roll)

### ACTION_INTENSITY (domain/constants.py)
`dict[str, float]`. Ключи: `player_attacks`, `player_threatens`, `dialogue`, `attack`, `move`, `stealth` и др. Fallback = 0.2.

### EventBus (CFRM Extensions — P2 Deobjectification Bridge)
- `attach_cfrm_bridge(bridge: Callable[[EventDTO], None])`: Привязывает функцию-мост деобъективации на время тика.
- `detach_cfrm_bridge()`: Отвязывает мост (гарантированно вызывается в `finally` блоке `TickOrchestrator`).
- **Поведение `publish()`:** Если `_cfrm_bridge` привязан, автоматически вызывает `bridge(event)` для трансформации объективного события в возмущение поля (`FieldDisturbance`).

---

## V. Пространство и Движение

### MovementIntent (LOD1: Macro Traversal & LOD0: Micro Steering)
*Используется ТОЛЬКО для перемещения между узлами макро-графа. ЗАПРЕЩЕНО для микро-перемещений (target == from).*

### SceneChange(field="position")
*Статус: РАЗРЕШЕНО. Атомарно обновляет узел и резолвит `local_position` (x,y) через SpatialService.*

### TraversalState [PLANNED]
- `npc_id`: `str`, `path`: `list[tuple[float, float]]`, `current_index`: `int`, `speed`: `float`, `started_at`: `int`, `target_node`: `str`, `locomotion`: `str` (WALK, RUN, SNEAK), `status`: `str` (PENDING, MOVING, ARRIVED, CANCELLED), `arrival_threshold`: `float` (0.3m)

### MovementStep [PLANNED]
- `npc_id`: `str`, `from_xy`: `tuple[float, float]`, `to_xy`: `tuple[float, float]`, `delta_seconds`: `float`, `traversal_id`: `str`

### LocalSteeringIntent [REJECTED - ADR-052]
*Архитектурное решение: Микро-движение (LOD0) реализовано через существующее поле `local_target_xy` в `MovementIntent` (см. ADR-052). Создание отдельной сущности признано расщеплением Единого Пространственного Авторитета.*
*Для визуального сближения внутри макро-зоны без изменения `position`.*
- `npc_id`, `target_entity_id`, `target_xy`, `speed`, `arrival_radius`

---

## VI. Game Loop, API и Persistence

### WorldSnapshotDTO
- `tick`: `int`
- `version`: `int`
- `last_event_id`: `Optional[UUID]`
- `player_position`: `Tuple[float, float]`
- `npc_positions`: `List[NPCPositionDTO]`
- `avatar_state`: `Optional[AvatarStateDTO] = None` // ADR-035: Феноменологическая проекция аватара
- `ambient_phenomenology`: `Optional[Dict[str, float]] = None` // ADR-040: Средовое давление (температура, плотность)
- `visible_events`: `List[VisibleEventDTO]`
- `available_actions`: `List[str]`
- `location_id`: `str`
- `weather`: `str`
- `time_of_day`: `str`
- `game_time_seconds`: `int = 0` // Абсолютное время симуляции
- `active_traversals`: `List[Dict] = field(default_factory=list)` // ADR-019: Транзиты для визуального Lerp. Структура dict: `npc_id, from_xy, to_xy, duration_seconds, started_at` (Добавлено в Сессии 29), `locomotion`.

### NPCPositionDTO
- `npc_id`: `str`, `x`: `float`, `y`: `float`, `location_id`: `str`, `facing`: `str`, `action`: `str`
- `display_name`: `str` // КРИТИЧЕСКИ ВАЖНО: заполнять из `data.get("name")`, иначе фронтенд показывает npc_id!

### PhysicalPresentationState (Enum)
*Визуальное физическое состояние аватара для рендера.*
- `HEALTHY`, `WOUNDED`, `BLEEDING`, `CRIPPLED`, `DYING`

### MentalPresentationState (Enum)
*Визуальное ментальное состояние аватара для рендера.*
- `CALM`, `STRESSED`, `PANICKED`, `DISSOCIATING`, `BROKEN`

### AvatarStateDTO (Frozen Dataclass — Феноменологическая проекция ADR-035, ADR-040)
*Перевод Simulation Truth в Rendering Projection. Фронтенд не знает о HP или pain.*
- `physical_state`: `PhysicalPresentationState`
- `mental_state`: `MentalPresentationState`
- `perceptual_stability`: `float` // 0.0-1.0 (1.0 = кристально чистое восприятие)
- `cognitive_coherence`: `float` // 0.0-1.0 (0.0 = диссоциация)
- `sensory_noise`: `float` // 0.0-1.0 (звон, пятна, глушение)
- `motor_disruption`: `float` // 0.0-1.0 (тремор, замедление моторики)
- `perceptual_latency`: `float` // 0.0-1.0, задержка сборки реальности
- `reality_reconciliation_rate`: `float` // 0.0-1.0, скорость восстановления когерентности
- `blood_visibility`: `float` // 0.0-1.0, кровь на экране/персонаже
- `breathing_profile`: `str` // calm, heavy, gasping, hyperventilating
- `posture_state`: `str` // upright, hunched, collapsed

### TurnResult (frontend/game_loop_bridge.py)
- `action_type`: `str = ""`, `npc_reactions`: `list[dict]`, `dm_text`: `str = ""`
- `game_time_seconds`: `int = 0`, `world_snapshot`: `Optional[dict] = None` (Force Merge), `npc_positions`: `Optional[dict] = None` (Force Merge)

### TickResultDTO / TickPlayerResultDTO
- `status`: `str` ("ok" | "error" | "no_scene"), `error`: `Optional[str]`, `changes`: `int` [DEPRECATED]

---

## VII. Frontend Contracts (Presentation Layer)

### NarrativeBeat
- `speaker`: `str` // Извлекается из dm_response через known_names
- `text`: `str`, `is_player`: `bool`, `delivery`: `DeliveryType`, `recognition`: `RecognitionLevel`, `lifetime`: `BeatLifetime`
- `creation_tick`: `int`, `alpha`: `float` (0.0-255.0), `is_fading`: `bool`, `is_active`: `bool`

### _MoveState (Внутренний контракт фронтенда)
- **Навигация:** `target_npc_id: Optional[str]`, `path: Optional[list]`, `path_index: int`
- **Кинетика:** `cooldown: float`, `walk_distance_accumulated: float`
- **Эмбодимент:** `facing_angle: float`, `facing_mode: Literal["VELOCITY", "LOOK_TARGET", "FREE"]`

### Frontend Local Vars
- `known_names`: `Dict[str, str]` // {npc_name.lower(): npc_name}
- `system_log`: `List[str]` // Для Log Layer (движение, ошибки)
- `_time_scale`: `int = 1` // 1, 4, 10, 50

---

## VIII. CFRM: Causal Field Reduction Model (Layer 1 & P1 Bridge)

**Онтологический постулат:** NPC operate on perceived causality, not actual causality. Snapshot is belief state derived from CFRM projection.

### ClusterID (Type Alias)
- `str` // Совпадает с `canonical_id` макро-узла (напр. "tavern_silver_wolf:main_hall")

### ClusterDef (Frozen Dataclass — Топология кластера)
- `cluster_id`: `ClusterID`
- `boundary_cells`: `FrozenSet[str]` // Исходящие связи в другие кластеры (прозрачность мембран)
- `version`: `int = 0` // Инкремент при дрейфе (пересечение NPC границ)

### ClusterGraph (Dataclass — Пространственная декомпозиция мира)
- `clusters`: `Dict[ClusterID, ClusterDef]` // Единственная структура мира. НЕ содержит состояния, содержит связи.
- Методы: `get_neighbors(cluster_id) -> Set[ClusterID]`, `update_version(cluster_id)`

### CausalAxis (Enum — Оси причинности)
- `PHYSICAL = "physical"` // Физика мира (удар, движение, шок)
- `COGNITIVE = "cognitive"` // Когнитивная обработка (речь, угрозы, внимание)
- `SOCIAL = "social"` // Социальная физика (слух, доверие, долг)

### EventBuffer (Dataclass — Временный causal input stream P2)
- `physical_disturbances`: `List[FieldDisturbance]`
- `cognitive_disturbances`: `List[FieldDisturbance]`
- `social_disturbances`: `List[FieldDisturbance]`
- Методы: `add(disturbance, axis)`, `drain() -> Tuple[List, List, List]` (Извлекает возмущения и очищает буфер для следующего тика)

### DisturbanceVector (Enum)
- `KINETIC = "kinetic"`
- `ACOUSTIC = "acoustic"`
- `MATTER = "matter"`
- `BEHAVIORAL = "behavioral"`

### FieldDisturbance (Frozen Dataclass — Возмущение причинного поля)
- `origin_cluster`: `ClusterID`
- `disturbance_type`: `CausalAxis`
- `magnitude`: `float`
- `vectors`: `Tuple[DisturbanceVector, ...]`
- `source_entity`: `str`
- `semantic_seed`: `Optional[str] = None` // Геном нарратива: "удар", "кража", "крик". Для SOCIAL/COGNITIVE — обязателен.

### PerceivedPhenomenon (Frozen Dataclass — Субъективный феномен)
- `perceived_intensity`: `float`
- `perceived_archetype`: `str` // Реконструированный смысл: "драка", "чистки", "угроза"
- `mutation_stage`: `int` // Стадия искажения: 0=глазами, 1=с чужих слов, 2=слух
- `distortion_nature`: `str` // Тип трансформации: "energy_loss", "dramatization", "paranoid_inference"
- `phenomenon_type`: `CausalAxis`

### PhenomenologicalState (Dataclass — Локальная истина кластера)
- `threat_level`: `float = 0.0`
- `visible_blood`: `bool = False`
- `dominant_sound`: `Optional[str] = None`
- `anomaly_score`: `float = 0.0`
- `nearby_entities`: `List[str]`

### PsychologicalPressure (Frozen Dataclass — Векторы давления на психику)
- `fear`: `float = 0.0`
- `uncertainty`: `float = 0.0`
- `aggression_trigger`: `float = 0.0`
- `dominance_shift`: `float = 0.0`
- `directive_obedience`: `float = 0.0` // ADR-036: Давление подчинения речевому акту (физика власти)`

### PerceptualKernel (Dataclass — Субъективная модель восприятия NPC)
- `threat_gradient`: `float = 0.0`
- `trust_gradient`: `float = 0.0`
- `uncertainty`: `float = 0.0`
- `anomaly_score`: `float = 0.0`
- `last_hostile_direction`: `Optional[str] = None`
- `dominant_emotion`: `Optional[str] = None`
- `aggression_inhibition`: `float = 0.0` // ADR-049: Топологическое подавление агрессии
- `initiative_suppression`: `float = 0.0` // ADR-049: Подавление воли/инициативы
- `compliance_bias`: `float = 0.0` // ADR-049: Склонность к подчинению`
- `recent_directive`: `Optional[Dict[str, Any]] = None` // ADR-056: Attention Capture. Формат: {"source": str, "salience": float, "interrupts_routine": bool}`

### ClusterOccupancy (Dataclass — Spatial Index O(1))
- `entity_to_cluster`: `Dict[str, ClusterID]` // npc_id/player -> cluster_id
- `cluster_to_entities`: `Dict[ClusterID, Set[str]]` // cluster_id -> set(npc_ids)
- Методы: `update_entity(entity_id, new_cluster)`, `get_cluster(entity_id)`, `get_entities_in_cluster(cluster_id)`, `remove_entity(entity_id)`

### ClassificationSource (Enum — Источник классификации ADR-038)
- `HARD_RULE = "hard_rule"` // Жёсткое правило из словаря
- `FALLBACK = "fallback"` // Fallback для неизвестных событий
- `HEURISTIC = "heuristic"` // Эвристика (заготовка на будущее)

### ClassificationResult (Frozen Dataclass — Эпистемическая оценка ADR-038)
- `axis`: `CausalAxis`
- `confidence`: `float` // 0.0-1.0, уверенность классификации
- `source`: `ClassificationSource`

### classify_event() (Epistemic Bridge ADR-038)
- Сигнатура: `classify_event(event_type: str) -> ClassificationResult`
- Маппит текущие `EventType.value` на оси CFRM с оценкой уверенности. Fallback для неизвестных событий -> `COGNITIVE` (confidence=0.2, source=FALLBACK).
- Сигнатура: `classify_event(event_type: str) -> CausalAxis`
- Маппит текущие `EventType.value` на 3 оси CFRM. Fallback для неизвестных событий -> `COGNITIVE`.

### _TickContext (TickOrchestrator — обновления Сессии 21)
- `event_buffer`: `EventBuffer` // Заполняется через мост _deobjectify_event (EventBus → FieldDisturbance)
- `cluster_occupancy`: `ClusterOccupancy` // Восстанавливается на старте тика из scene_state['npc_positions']

### NpcTickInput (backend/app/services/npc/npc_tick_contracts.py)
Frozen dataclass. Данные для NPC фазы — только чтение.
- `campaign_id`: `str`
- `location`: `str`
- `scene_state`: `dict` // READ-ONLY. Spatial чтение только через NpcTickServices.spatial_query
- `player_target_id`: `Optional[str]`
- `hub_event`: `EventContext`
- `is_session_start`: `bool`
- `action_type`: `str`
- `raw_input`: `str`
- `current_tick`: `int`
- `all_npcs_raw`: `list` // Legacy-dict NPC (shared reference)
- `nearby_npcs`: `list`
- `scene_continuity`: `Any` // SceneContinuity или None
- `spatial_events`: `list` // Для социальных триггеров
- `line_of_sight`: `dict`

### NpcTickServices (backend/app/services/npc/npc_tick_contracts.py)
Frozen dataclass. Сервисы, разрешённые оркестратором ДО вызова фазы.
- `memory_manager`: `Any`
- `relationship_store`: `Any`
- `social_engine`: `Optional[Any]`
- `reputation_engine`: `Optional[Any]`
- `economic_profiles`: `Dict[str, Any]`
- `event_bus`: `Any = None`
- `spatial_service`: `Optional[Any] = None` // SpatialService v1.2 — навигация (граф, узлы)
- `spatial_query`: `Optional[Any] = None` // SpatialQueryService — ADR-048 Authoritative Spatial Spine

### NpcTickBuffer (backend/app/services/npc/npc_tick_contracts.py)
Dataclass. Накопитель результатов NPC фазы — только запись.
- `dirty_npcs`: `set`
- `npc_contexts`: `list`
- `max_npc_stress`: `float = 0.0`
- `activity_overrides`: `Dict[str, str]`
- `communication_intents`: `list` // CommunicationIntent для Фазы 6
- `movement_intents`: `list` // MovementIntent — реактивное движение NPC
- `published_events`: `list` // DEPRECATED: нарушает §5.1

### SpatialQueryService (backend/app/services/spatial/spatial_query_service.py)
Authoritative Spatial Spine (ADR-048). Единственный легитимный способ получить пространственную истину для decision/perception/combat/movement.
- `__init__(npc_positions: Dict[str, dict], cluster_occupancy: Optional[ClusterOccupancy] = None, scene_state: Optional[dict] = None)`
- `get_entity_position(entity_id: str) -> Optional[dict]` // Словарь с 'local_position', 'position', 'node_id'
- `distance(entity_a: str, entity_b: str) -> float` // Евклидово расстояние. 999.0 если данных нет
- `distance_player(npc_id: str) -> float` // Расстояние от NPC до игрока. ADR-048: игрок = entity 'player'
- `player_distances(npc_ids: List[str]) -> Dict[str, float]` // Словарь дистанций от игрока до списка NPC
- `visibility(entity_a: str, entity_b: str) -> bool` // Проверка прямой видимости
- `cluster_relation(entity_a: str, entity_b: str) -> Optional[str]` // 'same', 'adjacent', 'distant', None

---

## IX. Player Entity & WillpowerGate (Hybrid Consciousness)

### Player Avatar (`npc_id="player"`)
Игрок внедряется в `all_npcs_raw` как полноправный агент симуляции.

- **body_profile**: Задается через Archetype (`Laborer`, `Soldier`, `Merchant`, `Drifter`, `Noble`).
- **psyche**: Задается через Temperament (`Fearful`, `Stoic`, `Impulsive`, `Calculating`). Определяет `drives_base` и `willpower`.
- **social_stats**: Формируется динамически. Отношение NPC к игроку подчиняется Social Drift.
- **AvatarAffectiveMemory**: Эмоциональная память аватара. Подвержена затуханию, вытеснению и травмам. Отличается от `PlayerMemory` (памяти человека-игрока).

---

### IntentParametersDTO (Frozen Dataclass — Строгий транспорт семантики ADR-035)
Убивает `Dict[str, Any]` в `IntentDTO.parameters`.

- **semantic_action**: `Optional[str]` # MOVE, THREATEN (извлечено Слоем 1). Критически важно для Физики Власти (ADR-042): триггерит _obedience_pressure.
- **target_reference**: `Optional[str]` # Сырая ссылка: 'тень', 'борко'
- **target_id**: `Optional[str]` # ID цели, найденный Слоем 2 (fuzzy matching)
- **physical_force**: `float = 0.1` # Кинетическая энергия
- **emotional_charge**: `float = 0.1` # Эмоциональный вклад
- **social_pressure**: `float = 0.0` # Социальный вес (для Физики Власти)
- **commitment_level**: `float = 0.8` # Уровень приверженности

### IntentPressureProfile (Frozen Dataclass)
Вектор давления намерения на психику аватара. Вычисляется `IntentPressureResolver`.

    violence: float = 0.0         # 0.0-1.0, физическое насилие
    humiliation: float = 0.0      # 0.0-1.0, унижение (своё или чужое)
    self_risk: float = 0.0        # 0.0-1.0, риск для жизни/здоровья аватара
    social_exposure: float = 0.0  # 0.0-1.0, социальная угроза (позор, изгнание)
    moral_violation: float = 0.0  # 0.0-1.0, нарушение внутренних убеждений
    identity_deviation: float = 0.0 # 0.0-1.0, отклонение от текущей модели Я
    trauma_trigger: float = 0.0     # 0.0-1.0, активация прошлого травматического опыта
    taboo_intensity: float = 0.0    # 0.0-1.0, нарушение культурных/личных табу

---

### WillState (Enum)
Шкала деградации воли. Заменяет бинарные исходы.

    COMPLY = "comply"             # Нет сопротивления
    RELUCTANT = "reluctant"       # Неохота, но делает
    DISTRESSED = "distressed"     # Сильный стресс, слезы, дрожь
    PANICKED = "panicked"         # Паника, иррациональное поведение
    DISSOCIATING = "dissociating" # Отчуждение от действия, "это не я"
    BROKEN = "broken"             # Сломлен, подчиняется безвольно
    CONDITIONED = "conditioned"   # Адаптировался к насилию, привык

---

### OriginLayer (Enum — ADR-040)
*Источник давления на психику аватара.*
- `WILL_CONFLICT = "will_conflict"`
- `AFFECTIVE_RESONANCE = "affective_resonance"`
- `PHYSIOLOGICAL_OVERRIDE = "physiological_override"`

### EmbodiedVector (Enum — ADR-040)
*Предрефлексивный моторный импульс аватара.*
- `AVOIDANCE = "avoidance"`     # Избегание, бегство
- `DESTROY = "destroy"`         # Агрессия, нападение
- `COLLAPSE = "collapse"`       # Падение, обморок
- `SUBMIT = "submit"`           # Подчинение, сдача
- `FREEZE = "freeze"`           # Оцепенение, столбняк

### WillResponseDTO (Frozen Dataclass — Результат работы WillpowerGate)
Возвращается, когда воля игрока проходит через психику аватара.

- `state`: `WillState` — Текущее состояние воли после воздействия
- `resistance`: `float` — 0.0-1.0, вычисленная сила сопротивления (Cumulative Strain)
- `fear_delta`: `float` — Прирост страха
- `identity_damage`: `float` — Урон идентичности (травма)
- `generated_emotions`: `List[EmotionPayload]` — Эмоции, порожденные конфликтом
- `generated_memories`: `List[dict]` — Следы в аффективной памяти аватара (`MemorySeed`)
- `counter_offer`: `Optional[IntentDTO]` — Аватар предлагает альтернативу (убежать, подкупить)
- `narration_hooks`: `List[str]` — Подсказки для LLM (`"плачет"`, `"дрожит"`, `"взгляд пустеет"`)
- `origin_layer`: `OriginLayer = OriginLayer.WILL_CONFLICT` // ADR-040: Источник давления
- `embodied_vector`: `Optional[EmbodiedVector] = None` // ADR-040: Моторный импульс (для UI)

---

### Avatar Creation Vector (MVP Contract)
Передается с фронтенда при создании новой игры.

- `name`: `str`
- `npc_id`: `str` — Всегда `"player"`
- `archetype`: `str` — `"Laborer"`, `"Soldier"`, `"Merchant"`, `"Drifter"`, `"Noble"`
- `temperament`: `str` — `"Fearful"`, `"Stoic"`, `"Impulsive"`, `"Calculating"`
- `body_profile`: `Dict[str, Any]` — Сгенерирован из Archetype
- `psyche`: `Dict[str, Any]` — Сгенерирована из Temperament

---

## X. Intent Compression Layer (Слой 1)

### IntentSemanticField (Pydantic BaseModel)
Вероятностная реконструкция намерения. Результат работы `IntentCompressor`.

- **action_type**: `ActionType` # MOVE, OBSERVE, INTERACT, ATTACK, THREATEN, PERSUADE, FLIRT, STEAL, GIVE, UNCERTAIN
- **target_reference**: `Optional[str]` # Сырая ссылка на цель: 'борко', 'тот мужик', 'кружка' (LLM не знает ID!)
- **target_zone**: `TargetZone` # HEAD, TORSO, ARMS, LEGS, GROIN, UNDEFINED
- **physical_force**: `float = 0.1` # 0.0-1.0, Кинетическая энергия
- **emotional_charge**: `float = 0.1` # 0.0-1.0, Эмоциональный вклад
- **social_pressure**: `float = 0.0` # 0.0-1.0, Социальный вес
- **commitment_level**: `float = 0.8` # 0.0-1.0, Уровень приверженности
- **tool_reference**: `Optional[str]` # Сырая ссылка на инструмент
- **semantic**: `EmotionalVector` # aggression, fear, shame, confidence, desperation (0.0-1.0)
- **raw_text**: `str` # Исходный текст для феноменологического перевода
- **confidence**: `ConfidenceVector` # parse, target, emotion, action (0.0-1.0)
- **ambiguity**: `SemanticAmbiguity` # CLEAR, PARTIAL, AMBIGUOUS

### EmotionalVector (BaseModel)
- `aggression`: `float = 0.0`
- `fear`: `float = 0.0`
- `shame`: `float = 0.0`
- `confidence`: `float = 0.5`
- `desperation`: `float = 0.0`

### ConfidenceVector (BaseModel)
- `parse`: `float = 1.0`
- `target`: `float = 0.0`
- `emotion`: `float = 0.8`
- `action`: `float = 1.0`

---

## XI. DecisionHub v2 & Legacy Bridge

### DecisionResult (backend/app/services/npc/decision_hub.py)
- `npc_id`: `str`
- `intent`: `Intent`
- `intent_target`: `Optional[str]`
- `score`: `float`
- `scores_trace`: `Dict[str, float]`
- `deltas`: `List[StateDeltas]` // ADR-032: Каноничный v2. Доменные payload (Emotion, Social).
- `narrative_fact`: `Optional[str] = None`
- `explanation_mode`: `bool = False`

### LegacyStateDeltaAdapter (backend/app/services/npc/legacy_delta_adapter.py)
*Односторонний деградационный шлюз v2 → v1. Для legacy downstream.*
- `collapse(deltas: Union[List[StateDeltas], StateDeltas]) -> StateDeltas`
- Схлопывает `EmotionPayload` и `SocialPayload` в плоский v1 объект.
- Логирует `[LEGACY_COLLAPSE_WARNING]` при потере доменов (Physiology, Identity).

---

## XII. Affective System & Resonance

### AffectiveImprint (backend/app/models/affect.py)
*Единица аффективной памяти — остаточное давление опыта.*
- `source_entity_id`: `str`
- `trigger_tags`: `tuple[str, ...]` // Семантические теги (violence, public, betrayal)
- `pain_signature`: `float` // 0.0-1.0
- `fear_signature`: `float` // 0.0-1.0
- `humiliation_signature`: `float` // 0.0-1.0
- `trust_shift`: `float` // -1.0 ... +1.0
- `reinforcement`: `float` // 0.0-1.0, укрепление при повторном воздействии
- `decay_rate`: `float` // 0.0-1.0, скорость затухания
- `created_at`: `int` // game_time_seconds
- `last_triggered_at`: `int` // game_time_seconds

### ResponseBias (Enum)
*Спектр реакций на травматический резонанс.*
- `FEAR`, `AGGRESSION`, `FREEZE`, `SUBMISSION`, `DISSOCIATION`

### ResonanceProfile (backend/app/models/affect.py)
*Результат сканирования аффективной памяти.*
- `triggered_imprints`: `tuple[str, ...]`
- `fear_resonance`, `humiliation_resonance`, `domination_resonance`, `violence_resonance`, `abandonment_resonance`: `float`
- `certainty_modifier`: `float`
- `dissociation_risk`: `float`
- `trigger_strength`: `float`
- `dominant_bias`: `ResponseBias

### DecisionContext (Frozen Dataclass — Топология решений ADR-049)
*Мост Ядро→Хаб. Проекция геометрии восприятия в геометрию решений (Каузальная дискретизация T+1).*
- **deformation**: `UtilityFieldDeformation` // Непрерывные векторы давления (aggression_suppression, initiative_suppression, compliance_bias, escape_salience)
- **compression**: `ActionSpaceCompression` // Feasibility-слой. Экстремальное сужение (constraints: Dict[str, float], где 0.0 = действие невозможно)
- **source**: `Optional[str]` // "perceptual_kernel" (из translate_kernel_to_context) или "cfrm_pressure" (из translate_pressure_to_context)
- **Трансляция**: Устав §1.2 — домен не знает о моделях. Метод `from_kernel()` удален (Сессия 34). Проекция `PerceptualKernel -> DecisionContext` выполняется в сервисном слое: `life_engine.tick_decisions()` (Каузальная дискретизация T+1).

### IntentResolution (Frozen Dataclass — Транзитный DTO ADR-034)
*Результат шлюза Фазы 1. GameLoop публикует артефакты на его основе, не принимая решений.*
- `original_intent`: `IntentDTO`
- `resolved_intent`: `Optional[IntentDTO]` // None если заблокировано волей
- `blocked`: `bool`
- `transformed`: `bool`
- `resistance_level`: `float` // 0.0-1.0
- `override_reason`: `Optional[str]` // WillState.value (почему заблокировано)
- `will_state`: `Optional[WillState]`
- `narration_hooks`: `List[str]` // Подсказки для LLM ("дрожит", "плачет")
- `counter_offer`: `Optional[IntentDTO]` // Альтернатива, предложенная аватаром
---

## XIII. Спринт 26: Феноменологические и Оптические Контракты

### GameActionResponse (Frontend Extension)
- will_conflict_data: Optional[dict] // ADR-039: Артефакты Конфликта Воли для Embodied Perception Interface. Содержит state, resistance, narration_hooks, counter_offer_action, counter_offer_text.

### SanitizedPerceptualVectors (Frontend Internal)
*Результат работы Presentation Firewall. Только скаляры, прошедшие санитизацию.*
- blood_visibility: float
- visual_instability: float
- attention_tunneling: float
- temporal_distortion: float
- perceptual_latency: float
- reality_reconciliation_rate: float
- emotional_temperature: float
- proximity_compression: float
- directional_pressure: Tuple[float, float]

### ManifestationProfile (Frontend Internal)
*Результат работы Perceptual Momentum. Оптическая деформация для рендерера.*
- visual_instability: float // Тремор, хроматическая аберрация
- auditory_distortion: float // Глушение, звон
- motor_disruption: float // Искажение отклика мыши/клавиш
- contrast_instability: float // Пульсация контраста
- attention_tunneling: float // Виньетка, сужение фокуса
- motion_bias: Tuple[float, float] // Вектор визуального сноса
- temporal_distortion: float // Лаг рендера
- temporal_assembly_delay: float // Задержка подтверждения реальности
- blood_visibility: float // Инерция кровавой виньетки

---

## XIV. Спринт 32: LifeEngine De-godification (ADR-051)

### LifeEngine.tick() Return Contract
*Смена парадигмы: LifeEngine возвращает намерения, а не исполняет их напрямую.*
- **Return Type:** `tuple[list[SceneChange], list[MovementIntent]]`
- `list[SceneChange]`: Когнитивные изменения (activity, visible). Телепортационные `SceneChange(field="location")` ЗАПРЕЩЕНЫ.
- `list[MovementIntent]`: Пространственные намерения (расписание, потребности, случайные события). Исполняются `TickOrchestrator` через `MovementEngine` для порождения `TraversalState`.

### DirectiveInterpretationSubscriber.handle() Input Contract
*Починка трубы давления: подписчик получает реальные данные NPC.*
- **Input:** `handle(event, all_npcs_raw: list[dict])` // Ранее передавался пустой список `[]`.
- **Зависимость:** Читает `psyche`, `perceptual_kernel` из `all_npcs_raw` для вычисления легитимности и цены отказа.

---

## XV. Спринт 30: Dual-Time Ontology & Каузальная Презентация (ADR-058)

### NPCPositionDTO (Backend API Boundary)
*Расширено для проброса Cognitive Freeze на фронтенд.*
- `initiative_suppression`: `float = 0.0` // Спринт 30: Уровень подавления воли (0.0-1.0). Передается из `PerceptualKernel` для визуализации паралича.

### NPCBuffer (Backend Internal)
*Расширено для агрегации когнитивного состояния перед записью в scene_state.*
- `initiative_suppressions`: `Dict[str, float]` // Спринт 30: Словарь npc_id -> initiative_suppression. Заполняется в npc_tick_pipeline, применяется в npc_orchestration.

### PerceivedEntity (Frontend Internal)
*Расширено слоями Traversal и Cognitive для непрерывной презентации.*
- **Traversal Layer (Спринт 30: Dual-Time Ontology):**
  - `traversal_status`: `str = "IDLE"` // PENDING, MOVING, ARRIVED, CANCELLED
  - `path_waypoints`: `list = field(default_factory=list)` // Визуальные x,y точки от бэкенда
  - `current_waypoint_idx`: `int = 0`
  - `traversal_progress`: `float = 0.0` // 0.0 - 1.0 прогресс между текущими waypoint
  - `traversal_speed`: `float = 1.5` // Скорость визуальной интерполяции (м/с)
- **Cognitive Layer (Спринт 30: Визуализация Cognitive Freeze):**
  - `initiative_suppression`: `float = 0.0` // 0.0-1.0, паралич воли. При >0.7 рендерер применяет моторный тремор.

---

## XVI. Инфраструктура Наблюдения: Causal Diagnostic System (ADR-059)

### CausalObserver (Background Thread)
*Запускается из `game_launcher.py` до pygame loop. Пишет один markdown-файл с тремя секциями. Читается LLM, не человеком.*

### LAST_SESSION.md Structure (LLM Context DTO)
*Формат оптимизирован для контекстного окна LLM-архитекторов. Конкретные факты, готовые команды, файлы и строки.*

- **Идентификация Архитектора:** Правила определения роли (Код, UI, Симуляция) на основе триггеров первого сообщения.
- **Секция #1 (Архитектор Кода):** Активные баги требующие патча (с файлом и строкой), последние изменения (из MUTATIONS.md), файлы с TODO/FIXME.
- **Секция #2 (Архитектор UI):** NPC с координатами/на нулях, визуальные аномалии (телепортации, слияния), что НЕ трогать.
- **Секция #3 (Архитектор Симуляции):** Tick/Decision health, Movement Pipeline (таблица Intent→Traversal→Coords по NPC), Directive Pipeline (результат приказов), Каузальные разрывы (цепи отказа с PowerShell для верификации).

### PatternRegistry (Diagnostic Regex)
*Паттерны для парсинга логов игры в реальном времени.*
- `decisions_zero`: `r"\[TICK_DECISIONS\] end: 0 decisions"`
- `intent_received`: `r"\[TRACE\]\[ENGINE_RECEIVED\] npc=(\w+)"`
- `node_not_found`: `r"\[MOVEMENT_ENGINE\] Узел '(\w+)' не найден"`
- `directive_detected`: `r"\[CAUSALITY\] Semantic action MOVE detected for NPC '(\w+)'"`
- `obedience_pressure`: `r"\[DIRECTIVE_INTERPRET\] Target=(\w+), Action=(\w+), ObediencePressure=([\d.]+)"
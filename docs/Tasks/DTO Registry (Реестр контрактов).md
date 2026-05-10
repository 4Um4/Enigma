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

**PhysiologyPayload** (Заменила CombatPayload)
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

### EventBus (CFRM Extensions — Layer 1 Capture)
- `attach_cfrm_buffer(buffer: Any)`: Привязывает `EventBuffer` к шине на время тика.
- `detach_cfrm_buffer()`: Отвязывает буфер (гарантированно вызывается в `finally` блоке `TickOrchestrator`).
- **Поведение `publish()`:** Если `_cfrm_buffer` привязан, автоматически вызывает `classify_event(event.type)` и `buffer.add(event, axis)` для захвата факта.

---

## V. Пространство и Движение

### MovementIntent (LOD1: Macro Traversal)
*Используется ТОЛЬКО для перемещения между узлами макро-графа. ЗАПРЕЩЕНО для микро-перемещений (target == from).*

### SceneChange(field="position")
*Статус: РАЗРЕШЕНО. Атомарно обновляет узел и резолвит `local_position` (x,y) через SpatialService.*

### TraversalState [PLANNED]
- `npc_id`: `str`, `path`: `list[tuple[float, float]]`, `current_index`: `int`, `speed`: `float`, `started_at`: `int`, `target_node`: `str`, `locomotion`: `str` (WALK, RUN, SNEAK), `status`: `str` (PENDING, MOVING, ARRIVED, CANCELLED), `arrival_threshold`: `float` (0.3m)

### MovementStep [PLANNED]
- `npc_id`: `str`, `from_xy`: `tuple[float, float]`, `to_xy`: `tuple[float, float]`, `delta_seconds`: `float`, `traversal_id`: `str`

### LocalSteeringIntent [PLANNED]
*Для визуального сближения внутри макро-зоны без изменения `position`.*
- `npc_id`, `target_entity_id`, `target_xy`, `speed`, `arrival_radius`

---

## VI. Game Loop, API и Persistence

### WorldSnapshotDTO
- `tick`: `int`, `version`: `int`, `last_event_id`: `Optional[UUID]`
- `player_position`: `Tuple[float, float]`, `npc_positions`: `List[NPCPositionDTO]`
- `visible_events`: `List[VisibleEventDTO]`, `available_actions`: `List[str]`
- `location_id`: `str`, `weather`: `str`, `time_of_day`: `str`
- `game_time_seconds`: `int = 0` // Абсолютное время симуляции

### NPCPositionDTO
- `npc_id`: `str`, `x`: `float`, `y`: `float`, `location_id`: `str`, `facing`: `str`, `action`: `str`
- `display_name`: `str` // КРИТИЧЕСКИ ВАЖНО: заполнять из `data.get("name")`, иначе фронтенд показывает npc_id!

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

### EventBuffer (Dataclass — Временный causal input stream)
- `physical_events`: `List[EventDTO]`
- `cognitive_events`: `List[EventDTO]`
- `social_events`: `List[EventDTO]`
- Методы: `add(event, axis)`, `drain() -> Tuple[List, List, List]` (Извлекает факты и очищает буфер для следующего тика)

### ClusterOccupancy (Dataclass — Spatial Index O(1))
- `entity_to_cluster`: `Dict[str, ClusterID]` // npc_id/player -> cluster_id
- `cluster_to_entities`: `Dict[ClusterID, Set[str]]` // cluster_id -> set(npc_ids)
- Методы: `update_entity(entity_id, new_cluster)`, `get_cluster(entity_id)`, `get_entities_in_cluster(cluster_id)`, `remove_entity(entity_id)`

### classify_event() (Legacy Bridge P1)
- Сигнатура: `classify_event(event_type: str) -> CausalAxis`
- Маппит текущие `EventType.value` на 3 оси CFRM. Fallback для неизвестных событий -> `COGNITIVE`.

### _TickContext (TickOrchestrator — обновления Сессии 18)
- `event_buffer`: `EventBuffer` // Заполняется через EventBus.attach_cfrm_buffer()
- `cluster_occupancy`: `ClusterOccupancy` // Восстанавливается на старте тика из scene_state['npc_positions']

---

## IX. Player Entity & WillpowerGate (Hybrid Consciousness)

### Player Avatar (`npc_id="player"`)
Игрок внедряется в `all_npcs_raw` как полноправный агент симуляции.

- **body_profile**: Задается через Archetype (`Laborer`, `Soldier`, `Merchant`, `Drifter`, `Noble`).
- **psyche**: Задается через Temperament (`Fearful`, `Stoic`, `Impulsive`, `Calculating`). Определяет `drives_base` и `willpower`.
- **social_stats**: Формируется динамически. Отношение NPC к игроку подчиняется Social Drift.
- **AvatarAffectiveMemory**: Эмоциональная память аватара. Подвержена затуханию, вытеснению и травмам. Отличается от `PlayerMemory` (памяти человека-игрока).

---

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

---

### Avatar Creation Vector (MVP Contract)
Передается с фронтенда при создании новой игры.

- `name`: `str`
- `npc_id`: `str` — Всегда `"player"`
- `archetype`: `str` — `"Laborer"`, `"Soldier"`, `"Merchant"`, `"Drifter"`, `"Noble"`
- `temperament`: `str` — `"Fearful"`, `"Stoic"`, `"Impulsive"`, `"Calculating"`
- `body_profile`: `Dict[str, Any]` — Сгенерирован из Archetype
- `psyche`: `Dict[str, Any]` — Сгенерирована из Temperament
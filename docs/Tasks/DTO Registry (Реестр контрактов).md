(05.05.2026 22:25) — Обновлено: 09.05.2026 (Physiology Domain)Phase8Resultdeltas: List[StateDeltas] (список вычисленных, но не применённых изменений)perceiving_npc_ids: Optional[Set[str]] (NPC, воспринявшие событие визуально/аудио)socially_affected_npc_ids: Optional[Set[str]] (NPC, затронутые социальной пропагацией)events_processed: int (количество обработанных событий)prop_dirty: bool (DEPRECATED — флаг мутации, удаляется после полной миграции на delta_buffer)

StateDeltas (# v2: Domain-Tagged Typed Payloads. v1 поля LOCKED и депрекированы)npc_id: Optional[str] (ОБЯЗАТЕЛЬНО для маршрутизации дельты. В тестах передается явно. None только для глобальных дельт)domain: Optional[DeltaDomain] (v2: SOCIAL, EMOTION, REPUTATION, IDENTITY, PHYSIOLOGY, SPATIAL)target: Optional[str] (v2: универсальный таргет — player, npc_id, faction_id)payload: Optional[DeltaPayload] (v2: Union[SocialPayload, EmotionPayload, ReputationPayload, IdentityPayload, PhysiologyPayload])

v1 backward compat (deprecated, удаляются после миграции DecisionHub)
intent_target: Optional[str] (DecisionHub → player-facing trust/fear)social_target: Optional[str] (Social decay/propagation → NPC→NPC trust/fear)faction_id: Optional[str] (Reputation decay → фракция, несовместим с trust/fear)stress_delta: float (v1: масштаб 0-100)stress_delta_effective: float (OUTPUT — реально применённое изменение после насыщения)emotion_delta: float (v1: масштаб -100..100)emotion_tag: Optional[EmotionTag]trust_delta: float (v1: масштаб 0-100)fear_delta: float (v1: масштаб 0-100)reputation_delta: float (v1: только с faction_id)trait_updates: Dict[str, float]new_trauma: Optional[str]source: stridentity_integrity_delta: floatpressure_resistance_delta: floatwill_state_override: Optional[WillState]

post_init валидация v2: если payload не None, его тип должен соответствовать domain (TypeError)post_init валидация v1: один тип таргета, reputation_delta требует faction_id, trust/fear ≠ faction_id

DeltaDomain (Enum)SOCIAL, EMOTION, REPUTATION, IDENTITY, PHYSIOLOGY, SPATIAL (FUTURE)

SocialPayload (frozen dataclass)trust_delta: float = 0.0, fear_delta: float = 0.0, affection_delta: float = 0.0, debt_delta: float = 0.0

EmotionPayload (frozen dataclass)stress_delta: float = 0.0, emotion_delta: float = 0.0, emotion_tag: Optional[str] = None, new_trauma: Optional[str] = None

ReputationPayload (frozen dataclass)reputation_delta: float = 0.0

IdentityPayload (frozen dataclass)identity_integrity_delta: float = 0.0, pressure_resistance_delta: float = 0.0, will_state_override: Optional[str] = None

InjuryDTO (frozen dataclass) — НОВОЕ (Physiology Domain)damage_type: str (slash, blunt, pierce, burn, crush)target_zone: str (head_eye_l, torso_groin, arm_r — функциональная зона, НЕ anatomical organ)structural_damage: float (0.0 - 1.0, физическое разрушение тканей)functional_loss: float (0.0 - 1.0, потеря функции зоны)critical_effects: Tuple[str, ...] (severed, bleeding, infected)

PhysiologyPayload (frozen dataclass) — НОВОЕ (ЗАМЕНЯЕТ CombatPayload)hp_delta: float = 0.0 (Макро-LOD: агрегированная потеря функции, НЕ истинное здоровье)pain_delta: float = 0.0 (0-100)fatigue_delta: float = 0.0 (0-100)blood_loss_delta: float = 0.0 (0-1.0 шкала)shock_impulse: float = 0.0 (0-1.0, физический шок — сигнал для EmotionSubscriber, No Domain Leakage)add_injuries: Tuple[InjuryDTO, ...] = ()add_statuses: Tuple[str, ...] = (bleeding, unconscious, crippled)remove_statuses: Tuple[str, ...] = ()

NPCStateSnapshot (TypedDict — READ-ONLY проекция NPC для idle handlers)npc_id: strstress: floatrelationship_cache: Dict[str, Any] ({target: {trust, fear, base_trust, ...}})base_values: Dict[str, Any] ({target: base_trust, ...} для drift-расчёта)faction_affiliations: List[str] ([faction_id, ...])hp: float (Агрегированная способность функционировать)max_hp: float (Из body_profile)pain: float (0-100)fatigue: float (0-100)blood_loss: float (0-1.0)consciousness: float (0-1.0, 0=кома/обморок)injuries_by_zone: Dict[str, List[Dict[str, Any]]] (Группировка по target_zone)base_abilities: Dict[str, float] (Из body_profile. НЕ ВЫЧИСЛЯТЬ effective в снапшоте!)modifiers: Dict[str, float] (Из body_state. Травмы/баффы/экипировка)

IdleTickHandler (Protocol)name: strhandle(npcs: List[NPCStateSnapshot], campaign_id: str, current_tick: int) → List[StateDeltas]

SocialDecayHandler (IdleTickHandler)name: "social_decay"SOCIAL_DECAY_RATE: 0.01 (1% дрейфа за тик)SOCIAL_DECAY_EPSILON: 0.001 (closing drift порог)Возвращает StateDeltas(npc_id, social_target, trust_delta, source="social_decay")Closing drift: if |base-current| < EPSILON → drift = base - current

ReputationDecayHandler (IdleTickHandler)name: "reputation_decay"Делегирует в ReputationEngine.compute_decay()Возвращает StateDeltas(faction_id, reputation_delta, source="reputation_decay")REPUTATION_DECAY_RATE: 0.005, REPUTATION_DECAY_EPSILON: 0.001

ACTION_INTENSITY (domain/constants.py)type: dict[str, float]Ключи: player_attacks, player_threatens, player_threatens_indirect, player_steals, player_flees, player_insults, player_interacts, dialogue, attack, move, stealthЗначения: базовая интенсивность (0.1 - 1.0). Если тип неизвестен, fallback = 0.2

ReactionSubscriber (Phase8Handler — Фаза 8, event-driven)name: "reaction"Подписка: _REACTION_EVENT_TYPES (PLAYER_ATTACKS, PLAYER_ATTACK, PLAYER_ATTACKED, PLAYER_THREATENS, PLAYER_INSULTS, COMBAT, THEFT, INTIMIDATION, BETRAYAL, HELP, SAVED_LIFE, OBJECT_DESTROYED)drain_events() → List[EventDTO]handle(events, Phase8Context) → Phase8Result(deltas=List[StateDeltas])Модификатор реакции: _compute_reaction_modifier(npc_dict) → floatcomposure_factor = 0.5 + (1 - composure) * 0.5 (stress 0-100 → 0.5-1.0)fear_factor = 0.5 + drives.fear * 2.0 (fear drive → 0.5-2.5)willpower_factor = 1.0 - willpower / 150.0 (willpower → 0.33-1.0)modifier = composure_factor * fear_factor * willpower_factorПравила реакций (_REACTION_RULES): event_type → (stress_base, fear_base, trust_actor_base)player_attacks: (15.0, 10.0, -8.0)combat: (18.0, 12.0, -6.0)help: (-3.0, 0.0, 5.0)saved_life: (-5.0, -3.0, 10.0)и т.д.Маршрутизация: source=player → intent_target="player"; source=NPC → social_target=source_idИсточник события исключён из реакций (npc_id == source → skip)perceiving_npcs: None (не установлен) → fallback на всех NPC; [] (пустой) → никто не реагирует

NPCStateSnapshot — маппинг данных (_build_npc_snapshots, ADR-004 + ADR-005 + ADR-0010)social_stats.trust → relationship_cache["player"]["trust"]social_stats.fear_of_player → relationship_cache["player"]["fear"]social_stats.debt → relationship_cache["player"]["debt"]psyche.loyalty_true → base_values["player"]status_profile.faction_rank.keys → faction_affiliationsВложенный relationship_cache: shallow copy + гарантированный player entry из social_statsПлоский кэш {trust: val} автоматически конвертируетсяNPC→NPC записи из village_relations.json обогащаются через _enrich_with_social_relations() при загрузкеPlayer entry ГАРАНТИРОВАН даже при наличии NPC→NPC записей (не перезаписывается, добавляется если отсутствует)Player base из loyalty_true ГАРАНТИРОВАН даже при наличии NPC→NPC base_values

Physiology Domain маппинг (ADR-0010):
body_profile.max_hp → max_hpbody_state.current_hp → hp (fallback на max_hp если нет)body_state.pain → painbody_state.fatigue → fatiguebody_state.blood_loss → blood_lossbody_state.consciousness → consciousnessbody_profile.abilities → base_abilitiesbody_state.modifiers → modifiersbody_state.injuries → injuries_by_zone (группировка по target_zone)

_enrich_with_social_relations (npc_loader.py — вызывается при загрузке)Вход: List[NPC dict], Dict[str, Any] (relations из village_relations.json)Мутирует NPC dicts in-place (только при загрузке)Формат: relationship_cache[target_id] = {trust: base_trust100, fear: 0.0, base_trust: base_trust100, nature: str}Формат: base_values[target_id] = base_trust * 100Не перезаписывает существующие записи (runtime мог мутировать)Шкала: 0-1 (JSON) → 0-100 (relationship_cache). Конвертация ×100Источник не найден в NPC списке → пропуск с debug logНекорректный rel_data (не dict) → пропуск без ошибки

NPCState (backend/app/models/npc_state.py) — ОБНОВЛЕНО ADR-0010body_state: Dict[str, Any] (Рантайм-контейнер физиологии. Ключи: current_hp, pain, fatigue, blood_loss, consciousness, injuries, modifiers, statuses)

GameLoop.idle_tick() Return Contract (dict)status: str ("ok", "no_scene", "not_ready", "error")changes: intnpc_positions: dict (DEPRECATED: читать из world_snapshot)events: listworld_snapshot: Optional[dict] (конвертировано из WorldSnapshotDTO, UUID→str)TickResultDTO (backend/app/services/tick_orchestrator.py)status: str ("ok" | "error" | "no_scene")error: Optional[str]changes: int (DEPRECATED)TickPlayerResultDTO (backend/app/services/tick_orchestrator.py)status: str ("ok" | "error")error: Optional[str]npc_contexts: listsnapshot: Optional[dict]events: List[Any]dirty_npcs: setactivity_overrides: Dict[str, str]max_npc_stress: floatmovement_intents: listfinalize_result: Optional[dict]EventDTO (backend/app/domain/events.py) — Паспорт события (Устав §2.1)id: UUIDtype: str (Использовать EventType.PLAYER_ATTACKS.value и др. Внутри шины хранятся как str!)source: str (player_name | npc_id)timestamp: floatpayload: Dict[str, Any] (Обязательные ключи для player_attacks: intensity, actor_id, target_id)visibility: Literal["public", "private", "whisper"]radius: floatpersistence_level: Literal["working", "session", "campaign"]NpcTickServices (backend/app/services/npc/npc_tick_contracts.py)memory_manager: Anyrelationship_store: Anysocial_engine: Anyreputation_engine: Anyeconomic_profiles: Anyevent_bus: Anyspatial_service: Any # ДОБАВЛЕНО: Инжекция SpatialServicePerceivedScene (frontend/game_types.py)location_id: strentities: List[PerceivedEntity]audio_events: List[AudioEvent]environment: PerceivedEnvironmentattention_focus_id: Optional[str]player_body_state: List[str]
InterpretationEngine.computestate: NPCStateevent: EventContextplayer_reputation: Optional[Dict[str, int]]drives_base: Dict[str, float] # ДОБАВЛЕНО: веса драйвов из profile_l0NPCPositionDTO (backend/app/domain/snapshot.py)npc_id: strx: floaty: floatlocation_id: strfacing: straction: strdisplay_name: str # КРИТИЧЕСКИ ВАЖНО: Должно заполняться из data.get("name") в WorldSnapshotBuilder, иначе фронтенд показывает npc_id!
NarrativeBeat (Frontend DTO)speaker: str (Извлекается из dm_response через known_names из scene_state, либо "Система"/"Мужчина"/"Женщина")text: stris_player: booldelivery: DeliveryType (Enum: NORMAL, WHISPER, SHOUT, INTERNAL, PANIC, INTERRUPT)certainty: float (0.0 - 1.0)recognition: RecognitionLevel (Enum: UNKNOWN_MALE, UNKNOWN_FEMALE, STRANGE_FACE, KNOWN_NAME)lifetime: BeatLifetime (Enum: TRANSIENT, PINNED, SLAM)creation_tick: int (pygame.time.get_ticks() в момент создания. 0 = не инициализирован)alpha: float (0.0 - 255.0, текущая прозрачность для dissolve-эффекта. По умолчанию 255.0)is_fading: bool (Флаг начала растворения. True, если TRANSIENT старше 5 секунд)is_active: bool (Участвует ли в текущем кадре. False = полностью растворился (alpha <= 0) и подлежит удалению из message_log)

Frontend Local Vars (не DTO, но важная часть контракта):known_names: Dict[str, str] — словарь {npc_name.lower(): npc_name}, собирается из scene_state["npc_positions"] для парсинга спикера.system_log: List[str] — список сырых строк для Log Layer (движение, ошибки, порталы), рендерится в правом верхнем углу.

TextInput (Frontend Widget)Поддержка инерции зажатия клавиш (update(dt)).Поддержка Shift+Enter (\n).Полный запрет Paste (Ctrl+V / Shift+Insert).
Session 14 Updates (08.05.2026 22:18)

check_random_events (backend/app/services/npc/life_engine.py)Возвращаемый тип: tuple[list[SceneChange], MovementIntent | None]Контракт: СТРОГО кортеж из 2 элементов. Возвращает ([], None) если NPC спит или событие не сгенерировано. Возвращает (changes, None) если событие обработано (intent уже применён внутри метода).НАРУШЕНИЕ КОНТРАКТА: Возврат голого списка [] или list[SceneChange] без оборачивания в кортеж приводит к крашу "not enough values to unpack" в _simulate_major/_simulate_minor.

SceneChange(field="position") — Статус: РАЗРЕШЕНО (ADR-0009)Ранее: Вызывало RuntimeError "Прямая мутация position запрещена".Сейчас: Страж смягчён. SceneChange(type=NPC_POSITION, field="position", value="main_hall") разрешён и является единственным легитимным способом обновить семантическую локацию NPC.Поведение SceneStateManager: При получении field="position" атомарно обновляет узел и резолвит local_position (x, y) через SpatialService.get_node().

MovementIntent — Область применения (LOD1: Macro Traversal)Архитектурное ограничение: MovementIntent используется ТОЛЬКО для перемещения между узлами макро-графа (main_hall -> bar_area, city -> forest).ЗАПРЕЩЕНО: Использовать MovementIntent для микро-перемещений внутри одной макро-зоны (target_node_id == from_node_id). Это приводит к онтологической лжи и архитектурной эрозии.

LocalSteeringIntent — ПЛАНИРУЕМАЯ DTO (LOD0: Micro Space)Статус: Не реализована. Требуется для визуального сближения NPC с объектами внутри одной макро-зоны.Назначение: Плавное перемещение (steering) к координатам (x,y) игрока или другого NPC без изменения семантического узла position.Поля (проект): npc_id, target_entity_id, target_xy, speed, arrival_radius.

Session 15 Updates (Impact Propagation Engine / Physiology Domain)

ImpactIntentDTO (backend/app/models/impact.py) — НОВОЕactor_id: strtarget_id: strdamage_type: str (slash, blunt, pierce, burn, crush)target_zone: Optional[str] (torso_groin, head_eye_l, arm_r. None = случайная по весам)force: float (0.0 - 100.0, базовая сила воздействия)weapon_reach: float = 1.0

ContactLevel (Enum) — НОВОЕMISS, GLANCING, PARTIAL, SOLID, PERFECT (Степень контакта, замена RPG Hit Roll)

ImpactEngine (backend/app/services/combat/impact_engine.py) — НОВОЕresolve_physical_impact(attacker: NPCStateSnapshot, defender: NPCStateSnapshot, intent: ImpactIntentDTO, rng_seed: int) → List[StateDeltas]Pure Function. Контактная модель (уклонение зависит от боли/усталости, а не RNG Hit Roll). Возвращает ТОЛЬКО Physiology-дельты (No Domain Leakage).
---
WorldSnapshotDTO (backend/app/domain/snapshot.py)tick: intversion: intlast_event_id: Optional[UUID]player_position: Tuple[float, float]npc_positions: List[NPCPositionDTO]visible_events: List[VisibleEventDTO]available_actions: List[str]location_id: strweather: strtime_of_day: strgame_time_seconds: int = 0 # ДОБАВЛЕНО: Абсолютное время симуляции (ед. истина)

GameScreen State (frontend/game_screen.py - не DTO, но важно)_time_scale: int = 1 # Множитель скорости (1, 4, 10, 50)
---
TurnResult (frontend/game_loop_bridge.py) — ОБНОВЛЕНО
action_type: str = ""
npc_reactions: list[dict] = field(default_factory=list)
dm_text: str = ""
tokens: int = 0
ms: int = 0
tps: float = 0.0
game_time_seconds: int = 0
error: Optional[str] = None
world_snapshot: Optional[dict] = None  # НОВОЕ: ADR-0014 Force Merge
npc_positions: Optional[dict] = None   # НОВОЕ: ADR-0014 Force Merge

GameActionResponse (frontend/api_client.py) — БЕЗ ИЗМЕНЕНИЙ (поля уже были, теперь заполняются)
dm_response: str
npc_reactions: list[dict]
world_changes: list[dict]
journal_entry_id: str | None
game_time_seconds: int = 0
world_snapshot: dict | None = None
npc_positions: dict | None = None,

TraversalState (ПЛАНИРУЕМАЯ DTO — ADR-0013, не реализована)
npc_id: str
path: list[tuple[float, float]]  # Список waypoint-ов (x, y)
current_index: int               # Текущий waypoint
speed: float                     # Метры в секунду
started_at: int                  # Tick начала traversal
target_node: str                 # Семантический узел назначения
locomotion: str                  # WALK, RUN, SNEAK
status: str                      # PENDING, MOVING, ARRIVED, CANCELLED
arrival_threshold: float         # Расстояние считающееся «прибыл» (0.3m)

MovementStep (ПЛАНИРУЕМАЯ DTO — ADR-0013, не реализована)
npc_id: str
from_xy: tuple[float, float]
to_xy: tuple[float, float]
delta_seconds: float
traversal_id: str  # Ссылка на TraversalState
---
ReductionPolicy (Enum) — НОВОЕ (DRSL)
ADDITIVE = "additive" — линейная физика (Σ). SOCIAL, REPUTATION.
BOUNDED_ADDITIVE = "bounded_additive" — накопление с насыщением (Σ + clamp). EMOTION.
OVERWRITE = "overwrite" — дискретная реальность (last-write-wins). IDENTITY, SPATIAL.
PHYSICS_COMPOSITE = "physics_composite" — эволюция состояния (S_t = F(S_{t-1}, impacts)). PHYSIOLOGY. В _aggregate_deltas обходит merge.

DELTA_POLICY_REGISTRY: Dict[DeltaDomain, ReductionPolicy]
SOCIAL → ADDITIVE
EMOTION → BOUNDED_ADDITIVE
REPUTATION → ADDITIVE
IDENTITY → OVERWRITE
PHYSIOLOGY → PHYSICS_COMPOSITE
SPATIAL → OVERWRITE

DeltaDomain (Enum) — ОБНОВЛЕНО (lowercase значения)
SOCIAL = "social"
EMOTION = "emotion"
REPUTATION = "reputation"
IDENTITY = "identity"
PHYSIOLOGY = "physiology"
SPATIAL = "spatial"

NPCStateSnapshot — ОБНОВЛЕНО
+ statuses: List[str] (Активные статусы: stagger, unconscious, bleeding и т.д.)

CombatSubscriber (Phase8Handler — Фаза 8, event-driven)
name: "combat"
Подписка: _COMBAT_EVENT_TYPES (PLAYER_ATTACKS, PLAYER_ATTACKED, COMBAT)
drain_events() → List[EventDTO]
handle(events, Phase8Context) → Phase8Result(deltas=List[StateDeltas])
ImpactIntentDTO extraction: payload.actor_id/fallback event.source, payload.target_id (обязателен), payload.force/intensity, payload.damage_type (fallback "blunt"), payload.target_zone, payload.weapon_reach (fallback 1.0)
Player fallback: если actor_id не в npc_by_id → идеальный снапшот (dexterity=12, strength=15)
Отсутствие target_id → skip event

PhysiologyDecayHandler (IdleTickHandler — Фаза 0.5, time-driven)
name: "physiology_decay"
Константы затухания:
  PAIN_DECAY_LAMBDA: 0.05
  FATIGUE_DECAY_LAMBDA: 0.03
  BLOOD_LOSS_DECAY_LAMBDA: 0.01
  CONSCIOUSNESS_RECOVERY: 0.02
  PHYSIOLOGY_DECAY_EPSILON: 0.001
Фазовые переходы:
  STAGGER_PAIN_THRESHOLD: 50.0 (pain > threshold → stagger)
  COLLAPSE_CONSCIOUSNESS: 0.1 (consciousness < threshold → unconscious)
handle(npcs, campaign_id, current_tick) → List[StateDeltas]
Leaky Integrator: S_t = S_{t-1} * exp(-lambda)
Closing drift: если остаток < EPSILON → обнуление напрямую
Emergent states: stagger (высокая боль), unconscious (низкое сознание)
---
_MoveState (frontend/game_screen.py - Внутренний контракт фронтенда)Статус: Обновлено ADR-0011target_npc_id: Optional[str] (Навигация: цель следования)path: Optional[list] (Навигация: список точек (x,y))path_index: int (Навигация: текущая точка пути)direction: Optional[str] (Навигация: легаси)cooldown: float (Кинетика: задержка до следующего шага)walk_distance_accumulated: float (Кинетика: накопленные метры для расчета времени)facing_angle: float (Эмбодимент: угол взгляда в радианах. -pi/2 = вверх)facing_mode: Literal["VELOCITY", "LOOK_TARGET", "FREE"] (Эмбодимент: правило расчета угла)

SceneRenderer.render() (frontend/scene_renderer.py)player_xy: Tuple[float, float]player_facing: float = -1.5708 (угол поворота стрелки игрока в радианах)dt: float = 0.016 (НОВОЕ: дельта времени для Lerp сглаживания поворота)

Frontend Calendar Functions (frontend/constants.py)format_game_time(total_seconds: int) -> str (Возвращает "HH:MM")format_world_date(total_seconds: int) -> str (НОВОЕ: Возвращает "Год X, День Y, HH:MM". Использует дублированные константы календаря из бэкенда)
---
EVENT SCHEMA v1 (Ontological Decomposition)
SPATIAL EVENTS (Физика мира)
MoveStartEvent { entity_id, from_position, to_position, velocity }MoveProgressEvent { entity_id, interpolated_position }MoveEndEvent { entity_id, final_position }ObjectMoveEvent { object_id, position }ZoneEnterEvent { entity_id, zone_id }ZoneExitEvent { entity_id, zone_id }

SEMANTIC EVENTS (Смысл состояния)
ActivityChangeEvent { entity_id, from_state, to_state }MoodChangeEvent { entity_id, mood }StatusEffectChangeEvent { entity_id, effect }ItemAddedEvent { target_id, item_id, amount }ItemRemovedEvent { target_id, item_id, amount }ItemTransferredEvent { from_id, to_id, item_id }RoleAssignedEvent { entity_id, role }

EFFECT EVENTS (Последствия мира)
EffectAppliedEvent { source_entity, target_entity, effect_type, duration, intensity }VisibilityChangedEvent { entity_id, visibility }SoundHeardEvent { listener_id, source_id, volume }StimulusDetectedEvent { entity_id, stimulus_type }DialogueStartEvent { participants }DialogueLineEvent { speaker_id, line }DialogueEndEvent { participants }
---

---
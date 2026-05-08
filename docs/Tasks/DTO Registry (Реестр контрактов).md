
---
(05.05.2026 22:25)
Phase8Result
deltas: List[StateDeltas] (список вычисленных, но не применённых изменений)
perceiving_npc_ids: Optional[Set[str]] (NPC, воспринявшие событие визуально/аудио)
socially_affected_npc_ids: Optional[Set[str]] (NPC, затронутые социальной пропагацией)
events_processed: int (количество обработанных событий)
prop_dirty: bool (DEPRECATED — флаг мутации, удаляется после полной миграции на delta_buffer)

StateDeltas (# LOCKED v1 — новые домены через рефакторинг, не через добавление полей)
npc_id: Optional[str] (ОБЯЗАТЕЛЬНО для маршрутизации дельты. В тестах передается явно. None только для глобальных дельт)
intent_target: Optional[str] (DecisionHub → player-facing trust/fear)
social_target: Optional[str] (Social decay/propagation → NPC→NPC trust/fear)
faction_id: Optional[str] (Reputation decay → фракция, несовместим с trust/fear)
stress_delta: float (изменение стресса, масштаб 0-100)
stress_delta_effective: float (OUTPUT — реально применённое изменение после насыщения)
emotion_delta: float (изменение эмоции, масштаб -100..100)
emotion_tag: Optional[EmotionTag] (переопределение текущей эмоции)
trust_delta: float (NPC→NPC, NPC→Player, масштаб 0-100. НЕ с faction_id)
fear_delta: float (NPC→NPC, NPC→Player, масштаб 0-100. НЕ с faction_id)
reputation_delta: float (только с faction_id. Семантически изолировано от trust)
trait_updates: Dict[str, float] (state_modifiers overlay)
new_trauma: Optional[str] (добавляет в trauma_markers)
source: str (event_type или "social_decay", "reputation_decay", "life_engine")
identity_integrity_delta: float (0..1 шкала)
pressure_resistance_delta: float (0..2 шкала)
will_state_override: Optional[WillState] (прямое переопределение воли)
post_init валидация: один тип таргета, reputation_delta требует faction_id, trust/fear несовместимы с faction_id

NPCStateSnapshot (TypedDict — READ-ONLY проекция NPC для idle handlers)
npc_id: str
stress: float
relationship_cache: Dict[str, Any] ({target: {trust, fear, base_trust, ...}})
base_values: Dict[str, Any] ({target: base_trust, ...} для drift-расчёта)
faction_affiliations: List[str] ([faction_id, ...])

IdleTickHandler (Protocol)
name: str
handle(npcs: List[NPCStateSnapshot], campaign_id: str, current_tick: int) → List[StateDeltas]

SocialDecayHandler (IdleTickHandler)
name: "social_decay"
SOCIAL_DECAY_RATE: 0.01 (1% дрейфа за тик)
SOCIAL_DECAY_EPSILON: 0.001 (closing drift порог)
Возвращает StateDeltas(npc_id, social_target, trust_delta, source="social_decay")
Closing drift: if |base-current| < EPSILON → drift = base - current

ReputationDecayHandler (IdleTickHandler)
name: "reputation_decay"
Делегирует в ReputationEngine.compute_decay()
Возвращает StateDeltas(faction_id, reputation_delta, source="reputation_decay")
REPUTATION_DECAY_RATE: 0.005, REPUTATION_DECAY_EPSILON: 0.001

ACTION_INTENSITY (domain/constants.py)
type: dict[str, float]
Ключи: player_attacks, player_threatens, player_threatens_indirect, player_steals, player_flees, player_insults, player_interacts, dialogue, attack, move, stealth
Значения: базовая интенсивность (0.1 - 1.0). Если тип неизвестен, fallback = 0.2

ReactionSubscriber (Phase8Handler — Фаза 8, event-driven)
name: "reaction"
Подписка: _REACTION_EVENT_TYPES (PLAYER_ATTACKS, PLAYER_ATTACK, PLAYER_ATTACKED, PLAYER_THREATENS, PLAYER_INSULTS, COMBAT, THEFT, INTIMIDATION, BETRAYAL, HELP, SAVED_LIFE, OBJECT_DESTROYED)
drain_events() → List[EventDTO]
handle(events, Phase8Context) → Phase8Result(deltas=List[StateDeltas])
Модификатор реакции: _compute_reaction_modifier(npc_dict) → float
composure_factor = 0.5 + (1 - composure) * 0.5 (stress 0-100 → 0.5-1.0)
fear_factor = 0.5 + drives.fear * 2.0 (fear drive → 0.5-2.5)
willpower_factor = 1.0 - willpower / 150.0 (willpower → 0.33-1.0)
modifier = composure_factor * fear_factor * willpower_factor
Правила реакций (_REACTION_RULES): event_type → (stress_base, fear_base, trust_actor_base)
player_attacks: (15.0, 10.0, -8.0)
combat: (18.0, 12.0, -6.0)
help: (-3.0, 0.0, 5.0)
saved_life: (-5.0, -3.0, 10.0)
и т.д.
Маршрутизация: source=player → intent_target="player"; source=NPC → social_target=source_id
Источник события исключён из реакций (npc_id == source → skip)
perceiving_npcs: None (не установлен) → fallback на всех NPC; [] (пустой) → никто не реагирует

NPCStateSnapshot — маппинг данных (_build_npc_snapshots, ADR-004 + ADR-005)
social_stats.trust → relationship_cache["player"]["trust"]
social_stats.fear_of_player → relationship_cache["player"]["fear"]
social_stats.debt → relationship_cache["player"]["debt"]
psyche.loyalty_true → base_values["player"]
status_profile.faction_rank.keys → faction_affiliations
Вложенный relationship_cache: shallow copy + гарантированный player entry из social_stats
Плоский кэш {trust: val} автоматически конвертируется
NPC→NPC записи из village_relations.json обогащаются через _enrich_with_social_relations() при загрузке
Player entry ГАРАНТИРОВАН даже при наличии NPC→NPC записей (не перезаписывается, добавляется если отсутствует)
Player base из loyalty_true ГАРАНТИРОВАН даже при наличии NPC→NPC base_values

_enrich_with_social_relations (npc_loader.py — вызывается при загрузке)
Вход: List[NPC dict], Dict[str, Any] (relations из village_relations.json)
Мутирует NPC dicts in-place (только при загрузке)
Формат: relationship_cache[target_id] = {trust: base_trust100, fear: 0.0, base_trust: base_trust100, nature: str}
Формат: base_values[target_id] = base_trust * 100
Не перезаписывает существующие записи (runtime мог мутировать)
Шкала: 0-1 (JSON) → 0-100 (relationship_cache). Конвертация ×100
Источник не найден в NPC списке → пропуск с debug log
Некорректный rel_data (не dict) → пропуск без ошибки

GameLoop.idle_tick() Return Contract (dict)
status: str ("ok", "no_scene", "not_ready", "error")
changes: int
npc_positions: dict (DEPRECATED: читать из world_snapshot)
events: list
world_snapshot: Optional[dict] (конвертировано из WorldSnapshotDTO, UUID→str)
TickResultDTO (backend/app/services/tick_orchestrator.py)
status: str ("ok" | "error" | "no_scene")
error: Optional[str]
changes: int (DEPRECATED)
TickPlayerResultDTO (backend/app/services/tick_orchestrator.py)
status: str ("ok" | "error")
error: Optional[str]
npc_contexts: list
snapshot: Optional[dict]
events: List[Any]
dirty_npcs: set
activity_overrides: Dict[str, str]
max_npc_stress: float
movement_intents: list
finalize_result: Optional[dict]
EventDTO (backend/app/domain/events.py) — Паспорт события (Устав §2.1)
id: UUID
type: str (Использовать EventType.PLAYER_ATTACKS.value и др. Внутри шины хранятся как str!)
source: str (player_name | npc_id)
timestamp: float
payload: Dict[str, Any] (Обязательные ключи для player_attacks: intensity, actor_id, target_id)
visibility: Literal["public", "private", "whisper"]
radius: float
persistence_level: Literal["working", "session", "campaign"]
NpcTickServices (backend/app/services/npc/npc_tick_contracts.py)
memory_manager: Any
relationship_store: Any
social_engine: Any
reputation_engine: Any
economic_profiles: Any
event_bus: Any
spatial_service: Any # ДОБАВЛЕНО: Инжекция SpatialService
PerceivedScene (frontend/game_types.py)
location_id: str
entities: List[PerceivedEntity]
audio_events: List[AudioEvent]
environment: PerceivedEnvironment
attention_focus_id: Optional[str]
player_body_state: List[str]
---
InterpretationEngine.compute
state: NPCState
event: EventContext
player_reputation: Optional[Dict[str, int]]
drives_base: Dict[str, float] # ДОБАВЛЕНО: веса драйвов из profile_l0
NPCPositionDTO (backend/app/domain/snapshot.py)
npc_id: str
x: float
y: float
location_id: str
facing: str
action: str
display_name: str # КРИТИЧЕСКИ ВАЖНО: Должно заполняться из data.get("name") в WorldSnapshotBuilder, иначе фронтенд показывает npc_id!
---
NarrativeBeat (Frontend DTO)speaker: strtext: stris_player: booldelivery: DeliveryType (Enum: NORMAL, WHISPER, SHOUT, INTERNAL, PANIC, INTERRUPT)certainty: float (0.0 - 1.0)recognition: RecognitionLevel (Enum: UNKNOWN_MALE, UNKNOWN_FEMALE, STRANGE_FACE, KNOWN_NAME)lifetime: BeatLifetime (Enum: TRANSIENT, PINNED, SLAM)is_active: bool

TextInput (Frontend Widget)Поддержка инерции зажатия клавиш (update(dt)).Поддержка Shift+Enter (\n).Полный запрет Paste (Ctrl+V / Shift+Insert).
---

---
Session 14 Updates (08.05.2026 22:18)

check_random_events (backend/app/services/npc/life_engine.py)Возвращаемый тип: tuple[list[SceneChange], MovementIntent | None]Контракт: СТРОГО кортеж из 2 элементов. Возвращает ([], None) если NPC спит или событие не сгенерировано. Возвращает (changes, None) если событие обработано (intent уже применён внутри метода).НАРУШЕНИЕ КОНТРАКТА: Возврат голого списка [] или list[SceneChange] без оборачивания в кортеж приводит к крашу "not enough values to unpack" в _simulate_major/_simulate_minor.

SceneChange(field="position") — Статус: РАЗРЕШЕНО (ADR-0009)Ранее: Вызывало RuntimeError "Прямая мутация position запрещена".Сейчас: Страж смягчён. SceneChange(type=NPC_POSITION, field="position", value="main_hall") разрешён и является единственным легитимным способом обновить семантическую локацию NPC.Поведение SceneStateManager: При получении field="position" атомарно обновляет узел и резолвит local_position (x, y) через SpatialService.get_node().

MovementIntent — Область применения (LOD1: Macro Traversal)Архитектурное ограничение: MovementIntent используется ТОЛЬКО для перемещения между узлами макро-графа (main_hall -> bar_area, city -> forest).ЗАПРЕЩЕНО: Использовать MovementIntent для микро-перемещений внутри одной макро-зоны (target_node_id == from_node_id). Это приводит к онтологической лжи и архитектурной эрозии.

LocalSteeringIntent — ПЛАНИРУЕМАЯ DTO (LOD0: Micro Space)Статус: Не реализована. Требуется для визуального сближения NPC с объектами внутри одной макро-зоны.Назначение: Плавное перемещение (steering) к координатам (x,y) игрока или другого NPC без изменения семантического узла position.Поля (проект): npc_id, target_entity_id, target_xy, speed, arrival_radius.
---
StateDeltas (# v2: Domain-Tagged Typed Payloads. v1 поля LOCKED и депрекированы)
npc_id: Optional[str] (ОБЯЗАТЕЛЬНО для маршрутизации. None только для глобальных дельт)
domain: Optional[DeltaDomain] (v2: SOCIAL, EMOTION, REPUTATION, IDENTITY, COMBAT, PHYSIOLOGY, SPATIAL)
target: Optional[str] (v2: универсальный таргет — player, npc_id, faction_id)
payload: Optional[DeltaPayload] (v2: Union[SocialPayload, EmotionPayload, ReputationPayload, IdentityPayload])

# v1 backward compat (deprecated, удаляются после миграции DecisionHub)
intent_target: Optional[str] (DecisionHub → player-facing trust/fear)
social_target: Optional[str] (Social decay/propagation → NPC→NPC trust/fear)
faction_id: Optional[str] (Reputation decay → фракция, несовместим с trust/fear)
stress_delta: float (v1: масштаб 0-100)
emotion_delta: float (v1: масштаб -100..100)
emotion_tag: Optional[EmotionTag]
trust_delta: float (v1: масштаб 0-100)
fear_delta: float (v1: масштаб 0-100)
reputation_delta: float (v1: только с faction_id)
trait_updates: Dict[str, float]
new_trauma: Optional[str]
source: str
identity_integrity_delta: float
pressure_resistance_delta: float
will_state_override: Optional[WillState]

post_init валидация v2: если payload не None, его тип должен соответствовать domain (TypeError)
post_init валидация v1: один тип таргета, reputation_delta требует faction_id, trust/fear ≠ faction_id

DeltaDomain (Enum)
SOCIAL, EMOTION, REPUTATION, IDENTITY, COMBAT (FUTURE), PHYSIOLOGY (FUTURE), SPATIAL (FUTURE)

SocialPayload (frozen dataclass)
trust_delta: float = 0.0, fear_delta: float = 0.0, affection_delta: float = 0.0, debt_delta: float = 0.0

EmotionPayload (frozen dataclass)
stress_delta: float = 0.0, emotion_delta: float = 0.0, emotion_tag: Optional[str] = None, new_trauma: Optional[str] = None

ReputationPayload (frozen dataclass)
reputation_delta: float = 0.0

IdentityPayload (frozen dataclass)
identity_integrity_delta: float = 0.0, pressure_resistance_delta: float = 0.0, will_state_override: Optional[str] = None
---

---
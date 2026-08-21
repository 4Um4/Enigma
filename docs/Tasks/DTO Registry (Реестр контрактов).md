
---
(05.05.2026 22:25)
Phase8Result
deltas: List[StateDeltas] (список вычисленных, но не применённых изменений)
perceiving_npc_ids: Optional[Set[str]] (NPC, воспринявшие событие визуально/аудио)
socially_affected_npc_ids: Optional[Set[str]] (NPC, затронутые социальной пропагацией)
events_processed: int (количество обработанных событий)
prop_dirty: bool (DEPRECATED — флаг мутации, удаляется после полной миграции на delta_buffer)

StateDeltas (# LOCKED v1 — новые домены через рефакторинг, не через добавление полей)
npc_id: Optional[str] (маршрутизация к конкретному NPC)
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

GameLoop.idle_tick() Return Contract (dict)
status: str ("ok", "no_scene", "not_ready", "error")
changes: int
npc_positions: dict (DEPRECATED: читать из world_snapshot)
events: list
world_snapshot: Optional[dict] (конвертировано из WorldSnapshotDTO, UUID→str)
---

---
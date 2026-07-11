# -*- coding: utf-8 -*-
"""
Tick Utils — чистые функции тик-оркестратора (DRSL, Snapshots, Paths).

path: backend/app/services/tick_utils.py
Назначение: Изоляция stateless-логики из TickOrchestrator для соблюдения Устав §1.2 (domain isolation).
Зависимости: app.core.config, app.models.delta_payloads, app.models.idle_tick, app.models.state_delta, app.services.dto, app.services.events.event_types
Основные сущности: resolve_affected_npcs, build_npc_snapshots, aggregate_deltas, get_npc_runtime_path
"""

import logging
import types
from pathlib import Path
from typing import Any, Dict, List

from app.core.config import settings
from app.models.delta_payloads import (
    SocialPayload, EmotionPayload, ReputationPayload, IdentityPayload, PerceptionPayload
)
from app.models.idle_tick import NPCStateSnapshot
from app.models.state_delta import DeltaDomain, StateDeltas, ReductionPolicy
from app.services.dto import DELTA_POLICY_REGISTRY
from app.services.events.event_types import EventType

logger = logging.getLogger(__name__)


def resolve_affected_npcs(event) -> list[str]:
    """Определяет список NPC затронутых событием."""
    affected: list[str] = []
    etype = event.type

    if etype == EventType.NPC_MOVED.value:
        affected.append(event.source)
    elif etype in (
        EventType.NPC_PROXIMITY_CLOSE.value,
        EventType.NPC_PROXIMITY_LEAVE.value,
    ):
        affected.extend(
            (event.payload.get("npc_a", ""), event.payload.get("npc_b", ""))
        )

    return [n for n in affected if n]


def build_npc_snapshots(all_npcs_raw: list) -> list:
    """Проецирует all_npcs_raw → List[NPCStateSnapshot] для handlers.

    Handlers работают только с контрактом, не с внутренностями scene_state.

    Маппинг данных:
      social_stats.trust         → relationship_cache["player"]["trust"] (0-100)
      social_stats.fear_of_player → relationship_cache["player"]["fear"]
      psyche.loyalty_true        → base_values["player"] (базовое доверие к игроку)
      status_profile.faction_rank → faction_affiliations (ключи фракций)

    NPC-to-NPC связи обогащаются через _enrich_with_social_relations() при загрузке.
    После обогащения relationship_cache содержит записи NPC→NPC из village_relations.json.
    Player entry гарантированно добавляется из social_stats (даже при наличии NPC→NPC записей).
    """
    snapshots = []
    for npc in all_npcs_raw:
        if not isinstance(npc, dict):
            continue

        npc_id = npc.get("id", "")
        psyche = npc.get("psyche", {})
        ss = npc.get("social_stats", {})

        # relationship_cache: вложенный формат {target: {trust, fear, ...}}
        existing_rc = npc.get("relationship_cache", {})
        if isinstance(existing_rc, dict) and any(
            isinstance(v, dict) for v in existing_rc.values()
        ):
            relationship_cache = dict(existing_rc)
        else:
            relationship_cache = {}

        _player_trust = float(ss.get("trust", 0.0))
        _player_fear = float(ss.get("fear_of_player", 0.0))
        _player_debt = float(ss.get("debt", 0.0))
        if "player" not in relationship_cache and (_player_trust != 0.0 or _player_fear != 0.0 or _player_debt != 0.0):
            relationship_cache["player"] = {
                "trust": _player_trust,
                "fear": _player_fear,
                "debt": _player_debt,
            }

        existing_bv = npc.get("base_values", {})
        base_values = dict(existing_bv) if existing_bv else {}

        if "player" not in base_values:
            _loyalty = float(psyche.get("loyalty_true", 50.0))
            base_values["player"] = _loyalty

        if existing_fa := npc.get("faction_affiliations", []):
            faction_affiliations = existing_fa
        else:
            _faction_rank = npc.get("status_profile", {}).get("faction_rank", {})
            faction_affiliations = list(_faction_rank.keys())

        body_profile = npc.get("body_profile", {})
        body_state = npc.get("body_state", {})
        
        _max_hp = float(body_profile.get("max_hp", 100.0))
        _current_hp = float(body_state.get("current_hp", _max_hp))
        
        _base_abilities = body_profile.get("abilities", {})
        _modifiers = body_state.get("modifiers", {})
        _statuses = body_state.get("statuses", [])
        
        _raw_injuries = body_state.get("injuries", [])
        injuries_by_zone: Dict[str, list] = {}
        for inj in _raw_injuries:
            zone = inj.get("target_zone", "unknown")
            if zone not in injuries_by_zone:
                injuries_by_zone[zone] = []
            injuries_by_zone[zone].append(inj)
        
        _affective_load = float(npc.get("affective_load", 0.0))
        _emotion = str(npc.get("emotion", "neutral") or "neutral")

        snapshots.append(NPCStateSnapshot(
            npc_id=npc_id,
            stress=float(psyche.get("stress", 0.0)),
            relationship_cache=relationship_cache,
            base_values=base_values,
            faction_affiliations=faction_affiliations,
            hp=_current_hp,
            max_hp=_max_hp,
            pain=float(body_state.get("pain", 0.0)),
            fatigue=float(body_state.get("fatigue", 0.0)),
            blood_loss=float(body_state.get("blood_loss", 0.0)),
            consciousness=float(body_state.get("consciousness", 1.0)),
            shock_impulse=float(body_state.get("shock_impulse", 0.0)),
            life_status=str(body_state.get("life_status", "ALIVE")),
            injuries_by_zone=injuries_by_zone,
            base_abilities=_base_abilities,
            modifiers=_modifiers,
            statuses=_statuses,
            affective_load=_affective_load,
            emotion=_emotion,
        ))
    return snapshots


def _reduce_additive(p1, p2):
    """Сливает два payload для ADDITIVE/BOUNDED_ADDITIVE доменов."""
    if p1 is None: return p2
    if p2 is None: return p1
    if type(p1) != type(p2): return p2 

    if isinstance(p1, SocialPayload):
        return SocialPayload(
            trust_delta=p1.trust_delta + p2.trust_delta,
            fear_delta=p1.fear_delta + p2.fear_delta,
            affection_delta=p1.affection_delta + p2.affection_delta,
            debt_delta=p1.debt_delta + p2.debt_delta,
        )
    if isinstance(p1, EmotionPayload):
        return EmotionPayload(
            stress_delta=p1.stress_delta + p2.stress_delta,
            emotion_delta=p1.emotion_delta + p2.emotion_delta,
            emotion_tag=p2.emotion_tag if p2.emotion_tag is not None else p1.emotion_tag,
            new_trauma=p2.new_trauma if p2.new_trauma is not None else p1.new_trauma,
            affective_load=p2.affective_load if p2.affective_load is not None else p1.affective_load,
        )
    if isinstance(p1, ReputationPayload):
        return ReputationPayload(
            reputation_delta=p1.reputation_delta + p2.reputation_delta
        )
    if isinstance(p1, IdentityPayload):
        return IdentityPayload(
            identity_integrity_delta=p1.identity_integrity_delta + p2.identity_integrity_delta,
            pressure_resistance_delta=p1.pressure_resistance_delta + p2.pressure_resistance_delta,
            will_state_override=p2.will_state_override if p2.will_state_override is not None else p1.will_state_override,
        )
    if isinstance(p1, PerceptionPayload):
        return PerceptionPayload(
            threat_gradient_delta=p1.threat_gradient_delta + p2.threat_gradient_delta,
            uncertainty_delta=p1.uncertainty_delta + p2.uncertainty_delta,
            anomaly_score_delta=p1.anomaly_score_delta + p2.anomaly_score_delta,
        )
    return p2


def aggregate_deltas(deltas: list) -> list:
    """Domain Reduction Semantics Layer (DRSL): редукция по законам физики доменов.
    
    Мастер Тай: система не различала коммутативные и некоммутативные эффекты.
    Бухгалтерия (Social) ≠ Физика (Physiology). 
    
    PHYSICS_COMPOSITE (Physiology) обходит merge — это инъекции энергии в тело,
    они обрабатываются ImpactEngine/StateApplicator как эволюция состояния, а не сумма.
    """
    # Разделение потоков: Физика (PHYSICS_COMPOSITE) обходит merge
    physics_deltas = []
    algebraic_deltas = []

    for d in deltas:
        if not isinstance(d, StateDeltas):
            continue

        policy = DELTA_POLICY_REGISTRY.get(d.domain, ReductionPolicy.ADDITIVE)
        
        if policy == ReductionPolicy.PHYSICS_COMPOSITE:
            physics_deltas.append(d)
        else:
            algebraic_deltas.append(d)

    # Бухгалтерская редукция (ADDITIVE / BOUNDED_ADDITIVE / OVERWRITE)
    groups: dict[tuple, StateDeltas] = {}

    for d in algebraic_deltas:
        if d.domain is not None:
            key = (d.npc_id, d.domain, d.target)
        else:
            key = (d.npc_id, None, d.intent_target or d.social_target or d.faction_id)

        if key in groups:
            existing = groups[key]
            policy = DELTA_POLICY_REGISTRY.get(d.domain, ReductionPolicy.ADDITIVE)
            
            if policy == ReductionPolicy.OVERWRITE and d.domain == DeltaDomain.IDENTITY:
                existing.identity_integrity_delta += d.identity_integrity_delta
                existing.pressure_resistance_delta += d.pressure_resistance_delta
                if d.will_state_override is not None:
                    existing.will_state_override = d.will_state_override
                # S115 FIX: Мерж IdentityPayload (compliance_bias, recent_directive, etc.)
                # Без этого payload от DirectiveInterpretationSubscriber теряется при агрегации.
                from app.models.delta_payloads import IdentityPayload
                if isinstance(d.payload, IdentityPayload) and isinstance(existing.payload, IdentityPayload):
                    existing.payload.compliance_bias_delta += d.payload.compliance_bias_delta
                    existing.payload.aggression_inhibition_delta += d.payload.aggression_inhibition_delta
                    existing.payload.initiative_suppression_delta += d.payload.initiative_suppression_delta
                    if d.payload.recent_directive_data:
                        existing.payload.recent_directive_data = d.payload.recent_directive_data
            else:
                existing.stress_delta += d.stress_delta
                existing.emotion_delta += d.emotion_delta
                existing.trust_delta += d.trust_delta
                existing.fear_delta += d.fear_delta
                existing.reputation_delta += d.reputation_delta
                existing.identity_integrity_delta += d.identity_integrity_delta
                existing.pressure_resistance_delta += d.pressure_resistance_delta
                
                for k, v in d.trait_updates.items():
                    existing.trait_updates[k] = existing.trait_updates.get(k, 0.0) + v
            
            if d.intent_target is not None: existing.intent_target = d.intent_target
            if d.social_target is not None: existing.social_target = d.social_target
            if d.faction_id is not None: existing.faction_id = d.faction_id
            
            if d.source != "unknown":
                existing.source = d.source
            
            if d.emotion_tag is not None:
                existing.emotion_tag = d.emotion_tag
            if d.new_trauma is not None:
                existing.new_trauma = d.new_trauma
            if d.will_state_override is not None:
                existing.will_state_override = d.will_state_override

            existing.payload = _reduce_additive(existing.payload, d.payload)
        else:
            groups[key] = d

    _result = list(groups.values()) + physics_deltas
    if physics_deltas:
        logger.debug(f"[AGGREGATE] algebraic={len(groups.values())} physics={len(physics_deltas)} physics_domains={[d.domain for d in physics_deltas[:3]]}")
    return _result


def get_npc_runtime_path(campaign_id: str) -> Path:
    """Путь к runtime-данным NPC для кампании (saves_dir/campaign_id/npc_runtime.json)."""
    return Path(settings.saves_dir) / campaign_id / "npc_runtime.json"


def create_tick_context(
    campaign_id: str,
    scene_state: dict,
    tick_number: int,
    interventions: list,
    npc_services: Any,
    drf_bus: "DRFBus",
    all_npcs_raw: list = None,
    shared_context: Any = None,
) -> "_TickContext":
    """[S98] Чистая сборка _TickContext для TickOrchestrator.execute().
    
    Изолирует deepcopy, rng_factory и инициализацию DTO от сайд-эффектов оркестратора.
    """
    import copy
    from app.services.dto import _TickContext
    from app.services.npc.kernel_rng import KernelRNG

    # S83.1: Tick = Pure Function Evaluation. Freeze input snapshot.
    input_snapshot = copy.deepcopy(scene_state)

    # KERNEL-ISOLATION: factory для per-NPC deterministic RNG.
    _rng_factory = lambda npc_id: KernelRNG(tick=tick_number, npc_id=npc_id)

    # Извлекаем player_intent (IntentDTO) из interventions (если есть действие игрока)
    _player_intent = None
    if interventions:
        for _interv in interventions:
            if getattr(_interv, "source", "") == "player":
                _payload = getattr(_interv, "payload", {})
                _action_str = _payload.get("semantic_action", "OBSERVE")
                # Мапим строковое действие в стандартный формат IntentDTO
                from app.domain.intent import IntentDTO, IntentParametersDTO
                _params = IntentParametersDTO(
                    semantic_action=_action_str,
                    target_reference=_payload.get("target_id", ""),
                    target_id=_payload.get("target_id", ""),
                )
                _player_intent = IntentDTO(
                    action=_action_str.lower(), # 'attack', 'move', etc.
                    target=_payload.get("target_id", ""),
                    parameters=_params,
                    text=_payload.get("text", ""),
                )
                break

    _is_player = any(getattr(i, 'source', '') == 'player' for i in interventions)
    ctx = _TickContext(
        campaign_id=campaign_id,
        scene_state=input_snapshot,
        tick_number=tick_number,
        interventions=interventions,
        npc_services=npc_services,
        drf_bus=drf_bus,
        rng_factory=_rng_factory,
        player_intent=_player_intent,
        all_npcs_raw=all_npcs_raw or [],
        shared_context=shared_context if shared_context is not None else types.SimpleNamespace(), # S116 FIX: Проброс shared_context из game_loop
        is_player_turn=_is_player, # S116 FIX: Передаём флаг в контекст
    )
    return ctx
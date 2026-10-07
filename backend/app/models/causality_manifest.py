"""
path: /project/backend/app/models/causality_manifest.py
Назначение: Layer 2 INV-CONSUMER-GAP / Causal Anatomy (ADR-O-414) — закрытый
    semantic manifest жизненного цикла полей census Слоя 1. Транскрипция Stage 2a
    (S317): 174 typed + 24 container = 198 ключей, авторитетный источник —
    reports/CENSUS_DUMP_S2A.txt. Data-модуль: НОЛЬ логики.
    Правила вердиктов Мастера: CAUSAL = только живой runtime proof (reader ≠
    consequence); DEBT = «честно знаем, что не доказали проводку» (никогда не
    зелёный); PROJECTION требует authority («проекция чего, SSOT — кто»);
    organ ∈ десятка (decision — НЕ орган, это terminal); орган не считается
    живым по наличию state. Расширение mode/organ/terminal = строка реестра.
    Миграция DEBT→CAUSAL после сбора proof = расширение CAUSAL-множества =
    мини-запись (ТЗ §4). DEBT-записи поглотили debt-реестр Stage 1
    (consumer_gap_debts.py, вердикт Q-A: единственный semantic SSOT).
Зависимости: dataclasses, typing (без импортов app/ — чистые данные).
Основные сущности: KNOWN_ORGANS, KNOWN_TERMINALS, VALID_MODES, FieldCausality, FIELD_CAUSALITY
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional

# ── Целевая organ-онтология (мандат Мастера S317) ──────────────────────────
# decision — НЕ орган: это terminal/downstream consumer. Воля/identity-контур
# (will_state, life_project, drives_runtime) десяткой не покрывается —
# organ=None + вопрос Мастеру, НЕ молчаливое растяжение реестра.
KNOWN_ORGANS = frozenset({
    "perception", "memory", "relationship", "emotion", "desire",
    "body", "experience", "provenance", "role", "knowledge",
})

# Новое значение terminal — только после археологического подтверждения
# реального downstream endpoint (не «удобно звучит»).
KNOWN_TERMINALS = frozenset({
    "decision", "belief", "emotion", "desire", "relationship",
    "diagnostic", "projection", "persistence",
})

VALID_MODES = frozenset({"CAUSAL", "PROJECTION", "INPUT", "DEBT"})


@dataclass(frozen=True)
class FieldCausality:
    mode: str                        # ∈ VALID_MODES
    organ: Optional[str] = None      # ∈ KNOWN_ORGANS; обязателен для CAUSAL
    terminal: Optional[str] = None   # ∈ KNOWN_TERMINALS; обязателен для CAUSAL
    authority: Optional[str] = None  # обязателен для PROJECTION|DEBT
    proof: Optional[str] = None      # обязателен для CAUSAL; файл обязан существовать
    probe_hint: Optional[Dict[str, Any]] = None  # корм Layer 3: {"injection": 90.0}


FIELD_CAUSALITY: Dict[str, FieldCausality] = {
    # ═══ decision_view (CG-D-04: класс не конструируется никем) ═══
    "decision_view.identity": FieldCausality("DEBT", terminal="decision", authority="CG-D-04"),
    "decision_view.profile": FieldCausality("DEBT", terminal="decision", authority="CG-D-04"),
    "decision_view.state": FieldCausality("DEBT", terminal="decision", authority="CG-D-04"),

    # ═══ event_memory (organ=memory; контур recall жив, causal proof не собран) ═══
    "event_memory.event_type": FieldCausality("DEBT", organ="memory", terminal="persistence", authority="ADR-O-414"),
    "event_memory.target_id": FieldCausality("INPUT"),
    "event_memory.emotion_tag": FieldCausality("DEBT", organ="memory", terminal=None, authority="ADR-O-414"),
    "event_memory.day": FieldCausality("DEBT", organ="memory", terminal="persistence", authority="NL-D3"),  # day=0 у всех runtime-записей: писателя нет
    "event_memory.importance": FieldCausality("DEBT", organ="memory", terminal="persistence", authority="ADR-O-414"),
    "event_memory.clarity": FieldCausality("DEBT", organ="memory", terminal=None, authority="ADR-O-414"),
    "event_memory.confidence": FieldCausality("DEBT", organ="memory", terminal=None, authority="ADR-O-414"),
    "event_memory.decay_rate": FieldCausality("DEBT", organ="memory", terminal="persistence", authority="ADR-O-414"),
    "event_memory.stage": FieldCausality("DEBT", organ="memory", terminal="persistence", authority="ADR-O-414"),
    "event_memory.sequence_id": FieldCausality("DEBT", organ="memory", terminal="persistence", authority="ADR-O-414"),
    "event_memory.summary": FieldCausality("DEBT", organ="memory", terminal="persistence", authority="ADR-O-414"),
    "event_memory.npc_id": FieldCausality("INPUT"),
    "event_memory.tags": FieldCausality("DEBT", organ="memory", terminal=None, authority="ADR-O-414"),
    "event_memory.is_secret": FieldCausality("DEBT", organ="memory", terminal=None, authority="ADR-O-414"),
    "event_memory.known_by": FieldCausality("DEBT", organ="memory", terminal=None, authority="ADR-O-414"),
    "event_memory.hidden_from": FieldCausality("DEBT", organ="memory", terminal=None, authority="ADR-O-414"),
    "event_memory.accessibility": FieldCausality("DEBT", organ="memory", terminal=None, authority="ADR-O-414"),
    "event_memory.secret_id": FieldCausality("DEBT", organ="memory", terminal=None, authority="ADR-O-414"),
    "event_memory.fulfilled": FieldCausality("DEBT", organ="memory", terminal=None, authority="ADR-O-414"),
    "event_memory.contract_ref": FieldCausality("DEBT", organ="memory", terminal=None, authority="CG-D-11"),
    "event_memory.is_compressed": FieldCausality("DEBT", organ="memory", terminal=None, authority="ADR-O-414"),
    "event_memory.compressed_from": FieldCausality("DEBT", organ="memory", terminal=None, authority="CG-D-12"),
    "event_memory.actor_id": FieldCausality("DEBT", organ="memory", terminal=None, authority="ADR-O-414"),

    # ═══ npc_identity_l1 (L1-черты = накопленный опыт) ═══
    "npc_identity_l1.npc_id": FieldCausality("INPUT"),
    "npc_identity_l1.active_traits": FieldCausality("DEBT", organ="experience", terminal="decision", authority="ADR-O-414"),

    # ═══ npc_personality (L0-конфиг) ═══
    "npc_personality.npc_id": FieldCausality("INPUT"),
    "npc_personality.tier": FieldCausality("INPUT"),
    "npc_personality.drives_base": FieldCausality("DEBT", organ="desire", terminal="decision", authority="ADR-O-414"),
    "npc_personality.willpower": FieldCausality("DEBT", organ=None, terminal="decision", authority="ADR-O-414"),  # контур воли вне десятки — вопрос Мастеру
    "npc_personality.breakpoint": FieldCausality("DEBT", organ=None, terminal="decision", authority="CG-D-10"),
    "npc_personality.loyalty_base": FieldCausality("DEBT", organ="relationship", terminal=None, authority="CG-D-10"),
    "npc_personality.can_awaken": FieldCausality("DEBT", organ=None, terminal=None, authority="CG-D-10"),
    "npc_personality.voice_profile": FieldCausality("INPUT"),
    "npc_personality.backstory": FieldCausality("INPUT"),
    "npc_personality.author_notes": FieldCausality("INPUT"),
    "npc_personality.identity_rigidity": FieldCausality("DEBT", organ="experience", terminal="decision", authority="ADR-O-414"),
    "npc_personality.gregariousness": FieldCausality("DEBT", organ=None, terminal=None, authority="CG-D-09"),

    # ═══ npc_state ═══
    "npc_state.npc_id": FieldCausality("INPUT"),
    "npc_state.gender": FieldCausality("INPUT"),
    "npc_state.stress": FieldCausality("DEBT", organ="emotion", terminal="decision", authority="ADR-O-414"),
    "npc_state.affective_load": FieldCausality("DEBT", organ="emotion", terminal="decision", authority="ADR-O-414"),
    "npc_state.affective_memory": FieldCausality("DEBT", organ="memory", terminal=None, authority="ADR-O-414"),
    "npc_state.social_input_ema": FieldCausality("DEBT", organ="relationship", terminal="decision", authority="ADR-O-414"),
    "npc_state.resentment": FieldCausality("DEBT", organ="relationship", terminal="decision", authority="ADR-O-414"),
    "npc_state.dependency": FieldCausality("DEBT", organ="relationship", terminal="decision", authority="ADR-O-414"),
    "npc_state.identity_integrity": FieldCausality("DEBT", organ="experience", terminal="decision", authority="ADR-O-414"),
    "npc_state.pressure_resistance": FieldCausality("DEBT", organ="experience", terminal="decision", authority="ADR-O-414"),
    "npc_state.recent_failures": FieldCausality("DEBT", organ="memory", terminal="decision", authority="ADR-O-414"),
    "npc_state.will_state": FieldCausality("DEBT", organ=None, terminal="decision", authority="ADR-O-414"),  # воля вне десятки
    "npc_state.behavior_mask": FieldCausality("DEBT", organ=None, terminal="projection", authority="RE-D9"),  # канал мёртв end-to-end (выборка 4)
    "npc_state.trauma_markers": FieldCausality("DEBT", organ="experience", terminal="decision", authority="ADR-O-414"),
    "npc_state.beliefs": FieldCausality("CAUSAL", organ="knowledge", terminal="decision",
                                        proof="backend/tests/sandbox/SUPERBOX/scenarios/causal_state_test.py", authority="S243"),
    "npc_state.life_project": FieldCausality("DEBT", organ=None, terminal="decision", authority="ADR-O-414"),  # identity-контур вне десятки
    "npc_state.life_project_state": FieldCausality("DEBT", organ=None, terminal="decision", authority="ADR-O-414"),
    "npc_state.body_state": FieldCausality("INPUT"),  # carrier-контейнер; семантика — в body_state.* ключах
    "npc_state.perceptual_kernel": FieldCausality("INPUT"),  # carrier; семантика — в perceptual_kernel.*
    "npc_state.affective_imprints": FieldCausality("DEBT", organ="memory", terminal=None, authority="CG-D-05"),  # двойной носитель
    "npc_state.current_role": FieldCausality("DEBT", organ="role", terminal="decision", authority="ADR-O-414"),
    "npc_state.role_history": FieldCausality("DEBT", organ="role", terminal="diagnostic", authority="CG-D-B1"),
    "npc_state.drives_runtime": FieldCausality("DEBT", organ="desire", terminal="decision", authority="ADR-O-414"),
    "npc_state.strain_memory": FieldCausality("DEBT", organ="experience", terminal=None, authority="CG-D-B1"),
    "npc_state.temporary_drives": FieldCausality("DEBT", organ="desire", terminal="decision", authority="ADR-O-414"),
    "npc_state.body_capabilities": FieldCausality("DEBT", organ="body", terminal="decision", authority="ADR-O-414"),
    "npc_state.conditions": FieldCausality("DEBT", organ="body", terminal="decision", authority="ADR-O-414"),
    "npc_state.wounds": FieldCausality("DEBT", organ="body", terminal="decision", authority="CG-D-B1"),
    "npc_state.threat_accumulator": FieldCausality("DEBT", organ="perception", terminal="decision", authority="CG-D-B1"),
    "npc_state.posture": FieldCausality("DEBT", organ="body", terminal=None, authority="ADR-O-414"),
    "npc_state.emotion": FieldCausality("DEBT", organ="emotion", terminal="projection", authority="ADR-O-414"),
    "npc_state.emotion_delta": FieldCausality("DEBT", organ="emotion", terminal=None, authority="ADR-O-414"),
    "npc_state.state_modifiers": FieldCausality("DEBT", organ="emotion", terminal=None, authority="CG-D-B1"),
    "npc_state.trait_activation": FieldCausality("DEBT", organ="experience", terminal=None, authority="CG-D-B1"),
    "npc_state.intent": FieldCausality("DEBT", organ=None, terminal=None, authority="ADR-O-414"),  # выход нервной системы, не орган
    "npc_state.intent_target": FieldCausality("INPUT"),
    "npc_state.intent_formed_at": FieldCausality("INPUT"),
    "npc_state.intent_duration": FieldCausality("DEBT", organ=None, terminal=None, authority="ADR-O-414"),
    "npc_state.intent_progress_ticks": FieldCausality("DEBT", organ=None, terminal=None, authority="ADR-O-414"),
    "npc_state.last_intent_change": FieldCausality("DEBT", organ=None, terminal=None, authority="CG-D-07"),
    "npc_state.pressure_accumulator": FieldCausality("DEBT", organ="relationship", terminal="decision", authority="CG-D-B1"),
    "npc_state.relationship_cache": FieldCausality("PROJECTION", organ="relationship", terminal="projection", authority="ADR-O-370"),  # проекция V2Store; SSOT — RelationshipStateStore
    "npc_state.cache_timestamp": FieldCausality("DEBT", organ="memory", terminal=None, authority="CG-D-06"),
    "npc_state.narrative_cache": FieldCausality("DEBT", organ="memory", terminal="decision", authority="ADR-O-414"),
    "npc_state.causal_ledger": FieldCausality("DEBT", organ="provenance", terminal="diagnostic", authority="ADR-O-414"),

    # ═══ perceptual_kernel (organ=perception) ═══
    "perceptual_kernel.threat_gradient": FieldCausality("DEBT", organ="perception", terminal="decision", authority="ADR-O-414"),
    "perceptual_kernel.trust_gradient": FieldCausality("DEBT", organ="perception", terminal=None, authority="CG-D-01"),
    "perceptual_kernel.uncertainty": FieldCausality("DEBT", organ="perception", terminal="decision", authority="ADR-O-414"),
    "perceptual_kernel.anomaly_score": FieldCausality("DEBT", organ="perception", terminal="decision", authority="ADR-O-414"),
    "perceptual_kernel.last_hostile_direction": FieldCausality("DEBT", organ="perception", terminal=None, authority="CG-D-03"),
    "perceptual_kernel.dominant_emotion": FieldCausality("DEBT", organ="perception", terminal=None, authority="CG-D-02"),
    "perceptual_kernel.aggression_inhibition": FieldCausality("DEBT", organ="emotion", terminal="decision", authority="ADR-O-414"),
    "perceptual_kernel.initiative_suppression": FieldCausality("DEBT", organ="emotion", terminal="decision", authority="ADR-O-414"),
    "perceptual_kernel.compliance_bias": FieldCausality("DEBT", organ="emotion", terminal="decision", authority="ADR-O-414"),
    "perceptual_kernel.somatic_urgency": FieldCausality("DEBT", organ="perception", terminal="decision", authority="ADR-O-414"),
    "perceptual_kernel.recent_directive": FieldCausality("DEBT", organ=None, terminal="decision", authority="ADR-O-414"),

    # ═══ role_change_entry (CG-D-13: diagnostic-only, PROJECTION-декларация) ═══
    "role_change_entry.from_role": FieldCausality("PROJECTION", organ="role", terminal="diagnostic", authority="CG-D-13"),
    "role_change_entry.to_role": FieldCausality("PROJECTION", organ="role", terminal="diagnostic", authority="CG-D-13"),
    "role_change_entry.tick": FieldCausality("INPUT"),
    "role_change_entry.reason": FieldCausality("PROJECTION", organ="role", terminal="diagnostic", authority="CG-D-13"),

    # ═══ state_delta flat (транспорт дельт) ═══
    "state_delta.npc_id": FieldCausality("INPUT"),
    "state_delta.source": FieldCausality("INPUT"),
    "state_delta.domain": FieldCausality("INPUT"),
    "state_delta.target": FieldCausality("INPUT"),
    "state_delta.intent_target": FieldCausality("INPUT"),
    "state_delta.social_target": FieldCausality("INPUT"),
    "state_delta.faction_id": FieldCausality("INPUT"),
    "state_delta.intent": FieldCausality("INPUT"),
    "state_delta.intent_tick": FieldCausality("INPUT"),
    "state_delta.payload": FieldCausality("INPUT"),  # carrier
    "state_delta.stress_delta": FieldCausality("DEBT", organ="emotion", terminal="decision", authority="ADR-O-414"),
    "state_delta.stress_delta_effective": FieldCausality("DEBT", organ="emotion", terminal="decision", authority="ADR-O-414"),
    "state_delta.emotion_delta": FieldCausality("DEBT", organ="emotion", terminal="decision", authority="ADR-O-414"),
    "state_delta.emotion_tag": FieldCausality("DEBT", organ="emotion", terminal="decision", authority="ADR-O-414"),
    "state_delta.trust_delta": FieldCausality("DEBT", organ="relationship", terminal="decision", authority="ADR-O-414"),
    "state_delta.fear_delta": FieldCausality("DEBT", organ="relationship", terminal="decision", authority="ADR-O-414"),
    "state_delta.reputation_delta": FieldCausality("DEBT", organ=None, terminal="persistence", authority="ADR-O-414"),
    "state_delta.trait_updates": FieldCausality("DEBT", organ="experience", terminal=None, authority="CG-D-B1"),
    "state_delta.new_trauma": FieldCausality("DEBT", organ="experience", terminal=None, authority="ADR-O-414"),
    "state_delta.identity_integrity_delta": FieldCausality("DEBT", organ="experience", terminal="decision", authority="ADR-O-414"),
    "state_delta.pressure_resistance_delta": FieldCausality("DEBT", organ="experience", terminal="decision", authority="ADR-O-414"),
    "state_delta.will_state_override": FieldCausality("DEBT", organ=None, terminal="decision", authority="ADR-O-414"),

    # ═══ payload: emotion ═══
    "state_delta.emotion_payload.stress_delta": FieldCausality("DEBT", organ="emotion", terminal="decision", authority="ADR-O-414"),
    "state_delta.emotion_payload.emotion_delta": FieldCausality("DEBT", organ="emotion", terminal="decision", authority="ADR-O-414"),
    "state_delta.emotion_payload.emotion_tag": FieldCausality("DEBT", organ="emotion", terminal="decision", authority="ADR-O-414"),
    "state_delta.emotion_payload.new_trauma": FieldCausality("DEBT", organ="experience", terminal=None, authority="ADR-O-414"),
    "state_delta.emotion_payload.affective_load": FieldCausality("DEBT", organ="emotion", terminal="decision", authority="ADR-O-414"),
    "state_delta.emotion_payload.affective_memory": FieldCausality("DEBT", organ="memory", terminal=None, authority="ADR-O-414"),

    # ═══ payload: identity ═══
    "state_delta.identity_payload.identity_integrity_delta": FieldCausality("DEBT", organ="experience", terminal="decision", authority="ADR-O-414"),
    "state_delta.identity_payload.pressure_resistance_delta": FieldCausality("DEBT", organ="experience", terminal="decision", authority="ADR-O-414"),
    "state_delta.identity_payload.drives_snapshot": FieldCausality("DEBT", organ="desire", terminal=None, authority="ADR-O-414"),
    "state_delta.identity_payload.strain_snapshot": FieldCausality("DEBT", organ="experience", terminal=None, authority="ADR-O-414"),
    "state_delta.identity_payload.aggression_inhibition_delta": FieldCausality("DEBT", organ="emotion", terminal="decision", authority="ADR-O-414"),
    "state_delta.identity_payload.initiative_suppression_delta": FieldCausality("DEBT", organ="emotion", terminal="decision", authority="ADR-O-414"),
    "state_delta.identity_payload.compliance_bias_delta": FieldCausality("DEBT", organ="emotion", terminal="decision", authority="ADR-O-414"),
    "state_delta.identity_payload.will_state_override": FieldCausality("DEBT", organ=None, terminal="decision", authority="ADR-O-414"),
    "state_delta.identity_payload.recent_directive_data": FieldCausality("DEBT", organ=None, terminal="decision", authority="ADR-O-414"),

    # ═══ payload: injury (ADR-123 домен) ═══
    "state_delta.injury_dto.damage_type": FieldCausality("DEBT", organ="body", terminal=None, authority="ADR-123"),
    "state_delta.injury_dto.target_zone": FieldCausality("DEBT", organ="body", terminal=None, authority="ADR-123"),
    "state_delta.injury_dto.structural_damage": FieldCausality("DEBT", organ="body", terminal=None, authority="ADR-123"),
    "state_delta.injury_dto.functional_loss": FieldCausality("DEBT", organ="body", terminal="decision", authority="ADR-123"),  # carrier-gap: ридер по дикту injuries (vital_state:198)
    "state_delta.injury_dto.critical_effects": FieldCausality("DEBT", organ="body", terminal=None, authority="ADR-123"),  # info-only by design

    # ═══ payload: perception ═══
    "state_delta.perception_payload.threat_gradient_delta": FieldCausality("DEBT", organ="perception", terminal="decision", authority="ADR-O-414"),
    "state_delta.perception_payload.uncertainty_delta": FieldCausality("DEBT", organ="perception", terminal="decision", authority="ADR-O-414"),
    "state_delta.perception_payload.anomaly_score_delta": FieldCausality("DEBT", organ="perception", terminal="decision", authority="ADR-O-414"),

    # ═══ payload: physiology ═══
    "state_delta.physiology_payload.hp_delta": FieldCausality("DEBT", organ="body", terminal=None, authority="ADR-123"),
    "state_delta.physiology_payload.pain_delta": FieldCausality("DEBT", organ="body", terminal="decision", authority="ADR-O-383", probe_hint={"injection": 95.0}),
    "state_delta.physiology_payload.fatigue_delta": FieldCausality("DEBT", organ="body", terminal="decision",
                                                                   authority="ADR-O-383", probe_hint={"injection": 90.0}),  # транспорт; CAUSAL живёт на container-ключе body_state.fatigue
    "state_delta.physiology_payload.blood_loss_delta": FieldCausality("DEBT", organ="body", terminal="decision", authority="ADR-O-383", probe_hint={"injection": 0.5}),
    "state_delta.physiology_payload.shock_impulse": FieldCausality("DEBT", organ="body", terminal="decision", authority="ADR-O-383", probe_hint={"injection": 0.95}),
    "state_delta.physiology_payload.energy_delta": FieldCausality("DEBT", organ="body", terminal="decision",
                                                                  authority="ADR-O-383", probe_hint={"injection": -90.0}),  # транспорт; CAUSAL живёт на container-ключе body_state.energy
    "state_delta.physiology_payload.hydration_delta": FieldCausality("DEBT", organ="body", terminal=None, authority="NL-D9"),  # разрыв decision (выборка 3)
    "state_delta.physiology_payload.nutrition_delta": FieldCausality("DEBT", organ="body", terminal=None, authority="NL-D9"),
    "state_delta.physiology_payload.add_injuries": FieldCausality("DEBT", organ="body", terminal=None, authority="ADR-123"),
    "state_delta.physiology_payload.add_statuses": FieldCausality("DEBT", organ="body", terminal=None, authority="ADR-123"),
    "state_delta.physiology_payload.remove_statuses": FieldCausality("DEBT", organ="body", terminal=None, authority="ADR-123"),

    # ═══ payload: social ═══
    "state_delta.social_payload.trust_delta": FieldCausality("DEBT", organ="relationship", terminal="decision", authority="ADR-O-414"),
    "state_delta.social_payload.fear_delta": FieldCausality("DEBT", organ="relationship", terminal="decision", authority="ADR-O-414"),
    "state_delta.social_payload.affection_delta": FieldCausality("DEBT", organ="relationship", terminal="decision", authority="ADR-O-414"),
    "state_delta.social_payload.debt_delta": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-414"),
    "state_delta.social_payload.social_input_ema_delta": FieldCausality("DEBT", organ="relationship", terminal="decision", authority="ADR-O-414"),

    # ═══ payload: reputation (нет flat-близнеца — единственный payload без flat-пары; пропущен при транскрипции, пойман bidirectional-гейтом до IPT) ═══
    "state_delta.reputation_payload.reputation_delta": FieldCausality("DEBT", organ=None, terminal="persistence", authority="ADR-O-414"),

    # ═══ payload: economic ═══
    "state_delta.economic_payload.money_delta": FieldCausality("DEBT", organ=None, terminal=None, authority="ADR-O-414"),
    "state_delta.economic_payload.goods_delta": FieldCausality("DEBT", organ=None, terminal=None, authority="S310"),  # β-Stage 2 живые швы

    # ═══ payload: will_conflict ═══
    "state_delta.will_conflict_payload.state": FieldCausality("DEBT", organ=None, terminal="projection", authority="ADR-O-414"),
    "state_delta.will_conflict_payload.resistance": FieldCausality("DEBT", organ=None, terminal="projection", authority="ADR-O-414"),
    "state_delta.will_conflict_payload.embodied_vector": FieldCausality("DEBT", organ=None, terminal="projection", authority="ADR-O-414"),
    "state_delta.will_conflict_payload.identity_damage": FieldCausality("DEBT", organ=None, terminal="projection", authority="ADR-O-414"),
    # ═══ ADR-O-418 (RE M2/D): need_delta_payload — RE-события → NeedLevel ═══
    # writer: relationship_event_semantics (pure reducer); reader:
    # state_applicator.apply_relationship_deltas → update_needs →
    # RelationshipStateStore (scene_state-backed, ADR-O-370). DEBT по
    # прецеденту payload-полей (статика ≠ consequence); миграция DEBT→CAUSAL
    # после SUPERBOX-proof — мини-запись (канон шапки манифеста).
    # ADR-O-418 (RE M2/D): миграция DEBT→CAUSAL после живого proof —
    # re_m2d_needs_test (SUPERBOX Treatment: INTIMATE_REJECTION → полный тик →
    # read-back frustration из персистентной сцены). source_event_id — DEBT:
    # ридер = [RE_NEEDS]-лог (E4-класс), пертурбация не собрана; terminal=None
    # несовместим с CAUSAL.
    "state_delta.need_delta_payload.need_id": FieldCausality("CAUSAL", organ="relationship", terminal="relationship", proof="backend/tests/sandbox/SUPERBOX/scenarios/re_m2d_needs_test.py"),
    "state_delta.need_delta_payload.pressure_delta": FieldCausality("CAUSAL", organ="relationship", terminal="relationship", proof="backend/tests/sandbox/SUPERBOX/scenarios/re_m2d_needs_test.py"),
    "state_delta.need_delta_payload.satiation_delta": FieldCausality("CAUSAL", organ="relationship", terminal="relationship", proof="backend/tests/sandbox/SUPERBOX/scenarios/re_m2d_needs_test.py"),
    "state_delta.need_delta_payload.frustration_delta": FieldCausality("CAUSAL", organ="relationship", terminal="relationship", proof="backend/tests/sandbox/SUPERBOX/scenarios/re_m2d_needs_test.py"),
    "state_delta.need_delta_payload.source_event_id": FieldCausality("DEBT", organ="provenance", terminal=None, authority="ADR-O-418"),

    # ═══ ADR-O-419 (RE G/H): time-driven контур ═══
    # need_slot.gen_rate — read-only конфиг-поле слота (writer by design нет;
    # читатель — relationship_dynamics, контур Фазы 0.5 за флагом). DEBT по
    # прецеденту NO_WRITER×9 группы need_slot.
    # NOTE: служебная книга кванта (relationship_state.dynamics.last_quantum_seconds)
    # НЕ декларируется: census Слоя 1 не собирает relationship_state-*dict-ключи
    # (CONTAINER_DOMAINS = body_state/needs, линтер ADR-O-414) — манифест = транскрипция
    # census (шапка), запись вне census = ложный STALE. Покрытие книги — микротесты
    # test_re_gh_dynamics (noop-чистота/mark-коммит) + SUPERBOX re_gh_dynamics_test;
    # расширение CONTAINER_DOMAINS — отдельное решение по санкции Мастера.
    "need_slot.gen_rate": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-419"),
    # ═══ ADR-O-419 NOTE→декларация (S334, задача 2): census собирает
    # relationship_state-домен (CONTAINER_DOMAINS + top-level const-резолв,
    # мини-ADR сканера O-414) — книга кванта легализована в манифесте.
    # Писатель (need_dynamics_mark через _ensure_dict-обёртку) невидим
    # тупому слою — честный NO_WRITER подавлен DEBT; leaf
    # last_quantum_seconds живёт внутри dynamics-дикта (вложенная ступень
    # вне верхнего уровня census Слоя 1; покрывается записью домена).
    # Вербатим NOTE S329: FieldCausality("DEBT", organ="relationship",
    # terminal="persistence", authority="ADR-O-419")
    "relationship_state.dynamics": FieldCausality("DEBT", organ="relationship", terminal="persistence", authority="ADR-O-419"),
    # directed — v2-поддерево 5 скаляров (M1b, ADR-O-371): runtime-писатель —
    # RAM-стор (sync_into_scene/бутстрап; слепота слоя к методам класса =
    # честный NO_WRITER); reader — scene_init:297 (бутстрап RAM-носителя).
    # DEBT по вердикту Мастера S334: искусственных writers не ищем;
    # жизненный цикл — фаза K removal-test.
    "relationship_state.directed": FieldCausality("DEBT", organ="relationship", terminal="persistence", authority="ADR-O-370"),

    # ═══ temporary_drive (organ=desire) ═══
    "temporary_drive.drive_type": FieldCausality("DEBT", organ="desire", terminal="decision", authority="ADR-O-414"),
    "temporary_drive.urgency": FieldCausality("DEBT", organ="desire", terminal="decision", authority="ADR-O-414"),
    "temporary_drive.reason": FieldCausality("DEBT", organ="desire", terminal=None, authority="ADR-O-414"),
    "temporary_drive.source_npc_id": FieldCausality("DEBT", organ="desire", terminal=None, authority="ADR-O-414"),
    "temporary_drive.tick_born": FieldCausality("INPUT"),
    "temporary_drive.tick_age": FieldCausality("INPUT"),

    # ═══ body_state (organ=body; контейнерные ключи) ═══
    "body_state.current_hp": FieldCausality("DEBT", organ="body", terminal="decision", authority="ADR-123"),
    "body_state.max_hp": FieldCausality("DEBT", organ="body", terminal=None, authority="ADR-123"),
    "body_state.pain": FieldCausality("DEBT", organ="body", terminal="decision", authority="ADR-O-383", probe_hint={"injection": 95.0}),
    "body_state.fatigue": FieldCausality("CAUSAL", organ="body", terminal="decision",
                                         proof="backend/tests/gameplay/test_gc09_body_causality.py", authority="ADR-O-383", probe_hint={"injection": 90.0}),
    "body_state.blood_loss": FieldCausality("DEBT", organ="body", terminal="decision", authority="ADR-O-383", probe_hint={"injection": 0.5}),
    "body_state.consciousness": FieldCausality("DEBT", organ="body", terminal="decision", authority="ADR-123"),
    "body_state.shock_impulse": FieldCausality("DEBT", organ="body", terminal="decision", authority="ADR-O-383", probe_hint={"injection": 0.95}),
    "body_state.energy": FieldCausality("CAUSAL", organ="body", terminal="decision",
                                        proof="backend/tests/gameplay/test_gc09_body_causality.py", authority="ADR-O-383", probe_hint={"injection": -90.0}),
    "body_state.hydration": FieldCausality("DEBT", organ="body", terminal=None, authority="NL-D9"),  # разрыв decision (выборка 3)
    "body_state.nutrition": FieldCausality("DEBT", organ="body", terminal=None, authority="NL-D9"),
    "body_state.hunger": FieldCausality("DEBT", organ="body", terminal=None, authority="ADR-O-414"),
    "body_state.statuses": FieldCausality("DEBT", organ="body", terminal=None, authority="ADR-123"),
    "body_state.injuries": FieldCausality("DEBT", organ="body", terminal="decision", authority="ADR-123"),
    "body_state.sleep_onset_tick": FieldCausality("DEBT", organ="body", terminal="decision", authority="ADR-O-375"),
    "body_state.sleep_pressure": FieldCausality("DEBT", organ="body", terminal="decision", authority="ADR-O-356"),
    "body_state.arousal": FieldCausality("DEBT", organ="body", terminal="decision", authority="ADR-O-356"),
    "body_state.wake_duration": FieldCausality("DEBT", organ="body", terminal=None, authority="ADR-O-375"),
    "body_state.coupling_profile": FieldCausality("DEBT", organ="body", terminal=None, authority="D-MOM"),  # orphaned derived state
    "body_state.modifiers": FieldCausality("DEBT", organ="body", terminal=None, authority="ADR-O-414"),
    "body_state.body_mass": FieldCausality("DEBT", organ="body", terminal=None, authority="CG-D-14"),
    "body_state.shock": FieldCausality("DEBT", organ="body", terminal=None, authority="CG-D-08"),  # phantom-read; канон shock_impulse
    "body_state.disabled": FieldCausality("DEBT", organ="body", terminal="decision", authority="ADR-O-414"),
    "body_state.money": FieldCausality("DEBT", organ=None, terminal=None, authority="ADR-SSOT-ECONOMIC"),
    "body_state.life_status": FieldCausality("DEBT", organ="body", terminal=None, authority="ADR-123"),

    # ═══ Stage 2b-2: экспансия Relationship/Desire/Knowledge/Memory/Experience ═══
    # (дамп CENSUS_DUMP_S2B.txt; 93 ключа. Контексты: ADR-O-370 (RE-контракты,
    # substrate dormant), ADR-O-394/395/397/413 (R5–R8 slices), O-354/355/357/358/
    # 360 (эпистемика S188-эпохи), NL-D4 (memory_crystal/experience_trace — слой
    # спит: модели+SQLite есть, писателей нет). Все DEBT — field-level proof не
    # собран; контурные proof (S243/GC-вертикали) ≠ покрывают поля — честность Q-B.
    # organ-разметка — первый живой coverage десятки.)

    # ── need_slot (organ=relationship; ADR-O-370; NO_WRITER×9 — substrate dormant) ──
    "need_slot.need_id": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),
    "need_slot.target_pressure": FieldCausality("DEBT", organ="relationship", terminal="decision", authority="ADR-O-370"),
    "need_slot.deficit_threshold": FieldCausality("DEBT", organ="relationship", terminal="decision", authority="ADR-O-370"),
    "need_slot.importance": FieldCausality("DEBT", organ="relationship", terminal="decision", authority="ADR-O-370"),
    "need_slot.rigidity": FieldCausality("DEBT", organ="relationship", terminal="decision", authority="ADR-O-370"),
    "need_slot.substitutability": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),
    "need_slot.adaptability": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),
    "need_slot.satiation_capacity": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),
    "need_slot.object_binding": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),
    "need_slot.homeostatic": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),
    "need_slot.change_rate": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),

    # ── need_level (organ=relationship) ──
    "need_level.need_id": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),
    "need_level.current_intensity": FieldCausality("DEBT", organ="relationship", terminal="decision", authority="ADR-O-370"),
    "need_level.satiation": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),
    "need_level.frustration": FieldCausality("DEBT", organ="relationship", terminal="decision", authority="ADR-O-370"),

    # ── preference_model / hard_constraint / exclusivity_requirement (RE-фазы) ──
    "preference_model.pref_id": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),
    "preference_model.strength": FieldCausality("DEBT", organ="relationship", terminal="decision", authority="ADR-O-370"),
    "preference_model.flexibility": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),
    "preference_model.confidence": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),
    "preference_model.learning_rate": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),
    "hard_constraint.constraint_id": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),
    "hard_constraint.necessity": FieldCausality("DEBT", organ="relationship", terminal="decision", authority="ADR-O-370"),
    "hard_constraint.violation_cost": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),
    "hard_constraint.negotiability": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),
    "hard_constraint.substitutability": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),
    "exclusivity_requirement.scope": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),
    "exclusivity_requirement.importance": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),
    "exclusivity_requirement.rigidity": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),
    "exclusivity_requirement.negotiability": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),
    "exclusivity_requirement.violation_cost": FieldCausality("DEBT", organ="relationship", terminal=None, authority="ADR-O-370"),

    # ── desired_change (organ=desire; R5–R8 production-proven контур) ──
    "desired_change.who": FieldCausality("DEBT", organ="desire", terminal="decision", authority="ADR-O-394"),
    "desired_change.reason": FieldCausality("DEBT", organ="desire", terminal="decision", authority="ADR-O-394"),
    "desired_change.state_type": FieldCausality("DEBT", organ="desire", terminal="decision", authority="ADR-O-394"),
    "desired_change.target_of_change": FieldCausality("DEBT", organ="desire", terminal="decision", authority="ADR-O-394"),
    "desired_change.addressee": FieldCausality("DEBT", organ="desire", terminal="decision", authority="ADR-O-413"),
    "desired_change.method_weights": FieldCausality("DEBT", organ="desire", terminal="decision", authority="ADR-O-394"),

    # ── proposition (organ=knowledge) ──
    "proposition.subject_id": FieldCausality("DEBT", organ="knowledge", terminal="belief", authority="ADR-O-354"),
    "proposition.predicate": FieldCausality("DEBT", organ="knowledge", terminal="belief", authority="ADR-O-354"),
    "proposition.object_id": FieldCausality("DEBT", organ="knowledge", terminal="belief", authority="ADR-O-354"),
    "proposition.polarity": FieldCausality("DEBT", organ="knowledge", terminal="belief", authority="ADR-O-354"),

    # ── claim_event (organ=knowledge; listener_id NO_READER — живая находка) ──
    "claim_event.event_id": FieldCausality("DEBT", organ="knowledge", terminal=None, authority="ADR-O-354"),
    "claim_event.claim_id": FieldCausality("DEBT", organ="knowledge", terminal=None, authority="ADR-O-354"),
    "claim_event.speaker_id": FieldCausality("DEBT", organ="knowledge", terminal="belief", authority="ADR-O-357"),
    "claim_event.listener_id": FieldCausality("DEBT", organ="knowledge", terminal=None, authority="ADR-O-354"),  # NO_READER: маршрутизация, не потребление
    "claim_event.proposition": FieldCausality("DEBT", organ="knowledge", terminal="belief", authority="ADR-O-354"),
    "claim_event.speech_act": FieldCausality("DEBT", organ="knowledge", terminal=None, authority="ADR-O-354"),
    "claim_event.tick": FieldCausality("INPUT"),

    # ── epistemic_record / epistemic_context (organ=knowledge) ──
    "epistemic_record.agent_id": FieldCausality("DEBT", organ="knowledge", terminal=None, authority="ADR-O-355"),
    "epistemic_record.proposition": FieldCausality("DEBT", organ="knowledge", terminal="decision", authority="ADR-O-355"),
    "epistemic_record.confidence": FieldCausality("DEBT", organ="knowledge", terminal="decision", authority="ADR-O-357"),
    "epistemic_record.source_id": FieldCausality("DEBT", organ="knowledge", terminal=None, authority="ADR-O-360"),
    "epistemic_record.source_claim_id": FieldCausality("DEBT", organ="knowledge", terminal=None, authority="ADR-O-355"),
    "epistemic_record.first_observed_tick": FieldCausality("INPUT"),
    "epistemic_record.last_updated_tick": FieldCausality("DEBT", organ="knowledge", terminal=None, authority="ADR-O-355"),
    "epistemic_context.agent_id": FieldCausality("DEBT", organ="knowledge", terminal=None, authority="ADR-O-355"),
    "epistemic_context.perceived_threats": FieldCausality("DEBT", organ="knowledge", terminal="decision", authority="ADR-O-355"),
    "epistemic_context.perceived_allies": FieldCausality("DEBT", organ="knowledge", terminal="decision", authority="ADR-O-355"),
    "epistemic_context.perceived_violations": FieldCausality("DEBT", organ="knowledge", terminal="decision", authority="ADR-O-355"),
    "epistemic_context.max_confidence": FieldCausality("DEBT", organ="knowledge", terminal="decision", authority="ADR-O-355"),
    "epistemic_context.trigger_proposition": FieldCausality("DEBT", organ="knowledge", terminal="decision", authority="ADR-O-355"),
    "epistemic_context.claims_about_self": FieldCausality("DEBT", organ="knowledge", terminal="decision", authority="ADR-O-390"),
    "epistemic_context.max_self_confidence": FieldCausality("DEBT", organ="knowledge", terminal="decision", authority="ADR-O-390"),

    # ── memory_crystal (organ=memory; NL-D4: слой спит) ──
    "memory_crystal.subject": FieldCausality("DEBT", organ="memory", terminal=None, authority="NL-D4"),
    "memory_crystal.predicate": FieldCausality("DEBT", organ="memory", terminal=None, authority="NL-D4"),
    "memory_crystal.object": FieldCausality("DEBT", organ="memory", terminal=None, authority="NL-D4"),
    "memory_crystal.source": FieldCausality("DEBT", organ="memory", terminal=None, authority="NL-D4"),
    "memory_crystal.origin_reference": FieldCausality("DEBT", organ="memory", terminal=None, authority="NL-D4"),
    "memory_crystal.related_episodes": FieldCausality("DEBT", organ="memory", terminal=None, authority="NL-D4"),
    "memory_crystal.confidence": FieldCausality("DEBT", organ="memory", terminal=None, authority="NL-D4"),
    "memory_crystal.retrieval_strength": FieldCausality("DEBT", organ="memory", terminal=None, authority="NL-D4"),
    "memory_crystal.emotional_weight": FieldCausality("DEBT", organ="memory", terminal=None, authority="NL-D4"),
    "memory_crystal.last_reinforced": FieldCausality("DEBT", organ="memory", terminal=None, authority="NL-D4"),
    "memory_crystal.times_recalled": FieldCausality("DEBT", organ="memory", terminal=None, authority="NL-D4"),
    "memory_crystal.owner_id": FieldCausality("DEBT", organ="memory", terminal=None, authority="NL-D4"),
    "memory_crystal.campaign_id": FieldCausality("INPUT"),

    # ── experience_trace (organ=experience; NL-D4) ──
    "experience_trace.actor_id": FieldCausality("DEBT", organ="experience", terminal=None, authority="NL-D4"),
    "experience_trace.owner_id": FieldCausality("DEBT", organ="experience", terminal=None, authority="NL-D4"),
    "experience_trace.source_id": FieldCausality("DEBT", organ="experience", terminal=None, authority="NL-D4"),
    "experience_trace.source_type": FieldCausality("DEBT", organ="experience", terminal=None, authority="NL-D4"),
    "experience_trace.content_reference": FieldCausality("DEBT", organ="experience", terminal=None, authority="NL-D4"),
    "experience_trace.meaning": FieldCausality("DEBT", organ="experience", terminal=None, authority="NL-D4"),
    "experience_trace.valence": FieldCausality("DEBT", organ="experience", terminal=None, authority="NL-D4"),
    "experience_trace.arousal": FieldCausality("DEBT", organ="experience", terminal=None, authority="NL-D4"),
    "experience_trace.novelty": FieldCausality("DEBT", organ="experience", terminal=None, authority="NL-D4"),
    "experience_trace.personal_relevance": FieldCausality("DEBT", organ="experience", terminal=None, authority="NL-D4"),
    "experience_trace.social_relevance": FieldCausality("DEBT", organ="experience", terminal=None, authority="NL-D4"),
    "experience_trace.identity_relevance": FieldCausality("DEBT", organ="experience", terminal=None, authority="NL-D4"),
    "experience_trace.belief_relevance": FieldCausality("DEBT", organ="experience", terminal=None, authority="NL-D4"),
    "experience_trace.confidence": FieldCausality("DEBT", organ="experience", terminal=None, authority="NL-D4"),
    "experience_trace.retrieval_strength": FieldCausality("DEBT", organ="experience", terminal=None, authority="NL-D4"),
    "experience_trace.timestamp": FieldCausality("DEBT", organ="experience", terminal=None, authority="NL-D4"),  # NO_WRITER: слой спит; INPUT не легализует сиротство (самопоймал №2-прогон 2b-2)
    "experience_trace.diagnostic": FieldCausality("DEBT", organ="experience", terminal=None, authority="NL-D4"),
    "experience_trace.applied_consumers": FieldCausality("DEBT", organ="experience", terminal=None, authority="NL-D4"),
}

"""
A21.2 End-to-End Autonomous Rumor Chain.
Фиксирует числовую траекторию уверенности и реальные выборы NPC.
Не принуждает к spread_rumor — только предоставляет условия.
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock
from dataclasses import dataclass

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.domain.epistemology import Proposition, Predicate, ClaimEvent, SpeechAct, EpistemicRecord
from app.services.npc.epistemic_store import EpistemicStore
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.services.npc.trust_based_reliability_provider import TrustBasedReliabilityProvider
from app.services.npc.decision_hub import DecisionHub
from app.models.npc_state import NPCState, EmotionTag, WillState


@dataclass
class MockDrives:
    values: dict
    def get(self, key, default=0.0):
        return self.values.get(key, default)


class MockRelStore:
    def __init__(self, trust_map):
        self._trust = trust_map
    def get_pair(self, campaign_id, observer, source):
        rel = MagicMock()
        rel.trust = self._trust.get((observer, source), 50.0)
        return rel


def _make_state(npc_id):
    state = MagicMock()
    state.npc_id = npc_id
    state.emotion = EmotionTag.NEUTRAL
    state.intent = None
    state.intent_target = None
    state.commitment = 0.0
    state.stress = 10.0
    state.will_state = WillState.FREE
    state.fatigue = 0.0
    state.hunger = 0.0
    state.health = 100.0
    state.relationship_cache = {}
    state.narrative_cache = []
    state.behavior_mask = MagicMock()
    state.behavior_mask.mask = None
    state.behavior_mask.is_active = False
    return state


def _make_profile(archetype):
    p = MagicMock()
    p.archetype = archetype
    return p


def test_autonomous_rumor_chain_trajectory():
    """
    Цепочка: A (вор) -> C (служанка) -> D (страж) -> E (торговец).
    Фиксируем уверенность и реальный выбор интента на каждом этапе.
    """
    prop = Proposition(subject_id="A", predicate=Predicate.STOLE, object_id="B")

    # Социальная сеть: все доверяют друг другу умеренно
    trust_map = {
        ("C", "A"): 60.0,
        ("D", "C"): 70.0,
        ("E", "D"): 60.0,
        ("C", "D"): 50.0,
        ("D", "E"): 50.0,
    }
    rel_store = MockRelStore(trust_map)
    provider = TrustBasedReliabilityProvider(relationship_store=rel_store, campaign_id="test")
    engine = BeliefRevisionEngine(reliability_provider=provider)

    stores = {npc: EpistemicStore() for npc in ["C", "D", "E"]}
    resolvers = {npc: EpistemicContextResolver(store=stores[npc]) for npc in stores}

    trajectory = []

    # === Этап 1: C становится свидетелем кражи A (direct_observation) ===
    # Даём слуху初始 вес 0.9, чтобы измерить пропускную способность сети,
    # а не умереть на пороге REPORT_CONFIDENCE_THRESHOLD=0.25.
    claim_a_c = ClaimEvent(
        event_id="e1", claim_id="claim_1", speaker_id="A", listener_id="C",
        proposition=prop, speech_act=SpeechAct.ASSERT, tick=1
    )
    rec_c = engine.revise("C", claim_a_c, None, {
        "source_type": "direct_observation", "original_source_id": "A"
    })
    stores["C"].upsert(rec_c)
    trajectory.append(("A->C", rec_c.confidence, None, None))

    # === Этап 2: C принимает решение ===
    ctx_c = resolvers["C"].resolve("C")
    mods_c = resolvers["C"].to_modifiers(ctx_c, archetype="maid")

    spatial = MagicMock()
    spatial.distance.return_value = 1.0

    hub = DecisionHub(seed=42)
    # Мокаем _get_rel_value для target selection
    hub._get_rel_value = lambda st, cid, key: trust_map.get((st.npc_id, cid), 0.0) if key == "trust" else 0.0

    event = MagicMock()
    event.event_type = "STOLE"
    event.witness_count = 1
    event.intensity = 0.5
    event.distance = 1.0
    event.actor_id = "A"
    event.target_id = "B"
    event.scene_flags = set()
    event.scene_facts = []
    event.location = "tavern"

    drives = MockDrives(values={"hunger": 0.1, "safety": 0.3, "control": 0.2})

    decision_c = hub.compute(
        state=_make_state("C"),
        personality=_make_profile("maid"),
        effective_drives=drives,
        event=event,
        epistemic_context=ctx_c,
        epistemic_modifiers=mods_c,
        spatial_query=spatial,
        all_npc_ids=["A", "B", "C", "D", "E"],
    )

    intent_c = decision_c.decision.intent.value
    target_c = decision_c.decision.intent_target
    trajectory.append(("C decision", rec_c.confidence, intent_c, target_c))

    # === Этап 3: Если C выбрал spread_rumor, передаём D ===
    if intent_c == "spread_rumor" and target_c:
        claim_c_d = ClaimEvent(
            event_id="e2", claim_id="claim_1", speaker_id="C", listener_id=target_c,
            proposition=prop, speech_act=SpeechAct.ASSERT, tick=2
        )
        rec_d = engine.revise(target_c, claim_c_d, None, {
            "source_type": "testimony",
            "original_source_id": "A",
            "speaker_confidence": rec_c.confidence
        })
        stores[target_c].upsert(rec_d)
        trajectory.append((f"C->{target_c}", rec_d.confidence, None, None))

        # === Этап 4: D принимает решение ===
        ctx_d = resolvers[target_c].resolve(target_c)
        mods_d = resolvers[target_c].to_modifiers(ctx_d, archetype="guard")

        decision_d = hub.compute(
            state=_make_state(target_c),
            personality=_make_profile("guard"),
            effective_drives=drives,
            event=event,
            epistemic_context=ctx_d,
            epistemic_modifiers=mods_d,
            spatial_query=spatial,
            all_npc_ids=["A", "B", "C", "D", "E"],
        )
        intent_d = decision_d.decision.intent.value
        target_d = decision_d.decision.intent_target
        trajectory.append((f"{target_c} decision", rec_d.confidence, intent_d, target_d))

        # === Этап 5: Если D выбрал spread_rumor, передаём E ===
        if intent_d == "spread_rumor" and target_d:
            claim_d_e = ClaimEvent(
                event_id="e3", claim_id="claim_1", speaker_id=target_c, listener_id=target_d,
                proposition=prop, speech_act=SpeechAct.ASSERT, tick=3
            )
            rec_e = engine.revise(target_d, claim_d_e, None, {
                "source_type": "testimony",
                "original_source_id": "A",
                "speaker_confidence": rec_d.confidence
            })
            stores[target_d].upsert(rec_e)
            trajectory.append((f"{target_c}->{target_d}", rec_e.confidence, None, None))

    # === ОТЧЁТ ===
    print("\n" + "="*60)
    print("A21.2 ЧИСЛОВАЯ ТРАЕКТОРИЯ АВТОНОМНОЙ ЦЕПОЧКИ")
    print("="*60)
    for stage, conf, intent, target in trajectory:
        if intent:
            print(f"{stage:20s} | confidence={conf:.4f} | intent={intent:15s} | target={target}")
        else:
            print(f"{stage:20s} | confidence={conf:.4f}")
    print("="*60)

    # Проверяем, что хотя бы первый этап прошёл
    assert trajectory[0][1] > 0.0, "C должен получить ненулевую уверенность"
    assert ctx_c.report_proposition is not None, "C должен иметь proposition для слуха"

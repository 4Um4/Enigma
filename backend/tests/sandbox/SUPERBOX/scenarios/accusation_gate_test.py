"""
SUPERBOX-ACCUSATION (S211, слой 4, §18): убеждение игрока = способность действовать.

  [C1] belief (shadow, STOLE, gold) conf=0.9 → ACCUSE проходит (None)
  [C2] belief conf=0.4 (слабый слух) → отклонено, причина содержит "epistemic gate"
  [C3] belief отсутствует → отклонено
  [C4] ЛОЖНОЕ обвинение: belief о невиновном (guard_borko, STOLE, gold) conf=0.8
       → ПРОХОДИТ — «поверил — и ошибся»: гейт проверяет веру, не истину;
       истинность решат NPC-реакции (эмерджентно), не флаг движка
  [C5] Последствия: RelationshipStore-дельта применена к цели (fear +25, trust −15)

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/accusation_gate_test.py
"""
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from app.domain.epistemology import Predicate, Proposition
from app.models.player_action import ActionType, PlayerAction
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
from app.services.npc.epistemic_store import EpistemicStore
from app.services.player_cognition.action_consequence_compiler import (
    ActionConsequenceCompiler,
)
from app.services.player_cognition.observation_log import ObservationLog
from app.services.player_cognition.player_belief_model import PlayerBeliefModel
from app.services.memory.relationship_store import RelationshipStore
from app.services.social.social_fabric_tracker import SocialFabricTracker

CAMP = "accusation_test"


def _make_compiler(rel_store, resolver):
    comp = ActionConsequenceCompiler(
        observation_log=ObservationLog(),
        belief_model=PlayerBeliefModel(),
        social_fabric=SocialFabricTracker(),
        truth_state=None,
        faction_tracker=None,
        relationship_store=rel_store,
        epistemic_resolver=resolver,
    )
    comp._campaign_id = CAMP
    return comp


def _give_belief(store, engine, subject, conf_provider_value=0.8):
    """Игрок получает belief через живой движок ревизии (не инъекцию!)."""
    from app.domain.events import EventDTO
    from app.domain.epistemology import ClaimEvent
    # создаём belief напрямую движком (claim от источника с высокой reliability)
    prop = Proposition(subject_id=subject, predicate=Predicate.STOLE,
                       object_id="gold", polarity=True)
    claim = ClaimEvent(event_id="e1", claim_id=f"c-{subject}", speaker_id="goran",
                       listener_id="player", proposition=prop, tick=1)
    record = engine.revise("player", claim, None)
    store.upsert(record)
    return record


def main() -> int:
    print("=" * 64)
    print("SUPERBOX-ACCUSATION: убеждение игрока = способность (S211, §18)")
    print("=" * 64)
    ok = True

    store = EpistemicStore()
    engine = BeliefRevisionEngine(
        reliability_provider=type("P", (), {"get_reliability": staticmethod(
            lambda observer, source, context=None: 0.9)})()
    )
    resolver = EpistemicContextResolver(store=store)
    rel = RelationshipStore(data_dir=tempfile.mkdtemp(prefix="acc_gate_"))
    comp = _make_compiler(rel, resolver)

    def _accuse(target, tick):
        return comp.process_action(PlayerAction(
            action_id=f"act-{tick}", tick=tick, actor_id="player",
            action_type=ActionType.ACCUSE, target_id=target, description="обвиняю"))

    # ── C3: без belief ──────────────────────────────────────────────
    r3 = _accuse("thief_shadow", 1)
    c3 = isinstance(r3, str) and "epistemic gate" in r3
    print(f"[C3] Без belief: отклонено ('{r3[:48]}...') — {'✅' if c3 else '❌'}")
    ok = ok and c3

    # ── C1: сильный belief (0.9 от движка ревизии) ──────────────────
    _give_belief(store, engine, "thief_shadow")
    r1 = _accuse("thief_shadow", 2)
    c1 = r1 is None
    print(f"[C1] Belief conf=0.9: ACCUSE прошёл — {'✅' if c1 else '❌'}")
    ok = ok and c1

    # ── C2: слабый belief (0.4 — ниже порога) ───────────────────────
    from app.domain.epistemology import EpistemicRecord
    store.upsert(EpistemicRecord(
        agent_id="player",
        proposition=Proposition(subject_id="maid_lusya", predicate=Predicate.STOLE,
                                object_id="gold", polarity=True),
        confidence=0.4, source_id="rumor", source_claim_id="c-weak",
        first_observed_tick=1, last_updated_tick=1))
    r2 = _accuse("maid_lusya", 3)
    c2 = isinstance(r2, str) and "conf=0.40" in r2
    print(f"[C2] Слабый слух (0.4): отклонено — {'✅' if c2 else '❌'}")
    ok = ok and c2

    # ── C4: ЛОЖНОЕ обвинение проходит (вера ≠ истина) ───────────────
    _give_belief(store, engine, "guard_borko")
    r4 = _accuse("guard_borko", 4)
    c4 = r4 is None
    print(f"[C4] Ложное обвинение невиновного (вера 0.9): ПРОХОДИТ — "
          f"{'✅' if c4 else '❌'} (истину решат NPC, не движок)")
    ok = ok and c4

    # ── C5: последствия (RelationshipStore) ─────────────────────────
    _pair = rel.get_pair(CAMP, "guard_borko", "player") or {}
    c5 = _pair.get("fear", 0.0) > 0.0 and _pair.get("trust", 100.0) < 100.0
    print(f"[C5] Дельты применены: fear={_pair.get('fear')}, trust={_pair.get('trust')} "
          f"— {'✅' if c5 else '❌'}")
    ok = ok and c5

    print("=" * 64)
    print("🎉 УБЕЖДЕНИЕ = СПОСОБНОСТЬ: игрок действует из знания — и может ошибиться."
          if ok else "❌ ТЕСТ С ОШИБКАМИ")
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
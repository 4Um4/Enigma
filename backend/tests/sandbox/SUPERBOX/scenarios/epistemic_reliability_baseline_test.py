"""
SUPERBOX-RELIABILITY-BASELINE: BEFORE/AFTER трейс канонизации testimony reliability.

Гейт ADR-O-357 (enforcement, вариант (a)):

  BEFORE — RelationshipReliabilityProvider (инлайн; УДАЛЁН в S20x. Режим before
  умирает ImportError по дизайну — артефакт reports/reliability_baseline_before.json
  сохранён как зафиксированная история до-канонизации);
  AFTER  — TrustBasedReliabilityProvider (канонический, назначенный аудитом ADR-O-357).

Трейс фиксирует ТОЛЬКО наблюдаемые выходы (reliability, confidence, modifiers),
не внутренности провайдеров. Любая AFTER-девиация сверх предегистрированной
delta-матрицы (H1/H2: нет дельты; H3b/H3c: предсказанная дельта врага)
= регрессия с известным источником.

Запуск:
  python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_reliability_baseline_test.py before
  python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_reliability_baseline_test.py after

Артефакт: reports/reliability_baseline_{before|after}.json
"""

import json
import logging
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("RELIABILITY_BASELINE")
logger.setLevel(logging.INFO)

from app.domain.events import EventDTO
from app.services.events.event_types import EventType
from app.services.events.claim_event_subscriber import ClaimEventSubscriber
from app.services.memory.relationship_store import RelationshipStore
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
from app.services.npc.epistemic_store import EpistemicStore
from app.services.spatial.spatial_query_service import SpatialQueryService

CAMPAIGN_ID = "reliability_baseline"
PLAYER = "player"
SOURCE = "npc_src"       # источник в сценариях A
FRIEND = "npc_friend"    # фиксированный друг (trust=80) в сценариях B
SUBJECT = "thief_shadow"
OBJECT = "gold"

# Сценарий A: один источник, create + same-source repeat.
TRUST_LEVELS_A = (-100.0, -50.0, -31.0, -30.0, -10.0, 0.0, 50.0, 100.0)
# Сценарий B: друг создаёт P, враг подтверждает (cross-source), враг повторяет (same-source).
# Здесь живёт предсказанная дельта H3b/H3c.
TRUST_LEVELS_B = (-100.0, -50.0, -31.0)


def _make_provider(mode: str, rel_store: Any):
    """Конструирует провайдер согласно режиму. Ленивый импорт: BEFORE-ветка
    умрёт после удаления инлайна — это ожидаемо, BEFORE-артефакт уже зафиксирован."""
    if mode == "before":
        from app.services.events.claim_event_subscriber import (
            RelationshipReliabilityProvider as Provider,
        )
    elif mode == "after":
        from app.services.npc.trust_based_reliability_provider import (
            TrustBasedReliabilityProvider as Provider,
        )
    else:
        raise ValueError(f"Неизвестный режим: {mode!r} (ожидался before|after)")
    return Provider(rel_store, CAMPAIGN_ID), Provider.__name__


def _make_pipe(mode: str, rel_store: Any, positions: Dict[str, Dict[str, Any]]):
    """Собирает живую трубу provider → engine → store → subscriber (паттерн SUPERBOX-014)."""
    provider, provider_name = _make_provider(mode, rel_store)
    store = EpistemicStore()
    engine = BeliefRevisionEngine(reliability_provider=provider)
    sq = SpatialQueryService(npc_positions=positions)
    subscriber = ClaimEventSubscriber(
        engine=engine, store=store, spatial_query_provider=lambda: sq
    )
    return provider, provider_name, store, subscriber


def _publish_claim(subscriber: ClaimEventSubscriber, speaker: str, tick: int) -> None:
    """Публикация COMMUNICATION_CLAIM напрямую в подписчика (минуя шину —
    шинный путь покрыт INV-PLAYER-EPISTEMIC-CLOSURE)."""
    event = EventDTO.create(
        event_type=EventType.COMMUNICATION_CLAIM.value,
        source=speaker,
        payload={
            "target_id": PLAYER,
            "claim_id": f"{speaker}-{tick}",
            "proposition": {
                "subject_id": SUBJECT,
                "predicate": "stole",
                "object_id": OBJECT,
                "polarity": True,
            },
            "speech_act": "assert",
            "tick": tick,
        },
    )
    subscriber.on_claim_event(event)


def _observe(store: EpistemicStore) -> Dict[str, Any]:
    """Наблюдаемые выходы: confidence топ-убеждения игрока + модификаторы резолвера."""
    record = store.get(PLAYER)
    conf = round(record.confidence, 4) if record else None
    context = EpistemicContextResolver(store=store).resolve(PLAYER)
    modifiers = EpistemicContextResolver.to_modifiers(context)
    return {
        "confidence": conf,
        "perceived_threats": list(context.perceived_threats),
        "modifiers": {k: round(v, 4) for k, v in modifiers.items()},
    }


def _scenario_a(mode: str, trust: Optional[float], tmp_root: Path, idx: int,
                speaker: str = SOURCE, preset_trust: bool = True) -> Dict[str, Any]:
    """Сценарий A: единственный источник. create (tick=1) + same-source repeat (tick=2)."""
    rel_store = RelationshipStore(data_dir=str(tmp_root / f"a{idx}"))
    if preset_trust and trust is not None:
        rel_store.update(CAMPAIGN_ID, PLAYER, speaker, {"trust": trust})
    positions = {
        PLAYER: {"local_position": {"x": 0.0, "y": 0.0}},
        speaker: {"local_position": {"x": 1.0, "y": 0.0}},
    }
    provider, provider_name, store, subscriber = _make_pipe(mode, rel_store, positions)

    reliability = round(provider.get_reliability(observer=PLAYER, source=speaker), 4)
    _publish_claim(subscriber, speaker, tick=1)
    create_obs = _observe(store)
    _publish_claim(subscriber, speaker, tick=2)
    repeat_obs = _observe(store)

    return {
        "trust": trust,
        "reliability": reliability,
        "create": create_obs,
        "same_source_repeat": repeat_obs,
    }


def _scenario_b(mode: str, enemy_trust: float, tmp_root: Path, idx: int) -> Dict[str, Any]:
    """Сценарий B (дельта H3b/H3c): друг (trust=80) создаёт P →
    враг подтверждает ту же пропозицию (cross-source update) →
    враг повторяет (same-source update)."""
    rel_store = RelationshipStore(data_dir=str(tmp_root / f"b{idx}"))
    rel_store.update(CAMPAIGN_ID, PLAYER, FRIEND, {"trust": 80.0})
    rel_store.update(CAMPAIGN_ID, PLAYER, "npc_enemy", {"trust": enemy_trust})
    positions = {
        PLAYER: {"local_position": {"x": 0.0, "y": 0.0}},
        FRIEND: {"local_position": {"x": 1.0, "y": 0.0}},
        "npc_enemy": {"local_position": {"x": 2.0, "y": 0.0}},
    }
    provider, provider_name, store, subscriber = _make_pipe(mode, rel_store, positions)

    rel_friend = round(provider.get_reliability(observer=PLAYER, source=FRIEND), 4)
    rel_enemy = round(provider.get_reliability(observer=PLAYER, source="npc_enemy"), 4)

    _publish_claim(subscriber, FRIEND, tick=1)      # create от друга
    friend_obs = _observe(store)
    _publish_claim(subscriber, "npc_enemy", tick=2)  # cross-source confirm
    cross_obs = _observe(store)
    _publish_claim(subscriber, "npc_enemy", tick=3)  # same-source repeat
    repeat_obs = _observe(store)

    return {
        "enemy_trust": enemy_trust,
        "reliability_friend": rel_friend,
        "reliability_enemy": rel_enemy,
        "friend_create": friend_obs,
        "enemy_cross_confirm": cross_obs,
        "enemy_same_repeat": repeat_obs,
    }


def run_baseline(mode: str) -> Dict[str, Any]:
    tmp_root = Path(tempfile.mkdtemp(prefix="rel_baseline_"))
    logger.info(f"[BASELINE] mode={mode}, tmp={tmp_root}")

    scenarios_a: List[Dict[str, Any]] = []
    failures: List[str] = []

    for i, t in enumerate(TRUST_LEVELS_A):
        try:
            scenarios_a.append(_scenario_a(mode, t, tmp_root, i))
        except Exception as e:  # ошибка фиксируется в артефакте, не глотается (L4)
            scenarios_a.append({"trust": t, "error": f"{type(e).__name__}: {e}"})
            failures.append(f"A[{t}]")

    scenarios_b: List[Dict[str, Any]] = []
    for i, t in enumerate(TRUST_LEVELS_B):
        try:
            scenarios_b.append(_scenario_b(mode, t, tmp_root, i))
        except Exception as e:
            scenarios_b.append({"enemy_trust": t, "error": f"{type(e).__name__}: {e}"})
            failures.append(f"B[{t}]")

    edge_cases: List[Dict[str, Any]] = []
    # H1: store отсутствует (provider с None).
    try:
        edge_cases.append({"case": "store_missing", **_scenario_a(
            mode, None, tmp_root, 90, preset_trust=False,
        )} if False else {"case": "store_missing", **_edge_store_missing(mode)})
    except Exception as e:
        edge_cases.append({"case": "store_missing", "error": f"{type(e).__name__}: {e}"})
        failures.append("EDGE[store_missing]")
    # H2: незнакомая пара (свежий store, никакой update).
    try:
        edge_cases.append({"case": "unknown_pair", **_edge_unknown_pair(mode, tmp_root)})
    except Exception as e:
        edge_cases.append({"case": "unknown_pair", "error": f"{type(e).__name__}: {e}"})
        failures.append("EDGE[unknown_pair]")

    return {
        "mode": mode,
        "scenarios_single_source": scenarios_a,
        "scenarios_cross_source": scenarios_b,
        "edge_cases": edge_cases,
        "failures": failures,
    }


def _edge_store_missing(mode: str) -> Dict[str, Any]:
    provider, provider_name = _make_provider(mode, None)
    store = EpistemicStore()
    engine = BeliefRevisionEngine(reliability_provider=provider)
    positions = {
        PLAYER: {"local_position": {"x": 0.0, "y": 0.0}},
        SOURCE: {"local_position": {"x": 1.0, "y": 0.0}},
    }
    sq = SpatialQueryService(npc_positions=positions)
    subscriber = ClaimEventSubscriber(
        engine=engine, store=store, spatial_query_provider=lambda: sq
    )
    reliability = round(provider.get_reliability(observer=PLAYER, source=SOURCE), 4)
    _publish_claim(subscriber, SOURCE, tick=1)
    return {"reliability": reliability, **_observe(store)}


def _edge_unknown_pair(mode: str, tmp_root: Path) -> Dict[str, Any]:
    # Свежий RelationshipStore без единой update — эмпирически вскрывает
    # фактический контракт get_pair для незнакомой пары (Runtime Data First).
    rel_store = RelationshipStore(data_dir=str(tmp_root / "edge_unknown"))
    provider, provider_name, store, subscriber = _make_pipe(
        mode, rel_store,
        {PLAYER: {"local_position": {"x": 0.0, "y": 0.0}},
         "npc_stranger": {"local_position": {"x": 1.0, "y": 0.0}}},
    )
    reliability = round(provider.get_reliability(observer=PLAYER, source="npc_stranger"), 4)
    _publish_claim(subscriber, "npc_stranger", tick=1)
    return {"reliability": reliability, **_observe(store)}


def main() -> int:
    mode = (sys.argv[1].lower() if len(sys.argv) > 1 else "before")
    if mode not in ("before", "after"):
        print(f"Неизвестный режим: {mode!r}. Ожидался before|after.")
        return 2

    result = run_baseline(mode)

    out_dir = BACKEND_ROOT.parent / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"reliability_baseline_{mode}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 64)
    print(f"RELIABILITY BASELINE [{mode.upper()}]")
    print("=" * 64)
    for s in result["scenarios_single_source"]:
        if "error" in s:
            print(f"  A trust={s['trust']:>7}: ERROR {s['error']}")
        else:
            print(f"  A trust={s['trust']:>7}: rel={s['reliability']:>7} "
                  f"create={s['create']['confidence']} repeat={s['same_source_repeat']['confidence']}")
    for s in result["scenarios_cross_source"]:
        if "error" in s:
            print(f"  B enemy={s['enemy_trust']:>7}: ERROR {s['error']}")
        else:
            print(f"  B enemy={s['enemy_trust']:>7}: rel_e={s['reliability_enemy']:>7} "
                  f"friend={s['friend_create']['confidence']} "
                  f"cross={s['enemy_cross_confirm']['confidence']} "
                  f"repeat={s['enemy_same_repeat']['confidence']}")
    for e in result["edge_cases"]:
        print(f"  EDGE {e['case']}: {e.get('reliability', e.get('error'))} "
              f"conf={e.get('confidence', '-')}")

    print(f"\nАртефакт: {out_path}")
    if result["failures"]:
        print(f"❌ Сценарии с ошибками: {result['failures']}")
        return 1
    print("✅ Все сценарии записаны.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
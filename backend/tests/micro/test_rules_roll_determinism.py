"""П-13 вердикты 2-3 Мастера: salt-детерминизм живого rules-roll + чистые social checks."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.events.rules_subscriber import RulesSubscriber


def _event(source: str = "player", tick: int = 100, etype: str = "player_attacks", target: str = "merchant_goran") -> SimpleNamespace:
    return SimpleNamespace(type=etype, payload={"target_id": target}, source=source, id=f"rules_{tick}")


def _snapshot(tick: int = 100, target: str = "merchant_goran") -> dict:
    return {
        "all_npcs_raw": [{"npc_id": target, "name": "Горан", "_archetype": "merchant"}],
        "tick_number": tick,
        "campaign_id": "test",
        "relationship_store": None,
        "raw_input": "ударить",
    }


def test_t1_determinism_same_inputs_same_roll():
    sub = RulesSubscriber()
    r1 = sub.handle(_event(tick=42), _snapshot(tick=42)).roll
    r2 = sub.handle(_event(tick=42), _snapshot(tick=42)).roll
    assert r1 == r2, "same (tick, actor, action, target) обязан давать тот же roll"


def test_t2_no_tick_degeneration_across_actors():
    sub = RulesSubscriber()
    rolls = {sub.handle(_event(source=f"p{i}"), _snapshot()).roll for i in range(10)}
    assert len(rolls) >= 2, (
        "разные actor на одном тике обязаны давать разные роллы "
        f"(дегенерация f(tick)); получено: {sorted(rolls)}"
    )


def test_t3_bounds_across_ticks():
    sub = RulesSubscriber()
    rolls = [sub.handle(_event(tick=t), _snapshot(tick=t)).roll for t in range(50)]
    assert all(1 <= r <= 20 for r in rolls), f"roll вне [1,20]: {sorted(set(rolls))}"
    assert len(set(rolls)) >= 5, "50 тиков с одним roll-значением = вырожденный seed"


def test_t4_social_checks_no_fake_d20():
    sub = RulesSubscriber()
    ev = _event(etype="player_interacts", target="maid_lusya")
    snap = _snapshot(target="maid_lusya")
    snap["raw_input"] = "сказать комплимент"
    delta = sub.handle(ev, snap)
    assert delta is not None and delta.success is True
    assert delta.checks == [], f"социальная ветка не должна фабриковать d20-метадату: {delta.checks}"

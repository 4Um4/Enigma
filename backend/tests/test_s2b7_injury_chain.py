# path: backend/tests/test_s2b7_injury_chain.py
# Назначение: S2B.7 §4.4 — production-интеграционный гейт Pain/Injury:
#     живой удар (CombatSubscriber → ImpactEngine, Фаза 8) → InjuryDTO →
#     материализация StateApplicator → Phase 0.5 снапшот (FLAT) →
#     InjuryProcessor живой (хронические дельты) → дифференциальный тест
#     раненый vs здоровый (S2B.7-7: integration gate, не unit).
# Зависимости: app.domain (events), app.models.phase8, app.services (body,
#     combat, events, npc, tick_utils)
# Основные сущности: TestS2B7InjuryChain

import copy

from app.domain.events import EventDTO
from app.models.phase8 import Phase8Context
from app.services.body.body_engine import BodyEngine
from app.services.combat.combat_subscriber import CombatSubscriber
from app.services.combat.injury_processor import InjuryProcessor
from app.services.events.event_bus import EventBus
from app.services.events.event_types import EventType
from app.services.npc.state_applicator import StateApplicator
from app.services.tick_utils import build_npc_snapshots

# Калибровка тестового входа (прогон #1: force=100, слэш в ногу →
# DEATH_CERTIFIED bl=1.000 — мгновенно смертельная кровопотеря, цепь жива).
# Лестница вниз ищет рану с functional_loss > 0, которая оставляет NPC
# живым: дифференциал §4.4 — capability, НЕ жизнь (S2B.7-3).
_FORCE_LADDER = (60.0, 50.0, 45.0, 40.0, 35.0, 30.0, 25.0, 20.0)
_SEED_TICKS = range(1, 33)


def _npc_raw() -> dict:
    """Production-форма NPC из all_npcs_raw (§13.4: объект реальности,
    не конструктор мечты; shape — по билдерам tick_utils/combat)."""
    return {
        "id": "guard_1",
        "npc_id": "guard_1",
        "name": "Страж",
        "psyche": {"stress": 10.0, "loyalty_true": 50.0},
        "social_stats": {"trust": 50.0, "fear_of_player": 10.0},
        "body_profile": {"max_hp": 100.0, "abilities": {"strength": 12.0}},
        "body_state": {
            "current_hp": 100.0,
            "max_hp": 100.0,
            "pain": 0.0,
            "fatigue": 0.0,
            "blood_loss": 0.0,
            "consciousness": 1.0,
            "shock_impulse": 0.0,
            "life_status": "ALIVE",
            "injuries": [],
            "modifiers": {},
            "statuses": [],
            "energy": 100.0,
            "hydration": 100.0,
            "nutrition": 100.0,
        },
        "routine": {"current": "idle"},
    }


class _MockState:
    """Носитель body_state для применения PHYSIOLOGY-дельт production-методом
    диспатча (прецедент: S2B.4-тест в test_action_commitment.py)."""

    def __init__(self, body_state: dict) -> None:
        self.npc_id = "guard_1"
        self.body_state = body_state


def _hit(zone: str, force: float, tick: float, ordinal: int = 0) -> EventDTO:
    """PLAYER_ATTACKS с явной зоной/силой. timestamp → детерминированный
    сид боевого KernelRNG (IRON RIVER D-1); ordinal разводит event_id."""
    return EventDTO.create(
        event_type=EventType.PLAYER_ATTACKS.value,
        source="player",
        payload={
            "actor_id": "player",
            "target_id": "guard_1",
            "damage_type": "slash",
            "target_zone": zone,
            "force": force,
        },
        timestamp=tick,
        ordinal=ordinal,
    )


def _apply_strike(payload, raw: dict, current_tick: int = 5) -> None:
    """Материализация удара production-методом диспатча."""
    _applicator = object.__new__(StateApplicator)
    _applicator._apply_physiology_deltas(
        _MockState(raw["body_state"]),  # type: ignore[arg-type]  # S2B.4-прецедент: duck-type носитель body_state (см. test_action_commitment)
        payload.hp_delta,
        payload.pain_delta,
        payload.fatigue_delta,
        payload.blood_loss_delta,
        list(payload.add_injuries),
        list(payload.add_statuses),
        list(payload.remove_statuses),
        payload.shock_impulse,
        current_tick=current_tick,
    )


def _find_survivable_leg_wound(sub: CombatSubscriber, ctx: Phase8Context):
    """Детерминированный перебор (сила × сид тика) до раны ноги:
    (а) functional_loss > 0 (impact_engine: structural > 15);
    (б) NPC выжил после материализации. attack_roll живёт в combat_math —
    промах/касание честно возможны; смертельность силы тоже честна."""
    for _force in _FORCE_LADDER:
        for _t in _SEED_TICKS:
            _res = sub.handle([_hit("leg_l", _force, float(_t))], ctx)
            for _d in _res.deltas:
                if not any(
                    i.functional_loss > 0.0 for i in _d.payload.add_injuries
                ):
                    continue
                _raw = _npc_raw()
                _apply_strike(_d.payload, _raw)
                if _raw["body_state"]["life_status"] == "ALIVE":
                    return _raw, _d.payload
    raise AssertionError(
        "за всю лестницу сил/сидов не найдено выживаемой раны ноги — "
        "цепь удара или пороги жизни недоступны"
    )


class TestS2B7InjuryChain:
    """§4.4: удар в живом контуре → рана материализована → снапшот доставил
    → InjuryProcessor жив → дифференциал раненый vs здоровый."""

    def test_production_strike_chain_and_differential(self):
        # ── 1. Живая Фаза 8: EventDTO → CombatSubscriber → ImpactEngine ──
        # player отсутствует в all_npcs_raw → _make_player_snapshot строит
        # атакующего по канону (Rule 60); shared_context=None → range-gate off.
        _sub = CombatSubscriber(EventBus())
        _ctx = Phase8Context(
            all_npcs_raw=[_npc_raw()],
            all_npc_contexts=[],
            shared_context=None,
            campaign_id="test_s2b7",
            tick_ctx=None,
        )
        _wounded_raw, _p = _find_survivable_leg_wound(_sub, _ctx)
        _healthy_raw = _npc_raw()

        # ── 2. Рана: свойства, не флаги (ADR-123); HP ≠ pain ≠ injury ──
        _inj = _p.add_injuries[0]
        assert _inj.target_zone == "leg_l"
        assert _inj.structural_damage > 0.0
        assert _inj.functional_loss > 0.0
        assert _p.hp_delta < 0.0

        # ── 3. StateApplicator материализовал рану в body_state ──
        _injuries = _wounded_raw["body_state"]["injuries"]
        assert len(_injuries) == 1, "InjuryDTO не материализована в body_state"
        assert _injuries[0]["target_zone"] == "leg_l"
        # S2B.7-G: эпизод раны датирован (мост к S2B.8 Recovery)
        assert _injuries[0].get("received_tick") == 5
        assert _wounded_raw["body_state"]["pain"] > 0.0
        assert _wounded_raw["body_state"]["current_hp"] < 100.0
        assert _wounded_raw["body_state"]["blood_loss"] > 0.0
        assert _wounded_raw["body_state"]["life_status"] == "ALIVE"

        # ── 4. Phase 0.5 production-снапшот: рана ДОСТАВЛЕНА (FLAT) ──
        _snap_w = build_npc_snapshots([copy.deepcopy(_wounded_raw)])[0]
        assert set(_snap_w["injuries_by_zone"]) == {"leg_l"}

        # ── 5. InjuryProcessor ЖИВ на production-снапшоте ──
        _chronic = InjuryProcessor().handle([_snap_w], "test_s2b7", 2)
        assert len(_chronic) == 1
        assert _chronic[0].source == "injury_effects"
        assert _chronic[0].payload.pain_delta > 0.0
        assert _chronic[0].payload.blood_loss_delta > 0.0

        # ── 6. ДИФФЕРЕНЦИАЛ §4.4: раненый vs здоровый ──
        _snap_h = build_npc_snapshots([copy.deepcopy(_healthy_raw)])[0]
        assert InjuryProcessor().handle([_snap_h], "test_s2b7", 2) == []

        # S2B.7-5: leg injury → movement capability ↓ — через СТОИМОСТЬ
        # движения (закон №8), не бинарный veto; ноги не ветят is_capable.
        _engine = BodyEngine()
        _w_cost = _engine.handle(
            [dict(_snap_w, velocity=(0.8, 0.0))], "t", 3
        )[0].payload.fatigue_delta
        _h_cost = _engine.handle(
            [dict(_snap_h, velocity=(0.8, 0.0))], "t", 3
        )[0].payload.fatigue_delta
        assert _w_cost > _h_cost, (
            f"раненая нога не удорожила движение: wounded={_w_cost} "
            f"healthy={_h_cost}"
        )
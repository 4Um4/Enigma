"""
path: /project/backend/tests/gameplay/test_gc09_body_causality.py
Назначение: GC-09A (§5a.9-реестр, вердикт Мастера 2026-09-05): Body Runtime /
    Homeostasis — GREEN-доказательство живого телесного контура в production
    тике: idle-тик → BodyEngine (idle-handler Фаза 0.5, game_loop:315) →
    PhysiologyPayload → StateApplicator → body_state-мутация. One-way-законы
    S2B.3/S2B.4 (hydration/nutrition только теряются) делают оси
    clamp-иммунными при здоровом старте (energy=MAX/fatigue=0 стоят на
    границах — их recovery-нога доказывается в GC-09B после fast-forward
    исчерпания через общую capability).
Зависимости: tests.gameplay.harness
Основные сущности: test_gc09a_body_writes_in_production_ticks
Запуск: cd backend; python -m pytest tests/gameplay/test_gc09_body_causality.py -v -s
"""

import pytest
from tests.gameplay.harness import TavernGameplayHarness

_TARGET = "blacksmith_orm"
_SECOND = "maid_lusya"


@pytest.fixture
def harness():
    _h = TavernGameplayHarness(seed=42)
    _h.new_game()
    yield _h
    _h.dispose()


def _axes(h, npc_id: str) -> dict:
    _b = h.read_body(npc_id)
    assert _b is not None, (
        f"GC09: телесные оси {npc_id} недостижимы (inspect_npc без "
        f"body-полей). Ключи снапшота: "
        f"{sorted((h.inspect_npc(npc_id) or {}).keys())[:25]}"
    )
    _out = {k: float(_b[k]) for k in _b if isinstance(_b.get(k), (int, float))}
    assert "hydration" in _out, (
        f"GC09: ось hydration отсутствует в body_state {npc_id}: "
        f"{sorted(_b.keys())}"
    )
    return _out


def test_gc09a_body_writes_in_production_ticks(harness):
    """GC-09A: 25 production-тиков → one-way-оси ОБЯЗАНЫ сместиться
    (BodyEngine жив в живом тике, не unit-only). GREEN = тело пишет;
    RED = RE-класс (механизм существует, игровая реальность не меняется)
    — тот же шов, что GC-11, на домене тела."""

    harness.advance_ticks(5)  # прогрев

    _before = {n: _axes(harness, n) for n in (_TARGET, _SECOND)}

    harness.advance_ticks(25)

    _after = {n: _axes(harness, n) for n in (_TARGET, _SECOND)}

    print(f"[GC09-A] before: {_before}")
    print(f"[GC09-A] after:  {_after}")

    for _n in (_TARGET, _SECOND):
        _hyd0, _hyd1 = _before[_n]["hydration"], _after[_n]["hydration"]
        _nut0 = _before[_n].get("nutrition")
        _nut1 = _after[_n].get("nutrition")
        print(f"[GC09-A] {_n}: hydration {_hyd0}→{_hyd1}; nutrition {_nut0}→{_nut1}")

        # S2B.3 one-way: hydration только теряется (≥0.2×(1+load)/тик)
        assert _hyd1 < _hyd0, (
            f"GC09-A FAIL ({_n}): hydration не упала за 25 живых тиков "
            f"({_hyd0}→{_hyd1}) — BodyEngine не применяется в production-тике "
            f"(suspect: idle-handler wiring game_loop:315 либо dict-write-back "
            f"дельт PHYSIOLOGY в runtime-носитель) — RE-класс: state exists, "
            f"consequence absent"
        )
        # S2B.4 one-way: nutrition только теряется (медленнее воды)
        if _nut0 is not None and _nut1 is not None:
            assert _nut1 < _nut0, (
                f"GC09-A FAIL ({_n}): nutrition не упала за 25 тиков "
                f"({_nut0}→{_nut1}) — тот же suspect-контур"
            )

def test_gc09b_body_exhaustion_blocks_intents(harness):
    """GC-09B: Embodied Constraint (RED-детектор, вердикт Мастера
    2026-09-05). Предельный износ (fatigue +90 / energy −90) — единственная
    переменная между двумя копиями живого NPCState. Доказываемый тезис:
    тело ДО порога смерти/бессознательности (Vital State Guard :440 —
    единственный существующий body-edge в compute) должно влиять на
    доступность интентов. RED сегодня = официальное доказательство
    STATE→BEHAVIOR GAP: между живым телом и DecisionHub нет порогового
    causal edge (Звено 3 = ADR-фронт BodyConstraintResolver)."""
    import copy as _copy

    from app.domain.identity_events import EffectiveDrives
    from app.services.economy.opportunity_engine import OpportunityResult
    from app.services.npc.decision_hub import DecisionHub, EventContext
    from app.services.npc.npc_loader import load_l2_state_from_runtime_dict
    from app.services.npc.state_applicator import StateApplicator

    harness.advance_ticks(3)
    _raw = harness.inspect_npc("maid_lusya")
    assert _raw is not None, "GC09-B: живой дикт недостижим"

    from app.services.npc.npc_loader import load_profile_from_legacy_json

    _state_A = load_l2_state_from_runtime_dict(_copy.deepcopy(_raw))
    # Personality живёт ОТДЕЛЬНО от NPCState (pipeline:216 — NPCProfileL0 из
    # того же дикта отдельной фабрикой; state.personality не существует).
    _personality = load_profile_from_legacy_json(_copy.deepcopy(_raw))

    _drives = EffectiveDrives.from_dict(
        {"control": 0.25, "significance": 0.25, "fear": 0.25, "desire": 0.25}
    )
    _event = EventContext(
        event_type="social",
        actor_id="player",
        success=True,
        intensity=1.0,
        distance=3.0,
        witness_count=2,
    )
    _opp = OpportunityResult(
        score=0.5, hidden_action_allowed=False, unlocked_intents=frozenset()
    )
    _hub = DecisionHub(seed=0)

    _state_B = load_l2_state_from_runtime_dict(_copy.deepcopy(_raw))
    _applicator = object.__new__(StateApplicator)
    _applicator._apply_physiology_deltas(
        _state_B, 0.0, 0.0, +90.0, 0.0, [], [], [], 0.0,
        energy_delta=-90.0,
    )
    # Гвард дифференциала: мутация обязана состояться (иначе тест измеряет воздух)
    _b_body = _state_B.body_state or {}
    assert _b_body.get("fatigue", 0.0) > 50.0, (
        f"GC09-B guard: physiology-мутация не применилась "
        f"(fatigue={_b_body.get('fatigue')}) — suspect: StateApplicator "
        f"против from_legacy-формы"
    )

    def _avail(st):
        return set(
            _hub._get_possible_intents(
                st, _personality, _event, _opp, effective_drives=_drives
            )
        )

    _a = _avail(_state_A)
    _b = _avail(_state_B)
    print(f"[GC09-B] A(rested) intents={sorted(_a)}")
    print(f"[GC09-B] B(exhausted) intents={sorted(_b)}")
    print(f"[GC09-B] B body: fatigue={_b_body.get('fatigue')} energy={_b_body.get('energy')}")

    # RED-детектор: сегодня ожидаем РОВНО это падение
    assert _b < _a, (
        f"GC09-B RED: exhausted-тело не закрывает ни один интент "
        f"(A={sorted(_a)}, B={sorted(_b)}; B.fatigue={_b_body.get('fatigue')}). "
        f"STATE→BEHAVIOR GAP, домен тела: causal edge BODY → DECISION "
        f"AVAILABILITY для осей выносливости отсутствует. Существующий "
        f"body-edge — только Vital State Guard (смерть/бессознательность, "
        f"compute:440). Формулировка Мастера (2026-09-05): «Body Simulation ≠ "
        f"Embodied Agency; state exists ≠ state has consequence». Звено 3 = "
        f"ADR-фронт BodyConstraintResolver (BodyState → ActionConstraints → "
        f"DecisionHub), НЕ патч _is_intent_available."
    )
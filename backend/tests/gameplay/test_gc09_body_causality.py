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
    """GC-09B-full R1-санация (S254/Мастер 2026-09-11): оригинальный GREEN
    был CAUSAL FALSE GREEN — единственная наблюдаемая разница A->B была
    RNG-артефактом (noise ±SCORE_NOISE_RANGE на каждый intent,
    decision_hub.py:1037/:1052; один хаб на два compute -> позиция-2 потока;
    S254 decisive-зонд: A/A-дрейф == A/B-дрейфу; fresh A == fresh B
    байт-идентично при fatigue 0.22 vs 90.2).
    Контракт R1 (Мастер): fresh hub + A/A control + noise-off +
    сохранение causal claim в усиленной форме — chronic cap 0.3 обязан
    множить scores capped-интентов (FLEE/ATTACK/APPROACH; MANIPULATE может
    отсутствовать в словаре хаба). При живом контуре — GREEN; при разрыве —
    RED-диагноз S254 L4-F8/F9 (НЕ ретушь: fix = R2 mini-ADR).
    Immutable evidence: reports/history/gc09b_vacuous_green_immutable.txt
    (git заморожен); оригинальный RED a6708f46 и vacuous GREEN a0cc0d42 —
    в git-истории."""
    import copy as _copy

    import app.services.npc.decision_hub as _dh
    from app.domain.identity_events import EffectiveDrives
    from app.services.cfrm.pressure_translator import translate_kernel_to_context
    from app.services.npc.decision_hub import DecisionHub, EventContext
    from app.services.npc.npc_loader import (
        load_l2_state_from_runtime_dict,
        load_profile_from_legacy_json,
    )

    harness.advance_ticks(3)
    _raw = harness.inspect_npc("maid_lusya")
    assert _raw is not None, "GC09-B: живой дикт недостижим"

    _state_A = load_l2_state_from_runtime_dict(_copy.deepcopy(_raw))
    _personality = load_profile_from_legacy_json(_copy.deepcopy(_raw))
    _drives = EffectiveDrives.from_dict(
        {"control": 0.25, "significance": 0.25, "fear": 0.25, "desire": 0.25}
    )
    _event = EventContext(
        event_type="social", actor_id="player", success=True,
        intensity=1.0, distance=3.0, witness_count=2,
    )

    _state_B = load_l2_state_from_runtime_dict(_copy.deepcopy(_raw))
    from app.services.npc.state_applicator import StateApplicator

    _applicator = object.__new__(StateApplicator)
    _applicator._apply_physiology_deltas(
        _state_B, 0.0, 0.0, +90.0, 0.0, [], [], [], 0.0, energy_delta=-90.0,
    )
    _b_body = _state_B.body_state or {}
    assert _b_body.get("fatigue", 0.0) > 50.0, "GC09-B guard: мутация не применилась"

    from app.models.npc_state import PerceptualKernel

    _orig_noise = _dh.SCORE_NOISE_RANGE
    _dh.SCORE_NOISE_RANGE = 0.0  # R1: noise-off — детерминированный режим

    def _decide(st):
        _ctx = translate_kernel_to_context(
            kernel=PerceptualKernel(), body_state=dict(st.body_state or {}),
            social_input_ema=0.0, gregariousness=0.5, has_active_commitment=False,
        )
        return DecisionHub(seed=0).compute(  # R1: FRESH hub на каждый decide
            state=st, personality=_personality, effective_drives=_drives,
            event=_event, decision_ctx=_ctx,
        )

    try:
        # R1 A/A-контроль: прибор обязан быть детерминирован (noise-off, fresh)
        _aa1 = _decide(_state_A)
        _aa2 = _decide(_state_A)
        assert _aa1.scores_trace == _aa2.scores_trace, (
            "GC09-B R1 A/A FAIL: noise-off + fresh-hub всё равно дрейфует — "
            "недетерминированный измерительный прибор; подозреваемый: ещё один "
            "RNG-терм в compute (искать rng-вызовы вне decision_hub.py:1037)"
        )

        _a = _decide(_state_A)
        _b = _decide(_state_B)
        print(
            f"[GC09-B-R1] A(rested)={_a.intent}; B(exhausted)={_b.intent}; "
            f"B.fatigue={_b_body.get('fatigue')}; "
            f"A.flee={_a.scores_trace.get('flee')}; "
            f"B.flee={_b.scores_trace.get('flee')}"
        )

        # R1 causal-claim (усиленная форма исходного): chronic cap 0.3
        # множит scores capped-интентов: B[k] ≈ round(A[k] * 0.3, 4)
        for _k in ("flee", "attack", "approach"):
            _va = _a.scores_trace.get(_k)
            _vb = _b.scores_trace.get(_k)
            assert _va is not None and _vb is not None, (
                f"GC09-B R1: capped-ось '{_k}' отсутствует в scores_trace — "
                "кандидат-набор теста не совпадает со словарём хаба"
            )
            assert abs(_vb - round(_va * 0.3, 4)) <= 0.0002, (
                f"GC09-B R1 RED: chronic cap не применяется к '{_k}' "
                f"(A={_va}, B={_vb}; ожидание ~A*0.3={round(_va * 0.3, 4)}). "
                "Диагноз S254 L4-F8/F9: translator пишет constraints "
                "{'FLEE':0.3,...}, DecisionHub их не потребляет — ФАЗА 1 "
                "(decision_hub.py:565) мертва по кейсу ('FLEE' vs 'flee'), "
                "потребитель 0<feasibility<1 отсутствует (ФАЗА 2 применяет "
                "только deformation). Fix = R2 (mini-ADR: нормализация ключей "
                "+ scores×feasibility), НЕ ретушь теста. Evidence: S254 "
                "decisive-зонд — fresh A == fresh B байт-идентично."
            )
    finally:
        _dh.SCORE_NOISE_RANGE = _orig_noise
    """GC-09B-full (ADR-O-383 oracle, observation-scope correction — вердикт
    Мастера Q-D): наблюдение ПОЛНОГО production-контура решения (decision_ctx
    из translate_kernel_to_context — официальный путь veto в живом тике).
    "Original GC-09B RED remains immutable evidence of the early
    availability-path blind spot. The post-implementation oracle is
    upgraded to observe the complete production decision contour because V1
    intentionally operates in the feasibility layer. The oracle upgrade is
    therefore an observation-scope correction, not a relaxation of the
    acceptance criterion."
    (Оригинальный RED-текст сохранён в истории коммитов a6708f46/
    gc09b_red4.txt как immutable evidence.)"""
    import copy as _copy

    from app.domain.identity_events import EffectiveDrives
    from app.services.cfrm.pressure_translator import translate_kernel_to_context
    from app.services.npc.decision_hub import DecisionHub, EventContext
    from app.services.npc.npc_loader import (
        load_l2_state_from_runtime_dict,
        load_profile_from_legacy_json,
    )

    harness.advance_ticks(3)
    _raw = harness.inspect_npc("maid_lusya")
    assert _raw is not None, "GC09-B: живой дикт недостижим"

    _state_A = load_l2_state_from_runtime_dict(_copy.deepcopy(_raw))
    _personality = load_profile_from_legacy_json(_copy.deepcopy(_raw))
    _drives = EffectiveDrives.from_dict(
        {"control": 0.25, "significance": 0.25, "fear": 0.25, "desire": 0.25}
    )
    _event = EventContext(
        event_type="social", actor_id="player", success=True,
        intensity=1.0, distance=3.0, witness_count=2,
    )
    _hub = DecisionHub(seed=0)

    _state_B = load_l2_state_from_runtime_dict(_copy.deepcopy(_raw))
    from app.services.npc.state_applicator import StateApplicator

    _applicator = object.__new__(StateApplicator)
    _applicator._apply_physiology_deltas(
        _state_B, 0.0, 0.0, +90.0, 0.0, [], [], [], 0.0, energy_delta=-90.0,
    )
    _b_body = _state_B.body_state or {}
    assert _b_body.get("fatigue", 0.0) > 50.0, "GC09-B guard: мутация не применилась"

    from app.models.npc_state import PerceptualKernel

    def _decide(st):
        _ctx = translate_kernel_to_context(
            kernel=PerceptualKernel(),
            body_state=dict(st.body_state or {}),
            social_input_ema=0.0,
            gregariousness=0.5,
            has_active_commitment=False,
        )
        return _hub.compute(
            state=st, personality=_personality, effective_drives=_drives,
            event=_event, decision_ctx=_ctx,
        ).intent

    _a = _decide(_state_A)
    _b = _decide(_state_B)
    print(f"[GC09-B-full] A(rested)={_a}; B(exhausted)={_b}; "
          f"B.fatigue={_b_body.get('fatigue')}")

    assert _b != _a, (
        f"GC-09B-full FAIL: chronic-veto не меняет итоговый выбор "
        f"(A={_a}, B={_b}, B.fatigue={_b_body.get('fatigue')}) — ADR-O-383 "
        f"не работает либо decision_ctx не доходит до feasibility-фильтра"
    )

    # Original GC-09B RED (immutable evidence, a6708f46 / gc09b_red4.txt):
    # ранний availability-тракт (`_get_possible_intents` без decision_ctx)
    # показал A≡B при fatigue=90.2 — blind spot раннего тракта. Удалён
    # при ADR-O-383 oracle-upgrade (observation-scope correction, Q-D);
    # RED-текст сохранён в git-истории дословно.
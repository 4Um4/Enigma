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
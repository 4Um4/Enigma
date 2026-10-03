# path: /project/backend/tests/gameplay/test_gc09_reproof_energy.py
# Назначение: ADR-O-383 energy re-proof: availability-тракт = тот же chronic cap 0.3
# (OR-гейт: fatigue>0.8 OR energy<0.1). Особенности против fatigue:
# (1) razor-margin — probe_hint −90 проходит порог 0.1 с запасом 0.001 при
#     baseline 99.9; сценарий ассертит чекпойнт energy < 10.0 (гейт сработал);
# (2) без track2-ассерта — sleep_pressure не прямо связан с energy-осью
#     (ADR-O-375: спит через fatigue-модулятор), потому фиксируется как annotation
#     при наличии, не ассерт.
# Выход: exit 0 = GREEN; исключение = RED.
# Зависимости: tests.gameplay.perturbation_harness.run_probe
# Основные сущности: run.

from tests.gameplay.perturbation_harness import ProbeSpec, run_probe

_NPC = "maid_lusya"
_CAPPED_AXES = ("flee", "attack", "approach", "manipulate")
_TOL_ABS = 0.30
_RAZOR_MARGIN_NOTE = (
    "energy −90 при baseline 99.9 → 0.099 < 0.1 — запас 0.001; "
    "baseline=100.0 сломал бы гейт (10.0 < 0.1 = False). Рекомендация владельцу "
    "ADR-O-383: probe_hint −95 или нестрогий <=. Решение владельца, не сценария."
)


def run() -> None:
    _res = run_probe(ProbeSpec(
        field="body_state.energy", npc_id=_NPC, injection=-90.0,
        write_kind="PHYSIOLOGY", horizon=6,
    ))
    print(f"RE-PROOF energy → verdict={_res.verdict}")
    print(f"  checkpoints={_res.checkpoints}")
    print(f"  score_diffs: {len(_res.score_diffs)} осей")
    # Гейт availability обязан сработать: чекпойнт post_injection < 10.0
    _post = _res.checkpoints.get("post_injection")
    assert _post is not None and _post < 10.0, (
        f"ENERGY RE-PROOF RED: availability-гейт не сработал (post={_post}, "
        f"порог 10.0 по ADR-O-383 _ENERGY_LOW_CANDIDATE=0.1; {_RAZOR_MARGIN_NOTE})"
    )
    _capped = [d for d in _res.score_diffs if d[2] in _CAPPED_AXES]
    assert _capped, (
        f"ENERGY RE-PROOF RED: capped-оси не деформированы при сработавшем гейте — "
        f"паттерн OR-ветки не проводит (diffs: {[(d[2]) for d in _res.score_diffs[:10]]})"
    )
    for _t, _npc, _axis, _base, _pert in _capped:
        _expected = _base * 0.3 if _base is not None else None
        assert _pert is not None and _expected is not None, (
            f"ENERGY RE-PROOF: ось {_axis} без чисел"
        )
        assert abs(_pert - _expected) <= _TOL_ABS, (
            f"ENERGY RE-PROOF RED: cap-паттерн нарушен на {_axis}: "
            f"pert={_pert}, expected~{_expected}(±{_TOL_ABS})"
        )
    print(f"  argmax_flip={_res.argmax_flip} (annotation)")
    print(f"  razor-margin: {_RAZOR_MARGIN_NOTE}")
    print("ИТОГ ENERGY RE-PROOF: GREEN (availability-тракт; CAUSAL проводимость доказана)")


if __name__ == "__main__":
    run()
# path: backend/tests/sandbox/SUPERBOX/scenarios/behavior_mask_future_semantics_test.py
# Назначение: ЗАВЕДОМО КРАСНЫЙ целевой щит BehaviorMask (SPEC E-BM1 §3): кодирует
#   контракты БУДУЩЕЙ семантики (вердикт Мета Тай), а не текущее состояние.
#   TARGET-красный = регистрация отсутствия возможности, НЕ сигнал подгонки.
#   Механизм-агностичен: зелёным T1/T2 сделает любая корректная реализация этапа B.
# Зависимости: behavior_mask_closure_test (реюз констант/тапов/ног, read-only),
#   app.services.phases.decision.evaluate_behavior_and_identity. Production не трогается.
# Основные сущности: T1 (монотонность ранга), T2 (отзывчивость приверженности),
#   T3/T4/T5 (направляющие NOT_IMPLEMENTED_FUTURE), R1-R3 (регресс-щит этапа A).
# Гейт: python -m py_compile перед каждым прогоном (Python 3.11, PEP 701).
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parents[3]  # scenarios -> SUPERBOX -> sandbox -> tests -> backend
for _p in (str(_HERE), str(_BACKEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Реюз канонического щита: константы, тапы, leg-раннер (G0-префлайт гарантирует
# __main__-гвард у модуля-донора — импорт не запускает его сценарий).
from behavior_mask_closure_test import (  # noqa: E402
    _CAMPAIGN,
    _NPC,
    _PRESETS,
    _PersistenceTap,
    _RelStoreStub,
    _run_leg,
)

from app.services.phases.decision import (  # noqa: E402
    evaluate_behavior_and_identity,
)

_PASS = "PASS"
_FAIL_TARGET = "FAIL_TARGET"        # красный by design: будущая семантика отсутствует
_FUTURE = "NOT_IMPLEMENTED_FUTURE"  # направляющий: канал не построен
_FAIL = "FAIL"                      # регресс-щит: авария
_INVALID = "INVALID"                # предусловие гарнеса нарушено — не целевой красный

# Фасад-классы FAKE_SUBMISSION (инвариант T1 не зависит от выбора механики)
_INCONSISTENT = ("attack", "intimidate", "warn")
_CONSISTENT = ("observe", "talk", "idle")

_REPORT = Path("reports") / "bm_future_semantics.json"


def _mk(cid: str, status: str, detail: str) -> Dict[str, str]:
    return {"id": cid, "status": status, "detail": detail}


def _phase_call_inplace(work: Dict[str, Any], trust: float, fear: float) -> List[Dict[str, Any]]:
    """Один вызов фазы на ЖИВОМ dict (без deepcopy): проекция сохраняется в work —
    это носитель эволюции состояния между вызовами (нужно T2). Прецедент —
    _phase_call канонического щита; отличие сознательное и единственное."""
    tap = _PersistenceTap()
    tap.attach()
    try:
        evaluate_behavior_and_identity(
            npc_states=[work],
            campaign_id=_CAMPAIGN,
            tick_number=1,
            game_day=3,
            memory_manager=None,
            l1_chronicle=None,
            economic_profiles_map=None,
            social_modifiers_map=None,
            relationship_store=_RelStoreStub(trust=trust, fear=fear),
        )
    finally:
        tap.detach()
    return [c for c in tap.finalize() if c.get("npc_id") == _NPC]


def _tick_gap(scores: Dict[str, Any]) -> Optional[float]:
    """D-гэп тика: несовместимые минус согласованные (Y1 из SPEC §2.3)."""
    inc = [scores[k] for k in _INCONSISTENT if k in scores]
    con = [scores[k] for k in _CONSISTENT if k in scores]
    if not inc or not con:
        return None
    return (sum(inc) / len(inc)) - (sum(con) / len(con))


def _check_t1(rec_ctrl: Dict[str, Any], rec_treat: Dict[str, Any]) -> Dict[str, str]:
    """T1 Монотонность ранга: маска не улучшает относительную позицию
    несовместимых действий. Ожидание сегодня: RED (знак-слепое умножение
    поднимает отрицательные скоры подавляемых к нулю)."""
    ctrl = rec_ctrl.get("scores_per_tick") or []
    treat = rec_treat.get("scores_per_tick") or []
    masks = rec_treat.get("mask_per_tick") or []
    gaps_c: List[float] = []
    gaps_t: List[float] = []
    for idx in range(min(len(ctrl), len(treat), len(masks))):
        if masks[idx] != "fake_submission":
            continue
        gc, gt = _tick_gap(ctrl[idx]), _tick_gap(treat[idx])
        if gc is None or gt is None:
            continue
        gaps_c.append(gc)
        gaps_t.append(gt)
    if not gaps_c:
        return _mk("T1", _INVALID, "нет пар тиков: маска+скор в обеих ногах")
    dc = sum(gaps_c) / len(gaps_c)
    dt = sum(gaps_t) / len(gaps_t)
    delta = dt - dc
    if delta <= 0.0:
        return _mk("T1", _PASS, f"инвариант держится: ΔD={delta:+.4f}")
    return _mk(
        "T1", _FAIL_TARGET,
        f"маска УЛУЧИЛА позицию несовместимых: ΔD={delta:+.4f} "
        f"(D_ctrl={dc:+.4f} -> D_treat={dt:+.4f}). Зелёнеет при ЛЮБОЙ корректной "
        f"механике подавления (SPEC E-BM1 §2.6); текущая — знак-слепое умножение base.",
    )


def _check_t2(fin_f0: Dict[str, Any]) -> Dict[str, str]:
    """T2 Отзывчивость приверженности: intensity пересчитывается из актуального
    состояния. Протокол: активация при fear=0.61, затем рост fear до 0.90 при
    устоявшейся маске. Цель: приверженность растёт к капу. Сегодня: гейт на тип
    (decision.py:228) отбрасывает пересчёт — заморозка."""
    work = copy.deepcopy(fin_f0)
    c1 = _phase_call_inplace(work, trust=-60.0, fear=0.61)
    i1 = next(
        (c.get("intensity_after") for c in c1 if c.get("mask_after") == "fake_submission"),
        None,
    )
    c2 = _phase_call_inplace(work, trust=-60.0, fear=0.90)
    i2 = next(
        (c.get("intensity_after") for c in c2 if c.get("mask_after") == "fake_submission"),
        None,
    )
    if i1 is None or i2 is None:
        return _mk("T2", _INVALID, f"предусловие: активация не произошла (i1={i1}, i2={i2})")
    if i2 > i1 + 1e-9:
        return _mk("T2", _PASS, f"приверженность отвечает состоянию: {i1} -> {i2}")
    return _mk(
        "T2", _FAIL_TARGET,
        f"приверженность заморожена: fear 0.61->0.90, intensity {i1} -> {i2}. "
        f"Цель (SPEC §2.1, поправка №3): пересчёт из актуального состояния; "
        f"сегодня гейт обновления смотрит только на тип маски.",
    )


def _future_stubs() -> List[Dict[str, str]]:
    """Направляющие контракты: каналы не построены; выводятся в отчёт, чтобы
    будущее решение имело готовую точку приёмки."""
    return [
        _mk("T3", _FUTURE,
            "Контекстность: изменение наблюдаемости/угрозы меняет выбор, не только "
            "скор (flee-триада: наблюдаемость / цена разоблачения / цена отказа). "
            "Зелёнеет при: стратегия предъявления читает observability."),
        _mk("T4", _FUTURE,
            "Контрфактическая причинность (проверка H-PL): отмена скрытой цели или "
            "закрытие окна прекращает подготовку. Зелёнеет при: связке "
            "цель->окно->действие (C'-композиция)."),
        _mk("T5", _FUTURE,
            "Рефлекторный этаж COLLAPSE: прямая угроза при сломанной воле оставляет "
            "спасение возможным. Зелёнеет при: контракте рефлексов ниже воли "
            "(COLLAPSE = состояние, не стратегия)."),
    ]


def _check_shield(
    rec_f0: Dict[str, Any],
    rec_f70: Dict[str, Any],
    fin_f0: Dict[str, Any],
) -> List[Dict[str, str]]:
    """Регресс-щит: этап A жив + граница состояние/стратегия не стёрта."""
    out: List[Dict[str, str]] = []
    fw = rec_f0.get("fake_writes")
    out.append(_mk("R1", _PASS if fw == 0 else _FAIL,
                   f"F0 контроль чист: fake_writes={fw} (ожидание 0)"))
    po = rec_f70.get("phase_origin_mask_writes")
    out.append(_mk("R2", _PASS if po == 0 else _FAIL,
                   f"ORDER-фикс этапа A жив: phase_origin={po} (ожидание 0)"))
    work = copy.deepcopy(fin_f0)
    caps = _phase_call_inplace(work, trust=50.0, fear=70.0)
    m = next((c.get("mask_after") for c in caps), None)
    out.append(_mk("R3", _PASS if m in (None, "none") else _FAIL,
                   f"разделение: страх+положительное доверие -> mask={m} (ожидание none; "
                   f"подлинная симпатия — не стратегия притворства)"))
    return out


def main() -> int:
    legs_rec: Dict[str, Dict[str, Any]] = {}
    legs_fin: Dict[str, Dict[str, Any]] = {}
    for rid in ("LEG-F0", "LEG-F0.7", "LEG-F70"):
        a, b = _run_leg(rid, _PRESETS[rid], True)
        # Порядок возврата _run_leg распознаётся по полю run_id (G0-префлайт)
        rec, fin = (a, b) if isinstance(a, dict) and "run_id" in a else (b, a)
        legs_rec[rid] = rec
        legs_fin[rid] = fin
        print(f"[BM-FUTURE] нога {rid}: mask_ticks={rec.get('mask_ticks_present')}")

    results: List[Dict[str, str]] = []

    # Контур TARGET (красный by design; exit-код не портит)
    for treat_id in ("LEG-F0.7", "LEG-F70"):
        results.append(_check_t1(legs_rec["LEG-F0"], legs_rec[treat_id]))
    results.append(_check_t2(legs_fin["LEG-F0"]))
    results.extend(_future_stubs())

    # Контур REGRESSION (зелёные гейты)
    results.extend(_check_shield(
        legs_rec["LEG-F0"], legs_rec["LEG-F70"], legs_fin["LEG-F0"]))

    for r in results:
        _marks = {
            _PASS: "[PASS]",
            _FAIL_TARGET: "[TARGET-RED]",
            _FUTURE: "[FUTURE]",
            _FAIL: "[SHIELD-FAIL]",
            _INVALID: "[INVALID]",
        }
        mark = _marks.get(r["status"], "[?]")
        print(f"{mark} {r['id']}: {r['detail']}")

    n_red = sum(1 for r in results if r["status"] == _FAIL_TARGET)
    n_future = sum(1 for r in results if r["status"] == _FUTURE)
    n_pass = sum(1 for r in results if r["status"] == _PASS)
    n_fail = sum(1 for r in results if r["status"] == _FAIL)
    n_invalid = sum(1 for r in results if r["status"] == _INVALID)

    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _REPORT.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                       encoding="utf-8")

    print(f"Итог: TARGET_RED={n_red} FUTURE={n_future} PASS={n_pass} "
          f"FAIL={n_fail} INVALID={n_invalid} report={_REPORT}")
    # exit != 0 только при провале регресс-щита или невалидности гарнеса:
    # целевой красный — регистрация уровня, не авария конвейера.
    return 1 if (n_fail or n_invalid) else 0


if __name__ == "__main__":
    raise SystemExit(main())
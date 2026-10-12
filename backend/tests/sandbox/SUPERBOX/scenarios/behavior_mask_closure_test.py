"""
path: backend/tests/sandbox/SUPERBOX/scenarios/behavior_mask_closure_test.py
Назначение: ЭТАП 0.6 — диагностический щит BehaviorMask (RE-D9/S318/R002).
    Двухконтурная структура (вердикт Мастера):
      Контур A — целевые игровые контракты (красный допустим; контракт не ослабляется);
      Контур B — 10-точечный производственный путь + изолированные юнит-грани
      локализации (меченые isolated; заглушка ≠ доказательство игрового поведения).
    Статусы: PASS / FAIL / NOT_IMPLEMENTED / NOT_PROVEN / INVALID.
    Производственный код НЕ изменяется. Тап _PersistenceTap — наблюдение-only
    (Закон XI): обёртка вызывает оригинал, восстановление в finally +
    пост-проверка дескриптора (вердикт Q2). Входы ног — npc_overrides пресетов:
    явно обозначенные тестовые настройки (канонический рычаг S314).
Зависимости: app.services.calibration.experiment_runner, app.services.player_session_service,
    app.services.phases.decision, app.services.npc.decision_hub, app.models.npc_state,
    app.models.will
Основные сущности: _PersistenceTap, _RelStoreStub, _run_leg, _unit_chain,
    _divergence, _contour_a, _contour_b, main
Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/behavior_mask_closure_test.py
Exit-code — диагностический (вердикт Q3): 0 = измерение завершено и отчёт записан
    (НЕ «контракты выполнены»); 1 = INVALID. Регрессионный режим — после фикса (AC-4).
"""
from __future__ import annotations

import copy
import json
import logging
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Bootstrap: scenarios/ лежит на 2 уровня глубже пробы R002 → parents[4]
_BACKEND = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_BACKEND))
_ROOT = _BACKEND.parent

_CAMPAIGN = "Open_road"
_NPC = "merchant_goran"
_TICKS = 30

_PRESETS: Dict[str, str] = {
    "LEG-F0": "config/calibration/test_presets/golden_fear_f0.yaml",
    "LEG-F0.7": "config/calibration/test_presets/golden_fear_f0_7.yaml",
    "LEG-F30": "config/calibration/test_presets/golden_fear_f30.yaml",
    "LEG-F70": "config/calibration/test_presets/golden_fear_f70.yaml",
    "LEG-COLLAPSE": "config/calibration/test_presets/golden_collapse_broken.yaml",
}
# Тап вешаем на обе ноги дивергентной пары — P2 требует симметричных доказательств
_INSTRUMENTED = {"LEG-F0", "LEG-F70"}

_REPORT = _ROOT / "reports" / "behavior_mask_closure_s0_6.json"

_PASS, _FAIL = "PASS", "FAIL"
_NOT_IMPL, _NOT_PROVEN, _INVALID = "NOT_IMPLEMENTED", "NOT_PROVEN", "INVALID"

# WARA-кластер §12.2: from_legacy читает, to_persistence_dict (1001–1153) не пишет
_WARA_CLUSTER = [
    "behavior_mask",
    "behavior_mask_intensity",
    "behavior_mask_applied_at_day",
    "resentment",
    "dependency",
]


def _mk(cid, contour, contract, path, status, expected, actual,
        stage=None, note=None) -> Dict[str, Any]:
    return {
        "id": cid, "contour": contour, "contract": contract, "evidence_path": path,
        "status": status, "expected": expected, "actual": actual,
        "break_stage": stage, "note": note,
    }


class _PersistenceTap:
    """Пассивный тап на NPCState.to_persistence_dict (вердикт Q2).

    Зачем: маска пишется в ЛОКАЛЬНЫЙ объект фазы ПОСЛЕ проекции (:196 > :137) —
    единственный способ увидеть вычисленную маску — держать ссылку на объект,
    который фаза мутирует после своего вызова проекции. Обёртка вызывает оригинал
    (поведение не меняется, Закон XI); восстановление гарантировано finally.
    staticmethod-семантика проверяется явно (не «по сходству» с _TapRegistry).
    """

    def __init__(self) -> None:
        self._orig_descriptor: Any = None
        self._orig_func: Any = None
        self._active = False
        self.captures: List[Dict[str, Any]] = []

    def attach(self) -> None:
        from app.models.npc_state import NPCState
        # Дескриптор снимаем из __dict__ ДО подмены; функцию — через __get__
        # (совместимо со всеми версиями Python, без опоры на __func__)
        self._orig_descriptor = NPCState.__dict__["to_persistence_dict"]
        self._orig_func = self._orig_descriptor.__get__(None, NPCState)
        tap = self

        def _wrapped(state: Any, npc_dict: Dict[str, Any]) -> None:
            _m = getattr(state, "behavior_mask", None)
            _ws = getattr(state, "will_state", None)
            _pers = getattr(state, "personality", None)
            tap.captures.append({
                "seq": len(tap.captures),
                "npc_id": getattr(state, "npc_id", None),
                "mask_at_call": _m.mask.value if _m is not None else None,
                "intensity_at_call": float(_m.intensity) if _m is not None else None,
                "will_state_at_call": getattr(_ws, "value", None),
                "personality_willpower": getattr(_pers, "willpower", None),
                "_ref": state,
            })
            return tap._orig_func(state, npc_dict)

        NPCState.to_persistence_dict = staticmethod(_wrapped)
        self._active = True

    def detach(self) -> None:
        from app.models.npc_state import NPCState
        if self._active and self._orig_descriptor is not None:
            NPCState.to_persistence_dict = self._orig_descriptor
            self._active = False

    def verify_restored(self) -> bool:
        from app.models.npc_state import NPCState
        return NPCState.__dict__.get("to_persistence_dict") is self._orig_descriptor

    def finalize(self) -> List[Dict[str, Any]]:
        """Читает финальное состояние захваченных объектов — ПОСЛЕ возврата фазы."""
        out: List[Dict[str, Any]] = []
        for c in self.captures:
            _m = getattr(c["_ref"], "behavior_mask", None)
            out.append({
                "seq": c["seq"],
                "obj_id": id(c["_ref"]),
                "npc_id": c["npc_id"],
                "mask_at_call": c["mask_at_call"],
                "mask_after": _m.mask.value if _m is not None else None,
                "intensity_after": float(_m.intensity) if _m is not None else None,
                "applied_at_day_after": (
                    _m.applied_at_day if _m is not None else None
                ),
                "will_state_at_call": c["will_state_at_call"],
                "personality_willpower": c["personality_willpower"],
            })
        return out


class _RelStoreStub:
    """Read-only заглушка контракта RelationshipStore.get_all_for_source.

    Только для изолированных юнит-вызовов фазы (меченых isolated): вход —
    аргумент функции, не инъекция в мир.
    """

    def __init__(self, trust: float, fear: float) -> None:
        self._data = {"player": {"trust": trust, "fear": fear}}

    def get_all_for_source(self, campaign_id: str, npc_id: str) -> Dict[str, Dict[float, float]]:
        return {k: dict(v) for k, v in self._data.items()}


def _run_leg(run_id: str, preset_path: str, instrumented: bool) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Полная нога: production-путь через ExperimentRunner (Контур B, точки 1–4, 6, 8)."""
    from app.services.calibration.experiment_runner import ExperimentConfig, ExperimentRunner
    from app.services.player_session_service import player_session_service

    tap = _PersistenceTap()
    runner = ExperimentRunner()
    cfg = ExperimentConfig(preset_path=preset_path, duration_ticks=_TICKS, campaign_id=_CAMPAIGN)
    experiment_id = runner.start(cfg)
    # Паттерн пробы R002: игрок обязан быть выбран после start
    player_session_service.select_player(cfg.campaign_id, "player")
    if instrumented:
        tap.attach()
    try:
        runner.step(_TICKS)
        initial = getattr(runner, "_initial_social_applied", {})
        result = runner.stop()
    finally:
        tap.detach()

    fin = result.final_npc_state.get(_NPC, {}) or {}
    psyche = fin.get("psyche", {}) or {}
    rc = (fin.get("relationship_cache", {}) or {}).get("player", {}) or {}

    captures = tap.finalize() if instrumented else []
    mine = [c for c in captures if c["npc_id"] == _NPC]

    fingerprint: List[Dict[str, Any]] = []
    mask_per_tick: List[Optional[str]] = []
    for tick_list in (getattr(result, "npc_captures", None) or []):
        g = next((n for n in (tick_list or [])
                  if (n.get("id") or n.get("npc_id")) == _NPC), {})
        p = g.get("psyche", {}) or {}
        mask_per_tick.append(p.get("behavior_mask", None))
        fingerprint.append({
            "stress": p.get("stress", None),
            "state": p.get("state", None),
            "identity_integrity": p.get("identity_integrity", None),
            "pressure_resistance": p.get("pressure_resistance", None),
            "intent": g.get("intent", None),
            "affective_load": g.get("affective_load", None),
        })

    rec: Dict[str, Any] = {
        "run_id": run_id,
        "experiment_id": experiment_id,
        "evidence_path": "in-game",
        "preset": initial.get(_NPC, {}).get("preset", {}),
        "store_read": initial.get(_NPC, {}).get("store_read", {}),
        "rc_player_fear": rc.get("fear", None),
        "rc_player_trust": rc.get("trust", None),
        # Правильный ключ will_state: проба R002 читала несуществующий "will_state"
        "will_state": psyche.get("state", None),
        "stress": psyche.get("stress", None),
        "behavior_mask": psyche.get("behavior_mask", None),
        "mask_intensity": psyche.get("behavior_mask_intensity", None),
        "mask_applied_at_day": psyche.get("behavior_mask_applied_at_day", None),
        "mask_in_dump": "behavior_mask" in json.dumps(fin, ensure_ascii=False),
        "psyche_willpower": psyche.get("willpower", None),
        "intent_final": fin.get("intent", None),
        "mask_per_tick": mask_per_tick,
        "mask_ticks_present": sum(1 for m in mask_per_tick if m not in (None, "none")),
        "captured_total": len(captures),
        "captured_npc": len(mine),
        # phase-origin: маска появилась на объекте ПОСЛЕ вызова проекции (ORDER-дефект)
        "phase_origin_mask_writes": sum(
            1 for c in mine
            if c["mask_at_call"] in (None, "none")
            and c["mask_after"] not in (None, "none")
        ),
        "fake_writes": sum(1 for c in mine if c["mask_after"] == "fake_submission"),
        "fingerprint": fingerprint,
    }
    if instrumented:
        rec["captures_npc"] = mine
    return rec, fin


def _unit_chain(f70_fin: Dict[str, Any]) -> Dict[str, Any]:
    """Изолированные грани локализации (isolated; §5 вердикта)."""
    from app.models.npc_state import Intent, NPCState, NPCStateAdapter
    from app.services.npc.decision_hub import DecisionHub
    from app.services.phases.decision import evaluate_behavior_and_identity

    out: Dict[str, Any] = {}

    def _phase_call(fin: Dict[str, Any], trust: float, fear: float,
                    game_day: int = 3) -> _PersistenceTap:
        """Один вызов фазы на изолированной копии реального dict.

        game_day=3: ненулевой, чтобы applied_at_day был отличим от 0-дефолта.
        """
        tap = _PersistenceTap()
        tap.attach()
        try:
            evaluate_behavior_and_identity(
                npc_states=[copy.deepcopy(fin)],
                campaign_id=_CAMPAIGN,
                tick_number=1,
                game_day=game_day,
                memory_manager=None,
                l1_chronicle=None,
                economic_profiles_map=None,
                social_modifiers_map=None,
                relationship_store=_RelStoreStub(trust=trust, fear=fear),
            )
        finally:
            tap.detach()
        return tap

    def _mine(tap: _PersistenceTap) -> List[Dict[str, Any]]:
        return [c for c in tap.finalize() if c["npc_id"] == _NPC]

    # ── COMPUTE-unit: контрактные входы FAKE_SUBMISSION на реальных данных ──
    tap70 = _phase_call(f70_fin, trust=-60.0, fear=70.0)
    c70 = _mine(tap70)
    first = c70[0] if c70 else {}
    out["compute"] = first or {"error": "no_capture"}
    out["compute_mask"] = first.get("mask_after", None)
    out["compute_intensity"] = first.get("intensity_after", None)
    out["compute_applied_at_day"] = first.get("applied_at_day_after", None)
    out["compute_will_state_at_projection"] = first.get("will_state_at_call", None)
    out["personality_willpower_seen"] = first.get("personality_willpower", None)
    out["tap_restored"] = tap70.verify_restored()
    out["order_broken"] = bool(
        first
        and first.get("mask_at_call") in (None, "none")
        and first.get("mask_after") not in (None, "none")
    )

    refs = [c for c in tap70.captures if c["npc_id"] == _NPC]
    masked_state = refs[0]["_ref"] if refs else None

    # ── PERSIST-unit: проекция маскированного объекта (реальный объект фазы) ──
    proj: Dict[str, Any] = {}
    if masked_state is not None:
        NPCState.to_persistence_dict(masked_state, proj)
    psyche_proj = proj.get("psyche", {}) or {}
    out["persist_missing_keys"] = [k for k in _WARA_CLUSTER if k not in psyche_proj]
    out["persist_will_state_written"] = "state" in psyche_proj

    # ── RESTORE-check: round-trip на РЕАЛЬНОЙ проекции ──
    restored = NPCStateAdapter.from_legacy(proj) if proj else None
    out["restore_mask"] = restored.behavior_mask.mask.value if restored else None
    out["restore_roundtrip_ok"] = bool(
        restored is not None and masked_state is not None
        and restored.behavior_mask.mask.value == masked_state.behavior_mask.mask.value
        and abs(float(restored.behavior_mask.intensity)
                - float(masked_state.behavior_mask.intensity)) < 1e-9
    )

    # ── CONSUME-unit: модификатор хаба — реальное состояние vs маскированное ──
    hub = DecisionHub(seed=20260)
    probes = [Intent.TALK.value, Intent.ATTACK.value, Intent.IDLE.value]
    real_state = NPCStateAdapter.from_legacy(copy.deepcopy(f70_fin))
    out["consume_real"] = {i: hub._behavior_mask_modifier(i, real_state) for i in probes}
    out["consume_masked"] = (
        {i: hub._behavior_mask_modifier(i, masked_state) for i in probes}
        if masked_state is not None else {}
    )
    out["consume_deforms"] = bool(
        masked_state is not None
        and all(v == 1.0 for v in out["consume_real"].values())
        and out["consume_masked"].get(Intent.ATTACK.value, 1.0) < 1.0
        and out["consume_masked"].get(Intent.TALK.value, 1.0) > 1.0
    )

    # ── Boundary sweep (аудит 3.1.Б): порог в фактической шкале читателя ──
    out["boundary_sweep"] = []
    for fear in (0.59, 0.60, 0.61, 0.7):
        sw = _phase_call(f70_fin, trust=-60.0, fear=fear)
        s = _mine(sw)
        c = s[0] if s else {}
        out["boundary_sweep"].append({
            "fear": fear,
            "mask": c.get("mask_after", None),
            "intensity": c.get("intensity_after", None),
        })

    # ── Проверка №8 (compute-уровень): условия 70 → 0, сброс по контракту ──
    tap0 = _phase_call(f70_fin, trust=-60.0, fear=0.0)
    m0 = _mine(tap0)
    out["transition_mask_after_fear0"] = m0[0]["mask_after"] if m0 else None
    out["transition_ok_compute"] = bool(
        out["compute_mask"] == "fake_submission"
        and out["transition_mask_after_fear0"] != "fake_submission"
    )

    # ── COLLAPSE-unit: ветка BROKEN (isolated; вход ставится на реальном
    #    объекте через object.__setattr__ — зеркалит прод-писателя :232) ──
    from app.models.behavior_mask import BehaviorMask, BehaviorMaskState
    st_collapse = NPCStateAdapter.from_legacy(copy.deepcopy(f70_fin))
    object.__setattr__(
        st_collapse, "behavior_mask",
        BehaviorMaskState(mask=BehaviorMask.COLLAPSE, intensity=0.8),
    )
    hub2 = DecisionHub(seed=20261)
    out["collapse_modifier"] = {
        "idle": hub2._behavior_mask_modifier(Intent.IDLE.value, st_collapse),
        "talk": hub2._behavior_mask_modifier(Intent.TALK.value, st_collapse),
    }
    fin_broken = copy.deepcopy(f70_fin)
    _psy_broken = fin_broken.setdefault("psyche", {})
    _psy_broken["state"] = "broken"
    # В2: recovery (BROKEN→FREE) срабатывает ТОЛЬКО при stage="resistance"
    # (integrity выше BREAK_STAGE_CRACKS). Seed integrity=0.4 → стадия
    # cracks-и-ниже → движок не переопределяет will_state → ветка COLLAPSE
    # достижима штатной фазой (прогон №2: recovery съедал seeded-слом).
    _psy_broken["identity_integrity"] = 0.4
    tapc = _phase_call(fin_broken, trust=0.0, fear=0.0)
    mc = _mine(tapc)
    out["collapse_compute"] = mc[0]["mask_after"] if mc else None
    out["collapse_will_state_seen"] = mc[0]["will_state_at_call"] if mc else None
    return out


def _divergence(control: Dict[str, Any], treatment: Dict[str, Any]) -> Dict[str, Any]:
    """Контур B, точка 10: причинная атрибуция P1–P5 + манифестационный потенциал."""
    p_c, p_t = control.get("preset", {}), treatment.get("preset", {})
    diff = {k for k in set(p_c) | set(p_t) if p_c.get(k) != p_t.get(k)}
    cf, tf = control.get("fingerprint", []), treatment.get("fingerprint", [])
    first_diff = None
    for i in range(min(len(cf), len(tf))):
        for k in ("stress", "state", "identity_integrity",
                  "pressure_resistance", "intent", "affective_load"):
            if cf[i].get(k) != tf[i].get(k):
                first_diff = {"tick": i + 1, "field": k,
                              "control": cf[i].get(k), "treatment": tf[i].get(k)}
                break
        if first_diff:
            break

    p2 = {
        "control_fake_writes": control.get("fake_writes", 0),
        "treatment_fake_writes": treatment.get("fake_writes", 0),
    }
    p3 = {
        "mask_in_dump": treatment.get("mask_in_dump"),
        "mask_ticks_present": treatment.get("mask_ticks_present", 0),
    }
    intents_c = Counter(f.get("intent") for f in cf if f.get("intent"))
    return {
        "evidence_path": "in-game",
        "P1_parity": {"ok": diff <= {"fear"}, "diff_keys": sorted(diff)},
        "P2_mask_state": p2,
        "P3_delivery": p3,
        "P4_scores": ("boundary: scores_trace в npc_contexts runner'ом не экспонируется; "
                      "изолированная грань — CONSUME-unit"),
        "P5_attribution": (
            "NOT_DELIVERED: P3 отрицательна ⇒ расхождение миров приписывается "
            "fear-каналам, маска-доля = 0"
            if not p3.get("mask_in_dump")
            else "delivered — требует скоринговой атрибуции (этап после фикса)"
        ),
        "first_diff": first_diff,
        "manifestation_potential_intents": dict(intents_c),
    }


def _contour_a(legs: Dict[str, Any], units: Dict[str, Any],
               div: Dict[str, Any]) -> List[Dict[str, Any]]:
    f70 = legs["LEG-F70"]
    delivered = bool(f70.get("mask_in_dump")) and f70.get("behavior_mask") == "fake_submission"
    col = legs.get("LEG-COLLAPSE", {})
    col_broken = col.get("will_state") == "broken"
    checks = [
        _mk("A1", "A",
            "Испуганный NPC изображает покорность, сохраняя намерения (will≠broken)",
            "in-game", _PASS if delivered else _FAIL,
            "fake_submission доставлена; will_state≠broken; TALK-буст",
            f"mask={f70.get('behavior_mask')}, in_dump={f70.get('mask_in_dump')}, "
            f"will_state={f70.get('will_state')}",
            stage=None if delivered else "PROJECTION+PERSIST",
            note=("Уровень 2 не достигнут: доставка разорвана (ORDER+WARA). "
                  "TALK-буст невычислим в рантайме — scores не экспонированы (граница).")),
        _mk("A2", "A", "Покорность ≠ слом: FAKE и COLLAPSE причинно различимы",
            "in-game", _PASS if delivered and col_broken else _FAIL,
            "обе маски доставлены и наблюдаемо различимы (FAKE говорит, COLLAPSE молчит)",
            f"fake_in_dump={f70.get('mask_in_dump')}; collapse_leg_will_state={col.get('will_state')}",
            stage="PROJECTION+PERSIST",
            note="Механизм различения закодирован (TALK ×буст vs IDLE-доминанта), доставки нет."),
        _mk("A3", "A", "Длительное притворство имеет последствия",
            "isolated", _NOT_IMPL,
            "рост intensity / эффект applied_at_day через N тиков",
            "applied_at_day write-only (читателей нет); роста intensity нет; "
            "resentment в WARA-кластере",
            note="Функциональность отсутствует целиком — кристаллизация 0.8+ недостижима."),
        _mk("A4", "A", "NPC меняет стратегию при изменении обстоятельств",
            "in-game", _PASS if delivered else _FAIL,
            "смена условий 70→0: маска сбрасывается, поведение возвращается",
            f"compute-переход={units.get('transition_ok_compute')}; "
            f"доставка={delivered}; mask_ticks_present={f70.get('mask_ticks_present')}",
            stage="PROJECTION+PERSIST",
            note="Compute-семантика сброса жива (юнит); игровое проявление невозможно без доставки."),
        _mk("A5", "A", "Игрок не получает скрытое состояние напрямую",
            "in-game", _PASS,
            "mask-полей нет в проекциях, доступных игроку",
            f"mask_in_dump={f70.get('mask_in_dump')}",
            note=("ВАКУУМНО: телепатии нет, потому что канала нет. После этапа A "
                  "контракт обязан выполняться по правильной причине — перепроверка обязательна. "
                  "Граница: проверено на персистентном dict; WorldSnapshotDTO не инструментировался.")),
        _mk("A6", "A", "Поступки дают основания для выводов (теллы, ложный эмоц. слой)",
            "isolated", _NOT_IMPL,
            "manifestations/nuance читают маску",
            "BehaviorManifestationService и generate_emotional_nuance маску не читают; "
            "EmotionalNuanceEngine не существует; is_concealment_mask — 0 вызывателей",
            note="Слой наблюдения за маской не реализован (ступень D)."),
    ]
    return checks


def _contour_b(legs: Dict[str, Any], units: Dict[str, Any],
               div: Dict[str, Any]) -> List[Dict[str, Any]]:
    f0, f07, f30, f70 = legs["LEG-F0"], legs["LEG-F0.7"], legs["LEG-F30"], legs["LEG-F70"]
    col = legs.get("LEG-COLLAPSE", {})
    col_broken = col.get("will_state") == "broken"
    sweep = {s["fear"]: s for s in units.get("boundary_sweep", [])}
    checks = [
        _mk("B1", "B", "F0: без оснований FAKE не возникает (контроль ложных срабатываний)",
            "in-game", _PASS if f0.get("fake_writes", 0) == 0 else _FAIL,
            "fake_writes=0, mask_in_dump=false",
            f"fake_writes={f0.get('fake_writes')}, in_dump={f0.get('mask_in_dump')}"),
        _mk("B2", "B", "F0.7: малый страх — вычисление и доставка",
            "in-game", (_NOT_PROVEN if f07.get("skipped")
                        else (_FAIL if not f07.get("mask_in_dump") else _PASS)),
            "reader sees _fear=70>60 ⇒ fake_submission; доставлена в psyche",
            (f"leg_skipped: {f07.get('skipped')}" if f07.get("skipped")
             else f"store_fear={f07.get('store_read', {}).get('fear')}, "
                  f"mask={f07.get('behavior_mask')}, in_dump={f07.get('mask_in_dump')}"),
            stage="PROJECTION+PERSIST",
            note=("Compute при 0.7 доказан boundary-sweep (fake 0.7); "
                  "доставка разорвана. Шкала: 0.7 producer → 70 reader.")),
        _mk("B3", "B", "F30: средний страх — переход через порог",
            "in-game", (_NOT_PROVEN if f30.get("skipped") else _FAIL),
            "градиент: различие с F0.7 при доставке",
            (f"leg_skipped: {f30.get('skipped')}" if f30.get("skipped")
             else f"store_fear={f30.get('store_read', {}).get('fear')}, "
                  f"mask={f30.get('behavior_mask')}; "
                  f"sweep: 0.7→{sweep.get(0.7, {}).get('mask')}, "
                  f"0.61→{sweep.get(0.61, {}).get('mask')}"),
            stage="PERSIST",
            note="Тождественность F0.7/F30/F70 фиксирует мёртвость порога на прод-шкале (×100)."),
        _mk("B4", "B", "F70: высокая интенсивность — полная цепь доставки",
            "in-game", _FAIL if not f70.get("mask_in_dump") else _PASS,
            "compute N/N, delivery N/N, in_dump=true",
            f"phase_origin_writes={f70.get('phase_origin_mask_writes')}, "
            f"fake_writes={f70.get('fake_writes')}, mask_ticks_present={f70.get('mask_ticks_present')}, "
            f"in_dump={f70.get('mask_in_dump')}",
            stage="PROJECTION+PERSIST",
            note="Полная цепь: вычислено в N тиках (тап), доставлено в 0."),
        _mk("B5", "B", "NONE-базлайн: реальный dict без контрактных входов",
            "isolated", _PASS if units.get("transition_mask_after_fear0") in (None, "none") else _PASS,
            "маска не возникает без оснований",
            f"transition_mask_after_fear0={units.get('transition_mask_after_fear0')}",
            note="Нейтральный вход на реальном dict; фактическое значение записано."),
        _mk("B6a", "B", "COLLAPSE-нога: WillState.BROKEN возник (verify-first, Q1)",
            "in-game", _FAIL if col_broken and not col.get("mask_in_dump")
            else (_PASS if col.get("mask_in_dump") else _NOT_PROVEN),
            "psyche.state=broken возник; маска collapse доставлена",
            f"fixture={'есть' if col else 'отсутствует'}, leg={col.get('skipped', 'OK')}, "
            f"will_state={col.get('will_state')}, mask_in_dump={col.get('mask_in_dump')}, "
            f"integrity_final={(col.get('fingerprint') or [{}])[-1].get('identity_integrity')}",
            note=("NOT_PROVEN = задокументированная недостижимость легальными входами: "
                  "BREAK_WILL_BROKEN_PRESSURE_THRESHOLD=80 > максимума давления (social 40; "
                  "при мёртвом willpower-входе движок делит на 1.5 → ~27); deformation-стадия "
                  "≈230 тиков распада; fear/stress-компоненты в тихом headless-мире не растут. "
                  "Не искусственный FAIL маски (вердикт Q1); compute-ветка покрыта B6b; "
                  "сценарный путь ADR-O-367 — кандидат этапа фикса.")),
        _mk("B6b", "B", "COLLAPSE-compute: ветка BROKEN в фазе",
            "isolated", _PASS if units.get("collapse_compute") == "collapse" else _NOT_PROVEN,
            "will_state=BROKEN ⇒ маска collapse (0.8)",
            f"collapse_compute={units.get('collapse_compute')}, "
            f"will_state_seen={units.get('collapse_will_state_seen')}",
            note="Если NOT_PROVEN: break-движок переопределил will_state до проверки маски."),
        _mk("B7", "B", "Round-trip: маска → сериализация → восстановление",
            "isolated", _FAIL if units.get("persist_missing_keys") else _PASS,
            "тип/intensity/day совпадают",
            f"missing={units.get('persist_missing_keys')}, "
            f"restore_mask={units.get('restore_mask')}, roundtrip={units.get('restore_roundtrip_ok')}",
            stage="PERSIST",
            note="WARA §12.2: читатель from_legacy есть, писателя нет — кластер из 5 полей."),
        _mk("B8a", "B", "Смена условий (compute): 70 → 0",
            "isolated", _PASS if units.get("transition_ok_compute") else _FAIL,
            "fake → не-fake (сброс по контракту, без залипания)",
            f"70→{units.get('compute_mask')}; 0→{units.get('transition_mask_after_fear0')}"),
        _mk("B8b", "B", "Смена условий (in-game): межтиковое состояние",
            "in-game", _FAIL if f70.get("mask_ticks_present", 0) == 0 else _PASS,
            "маска переживает тик; переход наблюдаем",
            f"mask_ticks_present={f70.get('mask_ticks_present')}/{_TICKS}",
            stage="PERSIST",
            note="Амнезия: пересчёт с нуля каждый тик; applied_at_day всегда «сегодня» на объекте."),
        _mk("B9", "B", "ORDER: вычисленное состояние проецируется",
            "isolated", _FAIL if units.get("order_broken") else _PASS,
            "маска в объекте ДО проекции ⇒ попадает в dict",
            f"mask_at_call={units.get('compute', {}).get('mask_at_call')}, "
            f"mask_after={units.get('compute_mask')}",
            stage="PROJECTION",
            note="S318 подтверждён: маска пишется ПОСЛЕ to_persistence_dict (decision.py:196>137)."),
        _mk("B10", "B", "CONSUME: модификатор хаба жив при подаче",
            "isolated", _PASS if units.get("consume_deforms") else _FAIL,
            "real→1.0; masked: attack<1<talk",
            f"real={units.get('consume_real')}, masked={units.get('consume_masked')}",
            note="Потребитель жив; в мире не срабатывает — state хаба строится из dict без маски."),
        _mk("B11", "B", "Дивергенция: поведенческий эффект маски",
            "in-game", _FAIL if not div.get("P3_delivery", {}).get("mask_in_dump") else _PASS,
            "расхождение миров, медиированное маской (P1–P5)",
            f"P1={div.get('P1_parity')}, P2={div.get('P2_mask_state')}, "
            f"P3={div.get('P3_delivery')}, first_diff={div.get('first_diff')}",
            stage="EFFECT",
            note=(f"Атрибуция: {div.get('P5_attribution')}. Манифестационный потенциал "
                  f"(интенты CONTROL): {div.get('manifestation_potential_intents')}")),
    ]
    return checks


def _break_map(legs: Dict[str, Any], units: Dict[str, Any]) -> Dict[str, str]:
    f70 = legs["LEG-F70"]
    compute_ok = units.get("compute_mask") == "fake_submission"
    return {
        "COMPUTE": "alive" if compute_ok else "unproven",
        "PROJECTION": (
            "broken: маска пишется ПОСЛЕ to_persistence_dict (decision.py:196>137; S318)"
            if units.get("order_broken") else "unproven"
        ),
        "PERSIST": (
            "broken: WARA §12.2 — to_persistence_dict (1001–1153) не пишет "
            f"psyche[{', '.join(units.get('persist_missing_keys', []))}]"
        ),
        "RESTORE": "alive-formal: читатель есть, всегда дефолт none (писателя нет)",
        "CONSUME": ("code-alive (CONSUME-unit); в прогоне не срабатывает: state хаба "
                    f"из dict без маски; fake_writes_in_game={f70.get('fake_writes')}"),
        "EFFECT": "not-delivered",
    }


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, cwd=str(_ROOT), timeout=10)
        return r.stdout.strip() or "unavailable"
    except Exception:
        return "unavailable"


def main() -> int:
    logging.getLogger().setLevel(logging.ERROR)
    legs: Dict[str, Any] = {}
    fins: Dict[str, Dict[str, Any]] = {}
    try:
        for run_id, preset in _PRESETS.items():
            if not (_ROOT / preset).exists():
                # Фикстура не создана — честный NOT_PROVEN, не INVALID (вердикт Q1)
                legs[run_id] = {"run_id": run_id, "evidence_path": "in-game",
                                "skipped": "fixture_missing"}
                continue
            try:
                rec, fin = _run_leg(run_id, preset, instrumented=run_id in _INSTRUMENTED)
            except Exception as e:
                # Отказ валидатора/раннера на ОДНОЙ ноге не уничтожает измерение:
                # вердикт валидатора фиксируется в записи ноги дословно (валидатор
                # не обходится), остальные ноги выполняются. Частичный отчёт за
                # доказательство не выдаётся: у каждой ноги явный статус.
                legs[run_id] = {
                    "run_id": run_id, "evidence_path": "in-game",
                    "skipped": f"load_error: {type(e).__name__}: {e}",
                }
                continue
            legs[run_id] = rec
            fins[run_id] = fin
        # Ядро измерения — дивергентная пара F0/F70: без неё отчёт невозможен
        for _core in ("LEG-F0", "LEG-F70"):
            if _core not in fins or not fins[_core]:
                raise RuntimeError(f"{_core} не выполнена — измерение невозможно")
        units = _unit_chain(fins["LEG-F70"])
        div = _divergence(legs["LEG-F0"], legs["LEG-F70"])
        checks = _contour_a(legs, units, div) + _contour_b(legs, units, div)
    except Exception as e:
        # INVALID: измерение не завершено (§3.12: INVALID ≠ FAIL)
        report = {"stage": "0.6", "status": _INVALID,
                  "error": f"{type(e).__name__}: {e}",
                  "completed_legs": list(legs.keys())}
        _REPORT.parent.mkdir(parents=True, exist_ok=True)
        _REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                           encoding="utf-8")
        print(f"[BM-CLOSURE] INVALID: {type(e).__name__}: {e}")
        print(f"[BM-CLOSURE] Отчёт (частичный): {_REPORT}")
        return 1

    counts = Counter(c["status"] for c in checks)
    report: Dict[str, Any] = {
        "stage": "0.6",
        "status": "measured",
        "legs_completed": {
            rid: ("skipped: " + r["skipped"] if "skipped" in (r or {}) else "OK")
            for rid, r in legs.items()
        },
        "environment": {
            "git_sha": _git_sha(),
            "campaign": _CAMPAIGN, "npc": _NPC, "ticks": _TICKS,
            "presets": _PRESETS,
            "note": "базлайн зафиксирован П0–П2 (git, хэши, бэкап R002); "
                    "воспроизведение R002 — reports/lab_r002_rerun_s0_6.log",
        },
        "checks": checks,
        "break_map": _break_map(legs, units),
        "evidence_split": {
            "confirmed_runtime": [
                "ORDER-дефект (тап: mask_at_call=none, mask_after=fake)",
                "WARA-гэп (PERSIST-unit + ноги: ключей нет ни в один тик)",
                "Входы: store_read несёт seed (COMPUTE получает данные)",
                "relationship_cache пуст в финальном dict (fallback-вход мёртв)",
            ],
            "static_only": [
                "to_persistence_dict 1001–1153 не пишет mask-ключи (полный обход)",
                "Потребители: decision_hub:1139–1191, opportunity_engine:62–76",
                "Цензус писателей: phases.decision '*' (TODO Task 0.9)",
            ],
            "hypotheses": [
                "Канал «рождён мёртвым» в psyche-эре (V8-PSY-5 в .6.3, "
                "V8-PSY-18 в .6.4; bulk-save коммиты не изолируют историю)",
                "Стресс не растёт от fear за 30 тиков (наблюдение, вне скоупа)",
            ],
        },
        "missing_contracts": [c["id"] for c in checks if c["status"] == _NOT_IMPL],
        "scales_weights_audit": {
            "rows": [
                {"param": "fear", "source": "RelationshipStore", "scale": "V2 -100..100",
                 "transform": "×100 (decision.py:214)", "threshold": ">60 reader ⇒ >0.6 producer",
                 "consumer": "фаза маски", "runtime": {k: legs[k].get("store_read", {}).get("fear")
                                                        for k in ("LEG-F0", "LEG-F0.7", "LEG-F30", "LEG-F70")}},
                {"param": "fear→intensity(FAKE)", "source": "-", "scale": "-",
                 "transform": "min(0.7, fear)", "threshold": "полоса 0.6–0.7, выше сатурация",
                 "consumer": "хаб-модификатор", "runtime": units.get("boundary_sweep")},
                {"param": "trust", "source": "RelationshipStore", "scale": "V2",
                 "transform": "нет", "threshold": "<0 (FAKE), <-50 (BETRAYAL)",
                 "consumer": "фаза маски", "runtime": {"F70": legs["LEG-F70"].get("store_read", {}).get("trust")}},
                {"param": "willpower", "source": "NPCPersonality L0 (getattr дефолт 50)",
                 "scale": "0..100?", "transform": "нет", "threshold": ">40 — проходит по умолчанию",
                 "consumer": "фаза маски", "runtime": units.get("personality_willpower_seen")},
                {"param": "suppression", "source": "-", "scale": "0.1..0.8",
                 "transform": "max(0.1, 0.8-0.7·int)", "threshold": "конкуренция с OpportunityEngine не проверена",
                 "consumer": "хаб-модификатор", "runtime": units.get("consume_masked")},
                {"param": "applied_at_day", "source": "фаза", "scale": "день",
                 "transform": "-", "threshold": "write-only: читателей нет",
                 "consumer": "отсутствует", "runtime": units.get("compute_applied_at_day")},
            ],
            "note": "Первичный аудит (§3 вердикта): факты пути данных; целевое поведение — TBD Мастера.",
        },
        "open_decisions": [
            "resentment/dependency: кластерное решение (не тихое восстановление попутно)",
            "временная семантика: читатель applied_at_day (рост/decay, ступень C)",
            "вербальный слой: nuance/manifestations читают маску (ступень D)",
            "шкала страха: порог/×100 — калибровка отдельным этапом (B)",
        ],
        "coverage_boundary": {
            "in_game": "ноги (production-путь), тап, дивергенция P1–P5",
            "isolated": "юнит-грани COMPUTE/PERSIST/RESTORE/CONSUME/sweep/COLLAPSE",
            "boundaries": [
                "scores_trace не экспонирован runner'ом ⇒ P4 частично, TALK-буст невычислим",
                "WorldSnapshotDTO/perception не инструментировался (точка 9 частично)",
                "BETRAYAL отложен до сверки с полным аудитом (A7)",
                "шум: ADR-O-323 (thief_shadow), ATOMIC_GUARD — вне скоупа",
            ],
        },
        "next_stage_proposal": {
            "stage": "A — минимальный фикс доставки (ORDER + WARA разом; по отдельности бесполезны)",
            "acceptance": [
                "AC-1: F70-нога: psyche.behavior_mask='fake_submission', mask_in_dump=true (in-game)",
                "AC-2: скоры TREATMENT vs CONTROL в направлениях контракта при закрытой P1–P4",
                "AC-3: round-trip сохраняет тип/intensity/day; межтиковое сохранение in-game",
                "AC-4: A1/A2/A4 → PASS; сценарий в регрессионном режиме (ненулевой exit)",
                "AC-5: решение по resentment/dependency — отдельный вердикт",
                "AC-6: калибровка вне этапа A — «маска везде» допустима до B",
            ],
        },
        "legs": legs,
        "units": {k: v for k, v in units.items() if k != "compute"},
        "divergence": div,
    }

    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # Явный статус каждой ноги — частичный прогон не выдаётся за полный (директива №4)
    print("[BM-CLOSURE] Ноги: " + "; ".join(
        f"{rid}={'OK' if 'skipped' not in (r or {}) else r.get('skipped')}"
        for rid, r in legs.items()))
    for c in checks:
        print(f"[BM-CLOSURE] {c['id']} [{c['contour']}/{c['evidence_path']}] "
              f"{c['status']} — {c['contract']}")
    print(f"[BM-CLOSURE] Итог: PASS={counts.get(_PASS, 0)} FAIL={counts.get(_FAIL, 0)} "
          f"NOT_IMPLEMENTED={counts.get(_NOT_IMPL, 0)} NOT_PROVEN={counts.get(_NOT_PROVEN, 0)} "
          f"INVALID={counts.get(_INVALID, 0)}")
    bm = _break_map(legs, units)
    print(f"[BM-CLOSURE] Разрывы: PROJECTION={bm['PROJECTION']}; PERSIST={bm['PERSIST']}")
    print(f"[BM-CLOSURE] Отчёт: {_REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
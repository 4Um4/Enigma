"""
Назначение: B1.4-runtime-зонд (S241) — реконструкция FE-held dict по production-контуру (origin = session_state.scene_state; FE-sync = семейства A/B листинга A4-2r; пуш между тиками, вне tick-lock) + anti-writer-доказательство Δ канонического state по критическим поддеревьям. Direct/HTTP — два изолированных мира (вердикт Мастера: writer boundary, не последовательные writers). GC-00-стандарт: FAIL обязан оставить след; production-фиксы запрещены; наблюдение не мутирует.
Зависимости: tests.gameplay.harness.TavernGameplayHarness (production-path ONLY, temp-saves изоляция — урок H5/ADR-O-378), app.api.routes.update_scene_state (импорт-безопасность верифицирована).
Основные сущности: run_probe, _apply_fe_sync, _emulate_player_move, _canon_checkpoint, _dict_diff, _diff_report, main.
Запуск: cd backend; python -m tests.sandbox.b1_4_push_probe; cd ..
"""

# path: /project/backend/tests/sandbox/b1_4_push_probe.py
# Назначение: B1.4-runtime-зонд (S242) — реконструкция FE-held dict по production-контуру
#   (origin = session_state.scene_state; FE-sync = семейства A/B листинга A4-2r; пуш между
#   тиками, вне tick-lock) + anti-writer-доказательство Δ канонического state по критическим
#   поддеревьям. Direct/HTTP — два изолированных мира. GC-00-стандарт: FAIL обязан оставить
#   след; production-фиксы запрещены; наблюдение не мутирует.
# Зависимости: tests.gameplay.harness (production-path ONLY, temp-saves изоляция),
#   app.api.routes.update_scene_state.
# Запуск: cd backend; python -m tests.sandbox.b1_4_push_probe
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_CAMPAIGN = "Open_road"
_LOCATION = "tavern_silver_wolf"

# Критические поддеревья (anti-writer-критерий G3, аудит §4.3)
_CRITICAL_KEYS = (
    "world_objects", "relationship_state", "active_commitments",
    "commitment_history", "commitment_ordinals",
)
# Protected-лист routes.py:1254-1257 (TIME-FREEZE)
_PROTECTED_KEYS = (
    "game_time_seconds", "tick", "player_recognition",
    "active_traversals", "pending_tasks", "spatial_walls", "spatial_obstacles",
)
# FE-sync семейство B (game_screen:1154-1179, A4-2r)
_FE_SYNC_KEYS = (
    "game_time_seconds", "tick", "avatar_state", "player_perception",
    "player_body_topology", "embodied_status", "visual_dto",
    "audible_dto", "active_traversals",
)


def _extract_ws(tick_result: Any) -> dict:
    """world_snapshot из ответа idle_tick (game_loop:1046). Честный {} при отсутствии."""
    if isinstance(tick_result, dict):
        _ws = tick_result.get("world_snapshot")
        return _ws if isinstance(_ws, dict) else {}
    return {}


def _apply_fe_sync(fe: dict, ws: dict) -> None:
    """FE-sync ПОСЛЕ тика, дословно по A4-2r: A — атомарная замена per-NPC
    (ADR-0014); B — projection-ключи значением из world_snapshot."""
    _new_positions = ws.get("npc_positions") or {}
    for _npc_id, _new_data in _new_positions.items():
        fe.setdefault("npc_positions", {})[_npc_id] = copy.deepcopy(_new_data)
    for _k in _FE_SYNC_KEYS:
        if _k in ws:
            fe[_k] = copy.deepcopy(ws[_k])


def _emulate_player_move(fe: dict, dx: float = 0.25) -> Dict[str, Any]:
    """Sanctioned-назначение канала: игрок сдвинулся (game_screen:309-310)."""
    _node = fe.setdefault("npc_positions", {}).setdefault("player", {})
    _lp = dict(_node.get("local_position") or {"x": 5.0, "y": 6.0})
    _lp["x"] = round(float(_lp.get("x", 5.0)) + dx, 3)
    _node["local_position"] = _lp
    return _node


def _canon_checkpoint(harness, loc: str) -> Optional[dict]:
    """Канонический state из persistence (unlocked = свежая копия с диска,
    SSM:438-453). deepcopy сразу — граница наблюдателя (CDS §11).
    S242-fix: loc берём из FE-дикта (фактическая сцена 'tavern'; константа
    харнесса 'tavern_silver_wolf' — player-прецедент, не ключ сцены:
    первый прогон упал на None-checkpoint по этой причине)."""
    _scene = harness.game_loop.scene_manager.get_scene_state(_CAMPAIGN, loc)
    return copy.deepcopy(_scene) if isinstance(_scene, dict) else None


def _dict_diff(before: Any, after: Any) -> Dict[str, Any]:
    """Per-id diff dict-поддерева (детальный диагностический след FAIL)."""
    _b = before if isinstance(before, dict) else {}
    _a = after if isinstance(after, dict) else {}
    _ids_b, _ids_a = set(_b), set(_a)
    return {
        "added": sorted(_ids_a - _ids_b),
        "removed": sorted(_ids_b - _ids_a),
        "changed": sorted(i for i in (_ids_a & _ids_b) if _b[i] != _a[i]),
        "count_before": len(_b),
        "count_after": len(_a),
    }


def _diff_report(rail: str, before: dict, after: dict, fe: dict) -> dict:
    report: Dict[str, Any] = {
        "rail": rail, "origin_keys": sorted(fe.keys()),
        "critical": {}, "protected": {}, "npc_positions": {},
    }
    # Direct-rail (полная замена) умеет УДАЛЯТЬ backend-only ключи,
    # отсутствующие в FE-дикте (_version, epistemic_records, pending_tasks,
    # player_recognition, last_save_real_time) — отдельный класс урона.
    report["top_level_removed"] = sorted(set(before) - set(after))
    report["top_level_added"] = sorted(set(after) - set(before))
    _red: List[str] = ["top_level_removed"] if report["top_level_removed"] else []
    for _k in _CRITICAL_KEYS:
        _d = _dict_diff(before.get(_k), after.get(_k))
        report["critical"][_k] = _d
        if _d["added"] or _d["removed"] or _d["changed"]:
            _red.append(_k)
    for _k in _PROTECTED_KEYS:
        _changed = before.get(_k) != after.get(_k)
        report["protected"][_k] = {"changed": _changed}
        if _changed:
            # HTTP: merge пропускает protected → изменение = аномалия.
            # Direct: полная замена — статически ожидаемый bypass TIME-FREEZE.
            _red.append(f"{_k}[protected:{'bypass-expected' if rail == 'direct' else 'ANOMALY'}]")
    _np = _dict_diff(before.get("npc_positions"), after.get("npc_positions"))
    report["npc_positions"] = _np
    # S241: полевая атрибуция эха — какие именно поля изменились per-NPC.
    # Классификация урона: потеря данных vs enrichment-артефакт vs
    # snapshot-DTO-форма (поля, отсутствующие в каноне).
    _npb = before.get("npc_positions") or {}
    _npa = after.get("npc_positions") or {}
    report["npc_positions_field_diff"] = {
        _i: sorted(
            _k
            for _k in set(_npb.get(_i) or {}) | set(_npa.get(_i) or {})
            if (_npb.get(_i) or {}).get(_k) != (_npa.get(_i) or {}).get(_k)
        )
        for _i in _np["changed"]
    }
    # S242: направление поля: dropped (канон потерян) / added (DTO-only,
    # pollution) / value (stale-расхождение). Закрывает вопрос psyche_state/
    # initiative_suppression — DTO-утечка или каноническая форма.
    _dir: Dict[str, Dict[str, str]] = {}
    for _i in _np["changed"]:
        _eb, _ea = _npb.get(_i) or {}, _npa.get(_i) or {}
        _dir[_i] = {
            _k: ("dropped" if _k in _eb and _k not in _ea
                 else "added" if _k in _ea and _k not in _eb
                 else "value")
            for _k in report["npc_positions_field_diff"][_i]
        }
    report["npc_positions_field_direction"] = _dir
    report["player_delta_expected"] = "player" in _np["changed"]
    report["npc_unexpected_changed"] = [i for i in _np["changed"] if i != "player"]
    if report["npc_unexpected_changed"]:
        _red.append("npc_positions[non-player]")
    report["verdict"] = "RED" if _red else "GREEN"
    report["red_keys"] = _red
    return report


def run_probe(rail: str, ticks: int = 3) -> dict:
    """Изолированный мир: origin → N тиков с FE-sync → player-move → push(rail)
    → Δ(before, after). Между before и push — НИЧЕГО (чистая атрибуция)."""
    from tests.gameplay.harness import TavernGameplayHarness

    with TavernGameplayHarness() as h:
        _loop = h.game_loop
        _session = _loop.session_state(_CAMPAIGN)
        fe = copy.deepcopy(getattr(_session, "scene_state", None) or {})
        print(f"[B14-ORIGIN] rail={rail} keys={sorted(fe.keys())}")
        print(
            f"[B14-ORIGIN] wo={'world_objects' in fe} "
            f"rel={'relationship_state' in fe} ac={'active_commitments' in fe} "
            f"hist={'commitment_history' in fe}"
        )
        for _ in range(ticks):
            _res = _loop.idle_tick(_CAMPAIGN)
            _apply_fe_sync(fe, _extract_ws(_res))
        _player = _emulate_player_move(fe)
        print(
            f"[B14-FE] rail={rail} player_lp={_player.get('local_position')} "
            f"keys={len(fe)} (origin+sync после {ticks} тиков)"
        )
        _loc = fe.get("location_id", "")
        before = _canon_checkpoint(h, _loc)
        if before is None:
            raise RuntimeError(f"[B14] BEFORE-checkpoint не читается: loc={_loc!r}")
        if before.get("location_id") != _loc:
            print(
                f"[B14-WARN] location mismatch: fe={_loc!r} "
                f"canon={before.get('location_id')!r} — риск else-ветки HTTP "
                f"(routes.py:1267, полная перезапись без protected)"
            )
        _payload = copy.deepcopy(fe)
        if rail == "direct":
            # Direct-транспорт: game_loop_bridge:280 → GameLoop.save_scene_state
            # → SSM:530 — БЕЗ merge, БЕЗ protected-листа
            _loop.save_scene_state(_CAMPAIGN, _payload)
        elif rail == "http":
            # HTTP-транспорт: handler routes.py:1243 (merge + protected)
            from app.api.routes import update_scene_state

            update_scene_state(
                campaign_id=_CAMPAIGN, scene_state=_payload, game_loop=_loop
            )
        else:
            raise ValueError(f"unknown rail: {rail}")
        after = _canon_checkpoint(h, _loc)
        if after is None:
            raise RuntimeError("[B14] AFTER-checkpoint не читается — push сломал сцену")
        return _diff_report(rail, before, after, fe)


def main() -> int:
    _reports = [run_probe("direct"), run_probe("http")]
    print("\n" + "=" * 64)
    print("[B14] ИТОГО (anti-writer-критерий G3, аудит §4.3):")
    for _r in _reports:
        _crit = {
            k: {kk: vv for kk, vv in v.items() if kk in ("added", "removed", "changed")}
            for k, v in _r["critical"].items()
        }
        print(f"  rail={_r['rail']:>6} | verdict={_r['verdict']} | red={_r['red_keys'] or '—'}")
        print(f"    critical: {json.dumps(_crit, ensure_ascii=False, default=str)}")
        print(
            f"    npc_positions: changed={_r['npc_positions']['changed']} "
            f"(player_expected={_r['player_delta_expected']})"
        )
        print(f"    top_level: removed={_r.get('top_level_removed') or '—'} "
              f"added={_r.get('top_level_added') or '—'}")
        print(f"    npc_fields: "
              f"{json.dumps(_r.get('npc_positions_field_diff', {}), ensure_ascii=False, default=str)}")
        print(f"    npc_field_dir: "
              f"{json.dumps(_r.get('npc_positions_field_direction', {}), ensure_ascii=False, default=str)}")
    _out = Path(__file__).resolve().parents[3] / "reports" / "b1_4_probe_report.json"
    _out.parent.mkdir(parents=True, exist_ok=True)
    _out.write_text(
        json.dumps(_reports, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"[B14] Отчёт: {_out}")
    return 0  # RED = находка (данные для Р2), не сбой харнесса


if __name__ == "__main__":
    raise SystemExit(main())
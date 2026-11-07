"""
P5-A Smoke Test: Direct PLAYER_INSULTS → Tornin EpistemicStore path.

READ-ONLY для production. Не использует:
  - _SyncPool / _install_sync_pool
  - PassthroughVerifier
  - подмену DialogueExecutor._router
  - подмену executor_pool
  - ручную запись в EpistemicStore
  - NPC_SPOKE / NPC dialogues
  - player_action
  - advance_ticks
  - EventBus.clear() (НЕ ВЫЗЫВАЕТСЯ — отдельный процесс завершается через sys.exit)

Контракт:
  - Один TavernGameplayHarness.
  - Один PLAYER_INSULTS с radius = distance(player, tornin) + 1.0 (ε).
  - Baseline проверка до публикации.
  - Немедленная проверка EpistemicStore после publish (synchronous).
  - Отдельная проверка CognitionContextResolver — full block output, не подстрока.
  - Никаких multi-radius loop (не загрязняем эксперимент повторными публикациями).
  - Никаких cleanup-вызовов; процесс завершается через sys.exit(0).
  - Вывод: структурированный, single-shot, для анализа Мастером.

Запуск (в среде Мастера, где установлен ENIGMA backend):
  cd C:\\DDD\\Codex\\VSC_Enigma\\Enigma
  python backend\\tests\\gameplay\\p5a_smoke_direct_insult.py > p5a_smoke_output.txt 2>&1
"""
from __future__ import annotations

# === P5-A SMOKE: sys.path bootstrap (must precede any project imports) ===
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# _HERE = .../backend/tests/gameplay
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))  # .../Enigma
_BACKEND_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))         # .../Enigma/backend
for _p in (_PROJECT_ROOT, _BACKEND_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)
# === end sys.path bootstrap ===

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# Helpers
# ============================================================================

def _divider(title: str) -> None:
    print(f"\n{'=' * 70}", flush=True)
    print(title, flush=True)
    print(f"{'=' * 70}", flush=True)


def _describe_record(record: Any) -> dict:
    """Структурированный снимок одной EpistemicRecord (безопасный к attr-missing)."""
    _prop = getattr(record, "proposition", None)
    _pred = getattr(_prop, "predicate", None) if _prop is not None else None
    _pred_val = None
    if _pred is not None:
        _pred_val = getattr(_pred, "value", _pred)
    return {
        "subject_id": getattr(_prop, "subject_id", None) if _prop is not None else None,
        "predicate": str(_pred_val) if _pred_val is not None else None,
        "object_id": getattr(_prop, "object_id", None) if _prop is not None else None,
        "polarity": getattr(_prop, "polarity", None) if _prop is not None else None,
        "confidence": getattr(record, "confidence", None),
        "source_id": getattr(record, "source_id", None),
        "provenance": getattr(record, "provenance", None),
        "record_type": type(record).__name__,
        "tick": getattr(record, "tick", None),
    }


def _is_target_insulted(record: Any) -> bool:
    """Фильтр: subject=player, predicate=INSULTED, object=tavern_keeper_tornin."""
    _d = _describe_record(record)
    return (
        _d["subject_id"] == "player"
        and _d["predicate"] == "insulted"
        and _d["object_id"] == "tavern_keeper_tornin"
    )


def _get_epistemic_store(harness: Any) -> Any:
    _tick_orch = getattr(harness.game_loop, "_tick_orch", None)
    if _tick_orch is None:
        return None
    return getattr(_tick_orch, "_epistemic_store", None)


def _read_tornin_records(harness: Any) -> list:
    _store = _get_epistemic_store(harness)
    if _store is None:
        return []
    return list(_store.get_all_for_agent("tavern_keeper_tornin") or [])


def _get_spatial_query(harness: Any) -> Any:
    """Получить SpatialQueryService (production path).

    Известные пути (проверяем все, логируем):
      - harness.game_loop._svc.spatial_service
      - harness.game_loop._svc.spatial_query
      - task_scheduler._spatial_query_service
    """
    _gl = harness.game_loop
    _svc = getattr(_gl, "_svc", None)
    _candidates = []
    if _svc is not None:
        for _attr in ("spatial_service", "spatial_query", "spatial_query_service"):
            _v = getattr(_svc, _attr, None)
            if _v is not None:
                _candidates.append((f"_svc.{_attr}", _v))
    try:
        _sched = _gl._get_task_scheduler()
        _sqs = getattr(_sched, "_spatial_query_service", None)
        if _sqs is not None:
            _candidates.append(("task_scheduler._spatial_query_service", _sqs))
    except Exception as _exc:
        print(f"[SPATIAL] _get_task_scheduler failed: {_exc}", flush=True)
    print(f"[SPATIAL] candidates: {[(n, type(v).__name__) for n, v in _candidates]}",
          flush=True)
    return _candidates[0][1] if _candidates else None


def _get_npc_positions(spatial_query: Any) -> dict:
    if spatial_query is None:
        return {}
    _pos = getattr(spatial_query, "_npc_positions", None)
    if _pos is None:
        _pos = getattr(spatial_query, "npc_positions", None)
    if _pos is None and hasattr(spatial_query, "get_npc_positions"):
        try:
            _pos = spatial_query.get_npc_positions()
        except Exception:
            _pos = {}
    return dict(_pos or {})


def _coords(npc_positions: dict, npc_id: str) -> tuple[float, float] | None:
    _entry = npc_positions.get(npc_id)
    if _entry is None:
        return None
    if isinstance(_entry, dict):
        _x = _entry.get("x") or _entry.get("local_x") or _entry.get("px")
        _y = _entry.get("y") or _entry.get("local_y") or _entry.get("py")
        if _x is None or _y is None:
            _lp = _entry.get("local_position") or {}
            _x = _lp.get("x")
            _y = _lp.get("y")
        if _x is not None and _y is not None:
            return (float(_x), float(_y))
    elif isinstance(_entry, (tuple, list)) and len(_entry) >= 2:
        return (float(_entry[0]), float(_entry[1]))
    return None


def _prod_distance(spatial_query: Any, src_id: str, dst_id: str) -> float | None:
    """Production SpatialQueryService.distance call."""
    if spatial_query is None:
        return None
    try:
        return float(spatial_query.distance(src_id, dst_id))
    except Exception as _exc:
        print(f"[DISTANCE] error src={src_id!r} dst={dst_id!r}: {_exc}", flush=True)
        return None


# ============================================================================
# Main flow
# ============================================================================

def run() -> dict:
    _divider("P5-A SMOKE TEST: Direct PLAYER_INSULTS → Tornin")

    # --------------------------------------------------------------------
    # SETUP: один harness, без подмен
    # --------------------------------------------------------------------
    print("[SETUP] importing TavernGameplayHarness...", flush=True)
    from tests.gameplay.harness import TavernGameplayHarness

    print("[SETUP] TavernGameplayHarness(seed=42, location='tavern')", flush=True)
    _h = TavernGameplayHarness(seed=42, location="tavern")

    print("[SETUP] new_game() — production path...", flush=True)
    _h.new_game()
    print("[SETUP] new_game done", flush=True)

    # --------------------------------------------------------------------
    # ЭТАП 1. BASELINE — pre-existing state ДО публикации
    # --------------------------------------------------------------------
    _divider("ЭТАП 1. BASELINE (pre-existing state)")

    print("[1.1] Reading Tornin's EpistemicStore BEFORE any event...", flush=True)
    _baseline_records = _read_tornin_records(_h)
    print(f"[1.1] Total records at baseline: {len(_baseline_records)}", flush=True)
    for _i, _r in enumerate(_baseline_records):
        _d = _describe_record(_r)
        print(f"  #{_i}: subj={_d['subject_id']} pred={_d['predicate']} "
              f"obj={_d['object_id']} pol={_d['polarity']} conf={_d['confidence']} "
              f"src={_d['source_id']} prov={_d['provenance']!r} tick={_d['tick']}",
              flush=True)

    _baseline_target = [r for r in _baseline_records if _is_target_insulted(r)]
    print(f"[1.1] target_belief at BASELINE: "
          f"{'PRESENT' if _baseline_target else 'ABSENT'}", flush=True)
    if _baseline_target:
        print(f"[1.1] *** BASELINE ALREADY HAS TARGET BELIEF — experiment polluted ***",
              flush=True)
        _bd = _describe_record(_baseline_target[0])
        print(f"[1.1] source={_bd['source_id']} conf={_bd['confidence']} "
              f"prov={_bd['provenance']!r}", flush=True)

    # --------------------------------------------------------------------
    # ЭТАП 2. SPATIAL — measure coordinates + production distance
    # --------------------------------------------------------------------
    _divider("ЭТАП 2. SPATIAL (coordinates + production distance)")

    print("[2.1] Locating SpatialQueryService...", flush=True)
    _sq = _get_spatial_query(_h)
    print(f"[2.1] spatial_query: {type(_sq).__name__ if _sq else 'None'}", flush=True)

    print("[2.2] Reading _npc_positions...", flush=True)
    _positions = _get_npc_positions(_sq)
    print(f"[2.2] _npc_positions keys: {list(_positions.keys())}", flush=True)
    print(f"[2.2] _npc_positions count: {len(_positions)}", flush=True)

    _player_coords = _coords(_positions, "player")
    _tornin_coords = _coords(_positions, "tavern_keeper_tornin")
    print(f"[2.3] player_position: {_player_coords}", flush=True)
    print(f"[2.3] tornin_position: {_tornin_coords}", flush=True)

    _tornin_in_positions = "tavern_keeper_tornin" in _positions
    print(f"[2.4] tornin_in_positions: {_tornin_in_positions}", flush=True)

    if _player_coords and _tornin_coords:
        _euclid = math.hypot(_player_coords[0] - _tornin_coords[0],
                             _player_coords[1] - _tornin_coords[1])
        print(f"[2.5] Euclidean distance (manual): {_euclid:.4f}", flush=True)
    else:
        _euclid = None
        print("[2.5] Euclidean: cannot compute (missing coords)", flush=True)

    _prod_dist = _prod_distance(_sq, "player", "tavern_keeper_tornin")
    print(f"[2.6] Production distance(player, tornin): {_prod_dist}", flush=True)

    # --------------------------------------------------------------------
    # Выбор радиуса: R = production_distance + ε (если distance измерен)
    # --------------------------------------------------------------------
    _EPSILON = 1.0
    if _prod_dist is not None:
        _radius = float(_prod_dist) + _EPSILON
        _radius_source = f"production_distance({float(_prod_dist):.4f}) + epsilon({_EPSILON})"
    elif _euclid is not None:
        _radius = float(_euclid) + _EPSILON
        _radius_source = f"euclidean({float(_euclid):.4f}) + epsilon({_EPSILON}) [PROD DISTANCE UNKNOWN]"
    else:
        _radius = 50.0
        _radius_source = "fallback 50.0 (no distance available — spatial query may be missing)"

    print(f"[2.7] chosen radius: {_radius:.4f}  (source: {_radius_source})", flush=True)

    # --------------------------------------------------------------------
    # ЭТАП 3. EVENT — single PLAYER_INSULTS publication
    # --------------------------------------------------------------------
    _divider("ЭТАП 3. EVENT (single PLAYER_INSULTS publication)")

    print("[3.1] importing EventDTO, get_event_bus, EventType...", flush=True)
    from app.domain.events import EventDTO
    from app.services.events.event_bus import get_event_bus
    from app.services.events.event_types import EventType

    print(f"[3.2] Publishing PLAYER_INSULTS target=tavern_keeper_tornin "
          f"radius={_radius:.4f}...", flush=True)
    _bus = get_event_bus()
    _event = EventDTO.create(
        event_type=EventType.PLAYER_INSULTS.value,
        source="player",
        payload={
            "target_id": "tavern_keeper_tornin",
            "text": "Ты дурак!",
            "action_type": "player_insults",
        },
        visibility="public",
        radius=_radius,
        persistence_level="session",
    )
    print(f"[3.2] event_id: {getattr(_event, 'id', '?')}", flush=True)
    print(f"[3.2] event.type: {getattr(_event, 'type', '?')}", flush=True)

    _bus.publish(_event)
    print("[3.3] EventBus.publish returned (all synchronous subscribers done)", flush=True)

    # --------------------------------------------------------------------
    # ЭТАП 4. EPISTEMIC — immediate EpistemicStore read for Tornin
    # --------------------------------------------------------------------
    _divider("ЭТАП 4. EPISTEMIC (immediate EpistemicStore check)")

    print("[4.1] Reading Tornin's EpistemicStore AFTER publish...", flush=True)
    _post_records = _read_tornin_records(_h)
    print(f"[4.1] Total records post-publish: {len(_post_records)}", flush=True)
    for _i, _r in enumerate(_post_records):
        _d = _describe_record(_r)
        print(f"  #{_i}: subj={_d['subject_id']} pred={_d['predicate']} "
              f"obj={_d['object_id']} pol={_d['polarity']} conf={_d['confidence']} "
              f"src={_d['source_id']} prov={_d['provenance']!r} "
              f"type={_d['record_type']} tick={_d['tick']}", flush=True)

    _post_target = [r for r in _post_records if _is_target_insulted(r)]
    if _post_target:
        _td = _describe_record(_post_target[0])
        print(f"\n[4.2] TARGET BELIEF: PRESENT", flush=True)
        print(f"[4.2]   source_id  = {_td['source_id']!r}", flush=True)
        print(f"[4.2]   predicate  = {_td['predicate']!r}", flush=True)
        print(f"[4.2]   confidence = {_td['confidence']!r}", flush=True)
        print(f"[4.2]   provenance = {_td['provenance']!r}", flush=True)
        print(f"[4.2]   polarity   = {_td['polarity']!r}", flush=True)
        print(f"[4.2]   tick       = {_td['tick']!r}", flush=True)
        _epistemic_present = True
    else:
        print(f"\n[4.2] TARGET BELIEF: ABSENT", flush=True)
        _epistemic_present = False

    # --------------------------------------------------------------------
    # ЭТАП 5. COGNITION — CognitionContextResolver.resolve_block FULL OUTPUT
    # --------------------------------------------------------------------
    _divider("ЭТАП 5. COGNITION (CognitionContextResolver — full block)")

    print("[5.1] Constructing CognitionContextResolver(memory_manager, epistemic_store)...",
          flush=True)
    from app.services.npc.cognition_context import CognitionContextResolver

    _store = _get_epistemic_store(_h)
    _sched = _h.game_loop._get_task_scheduler()
    _mm = getattr(_sched, "_memory_manager", None)
    print(f"[5.1] memory_manager: {type(_mm).__name__ if _mm else 'None'}", flush=True)
    print(f"[5.1] epistemic_store: {type(_store).__name__ if _store else 'None'}", flush=True)

    _resolver = CognitionContextResolver(memory_manager=_mm, epistemic_store=_store)
    print("[5.2] resolve_block('tavern_keeper_tornin', 'player')...", flush=True)
    try:
        _cog_block = _resolver.resolve_block("tavern_keeper_tornin", "player")
    except Exception as _exc:
        _cog_block = f"[ERROR resolve_block raised: {_exc}]"
        import traceback
        traceback.print_exc()

    _cog_len = len(_cog_block) if isinstance(_cog_block, str) else 0
    print(f"[5.3] cognition_block length: {_cog_len}", flush=True)
    print(f"[5.4] cognition_block FULL CONTENT:", flush=True)
    print(f"--- BEGIN COGNITION BLOCK ---", flush=True)
    print(_cog_block if _cog_block else "<empty>", flush=True)
    print(f"--- END COGNITION BLOCK ---", flush=True)

    _cognition_nonempty = _cog_len > 0

    # --------------------------------------------------------------------
    # ЭТАП 6. LIFECYCLE (READ-ONLY inspection — без dispose, без clear)
    # --------------------------------------------------------------------
    _divider("ЭТАП 6. LIFECYCLE (READ-ONLY)")

    _ep = getattr(_sched, "_executor_pool", None)
    _dq = getattr(_sched, "_dialogue_queue", None)
    _dq_pending = None
    if _dq is not None:
        try:
            _dq_pending = _dq.pending_count()
        except Exception:
            _dq_pending = "<no pending_count>"

    _has_unsubscribe = hasattr(_bus, "unsubscribe")
    _has_clear = hasattr(_bus, "clear")
    _subs_attr = None
    for _a in ("_subscribers", "subscribers", "_handlers", "_callbacks"):
        if hasattr(_bus, _a):
            _subs_attr = _a
            break

    _dm = getattr(_h.game_loop, "dm_agent", None)
    _router = getattr(_dm, "router", None) if _dm else None

    print(f"[6.1] task_scheduler._executor_pool: "
          f"{type(_ep).__name__ if _ep else 'None'}, "
          f"max_workers={getattr(_ep, '_max_workers', None) if _ep else None}", flush=True)
    print(f"[6.2] task_scheduler._dialogue_queue.pending_count: {_dq_pending}", flush=True)
    print(f"[6.3] EventBus type: {type(_bus).__name__}", flush=True)
    print(f"[6.4] EventBus has unsubscribe: {_has_unsubscribe}", flush=True)
    print(f"[6.5] EventBus has clear: {_has_clear}", flush=True)
    print(f"[6.6] EventBus subscribers attr: {_subs_attr}", flush=True)
    print(f"[6.7] dm_agent.router type: {type(_router).__name__ if _router else 'None'}",
          flush=True)

    # --------------------------------------------------------------------
    # FINAL VERDICT (raw observations, no interpretation)
    # --------------------------------------------------------------------
    _divider("VERDICT (raw observations, no interpretation)")

    print(f"BASELINE:", flush=True)
    print(f"  target_belief = {'PRESENT' if _baseline_target else 'ABSENT'}", flush=True)

    print(f"SPATIAL:", flush=True)
    print(f"  player_position = {_player_coords}", flush=True)
    print(f"  tornin_position = {_tornin_coords}", flush=True)
    print(f"  euclidean_distance = {_euclid}", flush=True)
    print(f"  production_distance = {_prod_dist}", flush=True)
    print(f"  tornin_in_positions = {_tornin_in_positions}", flush=True)
    print(f"  chosen_radius = {_radius:.4f}  (source: {_radius_source})", flush=True)

    print(f"EVENT:", flush=True)
    print(f"  published = TRUE", flush=True)
    print(f"  event_id = {getattr(_event, 'id', '?')}", flush=True)
    print(f"  radius = {_radius:.4f}", flush=True)

    print(f"EPISTEMIC:", flush=True)
    if _post_target:
        _td = _describe_record(_post_target[0])
        print(f"  target_belief = PRESENT", flush=True)
        print(f"  source_id = {_td['source_id']!r}", flush=True)
        print(f"  predicate = {_td['predicate']!r}", flush=True)
        print(f"  confidence = {_td['confidence']!r}", flush=True)
        print(f"  provenance = {_td['provenance']!r}", flush=True)
        print(f"  polarity = {_td['polarity']!r}", flush=True)
    else:
        print(f"  target_belief = ABSENT", flush=True)

    print(f"COGNITION:", flush=True)
    print(f"  block_length = {_cog_len}", flush=True)
    print(f"  block_nonempty = {_cognition_nonempty}", flush=True)
    print(f"  full_block_above (see section 5.4)", flush=True)

    print(f"\nLIFECYCLE (no dispose called, no clear called):", flush=True)
    print(f"  process will exit via sys.exit(0) — isolation by process boundary",
          flush=True)

    _result = {
        "baseline_target_present": bool(_baseline_target),
        "baseline_records_count": len(_baseline_records),
        "player_coords": _player_coords,
        "tornin_coords": _tornin_coords,
        "euclidean_distance": _euclid,
        "production_distance": _prod_dist,
        "tornin_in_positions": _tornin_in_positions,
        "radius_used": _radius,
        "radius_source": _radius_source,
        "epistemic_target_present": _epistemic_present,
        "epistemic_target_record": _describe_record(_post_target[0]) if _post_target else None,
        "cognition_block_length": _cog_len,
        "cognition_block_nonempty": _cognition_nonempty,
        "event_bus_has_unsubscribe": _has_unsubscribe,
        "router_type": type(_router).__name__ if _router else None,
    }
    return _result


# ============================================================================
# Entry point — отдельный процесс, sys.exit без cleanup
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        _ = run()
        print(f"\n[DONE] smoke test complete; process will exit", flush=True)
        sys.exit(0)
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)

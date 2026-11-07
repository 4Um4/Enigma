# backend/tests/sandbox/p5b_persistence_probe_v7.py
"""
P5-B v7 — финальный probe с правильным именем SQLite таблицы (state_kv).
Дополняет v6: независимо читает SQLite state_kv для epistemic_records.
"""
from __future__ import annotations
import os, sys, json, shutil, sqlite3, tempfile, traceback, time
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.config import settings, BASE_DIR
from app.services.game_loop_builder import build_game_loop
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
from app.domain.events import EventDTO
from app.domain.epistemology import Proposition, Predicate

SPY_LOG: List[Dict[str, Any]] = []

def _stamp(tag: str, **kw: Any) -> None:
    SPY_LOG.append({"tag": tag, **kw})
    print(f"[SPY] {tag}: " + json.dumps(kw, ensure_ascii=False, default=str))

def build_loop(data_dir: Path, saves_dir: Path) -> Any:
    settings.saves_dir = str(saves_dir)
    settings.environment = "development"
    loop = build_game_loop(data_dir=data_dir)
    try:
        ts = loop._get_task_scheduler()  # noqa
        for kind, ex in (getattr(ts, "_executors", {}) or {}).items():
            if hasattr(ex, "_router"):
                ex._router = MagicMock()
                if hasattr(ex._router, "route"):
                    ex._router.route.return_value = "[Test LLM Mock]"
    except Exception: pass
    return loop

def cleanup_loop(loop: Any) -> None:
    try:
        if hasattr(loop, "_task_scheduler"):
            ts = loop._task_scheduler
            if hasattr(ts, "_executor_pool"):
                try: ts._executor_pool.shutdown(wait=False, cancel_futures=True)
                except Exception: pass
    except Exception: pass

def init_scene(loop: Any) -> Dict[str, Any]:
    scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
    if scene is None:
        scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")
    return scene or {}

def attach_spies(loop: Any) -> Dict[str, Any]:
    refs: Dict[str, Any] = {}
    sm = loop.scene_manager
    orig_aca = sm._persistence.atomic_commit_all
    def _spy_aca(campaign_id, all_scenes, npc_states=None, events=None):
        ep_total = 0
        ep_preview = []
        for _lid, ss in (all_scenes or {}).items():
            recs = ss.get("epistemic_records", []) if isinstance(ss, dict) else []
            ep_total += len(recs)
            if recs and len(ep_preview) < 3:
                ep_preview.extend(recs[:3 - len(ep_preview)])
        _stamp("PERSIST.atomic_commit_all:ENTER",
               campaign=campaign_id, scenes_count=len(all_scenes or {}),
               epistemic_records_total=ep_total, epistemic_records_preview=ep_preview)
        result = orig_aca(campaign_id, all_scenes, npc_states, events)
        _stamp("PERSIST.atomic_commit_all:EXIT", result=result)
        return result
    sm._persistence.atomic_commit_all = _spy_aca  # type: ignore
    refs["spa"] = sm._persistence
    return refs

# === Independent SQLite read — CORRECT TABLE NAME: state_kv ===
def read_sqlite_independent(saves_dir: Path, campaign_id: str = "Open_road", location_id: str = "tavern") -> Dict[str, Any]:
    db_path = saves_dir / "enigma_runtime.db"
    if not db_path.exists():
        return {"error": f"DB not found at {db_path}"}
    try:
        # Open NEW connection (independent from adapter's connection)
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        # List tables
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cur.fetchall()]
        # Read state_kv with key scene:campaign:location
        target_key = f"scene:{campaign_id}:{location_id}"
        cur.execute("SELECT key, value, updated_at FROM state_kv WHERE key = ?;", [target_key])
        rows = cur.fetchall()
        result = {
            "db_path": str(db_path),
            "tables": tables,
            "target_key": target_key,
            "state_kv_rows_count": len(rows),
        }
        if rows:
            key, value, updated_at = rows[0]
            try:
                scene_dict = json.loads(value)
                if isinstance(scene_dict, dict):
                    ep_recs = scene_dict.get("epistemic_records", [])
                    result["scene_keys"] = sorted(list(scene_dict.keys()))
                    result["scene_tick"] = scene_dict.get("tick")
                    result["scene_game_time"] = scene_dict.get("game_time_seconds")
                    result["scene_location_id"] = scene_dict.get("location_id")
                    result["scene_campaign_id"] = scene_dict.get("campaign_id")
                    result["epistemic_records_count_in_sqlite"] = len(ep_recs)
                    result["epistemic_records_in_sqlite"] = ep_recs[:5]
                    # Find maid_lusya record specifically
                    maid_lusya_recs = [r for r in ep_recs if r.get("agent_id") == "maid_lusya"]
                    result["maid_lusya_records_count"] = len(maid_lusya_recs)
                    result["maid_lusya_record_in_sqlite"] = maid_lusya_recs[0] if maid_lusya_recs else None
            except Exception as e:
                result["parse_error"] = str(e)[:200]
                result["value_preview"] = value[:300]
        else:
            # Try alternate keys
            cur.execute("SELECT key FROM state_kv;")
            all_keys = [r[0] for r in cur.fetchall()]
            result["all_state_kv_keys"] = all_keys[:20]
        # All distinct keys for completeness
        cur.execute("SELECT key FROM state_kv WHERE key LIKE 'scene:%';")
        scene_keys = [r[0] for r in cur.fetchall()]
        result["all_scene_keys"] = scene_keys
        conn.close()
        return result
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

def snapshot_epistemic_store(loop: Any, agent_id: str = "maid_lusya") -> Dict[str, Any]:
    orch = getattr(loop, "_tick_orch", None)
    orch_store = getattr(orch, "_epistemic_store", None) if orch else None
    if orch_store is None:
        return {"error": "no orch store"}
    records = orch_store.get_all_for_agent(agent_id)
    return {
        "agent_id": agent_id,
        "records_count": len(records),
        "records": [
            {
                "agent_id": r.agent_id,
                "proposition": r.proposition.to_dict(),
                "confidence": r.confidence,
                "source_id": r.source_id,
                "source_claim_id": r.source_claim_id,
                "first_observed_tick": r.first_observed_tick,
                "last_updated_tick": r.last_updated_tick,
                "source_type": r.source_type,
                "original_source_id": r.original_source_id,
            }
            for r in records
        ]
    }

def publish_insult(target_id: str = "maid_lusya"):
    payload = {
        "action_type": "player_insults",
        "target_id": target_id,
        "content": "оскорбление",
        "event_tick": 1,
        "visibility": "public",
        "radius": 999.0,
        "location": "tavern",
        "campaign_id": "Open_road",
        "raw_input": "оскорбление",
    }
    evt = EventDTO.create(
        event_type=EventType.PLAYER_INSULTS,
        source="player",
        payload=payload,
        persistence_level="working",
    )
    _stamp("EVENT.publish", event_id=str(evt.id), target_id=target_id)
    get_event_bus().publish(evt)

def run_scenario(label: str, with_insult: bool, real_data_dir: Path, saves_dir: Path) -> Dict[str, Any]:
    print(f"\n{'#' * 78}\n# SCENARIO {label}: {'WITH' if with_insult else 'NO'} PLAYER_INSULTS\n# saves_dir={saves_dir}\n{'#' * 78}")
    SPY_LOG.clear()
    try: get_event_bus().clear()
    except Exception: pass

    _stamp(f"{label}.A1.clean_startup", saves_dir=str(saves_dir))
    loop1 = build_loop(real_data_dir, saves_dir)
    init_scene(loop1)
    attach_spies(loop1)
    _stamp(f"{label}.A1.epistemic_pre_insult", epistemic=snapshot_epistemic_store(loop1))

    if with_insult:
        publish_insult("maid_lusya")
        _stamp(f"{label}.A2.epistemic_post_insult", epistemic=snapshot_epistemic_store(loop1))
    else:
        _stamp(f"{label}.A2.no_insult", reason="control")

    _stamp(f"{label}.A3.idle_tick:START")
    try:
        result = loop1.idle_tick("Open_road")
        _stamp(f"{label}.A3.idle_tick:EXIT",
               status=result.get("status", "?") if isinstance(result, dict) else type(result).__name__)
    except Exception as e:
        _stamp(f"{label}.A3.idle_tick:ERROR", error=type(e).__name__, msg=str(e)[:300])
        cleanup_loop(loop1)
        return {"spy": list(SPY_LOG), "error": str(e)[:200]}

    _stamp(f"{label}.A3.epistemic_post_idle", epistemic=snapshot_epistemic_store(loop1))

    # Force save with epistemic_records (in case idle_tick doesn't propagate)
    try:
        scene = loop1.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is not None:
            orch = getattr(loop1, "_tick_orch", None)
            orch_store = getattr(orch, "_epistemic_store", None) if orch else None
            if orch_store is not None:
                scene["epistemic_records"] = orch_store.to_dict()
            loop1.scene_manager.save_scene_state("Open_road", scene)
    except Exception as e:
        _stamp(f"{label}.A3_5.save:ERROR", error=str(e)[:200])

    # === Independent SQLite read ===
    sqlite_evidence = read_sqlite_independent(saves_dir)
    _stamp(f"{label}.A3_6.sqlite_evidence", evidence=sqlite_evidence)

    # === Destroy ===
    _stamp(f"{label}.A4.destroy_loop1")
    cleanup_loop(loop1)
    del loop1
    import gc; gc.collect()
    time.sleep(0.5)
    _stamp(f"{label}.A4.destroyed")

    # === Rehydrate via new GameLoop ===
    _stamp(f"{label}.A5.rehydrate:START")
    loop2 = build_loop(real_data_dir, saves_dir)
    init_scene(loop2)
    _stamp(f"{label}.A5.epistemic_rehydrated", epistemic=snapshot_epistemic_store(loop2))

    # Resolver check
    try:
        orch = getattr(loop2, "_tick_orch", None)
        resolver = getattr(orch, "_epistemic_context_resolver", None) if orch else None
        if resolver is not None:
            ctx = resolver.resolve("maid_lusya")
            _stamp(f"{label}.A5_5.resolver_rehydrated",
                   agent_id=ctx.agent_id,
                   perceived_threats=list(ctx.perceived_threats),
                   claims_about_self=[p.to_dict() for p in ctx.claims_about_self],
                   max_self_confidence=ctx.max_self_confidence,
                   report_proposition=ctx.report_proposition.to_dict() if ctx.report_proposition else None)
    except Exception as e:
        _stamp(f"{label}.A5_5.resolver:ERROR", error=str(e)[:200])
    cleanup_loop(loop2)
    del loop2
    gc.collect()

    return {"spy": list(SPY_LOG)}

def main() -> int:
    print("\n" + "=" * 78)
    print("P5-B v7 — SQLite Epistemic Persistence Forensics (correct table: state_kv)")
    print("Baseline: 72cf47b0658ffe8cae6351213ddbfb3b48f2e6d2")
    print("=" * 78)

    real_data_dir = Path(settings.data_dir)
    saves_a = Path(tempfile.mkdtemp(prefix="p5b_v7_A_"))
    saves_b = Path(tempfile.mkdtemp(prefix="p5b_v7_B_"))

    try:
        spy_a = run_scenario("A", with_insult=True, real_data_dir=real_data_dir, saves_dir=saves_a)
        spy_b = run_scenario("B", with_insult=False, real_data_dir=real_data_dir, saves_dir=saves_b)

        print("\n" + "=" * 78)
        print("FORENSIC REPORT — P5-B v7")
        print("=" * 78)
        print("\n--- SCENARIO A (with PLAYER_INSULTS) ---")
        for e in spy_a.get("spy", []):
            print(f"  {e}")
        print("\n--- SCENARIO B (control, no PLAYER_INSULTS) ---")
        for e in spy_b.get("spy", []):
            print(f"  {e}")
        return 0
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1
    finally:
        for d in [saves_a, saves_b]:
            try: shutil.rmtree(d, ignore_errors=True)
            except Exception: pass

if __name__ == "__main__":
    sys.exit(main())
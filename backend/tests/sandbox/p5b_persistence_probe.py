# backend/tests/sandbox/p5b_persistence_probe.py
"""
P5-B — SQLite Epistemic Persistence Forensics.
Полный цикл: PLAYER_INSULTS → EpistemicStore → scene_state → commit_tick_result
            → SQLite → destroy GameLoop → new GameLoop → EpistemicStore rehydration.
A/B control. Независимое чтение SQLite через sqlite3.connect.
"""
from __future__ import annotations
import os, sys, json, shutil, sqlite3, tempfile, traceback, time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
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

# === Build loop with persistent saves_dir (NOT temp) ===
def build_loop(data_dir: Path, saves_dir: Path) -> Any:
    settings.saves_dir = str(saves_dir)
    settings.environment = "development"
    loop = build_game_loop(data_dir=data_dir)
    # Mock LLM router
    try:
        ts = loop._get_task_scheduler()  # noqa
        for kind, ex in (getattr(ts, "_executors", {}) or {}).items():
            if hasattr(ex, "_router"):
                ex._router = MagicMock()
                if hasattr(ex._router, "route"):
                    ex._router.route.return_value = "[Test LLM Mock]"
    except Exception as e:
        _stamp("HARNESS.mock_llm", error=str(e)[:200])
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

# === Attach spies on persistence chain ===
def attach_persistence_spies(loop: Any) -> Dict[str, Any]:
    refs: Dict[str, Any] = {}

    # 1. SceneStateManager.commit_tick_result
    sm = loop.scene_manager
    orig_ctr = sm.commit_tick_result
    def _spy_ctr(campaign_id, result_snapshot):
        ep_in_snap = result_snapshot.get("epistemic_records", []) if isinstance(result_snapshot, dict) else None
        _stamp("PERSIST.commit_tick_result:ENTER",
               campaign=campaign_id,
               tick=result_snapshot.get("tick") if isinstance(result_snapshot, dict) else "?",
               epistemic_records_count=len(ep_in_snap) if ep_in_snap is not None else None,
               epistemic_records_preview=ep_in_snap[:3] if ep_in_snap else [])
        result = orig_ctr(campaign_id, result_snapshot)
        _stamp("PERSIST.commit_tick_result:EXIT")
        return result
    sm.commit_tick_result = _spy_ctr  # type: ignore
    refs["sm"] = sm

    # 2. SceneStateManager.save_scene_state
    orig_sss = sm.save_scene_state
    def _spy_sss(campaign_id, scene_state):
        ep_in_ss = scene_state.get("epistemic_records", []) if isinstance(scene_state, dict) else None
        _stamp("PERSIST.save_scene_state:ENTER",
               campaign=campaign_id,
               tick_locked=getattr(sm, "_tick_locked", None),
               epistemic_records_count=len(ep_in_ss) if ep_in_ss is not None else None)
        result = orig_sss(campaign_id, scene_state)
        _stamp("PERSIST.save_scene_state:EXIT")
        return result
    sm.save_scene_state = _spy_sss  # type: ignore

    # 3. SqlitePersistenceAdapter.atomic_commit / atomic_commit_all
    spa = getattr(sm, "_persistence", None)
    if spa is not None:
        orig_ac = spa.atomic_commit
        def _spy_ac(campaign_id, scene_state, npc_states=None, events=None):
            ep_in_ss = scene_state.get("epistemic_records", []) if isinstance(scene_state, dict) else None
            _stamp("PERSIST.atomic_commit:ENTER",
                   campaign=campaign_id,
                   loc_id=scene_state.get("location_id") if isinstance(scene_state, dict) else "?",
                   epistemic_records_count=len(ep_in_ss) if ep_in_ss is not None else None,
                   epistemic_records_preview=ep_in_ss[:3] if ep_in_ss else [])
            result = orig_ac(campaign_id, scene_state, npc_states, events)
            _stamp("PERSIST.atomic_commit:EXIT", result=result)
            return result
        spa.atomic_commit = _spy_ac  # type: ignore

        orig_aca = spa.atomic_commit_all
        def _spy_aca(campaign_id, all_scenes, npc_states=None, events=None):
            ep_total = 0
            ep_preview = []
            for _lid, ss in (all_scenes or {}).items():
                recs = ss.get("epistemic_records", []) if isinstance(ss, dict) else []
                ep_total += len(recs)
                if recs and len(ep_preview) < 3:
                    ep_preview.extend(recs[:3 - len(ep_preview)])
            _stamp("PERSIST.atomic_commit_all:ENTER",
                   campaign=campaign_id,
                   scenes_count=len(all_scenes or {}),
                   epistemic_records_total=ep_total,
                   epistemic_records_preview=ep_preview)
            result = orig_aca(campaign_id, all_scenes, npc_states, events)
            _stamp("PERSIST.atomic_commit_all:EXIT", result=result)
            return result
        spa.atomic_commit_all = _spy_aca  # type: ignore
        refs["spa"] = spa
    return refs

# === Read SQLite independently ===
def read_sqlite_epistemic_records(saves_dir: Path, campaign_id: str = "Open_road", location_id: str = "tavern") -> Dict[str, Any]:
    db_path = saves_dir / "enigma_runtime.db"
    if not db_path.exists():
        return {"error": f"DB not found at {db_path}"}
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        # Show all tables
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cur.fetchall()]
        # KV-store schema
        cur.execute("SELECT key, value FROM kv_store WHERE key LIKE ?;", [f"scene:{campaign_id}:{location_id}"])
        rows = cur.fetchall()
        result = {
            "db_path": str(db_path),
            "tables": tables,
            "scene_kv_rows_count": len(rows),
        }
        if rows:
            key, value = rows[0]
            try:
                scene_dict = json.loads(value)
                result["scene_keys"] = sorted(list(scene_dict.keys())) if isinstance(scene_dict, dict) else None
                result["epistemic_records_count"] = len(scene_dict.get("epistemic_records", [])) if isinstance(scene_dict, dict) else 0
                result["epistemic_records_preview"] = scene_dict.get("epistemic_records", [])[:5] if isinstance(scene_dict, dict) else None
                result["scene_tick"] = scene_dict.get("tick") if isinstance(scene_dict, dict) else None
                result["scene_game_time"] = scene_dict.get("game_time_seconds") if isinstance(scene_dict, dict) else None
            except Exception as e:
                result["parse_error"] = str(e)[:200]
                result["value_preview"] = value[:300] if isinstance(value, str) else str(value)[:300]
        else:
            # Try alternate keys
            cur.execute("SELECT key FROM kv_store WHERE key LIKE ?;", [f"scene:{campaign_id}%"])
            alt_keys = [r[0] for r in cur.fetchall()]
            result["alternate_scene_keys"] = alt_keys
            cur.execute("SELECT key FROM kv_store;")
            all_keys = [r[0] for r in cur.fetchall()]
            result["all_kv_keys"] = all_keys[:30]
        conn.close()
        return result
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

# === Snapshot EpistemicStore ===
def snapshot_epistemic_store(loop: Any, agent_id: str = "maid_lusya") -> Dict[str, Any]:
    sub = getattr(loop, "_claim_event_subscriber", None)
    if sub is None:
        return {"error": "no subscriber"}
    store = getattr(sub, "_store", None)
    if store is None:
        return {"error": "no store"}
    orch = getattr(loop, "_tick_orch", None)
    orch_store = getattr(orch, "_epistemic_store", None) if orch else None
    # Use orch_store (the canonical one) or fall back to sub._store
    target_store = orch_store if orch_store is not None else store
    records = target_store.get_all_for_agent(agent_id)
    return {
        "agent_id": agent_id,
        "records_count": len(records),
        "records": [
            {
                "agent_id": r.agent_id,
                "proposition": r.proposition.to_dict() if hasattr(r.proposition, "to_dict") else str(r.proposition),
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

# === Snapshot scene_state epistemic_records ===
def snapshot_scene_state_epistemic(loop: Any) -> Dict[str, Any]:
    scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
    if scene is None:
        return {"error": "scene is None"}
    recs = scene.get("epistemic_records", [])
    return {
        "tick": scene.get("tick"),
        "game_time": scene.get("game_time_seconds"),
        "epistemic_records_count": len(recs),
        "epistemic_records_preview": recs[:5],
    }

# === Publish PLAYER_INSULTS ===
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

# === Run scenario ===
def run_scenario(label: str, with_insult: bool, real_data_dir: Path, saves_dir: Path) -> Dict[str, Any]:
    print(f"\n{'#' * 78}\n# SCENARIO {label}: {'WITH' if with_insult else 'NO'} PLAYER_INSULTS\n# saves_dir={saves_dir}\n{'#' * 78}")
    SPY_LOG.clear()
    try: get_event_bus().clear()
    except Exception: pass

    # === A1: clean startup ===
    _stamp(f"{label}.A1.clean_startup", saves_dir=str(saves_dir))
    loop1 = build_loop(real_data_dir, saves_dir)
    init_scene(loop1)
    refs = attach_persistence_spies(loop1)
    _stamp(f"{label}.A1.epistemic_pre_insult", epistemic=snapshot_epistemic_store(loop1))
    _stamp(f"{label}.A1.scene_pre_insult", scene=snapshot_scene_state_epistemic(loop1))

    # === A2: create belief (or skip) ===
    if with_insult:
        publish_insult("maid_lusya")
        _stamp(f"{label}.A2.epistemic_post_insult", epistemic=snapshot_epistemic_store(loop1))
    else:
        _stamp(f"{label}.A2.no_insult", reason="control")

    # === A3: trigger commit pipeline via idle_tick ===
    _stamp(f"{label}.A3.idle_tick:START")
    try:
        result = loop1.idle_tick("Open_road")
        _stamp(f"{label}.A3.idle_tick:EXIT",
               status=result.get("status", "?") if isinstance(result, dict) else type(result).__name__)
    except Exception as e:
        _stamp(f"{label}.A3.idle_tick:ERROR", error=type(e).__name__, msg=str(e)[:300])
        cleanup_loop(loop1)
        return {"spy": list(SPY_LOG), "error": str(e)[:200]}

    # Snapshot scene_state after idle_tick
    _stamp(f"{label}.A3.epistemic_post_idle", epistemic=snapshot_epistemic_store(loop1))
    _stamp(f"{label}.A3.scene_post_idle", scene=snapshot_scene_state_epistemic(loop1))

    # === A3.5: explicit save (in case idle_tick didn't trigger save_scene_state outside lock) ===
    try:
        scene = loop1.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is not None:
            # Get epistemic_records from orch and inject into scene
            orch = getattr(loop1, "_tick_orch", None)
            orch_store = getattr(orch, "_epistemic_store", None) if orch else None
            if orch_store is not None:
                scene["epistemic_records"] = orch_store.to_dict()
            loop1.scene_manager.save_scene_state("Open_road", scene)
            _stamp(f"{label}.A3_5.explicit_save", scene=snapshot_scene_state_epistemic(loop1))
    except Exception as e:
        _stamp(f"{label}.A3_5.explicit_save:ERROR", error=str(e)[:200])

    # === A3.6: Read SQLite independently ===
    sqlite_evidence = read_sqlite_epistemic_records(saves_dir)
    _stamp(f"{label}.A3_6.sqlite_evidence", evidence=sqlite_evidence)

    # === A4: Full destruction of runtime ===
    _stamp(f"{label}.A4.destroy_loop1", reason="no Python object transfer")
    cleanup_loop(loop1)
    del loop1
    import gc; gc.collect()
    time.sleep(0.3)  # ensure sqlite handle released
    _stamp(f"{label}.A4.destroyed")

    # === A5: Rehydration via new GameLoop ===
    _stamp(f"{label}.A5.rehydrate:START", saves_dir=str(saves_dir))
    loop2 = build_loop(real_data_dir, saves_dir)
    init_scene(loop2)
    _stamp(f"{label}.A5.epistemic_rehydrated", epistemic=snapshot_epistemic_store(loop2))

    # === A5.5: Resolver check ===
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
        else:
            _stamp(f"{label}.A5_5.resolver", error="resolver not found")
    except Exception as e:
        _stamp(f"{label}.A5_5.resolver:ERROR", error=str(e)[:200])
    cleanup_loop(loop2)
    del loop2
    gc.collect()

    return {"spy": list(SPY_LOG)}

# === MAIN ===
def main() -> int:
    print("\n" + "=" * 78)
    print("P5-B — SQLite Epistemic Persistence Forensics")
    print("Baseline: 72cf47b0658ffe8cae6351213ddbfb3b48f2e6d2")
    print("=" * 78)
    print(f"DATA_DIR={settings.data_dir}")
    print(f"BASE_DIR={BASE_DIR}")

    real_data_dir = Path(settings.data_dir)
    # Create two separate temp dirs for A and B (independent SQLite DBs)
    saves_a = Path(tempfile.mkdtemp(prefix="p5b_saves_A_"))
    saves_b = Path(tempfile.mkdtemp(prefix="p5b_saves_B_"))

    try:
        # === SCENARIO A ===
        spy_a = run_scenario("A", with_insult=True, real_data_dir=real_data_dir, saves_dir=saves_a)

        # === SCENARIO B ===
        spy_b = run_scenario("B", with_insult=False, real_data_dir=real_data_dir, saves_dir=saves_b)

        # === REPORT ===
        print("\n" + "=" * 78)
        print("FORENSIC REPORT — P5-B")
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
        # Cleanup temp dirs
        for d in [saves_a, saves_b]:
            try: shutil.rmtree(d, ignore_errors=True)
            except Exception: pass

if __name__ == "__main__":
    sys.exit(main())
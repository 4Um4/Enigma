"""F5 Headless Laboratory — USL-2 maid_lusya.

Использует TavernGameplayHarness (production entry point, campaign=Open_road).
Проверяет 4 механизма: EventMemory, Relationship, Belief, Imprints.

Артефакты: artifacts/f5/usl2_maid_lusya/
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

ARTIFACTS_DIR = ROOT / "artifacts" / "f5" / "usl2_maid_lusya"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

NPC_ID = "maid_lusya"
TICKS = 10


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def write_artifact(name: str, data: object) -> None:
    path = ARTIFACTS_DIR / name
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"  [ARTIFACT] {name}")


def snapshot_npc_state(harness, npc_id: str) -> dict:
    """Снимок NPC state из runtime."""
    npc = harness.inspect_npc(npc_id)
    if npc is None:
        return {"error": f"NPC {npc_id} not found"}

    narrative_cache = npc.get("narrative_cache", [])
    relationship_cache = npc.get("relationship_cache", {})
    psyche = npc.get("psyche", {})
    beliefs = psyche.get("beliefs", {})
    affective_imprints = npc.get("affective_imprints", [])

    return {
        "npc_id": npc_id,
        "name": npc.get("name", ""),
        "location_id": npc.get("location_id", ""),
        "stress": npc.get("stress", 0),
        "narrative_cache_count": len(narrative_cache) if narrative_cache else 0,
        "narrative_cache_sample": [
            {
                "day": m.get("day"),
                "summary": str(m.get("summary", ""))[:100],
                "importance": m.get("importance"),
                "tags": m.get("tags", []),
            }
            for m in (narrative_cache or [])[:5]
        ],
        "relationship_cache": {
            k: {"trust": v.get("trust"), "chronicle_origin": v.get("chronicle_origin")}
            for k, v in (relationship_cache or {}).items()
        },
        "psyche_beliefs": beliefs,
        "affective_imprints_count": len(affective_imprints) if affective_imprints else 0,
        "affective_imprints": [
            {
                "trigger_tags": imp.get("trigger_tags"),
                "decay_rate": imp.get("decay_rate"),
                "pain_signature": imp.get("pain_signature"),
            }
            for imp in (affective_imprints or [])
        ],
    }


def main() -> int:
    print(f"[F5] USL-2 maid_lusya Headless Laboratory — {timestamp()}")
    print(f"[F5] Campaign: Open_road (TavernGameplayHarness)")
    print(f"[F5] NPC: {NPC_ID}")
    print(f"[F5] Ticks: {TICKS}")
    print()

    # run_manifest.json
    import subprocess
    commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    manifest = {
        "script": "scripts/f5_usl2_maid_lusya.py",
        "commit_sha": commit_sha,
        "timestamp": timestamp(),
        "campaign_id": "Open_road",
        "npc_id": NPC_ID,
        "ticks": TICKS,
        "harness": "TavernGameplayHarness",
    }
    write_artifact("run_manifest.json", manifest)

    # Импорт harness
    from tests.gameplay.harness import TavernGameplayHarness

    print("[F5] Инициализация TavernGameplayHarness...")
    harness = TavernGameplayHarness(seed=42)
    try:
        harness.new_game()
        print(f"[F5] new_game OK (campaign={harness.campaign_id})")

        # runtime_before.json
        print("[F5] Снимок runtime_before...")
        before = snapshot_npc_state(harness, NPC_ID)
        write_artifact("runtime_before.json", before)
        print(f"  narrative_cache: {before.get('narrative_cache_count', 0)}")
        print(f"  relationship_cache: {list(before.get('relationship_cache', {}).keys())}")
        print(f"  psyche_beliefs: {list(before.get('psyche_beliefs', {}).keys())}")
        print(f"  affective_imprints: {before.get('affective_imprints_count', 0)}")

        # Прогон тиков
        print(f"\n[F5] Прогон {TICKS} idle_ticks...")
        events_log = []
        cognitive_trace = []
        for i in range(TICKS):
            tick_result = harness.game_loop.idle_tick(harness.campaign_id)
            harness.counters.ticks += 1
            scene = harness._scene_after_tick(tick_result)
            if scene:
                harness.counters.observe_scene(scene)
                harness._last_tick_scene = scene

            # Запись события
            event_entry = {
                "tick": i + 1,
                "game_time": scene.get("game_time_seconds") if scene else None,
                "npc_count": len(scene.get("npc_positions", {})) if scene else 0,
                "pending_tasks": len(scene.get("pending_tasks", [])) if scene else 0,
            }
            events_log.append(event_entry)

            # Когнитивный след maid_lusya
            npc_after = snapshot_npc_state(harness, NPC_ID)
            cognitive_trace.append({
                "tick": i + 1,
                "stress": npc_after.get("stress"),
                "narrative_cache_count": npc_after.get("narrative_cache_count"),
                "relationship_cache_keys": list(npc_after.get("relationship_cache", {}).keys()),
            })

        write_artifact("events.jsonl", "\n".join(json.dumps(e, ensure_ascii=False) for e in events_log))
        write_artifact("cognitive_trace.jsonl", "\n".join(json.dumps(c, ensure_ascii=False) for c in cognitive_trace))

        # runtime_after.json
        print(f"\n[F5] Снимок runtime_after...")
        after = snapshot_npc_state(harness, NPC_ID)
        write_artifact("runtime_after.json", after)
        print(f"  narrative_cache: {after.get('narrative_cache_count', 0)}")
        print(f"  relationship_cache: {list(after.get('relationship_cache', {}).keys())}")
        print(f"  psyche_beliefs: {list(after.get('psyche_beliefs', {}).keys())}")
        print(f"  affective_imprints: {after.get('affective_imprints_count', 0)}")

        # Counters
        print(f"\n[F5] Counters:")
        print(f"  ticks: {harness.counters.ticks}")
        print(f"  events_by_type: {harness.counters.events_by_type}")
        print(f"  npc_spoke: {harness.counters.npc_spoke}")
        print(f"  npc_moved: {harness.counters.npc_moved}")

        # Comparison
        comparison = {
            "before": {
                "narrative_cache_count": before.get("narrative_cache_count", 0),
                "relationship_cache_keys": list(before.get("relationship_cache", {}).keys()),
                "psyche_beliefs_keys": list(before.get("psyche_beliefs", {}).keys()),
                "affective_imprints_count": before.get("affective_imprints_count", 0),
                "stress": before.get("stress"),
            },
            "after": {
                "narrative_cache_count": after.get("narrative_cache_count", 0),
                "relationship_cache_keys": list(after.get("relationship_cache", {}).keys()),
                "psyche_beliefs_keys": list(after.get("psyche_beliefs", {}).keys()),
                "affective_imprints_count": after.get("affective_imprints_count", 0),
                "stress": after.get("stress"),
            },
            "delta": {
                "narrative_cache": after.get("narrative_cache_count", 0) - before.get("narrative_cache_count", 0),
                "affective_imprints": after.get("affective_imprints_count", 0) - before.get("affective_imprints_count", 0),
                "stress_delta": (after.get("stress", 0) or 0) - (before.get("stress", 0) or 0),
            },
            "counters": {
                "ticks": harness.counters.ticks,
                "events_by_type": harness.counters.events_by_type,
                "npc_spoke": harness.counters.npc_spoke,
                "npc_moved": harness.counters.npc_moved,
            },
        }
        write_artifact("comparison.json", comparison)

        # F5 статусы
        report = {
            "F5-01_EventMemory": {
                "seed_count": before.get("narrative_cache_count", 0),
                "runtime_available": before.get("narrative_cache_count", 0) > 0,
                "status": "GREEN" if before.get("narrative_cache_count", 0) > 0 else "RED",
                "note": "EventMemory загружены в narrative_cache" if before.get("narrative_cache_count", 0) > 0 else "EventMemory НЕ загружены",
            },
            "F5-02_Relationship": {
                "seed_count": len(before.get("relationship_cache", {})),
                "targets": list(before.get("relationship_cache", {}).keys()),
                "runtime_available": len(before.get("relationship_cache", {})) > 0,
                "status": "GREEN" if len(before.get("relationship_cache", {})) > 0 else "RED",
                "note": "Relationships загружены" if before.get("relationship_cache") else "Relationships НЕ загружены",
            },
            "F5-03_Belief": {
                "seed_count": len(before.get("psyche_beliefs", {})),
                "types": list(before.get("psyche_beliefs", {}).keys()),
                "runtime_available": len(before.get("psyche_beliefs", {})) > 0,
                "status": "GREEN" if len(before.get("psyche_beliefs", {})) > 0 else "RED",
                "note": "Beliefs загружены в psyche" if before.get("psyche_beliefs") else "Beliefs НЕ загружены в psyche",
            },
            "F5-04_Imprints": {
                "seed_count": before.get("affective_imprints_count", 0),
                "runtime_available": before.get("affective_imprints_count", 0) > 0,
                "status": "GREEN" if before.get("affective_imprints_count", 0) > 0 else "RED",
                "note": "Imprints загружены" if before.get("affective_imprints_count", 0) > 0 else "Imprints НЕ загружены",
            },
        }
        write_artifact("f5_status.json", report)

        print(f"\n[F5] ИТОГ:")
        for k, v in report.items():
            print(f"  {k}: {v['status']} ({v['note']})")

    finally:
        harness.dispose()
        print("\n[F5] Harness disposed.")

    print(f"\n[F5] Артефакты: {ARTIFACTS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

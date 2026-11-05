"""S415.2 A/B v9: Biography -> Memory -> Fear -> Decision -> Action -> Movement -> World State.

Проверяемая причинная цепочка:
  BIOGRAPHY -> MEMORY -> FEAR -> DECISION -> ACTION -> MOVEMENT -> WORLD STATE

Игрок не участвует. Никаких THREATEN, ручных intent/action, искусственных fear/trust.
Биография — единственное различие между A и B.

Методология (от Мастера):
- Если A не убежит от Торнина, это не повод подгонять тест.
- Установить, на каком звене причинная цепочка перестала работать.
- Не закрывать USL-2 только на основании различия intent.
- Требуется доказать прохождение до WORLD STATE.

Археология (probe v4): load_npcs_merged() даёт правильный narrative_cache
(10 EVENT entries, 4 с target_id: tornin x2, orm x2). MEM-1 работает в static path.

Открытое (probe v3): harness.inspect_npc() после idle_tick видит canon secrets
(не EVENT entries). Если runtime persistence перезаписывает narrative_cache —
эксперимент останавливается с диагностическим отчётом.
"""
import json
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# ── Конфигурация ────────────────────────────────────────────────────────────

N_TICKS = 10  # 10 idle ticks (быстрее; ~20-50 сек); можно увеличить до 30
SEED = 42
TARGET_NPC = "maid_lusya"
THREAT_NPC = "tavern_keeper_tornin"

# Monkeypatch targets (4) — ТЗ S415_HANDOFF §2
_PATCH_TARGETS: List[Tuple[str, Callable]] = [
    ("build_seed_memories", lambda npc_id, doc: ()),
    ("build_seed_relationships", lambda npc_id, doc: {}),
    ("build_seed_imprints", lambda doc: []),
    ("build_seed_beliefs", lambda doc: {}),
]


# ── Data classes ────────────────────────────────────────────────────────────

@dataclass
class VariantResult:
    variant: str
    pre_flight_static: Dict[str, Any] = field(default_factory=dict)
    pre_flight_runtime: Dict[str, Any] = field(default_factory=dict)
    post_tick_runtime: Dict[str, Any] = field(default_factory=dict)
    ticks_run: int = 0
    decisions: List[Dict] = field(default_factory=list)
    movement_intents: List[Dict] = field(default_factory=list)
    scene_changes: List[Dict] = field(default_factory=list)
    positions: Dict[str, List[Tuple[float, float]]] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    monkeypatch_active: bool = False


# ── Snapshots (read-only) ───────────────────────────────────────────────────

def _snapshot_npc_dict(npc: Optional[dict]) -> Dict[str, Any]:
    """Read-only snapshot of NPC dict (from inspect_npc or load_npcs_merged)."""
    if not npc:
        return {"present": False}
    _cache = npc.get("narrative_cache", []) or []
    _psyche = npc.get("psyche", {}) or {}
    _beliefs = _psyche.get("beliefs", {})
    _rc = npc.get("relationship_cache", {}) or {}
    return {
        "present": True,
        "narrative_cache_count": len(_cache),
        "narrative_cache_target_ids": [
            (m.get("target_id", "") if isinstance(m, dict) else getattr(m, "target_id", ""))
            for m in _cache
        ],
        "narrative_cache_types": [
            (m.get("_memory_type", "?") if isinstance(m, dict) else type(m).__name__)
            for m in _cache
        ],
        "narrative_cache_is_secret_flags": [
            (m.get("is_secret", False) if isinstance(m, dict) else getattr(m, "is_secret", False))
            for m in _cache
        ],
        "psyche_beliefs_keys": list(_beliefs.keys()) if isinstance(_beliefs, dict) else [],
        "affective_imprints_count": len(npc.get("affective_imprints", []) or []),
        "relationship_cache": {
            k: {"trust": v.get("trust"), "fear": v.get("fear"), "chronicle_origin": v.get("chronicle_origin")}
            for k, v in _rc.items() if isinstance(v, dict)
        },
        "stress": _psyche.get("stress", 0),
        "local_position": str(npc.get("local_position", (0.0, 0.0)))[:100],
    }


def _snapshot_load_npcs_merged(target_npc: str = TARGET_NPC) -> Dict[str, Any]:
    """Static path snapshot via load_npcs_merged() — НЕ runtime."""
    from app.services.npc.npc_loader import load_npcs_merged
    npcs = load_npcs_merged()
    for n in npcs:
        _id = n.get("id") or n.get("npc_id")
        if _id == target_npc:
            return _snapshot_npc_dict(n)
    return {"present": False, "error": f"{target_npc} not found in load_npcs_merged"}


def _snapshot_runtime(harness, target_npc: str = TARGET_NPC) -> Dict[str, Any]:
    """Runtime snapshot via harness.inspect_npc — LifeEngine cache after idle_tick."""
    npc = harness.inspect_npc(target_npc)
    return _snapshot_npc_dict(npc)


# ── Monkeypatch lifecycle ───────────────────────────────────────────────────

def _install_monkeypatch() -> Callable[[], None]:
    """Install chronicle_seeder stubs (4 targets). Returns restore callable."""
    from app.services.chronicle import chronicle_seeder
    originals: Dict[str, Callable] = {}
    for name, stub in _PATCH_TARGETS:
        originals[name] = getattr(chronicle_seeder, name)
        setattr(chronicle_seeder, name, stub)

    def restore() -> None:
        for name, orig in originals.items():
            setattr(chronicle_seeder, name, orig)

    return restore


# ── Capture hooks (observation taps) ────────────────────────────────────────

def _install_capture_hooks(harness, result: VariantResult) -> Callable[[], None]:
    """Install observation taps on NpcTickPipeline.run and MovementEngine.process_intents.
    Hooks НЕ меняют возвращаемые значения, аргументы, поведение — только наблюдают."""
    restores: List[Callable] = []

    # Hook 1: NpcTickPipeline.run -> capture movement_intents + npc_deltas
    try:
        from app.services.npc.npc_tick_pipeline import NpcTickPipeline
        _orig_run = NpcTickPipeline.run

        def _hooked_run(*args, **kwargs):
            _mutation = _orig_run(*args, **kwargs)
            try:
                _ints = getattr(_mutation, "movement_intents", []) or []
                _deltas = getattr(_mutation, "npc_deltas", []) or []
                for _mi in _ints:
                    _npc_id = getattr(_mi, "npc_id", "?")
                    _intent = getattr(_mi, "intent", "?")
                    _target = getattr(_mi, "target_id", "") or getattr(_mi, "target_node_id", "")
                    result.movement_intents.append({
                        "tick": result.ticks_run,
                        "npc_id": _npc_id,
                        "intent": str(_intent),
                        "target": str(_target),
                    })
                for _d in _deltas:
                    if hasattr(_d, "npc_id") and (getattr(_d, "npc_id", "") == TARGET_NPC or TARGET_NPC in str(getattr(_d, "npc_id", ""))):
                        result.decisions.append({
                            "tick": result.ticks_run,
                            "npc_id": getattr(_d, "npc_id", "?"),
                            "intent": str(getattr(_d, "intent", "")),
                            "delta_keys": list(getattr(_d, "deltas", {}).keys()) if hasattr(_d, "deltas") else [],
                        })
            except Exception as _e:
                result.errors.append(f"capture_hook_run: {_e}")
            return _mutation

        NpcTickPipeline.run = _hooked_run
        restores.append(lambda: setattr(NpcTickPipeline, "run", _orig_run))
    except Exception as _e:
        result.errors.append(f"install_hook_pipeline: {_e}")

    # Hook 2: MovementEngine.process_intents -> capture SceneChange
    try:
        from app.services.spatial.movement_engine import MovementEngine
        _orig_pi = MovementEngine.process_intents

        def _hooked_pi(self, *args, **kwargs):
            _changes = _orig_pi(self, *args, **kwargs)
            try:
                for _ch in (_changes or []):
                    _target = getattr(_ch, "target", "") or ""
                    if _target == TARGET_NPC or TARGET_NPC in str(_target):
                        _field = getattr(_ch, "field", "")
                        _new = getattr(_ch, "new_value", None)
                        _cause = getattr(_ch, "cause", "")
                        result.scene_changes.append({
                            "tick": result.ticks_run,
                            "target": str(_target),
                            "field": str(_field),
                            "new_value": str(_new)[:100] if _new else "",
                            "cause": str(_cause),
                        })
            except Exception as _e:
                result.errors.append(f"capture_hook_pi: {_e}")
            return _changes

        MovementEngine.process_intents = _hooked_pi
        restores.append(lambda: setattr(MovementEngine, "process_intents", _orig_pi))
    except Exception as _e:
        result.errors.append(f"install_hook_engine: {_e}")

    def restore_all() -> None:
        for r in restores:
            try:
                r()
            except Exception:
                pass

    return restore_all


# ── Distance computation ────────────────────────────────────────────────────

def _distance(p1: Any, p2: Any) -> float:
    if not p1 or not p2:
        return 0.0
    try:
        if isinstance(p1, dict):
            x1, y1 = float(p1.get("x", 0)), float(p1.get("y", 0))
        elif isinstance(p1, (list, tuple)):
            x1, y1 = float(p1[0]), float(p1[1])
        else:
            return 0.0
        if isinstance(p2, dict):
            x2, y2 = float(p2.get("x", 0)), float(p2.get("y", 0))
        elif isinstance(p2, (list, tuple)):
            x2, y2 = float(p2[0]), float(p2[1])
        else:
            return 0.0
        return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)
    except (TypeError, ValueError, IndexError, KeyError):
        return 0.0


def _total_distance(positions: List[Tuple[float, float]]) -> float:
    if len(positions) < 2:
        return 0.0
    return sum(_distance(positions[i], positions[i + 1]) for i in range(len(positions) - 1))


# ── Run variant ─────────────────────────────────────────────────────────────

def run_variant(variant: str, n_ticks: int = N_TICKS) -> VariantResult:
    """Run A (bio) or B (control) variant."""
    from tests.gameplay.harness import TavernGameplayHarness

    result = VariantResult(variant=variant)
    restore_patch: Optional[Callable] = None
    restore_hooks: Optional[Callable] = None
    harness: Optional[TavernGameplayHarness] = None

    try:
        # 1. Install monkeypatch (B only) — ДО создания harness
        if variant == "B":
            restore_patch = _install_monkeypatch()
            result.monkeypatch_active = True
            print(f"  [Variant {variant}] monkeypatch installed (4 chronicle_seeder stubs)")

        # 2. Create harness + new_game — патчи активны во время new_game
        print(f"  [Variant {variant}] creating harness + new_game...")
        harness = TavernGameplayHarness(seed=SEED)
        harness.new_game()

        # 3. Pre-flight: static path (load_npcs_merged) — НЕ runtime
        print(f"  [Variant {variant}] pre-flight: load_npcs_merged snapshot")
        result.pre_flight_static = _snapshot_load_npcs_merged()

        # 4. Pre-flight: runtime (inspect_npc) — после new_game, до ticks
        print(f"  [Variant {variant}] pre-flight: runtime snapshot (after new_game)")
        result.pre_flight_runtime = _snapshot_runtime(harness)

        # 5. Install capture hooks — observation taps
        restore_hooks = _install_capture_hooks(harness, result)

        # 6. Capture initial positions
        for _n in harness.game_loop._resolve_npcs_snapshot(harness.campaign_id) or []:
            _id = _n.get("id") or _n.get("npc_id", "?")
            _pos = _n.get("local_position", (0.0, 0.0))
            result.positions[_id] = [_pos]

        # 7. Run idle ticks
        print(f"  [Variant {variant}] running {n_ticks} idle ticks...")
        for i in range(n_ticks):
            try:
                harness.game_loop.idle_tick(harness.campaign_id)
                result.ticks_run += 1
                # Capture positions after each tick
                for _n in harness.game_loop._resolve_npcs_snapshot(harness.campaign_id) or []:
                    _id = _n.get("id") or _n.get("npc_id", "?")
                    _pos = _n.get("local_position", (0.0, 0.0))
                    if _id not in result.positions:
                        result.positions[_id] = []
                    result.positions[_id].append(_pos)
            except Exception as _e:
                result.errors.append(f"tick_{i}: {type(_e).__name__}: {_e}")
                break

        # 8. Post-tick runtime snapshot
        print(f"  [Variant {variant}] post-tick runtime snapshot")
        result.post_tick_runtime = _snapshot_runtime(harness)

    except Exception as _e:
        result.errors.append(f"run_variant: {type(_e).__name__}: {_e}")
    finally:
        # 9. Dispose harness FIRST, then restore hooks, then restore patch
        if harness:
            try:
                harness.dispose()
            except Exception as _e:
                result.errors.append(f"dispose: {_e}")
        if restore_hooks:
            restore_hooks()
        if restore_patch:
            restore_patch()
            print(f"  [Variant {variant}] monkeypatch restored")

    return result


# ── Verdict ─────────────────────────────────────────────────────────────────

def _verdict_link(name: str, a_val: Any, b_val: Any, expected_diff: bool) -> Dict:
    """Verdict для одного звена цепочки."""
    has_diff = a_val != b_val
    if expected_diff:
        status = "PASS" if has_diff else "FAIL_NO_DIFF"
    else:
        status = "PASS" if not has_diff else "WARN_UNEXPECTED_DIFF"
    return {
        "link": name,
        "A": a_val,
        "B": b_val,
        "expected_diff": expected_diff,
        "has_diff": has_diff,
        "status": status,
    }


def compute_verdict(a: VariantResult, b: VariantResult) -> Dict[str, Any]:
    """Verdict по каждому звену причинной цепочки."""
    links = []

    # BIOGRAPHY -> MEMORY: narrative_cache_count (static path)
    a_nc = a.pre_flight_static.get("narrative_cache_count", 0)
    b_nc = b.pre_flight_static.get("narrative_cache_count", 0)
    links.append(_verdict_link("BIOGRAPHY->MEMORY (static)", a_nc, b_nc, expected_diff=True))

    # MEM-1: target_id в static path
    a_tids = a.pre_flight_static.get("narrative_cache_target_ids", [])
    b_tids = b.pre_flight_static.get("narrative_cache_target_ids", [])
    a_tornin = [t for t in a_tids if t == THREAT_NPC]
    b_tornin = [t for t in b_tids if t == THREAT_NPC]
    links.append(_verdict_link(
        "MEM-1 target_id (tornin, static)",
        f"{len(a_tornin)} entries", f"{len(b_tornin)} entries",
        expected_diff=True,
    ))

    # MEMORY -> FEAR: trust/fear(Tornin) в relationship_cache
    a_rc = a.pre_flight_static.get("relationship_cache", {}).get(THREAT_NPC, {})
    b_rc = b.pre_flight_static.get("relationship_cache", {}).get(THREAT_NPC, {})
    a_trust = a_rc.get("trust")
    b_trust = b_rc.get("trust")
    links.append(_verdict_link("MEMORY->FEAR (trust tornin, static)", a_trust, b_trust, expected_diff=True))

    # Runtime persistence check: не перезаписывает ли narrative_cache?
    a_rt_nc = a.pre_flight_runtime.get("narrative_cache_count", 0)
    a_rt_types = a.pre_flight_runtime.get("narrative_cache_types", [])
    a_rt_event_count = sum(1 for t in a_rt_types if "EventMemory" in str(t))
    persistence_check = {
        "static_count": a_nc,
        "runtime_count": a_rt_nc,
        "runtime_event_count": a_rt_event_count,
        "runtime_types_sample": a_rt_types[:5],
        "status": "PASS" if a_rt_nc >= a_nc else "WARN_RUNTIME_LOST_MEMORY",
    }

    # DECISION: movement_intents для TARGET_NPC
    a_intents = [mi for mi in a.movement_intents if mi.get("npc_id") == TARGET_NPC]
    b_intents = [mi for mi in b.movement_intents if mi.get("npc_id") == TARGET_NPC]
    links.append(_verdict_link(
        "DECISION (movement_intents count)",
        len(a_intents), len(b_intents), expected_diff=True,
    ))

    # ACTION -> MOVEMENT: scene_changes для TARGET_NPC
    a_changes = [sc for sc in a.scene_changes if TARGET_NPC in sc.get("target", "")]
    b_changes = [sc for sc in b.scene_changes if TARGET_NPC in sc.get("target", "")]
    links.append(_verdict_link(
        "ACTION->MOVEMENT (scene_changes)",
        len(a_changes), len(b_changes), expected_diff=True,
    ))

    # MOVEMENT -> WORLD STATE: total distance
    a_dist = _total_distance(a.positions.get(TARGET_NPC, []))
    b_dist = _total_distance(b.positions.get(TARGET_NPC, []))
    links.append(_verdict_link(
        "MOVEMENT->WORLD_STATE (total distance)",
        round(a_dist, 3), round(b_dist, 3), expected_diff=True,
    ))

    # USL-2 verdict
    all_pass = all(link["status"].startswith("PASS") for link in links if link["expected_diff"])
    usl2 = "CLOSED" if all_pass and a_dist > 0 else "OPEN"

    return {
        "links": links,
        "persistence_check": persistence_check,
        "usl2_verdict": usl2,
        "A_intents": a_intents,
        "B_intents": b_intents,
        "A_scene_changes": a_changes,
        "B_scene_changes": b_changes,
        "A_total_distance": round(a_dist, 3),
        "B_total_distance": round(b_dist, 3),
        "A_errors": a.errors,
        "B_errors": b.errors,
    }


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("S415.2 A/B v9: Biography -> Memory -> Behavior")
    print("=" * 70)

    t0 = time.time()

    # Variant A (bio enabled)
    print("\n--- Variant A: Chronicle biography ENABLED ---")
    result_a = run_variant("A", n_ticks=N_TICKS)

    # Variant B (control: bio disabled via monkeypatch)
    print("\n--- Variant B: Chronicle biography DISABLED (monkeypatch) ---")
    result_b = run_variant("B", n_ticks=N_TICKS)

    # Verdict
    print("\n--- Verdict ---")
    verdict = compute_verdict(result_a, result_b)

    for link in verdict["links"]:
        print(f"  {link['link']}: A={link['A']}, B={link['B']} -> {link['status']}")

    print(f"\n  Persistence check: {verdict['persistence_check']['status']}")
    print(f"  USL-2 verdict: {verdict['usl2_verdict']}")
    print(f"  A total distance: {verdict['A_total_distance']}")
    print(f"  B total distance: {verdict['B_total_distance']}")

    if verdict["A_errors"]:
        print(f"  A errors: {verdict['A_errors']}")
    if verdict["B_errors"]:
        print(f"  B errors: {verdict['B_errors']}")

    # Write report
    report = {
        "experiment": "S415.2 A/B v9",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "config": {
            "n_ticks": N_TICKS,
            "seed": SEED,
            "target_npc": TARGET_NPC,
            "threat_npc": THREAT_NPC,
        },
        "A": {
            "variant": result_a.variant,
            "monkeypatch_active": result_a.monkeypatch_active,
            "pre_flight_static": result_a.pre_flight_static,
            "pre_flight_runtime": result_a.pre_flight_runtime,
            "post_tick_runtime": result_a.post_tick_runtime,
            "ticks_run": result_a.ticks_run,
            "movement_intents_count": len(result_a.movement_intents),
            "scene_changes_count": len(result_a.scene_changes),
            "positions": {k: [list(p) for p in v] for k, v in result_a.positions.items()},
            "movement_intents": result_a.movement_intents,
            "scene_changes": result_a.scene_changes,
            "errors": result_a.errors,
        },
        "B": {
            "variant": result_b.variant,
            "monkeypatch_active": result_b.monkeypatch_active,
            "pre_flight_static": result_b.pre_flight_static,
            "pre_flight_runtime": result_b.pre_flight_runtime,
            "post_tick_runtime": result_b.post_tick_runtime,
            "ticks_run": result_b.ticks_run,
            "movement_intents_count": len(result_b.movement_intents),
            "scene_changes_count": len(result_b.scene_changes),
            "positions": {k: [list(p) for p in v] for k, v in result_b.positions.items()},
            "movement_intents": result_b.movement_intents,
            "scene_changes": result_b.scene_changes,
            "errors": result_b.errors,
        },
        "verdict": verdict,
        "elapsed_seconds": round(time.time() - t0, 1),
    }

    report_path = ROOT / "reports" / "S415_2_AB_V9_REPORT.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nReport: {report_path}")
    print(f"Elapsed: {report['elapsed_seconds']}s")


if __name__ == "__main__":
    main()
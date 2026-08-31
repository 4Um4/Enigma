"""
path: scripts/w3_shadow_simple.py
Назначение: GORAN beta G1 (ADR-O-373) — упрощённый A/B/C-контур.
    Прецедент scripts/test_sleep_routing.py: фабрика build_game_loop()
    + публичный idle_tick(). Изоляция профилей — отдельные ПРОЦЕССЫ
    (свежие синглтоны/кэши на каждый прогон) + свежий temp-saves.
    Родитель запускает три дочерних процесса (A/OFF, B/ON, C/OFF-
    control), каждый пишет JSON-профиль; родитель сравнивает.
    Ось сравнения: финальные позиции NPC / real_errors / traversals /
    commitment-терминалы / crash / world_objects (sanity: 18 в таверне
    = спавнер отработал в production-контуре).
Запуск: python scripts/w3_shadow_simple.py  (из корня, под venv)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TICKS = 200
CAMPAIGN = "Open_road"
LOCATION = "tavern"


def run_child(tag: str) -> None:
    """Один профиль в чистом процессе: fresh temp-saves → 200 тиков → JSON."""
    import logging
    logging.getLogger().setLevel(logging.ERROR)  # ambient-шум долой; суть — в JSON

    from app.services.game_loop_builder import build_game_loop

    os.chdir(ROOT)
    tmp = Path(tempfile.mkdtemp(prefix=f"w3g1_{tag}_"))
    saves = tmp / "saves"
    (saves / "locations").mkdir(parents=True, exist_ok=True)
    # Прецедент test_sleep_routing: кампания в saves + S-142 templates-копия
    shutil.copytree(
        ROOT / "frontend/map_editor/campaigns/Open_road", saves / "Open_road")
    shutil.copy2(
        ROOT / "backend/data/locations/location_templates.json",
        saves / "locations/location_templates.json")

    profile = {"tag": tag, "crash": None, "real_errors": 0, "first_error": None}
    try:
        loop = build_game_loop(data_dir=saves)
        ticks_trav = 0
        for _ in range(1, TICKS + 1):
            try:
                loop.idle_tick(CAMPAIGN)
            except Exception as e:  # real crash — считаем, не глотаем
                profile["real_errors"] += 1
                if not profile["first_error"]:
                    profile["first_error"] = f"{type(e).__name__}: {e}"
            _scene = loop.scene_manager.get_scene_state(CAMPAIGN, LOCATION) or {}
            if _scene.get("active_traversals"):
                ticks_trav += 1

        scene = loop.scene_manager.get_scene_state(CAMPAIGN, LOCATION) or {}
        positions = {}
        for nid, p in (scene.get("npc_positions") or {}).items():
            lp = p.get("local_position") or {}
            positions[nid] = [
                round(float(lp.get("x", 0.0)), 2),
                round(float(lp.get("y", 0.0)), 2),
            ]
        if not positions:
            profile["crash"] = "scene init failed (npc_positions пуст)"
        terminals = [
            t for bucket in (scene.get("commitment_history") or {}).values()
            for t in bucket
        ]
        profile.update({
            "positions": positions,
            "ticks_with_traversals": ticks_trav,
            "terminals_total": len(terminals),
            "status_counts": dict(Counter(t.get("status") for t in terminals)),
            "world_objects": len(scene.get("world_objects") or {}),
        })
    except Exception as e:
        profile["crash"] = f"{type(e).__name__}: {e}"
    finally:
        out = ROOT / "reports" / f"w3g1_{tag}.json"
        out.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
        shutil.rmtree(tmp, ignore_errors=True)


def compare(a: dict, b: dict) -> list:
    diffs = []
    for key in ("crash", "real_errors", "ticks_with_traversals",
                "terminals_total", "status_counts", "world_objects"):
        if a.get(key) != b.get(key):
            diffs.append(f"{key}: {a.get(key)!r} vs {b.get(key)!r}")
    pa, pb = a.get("positions") or {}, b.get("positions") or {}
    if set(pa) != set(pb):
        diffs.append(f"NPC_SET: {sorted(set(pa) ^ set(pb))}")
    else:
        for nid in sorted(pa):
            if pa[nid] != pb[nid]:
                diffs.append(f"POSITION[{nid}]: {pa[nid]} vs {pb[nid]}")
    return diffs


def main() -> int:
    print(f"[W3_SIMPLE] GORAN beta G1: {TICKS} ticks x3 (A/B/C, процесс-изоляция)")
    results = {}
    profiles = (("A", False), ("B", True), ("C", False))
    for rep in range(2, int(os.environ.get("W3_G1_REPS", "0")) + 1):
        # Вердикт (a) Мастера: 2-3 A/B-пары. rep>=2 — суффиксные имена,
        # файлы реплик не затирают baseline A/B/C.
        for tag, shadow in (("A", False), ("B", True)):
            profiles = profiles + ((f"{tag}{rep}", shadow),)
    for tag, shadow in profiles:
        env = dict(os.environ)
        env.pop("W3_SHADOW_ENABLED", None)
        if shadow:
            env["W3_SHADOW_ENABLED"] = "1"
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), tag],
            env=env, capture_output=True, text=True, cwd=str(ROOT))
        results[tag] = json.loads(
            (ROOT / "reports" / f"w3g1_{tag}.json").read_text(encoding="utf-8"))
        r = results[tag]
        print(f"[W3_SIMPLE] {tag}: crash={r['crash']} errors={r['real_errors']} "
              f"npcs={len(r.get('positions') or {})} "
              f"world_objects={r.get('world_objects')}")
        if proc.returncode != 0:
            print(f"  child stderr tail: {proc.stderr[-400:]}")

    invalid = [t for t in ("A", "B", "C") if results[t]["crash"]]
    if invalid:
        print(f"[W3_SIMPLE] VERDICT: INVALID RUN — crash в {invalid}")
        return 2
    diffs_ab = compare(results["A"], results["B"])
    diffs_ac = compare(results["A"], results["C"])
    print(f"[W3_SIMPLE] DIFF(A|B)={len(diffs_ab)} DIFF(A|C)={len(diffs_ac)}")
    for d in diffs_ab:
        print(f"  AB - {d}")
    for d in diffs_ac:
        print(f"  AC - {d}")
    # (a)-критерий: повторные A/B-пары; теневые диффы обязаны
    # оставаться в пределах фонового диапазона (AC — baseline диапазона;
    # Ax|Ay повторные OFF-пары — вторая точка диапазона, если запущены)
    _ambient_scale = len(diffs_ac) or 1
    for rep in range(2, 10):
        _a_key, _b_key = f"A{rep}", f"B{rep}"
        if _a_key in results and _b_key in results:
            _d = compare(results[_a_key], results[_b_key])
            print(f"[W3_SIMPLE] DIFF({_a_key}|{_b_key})={len(_d)}")
            for _x in _d:
                print(f"  A{rep}B{rep} - {_x}")
    if not diffs_ab:
        print("[W3_SIMPLE] VERDICT: GREEN — тень невидима для поведения")
        return 0
    if not diffs_ac:
        print("[W3_SIMPLE] VERDICT: RED — дрейф коррелирует с тенью; стоп")
        return 1
    print("[W3_SIMPLE] VERDICT: INCONCLUSIVE-AMBIENT — фонов дрейф (A≠C); Мастеру")
    return 3


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "backend"))
    if len(sys.argv) > 1:          # дочерний режим: один профиль
        run_child(sys.argv[1])
    else:                          # родитель: три профиля + сравнение
        sys.exit(main())
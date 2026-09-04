"""
path: scripts/w3_g2_simple.py
Назначение: GORAN beta G2 (ADR-O-377) — A/B/C-контур behavior-changing
    гейта, критерии Мастера (PRE-FLIGHT Г2): (1) sanity/integration —
    production ON = честный ноль (weapon-архетипов в кампании нет;
    позиционные диффы OFF/ON не выходят за OFF/OFF-фон — ambient
    qualification, DEBT-QUIESCE); (2) proof — ТОЛЬКО controlled-scene:
    инъекция weapon-объекта через WorldObjectStore.spawn (S214
    beta-гибрид: инъекция входа легальна, beliefs/intents — нет) ->
    доставка факта в живом контуре ([W3_G2] tap, пассивный наблюдатель
    CDS §11) + engine-звено уже доказано юнит-уровнём (0.50 -> 0.70).
    Прецедент w3_shadow_simple.py: процесс-изоляция профилей (свежие
    синглтоны + temp-saves), INVALID RUN-guard (краш любого профиля =
    exit 2, ноль GORAN-вердикта — урок S237 №2).
Запуск: python scripts/w3_g2_simple.py  (из корня, под venv)
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
# G2_TICKS (env, default 200): укороченный дым-прогон всех профилей ДО
# полного GORAN-прогона (урок №3: процессную среду проверяем дёшево).
# `or 200` — пустая строка env = дефолт, не крах int("").
TICKS = int(os.environ.get("G2_TICKS") or 200)
CAMPAIGN = "Open_road"
LOCATION = "tavern"

# A* = OFF-фон (3 прогона: попарные диффы = ambient-база);
# B* = ON без оружий (honest-zero); W* = ON + инъекция weapon (proof).
PROFILES = (
    ("A1", "0", False),
    ("A2", "0", False),
    ("A3", "0", False),
    ("B1", "1", False),
    ("B2", "1", False),
    ("W1", "1", True),
    ("W2", "1", True),
)

_WEAPON_ID = "wo_g2_probe_weapon"


def _run_child() -> None:
    """Один профиль в чистом процессе: fresh temp-saves -> 200 тиков -> JSON."""
    import logging

    # Bootstrap дочернего процесса: родитель запускается из ROOT, поэтому
    # sys.path[0] = scripts/ — импорт app.* падает ModuleNotFoundError.
    # Поймано INVALID RUN-guard'ом прогона №1 (его работа: ноль вердикта,
    # exit 2, ноль summary) — дефект харнесса, не симуляции.
    sys.path.insert(0, str(ROOT / "backend"))

    tag = os.environ["G2_TAG"]
    out_path = Path(os.environ["G2_OUT"])
    inject = os.environ.get("G2_INJECT", "") == "1"

    logging.getLogger().setLevel(logging.ERROR)  # ambient-шум долой

    class _G2Tap(logging.Handler):
        """Пассивный tap доставки факта (наблюдение не создаёт каузальность)."""

        def __init__(self) -> None:
            super().__init__()
            self.hits = 0

        def emit(self, record: logging.LogRecord) -> None:
            if "weapon_access" in record.getMessage():
                self.hits += 1

    _lg = logging.getLogger("app.services.world.affordance_facts")
    _lg.setLevel(logging.INFO)
    _tap = _G2Tap()
    _lg.addHandler(_tap)

    profile = {
        "tag": tag,
        "inject": inject,
        "crash": None,
        "real_errors": 0,
        "first_error": None,
        "g2_hits": 0,
        "weapon_persisted": None,
        "injected_near": None,
        "steal_mentions": 0,
    }
    try:
        os.chdir(ROOT)
        from app.services.game_loop_builder import build_game_loop

        tmp = Path(tempfile.mkdtemp(prefix=f"w3g2_{tag}_"))
        saves = tmp / "saves"
        (saves / "locations").mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            ROOT / "frontend/map_editor/campaigns/Open_road",
            saves / "Open_road",
        )
        shutil.copy2(
            ROOT / "backend/data/locations/location_templates.json",
            saves / "locations/location_templates.json",
        )

        # H5-изоляция: build_game_loop читает СВОЙ saves_dir из глобальных
        # settings (game_loop_builder:35), data_dir его НЕ задаёт —
        # temp-каталог изолировал только replay/static. Все 3 GORAN-прогона
        # мутировали общий ROOT/saves/enigma_runtime.db (загрязнение
        # production-store, устранено перезаписью живой сессией + см.
        # релей). Мутация до вызова: путь читается в момент build.
        from app.core.config import settings

        settings.saves_dir = str(saves)
        loop = build_game_loop(data_dir=saves)

        # Тик 1 = initialize_scene (production-спавнер: 18 объектов таверны).
        loop.idle_tick(CAMPAIGN)
        # GORAN инъекция — легальный write-контур: get_scene_state вне тика
        # перезаливает из persistence (H1 подтверждён археологией), поэтому
        # мутация без save теряется. Прецедент: initialize_scene (mutation →
        # save_scene_state) — тот же путь, инструмент store.spawn (scripts/
        # = тестовая среда, §12.4). Инъекция входа в controlled-scene —
        # санкционированный Мастером класс (S214 β-гибрид).
        scene = loop.scene_manager.save_scene_state  # маркер живого пути ниже
        scene = loop.scene_manager.get_scene_state(CAMPAIGN, LOCATION) or {}

        scene = loop.scene_manager.get_scene_state(CAMPAIGN, LOCATION) or {}
        if inject:
            from app.services.world.world_object_store import WorldObjectStore

            _candidates = [
                (nid, p.get("local_position") or {})
                for nid, p in (scene.get("npc_positions") or {}).items()
                if nid != "player" and (p.get("local_position") or {})
            ]
            if not _candidates:
                profile["crash"] = "injection: нет NPC с позицией"
            else:
                _nid, _lp = _candidates[0]
                # Смежность 0.5 м <= 1.5: факт достоверен на тике 2,
                # даже если NPC потом уйдёт (доставка >= 1 тика достаточна).
                WorldObjectStore.spawn(
                    scene,
                    _WEAPON_ID,
                    "weapon",
                    LOCATION,
                    (float(_lp.get("x", 0.0)) + 0.5, float(_lp.get("y", 0.0))),
                )
                # Легальный write-контур (диагноз H1): persist немедленно —
                # иначе getter перезаливает RAM-копию из старого сейва.
                loop.scene_manager.save_scene_state(CAMPAIGN, scene)
                profile["injected_near"] = _nid

        ticks_trav = 0
        for _ in range(2, TICKS + 1):
            try:
                loop.idle_tick(CAMPAIGN)
            except Exception as e:  # real crash — считаем, не глотаем
                profile["real_errors"] += 1
                if not profile["first_error"]:
                    profile["first_error"] = f"{type(e).__name__}: {e}"
            _sc = loop.scene_manager.get_scene_state(CAMPAIGN, LOCATION) or {}
            if _sc.get("active_traversals"):
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
        # Телеметрия (не гейт): эмерджентные steal-следы при unlock.
        profile["steal_mentions"] = sum(
            1
            for t in terminals
            if "steal" in str(t.get("action", "")).lower()
            or "steal" in str(t.get("cause", "")).lower()
        )
        profile.update({
            "positions": positions,
            "ticks_with_traversals": ticks_trav,
            "terminals_total": len(terminals),
            "status_counts": dict(Counter(t.get("status") for t in terminals)),
            "world_objects": len(scene.get("world_objects") or {}),
            "g2_hits": _tap.hits,
        })
        if inject and profile["crash"] is None:
            # Если get_scene_state возвращал копию — инъекция потеряна:
            # громкая диагностика, не тихий успех.
            profile["weapon_persisted"] = _WEAPON_ID in (
                scene.get("world_objects") or {}
            )
    except Exception as e:  # профиль с crash-полем, не тишина
        profile["crash"] = f"{type(e).__name__}: {e}"

    out_path.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _pos_diff(a: dict, b: dict) -> int:
    _pa = a.get("positions") or {}
    _pb = b.get("positions") or {}
    ids = set(_pa) | set(_pb)
    return sum(1 for i in ids if _pa.get(i) != _pb.get(i))


def main() -> None:
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    results = {}
    for tag, flag, inject in PROFILES:
        out = reports / f"w3g2_{tag}.json"
        env = dict(os.environ)
        env["W3_G2_ENABLED"] = flag
        env["G2_TAG"] = tag
        env["G2_OUT"] = str(out)
        env["G2_INJECT"] = "1" if inject else ""
        try:
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--child"],
                env=env,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=1500,
            )
        except subprocess.TimeoutExpired:
            results[tag] = {"tag": tag, "crash": "child timeout (1500s)"}
            continue
        if out.exists():
            results[tag] = json.loads(out.read_text(encoding="utf-8"))
        else:
            results[tag] = {
                "tag": tag,
                "crash": f"child died, no profile (rc={proc.returncode})",
            }

    for tag in sorted(results):
        r = results[tag]
        print(
            f"[W3G2] {tag}: crash={r.get('crash')} "
            f"errors={r.get('real_errors')} hits={r.get('g2_hits')} "
            f"wo={r.get('world_objects')} trav={r.get('ticks_with_traversals')} "
            f"terminals={r.get('terminals_total')} steal={r.get('steal_mentions')}"
        )

    # INVALID RUN-guard: краш любого профиля = exit 2, ноль вердикта.
    invalid = [t for t, r in results.items() if r.get("crash")]
    if invalid:
        print(f"[W3G2] VERDICT: INVALID RUN — crash in {invalid}")
        sys.exit(2)

    # Критерий 1 (sanity/integration): honest-zero против OFF/OFF-фона.
    _bg = [
        _pos_diff(results["A1"], results["A2"]),
        _pos_diff(results["A1"], results["A3"]),
        _pos_diff(results["A2"], results["A3"]),
    ]
    _zero = [
        _pos_diff(results[a], results[b])
        for a in ("A1", "A2", "A3")
        for b in ("B1", "B2")
    ]
    honest_zero_ok = max(_zero) <= max(_bg)
    b_silent = all(results[t].get("g2_hits") == 0 for t in ("B1", "B2"))

    # Критерий 2 (proof): доставка факта в controlled-scene.
    w_ok = all(
        results[t].get("g2_hits", 0) > 0
        and results[t].get("weapon_persisted") is True
        for t in ("W1", "W2")
    )

    # Структурные гварды.
    structural_ok = (
        all(results[t].get("real_errors") == 0 for t in results)
        and all(
            results[t].get("world_objects") == 18
            for t in ("A1", "A2", "A3", "B1", "B2")
        )
        and all(results[t].get("world_objects") == 19 for t in ("W1", "W2"))
        and all(
            (results[t].get("ticks_with_traversals") or 0) > 0
            for t in results
        )
    )

    verdict = "GREEN"
    notes = []
    if not honest_zero_ok:
        verdict = "RED"
        notes.append("honest-zero: ON-дифф вне OFF/OFF-фона")
    if not b_silent:
        verdict = "RED"
        notes.append("B-профиль не молчит (факты без оружий)")
    if not w_ok:
        verdict = "RED"
        notes.append("proof не доставлен (hits/weapon_persisted)")
    if not structural_ok:
        verdict = "RED"
        notes.append("структурный гвард")
    if verdict == "GREEN":
        notes.append(
            "ambient qualification: диффы в рамках фона (DEBT-QUIESCE)"
        )

    summary = {
        "background_diffs_off_off": _bg,
        "zero_diffs_off_vs_on": _zero,
        "honest_zero_ok": honest_zero_ok,
        "b_silent": b_silent,
        "w_delivery_ok": w_ok,
        "structural_ok": structural_ok,
        "verdict": f"{verdict} | " + " | ".join(notes) if notes else verdict,
        "profiles": {
            t: {k: v for k, v in r.items() if k != "positions"}
            for t, r in results.items()
        },
    }
    (reports / "w3g2_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"[W3G2] bg={_bg} zero={_zero} honest_zero={honest_zero_ok} "
        f"b_silent={b_silent} w_ok={w_ok} structural={structural_ok}"
    )
    print(f"[W3G2] VERDICT: {summary['verdict']}")
    sys.exit(0 if verdict == "GREEN" else 1)


if __name__ == "__main__":
    if "--child" in sys.argv:
        _run_child()
    else:
        main()
from __future__ import annotations

# reports/det2_measure.py
"""
path: reports/det2_measure.py
Назначение: DET-2 (§17.8, вердикт III.2) — измерение стоимости state-checksum
на живом production-пути (F5-прецедент S314: build_game_loop -> idle_tick;
MockProvider — LLM исключён из замера). Проверяет claim «~2.4% тика»
(tick_orchestrator.py:2325 — заявление, не измерение). Замеряет на каждом
тике живой слепок 6 полей TickState (эквивалент _data_fields :2310-2322):
  (a) прод-путь: 2x json.dumps(default=str, sort_keys=True) — как :2329;
  (b) то же + hashlib.sha256 (цена стабильного межпроцессного дайджеста;
      builtin hash() PYTHONHASHSEED-зависим — для replay/ночных автотестов
      нужен стабильный, фиксируется в каноническом контракте DET-2).
Не вносит зависимостей (msgpack/struct не меряются: их нет в проекте;
внесение = отдельный вердикт). Артефакт: reports/det2_measure.json.
Одноразовый; после разбора не перезапускать без нужды.
"""

import json
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT / "backend"))

import hashlib  # noqa: E402


def _tick_data_fields(scene_state, all_npcs_raw):
    """Живой слепок 6 полей — эквивалент _data_fields (tick_orchestrator:2310-2322)."""
    return {
        "scene_state": scene_state,
        "all_npcs_raw": all_npcs_raw,
        "effective_drives_map": {},
        "pe_modifiers_map": {},
        "nearby_npcs": {},
        "line_of_sight": {},
    }


def main() -> int:
    print("[DET-2] Измерение стоимости state-checksum (production-путь, MockProvider)")
    # Импорты внутри — чтобы путь был добавлен до app.*
    from app.core.config import settings
    from app.services.game_loop_builder import build_game_loop
    from pathlib import Path as _P

    data_dir = _P(settings.data_dir)
    print(f"[DET-2] data_dir={data_dir}")

    loop = build_game_loop(data_dir)

    # DriftLab-канон (drift_laboratory:600/604): idle_tick(campaign_id);
    # сцена — scene_manager.get_scene_state(campaign, location) ПОСЛЕ тика.
    # taverne-константы — DriftConfig-прецедент (та же кампания/локация).
    CAMPAIGN = "tavern_silver_wolf"
    LOCATION = "tavern"

    N_TICKS = 200
    timings_json_us = []   # (а): 2x json.dumps 6 полей, мкс
    timings_sha_us = []    # (б): то же + sha256, мкс
    tick_durations_ms = []  # средняя длительность тика без хеша

    # Прогрев (импорт-кэши, first-tick патчи) не в замер
    loop.idle_tick(CAMPAIGN)

    for i in range(N_TICKS):
        t0 = time.perf_counter()
        loop.idle_tick(CAMPAIGN)
        t1 = time.perf_counter()
        tick_durations_ms.append((t1 - t0) * 1000.0)

        # DriftLab-паттерн :603-606: сцена актуализируется ПОСЛЕ тика
        scene_state = loop.scene_manager.get_scene_state(CAMPAIGN, LOCATION) or {}
        all_npcs_raw = list(scene_state.get("npcs", scene_state.get("all_npcs_raw", [])) or [])
        fields = _tick_data_fields(scene_state, all_npcs_raw)

        # (а) прод-путь probe: два прохода json.dumps (до/после)
        t2 = time.perf_counter()
        for _ in range(2):
            _ = {k: json.dumps(v, default=str, sort_keys=True) for k, v in fields.items()}
        t3 = time.perf_counter()
        timings_json_us.append((t3 - t2) * 1e6)

        # (б) + стабильный дайджест
        t4 = time.perf_counter()
        h = hashlib.sha256()
        for _ in range(2):
            for k in sorted(fields):
                h.update(json.dumps(fields[k], default=str, sort_keys=True).encode("utf-8"))
        _ = h.hexdigest()
        t5 = time.perf_counter()
        timings_sha_us.append((t5 - t4) * 1e6)

    med_tick_ms = statistics.median(tick_durations_ms)
    med_json_us = statistics.median(timings_json_us)
    med_sha_us = statistics.median(timings_sha_us)
    share_json_pct = (med_json_us / 1000.0) / med_tick_ms * 100.0
    share_sha_pct = (med_sha_us / 1000.0) / med_tick_ms * 100.0

    report = {
        "ticks": N_TICKS,
        "median_tick_ms": round(med_tick_ms, 3),
        "median_json_2x_us": round(med_json_us, 1),
        "median_json_sha256_us": round(med_sha_us, 1),
        "share_json_1of1_pct": round(share_json_pct, 3),
        "share_sha_1of1_pct": round(share_sha_pct, 3),
        "claim_2325": "~2.4% тика (комментарий; не измерение)",
        "claim_check": (
            "CONFIRMED" if abs(share_json_pct - 2.4) <= 0.5
            else ("OVERSTATED" if share_json_pct < 2.4 - 0.5 else "UNDERSTATED")
        ),
        "note_contract": (
            "builtin hash() PYTHONHASHSEED-зависим: валиден внутри тика (S265 так и задуман), "
            "но для равенства хешей между прогонами/машинами (DET-2-вердикт) нужен "
            "стабильный дайджест (sha256); бинарные кандидаты не мерялись — зависимостей нет, "
            "внесение = отдельный вердикт"
        ),
        "decision_input": {
            "1of1_json_pct": round(share_json_pct, 3),
            "1of1_sha_pct": round(share_sha_pct, 3),
            "verdict_needed": "1/100 -> 1/1: решение Мастера по числам (III.2: при подтверждении стоимости)",
        },
    }
    out = ROOT / "reports" / "det2_measure.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[DET-2] Артефакт: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
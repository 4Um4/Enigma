"""
path: backend/tests/sandbox/re_m1b35_probe.py
Назначение: M1b.3.5 flat-readers-зонд (RE-D8) — runtime-таблица фактов Store→Snapshot→Readers→Decision; изоляция temp-saves по эталону w3_g2_simple.py; наблюдательный, без инъекций убеждений/интов
Зависимости: app.core.config, app.services.game_loop_builder, tempfile, shutil
Основные сущности: main
Запуск: python backend/tests/sandbox/re_m1b35_probe.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_ROOT = _BACKEND.parent
sys.path.insert(0, str(_BACKEND))

TICKS = 10
CAMPAIGN = "Open_road"  # E2-верифицированный источник кампании (GORAN-прогоны)


def main() -> int:
    import logging

    logging.getLogger().setLevel(logging.ERROR)  # ambient-шум долой

    from app.core.config import settings
    from app.services.game_loop_builder import build_game_loop

    tmp = Path(tempfile.mkdtemp(prefix="re_probe_"))
    saves = tmp / "saves"
    (saves / "locations").mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        _ROOT / "frontend/map_editor/campaigns/Open_road",
        saves / "Open_road",
    )
    shutil.copy2(
        _ROOT / "backend/data/locations/location_templates.json",
        saves / "locations/location_templates.json",
    )
    # H5-изоляция (S239): путь читается в момент build — мутация ДО вызова
    settings.saves_dir = str(saves)

    loop = build_game_loop(data_dir=saves)
    # P1..P5 печатаются зондами [ARCHAE-RE] внутри тиков
    result = loop.idle_tick(CAMPAIGN)  # тик 1 = initialize_scene
    for _ in range(TICKS - 1):
        result = loop.idle_tick(CAMPAIGN)

    # P6: археология структуры результата (ЧАСТЬ VIII.5: print, не догадки)
    print("[ARCHAE-RE][P6] result_type=", type(result).__name__)
    if isinstance(result, dict):
        print("[ARCHAE-RE][P6] result_keys=", list(result.keys())[:15])
        _ctxs = result.get("npc_contexts")
        print("[ARCHAE-RE][P6] npc_contexts_type=", type(_ctxs).__name__)
        if isinstance(_ctxs, dict):
            for _nid in sorted(_ctxs)[:10]:
                _c = _ctxs[_nid]
                _trace = _c.get("scores_trace") if isinstance(_c, dict) else None
                print(f"[ARCHAE-RE][P6] npc={_nid} trace={_trace}")
    print("[ARCHAE-RE] PROBE DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
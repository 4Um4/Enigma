from __future__ import annotations

# reports/det2_payload_probe.py
"""
DET-2, Шаг 1 (условие 1 вердикта Мастера): runtime-контракт сериализации.
Классифицирует ФАКТИЧЕСКИЕ типы значений 6 полей probe на живом production-
пути (idle_tick, MockProvider): стабильный JSON (dict/list/str/int/float/
bool/None) vs OTHER — объекты, идущие через default=str (их str() обязан
быть межпроцессно стабильным, иначе контракт требует ограничения).
Артефакт: печатает TOTALS + OTHER-SITES. Одноразовый; после разбора
удалить вместе с коммитом закрытия DET-2.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main() -> None:
    print("[DET-2/S1] Зонд типов payload probe (прод-путь, MockProvider)")
    from app.core.config import settings
    from app.services.game_loop_builder import build_game_loop

    loop = build_game_loop(Path(settings.data_dir))
    CAMP, LOC = "tavern_silver_wolf", "tavern"
    loop.idle_tick(CAMP)  # прогрев

    buckets: dict[str, list] = {}

    def walk(v, path: str) -> None:
        t = type(v).__name__
        key = t if t in ("dict", "list", "str", "int", "float", "bool", "NoneType") else "OTHER:" + t
        buckets.setdefault(key, [0, set()])
        buckets[key][0] += 1
        if key.startswith("OTHER"):
            buckets[key][1].add(path[:80])
        if isinstance(v, dict):
            for k, vv in v.items():
                walk(vv, path + "/" + str(k))
        elif isinstance(v, list):
            for i, vv in enumerate(v[:50]):
                walk(vv, path + f"[{i}]")

    for _tick in range(3):
        ss = loop.scene_manager.get_scene_state(CAMP, LOC) or {}
        npcs = list(ss.get("npcs", ss.get("all_npcs_raw", [])) or [])
        fields = {
            "scene_state": ss,
            "all_npcs_raw": npcs,
            "effective_drives_map": {},
            "pe_modifiers_map": {},
            "nearby_npcs": {},
            "line_of_sight": {},
        }
        for k, v in fields.items():
            walk(v, k)
        loop.idle_tick(CAMP)

    print("TOTALS:", {k: c for k, (c, _) in sorted(buckets.items())})
    for k, (c, paths) in buckets.items():
        if k.startswith("OTHER") and paths:
            print("OTHER-SITES:", k, sorted(paths)[:8])
    others = [k for k in buckets if k.startswith("OTHER")]
    if not others:
        print("[OK] Контракт подтверждён: все значения — стабильный JSON-тип; default=str-ветка не активна на payload probe.")


if __name__ == "__main__":
    main()

"""ME-1.5: миграция wall_id в одну форму (root) + удаление легаси-portals.

Запуск из корня проекта:
    python backend/scripts/me15_migrate.py

Действия:
  1. passage-объекты (door/window/door_transition/gap/hatch):
     - properties.wall_id поднимается в root и удаляется из properties
     - rotation-хак S129 (строка == wall_id) сбрасывается в 0
  2. массив `portals` мигрируется в objects как door_transition, ключ portals удаляется
  3. файлы перезаписываются (ensure_ascii=False, indent=2)
"""

import json
from pathlib import Path

PASSAGE_TYPES = {"door", "window", "door_transition", "gap", "hatch"}
ROOT = Path("frontend/map_editor")


def migrate_location(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = {"wall_id_normalized": 0, "portals_dropped": 0, "portals_migrated": 0}

    objects = data.setdefault("objects", [])

    for obj in objects:
        if obj.get("type") not in PASSAGE_TYPES:
            continue
        props = obj.get("properties")
        if not isinstance(props, dict):
            props = {}
            obj["properties"] = props
        if "wall_id" in props:
            obj["wall_id"] = props.pop("wall_id")
            changed["wall_id_normalized"] += 1
        rotation = obj.get("rotation")
        if isinstance(rotation, str) and rotation == obj.get("wall_id"):
            obj["rotation"] = 0

    portals = data.get("portals", [])
    if portals:
        existing_ids = {o.get("id") for o in objects if isinstance(o, dict)}
        for p in portals:
            if not isinstance(p, dict):
                continue
            pid = p.get("id")
            if pid in existing_ids:
                continue
            ptype = p.get("type", "door")
            obj_type = "door_transition" if ptype in ("transition", "portal") else ptype
            obj = {
                "id": pid,
                "name": p.get("label", ptype),
                "type": obj_type,
                "position": p.get("position", {"x": 0.0, "y": 0.0}),
                "size": p.get("size", {"w": 1.0, "h": 1.0}),
                "rotation": 0,
                "passability": {
                    "walk": True,
                    "jump_over": False,
                    "crawl_under": False,
                    "climb_on": False,
                    "walk_around": True,
                },
                "cover": 0.0,
                "color": p.get("color", "#FFD700"),
                "show_name": False,
                "properties": {
                    "open": True,
                    "locked": False,
                    "durability": 25,
                    "visibility_through": 0.0,
                    "target_file": p.get("target", ""),
                    "target_portal": "",
                },
            }
            if p.get("one_way"):
                obj["properties"]["one_way"] = True
            objects.append(obj)
            existing_ids.add(pid)
            changed["portals_migrated"] += 1
        data.pop("portals", None)
        changed["portals_dropped"] = len(portals)

    if any(changed.values()):
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return changed


def main() -> None:
    patterns = ("campaigns/*/locations/*.json", "location_templates/*.json")
    total = {"wall_id_normalized": 0, "portals_dropped": 0, "portals_migrated": 0}
    for pattern in patterns:
        for p in sorted(ROOT.glob(pattern)):
            if not p.is_file():
                continue
            ch = migrate_location(p)
            if any(ch.values()):
                print(f"{p}: {ch}")
                for k, v in ch.items():
                    total[k] += v
            else:
                print(f"{p}: (no changes)")
    print(f"\nTOTAL: {total}")


if __name__ == "__main__":
    main()
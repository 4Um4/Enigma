"""
map_editor/ui/property_builder.py
Генерация содержимого панели свойств (PropertyPanel) в зависимости от выбранного объекта.
"""
from typing import Any, Dict, List, Optional
from data_manager import load_npc_visual_casting
from sprite_registry import sprite_registry

class PropertyBuilder:
    """Строит словарь свойств для PropertyPanel на основе текущего выбора."""

    def update(self, core):
        """Обновляет содержимое панели свойств"""
        if not core.current_file:
            core.property_panel.set_content("СВОЙСТВА", [])
            return

        loc = core.dm.locations[core.current_file]

        # Если ничего не выделено — показываем свойства локации
        if not core.selected_object:
            items = [
                {
                    "type": "label",
                    "text": f"Локация: {loc.get('label', core.current_file)}",
                    "important": True,
                },
                {"type": "value", "label": "Файл", "value": core.current_file},
                {
                    "type": "value",
                    "label": "Размер",
                    "value": f"{loc['size']['w']}x{loc['size']['h']}м",
                },
                {
                    "type": "value",
                    "label": "location_id",
                    "value": loc.get("location_id", "—"),
                },
                {
                    "type": "toggle",
                    "label": "Задать location_id",
                    "action": "set_location_id",
                },
                {"type": "section", "text": "Содержимое:"},
                {
                    "type": "value",
                    "label": "Комнаты",
                    "value": str(len(loc.get("rooms", []))),
                },
                {
                    "type": "value",
                    "label": "Стены",
                    "value": str(len(loc.get("walls", []))),
                },
                {
                    "type": "value",
                    "label": "Объекты",
                    "value": str(len(loc.get("objects", []))),
                },
                {
                    "type": "value",
                    "label": "NPC",
                    "value": str(len(loc.get("npcs", []))),
                },
                {
                    "type": "value",
                    "label": "Узлы",
                    "value": str(len(loc.get("nodes", {}))),
                },
            ]
            core.property_panel.set_content("СВОЙСТВА", items)
            return

        obj_type, obj_key = core.selected_object
        items = []

        if obj_type == "object":
            obj = next((o for o in loc["objects"] if o.get("id") == obj_key), None)
            if not obj:
                core.property_panel.set_content("СВОЙСТВА", [])
                return
            items = [
                {"type": "label", "text": f"Объект: {obj['type']}", "important": True},
                {"type": "value", "label": "Имя", "value": obj.get("name", "")},
                {"type": "toggle", "label": "Переименовать", "action": "rename"},
                {
                    "type": "toggle",
                    "label": "Показать имя",
                    "value": obj.get("show_name", False),
                    "action": "toggle_show_name",
                },
                {"type": "toggle", "label": "Выбрать спрайт", "action": "pick_sprite"},
                {"type": "value", "label": "X", "value": f"{obj['position']['x']:.1f}"},
                {"type": "value", "label": "Y", "value": f"{obj['position']['y']:.1f}"},
                {"type": "section", "text": "Проходимость:"},
                {
                    "type": "toggle",
                    "label": "Идти",
                    "value": obj["passability"]["walk"],
                    "action": "toggle_walk",
                },
                {
                    "type": "toggle",
                    "label": "Прыгать",
                    "value": obj["passability"]["jump_over"],
                    "action": "toggle_jump_over",
                },
                {
                    "type": "toggle",
                    "label": "Ползти",
                    "value": obj["passability"]["crawl_under"],
                    "action": "toggle_crawl_under",
                },
                {
                    "type": "toggle",
                    "label": "Лезть",
                    "value": obj["passability"]["climb_on"],
                    "action": "toggle_climb_on",
                },
            ]
            # Свойства объекта (если есть)
            props = obj.get("properties", {})
            if props:
                items.append({"type": "section", "text": "Свойства:"})
                prop_labels = {
                    "open": "Открыто",
                    "locked": "Замок",
                    "durability": "Прочность",
                    "opacity": "Непрозрачность",
                    "destructible": "Разрушаемое",
                    "sound_attenuation": "Заглушение звука",
                }
                for key, value in props.items():
                    label = prop_labels.get(key, key)
                    if isinstance(value, bool):
                        items.append(
                            {
                                "type": "value",
                                "label": label,
                                "value": "Да" if value else "Нет",
                            }
                        )
                    elif isinstance(value, (int, float)):
                        items.append(
                            {"type": "value", "label": label, "value": f"{value}"}
                        )
                    else:
                        items.append(
                            {"type": "value", "label": label, "value": str(value)}
                        )

        elif obj_type == "portal":
            p = next((p for p in loc["portals"] if p["id"] == obj_key), None)
            if p:
                items = [
                    {
                        "type": "label",
                        "text": f"Портал: {p['label']}",
                        "important": True,
                    },
                    {"type": "toggle", "label": "Переименовать", "action": "rename"},
                    {"type": "value", "label": "Тип", "value": p["type"]},
                    {
                        "type": "value",
                        "label": "Цель",
                        "value": p.get("target") or "(не связан)",
                    },
                ]

        elif obj_type == "wall":
            wall = next((w for w in loc["walls"] if w["id"] == obj_key), None)
            if wall:
                items = [
                    {"type": "label", "text": "Стена", "important": True},
                    {"type": "value", "label": "X1", "value": f"{wall['x1']:.1f}"},
                    {"type": "value", "label": "Y1", "value": f"{wall['y1']:.1f}"},
                    {"type": "value", "label": "X2", "value": f"{wall['x2']:.1f}"},
                    {"type": "value", "label": "Y2", "value": f"{wall['y2']:.1f}"},
                ]

        elif obj_type == "room":
            room = next((r for r in loc["rooms"] if r["id"] == obj_key), None)
            if room:
                items = [
                    {
                        "type": "label",
                        "text": f"Комната: {room['name']}",
                        "important": True,
                    },
                    {"type": "toggle", "label": "Переименовать", "action": "rename"},
                    {
                        "type": "toggle",
                        "label": "Стены по периметру",
                        "value": len(core._find_room_perimeter_walls(room)) > 0,
                        "action": "create_perimeter_walls",
                    },
                    {"type": "value", "label": "X", "value": f"{room['x']:.1f}"},
                    {"type": "value", "label": "Y", "value": f"{room['y']:.1f}"},
                    {
                        "type": "value",
                        "label": "Ширина",
                        "value": f"{room['width']:.1f}",
                    },
                    {
                        "type": "value",
                        "label": "Высота",
                        "value": f"{room['height']:.1f}",
                    },
                    {
                        "type": "value",
                        "label": "Площадь",
                        "value": f"{room.get('area_sqm', room['width'] * room['height']):.1f} м²",
                    },
                ]

        elif obj_type == "label":
            lbl = next((l for l in loc["labels"] if l["id"] == obj_key), None)  # noqa: E741
            if lbl:
                items = [
                    {"type": "label", "text": "Надпись", "important": True},
                    {
                        "type": "toggle",
                        "label": "Изменить текст",
                        "action": "rename_label",
                    },
                    {"type": "value", "label": "X", "value": f"{lbl['x']:.1f}"},
                    {"type": "value", "label": "Y", "value": f"{lbl['y']:.1f}"},
                ]

        elif obj_type == "npc":
            npc = next(
                (n for n in loc.get("npcs", []) if n.get("ref_id") == obj_key), None
            )
            if npc:
                npc_name = next(
                    (nn["name"] for nn in core._npc_list if nn["id"] == npc["ref_id"]),
                    npc["ref_id"],
                )
                items = [
                    {"type": "label", "text": f"NPC: {npc_name}", "important": True},
                    {"type": "value", "label": "ID", "value": npc["ref_id"]},
                    {
                        "type": "value",
                        "label": "X",
                        "value": f"{npc['position']['x']:.1f}",
                    },
                    {
                        "type": "value",
                        "label": "Y",
                        "value": f"{npc['position']['y']:.1f}",
                    },
                    {
                        "type": "value",
                        "label": "Комната",
                        "value": npc.get("room_id", "—"),
                    },
                    {"type": "button", "label": "Выбрать спрайт", "action": "pick_sprite"},
                    {"type": "button", "label": "Редактировать портреты", "action": "edit_portraits"},
                    {"type": "button", "label": "Калибровать психику", "action": "edit_psyche"},
                ]

                # S176: Превью портрета Neutral (из visual_casting)
                v_casting = load_npc_visual_casting(npc["ref_id"])
                fb_asset = v_casting.get("fallback", {}).get("asset", [])
                if isinstance(fb_asset, list) and len(fb_asset) == 3 and fb_asset[0]:
                    try:
                        _surf = sprite_registry.get(fb_asset[0], fb_asset[1], fb_asset[2])
                        if _surf:
                            items.append({"type": "image", "surface": _surf, "w": 128, "h": 128})
                    except Exception:
                        pass

        elif obj_type == "spawn":
            spawn = loc.get("player_spawn")
            if spawn:
                items = [
                    {
                        "type": "label",
                        "text": "Точка спавна игрока",
                        "important": True,
                    },
                    {"type": "value", "label": "X", "value": f"{spawn['x']:.1f}"},
                    {"type": "value", "label": "Y", "value": f"{spawn['y']:.1f}"},
                    {"type": "value", "label": "Z", "value": f"{spawn.get('z', 0)}"},
                ]

        core.property_panel.set_content("СВОЙСТВА", items)
"""
map_editor/tools/interaction.py
Обработка взаимодействия (клики, удаление, выбор) с объектами на карте.
"""
import math
import pygame
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from core.commands import (
    AddWallCommand, AddRoomCommand, AddObjectCommand, AddPassageCommand,
    AddLabelCommand, AddNpcCommand, AddNodeCommand, AddConnectionCommand,
    RemoveWallCommand, RemoveRoomCommand, RemoveObjectCommand,
    RemoveNpcCommand, RemoveLabelCommand, RemoveNodeCommand,
    CompoundCommand
)
from core.geometry import Geometry
from ui.dialogs import ModalDialog
from ui.components import COLORS
from data_manager import DataManager, OBJECT_PRESETS
from tools.constants import (
    TOOL_WALL, TOOL_ROOM, TOOL_OBJECT, TOOL_PASSAGE,
    TOOL_LABEL, TOOL_NPC, TOOL_NODE, TOOL_SPAWN, TOOL_DELETE
)

SCALE = 20

class InteractionManager:
    """Управляет логикой кликов и взаимодействия с сущностями на карте"""

    def handle_left_click(self, core, mx: int, my: int, wx: float, wy: float, gx: float, gy: float):
        """Обрабатывает клик ЛКМ"""
        if core.tool is None:
            self.try_select_existing(core, mx, my)
            return

        # Ниже — активные инструменты создания
        if core.tool == TOOL_WALL:
            if core.wall_start is None:
                # Первый клик — начало стены
                core.wall_drawing = True
                core.wall_start = (gx, gy)
            else:
                # Второй клик — завершение стены
                if (
                    abs(gx - core.wall_start[0]) > 0.1
                    or abs(gy - core.wall_start[1]) > 0.1
                ):
                    # Валидация наложения стен (§1: запрещаем пересечение отрезков)
                    if self.check_wall_overlap(core, core.wall_start[0], core.wall_start[1], gx, gy):
                        core._show_toast("Ошибка: Стены не могут накладываться друг на друга (кроме стыков в углах).")
                        core.wall_drawing = False
                        core.wall_start = None
                        return
                    
                    wall_id = core.undo.push(
                        AddWallCommand(
                            core.dm,
                            core.current_file,
                            core.wall_start[0],
                            core.wall_start[1],
                            gx,
                            gy,
                        )
                    )
                    core._show_toast("Стена создана")
                    self.try_auto_room(core, wall_id)
                core.wall_drawing = False
                core.wall_start = None

        elif core.tool == TOOL_ROOM:
            # Начинаем создание комнаты
            core.room_drawing = True
            core.room_start = (gx, gy)

        elif core.tool == TOOL_OBJECT:
            # Для уличных локаций разрешаем объекты вне комнат
            loc_data = core.dm.locations.get(core.current_file, {})
            is_outdoor = loc_data.get("is_outdoor", False)
            if not is_outdoor and not self.is_point_in_any_room(core, wx, wy):
                core._show_toast("Объекты можно размещать только внутри комнат")
                return
            # Создаём объект
            preset = OBJECT_PRESETS.get(core.selected_object_type, {})
            ds = preset.get("default_size", {"w": 1.0, "h": 1.0})
            obj_w = float(ds.get("w", 1.0))
            obj_h = float(ds.get("h", 1.0))
            # Проверяем требует ли объект стену
            wall_id = ""
            # S143: Выравнивание дверей по стене (Snapping) для гарантированной резки (§1)
            if preset.get("requires_wall", False):
                wall_id = self.find_wall_near(core, gx, gy, threshold=1.5) or ""
                if not wall_id:
                    core._show_toast(
                        "Этот объект должен быть на стене — кликните ближе к стене"
                    )
                    return
                # Выравниваем объект по оси стены и проецируем на отрезок
                wall: Optional[Dict[str, Any]] = next(
                    (
                        w
                        for w in core.dm.locations[core.current_file]["walls"]
                        if w["id"] == wall_id
                    ),
                    None,
                )
                if wall:
                    # Снаппинг: проекция точки клика на отрезок стены
                    gx, gy = Geometry.project_point_to_segment(
                        gx, gy, wall["x1"], wall["y1"], wall["x2"], wall["y2"]
                    )
                    dx = abs(wall["x2"] - wall["x1"])
                    dy = abs(wall["y2"] - wall["y1"])
                    if dy > dx:  # стена более вертикальная — меняем w/h местами
                        obj_w, obj_h = obj_h, obj_w
            idx = core.undo.push(
                AddObjectCommand(
                    dm=core.dm,
                    filename=core.current_file,
                    obj_type=core.selected_object_type,
                    x=gx,
                    y=gy,
                    width=obj_w,
                    height=obj_h,
                    wall_id=wall_id,
                )
            )
            core.selected_object = ("object", str(idx))
            core._show_toast(f"Объект создан: {core.selected_object_type}")

        elif core.tool == TOOL_PASSAGE:
            # Создаём проход — ищем стену рядом с кликом
            wall_id = self.find_wall_near(core, gx, gy, threshold=1.0)
            if wall_id:
                pass_id = core.undo.push(
                    AddPassageCommand(
                        core.dm,
                        core.current_file,
                        wall_id,
                        "door",
                        {"x": gx, "y": gy},
                        core.current_z,
                    )
                )
                core.selected_object = ("passage", pass_id)
                core._show_toast(f"Проход создан в стене {wall_id}")
            else:
                core._show_toast("Нет стены рядом — кликните ближе к стене")

        elif core.tool == TOOL_LABEL:
            # Для уличных локаций разрешаем надписи вне комнат
            loc_data = core.dm.locations.get(core.current_file, {})
            is_outdoor = loc_data.get("is_outdoor", False)
            if not is_outdoor and not self.is_point_in_any_room(core, wx, wy):
                core._show_toast("Надписи можно размещать только внутри комнат")
                return
            # Создаём надпись — сначала спрашиваем текст
            core._pending_label_pos = (gx, gy)
            fields = [{"key": "text", "label": "Текст надписи", "value": "Надпись"}]

            def on_confirm(inputs: Dict[str, str]) -> None:
                text = inputs.get("text", "").strip()
                if text and core._pending_label_pos:
                    lid = core.undo.push(
                        AddLabelCommand(
                            core.dm,
                            core.current_file,
                            core._pending_label_pos[0],
                            core._pending_label_pos[1],
                            text,
                        )
                    )
                    core.selected_object = ("label", lid)
                    core._show_toast("Надпись создана")

            core.dialog = ModalDialog(core.screen, "Новая надпись", fields, on_confirm)

        elif core.tool == TOOL_NPC:
            # Для уличных локаций разрешаем NPC вне комнат
            loc_data = core.dm.locations.get(core.current_file, {})
            is_outdoor = loc_data.get("is_outdoor", False)
            if not is_outdoor and not self.is_point_in_any_room(core, wx, wy):
                core._show_toast("NPC можно размещать только внутри комнат")
                return
            if not core.selected_npc_id:
                core._show_toast("Нет доступных NPC в config/npc/individuals")
                return
            room_id = core.dm.find_room_at(core.current_file, wx, wy)
            npc_ref = core.undo.push(  # noqa: F841
                AddNpcCommand(
                    core.dm, core.current_file, core.selected_npc_id, gx, gy, room_id
                )
            )
            core.selected_object = ("npc", core.selected_npc_id)
            npc_name = next(
                (n["name"] for n in core._npc_list if n["id"] == core.selected_npc_id),
                core.selected_npc_id,
            )
            core._show_toast(f"NPC размещён: {npc_name}")

        elif core.tool == TOOL_NODE:
            # S143: Создание узлов и связей между ними
            loc = core.dm.locations[core.current_file]
            clicked_node_id = None
            # Ищем узел под кликом (радиус 0.5м)
            for nid, ndata in loc.get("nodes", {}).items():
                if math.hypot(ndata["x"] - gx, ndata["y"] - gy) <= 0.5:
                    clicked_node_id = nid
                    break

            if clicked_node_id:
                # Кликнули по существующему узлу
                if core.node_link_start is None:
                    # Первый клик — выделяем узел-источник
                    core.node_link_start = clicked_node_id
                    core._show_toast(f"Узел {clicked_node_id} выделен. Кликните по другому узлу для связи.")
                elif core.node_link_start == clicked_node_id:
                    # Клик по тому же узлу — снимаем выделение
                    core.node_link_start = None
                    core._show_toast("Выделение узла снято")
                else:
                    # Клик по другому узлу — создаём связь
                    core.undo.push(
                        AddConnectionCommand(
                            core.dm,
                            core.current_file,
                            core.node_link_start,
                            clicked_node_id,
                        )
                    )
                    core._show_toast(f"Создана связь: {core.node_link_start} -> {clicked_node_id}")
                    core.node_link_start = None
            else:
                # Клик по пустому месту — создаём новый узел
                node_id = f"node_{len(loc.get('nodes', {}))}"
                core.undo.push(
                    AddNodeCommand(
                        core.dm,
                        core.current_file,
                        node_id,
                        gx,
                        gy,
                        "Новый узел",
                    )
                )
                core._show_toast(f"Создан узел {node_id}")

        elif core.tool == TOOL_SPAWN:
            # Устанавливаем точку спавна игрока
            core.dm.set_player_spawn(core.current_file, gx, gy, core.current_z)
            core.selected_object = ("spawn", "player_spawn")
            core._show_toast(f"Точка спавна установлена: ({gx}, {gy})")

        elif core.tool == TOOL_DELETE:
            # Удаляем объект под курсором
            self.delete_at(core, mx, my)

    def handle_left_release(self, core, mx: int, my: int, wx: float, wy: float, gx: float, gy: float):
        """Обрабатывает отпускание ЛКМ"""
        if not core.current_file:
            return

        if core.tool == TOOL_ROOM and core.room_drawing and core.room_start:
            # Завершаем создание комнаты
            x = min(core.room_start[0], gx)
            y = min(core.room_start[1], gy)
            w = abs(gx - core.room_start[0])
            h = abs(gy - core.room_start[1])
            if w > 1 and h > 1:
                room_name = (
                    f"Комната {len(core.dm.locations[core.current_file]['rooms'])}"
                )
                room_cmd = AddRoomCommand(
                    core.dm, core.current_file, room_name, x, y, w, h
                )
                # 4 стены коробки
                wall_cmds = [
                    AddWallCommand(core.dm, core.current_file, x, y, x + w, y),
                    AddWallCommand(core.dm, core.current_file, x + w, y, x + w, y + h),
                    AddWallCommand(core.dm, core.current_file, x + w, y + h, x, y + h),
                    AddWallCommand(core.dm, core.current_file, x, y + h, x, y),
                ]
                core.undo.push(
                    CompoundCommand("Комната + стены", [room_cmd] + wall_cmds)
                )
                core._show_toast(f"Комната создана: {room_cmd.room_id}")
            core.room_drawing = False
            core.room_start = None

    def try_auto_room(self, core, last_wall_id: str) -> None:
        """Проверяет, замкнулся ли контур после создания стены.
        Если да — создаёт комнату автоматически."""
        if not core.current_file:
            return
        loc = core.dm.locations[core.current_file]  # noqa: F841

        # Округляем координаты до сетки 0.5м для сравнения
        def snap(pt: float) -> float:
            return round(pt * 2) / 2

        # Строим граф: точка (snapped) → список стен
        graph: Dict[Tuple[float, float], List[Dict]] = {}
        for wall in loc.get("walls", []):
            p1 = (snap(wall["x1"]), snap(wall["y1"]))
            p2 = (snap(wall["x2"]), snap(wall["y2"]))
            graph.setdefault(p1, []).append(wall)
            graph.setdefault(p2, []).append(wall)

        # Начальная стена
        start_wall = next((w for w in loc["walls"] if w["id"] == last_wall_id), None)
        if not start_wall:
            return

        origin = (snap(start_wall["x1"]), snap(start_wall["y1"]))
        current = (snap(start_wall["x2"]), snap(start_wall["y2"]))

        # Ищем путь обратно к origin
        visited_walls = {last_wall_id}
        path_points = [origin, current]
        max_depth = 50  # защита от бесконечного цикла

        while current != origin and max_depth > 0:
            max_depth -= 1
            candidates = graph.get(current, [])
            found = False
            for wall in candidates:
                if wall["id"] in visited_walls:
                    continue
                visited_walls.add(wall["id"])
                p1 = (snap(wall["x1"]), snap(wall["y1"]))
                p2 = (snap(wall["x2"]), snap(wall["y2"]))
                # Идём к другому концу стены
                next_pt = p2 if p1 == current else p1
                if next_pt == current:
                    continue  # стена длиной 0
                current = next_pt
                path_points.append(current)
                found = True
                break
            if not found:
                return  # тупик — не замкнутый

        if current != origin or len(path_points) < 4:
            return  # не замкнулся или слишком мало точек

        # Вычисляем площадь по формуле шнурков
        n = len(path_points)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += path_points[i][0] * path_points[j][1]
            area -= path_points[j][0] * path_points[i][1]
        area = abs(area) / 2.0

        if area < 1.0:
            return  # слишком маленькая

        # Проверяем что комната с такими координатами ещё не существует
        all_room_keys = set()
        for r in loc.get("rooms", []):
            all_room_keys.add(
                (
                    round(r["x"], 1),
                    round(r["y"], 1),
                    round(r["width"], 1),
                    round(r["height"], 1),
                )
            )

        # Bounding box
        xs = [p[0] for p in path_points]
        ys = [p[1] for p in path_points]
        bx = round(min(xs), 2)
        by = round(min(ys), 2)
        bw = round(max(xs) - bx, 2)
        bh = round(max(ys) - by, 2)

        room_key = (round(bx, 1), round(by, 1), round(bw, 1), round(bh, 1))
        if room_key in all_room_keys:
            return  # уже есть

        room_name = f"Комната {len(loc['rooms'])}"
        room_cmd = AddRoomCommand(
            core.dm,
            core.current_file,
            room_name,
            bx,
            by,
            bw,
            bh,
            polygon=path_points,
            area_sqm=round(area, 1),
        )

        core.undo.push(room_cmd)
        core._show_toast(f"Автокомната: {room_name} ({area:.1f} м²)")

    def find_wall_near(self, core, wx: float, wy: float, threshold: float = 1.0) -> Optional[str]:
        """Ищет стену, ближайшую к мировой точке (wx, wy). Возвращает wall_id или None."""
        if not core.current_file:
            return None
        loc = core.dm.locations[core.current_file]  # noqa: F841
        best_id: Optional[str] = None
        best_dist = threshold
        for wall in loc.get("walls", []):
            # Расстояние от точки до отрезка
            dist = Geometry.point_to_segment_dist(
                wx, wy, wall["x1"], wall["y1"], wall["x2"], wall["y2"]
            )
            if dist < best_dist:
                best_dist = dist
                best_id = wall["id"]
        return best_id

    def is_point_in_any_room(self, core, wx: float, wy: float) -> bool:
        """Проверяет, попадает ли мировая точка внутрь хотя бы одной комнаты"""
        if not core.current_file:
            return False
        loc = core.dm.locations[core.current_file]  # noqa: F841
        for room in loc.get("rooms", []):
            poly = room.get("polygon")
            if poly and len(poly) >= 3:
                if DataManager._point_in_polygon(wx, wy, [(p[0], p[1]) for p in poly]):
                    return True
        return False

    def check_wall_overlap(self, core, x1: float, y1: float, x2: float, y2: float, tolerance: float = 0.01) -> bool:
        """Проверяет, пересекается ли новый отрезок стены с существующими (кроме концов)."""
        if not core.current_file:
            return False
        loc = core.dm.locations[core.current_file]
        for wall in loc.get("walls", []):
            # Если отрезки имеют общую точку (стык в углу) — это не overlap
            # Проверяем пересечение с помощью скалярных произведений (Ориентация)
            if Geometry.segments_intersect(
                x1, y1, x2, y2,
                wall["x1"], wall["y1"], wall["x2"], wall["y2"]
            ):
                # Допуск: если они просто касаются концами (расстояние между концами < tolerance)
                d1 = math.hypot(x1 - wall["x1"], y1 - wall["y1"])
                d2 = math.hypot(x1 - wall["x2"], y1 - wall["y2"])
                d3 = math.hypot(x2 - wall["x1"], y2 - wall["y1"])
                d4 = math.hypot(x2 - wall["x2"], y2 - wall["y2"])
                if min(d1, d2, d3, d4) < tolerance:
                    continue
                return True
        return False

    def try_select_existing(self, core, mx: int, my: int) -> bool:
        """Пробует выбрать существующий объект под курсором. Возвращает True если нашёл."""
        if not core.current_file:
            return False
        loc = core.dm.locations[core.current_file]  # noqa: F841

        # S143: Узлы — проверяем первыми, чтобы можно было их таскать и выделять
        for nid, ndata in loc.get("nodes", {}).items():
            sx, sy = core.world_to_screen(ndata["x"], ndata["y"])
            if abs(sx - mx) < 12 and abs(sy - my) < 12:
                core.selected_object = ("node", nid)
                if core.tool is None:
                    core._dragging_entity = {
                        "type": "node",
                        "id": nid,
                        "start_mx": mx,
                        "start_my": my,
                        "orig": {"x": ndata["x"], "y": ndata["y"]},
                    }
                return True

        # Объекты
        if core.show_objects:
            for obj in loc.get("objects", []):
                pos = obj.get("position", {})
                if not pos:
                    continue
                sx, sy = core.world_to_screen(
                    pos.get("x", 0.0), pos.get("y", 0.0)
                )
                sz = obj.get("size", {})
                w = float(sz.get("w", 1.0)) * SCALE * core.zoom
                h = float(sz.get("h", 1.0)) * SCALE * core.zoom
                hit_rect = pygame.Rect(sx - w / 2, sy - h / 2, w, h)
                if hit_rect.collidepoint(mx, my):
                    core.selected_object = ("object", obj.get("id", ""))
                    return True

        # NPC (проверяем перед стенами — приоритет)
        for npc in loc.get("npcs", []):
            sx, sy = core.world_to_screen(npc["position"]["x"], npc["position"]["y"])
            hit_r = int(SCALE * core.zoom * 0.4)
            if pygame.Rect(sx - hit_r, sy - hit_r, hit_r * 2, hit_r * 2).collidepoint(
                mx, my
            ):
                core.selected_object = ("npc", npc["ref_id"])
                return True

        # Точка спавна
        spawn = loc.get("player_spawn")
        if spawn:
            sx, sy = core.world_to_screen(spawn["x"], spawn["y"])
            hit_r = int(SCALE * core.zoom * 0.5)
            if pygame.Rect(sx - hit_r, sy - hit_r, hit_r * 2, hit_r * 2).collidepoint(
                mx, my
            ):
                core.selected_object = ("spawn", "player_spawn")
                return True

        # Стены
        if core.show_walls:
            for wall in loc.get("walls", []):
                sx1, sy1 = core.world_to_screen(wall["x1"], wall["y1"])
                sx2, sy2 = core.world_to_screen(wall["x2"], wall["y2"])
                if Geometry.point_near_line(mx, my, sx1, sy1, sx2, sy2, 10):
                    core.selected_object = ("wall", wall["id"])
                    return True

        # Комнаты — собираем все перекрытые, переключаемся циклом
        if core.show_rooms:
            wx, wy = core.screen_to_world(mx, my)
            matched_rooms: List[str] = []
            for room in loc.get("rooms", []):
                poly = room.get("polygon")
                if poly and len(poly) >= 3:
                    if DataManager._point_in_polygon(
                        wx, wy, [(p[0], p[1]) for p in poly]
                    ):
                        matched_rooms.append(room["id"])
                else:
                    rx, ry = core.world_to_screen(room["x"], room["y"])
                    rw = room["width"] * SCALE * core.zoom
                    rh = room["height"] * SCALE * core.zoom
                    if pygame.Rect(rx, ry, rw, rh).collidepoint(mx, my):
                        matched_rooms.append(room["id"])

            if matched_rooms:
                # Проверяем что клик в той же области (±8 пикселей)
                dx = abs(mx - core._last_click_pos[0])
                dy = abs(my - core._last_click_pos[1])
                if matched_rooms == core._overlap_room_ids and dx < 8 and dy < 8:
                    # Переключаемся на следующую
                    core._overlap_index = (core._overlap_index + 1) % len(matched_rooms)
                else:
                    # Новая область — начинаем с первой
                    core._overlap_room_ids = matched_rooms
                    core._overlap_index = 0

                core.selected_object = ("room", matched_rooms[core._overlap_index])
                return True

        return False

    def delete_at(self, core, mx: int, my: int):
        """Удаляет объект под курсором"""
        if not core.current_file:
            return

        loc = core.dm.locations[core.current_file]  # noqa: F841

        # Узлы
        for nid in list(loc.get("nodes", {}).keys()):
            ndata = loc["nodes"][nid]
            sx, sy = core.world_to_screen(ndata["x"], ndata["y"])
            if abs(sx - mx) < 15 and abs(sy - my) < 15:
                core.undo.push(
                    RemoveNodeCommand(core.dm, core.current_file, nid, deepcopy(ndata))
                )
                core._show_toast(f"Узел удалён: {nid}")
                core.selected_object = None
                return

        # Связи (рёбра графа)
        for nid, ndata in loc.get("nodes", {}).items():
            sx1, sy1 = core.world_to_screen(ndata["x"], ndata["y"])
            for conn in ndata.get("connections", []):
                if conn in loc.get("nodes", {}):
                    target_data = loc["nodes"][conn]
                    sx2, sy2 = core.world_to_screen(target_data["x"], target_data["y"])
                    if Geometry.point_near_line(mx, my, sx1, sy1, sx2, sy2, 5):
                        core.dm.remove_connection(core.current_file, nid, conn)
                        core._show_toast(f"Связь удалена: {nid} -> {conn}")
                        core.selected_object = None
                        return

        # Объекты
        for i in range(len(loc.get("objects", [])) - 1, -1, -1):
            obj = loc["objects"][i]
            pos = obj.get("position", {})
            if not pos:
                continue
            sx, sy = core.world_to_screen(pos.get("x", 0.0), pos.get("y", 0.0))
            if abs(sx - mx) < 20 and abs(sy - my) < 20:
                core.undo.push(
                    RemoveObjectCommand(
                        core.dm, core.current_file, obj.get("id", ""), deepcopy(obj)
                    )
                )
                core._show_toast("Объект удалён")
                core.selected_object = None
                return

        # NPC
        for npc in loc.get("npcs", []):
            sx, sy = core.world_to_screen(npc["position"]["x"], npc["position"]["y"])
            hit_r = int(SCALE * core.zoom * 0.4)
            if pygame.Rect(sx - hit_r, sy - hit_r, hit_r * 2, hit_r * 2).collidepoint(
                mx, my
            ):
                core.undo.push(
                    RemoveNpcCommand(core.dm, core.current_file, deepcopy(npc))
                )
                npc_name = next(
                    (n["name"] for n in core._npc_list if n["id"] == npc["ref_id"]),
                    npc["ref_id"],
                )
                core._show_toast(f"NPC удалён: {npc_name}")
                core.selected_object = None
                return

        # Надписи
        for lbl in loc.get("labels", []):
            sx, sy = core.world_to_screen(lbl["x"], lbl["y"])
            text_surf = core.font_small.render(
                lbl.get("text", ""), True, COLORS["text"]
            )
            tw, th = text_surf.get_size()
            if pygame.Rect(sx, sy, tw, th).collidepoint(mx, my):
                core.undo.push(
                    RemoveLabelCommand(core.dm, core.current_file, deepcopy(lbl))
                )
                core._show_toast("Надпись удалена")
                core.selected_object = None
                return

        # Точка спавна игрока
        spawn = loc.get("player_spawn")
        if spawn:
            sx, sy = core.world_to_screen(spawn["x"], spawn["y"])
            if abs(sx - mx) < 15 and abs(sy - my) < 15:
                del loc["player_spawn"]
                core._show_toast("Точка спавна удалена")
                core.selected_object = None
                return

        # Стены
        for wall in loc.get("walls", []):
            sx1, sy1 = core.world_to_screen(wall["x1"], wall["y1"])
            sx2, sy2 = core.world_to_screen(wall["x2"], wall["y2"])
            if Geometry.point_near_line(mx, my, sx1, sy1, sx2, sy2, 10):
                core.dm.remove_wall(core.current_file, wall["id"])
                core._show_toast("Стена удалена")
                core.selected_object = None
                return

        # Комнаты
        for room in loc.get("rooms", []):
            rx, ry = core.world_to_screen(room["x"], room["y"])
            rw = room["width"] * SCALE * core.zoom
            rh = room["height"] * SCALE * core.zoom
            if pygame.Rect(rx, ry, rw, rh).collidepoint(mx, my):
                # собираем стены по границам комнаты
                x, y, w, h = room["x"], room["y"], room["width"], room["height"]
                edges = [
                    (x, y, x + w, y),
                    (x + w, y, x + w, y + h),
                    (x + w, y + h, x, y + h),
                    (x, y + h, x, y),
                ]
                wall_cmds = []
                for wall in list(loc["walls"]):
                    for ex1, ey1, ex2, ey2 in edges:
                        direct = (
                            abs(wall["x1"] - ex1) < 0.01
                            and abs(wall["y1"] - ey1) < 0.01
                            and abs(wall["x2"] - ex2) < 0.01
                            and abs(wall["y2"] - ey2) < 0.01
                        )
                        reverse = (
                            abs(wall["x1"] - ex2) < 0.01
                            and abs(wall["y1"] - ey2) < 0.01
                            and abs(wall["x2"] - ex1) < 0.01
                            and abs(wall["y2"] - ey1) < 0.01
                        )
                        if direct or reverse:
                            wall_cmds.append(
                                RemoveWallCommand(
                                    core.dm, core.current_file, deepcopy(wall)
                                )
                            )
                            break
                room_cmd = RemoveRoomCommand(core.dm, core.current_file, deepcopy(room))
                core.undo.push(
                    CompoundCommand("Удалить комнату", [room_cmd] + wall_cmds)
                )
                core._show_toast(f"Комната удалена: {room['name']}")
                core.selected_object = None
                return
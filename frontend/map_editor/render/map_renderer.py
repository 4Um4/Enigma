"""
map_editor/render/map_renderer.py
Отрисовка карты: сетка, локации, объекты, NPC, UI элементы.
"""
import math
import pygame
from typing import Any, Dict, List, Optional, Tuple

from ui.components import COLORS, Dropdown
from data_manager import OBJECT_PRESETS, DataManager
from data.npc_data import NPC_SPRITE_MAP
from sprite_registry import sprite_registry
from tools.constants import TOOL_WALL, TOOL_ROOM, TOOL_NODE, MODE_WORLD, MODE_LOCAL

# Цвета объектов для отрисовки
OBJECT_COLORS = {
    "wall": (120, 80, 50),
    "decoration": (100, 100, 110),
    "furniture": (139, 69, 19),
}

SCALE = 20  # Масштаб: 1 метр = 20 пикселей (базовый, до зума)

class MapRenderer:
    """Управляет всей отрисовкой редактора карт"""

    def _world_to_screen(self, core, wx: float, wy: float) -> Tuple[int, int]:
        # Прокси к методу core, так как он там определен
        return core.world_to_screen(wx, wy)

    def _screen_to_world(self, core, sx: int, sy: int) -> Tuple[float, float]:
        return core.screen_to_world(sx, sy)

    def draw_world(self, core):
        """Отрисовывает карту мира"""
        self._draw_world_grid(core)

        # Локации
        for fname, data in core.dm.locations.items():
            rect = self._get_location_screen_rect(core, fname)
            if not rect:
                continue

            if data.get("is_outdoor"):
                color = (80, 120, 80)
            else:
                color = (100, 100, 110)

            if fname == core.current_file:
                color = (100, 150, 200)

            pygame.draw.rect(core.screen, color, rect, border_radius=4)
            pygame.draw.rect(core.screen, COLORS["border"], rect, 2, border_radius=4)

            label = core.font_bold.render(data.get("label", fname), True, COLORS["text_highlight"])
            core.screen.blit(label, (rect.x + 8, rect.y - 18))

            info_text = f"{data['size']['w']}x{data['size']['h']}м"
            info = core.font_small.render(info_text, True, COLORS["text_dim"])
            core.screen.blit(info, (rect.x + 8, rect.y + 5))

            p_count = len(data.get("portals", []))
            if p_count > 0:
                p_text = core.font_small.render(f"🚪{p_count}", True, COLORS["accent_yellow"])
                core.screen.blit(p_text, (rect.x + 8, rect.y + 20))

    def _draw_world_grid(self, core):
        """Отрисовывает сетку мира"""
        start_x = int(core.camera_x / (SCALE * core.zoom * 10)) - 1
        end_x = start_x + int(core.screen.get_width() / (SCALE * core.zoom * 10)) + 2
        start_y = int(core.camera_y / (SCALE * core.zoom * 10)) - 1
        end_y = start_y + int(core.screen.get_height() / (SCALE * core.zoom * 10)) + 2

        for x in range(start_x, end_x):
            sx = x * SCALE * core.zoom * 10 + core.camera_x
            pygame.draw.line(core.screen, COLORS["grid_major"], (sx, 0), (sx, core.screen.get_height()))
        for y in range(start_y, end_y):
            sy = y * SCALE * core.zoom * 10 + core.camera_y
            pygame.draw.line(core.screen, COLORS["grid_major"], (0, sy), (core.screen.get_width(), sy))

    def _get_location_screen_rect(self, core, fname: str) -> Optional[pygame.Rect]:
        """Возвращает экранный прямоугольник локации"""
        if fname not in core.dm.locations:
            return None
        data = core.dm.locations[fname]
        sx, sy = self._world_to_screen(core, data["origin"]["x"], data["origin"]["y"])
        sw = data["size"]["w"] * SCALE * core.zoom
        sh = data["size"]["h"] * SCALE * core.zoom
        return pygame.Rect(sx, sy, sw, sh)

    def draw_local(self, core):
        """Отрисовывает локацию в режиме редактирования"""
        if not core.current_file:
            return

        if core.show_grid:
            self._draw_local_grid(core)
        self._draw_location_bounds(core)

        if core.show_rooms:
            self._draw_rooms(core)
        if core.show_walls:
            self._draw_walls(core)

        self._draw_passages(core)
        self._draw_nodes(core)
        self._draw_labels(core)

        if core.show_objects:
            self._draw_objects(core)

        self._draw_npcs(core)
        self._draw_spawn(core)
        self._draw_preview(core)
        self._draw_selection(core)

        if core.observatory_data:
            self._draw_observatory(core)

    def _draw_observatory(self, core):
        """Финальная отрисовка Spatial Observatory."""
        if not core.observatory_data:
            return

        font = pygame.font.SysFont("Arial", 16)
        status_text = f"OBS REV: {core._observatory_revision} | DIRTY: {core._spatial_dirty}"
        text_surf = font.render(status_text, True, (255, 255, 0))
        core.screen.blit(text_surf, (10, core.menu_height + core.toolbar_height + 30))

        topo = core.observatory_data.get("topology", {})
        nodes = topo.get("nodes", [])
        edges = topo.get("edges", [])
        agents = core.observatory_data.get("agents", [])

        diag_text = f"Nodes: {len(nodes)} | Edges: {len(edges)} | Agents: {len(agents)}"
        diag_surf = font.render(diag_text, True, (255, 255, 0))
        core.screen.blit(diag_surf, (10, core.menu_height + core.toolbar_height + 50))

        diagnostics = core.observatory_data.get("diagnostics", [])
        if diagnostics:
            err = diagnostics[0]
            err_text = f"ERROR: {err.get('code', '')} - {err.get('message', '')[:120]}"
            err_surf = font.render(err_text, True, (255, 0, 0))
            core.screen.blit(err_surf, (10, core.menu_height + core.toolbar_height + 70))

        for edge in edges:
            from_node = next((n for n in nodes if n["node_id"] == edge["from_node_id"]), None)
            to_node = next((n for n in nodes if n["node_id"] == edge["to_node_id"]), None)
            if from_node and to_node:
                p1 = self._world_to_screen(core, from_node["position"][0], from_node["position"][1])
                p2 = self._world_to_screen(core, to_node["position"][0], to_node["position"][1])
                if edge.get("traversable", True):
                    pygame.draw.line(core.screen, (0, 200, 0), p1, p2, 4)
                else:
                    pygame.draw.line(core.screen, (255, 0, 0), p1, p2, 4)
                    mid_x = (p1[0] + p2[0]) // 2
                    mid_y = (p1[1] + p2[1]) // 2
                    pygame.draw.line(core.screen, (255, 255, 255), (mid_x - 8, mid_y - 8), (mid_x + 8, mid_y + 8), 4)
                    pygame.draw.line(core.screen, (255, 255, 255), (mid_x + 8, mid_y - 8), (mid_x - 8, mid_y + 8), 4)

        for node in nodes:
            sx, sy = self._world_to_screen(core, node["position"][0], node["position"][1])
            pygame.draw.circle(core.screen, (255, 255, 0), (int(sx), int(sy)), 10)
            pygame.draw.circle(core.screen, (0, 0, 0), (int(sx), int(sy)), 4)

        for agent in agents:
            path = agent.get("path")
            if not path or not path.get("points"):
                continue
            points = []
            for p in path["points"]:
                sx, sy = self._world_to_screen(core, p[0], p[1])
                points.append((int(sx), int(sy)))
            if len(points) >= 2:
                pygame.draw.lines(core.screen, (0, 100, 255), False, points, 5)

    def _draw_local_grid(self, core):
        """Отрисовывает локальную сетку"""
        screen_w = core.screen.get_width() - core.panel_width
        screen_h = core.screen.get_height()

        start_x = int((-core.camera_x) / (SCALE * core.zoom)) - 1
        end_x = start_x + int(screen_w / (SCALE * core.zoom)) + 2
        start_y = int((-core.camera_y) / (SCALE * core.zoom)) - 1
        end_y = start_y + int(screen_h / (SCALE * core.zoom)) + 2

        for x in range(start_x * 2, end_x * 2):
            sx = x * SCALE * core.zoom * 0.5 + core.camera_x
            pygame.draw.line(core.screen, COLORS["grid_minor"], (sx, core.menu_height + core.toolbar_height), (sx, screen_h))
        for y in range(start_y * 2, end_y * 2):
            sy = y * SCALE * core.zoom * 0.5 + core.camera_y
            pygame.draw.line(core.screen, COLORS["grid_minor"], (0, sy), (screen_w, sy))

        for x in range(start_x, end_x):
            sx = x * SCALE * core.zoom + core.camera_x
            color = COLORS["grid_major"] if x % 5 == 0 else COLORS["grid_minor"]
            pygame.draw.line(core.screen, color, (sx, core.menu_height + core.toolbar_height), (sx, screen_h))
        for y in range(start_y, end_y):
            sy = y * SCALE * core.zoom + core.camera_y
            color = COLORS["grid_major"] if y % 5 == 0 else COLORS["grid_minor"]
            pygame.draw.line(core.screen, color, (0, sy), (screen_w, sy))

        origin_x, origin_y = self._world_to_screen(core, 0, 0)
        if 0 <= origin_x <= screen_w:
            pygame.draw.line(core.screen, COLORS["accent_red"], (origin_x, core.menu_height + core.toolbar_height), (origin_x, screen_h), 2)
        if core.menu_height + core.toolbar_height <= origin_y <= screen_h:
            pygame.draw.line(core.screen, COLORS["accent_green"], (0, origin_y), (screen_w, origin_y), 2)

    def _draw_location_bounds(self, core):
        """Отрисовывает границы локации"""
        if not core.current_file:
            return
        loc = core.dm.locations[core.current_file]
        origin = loc.get("origin", {"x": 0, "y": 0})
        x, y = self._world_to_screen(core, origin["x"], origin["y"])
        w = loc["size"]["w"] * SCALE * core.zoom
        h = loc["size"]["h"] * SCALE * core.zoom

        bg_color = (40, 50, 40) if loc.get("is_outdoor") else (45, 45, 50)
        pygame.draw.rect(core.screen, bg_color, (x, y, w, h))
        pygame.draw.rect(core.screen, COLORS["border"], (x, y, w, h), 3)
        label = core.font.render(f"{loc['size']['w']}x{loc['size']['h']}м", True, COLORS["text_dim"])
        core.screen.blit(label, (x + 5, y - 15))

    def _find_label_position(self, core, room: Dict, objects_in_room: List[Dict]) -> Tuple[int, int]:
        """Находит лучшую позицию для надписи комнаты"""
        poly = room.get("polygon")
        if not poly:
            rx, ry = self._world_to_screen(core, room["x"], room["y"])
            return rx + 4, ry + 4

        screen_poly = [self._world_to_screen(core, p[0], p[1]) for p in poly]
        xs = [p[0] for p in screen_poly]
        ys = [p[1] for p in screen_poly]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        obj_positions = [(self._world_to_screen(core, o["position"]["x"], o["position"]["y"])) for o in objects_in_room]
        text_w, text_h = 150, 16
        step = 16
        best_pos = (min_x + 4, min_y + 4)
        best_dist = -1

        cx = min_x + text_w // 2 + 4
        while cx < max_x - text_w // 2 - 4:
            cy = min_y + text_h // 2 + 4
            while cy < max_y - text_h // 2 - 4:
                if (DataManager._point_in_polygon(cx - text_w // 2, cy - text_h // 2, screen_poly) and
                    DataManager._point_in_polygon(cx + text_w // 2, cy - text_h // 2, screen_poly) and
                    DataManager._point_in_polygon(cx - text_w // 2, cy + text_h // 2, screen_poly) and
                    DataManager._point_in_polygon(cx + text_w // 2, cy + text_h // 2, screen_poly)):
                    min_d = float("inf")
                    for ox, oy in obj_positions:
                        d = math.hypot(cx - ox, cy - oy)
                        if d < min_d: min_d = d
                    if not obj_positions: min_d = 999
                    if min_d > best_dist:
                        best_dist = min_d
                        best_pos = (int(cx) - text_w // 2, int(cy) - text_h // 2)
                cy += step
            cx += step
        return best_pos

    def _draw_rooms(self, core):
        """Отрисовывает комнаты"""
        if not core.current_file: return
        loc = core.dm.locations[core.current_file]
        for room in loc.get("rooms", []):
            poly = room.get("polygon")
            if poly and len(poly) >= 3:
                screen_pts = [self._world_to_screen(core, p[0], p[1]) for p in poly]
                pygame.draw.polygon(core.screen, (60, 60, 70), screen_pts)
                pygame.draw.polygon(core.screen, (100, 100, 120), screen_pts, 2)
            else:
                rx, ry = self._world_to_screen(core, room["x"], room["y"])
                rw = room["width"] * SCALE * core.zoom
                rh = room["height"] * SCALE * core.zoom
                pygame.draw.rect(core.screen, (60, 60, 70), (rx, ry, rw, rh))
                pygame.draw.rect(core.screen, (100, 100, 120), (rx, ry, rw, rh), 2)

            objects_in = [o for o in loc.get("objects", []) if core.dm.find_room_at(core.current_file, o["position"]["x"], o["position"]["y"]) == room["id"]]
            lx, ly = self._find_label_position(core, room, objects_in)
            area = room.get("area_sqm", round(room["width"] * room["height"], 1))
            label_str = f"{room['name']} — {area:.1f} м²"
            label = core.font_small.render(label_str, True, COLORS["text_dim"])
            core.screen.blit(label, (lx, ly))

    def _draw_walls(self, core):
        """Отрисовывает стены"""
        if not core.current_file: return
        loc = core.dm.locations[core.current_file]
        for wall in loc.get("walls", []):
            x1, y1 = self._world_to_screen(core, wall["x1"], wall["y1"])
            x2, y2 = self._world_to_screen(core, wall["x2"], wall["y2"])
            thickness = max(2, int(3 * core.zoom))
            pygame.draw.line(core.screen, OBJECT_COLORS["wall"], (x1, y1), (x2, y2), thickness)
            pygame.draw.circle(core.screen, (180, 120, 60), (x1, y1), 4)
            pygame.draw.circle(core.screen, (180, 120, 60), (x2, y2), 4)

    def _draw_passages(self, core):
        """Отрисовывает проходы"""
        if not core.current_file: return
        loc = core.dm.locations[core.current_file]
        for passage in loc.get("passages", []):
            if passage.get("z", 0) != core.current_z: continue
            sx, sy = self._world_to_screen(core, passage["position"]["x"], passage["position"]["y"])
            ptype = passage.get("type", "door")
            color = {"door": (255, 215, 0), "window": (135, 206, 235), "gap": (170, 170, 170)}.get(ptype, (255, 215, 0))
            pygame.draw.circle(core.screen, color, (sx, sy), 6)
            pygame.draw.circle(core.screen, COLORS["border"], (sx, sy), 6, 1)
            label = core.font_small.render(passage["id"], True, COLORS["text_dim"])
            core.screen.blit(label, (sx + 10, sy - 6))

    def _draw_labels(self, core):
        """Отрисовывает надписи"""
        if not core.current_file: return
        loc = core.dm.locations[core.current_file]
        for lbl in loc.get("labels", []):
            sx, sy = self._world_to_screen(core, lbl["x"], lbl["y"])
            text = lbl.get("text", "")
            if not text: continue
            color = COLORS["text_highlight"]
            if core.selected_object == ("label", lbl["id"]): color = COLORS["accent_yellow"]
            rendered = core.font_small.render(text, True, color)
            core.screen.blit(rendered, (sx, sy))

    def _draw_objects(self, core):
        """Отрисовывает объекты"""
        if not core.current_file: return
        loc = core.dm.locations[core.current_file]
        for i, obj in enumerate(loc.get("objects", [])):
            sx, sy = self._world_to_screen(core, obj["position"]["x"], obj["position"]["y"])
            w = obj["size"]["w"] * SCALE * core.zoom
            h = obj["size"]["h"] * SCALE * core.zoom
            try: rotation = float(obj.get("rotation") or 0)
            except (ValueError, TypeError): rotation = 0.0
            color = OBJECT_COLORS.get(obj["type"], OBJECT_COLORS["decoration"])

            preset = OBJECT_PRESETS.get(obj["type"], {})
            sprite_info = obj.get("sprite") or preset.get("sprite")
            sprite_surf = None
            if sprite_info:
                if len(sprite_info) >= 5:
                    _t = int(sprite_info[5]) if len(sprite_info) > 5 else 220
                    _o = int(sprite_info[6]) if len(sprite_info) > 6 else 1
                    sprite_surf = sprite_registry.get_rect(sprite_info[0], int(sprite_info[1]), int(sprite_info[2]), int(sprite_info[3]), int(sprite_info[4]), _t, _o)
                else:
                    sprite_surf = sprite_registry.get(sprite_info[0], sprite_info[1], sprite_info[2])

            if sprite_surf:
                sw, sh = sprite_surf.get_size()
                ratio = min(w / sw, h / sh)
                nw, nh = int(sw * ratio), int(sh * ratio)
                scaled = pygame.transform.scale(sprite_surf, (nw, nh))
                if rotation % 360 != 0: scaled = pygame.transform.rotate(scaled, -rotation)
                scaled_rect = scaled.get_rect(center=(int(sx), int(sy)))
                core.screen.blit(scaled, scaled_rect)
            else:
                if rotation % 360 != 0:
                    pts = core._rotated_rect_points(sx, sy, w, h, rotation)
                    pygame.draw.polygon(core.screen, color, pts)
                    pygame.draw.polygon(core.screen, COLORS["border"], pts, 1)
                else:
                    rect = pygame.Rect(sx - w / 2, sy - h / 2, w, h)
                    pygame.draw.rect(core.screen, color, rect, border_radius=2)
                    pygame.draw.rect(core.screen, COLORS["border"], rect, 1, border_radius=2)

            if obj.get("show_name", False):
                label_text = obj.get("name", obj["type"][:4])
                label = core.font_small.render(label_text, True, COLORS["text_highlight"])
                core.screen.blit(label, (sx - label.get_width() // 2, sy - h / 2 - 14))

    def _draw_npcs(self, core):
        """Отрисовывает NPC"""
        if not core.current_file: return
        loc = core.dm.locations[core.current_file]
        for npc in loc.get("npcs", []):
            sx, sy = self._world_to_screen(core, npc["position"]["x"], npc["position"]["y"])
            npc_name = next((n["name"] for n in core._npc_list if n["id"] == npc["ref_id"]), npc["ref_id"])
            sprite_info = npc.get("sprite") or NPC_SPRITE_MAP.get(npc["ref_id"], ("Deadbeat/deadbeat_b", 23, 21))
            if isinstance(sprite_info, dict):
                sprite_info = sprite_info.get("S") or next(iter(sprite_info.values()), None)
            size = int(SCALE * core.zoom * 1.5)
            sprite_surf = None
            if sprite_info:
                if len(sprite_info) >= 5:
                    _t = int(sprite_info[5]) if len(sprite_info) > 5 else 220
                    _o = int(sprite_info[6]) if len(sprite_info) > 6 else 1
                    sprite_surf = sprite_registry.get_rect(sprite_info[0], int(sprite_info[1]), int(sprite_info[2]), int(sprite_info[3]), int(sprite_info[4]), _t, _o)
                else:
                    sprite_surf = sprite_registry.get(sprite_info[0], sprite_info[1], sprite_info[2])

            is_selected = core.selected_object == ("npc", npc["ref_id"])
            if sprite_surf:
                sw, sh = sprite_surf.get_size()
                ratio = min(size / sw, size / sh)
                nw, nh = int(sw * ratio), int(sh * ratio)
                scaled = pygame.transform.scale(sprite_surf, (nw, nh))
                rect = scaled.get_rect(center=(int(sx), int(sy)))
                core.screen.blit(scaled, rect)
                if is_selected: pygame.draw.rect(core.screen, COLORS["accent_yellow"], rect.inflate(4, 4), 2)
            else:
                color = COLORS["accent_yellow"] if is_selected else (100, 180, 100)
                pygame.draw.circle(core.screen, color, (int(sx), int(sy)), size // 2)
                pygame.draw.circle(core.screen, COLORS["border"], (int(sx), int(sy)), size // 2, 1)

            label = core.font_small.render(npc_name, True, COLORS["text_highlight"])
            core.screen.blit(label, (sx - label.get_width() // 2, sy - size // 2 - 14))

    def _draw_spawn(self, core):
        """Отрисовывает точку спавна игрока"""
        if not core.current_file: return
        loc = core.dm.locations[core.current_file]
        spawn = loc.get("player_spawn")
        if not spawn: return
        sx, sy = self._world_to_screen(core, spawn["x"], spawn["y"])
        is_selected = core.selected_object == ("spawn", "player_spawn")
        size = int(SCALE * core.zoom * 0.5)
        color = COLORS["accent_yellow"] if is_selected else (255, 200, 0)
        points = [(sx, sy - size), (sx - size * 0.7, sy + size * 0.5), (sx + size * 0.7, sy + size * 0.5)]
        pygame.draw.polygon(core.screen, color, points)
        pygame.draw.polygon(core.screen, COLORS["border"], points, 2)
        label = core.font_small.render("СПАВН", True, COLORS["accent_yellow"])
        core.screen.blit(label, (sx - label.get_width() // 2, sy + size * 0.5 + 4))

    def _draw_nodes(self, core):
        """Отрисовывает навигационные узлы"""
        if not core.current_file: return
        loc = core.dm.locations[core.current_file]
        for nid, ndata in loc.get("nodes", {}).items():
            sx, sy = self._world_to_screen(core, ndata["x"], ndata["y"])
            for conn in ndata.get("connections", []):
                if ":" not in conn and conn in loc["nodes"]:
                    ex, ey = self._world_to_screen(core, loc["nodes"][conn]["x"], loc["nodes"][conn]["y"])
                    pygame.draw.line(core.screen, (80, 80, 90), (sx, sy), (ex, ey), 2)
                elif ":" in conn:
                    ex, ey = sx + 30, sy
                    for j in range(0, 30, 8):
                        pygame.draw.line(core.screen, COLORS["accent_yellow"], (sx + j, sy), (sx + min(j + 4, 30), sy), 2)

        for nid, ndata in loc.get("nodes", {}).items():
            sx, sy = self._world_to_screen(core, ndata["x"], ndata["y"])
            if core.node_link_start == nid: pygame.draw.circle(core.screen, COLORS["accent_yellow"], (sx, sy), 12)
            pygame.draw.circle(core.screen, COLORS["accent_blue"], (sx, sy), 8)
            pygame.draw.circle(core.screen, COLORS["text_highlight"], (sx, sy), 8, 2)
            label = core.font_small.render(ndata.get("label", nid), True, COLORS["text"])
            core.screen.blit(label, (sx + 10, sy - 8))

    def _draw_preview(self, core):
        """Отрисовывает предпросмотр при рисовании"""
        mx, my = pygame.mouse.get_pos()
        if core.tool == TOOL_WALL and core.wall_drawing and core.wall_start:
            x1, y1 = self._world_to_screen(core, core.wall_start[0], core.wall_start[1])
            pygame.draw.line(core.screen, COLORS["accent_yellow"], (x1, y1), (mx, my), 2)
            wx2, wy2 = self._screen_to_world(core, mx, my)
            length = math.hypot(wx2 - core.wall_start[0], wy2 - core.wall_start[1])
            mid_x = (x1 + mx) // 2
            mid_y = (y1 + my) // 2 - 14
            label = core.font_small.render(f"{length:.2f} м", True, COLORS["accent_yellow"])
            core.screen.blit(label, (mid_x - label.get_width() // 2, mid_y))
        elif core.tool == TOOL_ROOM and core.room_drawing and core.room_start:
            x1, y1 = self._world_to_screen(core, core.room_start[0], core.room_start[1])
            rect = pygame.Rect(min(x1, mx), min(y1, my), abs(mx - x1), abs(my - y1))
            pygame.draw.rect(core.screen, (100, 100, 120, 100), rect)
            pygame.draw.rect(core.screen, COLORS["accent_yellow"], rect, 2)
            wx1, wy1 = core.room_start
            wx2, wy2 = self._screen_to_world(core, mx, my)
            w_m = abs(wx2 - wx1)
            h_m = abs(wy2 - wy1)
            area = w_m * h_m
            if area > 0.5:
                area_text = f"{area:.1f} м² ({w_m:.1f}×{h_m:.1f})"
                area_surf = core.font_small.render(area_text, True, COLORS["accent_yellow"])
                core.screen.blit(area_surf, (rect.centerx - area_surf.get_width() // 2, rect.centery - area_surf.get_height() // 2))

    def _draw_selection(self, core):
        """Отрисовывает выделение объекта"""
        if not core.current_file or not core.selected_object: return
        obj_type, obj_key = core.selected_object
        loc = core.dm.locations[core.current_file]

        if obj_type == "object":
            obj = next((o for o in loc.get("objects", []) if o.get("id") == obj_key), None)
            if obj:
                sx, sy = self._world_to_screen(core, obj["position"]["x"], obj["position"]["y"])
                w = obj["size"]["w"] * SCALE * core.zoom
                h = obj["size"]["h"] * SCALE * core.zoom
                try: rotation = float(obj.get("rotation") or 0)
                except (ValueError, TypeError): rotation = 0.0
                preset = OBJECT_PRESETS.get(obj["type"], {})
                if not preset.get("sprite"):
                    if rotation % 360 != 0:
                        pts = core._rotated_rect_points(sx, sy, w + 6, h + 6, rotation)
                        pygame.draw.polygon(core.screen, COLORS["accent_yellow"], pts, 3)
                    else:
                        rect = pygame.Rect(sx - w / 2 - 3, sy - h / 2 - 3, w + 6, h + 6)
                        pygame.draw.rect(core.screen, COLORS["accent_yellow"], rect, 3, border_radius=3)
                if core.tool is None:
                    for handle in core._get_resize_handles(obj_key):
                        r = handle["rect"]
                        pygame.draw.rect(core.screen, COLORS["bg_panel"], r)
                        pygame.draw.rect(core.screen, COLORS["accent_yellow"], r, 1)
                    for btn in core._get_rotation_buttons(obj_key):
                        r = btn["rect"]
                        pygame.draw.circle(core.screen, COLORS["bg_panel"], r.center, r.width // 2)
                        pygame.draw.circle(core.screen, COLORS["border"], r.center, r.width // 2, 1)
                        cx, cy = r.center
                        if btn.get("action") == "mirror":
                            pygame.draw.line(core.screen, COLORS["text"], (cx - 5, cy), (cx + 5, cy), 2)
                            pygame.draw.polygon(core.screen, COLORS["text"], [(cx + 5, cy), (cx + 2, cy - 3), (cx + 2, cy + 3)])
                            pygame.draw.polygon(core.screen, COLORS["text"], [(cx - 5, cy), (cx - 2, cy - 3), (cx - 2, cy + 3)])
                        else:
                            if btn["delta"] > 0: pts = [(cx - 4, cy - 4), (cx - 4, cy + 4), (cx + 4, cy)]
                            else: pts = [(cx + 4, cy - 4), (cx + 4, cy + 4), (cx - 4, cy)]
                            pygame.draw.polygon(core.screen, COLORS["text"], pts)

        elif obj_type == "portal":
            for p in loc.get("portals", []):
                if p["id"] == obj_key:
                    sx, sy = self._world_to_screen(core, p["position"]["x"], p["position"]["y"])
                    pygame.draw.circle(core.screen, COLORS["accent_yellow"], (sx, sy), 18, 3)
                    break
        elif obj_type == "wall":
            for wall in loc.get("walls", []):
                if wall["id"] == obj_key:
                    x1, y1 = self._world_to_screen(core, wall["x1"], wall["y1"])
                    x2, y2 = self._world_to_screen(core, wall["x2"], wall["y2"])
                    pygame.draw.line(core.screen, COLORS["accent_yellow"], (x1, y1), (x2, y2), 4)
                    break
        elif obj_type == "room":
            for room in loc.get("rooms", []):
                if room["id"] == obj_key:
                    poly = room.get("polygon")
                    if poly and len(poly) >= 3:
                        screen_pts = [self._world_to_screen(core, p[0], p[1]) for p in poly]
                        pygame.draw.polygon(core.screen, COLORS["accent_yellow"], screen_pts, 3)
                    else:
                        rx, ry = self._world_to_screen(core, room["x"], room["y"])
                        rw = room["width"] * SCALE * core.zoom
                        rh = room["height"] * SCALE * core.zoom
                        pygame.draw.rect(core.screen, COLORS["accent_yellow"], (rx - 2, ry - 2, rw + 4, rh + 4), 3)
                    break

    def draw_ui(self, core):
        """Отрисовывает пользовательский интерфейс"""
        pygame.draw.rect(core.screen, COLORS["bg_menu"], (0, 0, core.screen.get_width(), core.menu_height))
        pygame.draw.line(core.screen, COLORS["border"], (0, core.menu_height), (core.screen.get_width(), core.menu_height))
        for btn in core.menu_buttons: btn.draw(core.screen, core.font)

        toolbar_y = core.menu_height
        pygame.draw.rect(core.screen, COLORS["bg_panel"], (0, toolbar_y, core.screen.get_width() - core.panel_width, core.toolbar_height))
        pygame.draw.line(core.screen, COLORS["border"], (0, toolbar_y + core.toolbar_height), (core.screen.get_width() - core.panel_width, toolbar_y + core.toolbar_height))
        for btn in core.toolbar_buttons: btn.draw(core.screen, core.font)

        if core.object_dropdown: core.object_dropdown.draw(core.screen, core.font, core.font_small)
        core.property_panel.draw(core.screen, core.font, core.font_small)
        self._draw_status_bar(core)
        if core.toast_timer > 0: self._draw_toast(core)

    def _draw_status_bar(self, core):
        """Отрисовывает статусную строку"""
        screen_h = core.screen.get_height()
        status_y = screen_h - core.status_height
        pygame.draw.rect(core.screen, COLORS["bg_menu"], (0, status_y, core.screen.get_width(), core.status_height))
        pygame.draw.line(core.screen, COLORS["border"], (0, status_y), (core.screen.get_width(), status_y))

        mx, my = pygame.mouse.get_pos()
        wx, wy = self._screen_to_world(core, mx, my) if core.mode == MODE_LOCAL else (0, 0)

        if core.mode == MODE_LOCAL:
            undo_info = f" | Отмена:{core.undo.undo_label}" if core.undo.can_undo else ""
            camp_info = f" | Кампания: {core.cm.campaign_data.get('name', core.cm.current_campaign_name or '?')}" if core.cm.is_open else " | (без кампании)"
            info = f"X:{wx:.1f} Y:{wy:.1f} | Этаж:{core.current_z} | Zoom:{core.zoom:.1f}x | {core.current_file or '—'}{camp_info}{undo_info}"
        else:
            info = f"Карта мира | Локаций: {len(core.dm.locations)}"

        text = core.font_small.render(info, True, COLORS["text_dim"])
        core.screen.blit(text, (10, status_y + 5))

        hints = "[TAB] Мир/Лок | [PgUp/PgDn] Этаж | [Ctrl+S] Save | [Ctrl+Z/Q] Undo/Redo | [Ctrl+C/V] Copy/Paste | [+/-] Зум"
        hint_text = core.font_small.render(hints, True, COLORS["text_dim"])
        core.screen.blit(hint_text, (core.screen.get_width() - hint_text.get_width() - 10, status_y + 5))

    def _draw_toast(self, core):
        """Отрисовывает всплывающее сообщение"""
        if not core.toast_message: return
        padding = 15
        text = core.font.render(core.toast_message, True, COLORS["text_highlight"])
        w = text.get_width() + padding * 2
        h = text.get_height() + padding
        x = (core.screen.get_width() - w) // 2
        y = core.screen.get_height() - h - 50
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((30, 30, 40, 220))
        core.screen.blit(overlay, (x, y))
        pygame.draw.rect(core.screen, COLORS["border"], (x, y, w, h), 1, border_radius=6)
        core.screen.blit(text, (x + padding, y + padding // 2))

    def _find_room_perimeter_walls(self, core, room: dict) -> list:
        """Находит стены, совпадающие с рёбрами комнаты"""
        if not core.current_file: return []
        loc = core.dm.locations[core.current_file]
        walls = loc.get("walls", [])
        if not walls: return []
        edges = []
        poly = room.get("polygon")
        return []
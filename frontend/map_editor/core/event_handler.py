"""
map_editor/core/event_handler.py
Обработка событий ввода: мышь, клавиатура, тулбар.
"""
import pygame
from typing import Any, Dict, Optional, Tuple

from core.commands import (
    MoveEntityCommand,
    ResizeObjectCommand,
    RotateObjectCommand,
    MirrorObjectCommand,
    SimpleNodeUpdateCommand,
    RenameCommand,
)
from ui.dialogs import ModalDialog

from tools.constants import (
    TOOL_WALL, TOOL_ROOM, TOOL_NODE, MODE_WORLD, MODE_LOCAL
)

SCALE = 20
ZOOM_STEP = 1.2
MIN_ZOOM = 0.4
MAX_ZOOM = 5.0

MODE_WORLD = "world"
MODE_LOCAL = "local"

class EventHandler:
    """Управляет всей обработкой ввода в редакторе карт"""

    def handle_event(self, core, event: pygame.event.Event):
        """Маршрутизатор событий"""
        mx, my = pygame.mouse.get_pos()

        # Горячие клавиши
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if core.wall_drawing:
                    core.wall_drawing = False
                    core.wall_start = None
                elif core.room_drawing:
                    core.room_drawing = False
                    core.room_start = None
                elif core.node_link_start is not None:
                    core.node_link_start = None
                    core._show_toast("Создание связи отменено")
                elif core.selected_object is not None or core.tool is not None:
                    core.selected_object = None
                    core._set_tool(None)
                else:
                    core._running = False  # Выход в главное меню

            elif event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
                # Удаление выбранного объекта
                if core.selected_object and core.tool is None:
                    core._delete_at(mx, my)

            elif event.key == pygame.K_TAB:
                core._toggle_mode()
            elif event.key == pygame.K_PAGEUP:
                core.current_z += 1
                core._show_toast(f"Этаж: {core.current_z}")
            elif event.key == pygame.K_PAGEDOWN:
                core.current_z = max(0, core.current_z - 1)
                core._show_toast(f"Этаж: {core.current_z}")

            elif event.key == pygame.K_s and pygame.key.get_mods() & pygame.KMOD_CTRL:
                if core.current_file:
                    if core.cm.is_open:
                        core.cm.save_location(core.current_file)
                    else:
                        core.dm.save(core.current_file)
                    core._rebuild_spatial_registry()
                    core._show_toast(f"Сохранено: {core.current_file}")

            elif event.key == pygame.K_z and pygame.key.get_mods() & pygame.KMOD_CTRL:
                label = core.undo.undo()
                if label:
                    core.selected_object = None
                    core._show_toast(f"Отменено: {label}")
                else:
                    core._show_toast("Нечего отменять")

            elif event.key == pygame.K_q and pygame.key.get_mods() & pygame.KMOD_CTRL:
                label = core.undo.redo()
                if label:
                    core.selected_object = None
                    core._show_toast(f"Возвращено: {label}")
                else:
                    core._show_toast("Нечего возвращать")

            elif event.key == pygame.K_c and pygame.key.get_mods() & pygame.KMOD_CTRL:
                core._copy_selection()

            elif event.key == pygame.K_F2:
                # F2 — переименовать выделенный объект
                if core.selected_object and core.tool is None:
                    mx, my = pygame.mouse.get_pos()
                    core._handle_double_click(mx, my)

            elif event.key == pygame.K_v and pygame.key.get_mods() & pygame.KMOD_CTRL:
                core._paste_clipboard()

            elif (
                event.key == pygame.K_PLUS
                or event.key == pygame.K_EQUALS
                or event.key == pygame.K_KP_PLUS
            ):
                core._zoom(ZOOM_STEP, mx, my)
            elif event.key == pygame.K_MINUS or event.key == pygame.K_KP_MINUS:
                core._zoom(1 / ZOOM_STEP, mx, my)
            elif event.key == pygame.K_0:
                core.zoom = 1.0
                core._center_camera()

        # Зум колёсиком мыши
        elif event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            if event.y > 0:
                core._zoom(ZOOM_STEP, mx, my)
            elif event.y < 0:
                core._zoom(1 / ZOOM_STEP, mx, my)

        # UI элементы
        for btn in core.menu_buttons:
            if btn.handle_event(event):
                return

        for btn in core.toolbar_buttons:
            if btn.handle_event(event):
                return

        if core.object_dropdown and core.object_dropdown.handle_event(event):
            return

        # Хэндлы ресайза на холсте — максимальный приоритет
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if (
                core.tool is None
                and core.selected_object
                and core.selected_object[0] == "object"
            ):
                for handle in core._get_resize_handles(core.selected_object[1]):
                    if handle["rect"].collidepoint(mx, my):
                        obj = next(
                            (
                                o
                                for o in core.dm.locations[core.current_file]["objects"]
                                if o.get("id") == core.selected_object[1]
                            ),
                            None,
                        )
                        if obj:
                            core._resizing = {
                                "obj_id": core.selected_object[1],
                                "handle": handle,
                                "start_mx": mx,
                                "start_my": my,
                                "start_w": obj["size"]["w"],
                                "start_h": obj["size"]["h"],
                            }
                        return

        # Перетаскивание выделенной сущности — после хэндлов и кнопок
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if (
                core.tool is None
                and core.selected_object
                and not core._resizing
                and not core.property_panel.rect.collidepoint(mx, my)
            ):
                if core._is_on_selected(mx, my) and core.selected_object is not None:
                    etype, eid = core.selected_object
                    orig = core._get_drag_orig(etype, eid)
                    if orig:
                        core._dragging_entity = {
                            "start_mx": mx,
                            "start_my": my,
                            "orig": orig,
                        }
                    return

        # Кнопки поворота/зеркала на холсте — приоритет над панелью свойств
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if (
                core.tool is None
                and core.selected_object
                and core.selected_object[0] == "object"
                and not core.property_panel.rect.collidepoint(mx, my)
            ):
                for btn in core._get_rotation_buttons(core.selected_object[1]):
                    if btn["rect"].collidepoint(mx, my):
                        obj = next(
                            (
                                o
                                for o in core.dm.locations[core.current_file]["objects"]
                                if o.get("id") == core.selected_object[1]
                            ),
                            None,
                        )
                        if obj:
                            if btn.get("action") == "mirror":
                                core.undo.push(
                                    MirrorObjectCommand(
                                        core.dm,
                                        core.current_file,
                                        core.selected_object[1],
                                        obj.get("mirrored", False),
                                    )
                                )
                            else:
                                try:
                                    old_rot = float(obj.get("rotation") or 0)
                                except (ValueError, TypeError):
                                    old_rot = 0.0
                                core.undo.push(
                                    RotateObjectCommand(
                                        core.dm,
                                        core.current_file,
                                        core.selected_object[1],
                                        old_rot,
                                        btn["delta"],
                                    )
                                )
                        return

        # Панель свойств
        action = core.property_panel.handle_event(event)
        if action:
            core._handle_property_action(action)
            return
        # Поглощаем клики внутри панели — чтобы не деселектить объекты
        if (
            event.type == pygame.MOUSEBUTTONDOWN
            and core.property_panel.rect.collidepoint(event.pos)
        ):
            return

        # Основное взаимодействие
        if core.mode == MODE_WORLD:
            self._handle_world_event(core, event)
        else:
            self._handle_local_event(core, event)

    def _handle_world_event(self, core, event: pygame.event.Event):
        """Обрабатывает события в режиме карты мира"""
        mx, my = pygame.mouse.get_pos()

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                mods = pygame.key.get_mods()
                # Shift+ЛКМ — перетаскивание локации (смещение origin)
                if mods & pygame.KMOD_SHIFT:
                    for fname, data in core.dm.locations.items():
                        rect = core._get_location_screen_rect(fname)
                        if rect and rect.collidepoint(mx, my):
                            core._dragging_location = fname
                            core._drag_offset = (mx - rect.x, my - rect.y)
                            return
                else:
                    # ЛКМ — выбор локации и переход в режим редактирования
                    for fname, data in core.dm.locations.items():
                        rect = core._get_location_screen_rect(fname)
                        if rect and rect.collidepoint(mx, my):
                            core.current_file = fname
                            core._toggle_mode()
                            return

            elif event.button == 2:
                # Колёсико — перемещение камеры
                core.dragging_camera = True

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 2:
                core.dragging_camera = False
            if (
                event.button == 1
                and hasattr(core, "_dragging_location")
                and core._dragging_location
            ):
                core._dragging_location = None

        elif event.type == pygame.MOUSEMOTION:
            if core.dragging_camera:
                core.camera_x += event.rel[0]
                core.camera_y += event.rel[1]
            elif hasattr(core, "_dragging_location") and core._dragging_location:
                # Перетаскивание локации — обновляем origin
                fname = core._dragging_location
                data = core.dm.locations.get(fname)
                if data:
                    new_sx = mx - core._drag_offset[0]
                    new_sy = my - core._drag_offset[1]
                    # Конвертируем экранные координаты обратно в мировые
                    data["origin"]["x"] = (new_sx - core.camera_x) / (SCALE * core.zoom)
                    data["origin"]["y"] = (new_sy - core.camera_y) / (SCALE * core.zoom)

    def _handle_local_event(self, core, event: pygame.event.Event):
        """Обрабатывает события в режиме редактирования локации"""
        mx, my = pygame.mouse.get_pos()

        # Проверяем что клик не в UI
        if my < core.menu_height + core.toolbar_height:
            return
        if mx > core.screen.get_width() - core.panel_width:
            return

        world_x, world_y = core.screen_to_world(mx, my)
        grid_x, grid_y = core.snap_to_grid(world_x, world_y, 0.5)

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # ЛКМ
                # Проверка двойного клика (< 400мс, < 8 пикселей)
                now = pygame.time.get_ticks()
                dx = abs(mx - core._last_click_pos[0])
                dy = abs(my - core._last_click_pos[1])
                if now - core._last_click_time < 400 and dx < 8 and dy < 8:
                    core._handle_double_click(mx, my)
                    core._last_click_time = 0
                else:
                    core._handle_left_click(mx, my, world_x, world_y, grid_x, grid_y)
                core._last_click_time = now
                core._last_click_pos = (mx, my)

            elif event.button == 2:  # Колёсико — двигать камеру
                core.dragging_camera = True
            elif event.button == 3:  # ПКМ
                if core.tool is not None:
                    # В режиме создания — выйти в покой, выделение остаётся
                    core._set_tool(None)
                else:
                    # В режиме покоя — снять выделение
                    core.selected_object = None

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                # S-OBS-05: Прямой триггер обновления Observatory при отпускании мыши
                if core.observatory_data is not None:
                    core._spatial_dirty = True
                    core._last_edit_time = pygame.time.get_ticks() - 300  # Немедленный запрос

                if core._resizing:
                    obj = next(
                        (
                            o
                            for o in core.dm.locations[core.current_file]["objects"]
                            if o.get("id") == core._resizing["obj_id"]
                        ),
                        None,
                    )
                    if obj:
                        new_w = round(obj["size"]["w"], 2)
                        new_h = round(obj["size"]["h"], 2)
                        old_w = round(core._resizing["start_w"], 2)
                        old_h = round(core._resizing["start_h"], 2)
                        if abs(new_w - old_w) > 0.01 or abs(new_h - old_h) > 0.01:
                            core.undo.push(
                                ResizeObjectCommand(
                                    core.dm,
                                    core.current_file,
                                    core._resizing["obj_id"],
                                    old_w,
                                    old_h,
                                    new_w,
                                    new_h,
                                )
                            )
                    core._resizing = None
                elif core._dragging_entity and core.selected_object is not None:
                    mx_now, my_now = event.pos
                    total_dx = mx_now - core._dragging_entity["start_mx"]
                    total_dy = my_now - core._dragging_entity["start_my"]
                    scale = 1.0 / (SCALE * core.zoom)
                    dx_world = round(total_dx * scale, 2)
                    dy_world = round(total_dy * scale, 2)
                    if abs(dx_world) > 0.01 or abs(dy_world) > 0.01:
                        etype, eid = core.selected_object
                        drag_wall = etype == "object" and bool(
                            core._dragging_entity["orig"].get("wall_id")
                        )
                        cmd = MoveEntityCommand(
                            core.dm,
                            core.current_file,
                            etype,
                            eid,
                            dx_world,
                            dy_world,
                            drag_wall,
                        )
                        cmd._skip_do = True
                        core.undo.push(cmd)
                    core._dragging_entity = None
                else:
                    core._handle_left_release(mx, my, world_x, world_y, grid_x, grid_y)
            elif event.button == 2:  # Колёсико
                core.dragging_camera = False

        elif event.type == pygame.MOUSEMOTION:
            if core._dragging_entity and core.selected_object is not None:
                mx_now, my_now = event.pos
                total_dx = mx_now - core._dragging_entity["start_mx"]
                total_dy = my_now - core._dragging_entity["start_my"]
                scale = 1.0 / (SCALE * core.zoom)
                dx_world = total_dx * scale
                dy_world = total_dy * scale
                if core.selected_object is not None:
                    etype, eid = core.selected_object
                    core._apply_drag(
                        etype, eid, core._dragging_entity["orig"], dx_world, dy_world
                    )
            elif core._resizing:
                obj = next(
                    (
                        o
                        for o in core.dm.locations[core.current_file]["objects"]
                        if o.get("id") == core._resizing["obj_id"]
                    ),
                    None,
                )
                if obj:
                    mx_now, my_now = event.pos
                    total_dx = mx_now - core._resizing["start_mx"]
                    total_dy = my_now - core._resizing["start_my"]
                    scale = 1.0 / (SCALE * core.zoom)
                    handle = core._resizing["handle"]

                    if handle["axis"] == "w":
                        # Только ширина (для объектов в стенах)
                        dw = total_dx * scale * handle["dir"]
                        obj["size"]["w"] = max(0.3, core._resizing["start_w"] + dw)
                    elif handle["axis"] == "h":
                        # Только высота (для вертикальных объектов в стенах)
                        dh = total_dy * scale * handle["dir"]
                        obj["size"]["h"] = max(0.3, core._resizing["start_h"] + dh)
                    else:
                        # Свободный ресайз по обоим осям
                        dw = total_dx * scale * handle["dir_x"]
                        dh = total_dy * scale * handle["dir_y"]
                        obj["size"]["w"] = max(0.3, core._resizing["start_w"] + dw)
                        obj["size"]["h"] = max(0.3, core._resizing["start_h"] + dh)
            elif core.dragging_camera:
                core.camera_x += event.rel[0]
                core.camera_y += event.rel[1]
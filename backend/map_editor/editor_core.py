"""
map_editor/editor_core.py
Главный редактор карт - ядро приложения
"""
import pygame
import sys
import math
from typing import Optional, Tuple, Dict, List, Any
from dataclasses import dataclass

from copy import deepcopy

from data_manager import DataManager, OBJECT_PRESETS, PORTAL_TYPES
from undo_manager import (
    UndoManager, AddWallCommand, RemoveWallCommand,
    AddRoomCommand, RemoveRoomCommand,
    AddNodeCommand, RemoveNodeCommand,
    AddObjectCommand, RemoveObjectCommand,
    AddPortalCommand, RemovePortalCommand,
    TogglePassabilityCommand, RotateObjectCommand, PasteCommand,
    CompoundCommand,
)
from campaign_manager import CampaignManager
from ui_components import (
    COLORS, Button, ToggleButton, TextInput, Dropdown,
    ModalDialog, Toolbar, PropertyPanel, DropDownMenu
)

# === Константы редактора ===
SCALE = 40  # пикселей в 1 метре
MIN_ZOOM = 0.3
MAX_ZOOM = 3.0
ZOOM_STEP = 1.2

# Режимы работы
MODE_WORLD = "world"      # Карта мира - выбор локаций
MODE_LOCAL = "local"      # Редактирование локации

# Инструменты
TOOL_SELECT = "select"
TOOL_WALL = "wall"        # Рисование стен
TOOL_ROOM = "room"        # Создание комнат
TOOL_OBJECT = "object"    # Размещение объектов
TOOL_PORTAL = "portal"    # Размещение порталов
TOOL_DELETE = "delete"    # Удаление

# Цвета объектов
OBJECT_COLORS = {
    "wall": (139, 69, 19),
    "bar": (101, 67, 33),
    "table": (139, 115, 85),
    "chair": (160, 82, 45),
    "door": (210, 105, 30),
    "window": (135, 206, 235),
    "stairs": (105, 105, 105),
    "decoration": (144, 238, 144),
}


@dataclass
class DragState:
    """Состояние перетаскивания"""
    active: bool = False
    start_x: float = 0
    start_y: float = 0
    item_type: str = ""  # "wall", "room", "node", "object"
    item_key: Any = None


class EditorCore:
    """Главный класс редактора карт"""
    
    def __init__(self, width: int = 1400, height: int = 900):
        pygame.init()
        pygame.display.set_caption("R4 Spatial Map Editor v2.0")
        self.screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        
        # Шрифты
        self.font = pygame.font.SysFont("consolas", 14)
        self.font_bold = pygame.font.SysFont("consolas", 14, bold=True)
        self.font_small = pygame.font.SysFont("consolas", 11)
        self.font_large = pygame.font.SysFont("consolas", 16, bold=True)
        
        # Данные
        self.dm = DataManager()
        self.cm = CampaignManager(self.dm)
        self.undo = UndoManager()
        self.clipboard = {"walls": [], "objects": [], "origin": (0.0, 0.0)}
        self.current_z: int = 0
        
        # Состояние
        self.mode = MODE_WORLD
        self.current_file: Optional[str] = None
        self.tool = TOOL_SELECT
        self.selected_object: Optional[Tuple[str, Any]] = None
        
        # Камера
        self.camera_x = 0.0
        self.camera_y = 0.0
        self.zoom = 1.0
        self.dragging_camera = False
        
        # Рисование
        self.wall_drawing = False
        self.wall_start: Optional[Tuple[float, float]] = None
        self.room_drawing = False
        self.room_start: Optional[Tuple[float, float]] = None
        
        # UI
        self.menu_height = 30
        self.toolbar_height = 45
        self.panel_width = 300
        self.status_height = 25
        
        self.dialog: Optional[ModalDialog] = None
        self.toast_message = ""
        self.toast_timer = 0
        
        # Настройки
        self.show_grid = True
        self.show_walls = True
        self.show_objects = True
        self.show_portals = True
        self.show_rooms = True
        
        # Выбранные типы
        self.selected_object_type = "table"
        self.selected_portal_type = "door"
        
        # Инициализация UI
        self._init_ui()
        
        # Приветственное сообщение
        self._show_toast("Добро пожаловать! Создайте локацию через меню File")
    
    def _init_ui(self):
        """Инициализирует элементы интерфейса"""
        screen_w = self.screen.get_width()
        screen_h = self.screen.get_height()
        
        # === Меню (кнопки в верхней панели) ===
        self.menu_buttons = []
        
        # File
        self.btn_file = Button(10, 2, 60, 26, "File", on_click=self._show_file_menu)
        self.menu_buttons.append(self.btn_file)
        
        # View
        self.btn_view = Button(75, 2, 60, 26, "View", on_click=self._show_view_menu)
        self.menu_buttons.append(self.btn_view)
        
        # === Тулбар ===
        toolbar_y = self.menu_height + 5
        self.toolbar_buttons = []
        
        # Группа: Навигация
        x = 10
        self.btn_tool_select = ToggleButton(x, toolbar_y, 80, 32, "👆 Выбор", 
                                           on_toggle=lambda s: self._set_tool(TOOL_SELECT) if s else None)
        self.btn_tool_select.state = True
        self.toolbar_buttons.append(self.btn_tool_select)
        x += 90
        
        # Группа: Строительство
        x += 10
        self.btn_tool_wall = ToggleButton(x, toolbar_y, 80, 32, "🧱 Стена",
                                         on_toggle=lambda s: self._set_tool(TOOL_WALL) if s else None)
        self.toolbar_buttons.append(self.btn_tool_wall)
        x += 90
        
        self.btn_tool_room = ToggleButton(x, toolbar_y, 90, 32, "📦 Комната",
                                         on_toggle=lambda s: self._set_tool(TOOL_ROOM) if s else None)
        self.toolbar_buttons.append(self.btn_tool_room)
        x += 100
        
        # Группа: Объекты
        x += 10
        self.btn_tool_object = ToggleButton(x, toolbar_y, 90, 32, "🪑 Объект",
                                           on_toggle=lambda s: self._set_tool(TOOL_OBJECT) if s else None)
        self.toolbar_buttons.append(self.btn_tool_object)
        x += 100
        
        self.btn_tool_portal = ToggleButton(x, toolbar_y, 90, 32, "🚪 Портал",
                                           on_toggle=lambda s: self._set_tool(TOOL_PORTAL) if s else None)
        self.toolbar_buttons.append(self.btn_tool_portal)
        x += 100
        
        # Группа: Удаление
        x += 10
        self.btn_tool_delete = ToggleButton(x, toolbar_y, 90, 32, "🗑️ Удалить",
                                           on_toggle=lambda s: self._set_tool(TOOL_DELETE) if s else None)
        self.toolbar_buttons.append(self.btn_tool_delete)
        
        # === Панель свойств ===
        panel_x = screen_w - self.panel_width
        panel_y = self.menu_height + self.toolbar_height + 10
        panel_h = screen_h - panel_y - self.status_height - 10
        self.property_panel = PropertyPanel(panel_x, panel_y, self.panel_width, panel_h)
        
        # === Дропдауны для типов объектов ===
        self.object_dropdown: Optional[Dropdown] = None
        self.portal_dropdown: Optional[Dropdown] = None
        
        # === Кнопки в панели ===
        self.panel_buttons = []
    
    def _set_tool(self, tool: str):
        """Устанавливает текущий инструмент"""
        self.tool = tool
        
        # Сбрасываем все кнопки
        for btn in self.toolbar_buttons:
            if isinstance(btn, ToggleButton):
                btn.state = False
        
        # Устанавливаем нужную кнопку
        tool_buttons = {
            TOOL_SELECT: self.btn_tool_select,
            TOOL_WALL: self.btn_tool_wall,
            TOOL_ROOM: self.btn_tool_room,
            TOOL_OBJECT: self.btn_tool_object,
            TOOL_PORTAL: self.btn_tool_portal,
            TOOL_DELETE: self.btn_tool_delete,
        }
        if tool in tool_buttons:
            tool_buttons[tool].state = True
        
        # Показываем подсказку
        tool_names = {
            TOOL_SELECT: "Выделение: кликайте по объектам",
            TOOL_WALL: "Стены: кликните и потяните для рисования",
            TOOL_ROOM: "Комнаты: кликните и потяните для создания",
            TOOL_OBJECT: "Объекты: кликните для размещения",
            TOOL_PORTAL: "Порталы: кликните для размещения",
            TOOL_DELETE: "Удаление: кликните по объекту для удаления",
        }
        self._show_toast(tool_names.get(tool, ""))
        
        # Создаём/убираем дропдауны
        self._update_dropdowns()
    
    def _update_dropdowns(self):
        """Обновляет дропдауны в зависимости от инструмента"""
        self.object_dropdown = None
        self.portal_dropdown = None
        
        if self.tool == TOOL_OBJECT:
            options = list(OBJECT_PRESETS.keys())
            self.object_dropdown = Dropdown(
                700, self.menu_height + 8, 120, 28,
                options=options, label="Тип"
            )
            self.object_dropdown.selected = list(OBJECT_PRESETS.keys()).index(self.selected_object_type)
            self.object_dropdown.on_select = lambda i, opt: setattr(self, 'selected_object_type', opt)
            
        elif self.tool == TOOL_PORTAL:
            options = [p["label"] for p in PORTAL_TYPES.values()]
            self.portal_dropdown = Dropdown(
                700, self.menu_height + 8, 140, 28,
                options=options, label="Тип"
            )
            self.portal_dropdown.selected = list(PORTAL_TYPES.keys()).index(self.selected_portal_type)
            self.portal_dropdown.on_select = lambda i, opt: setattr(
                self, 'selected_portal_type', list(PORTAL_TYPES.keys())[i]
            )
    
    def _show_file_menu(self):
        """Показывает выпадающее меню File"""
        items = [
            {"label": "Новая кампания...", "action": self._dialog_create_campaign},
            {"label": "Открыть кампанию...", "action": self._dialog_open_campaign},
            {"label": "Закрыть кампанию", "action": self._close_campaign,
             "disabled": not self.cm.is_open},
            {"type": "separator"},
            {"label": "Новая локация...", "action": self._dialog_new_location,
             "disabled": not self.cm.is_open},
            {"label": "Сохранить", "action": self._quick_save,
             "shortcut": "Ctrl+S", "disabled": not self.current_file},
            {"label": "Сохранить как...", "action": self._dialog_save_as,
             "disabled": not self.current_file},
            {"label": "Сохранить всё", "action": self._save_all,
             "disabled": not self.cm.is_open},
            {"type": "separator"},
            {"label": "Экспорт в ZIP...", "action": self._dialog_export_zip,
             "disabled": not self.cm.is_open},
            {"label": "Импорт из ZIP...", "action": self._dialog_import_zip},
        ]
        btn_rect = self.btn_file.rect
        self.dialog = DropDownMenu(btn_rect.x, btn_rect.bottom, items)

    def _dialog_create_campaign(self):
        """Диалог создания новой кампании"""
        fields = [
            {"key": "folder", "label": "Папка (латиница)", "value": "my_campaign"},
            {"key": "name", "label": "Название", "value": "Моя кампания"},
            {"key": "desc", "label": "Описание", "value": ""},
        ]
        def on_confirm(inputs):
            ok, err = self.cm.create_campaign(inputs["folder"], inputs["name"], inputs["desc"])
            if ok:
                self.cm.open_campaign(inputs["folder"])
                self.current_file = None
                self.mode = MODE_WORLD
                self.undo.clear()
                self._show_toast(f"Кампания: {inputs['name']}")
            else:
                self._show_toast(f"Ошибка: {err}")
        self.dialog = ModalDialog(self.screen, "Новая кампания", fields, on_confirm)

    def _dialog_open_campaign(self):
        """Диалог выбора кампании из списка"""
        campaigns = self.cm.list_campaigns()
        if not campaigns:
            self._show_toast("Нет ни одной кампании")
            return
        options = [f"{c['name']} ({c['location_count']} лок.)" for c in campaigns]
        folders = [c["folder"] for c in campaigns]

        fields = [{"key": "choice", "label": "Кампания", "value": options[0], "type": "choice",
                    "options": options}]
        def on_confirm(inputs):
            idx = options.index(inputs["choice"])
            ok, err = self.cm.open_campaign(folders[idx])
            if ok:
                self.current_file = None
                self.mode = MODE_WORLD
                self.undo.clear()
                self._show_toast(f"Открыта: {self.cm.campaign_data['name']}")
            else:
                self._show_toast(f"Ошибка: {err}")
        self.dialog = ModalDialog(self.screen, "Открыть кампанию", fields, on_confirm)

    def _close_campaign(self):
        """Закрывает текущую кампанию"""
        name = self.cm.campaign_data.get("name", "") if self.cm.campaign_data else ""
        self.cm.close_campaign()
        self.current_file = None
        self.mode = MODE_WORLD
        self.undo.clear()
        self._show_toast(f"Кампания закрыта: {name}")

    def _dialog_new_location(self):
        """Диалог создания новой локации внутри кампании"""
        fields = [
            {"key": "filename", "label": "Имя файла", "value": "new_location.json"},
            {"key": "label", "label": "Название локации", "value": "Новая локация"},
            {"key": "width", "label": "Ширина (м)", "value": "20", "type": "int"},
            {"key": "height", "label": "Высота (м)", "value": "15", "type": "int"},
            {"key": "outdoor", "label": "Уличная (да/нет)", "value": "нет"},
        ]
        def on_confirm(inputs):
            try:
                w = int(inputs.get("width", 20))
                h = int(inputs.get("height", 15))
                is_outdoor = inputs.get("outdoor", "").lower() in ("да", "yes", "y", "д")
                ok, err = self.dm.create_location(inputs["filename"], w, h, inputs["label"], is_outdoor)
                if ok:
                    self.cm.save_location(inputs["filename"])
                    self.current_file = inputs["filename"]
                    self.mode = MODE_LOCAL
                    self.undo.clear()
                    self._center_camera()
                    self._show_toast(f"Создана: {inputs['label']}")
                else:
                    self._show_toast(f"Ошибка: {err}")
            except ValueError:
                self._show_toast("Ошибка: неверный формат размеров")
        self.dialog = ModalDialog(self.screen, "Новая локация", fields, on_confirm)

    def _quick_save(self):
        """Быстрое сохранение текущей локации"""
        if not self.current_file:
            return
        if self.cm.is_open:
            self.cm.save_location(self.current_file)
        else:
            self.dm.save(self.current_file)
        self._show_toast(f"Сохранено: {self.current_file}")

    def _dialog_save_as(self):
        """Диалог сохранения локации под другим именем"""
        fields = [
            {"key": "filename", "label": "Новое имя файла", "value": self.current_file},
        ]
        def on_confirm(inputs):
            ok, err = self.cm.save_location_as(self.current_file, inputs["filename"])
            if ok:
                self.current_file = inputs["filename"]
                self._show_toast(f"Сохранено как: {inputs['filename']}")
            else:
                self._show_toast(f"Ошибка: {err}")
        self.dialog = ModalDialog(self.screen, "Сохранить как...", fields, on_confirm)

    def _save_all(self):
        """Сохраняет все локации кампании"""
        count = self.cm.save_all_locations()
        self._show_toast(f"Сохранено локаций: {count}")

    def _dialog_export_zip(self):
        """Диалог экспорта кампании в zip"""
        name = self.cm.campaign_data.get("name", "campaign") if self.cm.campaign_data else "campaign"
        safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
        fields = [
            {"key": "path", "label": "Путь к файлу", "value": f"{safe}.zip"},
        ]
        def on_confirm(inputs):
            ok, err = self.cm.export_to_zip(inputs["path"])
            if ok:
                self._show_toast(f"Экспортировано: {inputs['path']}")
            else:
                self._show_toast(f"Ошибка: {err}")
        self.dialog = ModalDialog(self.screen, "Экспорт в ZIP", fields, on_confirm)

    def _dialog_import_zip(self):
        """Диалог импорта кампании из zip"""
        fields = [
            {"key": "path", "label": "Путь к ZIP-файлу", "value": ""},
            {"key": "folder", "label": "Имя папки кампании", "value": "imported_campaign"},
        ]
        def on_confirm(inputs):
            if not inputs["path"]:
                self._show_toast("Укажите путь к файлу")
                return
            ok, err = self.cm.import_from_zip(inputs["path"], inputs["folder"])
            if ok:
                self._show_toast(f"Импортировано: {inputs['folder']}")
            else:
                self._show_toast(f"Ошибка: {err}")
        self.dialog = ModalDialog(self.screen, "Импорт из ZIP", fields, on_confirm)
    
    def _show_view_menu(self):
        """Переключает видимость элементов"""
        self.show_grid = not self.show_grid
        self._show_toast(f"Сетка: {'вкл' if self.show_grid else 'выкл'}")
    
    def _show_toast(self, message: str, duration: int = 180):
        """Показывает временное сообщение"""
        self.toast_message = message
        self.toast_timer = duration
    
    def _center_camera(self):
        """Центрирует камеру на текущей локации"""
        if self.current_file and self.current_file in self.dm.locations:
            loc = self.dm.locations[self.current_file]
            cx = loc["origin"]["x"] + loc["size"]["w"] / 2
            cy = loc["origin"]["y"] + loc["size"]["h"] / 2
            screen_cx = (self.screen.get_width() - self.panel_width) / 2
            screen_cy = (self.screen.get_height() - self.menu_height - self.toolbar_height) / 2
            self.camera_x = screen_cx - cx * SCALE * self.zoom
            self.camera_y = screen_cy - cy * SCALE * self.zoom + self.menu_height + self.toolbar_height
    
    # === Координатные преобразования ===
    def world_to_screen(self, wx: float, wy: float) -> Tuple[int, int]:
        """Преобразует мировые координаты в экранные"""
        sx = int(wx * SCALE * self.zoom + self.camera_x)
        sy = int(wy * SCALE * self.zoom + self.camera_y)
        return (sx, sy)
    
    def screen_to_world(self, sx: int, sy: int) -> Tuple[float, float]:
        """Преобразует экранные координаты в мировые"""
        wx = (sx - self.camera_x) / (SCALE * self.zoom)
        wy = (sy - self.camera_y) / (SCALE * self.zoom)
        return (wx, wy)
    
    def snap_to_grid(self, x: float, y: float, grid_size: float = 0.5) -> Tuple[float, float]:
        """Привязывает координаты к сетке"""
        return (round(x / grid_size) * grid_size, round(y / grid_size) * grid_size)
    
    def _rotated_rect_points(self, cx: float, cy: float, w: float, h: float, angle_deg: float) -> List[Tuple[float, float]]:
        """Возвращает 4 точки повёрнутого прямоугольника"""
        angle = math.radians(angle_deg)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        hw, hh = w / 2, h / 2
        corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
        return [(x * cos_a - y * sin_a + cx, x * sin_a + y * cos_a + cy) for x, y in corners]

    def _get_rotation_buttons(self, obj_index: int) -> List[Dict[str, Any]]:
        """Возвращает кнопки поворота для выделенного объекта"""
        if not self.current_file or obj_index < 0:
            return []
        loc = self.dm.locations[self.current_file]
        if obj_index >= len(loc["objects"]):
            return []
        obj = loc["objects"][obj_index]
        sx, sy = self.world_to_screen(obj["position"]["x"], obj["position"]["y"])
        w = obj["size"]["w"] * SCALE * self.zoom
        h = obj["size"]["h"] * SCALE * self.zoom
        radius = max(w, h) / 2 + 14
        btn_r = 10
        return [
            {"rect": pygame.Rect(sx - radius - btn_r, sy - btn_r, btn_r * 2, btn_r * 2), "delta": -45},
            {"rect": pygame.Rect(sx + radius - btn_r, sy - btn_r, btn_r * 2, btn_r * 2), "delta": 45},
        ]

    def _copy_selection(self) -> None:
        """Копирует выделенный объект или стену в буфер"""
        if not self.current_file or not self.selected_object:
            return
        loc = self.dm.locations[self.current_file]
        obj_type, obj_key = self.selected_object
        self.clipboard = {"walls": [], "objects": [], "origin": (0.0, 0.0)}
        self.current_z: int = 0
        self.current_z: int = 0

        if obj_type == "object" and 0 <= obj_key < len(loc["objects"]):
            obj = loc["objects"][obj_key]
            self.clipboard["objects"] = [deepcopy(obj)]
            self.clipboard["origin"] = (obj["position"]["x"], obj["position"]["y"])
            self._show_toast(f"Скопирован: {obj['type']}")
        elif obj_type == "wall":
            wall = next((w for w in loc["walls"] if w["id"] == obj_key), None)
            if wall:
                self.clipboard["walls"] = [deepcopy(wall)]
                self.clipboard["origin"] = ((wall["x1"] + wall["x2"]) / 2,
                                            (wall["y1"] + wall["y2"]) / 2)
                self._show_toast("Скопирована стена")

    def _paste_clipboard(self) -> None:
        """Вставляет содержимое буфера в позицию курсора"""
        if not self.current_file:
            return
        if not self.clipboard["walls"] and not self.clipboard["objects"]:
            self._show_toast("Буфер обмена пуст")
            return

        mx, my = pygame.mouse.get_pos()
        wx, wy = self.screen_to_world(mx, my)
        gx, gy = self.snap_to_grid(wx, wy, 0.5)

        ox, oy = self.clipboard["origin"]
        dx, dy = gx - ox, gy - oy
        if abs(dx) < 0.1 and abs(dy) < 0.1:
            dx, dy = 1.0, 1.0

        new_walls = []
        for wall in self.clipboard["walls"]:
            w = deepcopy(wall)
            w.pop("id", None)
            w["x1"] = round(w["x1"] + dx, 2)
            w["y1"] = round(w["y1"] + dy, 2)
            w["x2"] = round(w["x2"] + dx, 2)
            w["y2"] = round(w["y2"] + dy, 2)
            new_walls.append(w)

        new_objects = []
        for obj in self.clipboard["objects"]:
            o = deepcopy(obj)
            o["position"]["x"] = round(o["position"]["x"] + dx, 2)
            o["position"]["y"] = round(o["position"]["y"] + dy, 2)
            new_objects.append(o)

        self.undo.push(PasteCommand(self.dm, self.current_file, new_walls, new_objects))
        self._show_toast(f"Вставлено: {len(new_objects)} obj, {len(new_walls)} wall")

    # === Главный цикл ===
    def run(self):
        """Главный цикл приложения"""
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    
                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                    self._init_ui()
                    
                elif self.dialog and getattr(self.dialog, 'active', False):
                    if self.dialog.handle_event(event):
                        continue
                else:
                    self._handle_event(event)
            
            self._update()
            self._draw()
            pygame.display.flip()
            self.clock.tick(60)
        
        pygame.quit()
        sys.exit()
    
    def _handle_event(self, event: pygame.event.Event):
        """Обрабатывает события ввода"""
        mx, my = pygame.mouse.get_pos()
        
        # Горячие клавиши
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.wall_drawing:
                    self.wall_drawing = False
                    self.wall_start = None
                elif self.room_drawing:
                    self.room_drawing = False
                    self.room_start = None
                else:
                    self.selected_object = None
                    self._set_tool(TOOL_SELECT)
                    
            elif event.key == pygame.K_TAB:
                self._toggle_mode()
                
            elif event.key == pygame.K_s and pygame.key.get_mods() & pygame.KMOD_CTRL:
                if self.current_file:
                    if self.cm.is_open:
                        self.cm.save_location(self.current_file)
                    else:
                        self.dm.save(self.current_file)
                    self._show_toast(f"Сохранено: {self.current_file}")
                    
            elif event.key == pygame.K_z and pygame.key.get_mods() & pygame.KMOD_CTRL:
                label = self.undo.undo()
                if label:
                    self.selected_object = None
                    self._show_toast(f"Отменено: {label}")
                else:
                    self._show_toast("Нечего отменять")
                    
            elif event.key == pygame.K_q and pygame.key.get_mods() & pygame.KMOD_CTRL:
                label = self.undo.redo()
                if label:
                    self.selected_object = None
                    self._show_toast(f"Возвращено: {label}")
                else:
                    self._show_toast("Нечего возвращать")

            elif event.key == pygame.K_c and pygame.key.get_mods() & pygame.KMOD_CTRL:
                self._copy_selection()

            elif event.key == pygame.K_v and pygame.key.get_mods() & pygame.KMOD_CTRL:
                self._paste_clipboard()
                    
            elif event.key == pygame.K_PLUS or event.key == pygame.K_EQUALS or event.key == pygame.K_KP_PLUS:
                self._zoom(ZOOM_STEP, mx, my)
            elif event.key == pygame.K_MINUS or event.key == pygame.K_KP_MINUS:
                self._zoom(1 / ZOOM_STEP, mx, my)
            elif event.key == pygame.K_0:
                self.zoom = 1.0
                self._center_camera()

        # Зум колёсиком мыши
        elif event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            if event.y > 0:
                self._zoom(ZOOM_STEP, mx, my)
            elif event.y < 0:
                self._zoom(1 / ZOOM_STEP, mx, my)

        # UI элементы
        for btn in self.menu_buttons:
            if btn.handle_event(event):
                return
        
        for btn in self.toolbar_buttons:
            if btn.handle_event(event):
                return
        
        if self.object_dropdown and self.object_dropdown.handle_event(event):
            return
        if self.portal_dropdown and self.portal_dropdown.handle_event(event):
            return
        
        # Панель свойств
        action = self.property_panel.handle_event(event)
        if action:
            self._handle_property_action(action)
            return
        
        # Основное взаимодействие
        if self.mode == MODE_WORLD:
            self._handle_world_event(event)
        else:
            self._handle_local_event(event)
    
    def _toggle_mode(self):
        """Переключает между режимами мира и локации"""
        if self.mode == MODE_WORLD:
            if self.current_file:
                self.mode = MODE_LOCAL
                self._center_camera()
                self.undo.clear()
                self._show_toast(f"Редактирование: {self.current_file}")
            else:
                self._show_toast("Сначала выберите или создайте локацию")
        else:
            self.mode = MODE_WORLD
            self.selected_object = None
            self._show_toast("Карта мира")
    
    def _zoom(self, factor: float, cx: int, cy: int):
        """Изменяет масштаб относительно точки"""
        old_zoom = self.zoom
        new_zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom * factor))
        
        # Корректируем камеру чтобы зум был к курсору
        world_x = (cx - self.camera_x) / (SCALE * old_zoom)
        world_y = (cy - self.camera_y) / (SCALE * old_zoom)
        
        self.zoom = new_zoom
        self.camera_x = cx - world_x * SCALE * new_zoom
        self.camera_y = cy - world_y * SCALE * new_zoom
    
    def _handle_world_event(self, event: pygame.event.Event):
        """Обрабатывает события в режиме карты мира"""
        mx, my = pygame.mouse.get_pos()
        
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # ЛКМ - выбор локации
                for fname, data in self.dm.locations.items():
                    rect = self._get_location_screen_rect(fname)
                    if rect and rect.collidepoint(mx, my):
                        self.current_file = fname
                        self._toggle_mode()
                        return
                        
            elif event.button == 2 or (event.button == 3 and pygame.key.get_mods() & pygame.KMOD_SHIFT):
                # Средняя кнопка или Shift+ПКМ - перемещение камеры
                self.dragging_camera = True
                
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button in (2, 3):
                self.dragging_camera = False
                
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging_camera:
                self.camera_x += event.rel[0]
                self.camera_y += event.rel[1]
    
    def _handle_local_event(self, event: pygame.event.Event):
        """Обрабатывает события в режиме редактирования локации"""
        mx, my = pygame.mouse.get_pos()
        
        # Проверяем что клик не в UI
        if my < self.menu_height + self.toolbar_height:
            return
        if mx > self.screen.get_width() - self.panel_width:
            return
        
        world_x, world_y = self.screen_to_world(mx, my)
        grid_x, grid_y = self.snap_to_grid(world_x, world_y, 0.5)
        
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # ЛКМ
                self._handle_left_click(mx, my, world_x, world_y, grid_x, grid_y)
                
            elif event.button == 3:  # ПКМ
                self.dragging_camera = True
                
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self._handle_left_release(mx, my, world_x, world_y, grid_x, grid_y)
            elif event.button == 3:
                self.dragging_camera = False
                
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging_camera:
                self.camera_x += event.rel[0]
                self.camera_y += event.rel[1]
    
    def _handle_left_click(self, mx: int, my: int, wx: float, wy: float, gx: float, gy: float):
        """Обрабатывает клик ЛКМ в режиме редактирования"""
        if not self.current_file:
            return
        
        loc = self.dm.locations[self.current_file]
        
        if self.tool == TOOL_SELECT:
            # проверяем кнопки поворота у выделенного объекта
            if self.selected_object and self.selected_object[0] == "object":
                for btn in self._get_rotation_buttons(self.selected_object[1]):
                    if btn["rect"].collidepoint(mx, my):
                        obj = self.dm.locations[self.current_file]["objects"][self.selected_object[1]]
                        self.undo.push(RotateObjectCommand(
                            self.dm, self.current_file, self.selected_object[1],
                            obj.get("rotation", 0), btn["delta"]
                        ))
                        return
            # Ищем объект под курсором
            self._select_at(mx, my)
            
        elif self.tool == TOOL_WALL:
            # Начинаем рисование стены
            self.wall_drawing = True
            self.wall_start = (gx, gy)
            
        elif self.tool == TOOL_ROOM:
            # Начинаем создание комнаты
            self.room_drawing = True
            self.room_start = (gx, gy)
            
        elif self.tool == TOOL_OBJECT:
            # Создаём объект
            preset = OBJECT_PRESETS.get(self.selected_object_type, {})
            ds = preset.get("default_size", {"w": 1.0, "h": 1.0})
            idx = self.undo.push(AddObjectCommand(
                self.dm, self.current_file, self.selected_object_type,
                gx, gy, ds["w"], ds["h"]
            ))
            self.selected_object = ("object", idx)
            self._show_toast(f"Объект создан: {self.selected_object_type}")
            
        elif self.tool == TOOL_PORTAL:
            # Создаём портал
            portal_id = self.undo.push(AddPortalCommand(self.dm, self.current_file, self.selected_portal_type, gx, gy))
            self.selected_object = ("portal", portal_id)
            self._show_toast(f"Портал создан: {portal_id}")
            
        elif self.tool == TOOL_DELETE:
            # Удаляем объект под курсором
            self._delete_at(mx, my)
    
    def _handle_left_release(self, mx: int, my: int, wx: float, wy: float, gx: float, gy: float):
        """Обрабатывает отпускание ЛКМ"""
        if not self.current_file:
            return
        
        if self.tool == TOOL_WALL and self.wall_drawing and self.wall_start:
            # Завершаем рисование стены
            if abs(gx - self.wall_start[0]) > 0.1 or abs(gy - self.wall_start[1]) > 0.1:
                self.undo.push(AddWallCommand(self.dm, self.current_file,
                               self.wall_start[0], self.wall_start[1],
                               gx, gy))
                self._show_toast("Стена создана")
            self.wall_drawing = False
            self.wall_start = None
            
        elif self.tool == TOOL_ROOM and self.room_drawing and self.room_start:
            # Завершаем создание комнаты
            x = min(self.room_start[0], gx)
            y = min(self.room_start[1], gy)
            w = abs(gx - self.room_start[0])
            h = abs(gy - self.room_start[1])
            if w > 1 and h > 1:
                room_name = f"Комната {len(self.dm.locations[self.current_file]['rooms'])}"
                room_cmd = AddRoomCommand(self.dm, self.current_file, room_name, x, y, w, h)
                # 4 стены коробки
                wall_cmds = [
                    AddWallCommand(self.dm, self.current_file, x, y, x + w, y),
                    AddWallCommand(self.dm, self.current_file, x + w, y, x + w, y + h),
                    AddWallCommand(self.dm, self.current_file, x + w, y + h, x, y + h),
                    AddWallCommand(self.dm, self.current_file, x, y + h, x, y),
                ]
                self.undo.push(CompoundCommand("Комната + стены", [room_cmd] + wall_cmds))
                self._show_toast(f"Комната создана: {room_cmd.room_id}")
            self.room_drawing = False
            self.room_start = None
    
    def _select_at(self, mx: int, my: int):
        """Выбирает объект под курсором"""
        if not self.current_file:
            return
        
        loc = self.dm.locations[self.current_file]
        
        # Проверяем порталы (приоритет)
        if self.show_portals:
            for p in loc.get("portals", []):
                sx, sy = self.world_to_screen(p["position"]["x"], p["position"]["y"])
                if abs(sx - mx) < 20 and abs(sy - my) < 20:
                    self.selected_object = ("portal", p["id"])
                    return
        

        # Проверяем объекты
        if self.show_objects:
            for i, obj in enumerate(loc.get("objects", [])):
                sx, sy = self.world_to_screen(obj["position"]["x"], obj["position"]["y"])
                if abs(sx - mx) < 20 and abs(sy - my) < 20:
                    self.selected_object = ("object", i)
                    return
        
        # Проверяем стены
        if self.show_walls:
            for wall in loc.get("walls", []):
                sx1, sy1 = self.world_to_screen(wall["x1"], wall["y1"])
                sx2, sy2 = self.world_to_screen(wall["x2"], wall["y2"])
                if self._point_near_line(mx, my, sx1, sy1, sx2, sy2, 10):
                    self.selected_object = ("wall", wall["id"])
                    return
        
        # Проверяем комнаты
        if self.show_rooms:
            for room in loc.get("rooms", []):
                rx, ry = self.world_to_screen(room["x"], room["y"])
                rw = room["width"] * SCALE * self.zoom
                rh = room["height"] * SCALE * self.zoom
                if pygame.Rect(rx, ry, rw, rh).collidepoint(mx, my):
                    self.selected_object = ("room", room["id"])
                    return
        
        self.selected_object = None
    
    def _delete_at(self, mx: int, my: int):
        """Удаляет объект под курсором"""
        if not self.current_file:
            return
        
        loc = self.dm.locations[self.current_file]
        
        # Порталы
        for p in loc.get("portals", []):
            sx, sy = self.world_to_screen(p["position"]["x"], p["position"]["y"])
            if abs(sx - mx) < 20 and abs(sy - my) < 20:
                self.undo.push(RemovePortalCommand(self.dm, self.current_file, deepcopy(p)))
                self._show_toast(f"Портал удалён: {p['id']}")
                self.selected_object = None
                return
        
        # Узлы
        for nid in list(loc.get("nodes", {}).keys()):
            ndata = loc["nodes"][nid]
            sx, sy = self.world_to_screen(ndata["x"], ndata["y"])
            if abs(sx - mx) < 15 and abs(sy - my) < 15:
                self.undo.push(RemoveNodeCommand(self.dm, self.current_file, nid, deepcopy(ndata)))
                self._show_toast(f"Узел удалён: {nid}")
                self.selected_object = None
                return
        
        # Объекты
        for i in range(len(loc.get("objects", [])) - 1, -1, -1):
            obj = loc["objects"][i]
            sx, sy = self.world_to_screen(obj["position"]["x"], obj["position"]["y"])
            if abs(sx - mx) < 20 and abs(sy - my) < 20:
                self.undo.push(RemoveObjectCommand(self.dm, self.current_file, obj.get("id", ""), deepcopy(obj)))
                self._show_toast("Объект удалён")
                self.selected_object = None
                return
        
        # Стены
        for wall in loc.get("walls", []):
            sx1, sy1 = self.world_to_screen(wall["x1"], wall["y1"])
            sx2, sy2 = self.world_to_screen(wall["x2"], wall["y2"])
            if self._point_near_line(mx, my, sx1, sy1, sx2, sy2, 10):
                self.dm.remove_wall(self.current_file, wall["id"])
                self._show_toast("Стена удалена")
                self.selected_object = None
                return
        
        # Комнаты
        for room in loc.get("rooms", []):
            rx, ry = self.world_to_screen(room["x"], room["y"])
            rw = room["width"] * SCALE * self.zoom
            rh = room["height"] * SCALE * self.zoom
            if pygame.Rect(rx, ry, rw, rh).collidepoint(mx, my):
                # собираем стены по границам комнаты
                x, y, w, h = room["x"], room["y"], room["width"], room["height"]
                edges = [
                    (x, y, x + w, y), (x + w, y, x + w, y + h),
                    (x + w, y + h, x, y + h), (x, y + h, x, y),
                ]
                wall_cmds = []
                for wall in list(loc["walls"]):
                    for ex1, ey1, ex2, ey2 in edges:
                        direct = (abs(wall["x1"] - ex1) < 0.01 and abs(wall["y1"] - ey1) < 0.01 and
                                  abs(wall["x2"] - ex2) < 0.01 and abs(wall["y2"] - ey2) < 0.01)
                        reverse = (abs(wall["x1"] - ex2) < 0.01 and abs(wall["y1"] - ey2) < 0.01 and
                                   abs(wall["x2"] - ex1) < 0.01 and abs(wall["y2"] - ey1) < 0.01)
                        if direct or reverse:
                            wall_cmds.append(RemoveWallCommand(self.dm, self.current_file, deepcopy(wall)))
                            break
                room_cmd = RemoveRoomCommand(self.dm, self.current_file, deepcopy(room))
                self.undo.push(CompoundCommand("Удалить комнату", [room_cmd] + wall_cmds))
                self._show_toast(f"Комната удалена: {room['name']}")
                self.selected_object = None
                return
    
    def _point_near_line(self, px: int, py: int, x1: int, y1: int, x2: int, y2: int, threshold: int) -> bool:
        """Проверяет, находится ли точка рядом с отрезком"""
        # Расстояние от точки до отрезка
        line_len = math.hypot(x2 - x1, y2 - y1)
        if line_len == 0:
            return math.hypot(px - x1, py - y1) < threshold
        
        t = max(0, min(1, ((px - x1) * (x2 - x1) + (py - y1) * (py - y1)) / (line_len ** 2)))
        proj_x = x1 + t * (x2 - x1)
        proj_y = y1 + t * (y2 - y1)
        
        return math.hypot(px - proj_x, py - proj_y) < threshold
    
    def _handle_property_action(self, action: str):
        """Обрабатывает действия из панели свойств"""
        if not self.current_file or not self.selected_object:
            return
        
        obj_type, obj_key = self.selected_object
        loc = self.dm.locations[self.current_file]
        
        if action.startswith("toggle_"):
            flag = action[7:]  # Убираем "toggle_"
            if obj_type == "object":
                obj = loc["objects"][obj_key]
                self.undo.push(TogglePassabilityCommand(
                    self.dm, self.current_file, obj_key, flag, obj["passability"][flag]
                ))
    
    def _update(self):
        """Обновляет состояние"""
        if self.toast_timer > 0:
            self.toast_timer -= 1
        
        # Обновляем панель свойств
        self._update_property_panel()
    
    def _update_property_panel(self):
        """Обновляет содержимое панели свойств"""
        if not self.current_file or not self.selected_object:
            self.property_panel.set_content("СВОЙСТВА", [])
            return
        
        obj_type, obj_key = self.selected_object
        loc = self.dm.locations[self.current_file]
        items = []
        
        if obj_type == "object":
            obj = loc["objects"][obj_key]
            items = [
                {"type": "label", "text": f"Объект: {obj['type']}", "important": True},
                {"type": "value", "label": "X", "value": f"{obj['position']['x']:.1f}"},
                {"type": "value", "label": "Y", "value": f"{obj['position']['y']:.1f}"},
                {"type": "section", "text": "Проходимость:"},
                {"type": "toggle", "label": "Walk", "value": obj["passability"]["walk"], "action": "toggle_walk"},
                {"type": "toggle", "label": "Jump", "value": obj["passability"]["jump_over"], "action": "toggle_jump_over"},
                {"type": "toggle", "label": "Crawl", "value": obj["passability"]["crawl_under"], "action": "toggle_crawl_under"},
                {"type": "toggle", "label": "Climb", "value": obj["passability"]["climb_on"], "action": "toggle_climb_on"},
            ]
        
        elif obj_type == "portal":
            p = next((p for p in loc["portals"] if p["id"] == obj_key), None)
            if p:
                items = [
                    {"type": "label", "text": f"Портал: {p['label']}", "important": True},
                    {"type": "value", "label": "Тип", "value": p['type']},
                    {"type": "value", "label": "Цель", "value": p.get('target') or "(не связан)"},
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
                    {"type": "label", "text": f"Комната: {room['name']}", "important": True},
                    {"type": "value", "label": "X", "value": f"{room['x']:.1f}"},
                    {"type": "value", "label": "Y", "value": f"{room['y']:.1f}"},
                    {"type": "value", "label": "Ширина", "value": f"{room['width']:.1f}"},
                    {"type": "value", "label": "Высота", "value": f"{room['height']:.1f}"},
                ]
        
        self.property_panel.set_content("СВОЙСТВА", items)
    
    # === ОТРИСОВКА ===
    def _draw(self):
        """Отрисовывает всё"""
        self.screen.fill(COLORS["bg_dark"])
        
        if self.mode == MODE_WORLD:
            self._draw_world()
        else:
            self._draw_local()
        
        # UI поверх всего
        self._draw_ui()
        
        # Диалог
        if self.dialog and getattr(self.dialog, 'active', False):
            if isinstance(self.dialog, DropDownMenu):
                self.dialog.draw(self.screen, self.font)
            else:
                self.dialog.draw(self.font, self.font_small)
    
    def _draw_world(self):
        """Отрисовывает карту мира"""
        # Сетка мира
        self._draw_world_grid()
        
        # Локации
        for fname, data in self.dm.locations.items():
            rect = self._get_location_screen_rect(fname)
            if not rect:
                continue
            
            # Цвет в зависимости от типа
            if data.get("is_outdoor"):
                color = (80, 120, 80)  # Улица - зеленоватый
            else:
                color = (100, 100, 110)  # Помещение - серый
            
            if fname == self.current_file:
                color = (100, 150, 200)  # Выбранная - синий
            
            pygame.draw.rect(self.screen, color, rect, border_radius=4)
            pygame.draw.rect(self.screen, COLORS["border"], rect, 2, border_radius=4)
            
            # Название
            label = self.font_bold.render(data.get("label", fname), True, COLORS["text_highlight"])
            self.screen.blit(label, (rect.x + 8, rect.y - 18))
            
            # Инфо
            info_text = f"{data['size']['w']}x{data['size']['h']}м"
            info = self.font_small.render(info_text, True, COLORS["text_dim"])
            self.screen.blit(info, (rect.x + 8, rect.y + 5))
            
            # Количество порталов
            p_count = len(data.get("portals", []))
            if p_count > 0:
                p_text = self.font_small.render(f"🚪{p_count}", True, COLORS["accent_yellow"])
                self.screen.blit(p_text, (rect.x + 8, rect.y + 20))
    
    def _draw_world_grid(self):
        """Отрисовывает сетку мира"""
        # Крупная сетка (100м)
        start_x = int(self.camera_x / (SCALE * self.zoom * 10)) - 1
        end_x = start_x + int(self.screen.get_width() / (SCALE * self.zoom * 10)) + 2
        start_y = int(self.camera_y / (SCALE * self.zoom * 10)) - 1
        end_y = start_y + int(self.screen.get_height() / (SCALE * self.zoom * 10)) + 2
        
        for x in range(start_x, end_x):
            sx = x * SCALE * self.zoom * 10 + self.camera_x
            pygame.draw.line(self.screen, COLORS["grid_major"], (sx, 0), (sx, self.screen.get_height()))
        for y in range(start_y, end_y):
            sy = y * SCALE * self.zoom * 10 + self.camera_y
            pygame.draw.line(self.screen, COLORS["grid_major"], (0, sy), (self.screen.get_width(), sy))
    
    def _get_location_screen_rect(self, fname: str) -> Optional[pygame.Rect]:
        """Возвращает экранный прямоугольник локации"""
        if fname not in self.dm.locations:
            return None
        
        data = self.dm.locations[fname]
        sx, sy = self.world_to_screen(data["origin"]["x"], data["origin"]["y"])
        sw = data["size"]["w"] * SCALE * self.zoom
        sh = data["size"]["h"] * SCALE * self.zoom
        
        return pygame.Rect(sx, sy, sw, sh)
    
    def _draw_local(self):
        """Отрисовывает локацию в режиме редактирования"""
        if not self.current_file:
            return
        
        loc = self.dm.locations[self.current_file]
        
        # Сетка
        if self.show_grid:
            self._draw_local_grid()
        
        # Граница локации
        self._draw_location_bounds()
        
        # Комнаты
        if self.show_rooms:
            self._draw_rooms()
        
        # Стены
        if self.show_walls:
            self._draw_walls()
        
        # Объекты
        if self.show_objects:
            self._draw_objects()
        
        # Порталы
        if self.show_portals:
            self._draw_portals()
        
        # Предпросмотр рисования
        self._draw_preview()
        
        # Выделение
        self._draw_selection()
    
    def _draw_local_grid(self):
        """Отрисовывает локальную сетку"""
        # Определяем видимый диапазон
        screen_w = self.screen.get_width() - self.panel_width
        screen_h = self.screen.get_height()
        
        start_x = int((-self.camera_x) / (SCALE * self.zoom)) - 1
        end_x = start_x + int(screen_w / (SCALE * self.zoom)) + 2
        start_y = int((-self.camera_y) / (SCALE * self.zoom)) - 1
        end_y = start_y + int(screen_h / (SCALE * self.zoom)) + 2
        
        # Мелкая сетка (0.5м)
        for x in range(start_x * 2, end_x * 2):
            sx = x * SCALE * self.zoom * 0.5 + self.camera_x
            pygame.draw.line(self.screen, COLORS["grid_minor"], 
                           (sx, self.menu_height + self.toolbar_height), (sx, screen_h))
        for y in range(start_y * 2, end_y * 2):
            sy = y * SCALE * self.zoom * 0.5 + self.camera_y
            pygame.draw.line(self.screen, COLORS["grid_minor"], 
                           (0, sy), (screen_w, sy))
        
        # Крупная сетка (1м)
        for x in range(start_x, end_x):
            sx = x * SCALE * self.zoom + self.camera_x
            color = COLORS["grid_major"] if x % 5 == 0 else COLORS["grid_minor"]
            pygame.draw.line(self.screen, color, 
                           (sx, self.menu_height + self.toolbar_height), (sx, screen_h))
        for y in range(start_y, end_y):
            sy = y * SCALE * self.zoom + self.camera_y
            color = COLORS["grid_major"] if y % 5 == 0 else COLORS["grid_minor"]
            pygame.draw.line(self.screen, color, (0, sy), (screen_w, sy))
        
        # Координатные оси
        origin_x, origin_y = self.world_to_screen(0, 0)
        if 0 <= origin_x <= screen_w:
            pygame.draw.line(self.screen, COLORS["accent_red"], 
                           (origin_x, self.menu_height + self.toolbar_height), (origin_x, screen_h), 2)
        if self.menu_height + self.toolbar_height <= origin_y <= screen_h:
            pygame.draw.line(self.screen, COLORS["accent_green"], 
                           (0, origin_y), (screen_w, origin_y), 2)
    
    def _draw_location_bounds(self):
        """Отрисовывает границы локации"""
        if not self.current_file:
            return
        
        loc = self.dm.locations[self.current_file]
        x, y = self.world_to_screen(loc["origin"]["x"], loc["origin"]["y"])
        w = loc["size"]["w"] * SCALE * self.zoom
        h = loc["size"]["h"] * SCALE * self.zoom
        
        # Фон
        bg_color = (40, 50, 40) if loc.get("is_outdoor") else (45, 45, 50)
        pygame.draw.rect(self.screen, bg_color, (x, y, w, h))
        
        # Граница
        pygame.draw.rect(self.screen, COLORS["border"], (x, y, w, h), 3)
        
        # Размеры
        label = self.font.render(f"{loc['size']['w']}x{loc['size']['h']}м", True, COLORS["text_dim"])
        self.screen.blit(label, (x + 5, y - 15))
    
    def _draw_rooms(self):
        """Отрисовывает комнаты"""
        if not self.current_file:
            return
        
        loc = self.dm.locations[self.current_file]
        for room in loc.get("rooms", []):
            rx, ry = self.world_to_screen(room["x"], room["y"])
            rw = room["width"] * SCALE * self.zoom
            rh = room["height"] * SCALE * self.zoom
            
            # Фон комнаты
            pygame.draw.rect(self.screen, (60, 60, 70), (rx, ry, rw, rh))
            # Граница
            pygame.draw.rect(self.screen, (100, 100, 120), (rx, ry, rw, rh), 2)
            # Название
            name = self.font_small.render(room["name"], True, COLORS["text_dim"])
            self.screen.blit(name, (rx + 4, ry + 4))
    
    def _draw_walls(self):
        """Отрисовывает стены"""
        if not self.current_file:
            return
        
        loc = self.dm.locations[self.current_file]
        for wall in loc.get("walls", []):
            x1, y1 = self.world_to_screen(wall["x1"], wall["y1"])
            x2, y2 = self.world_to_screen(wall["x2"], wall["y2"])
            
            # Толщина линии зависит от зума
            thickness = max(2, int(3 * self.zoom))
            pygame.draw.line(self.screen, OBJECT_COLORS["wall"], (x1, y1), (x2, y2), thickness)
            
            # Точки концов
            pygame.draw.circle(self.screen, (180, 120, 60), (x1, y1), 4)
            pygame.draw.circle(self.screen, (180, 120, 60), (x2, y2), 4)
    
    def _draw_objects(self):
        """Отрисовывает объекты"""
        if not self.current_file:
            return
        
        loc = self.dm.locations[self.current_file]
        for i, obj in enumerate(loc.get("objects", [])):
            sx, sy = self.world_to_screen(obj["position"]["x"], obj["position"]["y"])
            w = obj["size"]["w"] * SCALE * self.zoom
            h = obj["size"]["h"] * SCALE * self.zoom
            rotation = obj.get("rotation", 0)
            color = OBJECT_COLORS.get(obj["type"], OBJECT_COLORS["decoration"])
            
            if rotation % 360 != 0:
                pts = self._rotated_rect_points(sx, sy, w, h, rotation)
                pygame.draw.polygon(self.screen, color, pts)
                pygame.draw.polygon(self.screen, COLORS["border"], pts, 1)
            else:
                rect = pygame.Rect(sx - w/2, sy - h/2, w, h)
                pygame.draw.rect(self.screen, color, rect, border_radius=2)
                pygame.draw.rect(self.screen, COLORS["border"], rect, 1, border_radius=2)
            
            # Имя объекта (для старых данных без name — fallback на тип)
            label_text = obj.get("name", obj["type"][:4])
            label = self.font_small.render(label_text, True, COLORS["text_highlight"])
            self.screen.blit(label, (sx - label.get_width() // 2, sy - h / 2 - 14))
    
    def _draw_nodes(self):
        """Отрисовывает навигационные узлы"""
        if not self.current_file:
            return
        
        loc = self.dm.locations[self.current_file]
        
        # Связи
        for nid, ndata in loc.get("nodes", {}).items():
            sx, sy = self.world_to_screen(ndata["x"], ndata["y"])
            
            for conn in ndata.get("connections", []):
                if ":" not in conn and conn in loc["nodes"]:
                    # Внутренняя связь
                    ex, ey = self.world_to_screen(loc["nodes"][conn]["x"], loc["nodes"][conn]["y"])
                    pygame.draw.line(self.screen, (80, 80, 90), (sx, sy), (ex, ey), 2)
                elif ":" in conn:
                    # Внешняя связь - пунктир
                    ex, ey = sx + 30, sy
                    for j in range(0, 30, 8):
                        pygame.draw.line(self.screen, COLORS["accent_yellow"], 
                                       (sx + j, sy), (sx + min(j + 4, 30), sy), 2)
        
        # Узлы
        for nid, ndata in loc.get("nodes", {}).items():
            sx, sy = self.world_to_screen(ndata["x"], ndata["y"])
            
            # Круг узла
            pygame.draw.circle(self.screen, COLORS["accent_blue"], (sx, sy), 8)
            pygame.draw.circle(self.screen, COLORS["text_highlight"], (sx, sy), 8, 2)
            
            # Подпись
            label = self.font_small.render(ndata.get("label", nid), True, COLORS["text"])
            self.screen.blit(label, (sx + 10, sy - 8))
    
    def _draw_portals(self):
        """Отрисовывает порталы"""
        if not self.current_file:
            return
        
        loc = self.dm.locations[self.current_file]
        
        for p in loc.get("portals", []):
            sx, sy = self.world_to_screen(p["position"]["x"], p["position"]["y"])
            
            # Цвет по типу
            portal_info = PORTAL_TYPES.get(p["type"], PORTAL_TYPES["door"])
            color = tuple(int(portal_info["color"][i:i+2], 16) for i in (1, 3, 5))
            
            # Иконка по типу
            if p["type"] == "door":
                pygame.draw.rect(self.screen, color, (sx - 10, sy - 20, 20, 40), 2)
                pygame.draw.line(self.screen, color, (sx, sy - 20), (sx, sy + 20), 1)
            elif p["type"] in ("stairs_up", "stairs_down"):
                pygame.draw.polygon(self.screen, color, [(sx, sy - 15), (sx + 15, sy), (sx - 15, sy)])
                if p["type"] == "stairs_up":
                    pygame.draw.polygon(self.screen, color, [(sx, sy - 10), (sx + 10, sy), (sx - 10, sy)])
            elif p["type"] == "ladder":
                pygame.draw.line(self.screen, color, (sx, sy - 20), (sx, sy + 20), 3)
                for i in range(-15, 16, 8):
                    pygame.draw.line(self.screen, color, (sx - 8, sy + i), (sx + 8, sy + i), 2)
            else:
                # Стандартная иконка
                pygame.draw.circle(self.screen, color, (sx, sy), 12)
            
            # Подпись
            label = self.font_small.render(p.get("label", p["id"]), True, color)
            self.screen.blit(label, (sx + 15, sy - 8))
            
            # Индикатор связи
            if p.get("target"):
                pygame.draw.circle(self.screen, COLORS["accent_green"], (sx - 15, sy - 15), 4)
    
    def _draw_preview(self):
        """Отрисовывает предпросмотр при рисовании"""
        mx, my = pygame.mouse.get_pos()
        
        if self.tool == TOOL_WALL and self.wall_drawing and self.wall_start:
            x1, y1 = self.world_to_screen(self.wall_start[0], self.wall_start[1])
            pygame.draw.line(self.screen, COLORS["accent_yellow"], (x1, y1), (mx, my), 2)
            # длина стены в метрах
            wx2, wy2 = self.screen_to_world(mx, my)
            length = math.hypot(wx2 - self.wall_start[0], wy2 - self.wall_start[1])
            mid_x = (x1 + mx) // 2
            mid_y = (y1 + my) // 2 - 14
            label = self.font_small.render(f"{length:.2f} м", True, COLORS["accent_yellow"])
            self.screen.blit(label, (mid_x - label.get_width() // 2, mid_y))
            
        elif self.tool == TOOL_ROOM and self.room_drawing and self.room_start:
            x1, y1 = self.world_to_screen(self.room_start[0], self.room_start[1])
            rect = pygame.Rect(min(x1, mx), min(y1, my), abs(mx - x1), abs(my - y1))
            pygame.draw.rect(self.screen, (100, 100, 120, 100), rect)
            pygame.draw.rect(self.screen, COLORS["accent_yellow"], rect, 2)
    
    def _draw_selection(self):
        """Отрисовывает выделение объекта"""
        if not self.current_file or not self.selected_object:
            return
        
        obj_type, obj_key = self.selected_object
        loc = self.dm.locations[self.current_file]
        
        if obj_type == "object":
            if 0 <= obj_key < len(loc.get("objects", [])):
                obj = loc["objects"][obj_key]
                sx, sy = self.world_to_screen(obj["position"]["x"], obj["position"]["y"])
                w = obj["size"]["w"] * SCALE * self.zoom
                h = obj["size"]["h"] * SCALE * self.zoom
                rotation = obj.get("rotation", 0)
                if rotation % 360 != 0:
                    pts = self._rotated_rect_points(sx, sy, w + 6, h + 6, rotation)
                    pygame.draw.polygon(self.screen, COLORS["accent_yellow"], pts, 3)
                else:
                    rect = pygame.Rect(sx - w/2 - 3, sy - h/2 - 3, w + 6, h + 6)
                    pygame.draw.rect(self.screen, COLORS["accent_yellow"], rect, 3, border_radius=3)
                # кнопки поворота
                for btn in self._get_rotation_buttons(obj_key):
                    r = btn["rect"]
                    pygame.draw.circle(self.screen, COLORS["bg_panel"], r.center, r.width // 2)
                    pygame.draw.circle(self.screen, COLORS["border"], r.center, r.width // 2, 1)
                    # треугольник-стрелка
                    cx, cy = r.center
                    if btn["delta"] > 0:  # по часовой →
                        pts = [(cx - 4, cy - 4), (cx - 4, cy + 4), (cx + 4, cy)]
                    else:  # против часовой ←
                        pts = [(cx + 4, cy - 4), (cx + 4, cy + 4), (cx - 4, cy)]
                    pygame.draw.polygon(self.screen, COLORS["text"], pts)
                
        elif obj_type == "portal":
            for p in loc.get("portals", []):
                if p["id"] == obj_key:
                    sx, sy = self.world_to_screen(p["position"]["x"], p["position"]["y"])
                    pygame.draw.circle(self.screen, COLORS["accent_yellow"], (sx, sy), 18, 3)
                    break
                    
        elif obj_type == "wall":
            for wall in loc.get("walls", []):
                if wall["id"] == obj_key:
                    x1, y1 = self.world_to_screen(wall["x1"], wall["y1"])
                    x2, y2 = self.world_to_screen(wall["x2"], wall["y2"])
                    pygame.draw.line(self.screen, COLORS["accent_yellow"], (x1, y1), (x2, y2), 4)
                    break
                    
        elif obj_type == "room":
            for room in loc.get("rooms", []):
                if room["id"] == obj_key:
                    rx, ry = self.world_to_screen(room["x"], room["y"])
                    rw = room["width"] * SCALE * self.zoom
                    rh = room["height"] * SCALE * self.zoom
                    pygame.draw.rect(self.screen, COLORS["accent_yellow"], (rx - 2, ry - 2, rw + 4, rh + 4), 3)
                    break
    
    def _draw_ui(self):
        """Отрисовывает пользовательский интерфейс"""
        # Верхняя панель (меню)
        pygame.draw.rect(self.screen, COLORS["bg_menu"], (0, 0, self.screen.get_width(), self.menu_height))
        pygame.draw.line(self.screen, COLORS["border"], (0, self.menu_height), 
                        (self.screen.get_width(), self.menu_height))
        
        for btn in self.menu_buttons:
            btn.draw(self.screen, self.font)
        
        # Тулбар
        toolbar_y = self.menu_height
        pygame.draw.rect(self.screen, COLORS["bg_panel"], 
                        (0, toolbar_y, self.screen.get_width() - self.panel_width, self.toolbar_height))
        pygame.draw.line(self.screen, COLORS["border"], 
                        (0, toolbar_y + self.toolbar_height),
                        (self.screen.get_width() - self.panel_width, toolbar_y + self.toolbar_height))
        
        for btn in self.toolbar_buttons:
            btn.draw(self.screen, self.font)
        
        # Дропдауны
        if self.object_dropdown:
            self.object_dropdown.draw(self.screen, self.font, self.font_small)
        if self.portal_dropdown:
            self.portal_dropdown.draw(self.screen, self.font, self.font_small)
        
        # Панель свойств
        self.property_panel.draw(self.screen, self.font, self.font_small)
        
        # Статусная строка
        self._draw_status_bar()
        
        # Toast сообщение
        if self.toast_timer > 0:
            self._draw_toast()
    
    def _draw_status_bar(self):
        """Отрисовывает статусную строку"""
        screen_h = self.screen.get_height()
        status_y = screen_h - self.status_height
        
        pygame.draw.rect(self.screen, COLORS["bg_menu"], 
                        (0, status_y, self.screen.get_width(), self.status_height))
        pygame.draw.line(self.screen, COLORS["border"], (0, status_y), (self.screen.get_width(), status_y))
        
        # Информация
        mx, my = pygame.mouse.get_pos()
        wx, wy = self.screen_to_world(mx, my) if self.mode == MODE_LOCAL else (0, 0)
        
        if self.mode == MODE_LOCAL:
            undo_info = f" | Отмена:{self.undo.undo_label}" if self.undo.can_undo else ""
            camp_info = f" | Кампания: {self.cm.campaign_data['name']}" if self.cm.is_open else " | (без кампании)"
            info = f"X:{wx:.1f} Y:{wy:.1f} | Этаж:{self.current_z} | Zoom:{self.zoom:.1f}x | {self.current_file or '—'}{camp_info}{undo_info}"
        else:
            info = f"Карта мира | Локаций: {len(self.dm.locations)}"
        
        text = self.font_small.render(info, True, COLORS["text_dim"])
        self.screen.blit(text, (10, status_y + 5))
        
        # Подсказки
        hints = "[TAB] Мир/Лок | [PgUp/PgDn] Этаж | [Ctrl+S] Save | [Ctrl+Z/Q] Undo/Redo | [Ctrl+C/V] Copy/Paste | [+/-] Зум"
        hint_text = self.font_small.render(hints, True, COLORS["text_dim"])
        self.screen.blit(hint_text, (self.screen.get_width() - hint_text.get_width() - 10, status_y + 5))
    
    def _draw_toast(self):
        """Отрисовывает всплывающее сообщение"""
        if not self.toast_message:
            return
        
        # Фон
        padding = 15
        text = self.font.render(self.toast_message, True, COLORS["text_highlight"])
        w = text.get_width() + padding * 2
        h = text.get_height() + padding
        
        x = (self.screen.get_width() - w) // 2
        y = self.screen.get_height() - h - 50
        
        # Полупрозрачный фон
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((30, 30, 40, 220))
        self.screen.blit(overlay, (x, y))
        
        pygame.draw.rect(self.screen, COLORS["border"], (x, y, w, h), 1, border_radius=6)
        self.screen.blit(text, (x + padding, y + padding // 2))


# Точка входа
if __name__ == "__main__":
    app = EditorCore()
    app.run()

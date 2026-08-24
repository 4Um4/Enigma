"""
map_editor/editor_core.py
Главный редактор карт - ядро приложения
"""

import json
import math
import threading
import urllib.request
import urllib.error
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pygame
from campaign_manager import CampaignManager
from data_manager import (
    NPC_SPRITE_MAP,
    OBJECT_PRESETS,
    DataManager,
    load_npc_individuals,
)
from sprite_registry import sprite_registry
from ui_components import (
    COLORS,
    Button,
    Dropdown,
    DropDownMenu,
    ModalDialog,
    PropertyPanel,
    ToggleButton,
)
from core.geometry import Geometry
from core.commands import (
    AddWallCommand,
    AddNodeCommand,
    AddConnectionCommand,
    AddLabelCommand,
    AddNpcCommand,
    AddObjectCommand,
    AddPassageCommand,
    AddRoomCommand,
    AddWallCommand,
    CompoundCommand,
    MirrorObjectCommand,
    MoveEntityCommand,
    PasteCommand,
    RemoveLabelCommand,
    RemoveNodeCommand,
    RemoveNpcCommand,
    RemoveObjectCommand,
    RemoveRoomCommand,
    RemoveWallCommand,
    RenameCommand,
    ResizeObjectCommand,
    RotateObjectCommand,
    SimpleNodeUpdateCommand,
    TogglePassabilityCommand,
    UndoManager,
)

# === Константы редактора ===
SCALE = 40  # пикселей в 1 метре
MIN_ZOOM = 0.3
MAX_ZOOM = 3.0
ZOOM_STEP = 1.2

# Режимы работы
MODE_WORLD = "world"  # Карта мира - выбор локаций
MODE_LOCAL = "local"  # Редактирование локации

# Инструменты
from tools.constants import (
    TOOL_SELECT, TOOL_WALL, TOOL_ROOM, TOOL_OBJECT, TOOL_PASSAGE,
    TOOL_LABEL, TOOL_NPC, TOOL_SPAWN, TOOL_DELETE, TOOL_NODE,
    MODE_WORLD, MODE_LOCAL, MODE_LAB
)

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
        self._dragging_location: Optional[str] = None
        self._drag_offset = (0, 0)
        self.tool = None  # None = режим покоя (выделение)
        self.selected_object: Optional[Tuple[str, Any]] = None

        # Камера
        self.camera_x = 0.0
        self.camera_y = 0.0
        self.zoom = 1.0
        self.dragging_camera = False
        self.camera_speed = 15  # пикселей за кадр при стрелках

        # Двойной клик для переименования
        self._last_click_time: int = 0
        self._last_click_pos: Tuple[int, int] = (0, 0)

        # Перекрытые комнаты — циклический выбор
        self._overlap_room_ids: List[str] = []
        self._overlap_index: int = -1

        # Позиция для размещения надписи (временная, до диалога)
        self._pending_label_pos: Optional[Tuple[float, float]] = None
        self._open_file_path: Optional[Any] = None  # путь к открытому файлу напрямую

        # Рисование
        self.wall_drawing = False
        self.wall_start: Optional[Tuple[float, float]] = None
        self.room_drawing = False
        self.room_start: Optional[Tuple[float, float]] = None
        self.node_link_start: Optional[str] = None  # S143: ID узла-источника для создания связи

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
        self.show_rooms = True

        # Выбранные типы
        self.selected_object_type = "table"
        from render.map_renderer import MapRenderer
        self.renderer = MapRenderer()

        from core.event_handler import EventHandler
        self.event_handler = EventHandler()

        from tools.interaction import InteractionManager
        self.interaction_manager = InteractionManager()

        from ui.property_builder import PropertyBuilder
        self.property_builder = PropertyBuilder()

        from ui.lab_screen import LabScreen
        self.lab_screen = LabScreen(self)

        self.selected_npc_id: str = ""  # id реального NPC из config
        self._npc_list: List[Dict[str, str]] = load_npc_individuals()
        if self._npc_list:
            self.selected_npc_id = self._npc_list[0]["id"]

        # Состояние ресайза и перетаскивания
        self._resizing: Optional[Dict[str, Any]] = None
        self._dragging_entity: Optional[Dict[str, Any]] = None

        # Инициализация UI
        self._init_ui()

        # Инициализация реестра спрайтов
        info = sprite_registry.get_sheet_info("Deadbeat/deadbeat_b.png")
        if info:
            print(f"Спрайтшит загружен: {info['cols']}x{info['rows']} тайлов")

        # BUG-P1-18: Хардкод "Open_road" удален. Редактор стартует пустым.
        self._show_toast(
            "Добро пожаловать! Откройте или создайте кампанию через меню File"
        )

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
        self.btn_view = Button(75, 2, 60, 26, "View", on_click=self._toggle_grid)
        self.menu_buttons.append(self.btn_view)

        # === Тулбар ===
        toolbar_y = self.menu_height + 5
        self.toolbar_buttons = []

        # Группа: Строительство
        x = 10
        self.btn_tool_wall = ToggleButton(
            x,
            toolbar_y,
            80,
            32,
            "🧱 Стена",
            on_toggle=lambda s: self._set_tool(TOOL_WALL) if s else None,
        )
        self.toolbar_buttons.append(self.btn_tool_wall)
        x += 90

        self.btn_tool_room = ToggleButton(
            x,
            toolbar_y,
            90,
            32,
            "📦 Комната",
            on_toggle=lambda s: self._set_tool(TOOL_ROOM) if s else None,
        )
        self.toolbar_buttons.append(self.btn_tool_room)
        x += 100

        # Группа: Объекты
        x += 10
        self.btn_tool_object = ToggleButton(
            x,
            toolbar_y,
            90,
            32,
            "🪑 Объект",
            on_toggle=lambda s: self._set_tool(TOOL_OBJECT) if s else None,
        )
        self.toolbar_buttons.append(self.btn_tool_object)
        x += 100

        self.btn_tool_passage = ToggleButton(
            x,
            toolbar_y,
            90,
            32,
            "🕳️ Проход",
            on_toggle=lambda s: self._set_tool(TOOL_PASSAGE) if s else None,
        )
        self.toolbar_buttons.append(self.btn_tool_passage)
        x += 100

        self.btn_tool_label = ToggleButton(
            x,
            toolbar_y,
            80,
            32,
            "📝 Надпись",
            on_toggle=lambda s: self._set_tool(TOOL_LABEL) if s else None,
        )
        self.toolbar_buttons.append(self.btn_tool_label)
        x += 90

        # Группа: Сущности
        x += 10
        self.btn_tool_npc = ToggleButton(
            x,
            toolbar_y,
            80,
            32,
            "👤 NPC",
            on_toggle=lambda s: self._set_tool(TOOL_NPC) if s else None,
        )
        self.toolbar_buttons.append(self.btn_tool_npc)
        x += 90

        self.btn_tool_spawn = ToggleButton(
            x,
            toolbar_y,
            90,
            32,
            "🏁 Спавн",
            on_toggle=lambda s: self._set_tool(TOOL_SPAWN) if s else None,
        )
        self.toolbar_buttons.append(self.btn_tool_spawn)
        x += 100

        # Группа: Удаление
        x += 10
        self.btn_tool_delete = ToggleButton(
            x,
            toolbar_y,
            90,
            32,
            "🗑️ Удалить",
            on_toggle=lambda s: self._set_tool(TOOL_DELETE) if s else None,
        )
        self.toolbar_buttons.append(self.btn_tool_delete)
        x += 100

        self.btn_tool_node = ToggleButton(
            x,
            toolbar_y,
            80,
            32,
            "🔵 Узел",
            on_toggle=lambda s: self._set_tool(TOOL_NODE) if s else None,
        )
        self.toolbar_buttons.append(self.btn_tool_node)

        # Группа: Observatory (ADR-O-330)
        x += 100
        self.btn_simulate = Button(
            x,
            toolbar_y,
            120,
            32,
            "▶ Симуляция",
            on_click=self._toggle_simulation,
        )
        self.toolbar_buttons.append(self.btn_simulate)
        self.observatory_data = None
        self._observatory_revision = 0
        self._geometry_hash = 0
        self._last_edit_time = 0
        self._spatial_dirty = False
        self._observatory_lock = threading.Lock()

        # === Панель свойств ===
        panel_x = screen_w - self.panel_width
        panel_y = self.menu_height + self.toolbar_height + 10
        panel_h = screen_h - panel_y - self.status_height - 10
        self.property_panel = PropertyPanel(panel_x, panel_y, self.panel_width, panel_h)

        # === Дропдауны для типов объектов ===
        self.object_dropdown: Optional[Dropdown] = None

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
            TOOL_WALL: self.btn_tool_wall,
            TOOL_ROOM: self.btn_tool_room,
            TOOL_OBJECT: self.btn_tool_object,
            TOOL_PASSAGE: self.btn_tool_passage,
            TOOL_LABEL: self.btn_tool_label,
            TOOL_NPC: self.btn_tool_npc,
            TOOL_SPAWN: self.btn_tool_spawn,
            TOOL_DELETE: self.btn_tool_delete,
            TOOL_NODE: self.btn_tool_node,
        }
        if tool in tool_buttons:
            tool_buttons[tool].state = True

        # Показываем подсказку
        tool_names = {
            TOOL_WALL: "Стены: первый клик — начало, второй — конец",
            TOOL_ROOM: "Комнаты: кликните и потяните для создания",
            TOOL_OBJECT: "Объекты: кликните для размещения",
            TOOL_PASSAGE: "Проход: кликните по стене для создания",
            TOOL_LABEL: "Надпись: кликните для размещения",
            TOOL_NPC: "NPC: кликните для размещения на карте",
            TOOL_SPAWN: "Спавн: кликните для установки точки появления игрока",
            TOOL_DELETE: "Удаление: кликните по объекту для удаления",
            TOOL_NODE: "Узлы: клик по пустому месту — создать, клик по узлу — выделить, клик по другому узлу — соединить",
        }
        if tool:
            self._show_toast(tool_names.get(tool, "Режим покоя — выделяйте объекты"))
        else:
            self._show_toast("Режим покоя — выделяйте объекты кликом")

        # Создаём/убираем дропдауны
        self._update_dropdowns()

    def _update_dropdowns(self):
        """Обновляет дропдауны в зависимости от инструмента"""
        self.object_dropdown = None

        if self.tool == TOOL_OBJECT:
            preset_keys = list(OBJECT_PRESETS.keys())
            options = [OBJECT_PRESETS[k]["label"] for k in preset_keys]
            self.object_dropdown = Dropdown(
                700, self.menu_height + 8, 120, 28, options=options, label="Тип"
            )
            self.object_dropdown.selected = preset_keys.index(self.selected_object_type)
            self.object_dropdown.on_select = lambda i, opt: setattr(
                self, "selected_object_type", preset_keys[i]
            )

        elif self.tool == TOOL_NPC:
            if not self._npc_list:
                self.object_dropdown = Dropdown(
                    700,
                    self.menu_height + 8,
                    180,
                    28,
                    options=["Нет NPC в config"],
                    label="NPC",
                )
                self.object_dropdown.enabled = False
            else:
                npc_ids = [n["id"] for n in self._npc_list]
                options = [n["name"] for n in self._npc_list]
                self.object_dropdown = Dropdown(
                    700, self.menu_height + 8, 180, 28, options=options, label="NPC"
                )
                try:
                    self.object_dropdown.selected = npc_ids.index(self.selected_npc_id)
                except ValueError:
                    self.object_dropdown.selected = 0
                    self.selected_npc_id = npc_ids[0]
                self.object_dropdown.on_select = lambda i, opt: setattr(
                    self, "selected_npc_id", npc_ids[i]
                )

    def _show_file_menu(self):
        """Показывает выпадающее меню File"""
        items = [
            {"label": "Новая кампания...", "action": self._dialog_create_campaign},
            {"label": "Открыть кампанию...", "action": self._dialog_open_campaign},
            {"type": "separator"},
            {
                "label": "Закрыть кампанию",
                "action": self._close_campaign,
                "disabled": not self.cm.is_open,
            },
            {"type": "separator"},
            {
                "label": "Новая локация...",
                "action": self._dialog_new_location,
                "disabled": not self.cm.is_open,
            },
            {
                "label": "Удалить локацию...",
                "action": self._dialog_delete_location,
                "disabled": not self.cm.is_open or not self.current_file,
            },
            {"type": "separator"},
            {
                "label": "Сохранить всё",
                "action": self._save_campaign,
                "shortcut": "Ctrl+Shift+S",
                "disabled": not self.cm.is_open,
            },
            {
                "label": "Сохранить",
                "action": self._quick_save,
                "shortcut": "Ctrl+S",
                "disabled": not self.current_file,
            },
            {
                "label": "Сохранить как...",
                "action": self._dialog_save_as,
                "disabled": not self.current_file,
            },
            {"type": "separator"},
            {
                "label": "Экспорт в ZIP...",
                "action": self._dialog_export_zip,
                "disabled": not self.cm.is_open,
            },
            {"label": "Импорт из ZIP...", "action": self._dialog_import_zip},
            {"type": "separator"},
            {"label": "В главное меню", "action": self._exit_to_main_menu},
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
            ok, err = self.cm.create_campaign(
                inputs["folder"], inputs["name"], inputs["desc"]
            )
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

        fields = [
            {
                "key": "choice",
                "label": "Кампания",
                "type": "choice",
                "options": options,
            }
        ]

        def on_confirm(inputs):
            choice = inputs.get("choice", "")
            # Безопасный поиск: точное совпадение
            idx = -1
            for i, opt in enumerate(options):
                if opt == choice:
                    idx = i
                    break
            if idx < 0:
                self._show_toast(f"Кампания не найдена: {choice}")
                return
            ok, err = self.cm.open_campaign(folders[idx])
            if ok:
                self.current_file = None
                self.mode = MODE_WORLD
                self.undo.clear()
                # S143 FIX: Защита от KeyError, используем current_campaign_name
                camp_name = self.cm.current_campaign_name or "Безымянная"
                self._show_toast(f"Открыта: {camp_name}")
            else:
                self._show_toast(f"Ошибка: {err}")

        self.dialog = ModalDialog(self.screen, "Открыть кампанию", fields, on_confirm)

    def _dialog_open_folder(self):
        """Открывает системный проводник для выбора папки с campaign.json"""
        import tkinter as tk
        from pathlib import Path
        from tkinter import filedialog

        # Скрываем мини-окно tkinter
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(
            title="Выберите папку с campaign.json",
            initialdir=str(Path(__file__).parent.parent.parent),
        )
        root.destroy()
        if not folder:
            return
        ok, err = self.cm.open_campaign_from_path(folder)
        if ok:
            self.current_file = None
            self.mode = MODE_WORLD
            self.undo.clear()
            self._show_toast(f"Открыта: {self.cm.campaign_data.get('name', folder)}")
        else:
            self._show_toast(f"Ошибка: {err}")

    def _dialog_open_file(self):
        """Открывает проводник для выбора JSON-файла локации"""
        import tkinter as tk
        from pathlib import Path
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        filepath = filedialog.askopenfilename(
            title="Выберите файл локации (.json)",
            initialdir=str(Path(__file__).parent / "location_templates"),
            filetypes=[("JSON файлы", "*.json"), ("Все файлы", "*.*")],
        )
        root.destroy()
        if not filepath:
            return
        filepath = Path(filepath)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self._show_toast(f"Ошибка чтения: {e}")
            return
        # Проверяем что это локация (есть size)
        if "size" not in data:
            self._show_toast("Это не файл локации (нет size)")
            return
        # Загружаем напрямую в dm.locations
        filename = filepath.name
        self.dm.locations[filename] = data
        # Запоминаем путь к файлу для сохранения
        self._open_file_path = filepath
        self.current_file = filename
        self.mode = MODE_LOCAL
        self.undo.clear()
        self._center_camera()
        label = data.get("label", filename)
        self._show_toast(f"Открыт файл: {label}")

    def _close_campaign(self):
        """Закрывает текущую кампанию"""
        name = self.cm.campaign_data.get("name", "") if self.cm.campaign_data else ""
        self.cm.close_campaign()
        self.current_file = None
        self.mode = MODE_WORLD
        self.undo.clear()
        self._show_toast(f"Кампания закрыта: {name}")

    def _exit_to_main_menu(self):
        """Прерывает цикл редактора и возвращает в главное меню"""
        self._running = False

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
                is_outdoor = inputs.get("outdoor", "").lower() in (
                    "да",
                    "yes",
                    "y",
                    "д",
                )
                ok, err = self.dm.create_location(
                    inputs["filename"], w, h, inputs["label"], is_outdoor
                )
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

    def _save_campaign(self):
        """Сохраняет ВСЕ локации текущей кампании"""
        if not self.cm.is_open:
            self._show_toast("Нет открытой кампании")
            return
        count = self.cm.save_all_locations()
        self._show_toast(f"Кампания сохранена ({count} локаций)")

    def _dialog_delete_location(self):
        """Диалог удаления текущей локации из кампании"""
        if not self.current_file or not self.cm.is_open:
            return
        loc_name = self.dm.locations[self.current_file].get("label", self.current_file)
        fields = [
            {
                "key": "confirm",
                "label": f"Удалить '{loc_name}'? (да/нет)",
                "value": "нет",
                "type": "choice",
                "options": ["нет", "да"],
            }
        ]

        def on_confirm(inputs):
            if inputs["confirm"] == "да":
                # Удаляем файл с диска
                loc_path = self.cm.campaign_path / "locations" / self.current_file
                if loc_path.exists():
                    loc_path.unlink()
                # Удаляем из памяти
                if self.current_file in self.dm.locations:
                    del self.dm.locations[self.current_file]
                self.current_file = None
                self.mode = MODE_WORLD
                self._show_toast(f"Локация удалена: {loc_name}")

        self.dialog = ModalDialog(self.screen, "Удаление локации", fields, on_confirm)

    def _quick_save(self):
        """Быстрое сохранение текущей локации"""
        if not self.current_file:
            return
        if self.cm.is_open:
            self.cm.save_location(self.current_file)
        else:
            self.dm.save(self.current_file)
        self._rebuild_spatial_registry()
        self._show_toast(f"Сохранено: {self.current_file}")

    def _toggle_simulation(self):
        """Включает/выключает режим Spatial Observatory."""
        if not self.current_file or self.mode != MODE_LOCAL:
            self._show_toast("Симуляция доступна только в локации")
            return

        if self.observatory_data is not None:
            self.observatory_data = None
            self._spatial_dirty = False
            self._show_toast("Симуляция выключена")
            return

        self._show_toast("Запрос симуляции...")
        # Временно устанавливаем пустой словарь, чтобы _update_observatory не вышел сразу
        self.observatory_data = {}  
        self._spatial_dirty = True
        self._last_edit_time = 0  # 0 заставит немедленно отправить запрос
        self._update_observatory()

    def _update_observatory(self):
        """
        Вызывается каждый кадр. Проверяет изменение геометрии через snapshot diffing.
        Если изменения есть и прошло >200мс с последнего редактирования — запрашивает обновление.
        """
        if self.observatory_data is None or not self.current_file:
            return

        editor_data = self.dm.locations.get(self.current_file)
        if not editor_data:
            return

        # S-OBS-05: Хэшируем весь editor_data. Любая мутация (стены, мебель, двери) изменит хэш.
        # default=str защищает от не-сериализуемых объектов (например, цветов), которые могли быть добавлены в память.
        try:
            current_hash = hash(json.dumps(editor_data, sort_keys=True, default=str))
        except Exception:
            current_hash = 0

        if current_hash != self._geometry_hash:
            self._geometry_hash = current_hash
            self._spatial_dirty = True
            self._last_edit_time = pygame.time.get_ticks()

        if self._spatial_dirty and (pygame.time.get_ticks() - self._last_edit_time > 200):
            self._spatial_dirty = False
            self._request_observatory_update()

    def _request_observatory_update(self):
        """Асинхронно запрашивает обновление ObservatoryDTO с latest-state-wins."""
        self._observatory_revision += 1
        revision = self._observatory_revision
        
        # S-OBS-05: Immutable snapshot для потока
        editor_data = deepcopy(self.dm.locations.get(self.current_file))
        if not editor_data:
            return
            
        agents_data = {}
        for npc in editor_data.get("npcs", []):
            npc_id = npc.get("ref_id")
            pos = npc.get("position", {"x": 5.0, "y": 5.0})
            if npc_id:
                agents_data[npc_id] = {
                    "position": "",
                    "local_position": pos,
                    "intent": {
                        "target_type": "ANCHOR",
                        "target_id": "bar",
                        "reason": "test_sim"
                    }
                }

        payload = {
            "campaign_id": "Open_road",
            "location_id": self.current_file.replace(".json", ""),
            "editor_data": editor_data,
            "agents_data": agents_data
        }
        
        def fetch_data():
            try:
                req = urllib.request.Request(
                    "http://localhost:8000/api/spatial/observatory",
                    data=json.dumps(payload).encode('utf-8'),
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=5.0) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    # S-OBS-05: Latest-state-wins validation
                    with self._observatory_lock:
                        if revision == self._observatory_revision:
                            self.observatory_data = data
            except urllib.error.HTTPError as e:
                error_body = e.read().decode('utf-8')
                print(f"[OBSERVATORY_API_ERROR] {error_body}")
            except Exception as e:
                print(f"[OBSERVATORY_ERROR] {e}")
                
        threading.Thread(target=fetch_data, daemon=True).start()

    def _dialog_save_as(self):
        """Сохраняет локацию в выбранную папку через проводник"""
        if not self.current_file or self.current_file not in self.dm.locations:
            self._show_toast("Нет открытого файла")
            return
        import tkinter as tk
        from pathlib import Path
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        # Начальная папка — текущая кампания или campaigns
        init_dir = (
            str(self.cm.campaign_path)
            if self.cm.campaign_path
            else str(Path(__file__).parent / "campaigns")
        )
        filepath = filedialog.asksaveasfilename(
            title="Сохранить локацию как...",
            initialdir=init_dir,
            initialfile=self.current_file,
            filetypes=[("JSON файлы", "*.json"), ("Все файлы", "*.*")],
        )
        root.destroy()
        if not filepath:
            return
        filepath = Path(filepath)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(
                    self.dm.locations[self.current_file],
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
            self._open_file_path = filepath
            self._show_toast(f"Сохранено: {filepath.name}")
        except Exception as e:
            self._show_toast(f"Ошибка сохранения: {e}")

    def _save_all(self):
        count = self.cm.save_all_locations()
        self._rebuild_spatial_registry()
        self._show_toast(f"Сохранено локаций: {count}")

    def _rebuild_spatial_registry(self) -> None:
        """S80.2: Запрашивает перестроение реестра через Gateway.
        Editor — только триггер, не владелец истины."""
        try:
            from spatial_compilation_gateway import SpatialCompilationGateway

            # V8-ED-5 FIX: Используем campaign_path из CampaignManager, не dm.base_dir
            if self.cm.campaign_path:
                campaign_id = self.cm.campaign_path.name
                SpatialCompilationGateway.request_rebuild(campaign_id)
            else:
                import logging as _logging
                _logging.getLogger(__name__).warning("[EDITOR] _rebuild_spatial_registry: campaign not open, skipping")
        except Exception as e:
            import logging as _logging

            _logging.getLogger(__name__).warning(
                f"[SPATIAL_REGISTRY] Ошибка компиляции: {e}"
            )

    def _dialog_export_zip(self):
        """Диалог экспорта кампании в zip"""
        name = (
            self.cm.campaign_data.get("name", "campaign")
            if self.cm.campaign_data
            else "campaign"
        )
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
            {
                "key": "folder",
                "label": "Имя папки кампании",
                "value": "imported_campaign",
            },
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

    def _toggle_grid(self):
        """Переключает видимость сетки"""
        self.show_grid = not self.show_grid
        self._show_toast(f"Сетка: {'вкл' if self.show_grid else 'выкл'}")

    def _show_toast(self, message: str, duration: int = 180):
        """Показывает временное сообщение"""
        self.toast_message = message
        self.toast_timer = duration

    def _center_camera(self):
        """Центрирует камеру на текущей локации"""
        if self.current_file and self.current_file in self.dm.locations:
            loc = self.dm.locations[self.current_file]  # noqa: F841
            origin = loc.get("origin", {"x": 0, "y": 0})
            cx = origin["x"] + loc["size"]["w"] / 2
            cy = origin["y"] + loc["size"]["h"] / 2
            screen_cx = (self.screen.get_width() - self.panel_width) / 2
            screen_cy = (
                self.screen.get_height() - self.menu_height - self.toolbar_height
            ) / 2
            self.camera_x = screen_cx - cx * SCALE * self.zoom
            self.camera_y = (
                screen_cy
                - cy * SCALE * self.zoom
                + self.menu_height
                + self.toolbar_height
            )

    # === Координатные преобразования ===
    def world_to_screen(self, wx: float, wy: float) -> Tuple[int, int]:
        """Преобразует мировые координаты в экранные"""
        return Geometry.world_to_screen(self.camera_x, self.camera_y, self.zoom, wx, wy)

    def screen_to_world(self, sx: int, sy: int) -> Tuple[float, float]:
        """Преобразует экранные координаты в мировые"""
        return Geometry.screen_to_world(self.camera_x, self.camera_y, self.zoom, sx, sy)

    def snap_to_grid(
        self, x: float, y: float, grid_size: float = 0.5
    ) -> Tuple[float, float]:
        """Привязывает координаты к сетке"""
        return Geometry.snap_to_grid(x, y, grid_size)

    def _rotated_rect_points(
        self, cx: float, cy: float, w: float, h: float, angle_deg: float
    ) -> List[Tuple[float, float]]:
        """Возвращает 4 точки повёрнутого прямоугольника"""
        return Geometry.rotated_rect_points(cx, cy, w, h, angle_deg)

    def _get_rotation_buttons(self, obj_id: str) -> List[Dict[str, Any]]:
        """Возвращает кнопки поворота/зеркала для выделенного объекта"""
        if not self.current_file or not obj_id:
            return []
        loc = self.dm.locations[self.current_file]  # noqa: F841
        obj = next((o for o in loc["objects"] if o.get("id") == obj_id), None)
        if not obj:
            return []
        sx, sy = self.world_to_screen(obj["position"]["x"], obj["position"]["y"])
        w = obj["size"]["w"] * SCALE * self.zoom
        h = obj["size"]["h"] * SCALE * self.zoom
        radius = max(w, h) / 2 + 14
        btn_r = 10

        # Определяем режим из пресета
        obj_type = obj.get("type", "")
        preset = OBJECT_PRESETS.get(obj_type, {})
        mode = preset.get("rotation_mode", "free")

        if mode == "mirror":
            # Одна кнопка зеркалирования сверху
            return [
                {
                    "rect": pygame.Rect(
                        sx - btn_r, sy - radius - btn_r, btn_r * 2, btn_r * 2
                    ),
                    "action": "mirror",
                },
            ]
        else:
            # Две кнопки поворота по бокам
            return [
                {
                    "rect": pygame.Rect(
                        sx - radius - btn_r, sy - btn_r, btn_r * 2, btn_r * 2
                    ),
                    "delta": -45,
                },
                {
                    "rect": pygame.Rect(
                        sx + radius - btn_r, sy - btn_r, btn_r * 2, btn_r * 2
                    ),
                    "delta": 45,
                },
            ]

    def _get_resize_handles(self, obj_id: str) -> List[Dict[str, Any]]:
        """Возвращает хэндлы углов для ресайза объекта"""
        if not self.current_file or not obj_id:
            return []
        loc = self.dm.locations[self.current_file]  # noqa: F841
        obj = next((o for o in loc["objects"] if o.get("id") == obj_id), None)
        if not obj:
            return []

        sx, sy = self.world_to_screen(obj["position"]["x"], obj["position"]["y"])
        w = obj["size"]["w"] * SCALE * self.zoom
        h = obj["size"]["h"] * SCALE * self.zoom
        hs = 5  # половина размера хэндла

        # Определяем режим из пресета
        obj_type = obj.get("type", "")
        preset = OBJECT_PRESETS.get(obj_type, {})
        is_wall_mounted = preset.get("requires_wall", False)

        if is_wall_mounted:
            # Определяем длинную сторону (длина двери) — её и ресайзим
            if w >= h:  # дверь горизонтальна
                return [
                    {
                        "rect": pygame.Rect(sx - w / 2 - hs, sy - hs, hs * 2, hs * 2),
                        "axis": "w",
                        "dir": -1,
                    },
                    {
                        "rect": pygame.Rect(sx + w / 2 - hs, sy - hs, hs * 2, hs * 2),
                        "axis": "w",
                        "dir": 1,
                    },
                ]
            else:  # дверь вертикальна (w и h были поменяны при создании)
                return [
                    {
                        "rect": pygame.Rect(sx - hs, sy - h / 2 - hs, hs * 2, hs * 2),
                        "axis": "h",
                        "dir": -1,
                    },
                    {
                        "rect": pygame.Rect(sx - hs, sy + h / 2 - hs, hs * 2, hs * 2),
                        "axis": "h",
                        "dir": 1,
                    },
                ]
        else:
            # Четыре угла — свободный ресайз
            return [
                {
                    "rect": pygame.Rect(
                        sx - w / 2 - hs, sy - h / 2 - hs, hs * 2, hs * 2
                    ),
                    "axis": "wh",
                    "dir_x": -1,
                    "dir_y": -1,
                },
                {
                    "rect": pygame.Rect(
                        sx + w / 2 - hs, sy - h / 2 - hs, hs * 2, hs * 2
                    ),
                    "axis": "wh",
                    "dir_x": 1,
                    "dir_y": -1,
                },
                {
                    "rect": pygame.Rect(
                        sx - w / 2 - hs, sy + h / 2 - hs, hs * 2, hs * 2
                    ),
                    "axis": "wh",
                    "dir_x": -1,
                    "dir_y": 1,
                },
                {
                    "rect": pygame.Rect(
                        sx + w / 2 - hs, sy + h / 2 - hs, hs * 2, hs * 2
                    ),
                    "axis": "wh",
                    "dir_x": 1,
                    "dir_y": 1,
                },
            ]

    def _is_on_selected(self, mx: int, my: int) -> bool:
        """Проверяет, попал ли клик именно на выделенную сущность"""
        if not self.selected_object:
            return False
        old_sel = self.selected_object
        self._try_select_existing(mx, my)
        is_same = self.selected_object == old_sel
        self.selected_object = old_sel  # восстанавливаем выделение
        return is_same

    def _get_drag_orig(self, etype: str, eid: str) -> Optional[Dict]:
        """Возвращает исходные координаты сущности для перетаскивания"""
        if not self.current_file:
            return None
        loc = self.dm.locations[self.current_file]  # noqa: F841
        if etype == "object":
            obj = next((o for o in loc["objects"] if o.get("id") == eid), None)
            if obj:
                data = {
                    "x": obj["position"]["x"],
                    "y": obj["position"]["y"],
                    "wall_id": obj.get("wall_id"),
                }
                if data["wall_id"]:
                    wall = next(
                        (w for w in loc["walls"] if w["id"] == data["wall_id"]), None
                    )
                    if wall:
                        data["wx1"] = wall["x1"]
                        data["wy1"] = wall["y1"]
                        data["wx2"] = wall["x2"]
                        data["wy2"] = wall["y2"]
                return data
        elif etype == "wall":
            wall = next((w for w in loc["walls"] if w["id"] == eid), None)
            if wall:
                return {
                    "x1": wall["x1"],
                    "y1": wall["y1"],
                    "x2": wall["x2"],
                    "y2": wall["y2"],
                }
        elif etype == "room":
            room = next((r for r in loc["rooms"] if r["id"] == eid), None)
            if room:
                data = {"x": room["x"], "y": room["y"]}
                if "polygon" in room:
                    data["polygon"] = [list(p) for p in room["polygon"]]
                return data
        elif etype == "node":
            node = loc["nodes"].get(eid)
            if node:
                return {"x": node["x"], "y": node["y"]}
        elif etype == "label":
            lbl = next((l for l in loc.get("labels", []) if l.get("id") == eid), None)  # noqa: E741
            if lbl:
                return {"x": lbl["x"], "y": lbl["y"]}
        elif etype == "npc":
            npc = next((n for n in loc.get("npcs", []) if n.get("ref_id") == eid), None)
            if npc:
                return {"x": npc["position"]["x"], "y": npc["position"]["y"]}
        elif etype == "spawn":
            spawn = loc.get("player_spawn")
            if spawn:
                return {"x": spawn["x"], "y": spawn["y"]}
        return None

    def _apply_drag(
        self, etype: str, eid: str, orig: Dict, dx: float, dy: float
    ) -> None:
        """Смещает сущность на dx, dy от исходных координат"""
        loc = self.dm.locations[self.current_file]  # noqa: F841
        if etype == "object":
            obj = next((o for o in loc["objects"] if o.get("id") == eid), None)
            if obj:
                target_x = orig["x"] + dx
                target_y = orig["y"] + dy
                
                # S143 §1: Snapping дверей к стенам при перетаскивании
                if obj.get("type") in ("door", "door_transition"):
                    wall_id = self._find_wall_near(target_x, target_y, threshold=1.5)
                    if wall_id:
                        wall = next((w for w in loc["walls"] if w["id"] == wall_id), None)
                        if wall:
                            # Проекция точки на отрезок стены (прилипание)
                            snap_x, snap_y = self._project_point_to_segment(
                                target_x, target_y, wall["x1"], wall["y1"], wall["x2"], wall["y2"]
                            )
                            obj["position"]["x"] = snap_x
                            obj["position"]["y"] = snap_y
                            obj["wall_id"] = wall_id
                            return
                    # Если стены рядом нет — оставляем дверь где есть, но снимаем привязку
                    obj["position"]["x"] = target_x
                    obj["position"]["y"] = target_y
                    obj["wall_id"] = ""
                    return

                obj["position"]["x"] = target_x
                obj["position"]["y"] = target_y
                if orig.get("wall_id"):
                    wall = next(
                        (w for w in loc["walls"] if w["id"] == orig["wall_id"]), None
                    )
                    if wall and "wx1" in orig:
                        wall["x1"] = orig["wx1"] + dx
                        wall["y1"] = orig["wy1"] + dy
                        wall["x2"] = orig["wx2"] + dx
                        wall["y2"] = orig["wy2"] + dy
        elif etype == "wall":
            wall = next((w for w in loc["walls"] if w["id"] == eid), None)
            if wall:
                wall["x1"] = orig["x1"] + dx
                wall["y1"] = orig["y1"] + dy
                wall["x2"] = orig["x2"] + dx
                wall["y2"] = orig["y2"] + dy
        elif etype == "room":
            room = next((r for r in loc["rooms"] if r["id"] == eid), None)
            if room:
                room["x"] = orig["x"] + dx
                room["y"] = orig["y"] + dy
                if "polygon" in orig:
                    room["polygon"] = [[p[0] + dx, p[1] + dy] for p in orig["polygon"]]
        elif etype == "node":
            node = loc["nodes"].get(eid)
            if node:
                node["x"] = orig["x"] + dx
                node["y"] = orig["y"] + dy
        elif etype == "label":
            lbl = next((l for l in loc.get("labels", []) if l.get("id") == eid), None)  # noqa: E741
            if lbl:
                lbl["x"] = orig["x"] + dx
                lbl["y"] = orig["y"] + dy
        elif etype == "npc":
            npc = next((n for n in loc.get("npcs", []) if n.get("ref_id") == eid), None)
            if npc:
                npc["position"]["x"] = orig["x"] + dx
                npc["position"]["y"] = orig["y"] + dy
        elif etype == "spawn":
            spawn = loc.get("player_spawn")
            if spawn:
                spawn["x"] = orig["x"] + dx
                spawn["y"] = orig["y"] + dy

    def _copy_selection(self) -> None:
        """Копирует выделенный объект или стену в буфер"""
        if not self.current_file or not self.selected_object:
            return
        obj_type, obj_key = self.selected_object
        # NPC и spawn не копируются
        if obj_type in ("npc", "spawn"):
            return
        loc = self.dm.locations[self.current_file]  # noqa: F841
        self.clipboard = {"walls": [], "objects": [], "origin": (0.0, 0.0)}
        self.current_z: int = 0
        self.current_z: int = 0

        if obj_type == "object":
            obj = next((o for o in loc["objects"] if o.get("id") == obj_key), None)
            if obj:
                self.clipboard["objects"] = [deepcopy(obj)]
                self.clipboard["origin"] = (obj["position"]["x"], obj["position"]["y"])
                self._show_toast(f"Скопирован: {obj['type']}")
        elif obj_type == "wall":
            wall = next((w for w in loc["walls"] if w["id"] == obj_key), None)
            if wall:
                self.clipboard["walls"] = [deepcopy(wall)]
                self.clipboard["origin"] = (
                    (wall["x1"] + wall["x2"]) / 2,
                    (wall["y1"] + wall["y2"]) / 2,
                )
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
        self._running = True
        while self._running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False

                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode(
                        (event.w, event.h), pygame.RESIZABLE
                    )
                    self._init_ui()

                elif self.dialog and getattr(self.dialog, "active", False):
                    if self.dialog.handle_event(event):
                        continue
                elif hasattr(self, "calibration_panel") and self.calibration_panel and getattr(self.calibration_panel, "active", False):
                    self.calibration_panel.handle_event(event)
                elif hasattr(self, "vc_editor") and self.vc_editor and getattr(self.vc_editor, "active", False):
                    if self.vc_editor.handle_event(event):
                        continue
                else:
                    self._handle_event(event)

            self._update_observatory()
            self._update()
            self._draw()
            pygame.display.flip()
            self.clock.tick(60)

        return

    def _handle_event(self, event: pygame.event.Event):
        self.event_handler.handle_event(self, event)

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

    def _handle_double_click(self, mx: int, my: int) -> None:
        """Обрабатывает двойной клик — редактирование свойств сущности"""
        if not self.current_file or not self.selected_object:
            return

        entity_type, entity_id = self.selected_object
        old_name = self.dm.get_entity_name(self.current_file, entity_type, entity_id)

        # ADR-O-326: Для навигационных узлов открываем расширенный редактор
        if entity_type == "node":
            node_data = self.dm.locations[self.current_file]["nodes"].get(entity_id, {})
            old_role = node_data.get("role", "default")
            old_tags = ", ".join(node_data.get("tags", []))

            fields = [
                {"key": "name", "label": "Название (Label)", "value": old_name},
                {
                    "key": "role",
                    "label": "Роль (NodeRole)",
                    "type": "choice",
                    "value": old_role,
                    "options": [
                        "default", "bar", "bed", "entrance", "table",
                        "workbench", "market", "transition", "boundary",
                        "guard_post", "dark_corner", "serving_station",
                        "kitchen_counter", "inn_desk"
                    ]
                },
                {"key": "tags", "label": "Теги (через запятую)", "value": old_tags}
            ]

            def on_node_confirm(inputs: Dict[str, str]) -> None:
                new_name = inputs.get("name", "").strip()
                new_role = inputs.get("role", "default")
                tags_str = inputs.get("tags", "")
                new_tags = [t.strip() for t in tags_str.split(",") if t.strip()]

                # Используем простой undo через обновление состояния
                self.undo.push(
                    SimpleNodeUpdateCommand(
                        self.dm, self.current_file, entity_id,
                        old_name, old_role, node_data.get("tags", []),
                        new_name, new_role, new_tags
                    )
                )
                self._show_toast(f"Узел обновлён: {new_name}")

            self.dialog = ModalDialog(self.screen, "Свойства узла", fields, on_node_confirm)
            return

        # Стандартное переименование для остальных объектов
        fields = [{"key": "name", "label": "Новое имя", "value": old_name}]

        def on_confirm(inputs: Dict[str, str]) -> None:
            new_name = inputs.get("name", "").strip()
            if new_name and new_name != old_name:
                self.undo.push(
                    RenameCommand(
                        self.dm,
                        self.current_file,
                        entity_type,
                        entity_id,
                        old_name,
                        new_name,
                    )
                )
                self._show_toast(f"Переименовано: {new_name}")

        self.dialog = ModalDialog(self.screen, "Переименовать", fields, on_confirm)

    def _handle_left_click(self, mx: int, my: int, wx: float, wy: float, gx: float, gy: float):
        self.interaction_manager.handle_left_click(self, mx, my, wx, wy, gx, gy)

    def _handle_left_release(self, mx: int, my: int, wx: float, wy: float, gx: float, gy: float):
        self.interaction_manager.handle_left_release(self, mx, my, wx, wy, gx, gy)

    def _try_auto_room(self, last_wall_id: str) -> None:
        self.interaction_manager.try_auto_room(self, last_wall_id)

    def _find_wall_near(self, wx: float, wy: float, threshold: float = 1.0) -> Optional[str]:
        return self.interaction_manager.find_wall_near(self, wx, wy, threshold)

    def _is_point_in_any_room(self, wx: float, wy: float) -> bool:
        return self.interaction_manager.is_point_in_any_room(self, wx, wy)

    def _point_to_segment_dist(
        self, px: float, py: float, x1: float, y1: float, x2: float, y2: float
    ) -> float:
        """Расстояние от точки до отрезка"""
        return Geometry.point_to_segment_dist(px, py, x1, y1, x2, y2)

    def _project_point_to_segment(
        self, px: float, py: float, x1: float, y1: float, x2: float, y2: float
    ) -> Tuple[float, float]:
        """Проецирует точку на отрезок. Возвращает (proj_x, proj_y)."""
        return Geometry.project_point_to_segment(px, py, x1, y1, x2, y2)

    def _check_wall_overlap(self, x1: float, y1: float, x2: float, y2: float, tolerance: float = 0.01) -> bool:
        return self.interaction_manager.check_wall_overlap(self, x1, y1, x2, y2, tolerance)

    def _segments_intersect(
        self, x1: float, y1: float, x2: float, y2: float,
        x3: float, y3: float, x4: float, y4: float
    ) -> bool:
        """Стандартный алгоритм проверки пересечения отрезков (CCW)."""
        return Geometry.segments_intersect(x1, y1, x2, y2, x3, y3, x4, y4)

    def _try_select_existing(self, mx: int, my: int) -> bool:
        return self.interaction_manager.try_select_existing(self, mx, my)

    def _delete_at(self, mx: int, my: int):
        self.interaction_manager.delete_at(self, mx, my)

    def _point_near_line(
        self, px: int, py: int, x1: int, y1: int, x2: int, y2: int, threshold: int
    ) -> bool:
        """Проверяет, находится ли точка рядом с отрезком"""
        return Geometry.point_near_line(px, py, x1, y1, x2, y2, threshold)

    def _handle_property_action(self, action: str):
        """Обрабатывает действия из панели свойств"""
        if not self.current_file:
            return

        # Действия над локацией (когда ничего не выделено)
        if not self.selected_object:
            loc = self.dm.locations[self.current_file]  # noqa: F841
            if action == "set_location_id":
                current_val = loc.get("location_id", "")
                fields = [
                    {"key": "location_id", "label": "location_id", "value": current_val}
                ]

                def on_confirm(inputs: Dict[str, str]) -> None:
                    new_val = inputs.get("location_id", "").strip()
                    loc["location_id"] = new_val
                    self._show_toast(f"location_id = {new_val or '(пусто)'}")

                self.dialog = ModalDialog(
                    self.screen, "Задать location_id", fields, on_confirm
                )
            return

        obj_type, obj_key = self.selected_object
        loc = self.dm.locations[self.current_file]  # noqa: F841

        if action == "create_perimeter_walls" and obj_type == "room":
            room = next((r for r in loc["rooms"] if r["id"] == obj_key), None)
            if room:
                existing = self._find_room_perimeter_walls(room)

                if existing:
                    # Стены есть → УДАЛЯЕМ их
                    for wall in existing:
                        self.dm.remove_wall(self.current_file, wall["id"])
                    self._show_toast(
                        f"Удалено стен: {len(existing)} для {room['name']}"
                    )
                else:
                    # Стен нет → СОЗДАЁМ их
                    thickness = 0.2
                    poly = room.get("polygon")
                    created = 0

                    if poly and len(poly) >= 3:
                        for i in range(len(poly)):
                            x1, y1 = poly[i]
                            x2, y2 = poly[(i + 1) % len(poly)]
                            self.dm.add_wall(
                                self.current_file, x1, y1, x2, y2, "wall", thickness
                            )
                            created += 1
                    else:
                        rx, ry = room["x"], room["y"]
                        rw, rh = room["width"], room["height"]
                        perimeter = [
                            (rx, ry, rx + rw, ry),
                            (rx + rw, ry, rx + rw, ry + rh),
                            (rx, ry + rh, rx + rw, ry + rh),
                            (rx, ry, rx, ry + rh),
                        ]
                        for wx1, wy1, wx2, wy2 in perimeter:
                            self.dm.add_wall(
                                self.current_file, wx1, wy1, wx2, wy2, "wall", thickness
                            )
                            created += 1
                    self._show_toast(f"Создано стен: {created} для {room['name']}")

                self._update_property_panel()
            return

        if action == "rename":
            old_name = self.dm.get_entity_name(self.current_file, obj_type, obj_key)
            fields = [{"key": "name", "label": "Новое имя", "value": old_name}]

            def on_confirm(inputs: Dict[str, str]) -> None:
                new_name = inputs.get("name", "").strip()
                if new_name and new_name != old_name:
                    self.undo.push(
                        RenameCommand(
                            self.dm,
                            self.current_file,
                            obj_type,
                            obj_key,
                            old_name,
                            new_name,
                        )
                    )
                    self._show_toast(f"Переименовано: {new_name}")

            self.dialog = ModalDialog(self.screen, "Переименовать", fields, on_confirm)
            return

        if action == "toggle_show_name" and obj_type == "object":
            obj = next((o for o in loc["objects"] if o.get("id") == obj_key), None)
            if obj:
                obj["show_name"] = not obj.get("show_name", False)
            return

        if action == "edit_psyche" and obj_type == "npc":
            from data_manager import load_npc_calibration, save_npc_calibration
            from ui.dialogs import CalibrationPanel
            
            npc = next((n for n in loc.get("npcs", []) if n["ref_id"] == obj_key), None)
            if not npc:
                return
            
            psyche, drives = load_npc_calibration(npc["ref_id"])
            
            def on_save_psyche(new_psyche, new_drives):
                save_npc_calibration(npc["ref_id"], new_psyche, new_drives)
                self._show_toast(f"Психика откалибрована для {npc['ref_id']}")
                self.calibration_panel = None

            self.calibration_panel = CalibrationPanel(
                self.screen, npc["ref_id"], npc.get("name", npc["ref_id"]), psyche, drives
            )
            self.calibration_panel.on_save = on_save_psyche
            return

        if action == "edit_portraits" and obj_type == "npc":
            from data_manager import load_npc_visual_casting, save_npc_visual_casting
            from visual_casting_editor import VisualCastingEditor
            npc = next((n for n in loc.get("npcs", []) if n["ref_id"] == obj_key), None)
            if not npc:
                return
            
            current_casting = load_npc_visual_casting(npc["ref_id"])
            if not current_casting:
                current_casting = {"fallback": {"expression_id": "neutral", "asset": ["", 0, 0]}, "rules": []}
                
            def on_save_casting(new_casting):
                save_npc_visual_casting(npc["ref_id"], new_casting)
                self._show_toast(f"Visual Casting сохранён для {npc['ref_id']}")
                self.vc_editor = None

            self.vc_editor = VisualCastingEditor(self.screen, npc["ref_id"], current_casting)
            self.vc_editor.on_save = on_save_casting
            return

        if action == "pick_sprite":
            from visual_casting_editor import VisualCastingEditor
            
            if obj_type == "object":
                obj = next((o for o in loc["objects"] if o.get("id") == obj_key), None)
                if obj:
                    current_sprite = obj.get("sprite", [])
                    dummy_casting = {"fallback": {"expression_id": "neutral", "asset": current_sprite}, "rules": []}
                    
                    def on_save_obj_sprite(new_casting):
                        fb = new_casting.get("fallback", {}).get("asset")
                        if fb and len(fb) >= 5:
                            obj["sprite"] = fb
                            self._show_toast("Спрайт объекта обновлён")
                        self.vc_editor = None
                        
                    self.vc_editor = VisualCastingEditor(self.screen, obj["id"], dummy_casting, simple_mode=True)
                    self.vc_editor.on_save = on_save_obj_sprite
                    return

            elif obj_type == "npc":
                npc = next((n for n in loc.get("npcs", []) if n["ref_id"] == obj_key), None)
                if npc:
                    current_sprite = npc.get("sprite", [])
                    dummy_casting = {"fallback": {"expression_id": "neutral", "asset": current_sprite}, "rules": []}
                    
                    def on_save_npc_sprite(new_casting):
                        fb = new_casting.get("fallback", {}).get("asset")
                        if fb and (isinstance(fb, dict) or len(fb) >= 5):
                            npc["sprite"] = fb
                            self._show_toast("Спрайт NPC обновлён")
                        self.vc_editor = None
                        
                    self.vc_editor = VisualCastingEditor(self.screen, npc["ref_id"], dummy_casting, simple_mode=True)
                    self.vc_editor.on_save = on_save_npc_sprite
                    return

        if action == "rename_label":
            lbl = next((l for l in loc["labels"] if l["id"] == obj_key), None)  # noqa: E741
            if lbl:
                old_text = lbl.get("text", "")
                fields = [{"key": "text", "label": "Текст", "value": old_text}]

                def on_confirm_lbl(inputs: Dict[str, str]) -> None:
                    new_text = inputs.get("text", "").strip()
                    if new_text and new_text != old_text:
                        self.dm.rename_label(self.current_file, obj_key, new_text)
                        self._show_toast("Текст изменён")

                self.dialog = ModalDialog(
                    self.screen, "Изменить текст", fields, on_confirm_lbl
                )
            return

        if action.startswith("toggle_"):
            flag = action[7:]  # Убираем "toggle_"
            if obj_type == "object":
                obj = next((o for o in loc["objects"] if o.get("id") == obj_key), None)
            if not obj:
                return
            self.undo.push(
                TogglePassabilityCommand(
                    self.dm, self.current_file, obj_key, flag, obj["passability"][flag]
                )
            )

    def _update(self):
        """Обновляет состояние"""
        if self.toast_timer > 0:
            self.toast_timer -= 1

        # Плавное движение камеры стрелками (проверяем зажатие)
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            self.camera_x += self.camera_speed
        if keys[pygame.K_RIGHT]:
            self.camera_x -= self.camera_speed
        if keys[pygame.K_UP]:
            self.camera_y += self.camera_speed
        if keys[pygame.K_DOWN]:
            self.camera_y -= self.camera_speed

        # Обновляем панель свойств
        if self.mode == MODE_LAB:
            self.lab_screen.update()
        else:
            self._update_property_panel()

    def _update_property_panel(self):
        self.property_builder.update(self)

    # === ОТРИСОВКА ===
    def _draw(self):
        """Отрисовывает всё"""
        self.screen.fill(COLORS["bg_dark"])

        if self.mode == MODE_LAB:
            self.lab_screen.draw()
            return  # Выходим, чтобы не рисовать тулбар и меню редактора

        if self.mode == MODE_WORLD:
            self._draw_world()
        else:
            self._draw_local()

        # UI поверх всего
        self._draw_ui()

        # Диалог
        if self.dialog and getattr(self.dialog, "active", False):
            if isinstance(self.dialog, DropDownMenu):
                self.dialog.draw(self.screen, self.font)
            else:
                self.dialog.draw(self.font, self.font_small)
        if hasattr(self, "calibration_panel") and self.calibration_panel and getattr(self.calibration_panel, "active", False):
            self.calibration_panel.draw(self.font, self.font_small)
        elif hasattr(self, "vc_editor") and self.vc_editor and getattr(self.vc_editor, "active", False):
            self.vc_editor.draw(self.font, self.font_small)

    def _draw_world(self):
        self.renderer.draw_world(self)

    def _draw_local(self):
        self.renderer.draw_local(self)

    def _draw_ui(self):
        self.renderer.draw_ui(self)

    def _get_location_screen_rect(self, fname: str) -> Optional[pygame.Rect]:
        """Возвращает экранный прямоугольник локации"""
        if fname not in self.dm.locations:
            return None
        data = self.dm.locations[fname]
        sx, sy = self.world_to_screen(data["origin"]["x"], data["origin"]["y"])
        sw = data["size"]["w"] * SCALE * self.zoom
        sh = data["size"]["h"] * SCALE * self.zoom
        return pygame.Rect(sx, sy, sw, sh)

    def _find_room_perimeter_walls(self, room: dict) -> list:
        """Находит стены, совпадающие с рёбрами комнаты (прямоугольной или полигональной)"""
        if not self.current_file:
            return []
        loc = self.dm.locations[self.current_file]
        walls = loc.get("walls", [])
        if not walls:
            return []
        edges = []
        poly = room.get("polygon")
        if poly and len(poly) >= 3:
            for i in range(len(poly)):
                edges.append(
                    (
                        poly[i][0],
                        poly[i][1],
                        poly[(i + 1) % len(poly)][0],
                        poly[(i + 1) % len(poly)][1],
                    )
                )
        else:
            rx, ry = room["x"], room["y"]
            rw, rh = room["width"], room["height"]
            edges = [
                (rx, ry, rx + rw, ry),
                (rx + rw, ry, rx + rw, ry + rh),
                (rx, ry + rh, rx + rw, ry + rh),
                (rx, ry, rx, ry + rh),
            ]
        matched = []
        for wall in walls:
            for ex1, ey1, ex2, ey2 in edges:
                direct = (
                    abs(wall["x1"] - ex1) < 0.3
                    and abs(wall["y1"] - ey1) < 0.3
                    and abs(wall["x2"] - ex2) < 0.3
                    and abs(wall["y2"] - ey2) < 0.3
                )
                reverse = (
                    abs(wall["x1"] - ex2) < 0.3
                    and abs(wall["y1"] - ey2) < 0.3
                    and abs(wall["x2"] - ex1) < 0.3
                    and abs(wall["y2"] - ey1) < 0.3
                )
                if direct or reverse:
                    matched.append(wall)
                    break
        return matched


# Точка входа
if __name__ == "__main__":
    app = EditorCore()
    app.run()
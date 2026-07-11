"""
map_editor/editor_core.py
Главный редактор карт - ядро приложения
"""
import pygame
import json
from sprite_registry import sprite_registry
import math
from typing import Optional, Tuple, Dict, List, Any
from dataclasses import dataclass

from copy import deepcopy

from data_manager import DataManager, OBJECT_PRESETS, NPC_SPRITE_MAP, load_npc_individuals
from undo_manager import (
    UndoManager, AddWallCommand, RemoveWallCommand,
    AddRoomCommand, RemoveRoomCommand,
    RemoveNodeCommand,
    AddObjectCommand, RemoveObjectCommand,
    AddPassageCommand,
    TogglePassabilityCommand, RotateObjectCommand, MirrorObjectCommand, ResizeObjectCommand, MoveEntityCommand, PasteCommand,
    CompoundCommand, RenameCommand, AddLabelCommand, RemoveLabelCommand,
    AddNpcCommand, RemoveNpcCommand,
)
from campaign_manager import CampaignManager
from ui_components import (
    COLORS, Button, ToggleButton, Dropdown,
    ModalDialog, PropertyPanel, DropDownMenu
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
TOOL_PASSAGE = "passage"  # Создание прохода в стене
TOOL_LABEL = "label"      # Создание надписи
TOOL_NPC = "npc"          # Размещение NPC
TOOL_SPAWN = "spawn"      # Установка точки спавна игрока
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
        self._show_toast("Добро пожаловать! Откройте или создайте кампанию через меню File")
    
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
        
        self.btn_tool_passage = ToggleButton(x, toolbar_y, 90, 32, "🕳️ Проход",
                                              on_toggle=lambda s: self._set_tool(TOOL_PASSAGE) if s else None)
        self.toolbar_buttons.append(self.btn_tool_passage)
        x += 100
        
        self.btn_tool_label = ToggleButton(x, toolbar_y, 80, 32, "📝 Надпись",
                                           on_toggle=lambda s: self._set_tool(TOOL_LABEL) if s else None)
        self.toolbar_buttons.append(self.btn_tool_label)
        x += 90
        
        # Группа: Сущности
        x += 10
        self.btn_tool_npc = ToggleButton(x, toolbar_y, 80, 32, "👤 NPC",
                                         on_toggle=lambda s: self._set_tool(TOOL_NPC) if s else None)
        self.toolbar_buttons.append(self.btn_tool_npc)
        x += 90
        
        self.btn_tool_spawn = ToggleButton(x, toolbar_y, 90, 32, "🏁 Спавн",
                                           on_toggle=lambda s: self._set_tool(TOOL_SPAWN) if s else None)
        self.toolbar_buttons.append(self.btn_tool_spawn)
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
                700, self.menu_height + 8, 120, 28,
                options=options, label="Тип"
            )
            self.object_dropdown.selected = preset_keys.index(self.selected_object_type)
            self.object_dropdown.on_select = lambda i, opt: setattr(self, 'selected_object_type', preset_keys[i])
        
        elif self.tool == TOOL_NPC:
            if not self._npc_list:
                self.object_dropdown = Dropdown(
                    700, self.menu_height + 8, 180, 28,
                    options=["Нет NPC в config"], label="NPC"
                )
                self.object_dropdown.enabled = False
            else:
                npc_ids = [n["id"] for n in self._npc_list]
                options = [n["name"] for n in self._npc_list]
                self.object_dropdown = Dropdown(
                    700, self.menu_height + 8, 180, 28,
                    options=options, label="NPC"
                )
                try:
                    self.object_dropdown.selected = npc_ids.index(self.selected_npc_id)
                except ValueError:
                    self.object_dropdown.selected = 0
                    self.selected_npc_id = npc_ids[0]
                self.object_dropdown.on_select = lambda i, opt: setattr(self, 'selected_npc_id', npc_ids[i])
    
    def _show_file_menu(self):
        """Показывает выпадающее меню File"""
        items = [
            {"label": "Новая кампания...", "action": self._dialog_create_campaign},
            {"label": "Открыть кампанию...", "action": self._dialog_open_folder},
            {"type": "separator"},
            {"label": "Закрыть кампанию", "action": self._close_campaign,
             "disabled": not self.cm.is_open},
            {"type": "separator"},
            {"label": "Новая локация...", "action": self._dialog_new_location,
             "disabled": not self.cm.is_open},
            {"label": "Удалить локацию...", "action": self._dialog_delete_location,
             "disabled": not self.cm.is_open or not self.current_file},
            {"type": "separator"},
            {"label": "Сохранить всё", "action": self._save_campaign,
             "shortcut": "Ctrl+Shift+S", "disabled": not self.cm.is_open},
            {"label": "Сохранить", "action": self._quick_save,
             "shortcut": "Ctrl+S", "disabled": not self.current_file},
            {"label": "Сохранить как...", "action": self._dialog_save_as,
             "disabled": not self.current_file},
            {"type": "separator"},
            {"label": "Экспорт в ZIP...", "action": self._dialog_export_zip,
             "disabled": not self.cm.is_open},
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
            choice = inputs["choice"]
            # Безопасный поиск: точное совпадение или по началу строки
            idx = -1
            for i, opt in enumerate(options):
                if opt == choice or opt.startswith(choice):
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
                self._show_toast(f"Открыта: {self.cm.campaign_data['name']}")
            else:
                self._show_toast(f"Ошибка: {err}")
        self.dialog = ModalDialog(self.screen, "Открыть кампанию", fields, on_confirm)

    def _dialog_open_folder(self):
        """Открывает системный проводник для выбора папки с campaign.json"""
        import tkinter as tk
        from tkinter import filedialog
        from pathlib import Path
        # Скрываем мини-окно tkinter
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(
            title="Выберите папку с campaign.json",
            initialdir=str(Path(__file__).parent.parent.parent)
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
        from tkinter import filedialog
        from pathlib import Path
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        filepath = filedialog.askopenfilename(
            title="Выберите файл локации (.json)",
            initialdir=str(Path(__file__).parent / "location_templates"),
            filetypes=[("JSON файлы", "*.json"), ("Все файлы", "*.*")]
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
        fields = [{"key": "confirm", "label": f"Удалить '{loc_name}'? (да/нет)", "value": "нет", "type": "choice",
                    "options": ["нет", "да"]}]
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

    def _dialog_save_as(self):
        """Сохраняет локацию в выбранную папку через проводник"""
        if not self.current_file or self.current_file not in self.dm.locations:
            self._show_toast("Нет открытого файла")
            return
        import tkinter as tk
        from tkinter import filedialog
        from pathlib import Path
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        # Начальная папка — текущая кампания или campaigns
        init_dir = str(self.cm.campaign_path) if self.cm.campaign_path else str(Path(__file__).parent / "campaigns")
        filepath = filedialog.asksaveasfilename(
            title="Сохранить локацию как...",
            initialdir=init_dir,
            initialfile=self.current_file,
            filetypes=[("JSON файлы", "*.json"), ("Все файлы", "*.*")]
        )
        root.destroy()
        if not filepath:
            return
        filepath = Path(filepath)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.dm.locations[self.current_file], f, indent=2, ensure_ascii=False)
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
            campaign_id = self.dm.base_dir.parent.name
            SpatialCompilationGateway.request_rebuild(campaign_id)
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning(f"[SPATIAL_REGISTRY] Ошибка компиляции: {e}")

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
            loc = self.dm.locations[self.current_file]
            origin = loc.get("origin", {"x": 0, "y": 0})
            cx = origin["x"] + loc["size"]["w"] / 2
            cy = origin["y"] + loc["size"]["h"] / 2
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

    def _get_rotation_buttons(self, obj_id: str) -> List[Dict[str, Any]]:
        """Возвращает кнопки поворота/зеркала для выделенного объекта"""
        if not self.current_file or not obj_id:
            return []
        loc = self.dm.locations[self.current_file]
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
                {"rect": pygame.Rect(sx - btn_r, sy - radius - btn_r, btn_r * 2, btn_r * 2), "action": "mirror"},
            ]
        else:
            # Две кнопки поворота по бокам
            return [
                {"rect": pygame.Rect(sx - radius - btn_r, sy - btn_r, btn_r * 2, btn_r * 2), "delta": -45},
                {"rect": pygame.Rect(sx + radius - btn_r, sy - btn_r, btn_r * 2, btn_r * 2), "delta": 45},
            ]

    def _get_resize_handles(self, obj_id: str) -> List[Dict[str, Any]]:
        """Возвращает хэндлы углов для ресайза объекта"""
        if not self.current_file or not obj_id:
            return []
        loc = self.dm.locations[self.current_file]
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
                    {"rect": pygame.Rect(sx - w/2 - hs, sy - hs, hs * 2, hs * 2), "axis": "w", "dir": -1},
                    {"rect": pygame.Rect(sx + w/2 - hs, sy - hs, hs * 2, hs * 2), "axis": "w", "dir": 1},
                ]
            else:  # дверь вертикальна (w и h были поменяны при создании)
                return [
                    {"rect": pygame.Rect(sx - hs, sy - h/2 - hs, hs * 2, hs * 2), "axis": "h", "dir": -1},
                    {"rect": pygame.Rect(sx - hs, sy + h/2 - hs, hs * 2, hs * 2), "axis": "h", "dir": 1},
                ]
        else:
            # Четыре угла — свободный ресайз
            return [
                {"rect": pygame.Rect(sx - w/2 - hs, sy - h/2 - hs, hs * 2, hs * 2), "axis": "wh", "dir_x": -1, "dir_y": -1},
                {"rect": pygame.Rect(sx + w/2 - hs, sy - h/2 - hs, hs * 2, hs * 2), "axis": "wh", "dir_x": 1, "dir_y": -1},
                {"rect": pygame.Rect(sx - w/2 - hs, sy + h/2 - hs, hs * 2, hs * 2), "axis": "wh", "dir_x": -1, "dir_y": 1},
                {"rect": pygame.Rect(sx + w/2 - hs, sy + h/2 - hs, hs * 2, hs * 2), "axis": "wh", "dir_x": 1, "dir_y": 1},
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
        loc = self.dm.locations[self.current_file]
        if etype == "object":
            obj = next((o for o in loc["objects"] if o.get("id") == eid), None)
            if obj:
                data = {"x": obj["position"]["x"], "y": obj["position"]["y"], "wall_id": obj.get("wall_id")}
                if data["wall_id"]:
                    wall = next((w for w in loc["walls"] if w["id"] == data["wall_id"]), None)
                    if wall:
                        data["wx1"] = wall["x1"]; data["wy1"] = wall["y1"]
                        data["wx2"] = wall["x2"]; data["wy2"] = wall["y2"]
                return data
        elif etype == "wall":
            wall = next((w for w in loc["walls"] if w["id"] == eid), None)
            if wall: return {"x1": wall["x1"], "y1": wall["y1"], "x2": wall["x2"], "y2": wall["y2"]}
        elif etype == "room":
            room = next((r for r in loc["rooms"] if r["id"] == eid), None)
            if room:
                data = {"x": room["x"], "y": room["y"]}
                if "polygon" in room: data["polygon"] = [list(p) for p in room["polygon"]]
                return data
        elif etype == "node":
            node = loc["nodes"].get(eid)
            if node: return {"x": node["x"], "y": node["y"]}
        elif etype == "label":
            lbl = next((l for l in loc.get("labels", []) if l.get("id") == eid), None)
            if lbl: return {"x": lbl["x"], "y": lbl["y"]}
        elif etype == "npc":
            npc = next((n for n in loc.get("npcs", []) if n.get("ref_id") == eid), None)
            if npc: return {"x": npc["position"]["x"], "y": npc["position"]["y"]}
        elif etype == "spawn":
            spawn = loc.get("player_spawn")
            if spawn: return {"x": spawn["x"], "y": spawn["y"]}
        return None

    def _apply_drag(self, etype: str, eid: str, orig: Dict, dx: float, dy: float) -> None:
        """Смещает сущность на dx, dy от исходных координат"""
        loc = self.dm.locations[self.current_file]
        if etype == "object":
            obj = next((o for o in loc["objects"] if o.get("id") == eid), None)
            if obj:
                obj["position"]["x"] = orig["x"] + dx
                obj["position"]["y"] = orig["y"] + dy
                if orig.get("wall_id"):
                    wall = next((w for w in loc["walls"] if w["id"] == orig["wall_id"]), None)
                    if wall and "wx1" in orig:
                        wall["x1"] = orig["wx1"] + dx; wall["y1"] = orig["wy1"] + dy
                        wall["x2"] = orig["wx2"] + dx; wall["y2"] = orig["wy2"] + dy
        elif etype == "wall":
            wall = next((w for w in loc["walls"] if w["id"] == eid), None)
            if wall:
                wall["x1"] = orig["x1"] + dx; wall["y1"] = orig["y1"] + dy
                wall["x2"] = orig["x2"] + dx; wall["y2"] = orig["y2"] + dy
        elif etype == "room":
            room = next((r for r in loc["rooms"] if r["id"] == eid), None)
            if room:
                room["x"] = orig["x"] + dx; room["y"] = orig["y"] + dy
                if "polygon" in orig:
                    room["polygon"] = [[p[0] + dx, p[1] + dy] for p in orig["polygon"]]
        elif etype == "node":
            node = loc["nodes"].get(eid)
            if node:
                node["x"] = orig["x"] + dx; node["y"] = orig["y"] + dy
        elif etype == "label":
            lbl = next((l for l in loc.get("labels", []) if l.get("id") == eid), None)
            if lbl:
                lbl["x"] = orig["x"] + dx; lbl["y"] = orig["y"] + dy
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
        loc = self.dm.locations[self.current_file]
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
        self._running = True
        while self._running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
                    
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
        
        return
    
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
                elif self.selected_object is not None or self.tool is not None:
                    self.selected_object = None
                    self._set_tool(None)
                else:
                    self._running = False  # Выход в главное меню
                    
            elif event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
                # Удаление выбранного объекта
                if self.selected_object and self.tool is None:
                    self._delete_at(mx, my)
                    
            elif event.key == pygame.K_TAB:
                self._toggle_mode()
            elif event.key == pygame.K_PAGEUP:
                self.current_z += 1
                self._show_toast(f"Этаж: {self.current_z}")
            elif event.key == pygame.K_PAGEDOWN:
                self.current_z = max(0, self.current_z - 1)
                self._show_toast(f"Этаж: {self.current_z}")
            
            elif event.key == pygame.K_s and pygame.key.get_mods() & pygame.KMOD_CTRL:
                if self.current_file:
                    if self.cm.is_open:
                        self.cm.save_location(self.current_file)
                    else:
                        self.dm.save(self.current_file)
                    self._rebuild_spatial_registry()
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
                    
            elif event.key == pygame.K_F2:
                # F2 — переименовать выделенный объект
                if self.selected_object and self.tool is None:
                    mx, my = pygame.mouse.get_pos()
                    self._handle_double_click(mx, my)

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
        
        # Хэндлы ресайза на холсте — максимальный приоритет
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if self.tool is None and self.selected_object and self.selected_object[0] == "object":
                for handle in self._get_resize_handles(self.selected_object[1]):
                    if handle["rect"].collidepoint(mx, my):
                        obj = next((o for o in self.dm.locations[self.current_file]["objects"] if o.get("id") == self.selected_object[1]), None)
                        if obj:
                            self._resizing = {
                                "obj_id": self.selected_object[1],
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
            if self.tool is None and self.selected_object and not self._resizing and not self.property_panel.rect.collidepoint(mx, my):
                if self._is_on_selected(mx, my) and self.selected_object is not None:
                    etype, eid = self.selected_object
                    orig = self._get_drag_orig(etype, eid)
                    if orig:
                        self._dragging_entity = {"start_mx": mx, "start_my": my, "orig": orig}
                    return

        # Кнопки поворота/зеркала на холсте — приоритет над панелью свойств
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if self.tool is None and self.selected_object and self.selected_object[0] == "object" and not self.property_panel.rect.collidepoint(mx, my):
                for btn in self._get_rotation_buttons(self.selected_object[1]):
                    if btn["rect"].collidepoint(mx, my):
                        obj = next((o for o in self.dm.locations[self.current_file]["objects"] if o.get("id") == self.selected_object[1]), None)
                        if obj:
                            if btn.get("action") == "mirror":
                                self.undo.push(MirrorObjectCommand(
                                    self.dm, self.current_file, self.selected_object[1],
                                    obj.get("mirrored", False)
                                ))
                            else:
                                try:
                                    old_rot = float(obj.get("rotation") or 0)
                                except (ValueError, TypeError):
                                    old_rot = 0.0
                                self.undo.push(RotateObjectCommand(
                                    self.dm, self.current_file, self.selected_object[1],
                                    old_rot, btn["delta"]
                                ))
                        return

        # Панель свойств
        action = self.property_panel.handle_event(event)
        if action:
            self._handle_property_action(action)
            return
        # Поглощаем клики внутри панели — чтобы не деселектить объекты
        if event.type == pygame.MOUSEBUTTONDOWN and self.property_panel.rect.collidepoint(event.pos):
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
            if event.button == 1:
                mods = pygame.key.get_mods()
                # Shift+ЛКМ — перетаскивание локации (смещение origin)
                if mods & pygame.KMOD_SHIFT:
                    for fname, data in self.dm.locations.items():
                        rect = self._get_location_screen_rect(fname)
                        if rect and rect.collidepoint(mx, my):
                            self._dragging_location = fname
                            self._drag_offset = (
                                mx - rect.x,
                                my - rect.y
                            )
                            return
                else:
                    # ЛКМ — выбор локации и переход в режим редактирования
                    for fname, data in self.dm.locations.items():
                        rect = self._get_location_screen_rect(fname)
                        if rect and rect.collidepoint(mx, my):
                            self.current_file = fname
                            self._toggle_mode()
                            return
                        
            elif event.button == 2:
                # Колёсико — перемещение камеры
                self.dragging_camera = True
                
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 2:
                self.dragging_camera = False
            if event.button == 1 and hasattr(self, '_dragging_location') and self._dragging_location:
                self._dragging_location = None
                
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging_camera:
                self.camera_x += event.rel[0]
                self.camera_y += event.rel[1]
            elif hasattr(self, '_dragging_location') and self._dragging_location:
                # Перетаскивание локации — обновляем origin
                fname = self._dragging_location
                data = self.dm.locations.get(fname)
                if data:
                    new_sx = mx - self._drag_offset[0]
                    new_sy = my - self._drag_offset[1]
                    # Конвертируем экранные координаты обратно в мировые
                    data["origin"]["x"] = (new_sx - self.camera_x) / (SCALE * self.zoom)
                    data["origin"]["y"] = (new_sy - self.camera_y) / (SCALE * self.zoom)


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
                # Проверка двойного клика (< 400мс, < 8 пикселей)
                now = pygame.time.get_ticks()
                dx = abs(mx - self._last_click_pos[0])
                dy = abs(my - self._last_click_pos[1])
                if now - self._last_click_time < 400 and dx < 8 and dy < 8:
                    self._handle_double_click(mx, my)
                    self._last_click_time = 0
                else:
                    self._handle_left_click(mx, my, world_x, world_y, grid_x, grid_y)
                self._last_click_time = now
                self._last_click_pos = (mx, my)
                
            elif event.button == 2:  # Колёсико — двигать камеру
                self.dragging_camera = True
            elif event.button == 3:  # ПКМ
                if self.tool is not None:
                    # В режиме создания — выйти в покой, выделение остаётся
                    self._set_tool(None)
                else:
                    # В режиме покоя — снять выделение
                    self.selected_object = None
                
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                if self._resizing:
                    obj = next((o for o in self.dm.locations[self.current_file]["objects"] if o.get("id") == self._resizing["obj_id"]), None)
                    if obj:
                        new_w = round(obj["size"]["w"], 2)
                        new_h = round(obj["size"]["h"], 2)
                        old_w = round(self._resizing["start_w"], 2)
                        old_h = round(self._resizing["start_h"], 2)
                        if abs(new_w - old_w) > 0.01 or abs(new_h - old_h) > 0.01:
                            self.undo.push(ResizeObjectCommand(
                                self.dm, self.current_file, self._resizing["obj_id"],
                                old_w, old_h, new_w, new_h
                            ))
                    self._resizing = None
                elif self._dragging_entity and self.selected_object is not None:
                    mx_now, my_now = event.pos
                    total_dx = mx_now - self._dragging_entity["start_mx"]
                    total_dy = my_now - self._dragging_entity["start_my"]
                    scale = 1.0 / (SCALE * self.zoom)
                    dx_world = round(total_dx * scale, 2)
                    dy_world = round(total_dy * scale, 2)
                    if abs(dx_world) > 0.01 or abs(dy_world) > 0.01:
                        etype, eid = self.selected_object
                        drag_wall = etype == "object" and bool(self._dragging_entity["orig"].get("wall_id"))
                        cmd = MoveEntityCommand(
                            self.dm, self.current_file, etype, eid,
                            dx_world, dy_world, drag_wall
                        )
                        cmd._skip_do = True
                        self.undo.push(cmd)
                    self._dragging_entity = None
                else:
                    self._handle_left_release(mx, my, world_x, world_y, grid_x, grid_y)
            elif event.button == 2:  # Колёсико
                self.dragging_camera = False
                
        elif event.type == pygame.MOUSEMOTION:
            if self._dragging_entity and self.selected_object is not None:
                mx_now, my_now = event.pos
                total_dx = mx_now - self._dragging_entity["start_mx"]
                total_dy = my_now - self._dragging_entity["start_my"]
                scale = 1.0 / (SCALE * self.zoom)
                dx_world = total_dx * scale
                dy_world = total_dy * scale
                if self.selected_object is not None:
                    etype, eid = self.selected_object
                    self._apply_drag(etype, eid, self._dragging_entity["orig"], dx_world, dy_world)
            elif self._resizing:
                obj = next((o for o in self.dm.locations[self.current_file]["objects"] if o.get("id") == self._resizing["obj_id"]), None)
                if obj:
                    mx_now, my_now = event.pos
                    total_dx = mx_now - self._resizing["start_mx"]
                    total_dy = my_now - self._resizing["start_my"]
                    scale = 1.0 / (SCALE * self.zoom)
                    handle = self._resizing["handle"]
                    
                    if handle["axis"] == "w":
                        # Только ширина (для объектов в стенах)
                        dw = total_dx * scale * handle["dir"]
                        obj["size"]["w"] = max(0.3, self._resizing["start_w"] + dw)
                    elif handle["axis"] == "h":
                        # Только высота (для вертикальных объектов в стенах)
                        dh = total_dy * scale * handle["dir"]
                        obj["size"]["h"] = max(0.3, self._resizing["start_h"] + dh)
                    else:
                        # Свободный ресайз по обоим осям
                        dw = total_dx * scale * handle["dir_x"]
                        dh = total_dy * scale * handle["dir_y"]
                        obj["size"]["w"] = max(0.3, self._resizing["start_w"] + dw)
                        obj["size"]["h"] = max(0.3, self._resizing["start_h"] + dh)
            elif self.dragging_camera:
                self.camera_x += event.rel[0]
                self.camera_y += event.rel[1]
    
    def _handle_double_click(self, mx: int, my: int) -> None:
        """Обрабатывает двойной клик — переименование сущности"""
        if not self.current_file or not self.selected_object:
            return
        
        entity_type, entity_id = self.selected_object
        old_name = self.dm.get_entity_name(self.current_file, entity_type, entity_id)
        
        fields = [{"key": "name", "label": "Новое имя", "value": old_name}]
        
        def on_confirm(inputs: Dict[str, str]) -> None:
            new_name = inputs.get("name", "").strip()
            if new_name and new_name != old_name:
                self.undo.push(RenameCommand(
                    self.dm, self.current_file, entity_type, entity_id,
                    old_name, new_name))
                self._show_toast(f"Переименовано: {new_name}")
        
        self.dialog = ModalDialog(self.screen, "Переименовать", fields, on_confirm)
    
    def _handle_left_click(self, mx: int, my: int, wx: float, wy: float, gx: float, gy: float):
        """Обрабатывает клик ЛКМ в режиме редактирования"""
        if not self.current_file:
            return
        
        loc = self.dm.locations[self.current_file]
        
        # Режим покоя (tool=None) — клик выделяет объекты
        if self.tool is None:
            self._try_select_existing(mx, my)
            return
        
        # Ниже — активные инструменты создания
        if self.tool == TOOL_WALL:
            if self.wall_start is None:
                # Первый клик — начало стены
                self.wall_drawing = True
                self.wall_start = (gx, gy)
            else:
                # Второй клик — завершение стены
                if abs(gx - self.wall_start[0]) > 0.1 or abs(gy - self.wall_start[1]) > 0.1:
                    wall_id = self.undo.push(AddWallCommand(self.dm, self.current_file,
                                   self.wall_start[0], self.wall_start[1],
                                   gx, gy))
                    self._show_toast("Стена создана")
                    self._try_auto_room(wall_id)
                self.wall_drawing = False
                self.wall_start = None
            
        elif self.tool == TOOL_ROOM:
            # Начинаем создание комнаты
            self.room_drawing = True
            self.room_start = (gx, gy)
            
        elif self.tool == TOOL_OBJECT:
            # Для уличных локаций разрешаем объекты вне комнат
            loc_data = self.dm.locations.get(self.current_file, {})
            is_outdoor = loc_data.get("is_outdoor", False)
            if not is_outdoor and not self._is_point_in_any_room(wx, wy):
                self._show_toast("Объекты можно размещать только внутри комнат")
                return
            # Создаём объект
            preset = OBJECT_PRESETS.get(self.selected_object_type, {})
            ds = preset.get("default_size", {"w": 1.0, "h": 1.0})
            obj_w, obj_h = ds["w"], ds["h"]
            # Проверяем требует ли объект стену
            wall_id = ""
            if preset.get("requires_wall", False):
                wall_id = self._find_wall_near(gx, gy, threshold=1.0) or ""
                if not wall_id:
                    self._show_toast("Этот объект должен быть на стене — кликните ближе к стене")
                    return
                # Выравниваем объект по оси стены
                wall = next((w for w in self.dm.locations[self.current_file]["walls"] if w["id"] == wall_id), None)
                if wall:
                    dx = abs(wall["x2"] - wall["x1"])
                    dy = abs(wall["y2"] - wall["y1"])
                    if dy > dx:  # стена более вертикальная — меняем w/h местами
                        obj_w, obj_h = obj_h, obj_w
            idx = self.undo.push(AddObjectCommand(
                self.dm, self.current_file, self.selected_object_type,
                gx, gy, obj_w, obj_h, wall_id
            ))
            self.selected_object = ("object", str(idx))
            self._show_toast(f"Объект создан: {self.selected_object_type}")
            
        elif self.tool == TOOL_PASSAGE:
            # Создаём проход — ищем стену рядом с кликом
            wall_id = self._find_wall_near(gx, gy, threshold=1.0)
            if wall_id:
                pass_id = self.undo.push(AddPassageCommand(
                    self.dm, self.current_file, wall_id, "door",
                    {"x": gx, "y": gy}, self.current_z))
                self.selected_object = ("passage", pass_id)
                self._show_toast(f"Проход создан в стене {wall_id}")
            else:
                self._show_toast("Нет стены рядом — кликните ближе к стене")
            
        elif self.tool == TOOL_LABEL:
            # Для уличных локаций разрешаем надписи вне комнат
            loc_data = self.dm.locations.get(self.current_file, {})
            is_outdoor = loc_data.get("is_outdoor", False)
            if not is_outdoor and not self._is_point_in_any_room(wx, wy):
                self._show_toast("Надписи можно размещать только внутри комнат")
                return
            # Создаём надпись — сначала спрашиваем текст
            self._pending_label_pos = (gx, gy)
            fields = [{"key": "text", "label": "Текст надписи", "value": "Надпись"}]
            def on_confirm(inputs: Dict[str, str]) -> None:
                text = inputs.get("text", "").strip()
                if text and self._pending_label_pos:
                    lid = self.undo.push(AddLabelCommand(
                        self.dm, self.current_file,
                        self._pending_label_pos[0], self._pending_label_pos[1], text))
                    self.selected_object = ("label", lid)
                    self._show_toast(f"Надпись создана")
            self.dialog = ModalDialog(self.screen, "Новая надпись", fields, on_confirm)
            
        elif self.tool == TOOL_NPC:
            # Для уличных локаций разрешаем NPC вне комнат
            loc_data = self.dm.locations.get(self.current_file, {})
            is_outdoor = loc_data.get("is_outdoor", False)
            if not is_outdoor and not self._is_point_in_any_room(wx, wy):
                self._show_toast("NPC можно размещать только внутри комнат")
                return
            if not self.selected_npc_id:
                self._show_toast("Нет доступных NPC в config/npc/individuals")
                return
            room_id = self.dm.find_room_at(self.current_file, wx, wy)
            npc_ref = self.undo.push(AddNpcCommand(
                self.dm, self.current_file, self.selected_npc_id,
                gx, gy, room_id
            ))
            self.selected_object = ("npc", self.selected_npc_id)
            npc_name = next((n["name"] for n in self._npc_list if n["id"] == self.selected_npc_id), self.selected_npc_id)
            self._show_toast(f"NPC размещён: {npc_name}")
            
        elif self.tool == TOOL_SPAWN:
            # Устанавливаем точку спавна игрока
            self.dm.set_player_spawn(self.current_file, gx, gy, self.current_z)
            self.selected_object = ("spawn", "player_spawn")
            self._show_toast(f"Точка спавна установлена: ({gx}, {gy})")
            
        elif self.tool == TOOL_DELETE:
            # Удаляем объект под курсором
            self._delete_at(mx, my)
    
    def _handle_left_release(self, mx: int, my: int, wx: float, wy: float, gx: float, gy: float):
        """Обрабатывает отпускание ЛКМ"""
        if not self.current_file:
            return
        
        if self.tool == TOOL_ROOM and self.room_drawing and self.room_start:
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
    
    def _try_auto_room(self, last_wall_id: str) -> None:
        """Проверяет, замкнулся ли контур после создания стены.
        Если да — создаёт комнату автоматически."""
        if not self.current_file:
            return
        loc = self.dm.locations[self.current_file]
        
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
            all_room_keys.add((round(r["x"], 1), round(r["y"], 1),
                               round(r["width"], 1), round(r["height"], 1)))
        
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
            self.dm, self.current_file, room_name, bx, by, bw, bh,
            polygon=path_points, area_sqm=round(area, 1))
        
        self.undo.push(room_cmd)
        self._show_toast(f"Автокомната: {room_name} ({area:.1f} м²)")
    
    def _find_wall_near(self, wx: float, wy: float, threshold: float = 1.0) -> Optional[str]:
        """Ищет стену, ближайшую к мировой точке (wx, wy). Возвращает wall_id или None."""
        if not self.current_file:
            return None
        loc = self.dm.locations[self.current_file]
        best_id: Optional[str] = None
        best_dist = threshold
        for wall in loc.get("walls", []):
            # Расстояние от точки до отрезка
            dist = self._point_to_segment_dist(wx, wy,
                                                wall["x1"], wall["y1"],
                                                wall["x2"], wall["y2"])
            if dist < best_dist:
                best_dist = dist
                best_id = wall["id"]
        return best_id
    
    def _is_point_in_any_room(self, wx: float, wy: float) -> bool:
        """Проверяет, попадает ли мировая точка внутрь хотя бы одной комнаты"""
        if not self.current_file:
            return False
        loc = self.dm.locations[self.current_file]
        for room in loc.get("rooms", []):
            poly = room.get("polygon")
            if poly and len(poly) >= 3:
                if DataManager._point_in_polygon(wx, wy, [(p[0], p[1]) for p in poly]):
                    return True
        return False

    @staticmethod
    def _point_to_segment_dist(px: float, py: float,
                                x1: float, y1: float,
                                x2: float, y2: float) -> float:
        """Расстояние от точки до отрезка"""
        dx, dy = x2 - x1, y2 - y1
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            return math.hypot(px - x1, py - y1)
        t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / length_sq))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy
        return math.hypot(px - proj_x, py - proj_y)
    
    def _try_select_existing(self, mx: int, my: int) -> bool:
        """Пробует выбрать существующий объект под курсором. Возвращает True если нашёл."""
        if not self.current_file:
            return False
        loc = self.dm.locations[self.current_file]
        
        # Объекты
        if self.show_objects:
            for obj in loc.get("objects", []):
                sx, sy = self.world_to_screen(obj["position"]["x"], obj["position"]["y"])
                w = obj["size"]["w"] * SCALE * self.zoom
                h = obj["size"]["h"] * SCALE * self.zoom
                hit_rect = pygame.Rect(sx - w/2, sy - h/2, w, h)
                if hit_rect.collidepoint(mx, my):
                    self.selected_object = ("object", obj.get("id", ""))
                    return True
        
        # NPC (проверяем перед стенами — приоритет)
        for npc in loc.get("npcs", []):
            sx, sy = self.world_to_screen(npc["position"]["x"], npc["position"]["y"])
            hit_r = int(SCALE * self.zoom * 0.4)
            if pygame.Rect(sx - hit_r, sy - hit_r, hit_r * 2, hit_r * 2).collidepoint(mx, my):
                self.selected_object = ("npc", npc["ref_id"])
                return True
        
        # Точка спавна
        spawn = loc.get("player_spawn")
        if spawn:
            sx, sy = self.world_to_screen(spawn["x"], spawn["y"])
            hit_r = int(SCALE * self.zoom * 0.5)
            if pygame.Rect(sx - hit_r, sy - hit_r, hit_r * 2, hit_r * 2).collidepoint(mx, my):
                self.selected_object = ("spawn", "player_spawn")
                return True
        
        # Стены
        if self.show_walls:
            for wall in loc.get("walls", []):
                sx1, sy1 = self.world_to_screen(wall["x1"], wall["y1"])
                sx2, sy2 = self.world_to_screen(wall["x2"], wall["y2"])
                if self._point_near_line(mx, my, sx1, sy1, sx2, sy2, 10):
                    self.selected_object = ("wall", wall["id"])
                    return True
        
        # Комнаты — собираем все перекрытые, переключаемся циклом
        if self.show_rooms:
            wx, wy = self.screen_to_world(mx, my)
            matched_rooms: List[str] = []
            for room in loc.get("rooms", []):
                poly = room.get("polygon")
                if poly and len(poly) >= 3:
                    if DataManager._point_in_polygon(wx, wy, [(p[0], p[1]) for p in poly]):
                        matched_rooms.append(room["id"])
                else:
                    rx, ry = self.world_to_screen(room["x"], room["y"])
                    rw = room["width"] * SCALE * self.zoom
                    rh = room["height"] * SCALE * self.zoom
                    if pygame.Rect(rx, ry, rw, rh).collidepoint(mx, my):
                        matched_rooms.append(room["id"])
            
            if matched_rooms:
                # Проверяем что клик в той же области (±8 пикселей)
                dx = abs(mx - self._last_click_pos[0])
                dy = abs(my - self._last_click_pos[1])
                if matched_rooms == self._overlap_room_ids and dx < 8 and dy < 8:
                    # Переключаемся на следующую
                    self._overlap_index = (self._overlap_index + 1) % len(matched_rooms)
                else:
                    # Новая область — начинаем с первой
                    self._overlap_room_ids = matched_rooms
                    self._overlap_index = 0
                
                self.selected_object = ("room", matched_rooms[self._overlap_index])
                return True
        
        return False
    
    def _delete_at(self, mx: int, my: int):
        """Удаляет объект под курсором"""
        if not self.current_file:
            return
        
        loc = self.dm.locations[self.current_file]
        
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
        
        # NPC
        for npc in loc.get("npcs", []):
            sx, sy = self.world_to_screen(npc["position"]["x"], npc["position"]["y"])
            hit_r = int(SCALE * self.zoom * 0.4)
            if pygame.Rect(sx - hit_r, sy - hit_r, hit_r * 2, hit_r * 2).collidepoint(mx, my):
                self.undo.push(RemoveNpcCommand(self.dm, self.current_file, deepcopy(npc)))
                npc_name = next((n["name"] for n in self._npc_list if n["id"] == npc["ref_id"]), npc["ref_id"])
                self._show_toast(f"NPC удалён: {npc_name}")
                self.selected_object = None
                return
        
        # Надписи
        for lbl in loc.get("labels", []):
            sx, sy = self.world_to_screen(lbl["x"], lbl["y"])
            text_surf = self.font_small.render(lbl.get("text", ""), True, COLORS["text"])
            tw, th = text_surf.get_size()
            if pygame.Rect(sx, sy, tw, th).collidepoint(mx, my):
                self.undo.push(RemoveLabelCommand(self.dm, self.current_file, deepcopy(lbl)))
                self._show_toast("Надпись удалена")
                self.selected_object = None
                return
        
        # Точка спавна игрока
        spawn = loc.get("player_spawn")
        if spawn:
            sx, sy = self.world_to_screen(spawn["x"], spawn["y"])
            if abs(sx - mx) < 15 and abs(sy - my) < 15:
                del loc["player_spawn"]
                self._show_toast("Точка спавна удалена")
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
        
        t = max(0, min(1, ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / (line_len ** 2)))
        proj_x = x1 + t * (x2 - x1)
        proj_y = y1 + t * (y2 - y1)
        
        return math.hypot(px - proj_x, py - proj_y) < threshold
    
    def _handle_property_action(self, action: str):
        """Обрабатывает действия из панели свойств"""
        if not self.current_file:
            return
        
        # Действия над локацией (когда ничего не выделено)
        if not self.selected_object:
            loc = self.dm.locations[self.current_file]
            if action == "set_location_id":
                current_val = loc.get("location_id", "")
                fields = [{"key": "location_id", "label": "location_id", "value": current_val}]
                def on_confirm(inputs: Dict[str, str]) -> None:
                    new_val = inputs.get("location_id", "").strip()
                    loc["location_id"] = new_val
                    self._show_toast(f"location_id = {new_val or '(пусто)'}")
                self.dialog = ModalDialog(self.screen, "Задать location_id", fields, on_confirm)
            return
        
        obj_type, obj_key = self.selected_object
        loc = self.dm.locations[self.current_file]
        
        if action == "create_perimeter_walls" and obj_type == "room":
            room = next((r for r in loc["rooms"] if r["id"] == obj_key), None)
            if room:
                existing = self._find_room_perimeter_walls(room)
                
                if existing:
                    # Стены есть → УДАЛЯЕМ их
                    for wall in existing:
                        self.dm.remove_wall(self.current_file, wall["id"])
                    self._show_toast(f"Удалено стен: {len(existing)} для {room['name']}")
                else:
                    # Стен нет → СОЗДАЁМ их
                    thickness = 0.2
                    poly = room.get("polygon")
                    created = 0
                    
                    if poly and len(poly) >= 3:
                        for i in range(len(poly)):
                            x1, y1 = poly[i]
                            x2, y2 = poly[(i + 1) % len(poly)]
                            self.dm.add_wall(self.current_file, x1, y1, x2, y2, "wall", thickness)
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
                            self.dm.add_wall(self.current_file, wx1, wy1, wx2, wy2, "wall", thickness)
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
                    self.undo.push(RenameCommand(
                        self.dm, self.current_file, obj_type, obj_key,
                        old_name, new_name))
                    self._show_toast(f"Переименовано: {new_name}")
            self.dialog = ModalDialog(self.screen, "Переименовать", fields, on_confirm)
            return
        
        if action == "toggle_show_name" and obj_type == "object":
            obj = next((o for o in loc["objects"] if o.get("id") == obj_key), None)
            if obj:
                obj["show_name"] = not obj.get("show_name", False)
            return
        
        if action == "rename_label":
            lbl = next((l for l in loc["labels"] if l["id"] == obj_key), None)
            if lbl:
                old_text = lbl.get("text", "")
                fields = [{"key": "text", "label": "Текст", "value": old_text}]
                def on_confirm_lbl(inputs: Dict[str, str]) -> None:
                    new_text = inputs.get("text", "").strip()
                    if new_text and new_text != old_text:
                        self.dm.rename_label(self.current_file, obj_key, new_text)
                        self._show_toast("Текст изменён")
                self.dialog = ModalDialog(self.screen, "Изменить текст", fields, on_confirm_lbl)
            return
        
        if action.startswith("toggle_"):
            flag = action[7:]  # Убираем "toggle_"
            if obj_type == "object":
                obj = next((o for o in loc["objects"] if o.get("id") == obj_key), None)
            if not obj:
                return
            self.undo.push(TogglePassabilityCommand(
                self.dm, self.current_file, obj_key, flag, obj["passability"][flag]
            ))
    
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
        self._update_property_panel()
    
    def _update_property_panel(self):
        """Обновляет содержимое панели свойств"""
        if not self.current_file:
            self.property_panel.set_content("СВОЙСТВА", [])
            return
        
        loc = self.dm.locations[self.current_file]
        
        # Если ничего не выделено — показываем свойства локации
        if not self.selected_object:
            items = [
                {"type": "label", "text": f"Локация: {loc.get('label', self.current_file)}", "important": True},
                {"type": "value", "label": "Файл", "value": self.current_file},
                {"type": "value", "label": "Размер", "value": f"{loc['size']['w']}x{loc['size']['h']}м"},
                {"type": "value", "label": "location_id", "value": loc.get("location_id", "—")},
                {"type": "toggle", "label": "✏️ Задать location_id", "action": "set_location_id"},
                {"type": "section", "text": "Содержимое:"},
                {"type": "value", "label": "Комнаты", "value": str(len(loc.get("rooms", [])))},
                {"type": "value", "label": "Стены", "value": str(len(loc.get("walls", [])))},
                {"type": "value", "label": "Объекты", "value": str(len(loc.get("objects", [])))},
                {"type": "value", "label": "NPC", "value": str(len(loc.get("npcs", [])))},
                {"type": "value", "label": "Узлы", "value": str(len(loc.get("nodes", {})))},
            ]
            self.property_panel.set_content("СВОЙСТВА", items)
            return
        
        obj_type, obj_key = self.selected_object
        items = []
        
        obj_type, obj_key = self.selected_object
        loc = self.dm.locations[self.current_file]
        items = []
        
        if obj_type == "object":
            obj = next((o for o in loc["objects"] if o.get("id") == obj_key), None)
            if not obj:
                self.property_panel.set_content("СВОЙСТВА", [])
                return
            items = [
                {"type": "label", "text": f"Объект: {obj['type']}", "important": True},
                {"type": "value", "label": "Имя", "value": obj.get("name", "")},
                {"type": "toggle", "label": "✏️ Переименовать", "action": "rename"},
                {"type": "toggle", "label": "Показать имя", "value": obj.get("show_name", False), "action": "toggle_show_name"},
                {"type": "value", "label": "X", "value": f"{obj['position']['x']:.1f}"},
                {"type": "value", "label": "Y", "value": f"{obj['position']['y']:.1f}"},
                {"type": "section", "text": "Проходимость:"},
                {"type": "toggle", "label": "Идти", "value": obj["passability"]["walk"], "action": "toggle_walk"},
                {"type": "toggle", "label": "Прыгать", "value": obj["passability"]["jump_over"], "action": "toggle_jump_over"},
                {"type": "toggle", "label": "Ползти", "value": obj["passability"]["crawl_under"], "action": "toggle_crawl_under"},
                {"type": "toggle", "label": "Лезть", "value": obj["passability"]["climb_on"], "action": "toggle_climb_on"},
            ]
            # Свойства объекта (если есть)
            props = obj.get("properties", {})
            if props:
                items.append({"type": "section", "text": "Свойства:"})
                prop_labels = {
                    "open": "Открыто", "locked": "Замок", "durability": "Прочность",
                    "opacity": "Непрозрачность", "destructible": "Разрушаемое",
                    "sound_attenuation": "Заглушение звука"
                }
                for key, value in props.items():
                    label = prop_labels.get(key, key)
                    if isinstance(value, bool):
                        items.append({"type": "value", "label": label, "value": "Да" if value else "Нет"})
                    elif isinstance(value, (int, float)):
                        items.append({"type": "value", "label": label, "value": f"{value}"})
                    else:
                        items.append({"type": "value", "label": label, "value": str(value)})
        
        elif obj_type == "portal":
            p = next((p for p in loc["portals"] if p["id"] == obj_key), None)
            if p:
                items = [
                    {"type": "label", "text": f"Портал: {p['label']}", "important": True},
                    {"type": "toggle", "label": "✏️ Переименовать", "action": "rename"},
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
                    {"type": "toggle", "label": "✏️ Переименовать", "action": "rename"},
                    {"type": "toggle", "label": "🔨 Стены по периметру", "value": len(self._find_room_perimeter_walls(room)) > 0, "action": "create_perimeter_walls"},
                    {"type": "value", "label": "X", "value": f"{room['x']:.1f}"},
                    {"type": "value", "label": "Y", "value": f"{room['y']:.1f}"},
                    {"type": "value", "label": "Ширина", "value": f"{room['width']:.1f}"},
                    {"type": "value", "label": "Высота", "value": f"{room['height']:.1f}"},
                    {"type": "value", "label": "Площадь", "value": f"{room.get('area_sqm', room['width'] * room['height']):.1f} м²"},
                ]
        
        elif obj_type == "label":
            lbl = next((l for l in loc["labels"] if l["id"] == obj_key), None)
            if lbl:
                items = [
                    {"type": "label", "text": "Надпись", "important": True},
                    {"type": "toggle", "label": "✏️ Изменить текст", "action": "rename_label"},
                    {"type": "value", "label": "X", "value": f"{lbl['x']:.1f}"},
                    {"type": "value", "label": "Y", "value": f"{lbl['y']:.1f}"},
                ]
        
        elif obj_type == "npc":
            npc = next((n for n in loc.get("npcs", []) if n.get("ref_id") == obj_key), None)
            if npc:
                npc_name = next((nn["name"] for nn in self._npc_list if nn["id"] == npc["ref_id"]), npc["ref_id"])
                items = [
                    {"type": "label", "text": f"NPC: {npc_name}", "important": True},
                    {"type": "value", "label": "ID", "value": npc["ref_id"]},
                    {"type": "value", "label": "X", "value": f"{npc['position']['x']:.1f}"},
                    {"type": "value", "label": "Y", "value": f"{npc['position']['y']:.1f}"},
                    {"type": "value", "label": "Комната", "value": npc.get("room_id", "—")},
                ]
        
        elif obj_type == "spawn":
            spawn = loc.get("player_spawn")
            if spawn:
                items = [
                    {"type": "label", "text": "🏁 Точка спавна игрока", "important": True},
                    {"type": "value", "label": "X", "value": f"{spawn['x']:.1f}"},
                    {"type": "value", "label": "Y", "value": f"{spawn['y']:.1f}"},
                    {"type": "value", "label": "Z", "value": f"{spawn.get('z', 0)}"},
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
            
            # Название локации
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
        
        # Проходы (внутренние двери в стенах)
        self._draw_passages()
        self._draw_nodes()  # BUG-P1-12: Включаем отрисовку навигационных узлов
        
        # Надписи (поверх всего, чтобы не перекрывались)
        self._draw_labels()
        
        # Объекты
        if self.show_objects:
            self._draw_objects()
        
        # NPC
        self._draw_npcs()
        
        # Точка спавна игрока
        self._draw_spawn()
        
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
        origin = loc.get("origin", {"x": 0, "y": 0})
        x, y = self.world_to_screen(origin["x"], origin["y"])
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
    
    def _find_label_position(self, room: Dict, objects_in_room: List[Dict]) -> Tuple[int, int]:
        """Находит лучшую позицию для надписи комнаты — максимально удалённую от объектов."""
        poly = room.get("polygon")
        if not poly:
            rx, ry = self.world_to_screen(room["x"], room["y"])
            return rx + 4, ry + 4
        
        # Экранные координаты полигона
        screen_poly = [self.world_to_screen(p[0], p[1]) for p in poly]
        # Bounding box
        xs = [p[0] for p in screen_poly]
        ys = [p[1] for p in screen_poly]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        # Экранные позиции объектов
        obj_positions = [(self.world_to_screen(o["position"]["x"], o["position"]["y"]))
                         for o in objects_in_room]
        
        # Сетка кандидатов — с запасом на размер текста
        text_w, text_h = 150, 16  # примерный максимальный размер надписи
        step = 16
        best_pos = (min_x + 4, min_y + 4)
        best_dist = -1
        
        cx = min_x + text_w // 2 + 4
        while cx < max_x - text_w // 2 - 4:
            cy = min_y + text_h // 2 + 4
            while cy < max_y - text_h // 2 - 4:
                # Проверяем что ЛЕВЫЙ ВЕРХНИЙ угол текста и ПРАВЫЙ НИЖНИЙ — внутри полигона
                if (DataManager._point_in_polygon(cx - text_w // 2, cy - text_h // 2, screen_poly) and
                    DataManager._point_in_polygon(cx + text_w // 2, cy - text_h // 2, screen_poly) and
                    DataManager._point_in_polygon(cx - text_w // 2, cy + text_h // 2, screen_poly) and
                    DataManager._point_in_polygon(cx + text_w // 2, cy + text_h // 2, screen_poly)):
                    # Минимальное расстояние до объектов
                    min_d = float('inf')
                    for ox, oy in obj_positions:
                        d = math.hypot(cx - ox, cy - oy)
                        if d < min_d:
                            min_d = d
                    if not obj_positions:
                        min_d = 999
                    if min_d > best_dist:
                        best_dist = min_d
                        best_pos = (int(cx) - text_w // 2, int(cy) - text_h // 2)
                cy += step
            cx += step
        
        return best_pos
    
    def _draw_rooms(self):
        """Отрисовывает комнаты — полигональные или прямоугольные"""
        if not self.current_file:
            return
        
        loc = self.dm.locations[self.current_file]
        for room in loc.get("rooms", []):
            poly = room.get("polygon")
            
            if poly and len(poly) >= 3:
                # Полигональная комната
                screen_pts = [self.world_to_screen(p[0], p[1]) for p in poly]
                pygame.draw.polygon(self.screen, (60, 60, 70), screen_pts)
                pygame.draw.polygon(self.screen, (100, 100, 120), screen_pts, 2)
            else:
                # Прямоугольная (совместимость)
                rx, ry = self.world_to_screen(room["x"], room["y"])
                rw = room["width"] * SCALE * self.zoom
                rh = room["height"] * SCALE * self.zoom
                pygame.draw.rect(self.screen, (60, 60, 70), (rx, ry, rw, rh))
                pygame.draw.rect(self.screen, (100, 100, 120), (rx, ry, rw, rh), 2)
            
            # Надпись — умная позиция, уходящая от объектов
            objects_in = [o for o in loc.get("objects", [])
                          if self.dm.find_room_at(self.current_file,
                                                    o["position"]["x"],
                                                    o["position"]["y"]) == room["id"]]
            lx, ly = self._find_label_position(room, objects_in)
            area = room.get("area_sqm", round(room["width"] * room["height"], 1))
            label_str = f"{room['name']} — {area:.1f} м²"
            label = self.font_small.render(label_str, True, COLORS["text_dim"])
            self.screen.blit(label, (lx, ly))
    
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
    
    def _draw_passages(self):
        """Отрисовывает проходы (внутренние двери/окна в стенах)"""
        if not self.current_file:
            return
        loc = self.dm.locations[self.current_file]
        for passage in loc.get("passages", []):
            if passage.get("z", 0) != self.current_z:
                continue
            sx, sy = self.world_to_screen(passage["position"]["x"], passage["position"]["y"])
            # Цвет по типу: дверь — жёлтый, окно — голубой, пролом — серый
            ptype = passage.get("type", "door")
            color = {"door": (255, 215, 0), "window": (135, 206, 235), "gap": (170, 170, 170)}.get(ptype, (255, 215, 0))
            pygame.draw.circle(self.screen, color, (sx, sy), 6)
            pygame.draw.circle(self.screen, COLORS["border"], (sx, sy), 6, 1)
            label = self.font_small.render(passage["id"], True, COLORS["text_dim"])
            self.screen.blit(label, (sx + 10, sy - 6))
    
    def _draw_labels(self):
        """Отрисовывает произвольные надписи"""
        if not self.current_file:
            return
        loc = self.dm.locations[self.current_file]
        for lbl in loc.get("labels", []):
            sx, sy = self.world_to_screen(lbl["x"], lbl["y"])
            text = lbl.get("text", "")
            if not text:
                continue
            color = COLORS["text_highlight"]
            # Если выделена — подсветить
            if self.selected_object == ("label", lbl["id"]):
                color = COLORS["accent_yellow"]
            rendered = self.font_small.render(text, True, color)
            self.screen.blit(rendered, (sx, sy))
    
    def _draw_objects(self):
        """Отрисовывает объекты"""
        if not self.current_file:
            return
        
        loc = self.dm.locations[self.current_file]
        for i, obj in enumerate(loc.get("objects", [])):
            sx, sy = self.world_to_screen(obj["position"]["x"], obj["position"]["y"])
            w = obj["size"]["w"] * SCALE * self.zoom
            h = obj["size"]["h"] * SCALE * self.zoom
            try:
                rotation = float(obj.get("rotation") or 0)
            except (ValueError, TypeError):
                rotation = 0.0
            color = OBJECT_COLORS.get(obj["type"], OBJECT_COLORS["decoration"])
            
            # Попытка получить спрайт из пресета
            preset = OBJECT_PRESETS.get(obj["type"], {})
            sprite_info = preset.get("sprite")
            sprite_surf = None
            if sprite_info:
                sprite_surf = sprite_registry.get(sprite_info[0], sprite_info[1], sprite_info[2])
            
            if sprite_surf:
                # Отрисовка спрайта с масштабированием без рамки
                scaled = pygame.transform.scale(sprite_surf, (int(w), int(h)))
                if rotation % 360 != 0:
                    scaled = pygame.transform.rotate(scaled, -rotation)
                scaled_rect = scaled.get_rect(center=(int(sx), int(sy)))
                self.screen.blit(scaled, scaled_rect)
            else:
                # Fallback на цветной квадрат
                if rotation % 360 != 0:
                    pts = self._rotated_rect_points(sx, sy, w, h, rotation)
                    pygame.draw.polygon(self.screen, color, pts)
                    pygame.draw.polygon(self.screen, COLORS["border"], pts, 1)
                else:
                    rect = pygame.Rect(sx - w/2, sy - h/2, w, h)
                    pygame.draw.rect(self.screen, color, rect, border_radius=2)
                    pygame.draw.rect(self.screen, COLORS["border"], rect, 1, border_radius=2)
            
            # Имя объекта — только если включено показ
            if obj.get("show_name", False):
                label_text = obj.get("name", obj["type"][:4])
                label = self.font_small.render(label_text, True, COLORS["text_highlight"])
                self.screen.blit(label, (sx - label.get_width() // 2, sy - h / 2 - 14))
    
    def _draw_npcs(self):
        """Отрисовывает размещённых NPC (реальных из config)"""
        if not self.current_file:
            return
        
        loc = self.dm.locations[self.current_file]
        for npc in loc.get("npcs", []):
            sx, sy = self.world_to_screen(npc["position"]["x"], npc["position"]["y"])
            
            # Имя NPC из списка загруженных
            npc_name = next((n["name"] for n in self._npc_list if n["id"] == npc["ref_id"]), npc["ref_id"])
            
            # Спрайт из маппинга или дефолтный
            sprite_info = NPC_SPRITE_MAP.get(npc["ref_id"], ("Deadbeat/deadbeat_b", 23, 21))
            size = int(SCALE * self.zoom * 0.8)
            sprite_surf = sprite_registry.get(sprite_info[0], sprite_info[1], sprite_info[2])
            
            is_selected = self.selected_object == ("npc", npc["ref_id"])
            
            if sprite_surf:
                scaled = pygame.transform.scale(sprite_surf, (size, size))
                rect = scaled.get_rect(center=(int(sx), int(sy)))
                self.screen.blit(scaled, rect)
                if is_selected:
                    pygame.draw.rect(self.screen, COLORS["accent_yellow"], rect.inflate(4, 4), 2)
            else:
                color = COLORS["accent_yellow"] if is_selected else (100, 180, 100)
                pygame.draw.circle(self.screen, color, (int(sx), int(sy)), size // 2)
                pygame.draw.circle(self.screen, COLORS["border"], (int(sx), int(sy)), size // 2, 1)
            
            # Подпись с реальным именем NPC
            label = self.font_small.render(npc_name, True, COLORS["text_highlight"])
            self.screen.blit(label, (sx - label.get_width() // 2, sy - size // 2 - 14))
    
    def _draw_spawn(self):
        """Отрисовывает точку спавна игрока"""
        if not self.current_file:
            return
        
        loc = self.dm.locations[self.current_file]
        spawn = loc.get("player_spawn")
        if not spawn:
            return
        
        sx, sy = self.world_to_screen(spawn["x"], spawn["y"])
        is_selected = self.selected_object == ("spawn", "player_spawn")
        
        # Флаг — жёлтый треугольник
        size = int(SCALE * self.zoom * 0.5)
        color = COLORS["accent_yellow"] if is_selected else (255, 200, 0)
        
        points = [
            (sx, sy - size),
            (sx - size * 0.7, sy + size * 0.5),
            (sx + size * 0.7, sy + size * 0.5),
        ]
        pygame.draw.polygon(self.screen, color, points)
        pygame.draw.polygon(self.screen, COLORS["border"], points, 2)
        
        # Подпись
        label = self.font_small.render("СПАВН", True, COLORS["accent_yellow"])
        self.screen.blit(label, (sx - label.get_width() // 2, sy + size * 0.5 + 4))
    
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
            # Площадь в реальном времени
            wx1, wy1 = self.room_start
            wx2, wy2 = self.screen_to_world(mx, my)
            w_m = abs(wx2 - wx1)
            h_m = abs(wy2 - wy1)
            area = w_m * h_m
            if area > 0.5:
                area_text = f"{area:.1f} м² ({w_m:.1f}×{h_m:.1f})"
                area_surf = self.font_small.render(area_text, True, COLORS["accent_yellow"])
                self.screen.blit(area_surf, (rect.centerx - area_surf.get_width() // 2,
                                              rect.centery - area_surf.get_height() // 2))
    
    def _draw_selection(self):
        """Отрисовывает выделение объекта"""
        if not self.current_file or not self.selected_object:
            return
        
        obj_type, obj_key = self.selected_object
        loc = self.dm.locations[self.current_file]
        
        if obj_type == "object":
            obj = next((o for o in loc.get("objects", []) if o.get("id") == obj_key), None)
            if obj:
                sx, sy = self.world_to_screen(obj["position"]["x"], obj["position"]["y"])
                w = obj["size"]["w"] * SCALE * self.zoom
                h = obj["size"]["h"] * SCALE * self.zoom
                try:
                    rotation = float(obj.get("rotation") or 0)
                except (ValueError, TypeError):
                    rotation = 0.0
                # Рамка выделения — только для объектов без спрайта
                preset = OBJECT_PRESETS.get(obj["type"], {})
                if not preset.get("sprite"):
                    if rotation % 360 != 0:
                        pts = self._rotated_rect_points(sx, sy, w + 6, h + 6, rotation)
                        pygame.draw.polygon(self.screen, COLORS["accent_yellow"], pts, 3)
                    else:
                        rect = pygame.Rect(sx - w/2 - 3, sy - h/2 - 3, w + 6, h + 6)
                        pygame.draw.rect(self.screen, COLORS["accent_yellow"], rect, 3, border_radius=3)
                # хэндлы ресайза — только в режиме выбора
                if self.tool is None:
                    for handle in self._get_resize_handles(obj_key):
                        r = handle["rect"]
                        pygame.draw.rect(self.screen, COLORS["bg_panel"], r)
                        pygame.draw.rect(self.screen, COLORS["accent_yellow"], r, 1)
                # кнопки поворота/зеркала — только в режиме выбора
                if self.tool is None:
                    for btn in self._get_rotation_buttons(obj_key):
                        r = btn["rect"]
                        pygame.draw.circle(self.screen, COLORS["bg_panel"], r.center, r.width // 2)
                        pygame.draw.circle(self.screen, COLORS["border"], r.center, r.width // 2, 1)
                        cx, cy = r.center
                        if btn.get("action") == "mirror":
                            # горизонтальная двусторонняя стрелка ↔
                            pygame.draw.line(self.screen, COLORS["text"], (cx - 5, cy), (cx + 5, cy), 2)
                            pygame.draw.polygon(self.screen, COLORS["text"], [(cx + 5, cy), (cx + 2, cy - 3), (cx + 2, cy + 3)])
                            pygame.draw.polygon(self.screen, COLORS["text"], [(cx - 5, cy), (cx - 2, cy - 3), (cx - 2, cy + 3)])
                        else:
                            # треугольник-стрелка поворота
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
                    poly = room.get("polygon")
                    if poly and len(poly) >= 3:
                        screen_pts = [self.world_to_screen(p[0], p[1]) for p in poly]
                        pygame.draw.polygon(self.screen, COLORS["accent_yellow"], screen_pts, 3)
                    else:
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
            camp_info = f" | Кампания: {self.cm.campaign_data.get('name', self.cm.current_campaign_name or '?')}" if self.cm.is_open else " | (без кампании)"
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


    def _find_room_perimeter_walls(self, room: dict) -> list:
        """Находит стены, совпадающие с рёбрами комнаты (прямоугольной или полигональной)"""
        if not self.current_file:
            return []
        loc = self.dm.locations[self.current_file]
        walls = loc.get("walls", [])
        if not walls:
            return []
        
        # Собираем рёбра комнаты
        edges = []
        poly = room.get("polygon")
        if poly and len(poly) >= 3:
            for i in range(len(poly)):
                edges.append((poly[i][0], poly[i][1], poly[(i+1) % len(poly)][0], poly[(i+1) % len(poly)][1]))
        else:
            rx, ry = room["x"], room["y"]
            rw, rh = room["width"], room["height"]
            edges = [
                (rx, ry, rx + rw, ry),
                (rx + rw, ry, rx + rw, ry + rh),
                (rx, ry + rh, rx + rw, ry + rh),
                (rx, ry, rx, ry + rh),
            ]
        
        # Ищем стены, совпадающие с рёбрами (прямо или наоборот)
        matched = []
        for wall in walls:
            for ex1, ey1, ex2, ey2 in edges:
                direct = (abs(wall["x1"] - ex1) < 0.3 and abs(wall["y1"] - ey1) < 0.3 and
                          abs(wall["x2"] - ex2) < 0.3 and abs(wall["y2"] - ey2) < 0.3)
                reverse = (abs(wall["x1"] - ex2) < 0.3 and abs(wall["y1"] - ey2) < 0.3 and
                           abs(wall["x2"] - ex1) < 0.3 and abs(wall["y2"] - ey1) < 0.3)
                if direct or reverse:
                    matched.append(wall)
                    break
        return matched


# Точка входа
if __name__ == "__main__":
    app = EditorCore()
    app.run()

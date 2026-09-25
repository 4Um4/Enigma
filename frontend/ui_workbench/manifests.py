"""
path: /frontend/ui_workbench/manifests.py
Назначение: Декларативные контракты окон Workbench. Окно = данные, не код.
Зависимости: dataclasses, enum, typing
Основные сущности: WindowState, WindowManifest, InputBinding

ЗАКОН ПАКЕТА (неписаное правило, зафиксированное Мастером):
1. UI может становиться умнее, не становясь источником истины.
2. Binding декларативен: manifest.data_source — ИМЯ DTO-канала.
   Окна не импортируют backend. Никогда.
3. Тема определяет КАК выглядит, не ЧТО показывается.
4. Ввод маршрутизируется диспетчером, не if-россыпью в game_screen.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class WindowState(Enum):
    """FSM состояния окна. Переходы — только через WindowRegistry.
    Прецедент: TraversalState / Commitment FSM (единый владелец lifecycle)."""
    HIDDEN = "hidden"                    # не рендерится, не получает ввод
    COLLAPSED_TO_TITLE = "collapsed"     # рендерится только заголовок
    FULL = "full"                        # полное окно

    # Точки роста (заложены, не реализуются в v1):
    # DOCKED, MODAL — schema-versioned поля уже резервируют место.


@dataclass(frozen=True)
class InputBinding:
    """Декларативный контракт взаимодействия. Единый реестр хоткеев
    (совместимость с keybinds.json, S217) — проверка конфликтов в InputDispatcher."""
    hotkey: Optional[int] = None          # pygame.K_* (например, K_j)
    modal: bool = False                   # True: окно захватывает весь ввод
    passthrough: bool = True              # False: блокирует ввод сцене под собой
    click_title_collapse: bool = True     # клик по заголовку сворачивает/разворачивает


@dataclass(frozen=True)
class WindowManifest:
    # free_rect (v3a): пользовательская геометрия (drag в Workbench) переопределяет
    # анкер. None = окно живёт по anchor/offset/size_policy. SnapEngine заполняет.
    # Хранится в persistence, не в манифесте (манифест = заводские дефолты).
    """Декларация окна. Окно без data_source невалидно (Закон Причинности:
    UI-элемент обязан иметь источник событий мира)."""
    window_id: str
    title: str
    layer: int                            # 2|3|4 — когнитивные слои UI Doctrine
    data_source: str                      # имя DTO-канала: "dialog_journal", "player_perception"...
    default_state: WindowState = WindowState.HIDDEN
    collapsible: bool = True
    # AnchoredRect-спецификация (строки — чтобы манифест остался сериализуемым):
    anchor: str = "top_right"             # top_left|top_right|bottom_left|bottom_right|center
    offset: Tuple[int, int] = (0, 0)      # px от якоря (в сторону экрана)
    size_policy: Tuple[float, float] = (0.30, 0.60)  # доля viewport (w, h)
    min_size: Tuple[int, int] = (280, 200)
    max_size: Tuple[int, int] = (720, 1000)
    snap_enabled: bool = True
    z_order: int = 10
    binding: InputBinding = field(default_factory=InputBinding)

    def validate(self) -> None:
        """Fail-fast при создании невалидного манифеста (L0: ValueError, не тихий fallback)."""
        if not self.window_id or not self.title:
            raise ValueError(f"WindowManifest: window_id/title обязательны ({self.window_id!r})")
        if self.layer not in (2, 3, 4):
            raise ValueError(f"WindowManifest[{self.window_id}]: layer={self.layer} вне 2..4 (UI Doctrine §IX)")
        if not self.data_source:
            raise ValueError(f"WindowManifest[{self.window_id}]: data_source обязателен (Закон Причинности)")

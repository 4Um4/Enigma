"""
path: /frontend/ui_workbench/windows/board_window.py
Назначение: Окно «Доска расследования» (Phase 4 MVI) — стол, на котором
    игрок раскладывает уже полученные ENIGMA-материалы. Рендер = чистая
    проекция: карточки рисуются из board-канала (организация), материал
    джойнится клиентом против dialog_journal по event_id (резолв —
    ответственность клиента, M7). Мёртвая карточка (ref вытеснен FIFO
    cap-100) рендерится серым с provenance-хвостом — валидное состояние.
    Окно НЕ вычисляет семантику (UI DOCTRINE §XII: выводы строит игрок).
Зависимости: ui_workbench.manifests, pygame (для K_b)
Основные сущности: BOARD_MANIFEST
"""
import pygame

from ui_workbench.manifests import InputBinding, WindowManifest, WindowState

BOARD_MANIFEST = WindowManifest(
    window_id="board",
    title="Доска",
    layer=3,                                       # Осознанный анализ (UI Doctrine §IX)
    data_source="investigation_board",             # board-канал: GET /api/board/{campaign}
    default_state=WindowState.HIDDEN,
    anchor="top_right",
    offset=(24, 60),                               # ниже Журнала (анкер тот же)
    size_policy=(0.40, 0.70),
    min_size=(420, 300),
    max_size=(900, 1100),
    z_order=11,
    binding=InputBinding(hotkey=pygame.K_b, click_title_collapse=True),
)
"""
path: /project/frontend/ui_workbench/windows/mini_windows.py
Назначение: Мини-окна HUD (миграция legacy-полос game_screen в Workbench):
    world_clock (дата/время), time_scale (темп). Данные — DTO-каналы (M7).
Зависимости: ui_workbench.manifests
Основные сущности: WORLD_CLOCK_MANIFEST, TIME_SCALE_MANIFEST
"""
from ui_workbench.manifests import WindowManifest, WindowState

WORLD_CLOCK_MANIFEST = WindowManifest(
    window_id="world_clock",
    title="Время",
    layer=2,
    data_source="world_clock",
    default_state=WindowState.COLLAPSED_TO_TITLE,
    anchor="top_right",
    offset=(20, 6),
    size_policy=(0.16, 0.06),
    min_size=(150, 26),
)

TIME_SCALE_MANIFEST = WindowManifest(
    window_id="time_scale",
    title="Темп",
    layer=2,
    data_source="time_scale",
    default_state=WindowState.COLLAPSED_TO_TITLE,
    anchor="top_right",
    offset=(20, 40),
    size_policy=(0.10, 0.05),
    min_size=(90, 26),
)
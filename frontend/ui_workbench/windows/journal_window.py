"""
path: /frontend/ui_workbench/windows/journal_window.py
Назначение: Первый потребитель Workbench — окно Журнала (Journal as a Window).
v1-заготовка: манифест + контракт рендера. Реальный draw поверх analysis_renderer — Шаг 2.
Зависимости: ui_workbench.manifests, pygame (для K_j)
Основные сущности: JOURNAL_MANIFEST
"""
import pygame

from ui_workbench.manifests import InputBinding, WindowManifest, WindowState

JOURNAL_MANIFEST = WindowManifest(
    window_id="journal",
    title="Журнал",
    layer=3,                                   # Осознанный анализ (UI Doctrine §IX)
    data_source="dialog_journal",              # SSOT: avatar_service.get_journal → snapshot
    default_state=WindowState.HIDDEN,
    anchor="top_right",
    offset=(12, 12),
    size_policy=(0.32, 0.62),
    min_size=(360, 260),
    max_size=(680, 940),
    z_order=10,
    binding=InputBinding(hotkey=pygame.K_j, click_title_collapse=True),
)
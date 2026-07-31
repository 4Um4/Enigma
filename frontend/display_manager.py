"""
Назначение: будет читать настройки из файла и применять их во всех экранах.
"""

import pygame
import os
import yaml
from pathlib import Path

# Путь к файлу настроек (создается в папке игры)
CONFIG_PATH = Path("config/user_settings.yaml")

DISPLAY_MODES = {
    'windowed': pygame.RESIZABLE,
    'borderless': pygame.NOFRAME,
    'exclusive': pygame.FULLSCREEN,
}

DEFAULT_SETTINGS = {
    'display_mode': 'windowed',
    'resolution': {'width': 1400, 'height': 900},
    'vsync': 1
}

def load_display_settings() -> dict:
    """Загружает настройки графики из YAML файла."""
    if not CONFIG_PATH.exists():
        return DEFAULT_SETTINGS.copy()
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
            settings = data.get('graphics', DEFAULT_SETTINGS.copy())
            
            # Нормализация разрешения (защита от строкового формата "WxH")
            res = settings.get('resolution')
            if isinstance(res, str):
                try:
                    w, h = res.lower().split('x')
                    settings['resolution'] = {'width': int(w), 'height': int(h)}
                except Exception:
                    settings['resolution'] = {'width': 1400, 'height': 900}
            elif not isinstance(res, dict):
                settings['resolution'] = {'width': 1400, 'height': 900}
                
            return settings
    except Exception:
        return DEFAULT_SETTINGS.copy()

def save_display_settings(settings_data: dict) -> None:
    """Сохраняет настройки графики в YAML файл."""
    data = {}
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            pass
    
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data['graphics'] = settings_data
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        yaml.safe_dump(data, f, allow_unicode=True)

def create_window() -> pygame.Surface:
    """Создает окно Pygame на основе загруженных настроек."""
    settings = load_display_settings()
    mode = settings.get('display_mode', 'windowed')
    res = settings.get('resolution', {'width': 1400, 'height': 900})
    # Защита от некорректного формата (строка вместо dict)
    if isinstance(res, str):
        try:
            w, h = res.lower().split('x')
            res = {'width': int(w), 'height': int(h)}
        except Exception:
            res = {'width': 1400, 'height': 900}
    width, height = res.get('width', 1400), res.get('height', 900)
    vsync = settings.get('vsync', 1)
    
    flags = DISPLAY_MODES.get(mode, pygame.RESIZABLE)
    
    if mode == 'borderless':
        # Для borderless используем полное разрешение монитора
        info = pygame.display.Info()
        width, height = info.current_w, info.current_h
        flags = pygame.NOFRAME
    elif mode == 'exclusive':
        flags = pygame.FULLSCREEN | pygame.SCALED
    else:
        # Оконный режим поддерживает изменение размера
        flags = pygame.RESIZABLE
        if vsync:
            flags |= pygame.SCALED

    try:
        screen = pygame.display.set_mode((width, height), flags, vsync=vsync)
    except pygame.error:
        # Fallback если драйвер не поддерживает запрошенные флаги (например, SCALED+vsync)
        screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
    return screen

def get_available_resolutions() -> list:
    """Возвращает список поддерживаемых монитором разрешений."""
    modes = pygame.display.list_modes()
    if modes == -1 or modes == 0:
        return [(1400, 900), (1920, 1080)]
    # Фильтруем минимум 1280x720 и сортируем по убыванию
    filtered = [(w, h) for w, h in modes if w >= 1280 and h >= 720]
    filtered.sort(key=lambda x: x[0], reverse=True)
    return filtered
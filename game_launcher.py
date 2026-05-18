#!/usr/bin/env python3
"""
path: /game_launcher.py
Назначение: Главная точка входа — управляет жизненным циклом pygame и диспетчеризирует между меню, редактором и игрой
Зависимости: pygame, game_menu, campaign_select, map_editor.editor_core
Основные сущности: main()

Запуск: python game_launcher.py

backend/game_launcher.py
Главная точка входа — игровое меню, запускающее редактор или игру.
Управляет жизненным циклом pygame единообразно для всех подсистем.
"""
import sys
import os
import subprocess
from datetime import datetime


# Два пути нужны из-за голых импортов внутри map_editor (sprite_registry и т.д.)
# TODO: временное решение — после миграции map_editor на относительные импорты убрать второй путь
_ROOT = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.join(_ROOT, "backend")
_FRONTEND_DIR = os.path.join(_ROOT, "frontend")
sys.path.insert(0, _BACKEND_DIR)
sys.path.insert(0, _FRONTEND_DIR)
sys.path.insert(0, os.path.join(_FRONTEND_DIR, "map_editor"))
sys.path.insert(0, _ROOT)  # нужен для импорта пакета diagnostics/ из корня

import pygame
from game_menu import GameMenu, MenuAction
from campaign_select import CampaignSelectScreen
from character_select import CharacterSelectScreen
from game_screen import GameScreen

WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900

# Backend URL — Pygame клиент подключается сюда
_BACKEND_URL = "http://127.0.0.1:8000"
_BACKEND_STARTUP_TIMEOUT = 30  # секунд ожидания (5 проверок × 2сек + startup)


def _ensure_backend_running() -> subprocess.Popen:
    """
    Запускает FastAPI в фоне если ещё не запущен.
    Возвращает Popen для управления жизненным циклом.
    """
    # Проверяем — уже запущен?
    try:
        import urllib.request
        with urllib.request.urlopen(f"{_BACKEND_URL}/api/health", timeout=2) as resp:
            if resp.status == 200:
                print("  ✓ Backend уже запущен")
                return None
    except Exception:
        pass  # backend не запущен — это норма при первичном запуске

    # Запускаем uvicorn в фоне
    # CDS Pipeline: направляем stdout/stderr бэкенда в лог-файл для CausalObserver
    _logs_dir = os.path.join(_BACKEND_DIR, "logs")
    os.makedirs(_logs_dir, exist_ok=True)
    _log_filepath = os.path.join(_logs_dir, f"backend_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    _log_file = open(_log_filepath, "a", encoding="utf-8")

    # Флаг -u отключает буферизацию Python, чтобы CDS получал логи мгновенно
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=_BACKEND_DIR,
        stdout=_log_file,
        stderr=_log_file,
    )

    # Ждём готовности
    print(f"  ○ Запуск backend ({_BACKEND_URL})... (в фоне)")
    # Не ждём — FallbackGateway в игре переключится на Direct если HTTP недоступен
    return proc


def _launch_editor() -> None:
    """Запускает редактор карт и возвращает управление после его закрытия"""
    from map_editor.editor_core import EditorCore
    editor = EditorCore(WINDOW_WIDTH, WINDOW_HEIGHT)
    editor.run()
    # EditorCore больше не вызывает pygame.quit()/sys.exit() — управление возвращается сюда


def _init_menu_display():
    """Пересоздаёт поверхность и меню при старте и после выхода из подсистем"""
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("Enigma")
    clock = pygame.time.Clock()
    menu = GameMenu(screen, clock)
    return screen, clock, menu


def main() -> None:
    """Главная функция — запускает backend, инициализирует pygame, запускает цикл меню"""
    print("\n=== Enigma Startup ===")
    backend_proc = _ensure_backend_running()
    print("=== Pygame Init ===\n")

    pygame.init()
    screen, clock, menu = _init_menu_display()

    # --- CDS: Causal Diagnostic System ---
    _observer = None
    try:
        from diagnostics.causal_observer import CausalObserver
        _observer = CausalObserver()
        _observer.start()
    except Exception as _cds_err:
        print(f"[CDS] Не удалось запустить наблюдатель (игра продолжится): {_cds_err}")

    try:
        while True:
            action = menu.run()

            if action == MenuAction.EDITOR:
                _launch_editor()
                # После выхода из редактора — пересоздаём поверхность и возвращаемся в меню
                screen, clock, menu = _init_menu_display()

            elif action == MenuAction.NEW_GAME:
                screen = pygame.display.get_surface()
                select_screen = CampaignSelectScreen(screen, clock)
                selected_folder = select_screen.run()
                if selected_folder is not None:
                    screen = pygame.display.get_surface()
                    char_screen = CharacterSelectScreen(screen, clock, selected_folder)
                    selected_char = char_screen.run()
                    if selected_char is not None:
                        screen = pygame.display.get_surface()
                        game_screen = GameScreen(screen, clock)
                        game_screen.run(selected_folder, selected_char)
                # Возвращаемся в меню — пересоздаём поверхность и меню
                screen, clock, menu = _init_menu_display()

            elif action == MenuAction.SETTINGS:
                # TODO: временная заглушка — экран настроек
                pass

            elif action == MenuAction.EXIT:
                break

    finally:
        # CDS: записываем отчёт при любом завершении (EXIT, исключение, крэш)
        if _observer is not None:
            try:
                _observer.stop()
                _observer.export("reports/LAST_SESSION.md")
            except Exception as _cds_err:
                print(f"[CDS] Ошибка экспорта: {_cds_err}")

    pygame.quit()

    # Убиваем backend + llama-server при любом выходе
    if sys.platform == "win32":
        for _port in [8000, 8080]:
            try:
                _find = subprocess.run(
                    ["netstat", "-ano"],
                    capture_output=True, text=True, timeout=5,
                )
                for _line in _find.stdout.splitlines():
                    _parts = _line.split()
                    if (len(_parts) >= 2
                            and _parts[1].endswith(f":{_port}")
                            and "LISTENING" in _line):
                        subprocess.run(
                            ["taskkill", "/T", "/F", "/PID", _parts[-1]],
                            capture_output=True, timeout=5,
                        )
            except Exception:
                pass
    elif backend_proc is not None and backend_proc.poll() is None:
        backend_proc.terminate()

    sys.exit(0)


if __name__ == "__main__":
    main()
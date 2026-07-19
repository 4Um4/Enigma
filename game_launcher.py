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

import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Два пути нужны из-за голых импортов внутри map_editor (sprite_registry и т.д.)
# TODO: временное решение — после миграции map_editor на относительные импорты убрать второй путь
_ROOT = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.join(_ROOT, "backend")
_FRONTEND_DIR = os.path.join(_ROOT, "frontend")
sys.path.insert(0, _BACKEND_DIR)
sys.path.insert(0, _FRONTEND_DIR)
sys.path.insert(0, os.path.join(_FRONTEND_DIR, "map_editor"))
sys.path.insert(0, _ROOT)  # нужен для импорта пакета diagnostics/ из корня

import pygame  # noqa: E402
from campaign_select import CampaignSelectScreen  # noqa: E402
from character_select import CharacterSelectScreen  # noqa: E402
from game_menu import GameMenu, MenuAction  # noqa: E402
from game_screen import GameScreen  # noqa: E402
from settings_screen import SettingsScreen  # noqa: E402

WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900

# Backend URL — Pygame клиент подключается сюда
_BACKEND_URL = "http://localhost:8000"
_BACKEND_STARTUP_TIMEOUT = 120  # секунд ожидания (LLM грузится долго)


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
    # BUG M FIX: Перенаправляем stdout/stderr subprocess в CDS лог,
    # чтобы print()-маркеры (DRF_EMIT, IDLE_TRACE, TRAV_CREATE_PRE и т.д.)
    # были видны CausalObserver. Без этого 89 критических маркеров слепы.
    _cds_log_for_subprocess = Path(_BACKEND_DIR) / "logs" / "cds_backend.log"
    _subprocess_log = open(str(_cds_log_for_subprocess), "a", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        cwd=_BACKEND_DIR,
        stdout=_subprocess_log,
        stderr=_subprocess_log,
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


def _kill_zombies():
    """Убивает зомби-процессы python (uvicorn) на порту 8000 перед стартом."""
    import subprocess

    try:
        # Убиваем только зависший бэкенд (uvicorn), LLM не трогаем!
        for port in [8000]:
            res = subprocess.run(
                f"netstat -ano | findstr :{port}",
                shell=True,
                capture_output=True,
                text=True,
            )
            for line in res.stdout.splitlines():
                parts = line.split()
                if len(parts) > 4 and parts[-2] == "LISTENING":
                    pid = parts[-1]
                    subprocess.run(
                        f"taskkill /F /PID {pid}", shell=True, capture_output=True
                    )
    except Exception:
        pass


def main() -> None:
    """Главная функция — запускает backend, инициализирует pygame, запускает цикл меню"""
    print("\n=== Enigma Startup ===")
    backend_proc = _ensure_backend_running()
    print("=== Pygame Init ===\n")

    pygame.init()
    screen, clock, menu = _init_menu_display()

    # --- CDS: Causal Diagnostic System ---
    _observer = None
    _cds_log_path = None
    try:
        _logs_dir = Path(_BACKEND_DIR) / "logs"
        _logs_dir.mkdir(exist_ok=True)
        # Фиксированный путь, чтобы подпроцесс Uvicorn тоже мог писать в этот файл
        _cds_log_path = _logs_dir / "cds_backend.log"
        # Очищаем лог при старте новой сессии
        with open(_cds_log_path, "w", encoding="utf-8") as f:
            f.write(f"=== ENIGMA SESSION STARTED {datetime.now()} ===\n")

        _cds_handler = logging.FileHandler(str(_cds_log_path), encoding="utf-8")
        _cds_handler.setLevel(logging.DEBUG)
        _cds_handler.setFormatter(
            logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s")
        )

        _root_logger = logging.getLogger()
        _root_logger.setLevel(logging.INFO)
        _root_logger.addHandler(_cds_handler)

        from diagnostics.causal_observer import CausalObserver

        _observer = CausalObserver(log_path=str(_cds_log_path))
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
                    # ADR-O-146: New Game = сброс runtime мира
                    # Ждём готовности backend (race condition: uvicorn мог ещё не подняться)
                    import time as _time

                    _backend_ok = False
                    print("  ○ Ожидание готовности backend...", end="", flush=True)
                    # Ждём до _BACKEND_STARTUP_TIMEOUT секунд (бэкенд грузит LLM)
                    for _attempt in range(_BACKEND_STARTUP_TIMEOUT):
                        try:
                            import urllib.request as _ur

                            with _ur.urlopen(
                                f"{_BACKEND_URL}/api/health", timeout=2
                            ) as _hr:
                                if _hr.status == 200:
                                    _backend_ok = True
                                    break
                        except Exception:
                            pass
                        print(".", end="", flush=True)
                        _time.sleep(1)
                    print()
                    if _backend_ok:
                        try:
                            from api_client import HttpClient

                            _http = HttpClient(base_url=_BACKEND_URL)
                            _http.post(f"/api/game/new/{selected_folder}", payload={})
                            print(f"  ✓ Runtime сброшен для '{selected_folder}'")
                        except Exception as e:
                            print(f"  ⚠ New game reset failed: {e}")
                    else:
                        print(
                            f"  ⚠ Backend не отвечает {_BACKEND_STARTUP_TIMEOUT}с, сброс пропущен"
                        )
                    screen = pygame.display.get_surface()
                    char_screen = CharacterSelectScreen(screen, clock, selected_folder)
                    selected_char = char_screen.run()
                    if selected_char is not None:
                        screen = pygame.display.get_surface()
                        game_screen = GameScreen(screen, clock)
                        game_screen.run(selected_folder, selected_char)
                # Возвращаемся в меню — пересоздаём поверхность и меню
                screen, clock, menu = _init_menu_display()

            elif action == MenuAction.CONTINUE:
                # ADR-O-146: Continue = загрузка существующего сохранения (без сброса)
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
                settings_screen = SettingsScreen(screen, clock)
                settings_screen.run()
                # Возвращаемся в меню — пересоздаём поверхность и меню
                screen, clock, menu = _init_menu_display()

            elif action == MenuAction.EXIT:
                break

    finally:
        # CDS: Сбрасываем буфер логов на диск перед чтением
        logging.shutdown()

        # CDS: записываем отчёт при любом завершении (EXIT, исключение, крэш)
        if _observer is not None:
            try:
                _observer.stop()
                _observer.export("reports/LAST_SESSION.md")
            except Exception as _cds_err:
                print(f"[CDS] Ошибка экспорта: {_cds_err}")

        pass  # лог-файл не используется

    pygame.quit()

    # Убиваем backend + llama-server при любом выходе
    if sys.platform == "win32":
        from app.core.config import settings as _enigma_settings
        for _port in [8000, _enigma_settings.llama_cpp_port]:
            try:
                _find = subprocess.run(
                    ["netstat", "-ano"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                for _line in _find.stdout.splitlines():
                    _parts = _line.split()
                    if (
                        len(_parts) >= 2
                        and _parts[1].endswith(f":{_port}")
                        and "LISTENING" in _line
                    ):
                        subprocess.run(
                            ["taskkill", "/T", "/F", "/PID", _parts[-1]],
                            capture_output=True,
                            timeout=5,
                        )
            except Exception:
                pass
    elif backend_proc is not None and backend_proc.poll() is None:
        backend_proc.terminate()

    sys.exit(0)


if __name__ == "__main__":
    main()

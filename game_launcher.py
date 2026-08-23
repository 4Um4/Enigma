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

# Центрируем окно игры на экране (должно быть до импорта pygame)
os.environ['SDL_VIDEO_CENTERED'] = '1'

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
from campaign_select import CampaignSelectScreen  # type: ignore  # noqa: E402
from character_select import CharacterSelectScreen  # type: ignore  # noqa: E402
from game_menu import GameMenu, MenuAction  # type: ignore  # noqa: E402
from game_screen import GameScreen  # type: ignore  # noqa: E402
from settings_screen import SettingsScreen  # type: ignore  # noqa: E402

WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900

# Backend URL — загружается из конфига внутри main() и _ensure_backend_running()
_BACKEND_URL = "http://localhost:8000"
_BACKEND_STARTUP_TIMEOUT = 120  # секунд ожидания (LLM грузится долго)


def _ensure_llm_running() -> subprocess.Popen:
    """Запускает llama-server.exe локально, если он ещё не запущен."""
    import urllib.request
    
    # Локальный импорт конфига
    from app.core.config import settings as _enigma_settings  # type: ignore
    _llm_port = getattr(_enigma_settings, "llama_cpp_port", 8181)
    _llm_url = f"http://localhost:{_llm_port}/health"
    
    # Проверяем — уже запущен?
    try:
        with urllib.request.urlopen(_llm_url, timeout=2) as resp:
            if resp.status == 200:
                print("  ✓ LLM сервер уже запущен")
                return None
    except Exception:
        pass # LLM не запущен, это норма
        
    # Ищем исполняемый файл llama-server
    _llm_exe = os.path.join(_ROOT, "Models LLM", "llama", "llama-server.exe")
    if not os.path.exists(_llm_exe):
        _llm_exe = os.path.join(_ROOT, "Models LLM", "llama", "main.exe")
        if not os.path.exists(_llm_exe):
            print("  ✗ llama-server.exe не найден. LLM не будет запущен.")
            return None
            
    # Берем путь к модели из настроек бэкенда
    _model_path = getattr(_enigma_settings, "llama_cpp_model_path", os.path.join(_ROOT, "Models LLM", "Qwen2.5-7B-Instruct-abliterated-v2.Q5_K_M.gguf"))
    if not os.path.exists(_model_path):
        print(f"  ✗ Файл модели не найден: {_model_path}. LLM не будет запущен.")
        return None
        
    _creation_flags = 0
    if sys.platform == 'win32':
        _creation_flags = 0x08000000  # CREATE_NO_WINDOW
        
    # Лог для LLM
    _llm_log_path = Path(_ROOT) / "backend" / "logs" / "llama_server.log"
    _llm_log_path.parent.mkdir(parents=True, exist_ok=True)
    _llm_log = open(str(_llm_log_path), "a", encoding="utf-8")
    
    try:
        _gpu_layers = getattr(_enigma_settings, "gpu_layers", 35)
    except Exception:
        _gpu_layers = 35
        
    proc = subprocess.Popen(
        [
            _llm_exe,
            "--host", "127.0.0.1",
            "--port", str(_llm_port),
            "-m", _model_path,
            "-c", "8192",
            "-ngl", str(_gpu_layers),
            "--metrics"
        ],
        cwd=os.path.dirname(_llm_exe),
        stdout=_llm_log,
        stderr=_llm_log,
        creationflags=_creation_flags
    )
    print(f"  ○ Запуск LLM сервера (PID {proc.pid})...")
    return proc


def _ensure_servers_running() -> tuple:
    """Запускает LLM и FastAPI, рисует экран загрузки и ждёт готовности обоих."""
    import urllib.request
    import time
    import pygame

    from app.core.config import settings as _enigma_settings  # type: ignore
    _api_host = _enigma_settings.api_host
    _api_port = _enigma_settings.api_port
    _llm_port = getattr(_enigma_settings, "llama_cpp_port", 8181)
    global _BACKEND_URL
    _BACKEND_URL = f"http://localhost:{_api_port}"

    # 1. Запускаем LLM в фоне (Popen не блокирует поток)
    llm_proc = _ensure_llm_running()

    # 2. Проверяем — уже запущен ли Backend?
    backend_proc = None
    try:
        with urllib.request.urlopen(f"{_BACKEND_URL}/api/health", timeout=2) as resp:
            if resp.status == 200:
                print("  ✓ Backend уже запущен")
                backend_proc = None
    except Exception:
        # Backend не запущен — запускаем
        _cds_log_for_subprocess = Path(_BACKEND_DIR) / "logs" / "cds_backend.log"
        _cds_log_for_subprocess.parent.mkdir(parents=True, exist_ok=True)
        _subprocess_log = open(str(_cds_log_for_subprocess), "a", encoding="utf-8")

        _creation_flags = 0
        if sys.platform == 'win32':
            _creation_flags = 0x08000000  # CREATE_NO_WINDOW

        _env = os.environ.copy()
        _env["PYTHONIOENCODING"] = "utf-8"
        _env["PYTHONUTF8"] = "1"

        backend_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                _api_host,
                "--port",
                str(_api_port),
            ],
            cwd=_BACKEND_DIR,
            stdout=_subprocess_log,
            stderr=_subprocess_log,
            creationflags=_creation_flags,
            env=_env,
        )
        print(f"  ○ Запуск backend ({_BACKEND_URL})...")

    # 3. Инициализируем экран загрузки
    screen = pygame.display.get_surface()
    if not screen:
        screen = pygame.display.set_mode((800, 600))
        pygame.display.set_caption("Загрузка Bloodloom...")

    font = pygame.font.SysFont("Arial", 24)
    clock = pygame.time.Clock()

    _backend_ok = False
    _llm_ok = (llm_proc is None)  # Если LLM не запущен нами (уже шел или ошибка), не ждем его

    for _attempt in range(_BACKEND_STARTUP_TIMEOUT):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if backend_proc: backend_proc.terminate()
                if llm_proc: llm_proc.terminate()
                pygame.quit()
                sys.exit(0)

        screen.fill((20, 20, 20))
        loading_text = font.render("Идёт загрузка мира...", True, (200, 200, 200))
        screen.blit(loading_text, (50, 50))

        progress = _attempt / _BACKEND_STARTUP_TIMEOUT
        pygame.draw.rect(screen, (50, 50, 50), (50, 100, 700, 20))
        pygame.draw.rect(screen, (0, 120, 200), (50, 100, int(700 * progress), 20))

        status_text = "Ожидание AI-модели..." if not _llm_ok else "Ожидание Backend..."
        sec_text = font.render(status_text, True, (150, 150, 150))
        screen.blit(sec_text, (50, 130))
        pygame.display.flip()
        clock.tick(30)

        if backend_proc is not None and backend_proc.poll() is not None:
            print(f"\n  ✗ Backend процесс упал с кодом {backend_proc.returncode}.")
            backend_proc = None

        if llm_proc is not None and llm_proc.poll() is not None:
            print(f"\n  ✗ LLM процесс упал с кодом {llm_proc.returncode}.")
            llm_proc = None

        if not _backend_ok and backend_proc is not None:
            try:
                with urllib.request.urlopen(f"{_BACKEND_URL}/api/health", timeout=2) as resp:
                    if resp.status == 200:
                        _backend_ok = True
                        print("\n  ✓ Backend готов к работе")
            except Exception:
                pass
        elif backend_proc is None and not _backend_ok:
            _backend_ok = True

        if not _llm_ok and llm_proc is not None:
            try:
                with urllib.request.urlopen(f"http://localhost:{_llm_port}/health", timeout=2) as resp:
                    if resp.status == 200:
                        _llm_ok = True
                        print("\n  ✓ LLM готов к работе")
            except Exception:
                pass

        if _backend_ok and _llm_ok:
            break

    if not (_backend_ok and _llm_ok):
        print(f"\n  ⚠ Не все сервисы готовы за {_BACKEND_STARTUP_TIMEOUT}с")

    return backend_proc, llm_proc


def _launch_editor() -> None:
    """Запускает редактор карт и возвращает управление после его закрытия"""
    from map_editor.editor_core import EditorCore

    editor = EditorCore(WINDOW_WIDTH, WINDOW_HEIGHT)
    editor.run()
    # EditorCore больше не вызывает pygame.quit()/sys.exit() — управление возвращается сюда


def _init_menu_display():
    """Пересоздаёт поверхность и меню при старте и после выхода из подсистем"""
    from display_manager import create_window
    screen = create_window()
    pygame.display.set_caption("Bloodloom")
    clock = pygame.time.Clock()
    menu = GameMenu(screen, clock)
    return screen, clock, menu


def _kill_zombies():
    """Убивает зомби-процессы (uvicorn, llama-server) перед стартом."""
    import subprocess
    from app.core.config import settings as _enigma_settings  # type: ignore

    # 1. Убиваем по портам (самый надежный способ найти висящие сокеты)
    try:
        for port in [_enigma_settings.api_port, getattr(_enigma_settings, "llama_cpp_port", 8181)]:
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
                        f"taskkill /F /T /PID {pid}", shell=True, capture_output=True
                    )
    except Exception:
        pass
        
    # 2. Убиваем все экземпляры llama-server.exe (фоллбэк)
    try:
        subprocess.run("taskkill /F /IM llama-server.exe", shell=True, capture_output=True)
        subprocess.run("taskkill /F /IM llama-server.exe", shell=True, capture_output=True)
    except Exception:
        pass


def main() -> None:
    """Главная функция — запускает backend, инициализирует pygame, запускает цикл меню"""
    print("\n=== Enigma Startup ===")
    _kill_zombies()
    
    # Инициализируем pygame до запуска бэкенда, чтобы отрисовать экран загрузки
    print("=== Pygame Init ===")
    pygame.init()
    
    backend_proc, llm_proc = _ensure_servers_running()
    
    screen, clock, menu = _init_menu_display()

    # --- CDS: Causal Diagnostic System ---
    _observer = None
    _cds_log_path = None
    try:
        _logs_dir = Path(_BACKEND_DIR) / "logs"
        _logs_dir.mkdir(parents=True, exist_ok=True)
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
                    screen = pygame.display.get_surface()
                    char_screen = CharacterSelectScreen(screen, clock, selected_folder)
                    selected_data = char_screen.run()
                    if selected_data is not None:
                        # ADR-O-146: New Game = сброс runtime мира через шлюз
                        # Ждём готовности backend (race condition: uvicorn мог ещё не подняться)
                        import time as _time

                        _backend_ok = False
                        print("  ○ Ожидание готовности backend...", end="", flush=True)
                        for _attempt in range(_BACKEND_STARTUP_TIMEOUT):
                            try:
                                import urllib.request as _ur
                                with _ur.urlopen(
                                    f"{_BACKEND_URL}/api/health", timeout=2
                                ) as _hr:
                                    if _hr.status == 200:
                                        _backend_ok = True
                                        print(f"\n  [DIAG_LAUNCH] Health OK on attempt {_attempt}", flush=True)
                                        break
                            except Exception as _e:
                                print(f"\n  [DIAG_LAUNCH] Wait exception: {_e}", flush=True)
                            print(".", end="", flush=True)
                            _time.sleep(1)
                        print()
                        print(f"  [DIAG_LAUNCH] Backend OK: {_backend_ok}", flush=True)
                        
                        _reset_ok = False
                        if _backend_ok:
                            try:
                                from api_client import create_game_gateway
                                _gateway, _ = create_game_gateway()
                                
                                _result = _gateway.new_game(
                                    campaign_id=selected_folder,
                                    continuity_mode=selected_data.get("continuity_mode", "isolated"),
                                    source_campaign_id=selected_folder  # MVP: source = self
                                )
                                if not isinstance(_result, dict):
                                    raise RuntimeError(f"Gateway returned non-dict: {_result}")
                                _reset_ok = bool(_result.get("reset"))
                                if _reset_ok:
                                    print(f"  ✓ Runtime сброшен для '{selected_folder}'")
                                else:
                                    print(f"  ⚠ New game reset failed: {_result.get('error', 'Unknown')}")
                            except Exception as e:
                                print(f"  ⚠ Gateway initialization failed: {e}")
                        else:
                            print(f"  ⚠ Backend не отвечает {_BACKEND_STARTUP_TIMEOUT}с, сброс пропущен")
                        
                        # Запускаем игру только если сброс мира прошёл успешно
                        if _reset_ok:
                            screen = pygame.display.get_surface()
                            game_screen = GameScreen(screen, clock)
                            game_screen.run(selected_folder, selected_data["character_id"])
                        else:
                            print("  ✖ Запуск игры отменён из-за ошибки сброса мира.")
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
                    selected_data = char_screen.run()
                    if selected_data is not None:
                        # NEW-MVP-002 FIX: Ждём готовности backend и инициализируем кампанию (без сброса).
                        import time as _time
                        import urllib.request as _ur
                        _backend_ok = False
                        for _attempt in range(10):
                            try:
                                with _ur.urlopen(f"{_BACKEND_URL}/api/health", timeout=2) as _hr:
                                    if _hr.status == 200:
                                        _backend_ok = True
                                        break
                            except Exception:
                                _time.sleep(0.5)
                        
                        if _backend_ok:
                            try:
                                from api_client import create_game_gateway
                                _gateway, _ = create_game_gateway()
                                # continuity_mode="continuous" сохраняет прогресс и инициализирует MVP
                                _gateway.new_game(
                                    campaign_id=selected_folder,
                                    continuity_mode="continuous",
                                    source_campaign_id=selected_folder
                                )
                            except Exception as e:
                                print(f"  ⚠ Continue backend init failed: {e}")

                        screen = pygame.display.get_surface()
                        game_screen = GameScreen(screen, clock)
                        game_screen.run(selected_folder, selected_data["character_id"])
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
    print("\n[CLEANUP] Завершение процессов backend и LLM...")
    if sys.platform == "win32":
        from app.core.config import settings as _enigma_settings  # type: ignore
        
        # 1. Убиваем деревья процессов uvicorn и LLM напрямую по их PID
        for _proc in [backend_proc, llm_proc]:
            if _proc is not None and _proc.poll() is None:
                try:
                    subprocess.run(["taskkill", "/T", "/F", "/PID", str(_proc.pid)], capture_output=True, timeout=5)
                except Exception:
                    pass
            
        # 2. Убиваем всё, что слушает порты (фоллбэк для зомби без Popen-ссылки)
        for _port in [_enigma_settings.api_port, _enigma_settings.llama_cpp_port]:
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

    # Принудительно убиваем процесс игры, чтобы не было зомби (Фикс PyInstaller/Windows)
    import os
    os._exit(0)


if __name__ == "__main__":
    main()

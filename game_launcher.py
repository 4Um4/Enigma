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

# Локальные серверы (uvicorn, llama-server) никогда не ходят через прокси:
# без этого urllib на машинах с системным прокси/WPAD платит до ~4с на КАЖДЫЙ
# health-запрос (десятки запросов за старт) — наблюдено на PowerShell-замерах,
# Python-клиент читает те же настройки реестра. Страховка дистрибутива.
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'

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

# ─── LOG-GATE-UI: диагноз «почему AI не работает» ────────────────────────────
# Причина заполняется в _ensure_llm_running (exe/модель не найдены) и в цикле
# ожидания (_ensure_servers_running), когда llama-server умер: свежий вывод
# его логов классифицируется в понятную игроку причину и показывается прямо
# на экране загрузки + финальной карточке. Игрок может сфотографировать
# экран и прислать — логи не нужны.
_LLM_DIAG = {"reason": "", "detail": "", "log_offset": 0}

_LLM_REASONS = {
    "exe_missing": "Не найден llama-server.exe — движок AI отсутствует. Переустановите игру (компонент «Движок llama.cpp»).",
    "model_missing": "Файл AI-модели не найден. Скачайте модель: Настройки → LLM Модели.",
    "cuda": "Видеокарта или её драйвер не поддерживают CUDA. Нужна видеокарта NVIDIA и свежий драйвер.",
    "vram": "Недостаточно видеопамяти (VRAM) для этой модели. Выберите модель поменьше: Настройки → LLM Модели.",
    "blocked": "llama-server.exe заблокирован системой или антивирусом. Разрешите запуск этого файла.",
    "port": "Порт LLM занят другим процессом. Перезагрузите компьютер и запустите игру снова.",
    "model_bad": "Файл модели повреждён (обрыв при скачивании). Настройки → LLM Модели → «Скачать заново».",
    "unknown": "LLM-сервер завершился с ошибкой.",
}


def _llm_classify(text: str):
    """Свежий вывод llama-server → (ключ причины, строка-деталь для игрока)."""
    if not text or not text.strip():
        return "unknown", ""
    _low = text.lower()
    # Дефинитивные признаки отсутствия/неработающего CUDA — важнее VRAM-правил:
    # «failed to allocate» на машине без NVIDIA не должен уводить в неверную
    # причину («недостаточно видеопамяти»).
    if any(
        _n in _low
        for _n in (
            "no cuda-capable", "cuda driver version is insufficient",
            "failed to initialize cuda", "cuda error", "no devices",
        )
    ):
        return "cuda", _first_detail(text)
    _rules = [
        ("vram", ("out of memory", "oom", "failed to allocate", "not enough memory", "vram")),
        ("cuda", (
            "ggml_backend_cuda", "cudamalloc", "cublas", "cudart", "cudnn",
        )),
        ("model_missing", ("no such file", "does not exist", "file not found", "unable to open")),
        ("model_bad", ("unable to load model", "failed to load model", "error loading model", "invalid magic", "corrupt")),
        ("blocked", ("winerror 5", "access is denied", "permission denied", "0x80070005")),
        ("port", ("address already in use", "error while binding", "failed to bind", "only one usage of each socket")),
    ]
    # Первая содержательная строка вывода — кандидат в «деталь» для скриншота.
    _detail = _first_detail(text)
    for _key, _needles in _rules:
        if any(_n in _low for _n in _needles):
            return _key, _detail
    return "unknown", _detail


def _first_detail(text: str) -> str:
    """Первая содержательная строка вывода llama-server — «деталь» для скриншота."""
    for _line in text.splitlines():
        _s = _line.strip()
        if len(_s) > 20 and not _s.startswith(("srv ", "main:", "slot", "print_timing", "prompt ")):
            return _s[:160]
    return ""



def _llm_read_new_output() -> str:
    """Свежий (с момента текущего запуска) вывод llama-server из логов.
    llama_server.log читается с запомненного смещения — ошибки прошлых
    запусков не смешиваются с текущими; llama_server_stderr.log — хвост
    60 строк (его пишет backend-путь запуска)."""
    _parts = []
    _p_main = Path(_ROOT) / "backend" / "logs" / "llama_server.log"
    try:
        if _p_main.exists():
            _size = _p_main.stat().st_size
            _off = min(int(_LLM_DIAG.get("log_offset", 0)), _size)
            with open(_p_main, "r", encoding="utf-8", errors="replace") as _f:
                if _off:
                    _f.seek(_off)
                _parts.append(_f.read())
    except Exception:
        pass
    _p_err = Path(_ROOT) / "backend" / "logs" / "llama_server_stderr.log"
    try:
        if _p_err.exists():
            _lines = _p_err.read_text(encoding="utf-8", errors="replace").splitlines()
            _parts.append("\n".join(_lines[-60:]))
    except Exception:
        pass
    return "\n".join(_parts)


def _wrap_ru(text: str, width: int = 68):
    """Перенос длинных русских строк по словам (для pygame-рендера)."""
    _out = []
    for _para in text.splitlines():
        _cur = ""
        for _word in _para.split():
            _cand = (_cur + " " + _word).strip()
            if len(_cand) <= width:
                _cur = _cand
            else:
                if _cur:
                    _out.append(_cur)
                _cur = _word
        if _cur:
            _out.append(_cur)
    return _out


def _draw_llm_diag_screen(seconds: float = 10.0) -> None:
    """Полноэкранная карточка «почему AI не работает»: игрок фотографирует
    и присылает разработчику — логи не нужны. Ждёт клавишу/клик или seconds."""
    _screen = pygame.display.get_surface()
    if not _screen:
        return
    pygame.font.init()  # страховка: шрифтовая подсистема может быть не инициализирована
    _font = pygame.font.SysFont("Arial", 22)
    _font_big = pygame.font.SysFont("Arial", 30, bold=True)
    _reason = _LLM_REASONS.get(_LLM_DIAG.get("reason", ""), _LLM_REASONS["unknown"])
    _detail = str(_LLM_DIAG.get("detail", "")).strip()
    _lines = ["NPC не смогут говорить с игроком."]
    _lines += _wrap_ru(_reason)
    if _detail:
        _lines += ["", "Техническая деталь (пришлите её разработчику):"]
        _lines += _wrap_ru(_detail, 80)
    _lines += [
        "",
        "Игра продолжится без AI-диалогов NPC.",
        "Управление моделями: Настройки → LLM Модели.",
        "",
        "Нажмите любую клавишу, чтобы продолжить...",
    ]
    _clock = pygame.time.Clock()
    _end = pygame.time.get_ticks() + int(seconds * 1000)
    while pygame.time.get_ticks() < _end:
        for _ev in pygame.event.get():
            if _ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)
            if _ev.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                return
        _screen.fill((20, 20, 20))
        _y = 50
        _screen.blit(_font_big.render("AI не запущен", True, (255, 170, 60)), (50, _y))
        _y += 56
        for _ln in _lines:
            if _ln:
                _color = (255, 170, 60) if _ln.startswith("NPC") else (220, 220, 220)
                _screen.blit(_font.render(_ln, True, _color), (50, _y))
            _y += 28
        pygame.display.flip()
        _clock.tick(30)
# ─── конец LOG-GATE-UI ───────────────────────────────────────────────────────


def _ensure_llm_running() -> subprocess.Popen:
    """Запускает llama-server.exe локально, если он ещё не запущен."""
    import urllib.request
    
    # Локальный импорт конфига
    from app.core.config import settings as _enigma_settings  # type: ignore
    _llm_port = getattr(_enigma_settings, "llama_cpp_port", 8181)
    _llm_url = f"http://127.0.0.1:{_llm_port}/health"
    
    # Проверяем — уже запущен? timeout=0.5: после _kill_zombies() LLM почти
    # всегда мёртв, 2с ожидания были гарантированной потерей на каждом старте.
    # 0.5с достаточно для ответа живого localhost-сервера.
    try:
        with urllib.request.urlopen(_llm_url, timeout=0.5) as resp:
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
            # LOG-GATE-UI: показываем причину игроку на экране загрузки.
            _LLM_DIAG["reason"] = "exe_missing"
            _LLM_DIAG["detail"] = _llm_exe
            return None
      
    # Берем путь к модели из настроек бэкенда
    _model_path = getattr(_enigma_settings, "llama_cpp_model_path", os.path.join(_ROOT, "Models LLM", "Qwen2.5-7B-Instruct-abliterated-v2.Q4_K_M.gguf"))
    _file_exists = os.path.exists(_model_path)
    _file_size = os.path.getsize(_model_path) if _file_exists else 0
    print(f"  [DIAG_LAUNCH] Проверка модели: {_model_path} (exists={_file_exists}, size={_file_size} bytes)")
    if not _file_exists or _file_size < 1024 * 1024:  # Файл должен быть больше 1 МБ
        print(f"  ✗ Файл модели не найден или повреждён (размер < 1МБ): {_model_path}.")
        # LOG-GATE-UI: причина видна игроку; после экрана загрузки main()
        # сам откроет принудительный экран Настройки → LLM Модели.
        _LLM_DIAG["reason"] = "model_missing"
        _LLM_DIAG["detail"] = _model_path
        return None

    _creation_flags = 0
    if sys.platform == 'win32':
        _creation_flags = 0x08000000  # CREATE_NO_WINDOW
        
    # Лог для LLM
    _llm_log_path = Path(_ROOT) / "backend" / "logs" / "llama_server.log"
    _llm_log_path.parent.mkdir(parents=True, exist_ok=True)
    _llm_log = open(str(_llm_log_path), "a", encoding="utf-8")

    # LOG-GATE-UI: запоминаем размер лога — если llama-server умрёт, читаем
    # только свежий вывод (ошибки прошлых запусков не попадут в диагноз).
    try:
        _LLM_DIAG["log_offset"] = _llm_log_path.stat().st_size
    except Exception:
        _LLM_DIAG["log_offset"] = 0

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
    # 127.0.0.1, не localhost: config.py биндит api_host=127.0.0.1, а резолв
    # localhost на части машин (IPv6 ::1 -> IPv4 фолбэк) добавляет секунды
    # к КАЖДОМУ health-запросу — наблюдено замерами (refused за 4с вместо мс).
    # Единый хост с биндом — заодно честнее.
    _BACKEND_URL = f"http://127.0.0.1:{_api_port}"
    import os as _os_cfg  # AUDIT #13: LLM-вкладка читает тот же адрес
    _os_cfg.environ.setdefault("ENIGMA_BACKEND_URL", _BACKEND_URL)

    # ЕДИНАЯ шкала прогресса на весь _ensure_servers_running (окно уже создано
    # в main()). Раньше бар существовал только в цикле ожидания готовности и
    # стоял на нуле ~4-5с, пока zombie-kill + LLM health + backend spawn
    # выполнялись молча. Теперь: бар + статус одним вызовом, доли шкалы
    # подобраны из фактических таймингов лога.
    _status_screen = pygame.display.get_surface()
    _status_font = pygame.font.SysFont("Arial", 24)

    def _draw_progress(text: str, fraction: float) -> None:
        """Рисует окно загрузки: заголовок, статус этапа, бар (0..1).
        fraction может уточняться внутри этапа (LLM wait передаёт свой прогресс)."""
        if not _status_screen:
            return
        _status_screen.fill((20, 20, 20))
        _title = _status_font.render("Идёт загрузка мира...", True, (200, 200, 200))
        _status_screen.blit(_title, (50, 50))
        _status_screen.blit(_status_font.render(text, True, (150, 150, 150)), (50, 130))
        # Бар в том же стиле, что и цикл ожидания ниже (единый вид экрана)
        pygame.draw.rect(_status_screen, (50, 50, 50), (50, 100, 700, 20))
        _fill = int(700 * max(0.0, min(1.0, fraction)))
        if _fill > 0:
            pygame.draw.rect(_status_screen, (0, 120, 200), (50, 100, _fill, 20))
        # LOG-GATE-UI: живой диагноз «почему AI не работает» — виден игроку
        # весь прогон ожидания, логи не нужны.
        if _LLM_DIAG.get("reason"):
            _diag_y = 150
            _diag_text = "⚠ AI не запущен: " + _LLM_REASONS.get(_LLM_DIAG["reason"], _LLM_REASONS["unknown"])
            for _ln in _wrap_ru(_diag_text)[:4]:
                _status_screen.blit(_font.render(_ln, True, (255, 170, 60)), (50, _diag_y))
                _diag_y += 26
        pygame.display.flip()

    # Этап 1/5: очистка зомби (netstat/taskkill ~1с) — была полностью невидима
    _draw_progress("Очистка фоновых процессов...", 0.10)

    # Этап 2/5: LLM health check (timeout=2) + Popen
    _draw_progress("Подготовка AI-модели...", 0.30)

    # 1. Запускаем LLM в фоне (Popen не блокирует поток)
    llm_proc = _ensure_llm_running()

    # Этап 3/5: спавн backend
    _draw_progress("Запуск игрового сервера...", 0.50)

    # 2. Проверяем — уже запущен ли Backend?
    backend_proc = None
    # timeout=0.5 — та же логика: после _kill_zombies() backend мёртв,
    # ждать 2с нечего (живой localhost отвечает за миллисекунды)
    try:
        with urllib.request.urlopen(f"{_BACKEND_URL}/api/health", timeout=0.5) as resp:
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
        _dt("backend Popen issued")

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

        # Общая шкала: ожидание готовности — последние 50% (0.50 → 1.0),
        # делённые между LLM и backend по факту их готовности
        _stage_fraction = 0.50
        if _llm_ok:
            _stage_fraction += 0.25
        if _backend_ok:
            _stage_fraction += 0.25
        # Внутри этапа — плавный подтProgress по попыткам (до 0.2 доли шкалы)
        _attempt_frac = (_attempt / _BACKEND_STARTUP_TIMEOUT) * 0.20
        _status_text = "Ожидание AI-модели..." if not _llm_ok else "Ожидание Backend..."
        _draw_progress(_status_text, _stage_fraction + _attempt_frac * (0.5 if _llm_ok or _backend_ok else 1.0))

        if backend_proc is not None and backend_proc.poll() is not None:
            print(f"\n  ✗ Backend процесс упал с кодом {backend_proc.returncode}.")
            backend_proc = None

        if llm_proc is not None and llm_proc.poll() is not None:
            print(f"\n  ✗ LLM процесс упал с кодом {llm_proc.returncode}.")
            # LOG-GATE-UI: классифицируем свежий вывод llama-server в понятную
            # игроку причину; ждать умерший процесс оставшиеся попытки смысла
            # нет — продолжаем без LLM (диагноз останется на экране загрузки).
            _reason, _detail = _llm_classify(_llm_read_new_output())
            _LLM_DIAG["reason"] = _reason
            _LLM_DIAG["detail"] = _detail or f"exit code {llm_proc.returncode}"
            llm_proc = None
            _llm_ok = True

        # Опрос выживших: timeout=0.3 — живой localhost отвечает <100мс;
        # закрытый порт даёт ConnectionRefused мгновенно (не таймаут).
        # Прежние timeout=2 на каждый чек удлиняли цикл: 2 невыполненных
        # запроса = до 4с за проход при шаге кадра 1/30с.
        if not _backend_ok and backend_proc is not None:
            try:
                with urllib.request.urlopen(f"{_BACKEND_URL}/api/health", timeout=0.3) as resp:
                    if resp.status == 200:
                        _backend_ok = True
                        print("\n  ✓ Backend готов к работе")
                        _dt("backend health OK")
            except Exception:
                pass
        elif backend_proc is None and not _backend_ok:
            _backend_ok = True

        if not _llm_ok and llm_proc is not None:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{_llm_port}/health", timeout=0.3) as resp:
                    if resp.status == 200:
                        _llm_ok = True
                        print("\n  ✓ LLM готов к работе")
                        _dt("llm health OK")
            except Exception:
                pass

        if _backend_ok and _llm_ok:
            break

    if not (_backend_ok and _llm_ok):
        print(f"\n  ⚠ Не все сервисы готовы за {_BACKEND_STARTUP_TIMEOUT}с")

    # LOG-GATE-UI: финальная карточка с причиной («AI не запущен — потому
    # что…»). Для model_missing не показываем: сразу после возврата main()
    # сам откроет принудительный экран Настройки → LLM Модели.
    if _LLM_DIAG.get("reason") and _LLM_DIAG["reason"] != "model_missing":
        _draw_llm_diag_screen()

    _dt(f"wait loop done (backend_ok={_backend_ok}, llm_ok={_llm_ok})")
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
        _no_window = 0x08000000 if sys.platform == 'win32' else 0  # CREATE_NO_WINDOW
        for port in [_enigma_settings.api_port, getattr(_enigma_settings, "llama_cpp_port", 8181)]:
            res = subprocess.run(
                f"netstat -ano | findstr :{port}",
                shell=True,
                capture_output=True,
                text=True,
                creationflags=_no_window,
            )
            for line in res.stdout.splitlines():
                parts = line.split()
                if len(parts) > 4 and parts[-2] == "LISTENING":
                    pid = parts[-1]
                    subprocess.run(
                        f"taskkill /F /T /PID {pid}", shell=True, capture_output=True,
                        creationflags=_no_window,
                    )
    except Exception:
        pass
        
    # 2. Убиваем все экземпляры llama-server.exe (фоллбэк)
    try:
        subprocess.run("taskkill /F /IM llama-server.exe", shell=True, capture_output=True)
        subprocess.run("taskkill /F /IM llama-server.exe", shell=True, capture_output=True)
    except Exception:
        pass


def _wait_backend_ready(max_attempts: int = 5, timeout: float = 2.0) -> bool:
    """Быстрая проверка живости backend перед сбросом/инициализацией мира.
    НЕ запускает процесс (это делает _ensure_servers_running один раз при старте) —
    лишь подтверждает HTTP-готовность. Молчит при успехе с первой попытки:
    визуально в логе не должно быть 'второго ожидания'."""
    import urllib.request
    import time as _t
    for _attempt in range(max_attempts):
        try:
            with urllib.request.urlopen(f"{_BACKEND_URL}/api/health", timeout=timeout) as _hr:
                if _hr.status == 200:
                    if _attempt > 0:
                        print(f"\n  ✓ Backend готов (попытка {_attempt + 1})")
                    return True
        except Exception:
            pass
        print(".", end="", flush=True)
        _t.sleep(1)
    print()
    return False


_T0 = None

def _dt(msg: str) -> None:
    """Диагностическая метка elapsed от старта main(): раскладка секунд запуска.
    Пишет в ОТДЕЛЬНЫЙ startup_timing.log: cds_backend.log непригоден —
    CDS-инициализация ниже по main() перезаписывает его режимом "w" и
    стирает все метки, записанные до неё (наблюдено: пустой Select-String)."""
    import time as _t
    global _T0
    if _T0 is None:
        _T0 = _t.monotonic()
    try:
        _log = Path(_BACKEND_DIR) / "logs" / "startup_timing.log"
        _log.parent.mkdir(parents=True, exist_ok=True)
        with open(_log, "a", encoding="utf-8") as _f:
            _f.write(f"[TIMING] +{_t.monotonic() - _T0:6.2f}с  {msg}\n")
    except Exception:
        pass  # диагностика не должна ронять запуск

def main() -> None:
    """Главная функция — запускает backend, инициализирует pygame, запускает цикл меню"""
    # Окно загрузки — ПЕРВОЕ действие main(): игрок видит отклик мгновенно,
    # пока идёт тяжёлая подготовка (zombie-kill ~1с, LLM health timeout ~2с,
    # backend spawn ~2с). Раньше окно создавалось внутри
    # _ensure_servers_running ПОСЛЕ обоих Popen — 4-5 сек без окна = «завис».
    # _ensure_servers_running подхватит эту поверхность через get_surface().
    print("=== Pygame Init ===")
    pygame.init()
    _boot_screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("Загрузка Bloodloom...")
    _boot_screen.fill((20, 20, 20))
    _boot_font = pygame.font.SysFont("Arial", 24)
    _boot_text = _boot_font.render("Идёт загрузка мира...", True, (200, 200, 200))
    _boot_screen.blit(_boot_text, (50, 50))
    pygame.display.flip()
    
    print("\n=== Enigma Startup ===")
    _dt("main() start")
    _kill_zombies()
    _dt("zombie-kill done")
    
    backend_proc, llm_proc = _ensure_servers_running()
    _dt("servers ready")
    
    # Проверка наличия модели LLM перед стартом меню
    import importlib
    from pathlib import Path
    _enigma_settings = importlib.import_module("app.core.config").settings
    if not Path(_enigma_settings.llama_cpp_model_path).exists():
        print("  ⚠ Файл модели не найден! Открытие экрана скачивания...")
        screen, clock, menu = _init_menu_display()
        settings_screen = SettingsScreen(screen, clock)
        settings_screen.run(initial_tab="llm")
        # После закрытия настроек — продолжаем работу (бэкенд уже запущен)
    
    screen, clock, menu = _init_menu_display()
    _dt("menu display created — START-TO-MENU TOTAL")

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
    _dt("CDS observer init done")

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
                        # ADR-O-146: New Game = сброс runtime мира через шлюз.
                        # Быстрая страховка живости (не запуск!): backend поднят
                        # в _ensure_servers_running; здесь ловим только падение
                        # за время, пока игрок был в меню. Тишина = успех.
                        _backend_ok = _wait_backend_ready(5)
                        print(f"  [DIAG_LAUNCH] Backend OK: {_backend_ok}", flush=True)
                        
                        _reset_ok = False
                        if _backend_ok:
                            import os as _os
                            _os.environ.setdefault("ENIGMA_BACKEND_URL", _BACKEND_URL)
                            try:
                                from api_client import create_game_gateway
                                _gateway, _ = create_game_gateway(base_url=_BACKEND_URL)
                                
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
                            game_result = game_screen.run(selected_folder, selected_data["character_id"])
                            # Обработка паузы (ESC открывает настройки, затем продолжаем)
                            while game_result == "PAUSE":
                                screen = pygame.display.get_surface()
                                settings_screen = SettingsScreen(screen, clock)
                                settings_screen.run(initial_tab="graphics")
                                # Пересоздаём поверхность и продолжаем игру
                                screen = pygame.display.get_surface()
                                game_screen = GameScreen(screen, clock)
                                game_result = game_screen.run(selected_folder, selected_data["character_id"])
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
                            import os as _os
                            _os.environ.setdefault("ENIGMA_BACKEND_URL", _BACKEND_URL)
                            try:
                                from api_client import create_game_gateway
                                _gateway, _ = create_game_gateway(base_url=_BACKEND_URL)
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

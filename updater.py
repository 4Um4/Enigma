"""
path: /updater.py
Назначение: Автоматическая проверка обновлений на GitHub и запуск игры. Реализует ТЗ раздел 12.
Зависимости: os, sys, json, urllib.request, subprocess, tempfile, tkinter
Основные сущности: get_local_version, get_latest_release, download_file, main
"""

import os
import sys
import json
import urllib.request
import subprocess
import tempfile
import traceback
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter import font as tkfont

# --- КОНФИГУРАЦИЯ ---
GITHUB_OWNER = "4Um4"
GITHUB_REPO = "Enigma"
VERSION_FILE = "version.txt"

def get_app_dir():
    """Возвращает директорию, где находится Bloodloom.exe (или скрипт)"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.getcwd()

def get_local_version():
    app_dir = get_app_dir()
    version_path = os.path.join(app_dir, VERSION_FILE)
    if not os.path.exists(version_path):
        return "0.0.0.0"
    with open(version_path, "r", encoding="utf-8") as f:
        return f.read().strip().lower().replace("v", "").replace("\x00", "")

def get_latest_release():
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Bloodloom-Updater'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data
    except Exception as e:
        return None

def download_file_with_progress(url, dest, progress_cb=None):
    """Скачивание с реальным прогрессом (байты -> проценты), отменой и
    частичной записью на диск (не в память: файл ~1.4 ГБ).
    progress_cb(done_mb, total_mb, speed_mbs, eta_sec) — вызывается на каждом чанке.
    Возвращает: True | False (ошибка) | None (отменено пользователем)."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Bloodloom-Updater'})
        with urllib.request.urlopen(req, timeout=30) as response:
            total = int(response.headers.get('Content-Length', 0) or 0)
            import time as _t
            t0 = _t.time()
            done = 0
            with open(dest + '.part', 'wb') as out_file:
                while True:
                    if progress_cb and progress_cb.cancelled:
                        out_file.close()
                        try:
                            os.remove(dest + '.part')
                        except OSError:
                            pass
                        return None
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    done += len(chunk)
                    if progress_cb and total > 0:
                        elapsed = max(0.001, _t.time() - t0)
                        speed = done / (1024 * 1024) / elapsed
                        eta = (total - done) / (1024 * 1024) / speed if speed > 0 else 0
                        progress_cb(done // (1024 * 1024), total // (1024 * 1024), speed, eta)
        os.replace(dest + '.part', dest)
        return True
    except Exception:
        try:
            os.remove(dest + '.part')
        except OSError:
            pass
        return False

def main():
    app_dir = get_app_dir()
    # КРИТИЧЕСКИ ВАЖНО: меняем рабочую директорию на папку с игрой
    os.chdir(app_dir)

    local_ver = get_local_version()
    release = get_latest_release()
    
    if release:
        latest_ver = release.get('tag_name', '').lower().replace("v", "")
        if latest_ver and latest_ver != local_ver:
            root = tk.Tk()
            root.withdraw()
            release_notes = release.get('body', 'Ежедневное обновление раннего доступа.')
            answer = messagebox.askyesno(
                "Доступно обновление Bloodloom",
                f"Текущая версия: {local_ver}\nНовая версия: {latest_ver}\n\n{release_notes}\n\nСкачать и установить обновление сейчас?"
            )
            root.destroy()
            
            if answer:
                temp_dir = tempfile.gettempdir()
                assets = release.get('assets', [])
                
                main_setup_url = None
                
                for asset in assets:
                    # Фильтр: основной установщик = .exe (не models-ассет — их больше нет).
                    # .rar (легаси-сжатие >2ГБ релизов) обновлятор ставить не умеет —
                    # такие релизы считаются несовместимыми с автообновлением.
                    if asset['name'].endswith('.exe') and not asset['name'].startswith('Bloodloom_models'):
                        main_setup_url = asset['browser_download_url']
                
                # Раньше здесь была минута молчания: 1.4 ГБ качались в память без
                # единого окна (наблюдено Мастером: «нажал Да — ничего»). Теперь —
                # живое окно прогресса с байтами, скоростью, ETA и отменой.
                import threading
                import time as _time
                
                if not main_setup_url:
                    _err = tk.Tk(); _err.withdraw()
                    messagebox.showerror(
                        "Обновление недоступно",
                        "В последнем релизе нет подходящего файла установки (.exe).\n"
                        "Возможно, релиз опубликован архивом .rar. Скачайте его вручную\n"
                        "со страницы релизов GitHub.")
                    _err.destroy()
                    os._exit(1)
                
                main_path = os.path.join(temp_dir, "bloodloom_main_update.exe")
                
                win = tk.Tk()
                win.title("Обновление Bloodloom")
                win.geometry("480x220")
                win.resizable(False, False)
                win.configure(bg="#0F1419")
                try:
                    win.attributes("-topmost", True)
                except tk.TclError:
                    pass
                _cx = (win.winfo_screenwidth() // 2) - 240
                _cy = (win.winfo_screenheight() // 2) - 110
                win.geometry(f"480x220+{_cx}+{_cy}")
                
                _title_font = tkfont.Font(family="Segoe UI", size=14, weight="bold")
                _status_font = tkfont.Font(family="Segoe UI", size=11)
                tk.Label(win, text="Загрузка обновления Bloodloom", font=_title_font,
                         bg="#0F1419", fg="#00A887").pack(pady=(24, 8))
                
                _info = tk.Label(win, text="Подключение...", font=_status_font,
                                 bg="#0F1419", fg="#FFFFFF")
                _info.pack(pady=4)
                
                _bar = ttk.Progressbar(win, length=420, mode='determinate', maximum=100)
                _bar.pack(pady=12)
                
                _speed = tk.Label(win, text="", font=_status_font, bg="#0F1419", fg="#8FA3B0")
                _speed.pack()
                
                class _CB:
                    def __init__(self):
                        self.cancelled = False
                    def __call__(self, done_mb, total_mb, speed_mbs, eta_sec):
                        # Обновления UI — только через after(): download идёт в потоке
                        pct = int(done_mb * 100 / total_mb) if total_mb else 0
                        _eta = f"{int(eta_sec // 60)}м {int(eta_sec % 60)}с"
                        _info_text = f"Загружено {done_mb} из {total_mb} МБ ({pct}%)"
                        _speed_text = f"Скорость: {speed_mbs:.1f} МБ/с | Осталось: {_eta}"
                        win.after(0, lambda: (
                            _bar.configure(value=pct),
                            _info.configure(text=_info_text),
                            _speed.configure(text=_speed_text),
                        ))
                
                _cb = _CB()
                
                _btn = tk.Button(win, text="Отменить", command=lambda: setattr(_cb, 'cancelled', True),
                                 bg="#252530", fg="#FF6B6B", activebackground="#3a3a3a",
                                 relief="flat", padx=16, pady=4)
                _btn.pack(pady=10)
                
                _result = {}
                
                def _worker():
                    _result['ok'] = download_file_with_progress(main_setup_url, main_path, _cb)
                    win.after(0, win.quit)
                
                threading.Thread(target=_worker, daemon=True).start()
                win.mainloop()
                
                if _cb.cancelled or _result.get('ok') is None:
                    win.destroy()
                    _c = tk.Tk(); _c.withdraw()
                    messagebox.showinfo("Обновление отменено", "Загрузка отменена. Недокачанный файл удалён.\nЗапустите игру позже, чтобы повторить.")
                    _c.destroy()
                    os._exit(0)  # Отмена = не запускаем игру со старой версией молча
                
                win.destroy()
                
                if _result.get('ok') is True:
                    try:
                        # Установщик напрямую (без 'cmd /c start'): не всплывает чёрное
                        # окно, нет слоя кавычек. Дочерний переживает os._exit родителя.
                        _flags = 0x08000000 if sys.platform == 'win32' else 0
                        subprocess.Popen(
                            [main_path, '/VERYSILENT', '/SUPPRESSMSGBOXES',
                             '/NOCANCEL', '/NORESTART', '/CLOSEAPPLICATIONS'],
                            creationflags=_flags,
                        )
                        _s = tk.Tk(); _s.withdraw()
                        messagebox.showinfo(
                            "Обновление загружено",
                            "Установщик запущен. Игра обновится автоматически\n"
                            "и ярлык можно будет запустить снова через минуту.")
                        _s.destroy()
                        os._exit(0)
                    except Exception as _e:
                        _err = tk.Tk(); _err.withdraw()
                        messagebox.showerror("Ошибка запуска установщика", f"Установщик скачан, но не запустился:\n{_e}\n\nФайл: {main_path}")
                        _err.destroy()
                        os._exit(1)
                
                # Скачивание упало (сеть и т.п.)
                _err = tk.Tk(); _err.withdraw()
                messagebox.showerror(
                    "Ошибка загрузки",
                    "Не удалось скачать обновление (проблема сети или GitHub).\n"
                    "Проверьте соединение и запустите игру снова — загрузка начнётся заново.")
                _err.destroy()
                os._exit(1)
                
                # Блок доставки моделей удалён: недостижим (os._exit выше) и устарел —
                # models_setup-ассеты больше не публикуются, модель доставляет
                # внутриигровой загрузчик (Настройки -> LLM Модели, докачка/отмена).

    # ЗАПУСК ИГРЫ
    launcher_path = os.path.join(app_dir, "game_launcher.pyc")
    if not os.path.exists(launcher_path):
        launcher_path = os.path.join(app_dir, "game_launcher.py") # Фоллбэк для разработки
    if os.path.exists(launcher_path):
        # Ищем портативный Python в _internal/python/ (согласно Дополнению А, п. А.2)
        portable_python = os.path.join(app_dir, "_internal", "python", "python.exe")
        # Фолбэк на .venv для разработки
        venv_python = os.path.join(app_dir, ".venv", "Scripts", "python.exe")
        
        if os.path.exists(portable_python):
            python_exe = portable_python
        elif os.path.exists(venv_python):
            python_exe = venv_python
        else:
            python_exe = "python" # Системный Python (последняя попытка)
        
        _creation_flags = 0
        if sys.platform == 'win32':
            _creation_flags = 0x08000000 # CREATE_NO_WINDOW
            
        try:
            _env = os.environ.copy()
            _env["PYTHONIOENCODING"] = "utf-8"
            _env["PYTHONUTF8"] = "1"
            
            # Запускаем Splash Screen в фоне (если он существует)
            splash_exe = os.path.join(app_dir, "Bloodloom_splash.exe")
            if os.path.exists(splash_exe):
                subprocess.Popen([splash_exe])
                
            subprocess.Popen([python_exe, launcher_path], creationflags=_creation_flags, env=_env)
        except Exception as e:
            with open(os.path.join(app_dir, "launch_error.log"), "w", encoding="utf-8") as f:
                f.write(f"Не удалось запустить python.exe. Ошибка: {e}\n")
                f.write(f"Искал портативный в: {portable_python}\n")
                f.write(f"Искал venv в: {venv_python}\n")
    else:
        with open(os.path.join(app_dir, "launch_error.log"), "w", encoding="utf-8") as f:
            f.write(f"Файл game_launcher.py не найден в {app_dir}\n")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Ловим любые другие ошибки, чтобы они не остались незамеченными
        app_dir = get_app_dir()
        with open(os.path.join(app_dir, "updater_crash.log"), "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
    finally:
        # Принудительно убиваем процесс обновлятора, чтобы не было зомби
        import os
        os._exit(0)
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
from tkinter import messagebox

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

def download_file(url, dest):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Bloodloom-Updater'})
        with urllib.request.urlopen(req, timeout=60) as response:
            with open(dest, 'wb') as out_file:
                out_file.write(response.read())
        return True
    except Exception as e:
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
                setup_exe_url = None
                bin_urls = []
                for asset in assets:
                    if asset['name'].endswith('.exe'):
                        setup_exe_url = asset['browser_download_url']
                    elif asset['name'].endswith('.bin'):
                        bin_urls.append(asset['browser_download_url'])
                
                if setup_exe_url:
                    setup_path = os.path.join(temp_dir, "bloodloom_setup_update.exe")
                    if download_file(setup_exe_url, setup_path):
                        all_downloaded = True
                        for i, bin_url in enumerate(bin_urls, 1):
                            bin_path = os.path.join(temp_dir, f"bloodloom_setup_update-{i}.bin")
                            if not download_file(bin_url, bin_path):
                                all_downloaded = False
                                break
                        if all_downloaded:
                            try:
                                subprocess.run([setup_path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NOCANCEL", "/NORESTART"], check=True)
                            except Exception:
                                pass

    # ЗАПУСК ИГРЫ
    launcher_path = os.path.join(app_dir, "game_launcher.py")
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
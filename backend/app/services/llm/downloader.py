"""
Менеджер скачивания LLM-моделей.
Позволяет проверять наличие моделей, инициировать загрузку и трекать прогресс.
"""
import json
import logging
import urllib.request
from pathlib import Path
from typing import Dict

from app.core.config import BASE_DIR

logger = logging.getLogger(__name__)

LLM_SOURCES_FILE = BASE_DIR / "config" / "llm_sources.json"

# Глобальное хранилище прогресса скачивания (key -> percentage)
_DOWNLOAD_STATUS: Dict[str, float] = {}
_DOWNLOAD_ERRORS: Dict[str, str] = {}
_DOWNLOAD_CANCEL: Dict[str, bool] = {}
_REMOTE_SIZE_CACHE: Dict[str, int] = {}
_REMOTE_SIZE_CACHE_TIME: Dict[str, float] = {}

_VRAM_CACHE: int = 0

def _init_vram_cache():
    """Фоновая инициализация кэша VRAM, чтобы не блокировать первый запрос."""
    global _VRAM_CACHE
    _VRAM_CACHE = _get_vram_mb()

def _get_vram_mb() -> int:
    """Получает объём видеопамяти в МБ (кэшируется при первом вызове)."""
    global _VRAM_CACHE
    if _VRAM_CACHE > 0:
        return _VRAM_CACHE

    import subprocess
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            _VRAM_CACHE = int(result.stdout.strip().split("\n")[0])
            return _VRAM_CACHE
    except Exception as e:
        # nvidia-smi отсутствует/недоступен — легальная деградация до VRAM=0,
        # но отказ обязан быть наблюдаемым (L4 / ADR-O-308, INV-SILENT-FAILURE)
        logger.debug(f"[LLM-VRAM] nvidia-smi недоступен, VRAM=0: {e}")
    return 0

def _get_remote_size(url: str, key: str) -> int:
    """Определяет размер файла через HF Tree API (JSON, без CDN-редиректов).
    Кэширует результат на 5 минут. PowerShell-HEAD работал, а urllib-HEAD — нет:
    CDN HuggingFace по-разному отвечает им; Tree API даёт размеры надёжно."""
    import json as _json
    import time
    _now = time.time()
    if key in _REMOTE_SIZE_CACHE and _now - _REMOTE_SIZE_CACHE_TIME.get(key, 0) < 300:
        return _REMOTE_SIZE_CACHE[key]
    try:
        # URL вида https://huggingface.co/{repo}/resolve/{rev}/{filename}
        _parts = url.split("/")
        _idx = _parts.index("resolve")
        _repo = "/".join(_parts[_idx - 2:_idx])
        _fname = "/".join(_parts[_idx + 2:])
        _api_url = f"https://huggingface.co/api/models/{_repo}/tree/main"
        _headers = {"User-Agent": "Bloodloom/0.5.3"}
        # Gated-репозитории (PygmalionAI, IlyaGusev) отдают 401 без токена.
        # Токен берём из окружения — тот же, что и для скачивания.
        import os as _os
        _hf_token = _os.environ.get("HF_TOKEN", "")
        if _hf_token:
            _headers["Authorization"] = f"Bearer {_hf_token}"
        _req = urllib.request.Request(_api_url, headers=_headers)
        with urllib.request.urlopen(_req, timeout=10) as _resp:
            _files = _json.loads(_resp.read().decode("utf-8"))
        # Сплит-файлы (Qwen2.5-14B): HF режет большие GGUF на части
        # {base}-0000N-of-0000M.gguf. Размер модели = сумма всех частей.
        if "-of-" in _fname:
            _base_prefix = _fname[: -len(".gguf")].rsplit("-", 3)[0] + "-"
            _total = 0
            _found = 0
            for _f in _files:
                _p = _f.get("path", "")
                if _p.startswith(_base_prefix) and "-of-" in _p and _p.endswith(".gguf"):
                    _total += int(_f.get("size", 0) or 0)
                    _found += 1
            if _found > 0 and _total > 0:
                _REMOTE_SIZE_CACHE[key] = _total
                _REMOTE_SIZE_CACHE_TIME[key] = _now
                return _total
            print(f"[REMOTE_SIZE] split parts not in tree: key={key} fname={_fname}")
            return 0
        for _f in _files:
            if _f.get("path") == _fname:
                _size = int(_f.get("size", 0) or 0)
                if _size > 0:
                    _REMOTE_SIZE_CACHE[key] = _size
                    _REMOTE_SIZE_CACHE_TIME[key] = _now
                    return _size
        print(f"[REMOTE_SIZE] file not in tree: key={key} fname={_fname}")
    except Exception as _e:
        print(f"[REMOTE_SIZE] tree api fail: key={key} err={_e}")
    return 0
    """Делает HEAD запрос для получения размера файла. Кэширует на 5 минут."""
    import time
    _now = time.time()
    if key in _REMOTE_SIZE_CACHE and _now - _REMOTE_SIZE_CACHE_TIME.get(key, 0) < 300:
        return _REMOTE_SIZE_CACHE[key]
    try:
        _req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Bloodloom/0.5.3"})
        with urllib.request.urlopen(_req, timeout=5) as _resp:
            _size = int(_resp.headers.get("Content-Length", 0) or 0)
            if _size <= 0:
                _size = int(_resp.headers.get("x-linked-size", 0) or 0)
            if _size > 0:
                _REMOTE_SIZE_CACHE[key] = _size
                _REMOTE_SIZE_CACHE_TIME[key] = _now
                return _size
    except Exception as e:
        # HEAD-проба не удалась (CDN/сеть) — наблюдаемо, управление уходит в Range-fallback (L4)
        logger.debug(f"[LLM-SIZE] HEAD-проба не удалась, Range-fallback: {url}: {e}")
    # Fallback: запрос 1 байта через Range — полный размер в Content-Range ("bytes 0-0/4683073920")
    try:
        _req = urllib.request.Request(url, headers={"User-Agent": "Bloodloom/0.5.3", "Range": "bytes=0-0"})
        with urllib.request.urlopen(_req, timeout=5) as _resp:
            _cr = _resp.headers.get("Content-Range", "")
            if "/" in _cr:
                _size = int(_cr.split("/")[-1])
                _REMOTE_SIZE_CACHE[key] = _size
                _REMOTE_SIZE_CACHE_TIME[key] = _now
                return _size
    except Exception as e:
        # Обе пробы размера не дали результат — размер UNKNOWN (0), отказ наблюдаем (L4);
        # «скачано» на пустом/битом файле останется невозможным: валидация требует размер >1 МБ
        logger.debug(f"[LLM-SIZE] размер не определён (HEAD и Range не удались): {url}: {e}")
    return 0

def _update_remote_sizes_once() -> None:
    """Один проход по всем моделям: определяет размеры на сервере.
    Печатает результат для диагностики (ЧАСТЬ VIII.5: print, не logger)."""
    sources = get_llm_sources()
    for key, info in sources.items():
        _url = info.get("url", "")
        if not _url:
            continue
        # _get_remote_size сам пропускает свежий кэш (< 300 сек),
        # поэтому ретраятся только модели с неизвестным размером
        _size = _get_remote_size(_url, key)
        if _size > 0:
            print(f"[REMOTE_SIZE] OK key={key} size_mb={int(_size / 1024 / 1024)}")
        else:
            print(f"[REMOTE_SIZE] FAIL key={key} url={_url}")

def _remote_sizes_worker() -> None:
    """Периодический воркер: обновляет размеры каждые 60 сек, живёт вечно.
    Одна битая модель не прерывает цикл (тихий отказ запрещён)."""
    import time as _time
    while True:
        try:
            _update_remote_sizes_once()
        except Exception as _e:
            print(f"[REMOTE_SIZE] worker iteration failed: {_e}")
        _time.sleep(60)

# Ленивый запуск воркеров: при импорте ПОРОЖДАТЬ потоки нельзя — модуль ещё
# не доисполнен, get_llm_sources ниже по файлу ещё не определена (NameError
# в первой итерации воркера, наблюдаемо в smoke-тесте). Стартуем из
# get_model_status() — она вызывается только после полного импорта модуля.
import threading

_WORKERS_STARTED = False

def _ensure_background_workers() -> None:
    """Идемпотентный запуск воркеров размеров и VRAM (ровно один раз)."""
    global _WORKERS_STARTED
    if _WORKERS_STARTED:
        return
    _WORKERS_STARTED = True
    threading.Thread(target=_remote_sizes_worker, daemon=True).start()
    threading.Thread(target=_init_vram_cache, daemon=True).start()

def get_llm_sources() -> Dict:
    """Читает конфигурацию источников LLM."""
    if not LLM_SOURCES_FILE.exists():
        return {}
    try:
        with open(LLM_SOURCES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка чтения {LLM_SOURCES_FILE}: {e}")
        return {}

def get_model_status() -> Dict:
    """Возвращает статус: скачаны ли требуемые модели, прогресс и ошибки. + Сканирует ручные модели."""
    from app.core.config import settings
    _ensure_background_workers()  # ленивый старт: модуль гарантированно загружен целиком

    sources = get_llm_sources()
    status = {}
    _active_path = Path(settings.llama_cpp_model_path)
    _vram_mb = _get_vram_mb()
    _vram_80_limit = _vram_mb * 0.8 if _vram_mb > 0 else 0

    for key, info in sources.items():
        _t_path = info["target_path"].replace("\\", "/")
        target = (BASE_DIR / _t_path).resolve()
        url = info.get("url", "")
        progress = _DOWNLOAD_STATUS.get(key)
        is_downloading = progress is not None and progress >= 0
        is_error = progress is not None and progress < 0

        # Сплит-модели: file_size = сумма всех частей, существование = все части на диске
        _split_parts = int(info.get("split_parts", 1) or 1)
        if _split_parts > 1:
            _tname = target.name
            _part_paths = [
                target.parent / _tname.replace(
                    f"-00001-of-{_split_parts:05d}.gguf",
                    f"-{_i:05d}-of-{_split_parts:05d}.gguf",
                )
                for _i in range(1, _split_parts + 1)
            ]
            _file_exists = all(_p.exists() for _p in _part_paths)
            _file_size = sum(_p.stat().st_size for _p in _part_paths if _p.exists())
        else:
            _file_exists = target.exists()
            _file_size = target.stat().st_size if _file_exists else 0
        _remote_size = _REMOTE_SIZE_CACHE.get(key, 0)  # Читаем из кэша, обновляемого в фоне

        # Файл считается валидным, только если мы знаем его размер на сервере и он совпадает
        # Для ручных моделей (без URL) — просто больше 1 МБ
        if url:
            # Если знаем remote_size, проверяем целостность. Если нет - верим, что файл целый, если он больше 1 МБ
            _file_valid = (
                (_remote_size > 0 and _file_size >= _remote_size * 0.99)
                or (_remote_size == 0 and _file_size > 1024 * 1024)
            ) and (_split_parts <= 1 or _file_exists)
        else:
            _file_valid = _file_size > 1024 * 1024

        _r_size_mb = int(_remote_size / 1024 / 1024)
        status[key] = {
            "display_name": info.get("display_name", key),
            "target_path": str(target),  # Добавлено для фильтра дубликатов
            "is_downloaded": _file_valid and not is_downloading,
            "is_active": target == _active_path,
            "file_size_mb": int(_file_size / 1024 / 1024),
            "remote_size_mb": _r_size_mb,
            "required": info.get("required", False),
            "is_downloading": is_downloading,
            "progress": progress if progress is not None and progress >= 0 else 0.0,
            "error": is_error,
            "error_message": _DOWNLOAD_ERRORS.get(key, "Неизвестная ошибка") if is_error else "",
            "manual": False,
            "gated": info.get("gated", False),
            "recommended": _vram_80_limit > 0 and _r_size_mb > 0 and _r_size_mb <= _vram_80_limit
        }

    # Собираем пути файлов, которые уже есть в статусе, чтобы не дублировать
    _existing_files = {Path(v.get("target_path", "")).name.lower() for v in status.values() if isinstance(v, dict)}

    # Сканируем папку Models LLM на наличие ручных .gguf файлов
    _llm_dir = BASE_DIR / "Models LLM"
    if _llm_dir.exists():
        for _f in _llm_dir.glob("*.gguf"):
            if _f.name.lower() in _existing_files:
                continue  # Файл уже есть в списке, пропускаем
            if "-of-" in _f.stem:
                continue  # Сплит-часть большой модели — не самостоятельная модель

            _key = _f.stem
            _file_size = _f.stat().st_size
            _manual_valid = _file_size > 1024 * 1024  # Больше 1 МБ
            status[_key] = {
                "display_name": _f.name,
                "is_downloaded": _manual_valid,
                "is_active": _f == _active_path,
                "file_size_mb": int(_file_size / 1024 / 1024),
                "remote_size_mb": 0,
                "required": False,
                "is_downloading": False,
                "progress": 100.0 if _manual_valid else 0.0,
                "error": False,
                "manual": True
            }
    return status

def _reporthook(block_num: int, block_size: int, total_size: int, model_key: str):
    """Callback для urllib.urlretrieve для вычисления процентов."""
    if total_size > 0:
        downloaded = block_num * block_size
        progress = min(100.0, (downloaded / total_size) * 100.0)
        _DOWNLOAD_STATUS[model_key] = round(progress, 1)

def _download_split_model(model_key: str, info: dict, target_path, url: str, parts: int, force: bool) -> bool:
    """Скачивает все части сплит-модели (HF-канон {base}-0000N-of-0000M.gguf).
    Общий прогресс — по суммарным байтам. llama-server грузит сплиты нативно:
    в -m передаётся первая часть, остальные подхватываются из той же папки."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    _DOWNLOAD_STATUS[model_key] = 0.0
    _DOWNLOAD_CANCEL[model_key] = False
    _tname = target_path.name
    _first_suffix = f"-00001-of-{parts:05d}.gguf"
    _total_size = 0
    _done_bytes = 0
    _cur_part = None  # часть, качающаяся сейчас — удаляется при отмене

    try:
        import os as _os
        _hf_token = _os.environ.get("HF_TOKEN", "")
        for _i in range(1, parts + 1):
            _suffix = f"-{_i:05d}-of-{parts:05d}.gguf"
            _cur_part = target_path.parent / _tname.replace(_first_suffix, _suffix)
            _part_url = url.replace(_first_suffix, _suffix)
            if force and _cur_part.exists():
                _cur_part.unlink(missing_ok=True)

            _existing = _cur_part.stat().st_size if _cur_part.exists() else 0
            _headers = {"User-Agent": "Bloodloom/0.5.3"}
            if _existing > 0:
                _headers["Range"] = f"bytes={_existing}-"
            if _hf_token:
                _headers["Authorization"] = f"Bearer {_hf_token}"

            _req = urllib.request.Request(_part_url, headers=_headers)
            with urllib.request.urlopen(_req, timeout=30) as _resp:
                _clen = int(_resp.info().get("Content-Length", 0) or 0)
                if _existing > 0 and _resp.status == 206:
                    _clen += _existing
                elif _existing > 0 and _resp.status == 200:
                    _existing = 0
                    _cur_part.unlink(missing_ok=True)
                _total_size += _clen
                _done_bytes += _existing
                with open(_cur_part, "ab" if _existing > 0 else "wb") as _f:
                    while True:
                        if _DOWNLOAD_CANCEL.get(model_key, False):
                            raise RuntimeError("cancelled")
                        _chunk = _resp.read(65536)
                        if not _chunk:
                            break
                        _f.write(_chunk)
                        _done_bytes += len(_chunk)
                        if _total_size > 0:
                            _DOWNLOAD_STATUS[model_key] = round(
                                min(100.0, _done_bytes / _total_size * 100.0), 1
                            )
        if model_key in _DOWNLOAD_STATUS:
            del _DOWNLOAD_STATUS[model_key]
        logger.info(f"Модель '{model_key}' ({parts} частей) скачана в {target_path.parent}")
        return True
    except RuntimeError:
        # Отмена: недокачанная часть удаляется, целые части остаются (докачка)
        if _cur_part is not None and _cur_part.exists():
            _cur_part.unlink(missing_ok=True)
        _DOWNLOAD_STATUS[model_key] = -1.0
        _DOWNLOAD_ERRORS[model_key] = "Скачивание отменено пользователем"
        _DOWNLOAD_CANCEL[model_key] = False
        return False
    except urllib.error.HTTPError as _http_err:
        _msg = ("Модель закрыта лицензией (401). Требуется HF_TOKEN или ручное скачивание."
                if _http_err.code == 401 else f"HTTP ошибка {_http_err.code}")
        _DOWNLOAD_STATUS[model_key] = -1.0
        _DOWNLOAD_ERRORS[model_key] = _msg
        return False
    except Exception as _e:
        logger.error(f"Ошибка скачивания модели '{model_key}': {_e}")
        _DOWNLOAD_STATUS[model_key] = -1.0
        _DOWNLOAD_ERRORS[model_key] = str(_e)
        return False

def download_model(model_key: str, force: bool = False) -> bool:
    """Скачивает модель по ключу из llm_sources.json. Если force=True — удаляет старый файл."""
    sources = get_llm_sources()
    if model_key not in sources:
        logger.error(f"Модель '{model_key}' не найдена в конфигурации.")
        return False

    info = sources[model_key]
    target_path = BASE_DIR / info["target_path"]
    url = info["url"]

    # Сплит-модели (Qwen2.5-14B): скачиваем все части отдельным путём
    _split_parts = int(info.get("split_parts", 1) or 1)
    if _split_parts > 1:
        return _download_split_model(model_key, info, target_path, url, _split_parts, force)

    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Удаляем старый файл, если включён force или если он слишком мал (повреждён)
    if target_path.exists() and (force or target_path.stat().st_size < 1024 * 1024):
        target_path.unlink(missing_ok=True)
        _DOWNLOAD_STATUS[model_key] = 0.0  # Сбрасываем прогресс

    logger.info(f"Начало скачивания модели '{model_key}' из {url}...")
    _DOWNLOAD_STATUS[model_key] = 0.0

    try:
        _existing_size = target_path.stat().st_size if target_path.exists() else 0
        _headers = {"User-Agent": "Bloodloom/0.5.3"}
        if _existing_size > 0:
            _headers["Range"] = f"bytes={_existing_size}-"

        # Поддержка HF_TOKEN для лицензионных моделей (gemma и т.п.)
        import os as _os
        _hf_token = _os.environ.get("HF_TOKEN", "")
        if _hf_token:
            _headers["Authorization"] = f"Bearer {_hf_token}"

        _req = urllib.request.Request(url, headers=_headers)
        with urllib.request.urlopen(_req, timeout=30) as _response:
            _total_size = int(_response.info().get('Content-Length', 0))
            if _existing_size > 0 and _response.status == 206:  # 206 Partial Content — докачка поддерживается
                _total_size += _existing_size
            elif _existing_size > 0 and _response.status == 200:  # Сервер не поддерживает докачку — начинаем сначала
                _existing_size = 0
                target_path.unlink(missing_ok=True)

            _cancelled = False
            with open(target_path, 'ab' if _existing_size > 0 else 'wb') as _f:
                _downloaded = _existing_size
                while True:
                    if _DOWNLOAD_CANCEL.get(model_key, False):
                        _cancelled = True
                        break
                    _chunk = _response.read(8192)
                    if not _chunk:
                        break
                    _f.write(_chunk)
                    _downloaded += len(_chunk)
                    if _total_size > 0:
                        _progress = min(100.0, (_downloaded / _total_size) * 100.0)
                        _DOWNLOAD_STATUS[model_key] = round(_progress, 1)

        if _cancelled:
            # Отмена: удаляем недокачанный файл, фиксируем ошибку для UI
            target_path.unlink(missing_ok=True)
            _DOWNLOAD_STATUS[model_key] = -1.0
            _DOWNLOAD_ERRORS[model_key] = "Скачивание отменено пользователем"
            _DOWNLOAD_CANCEL[model_key] = False
            logger.info(f"Скачивание модели '{model_key}' отменено пользователем")
            return False

        logger.info(f"Модель '{model_key}' успешно скачана в {target_path}")
        if model_key in _DOWNLOAD_STATUS:
            del _DOWNLOAD_STATUS[model_key]
        return True
    except urllib.error.HTTPError as _http_err:
        if _http_err.code == 401:
            _msg = ("Модель закрыта лицензией (401). Зайдите на huggingface.co, "
                    "войдите в аккаунт и примите лицензию. Затем скачайте вручную "
                    "в папку Models LLM или задайте переменную окружения HF_TOKEN.")
        else:
            _msg = f"HTTP ошибка {_http_err.code}"
        logger.error(f"Ошибка скачивания модели '{model_key}': {_msg}")
        _DOWNLOAD_STATUS[model_key] = -1.0
        _DOWNLOAD_ERRORS[model_key] = _msg
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка скачивания модели '{model_key}': {e}")
        _DOWNLOAD_STATUS[model_key] = -1.0
        _DOWNLOAD_ERRORS[model_key] = str(e)
        return False

def cancel_download(model_key: str) -> bool:
    """Запрашивает отмену активного скачивания. Файл удалит цикл загрузки."""
    _progress = _DOWNLOAD_STATUS.get(model_key)
    if _progress is not None and _progress >= 0:
        _DOWNLOAD_CANCEL[model_key] = True
        return True
    return False

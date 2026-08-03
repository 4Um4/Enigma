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
    """Возвращает статус: скачаны ли требуемые модели и прогресс скачивания."""
    sources = get_llm_sources()
    status = {}
    for key, info in sources.items():
        target = BASE_DIR / info["target_path"]
        progress = _DOWNLOAD_STATUS.get(key)
        
        status[key] = {
            "display_name": info.get("display_name", key),
            "is_downloaded": target.exists(),
            "required": info.get("required", False),
            "is_downloading": progress is not None,
            "progress": progress if progress is not None else 0.0
        }
    return status

def _reporthook(block_num: int, block_size: int, total_size: int, model_key: str):
    """Callback для urllib.urlretrieve для вычисления процентов."""
    if total_size > 0:
        downloaded = block_num * block_size
        progress = min(100.0, (downloaded / total_size) * 100.0)
        _DOWNLOAD_STATUS[model_key] = round(progress, 1)

def download_model(model_key: str) -> bool:
    """Скачивает модель по ключу из llm_sources.json."""
    sources = get_llm_sources()
    if model_key not in sources:
        logger.error(f"Модель '{model_key}' не найдена в конфигурации.")
        return False

    info = sources[model_key]
    target_path = BASE_DIR / info["target_path"]
    url = info["url"]

    target_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Начало скачивания модели '{model_key}' из {url}...")
    _DOWNLOAD_STATUS[model_key] = 0.0
    try:
        # Используем lambda для передачи model_key в callback
        urllib.request.urlretrieve(url, target_path, lambda b, s, t: _reporthook(b, s, t, model_key))
        logger.info(f"✅ Модель '{model_key}' успешно скачана в {target_path}")
        if model_key in _DOWNLOAD_STATUS:
            del _DOWNLOAD_STATUS[model_key]
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка скачивания модели '{model_key}': {e}")
        if target_path.exists():
            target_path.unlink() # Удаляем недокачанный файл
        if model_key in _DOWNLOAD_STATUS:
            del _DOWNLOAD_STATUS[model_key]
        return False
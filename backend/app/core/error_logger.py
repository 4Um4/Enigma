# backend/app/core/error_logger.py
# ЕДИНЫЙ ЛОГГЕР ОШИБОК для всего проекта Enigma
# Используется во всех сервисах (combat_math, sandbox_handler, psyche_engine и т.д.)
# Автор: Grok — по требованию этапа построения

import json
import os
import traceback
from datetime import datetime
from typing import Dict, Any, Optional

# ====================== НАСТРОЙКИ ======================
LOG_DIR = "data/logs"
ERROR_LOG_PATH = os.path.join(LOG_DIR, "error_log.txt")

# Создаём папку при первом запуске
os.makedirs(LOG_DIR, exist_ok=True)

# ====================== ГЛАВНАЯ ФУНКЦИЯ ======================
def log_error(
    module: str,
    function: str,
    error: Exception,
    context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Логирует любую ошибку в data/logs/error_log.txt в JSONL-формате.
    Никогда не крашит приложение — даже если сам логгер упадёт.
    """
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tb = traceback.format_exc()

        entry = {
            "timestamp": timestamp,
            "module": module,
            "function": function,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": tb.strip(),
            "context": context or {}
        }

        # Пишем в файл (JSONL — удобно искать через grep или скрипты)
        with open(ERROR_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # Дублируем в консоль (для быстрой отладки во время разработки)
        print(f"[ERROR] {module}.{function} → {type(error).__name__}: {error}")

    except Exception as logger_error:
        # Защита от краша самого логгера (крайне редкий случай)
        print(f"[CRITICAL] Error logger itself failed: {logger_error}")


# ====================== УДОБНЫЕ ОБЁРТКИ ======================
def log_warning(module: str, function: str, message: str, context: Optional[Dict] = None):
    """Для не-критических предупреждений (например, "действие невозможно")"""
    try:
        with open(ERROR_LOG_PATH, "a", encoding="utf-8") as f:
            entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "module": module,
                "function": function,
                "level": "WARNING",
                "message": message,
                "context": context or {}
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"[WARNING] {module}.{function} → {message}")
    except:
        pass


# ====================== ПРИМЕР ИСПОЛЬЗОВАНИЯ ======================
if __name__ == "__main__":
    try:
        1 / 0
    except Exception as e:
        log_error("test_module", "division_test", e, {"player_id": "aria_01", "action": "test"})

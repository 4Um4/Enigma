# C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\log_gate.py
# -*- coding: utf-8 -*-
"""
path: /backend/app/core/log_gate.py

Назначение: Центральный гейт записи runtime-логов в файлы (§15.2 Logging/telemetry).
Позволяет полностью отключить файловую запись логов (scene_changes.jsonl,
enigma_audit.jsonl, combat_log.jsonl, enigma_YYYYMMDD.jsonl) без отключения
самих подсистем. Основной сценарий — запуск тестов из git-хуков (.githooks/pre-push):
тесты выполняются как обычно, но не трогают файлы в backend/data/logs.

Использование:
    ENIGMA_DISABLE_FILE_LOGS=1 python -m pytest ...   # файловые логи молчат

Зависимости: os
Основные сущности: file_logs_enabled(), FILE_LOGS_ENV_VAR
"""

import os

FILE_LOGS_ENV_VAR = "ENIGMA_DISABLE_FILE_LOGS"

_TRUTHY = ("1", "true", "yes", "on")


def file_logs_enabled() -> bool:
    """True — запись runtime-логов в файлы разрешена.

    False — установлена переменная окружения ENIGMA_DISABLE_FILE_LOGS
    со значением 1/true/yes/on (регистронезависимо): все файловые логгеры
    обязаны пропустить запись (в памяти/через logging можно продолжать).
    """
    return os.environ.get(FILE_LOGS_ENV_VAR, "").strip().lower() not in _TRUTHY

r"""path: /project/scripts/det_holder.py

Назначение: держатель тёплого llama-server для M2-замеров DEBT-INFERENCE-NONDET
    (матрица M1/M2/M3, вердикт Мастера). Спавнит сервер через llm_server_manager
    и спит 2 часа — corpus-прогоны REUSE-ят инстанс (их atexit убивает только
    собственных детей). Пульс для наблюдателя — порт 8181 в LISTEN.
    Teardown — извне: Stop-Process держателя + сервер по PID порта.
Зависимости: scripts/llm_server_manager.py (сам вставляет backend в sys.path)
Основные сущности: нет — чистый сценарный скрипт.

Запуск: Start-Process -FilePath "python" -ArgumentList "scripts\det_holder.py" -RedirectStandardOutput reports\det_m2_holder.txt -RedirectStandardError reports\det_m2_holder_err.txt -WindowStyle Hidden
"""

import sys
import time
from pathlib import Path

# Этап 4.1.11: migrated to Host broker SDK. Принцип Мастера: идентификация ≠ владение.
# det_holder — lease holder (not server spawner). Host broker owns lifecycle.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "backend"))

from app.services.llm.runtime.client import ensure_llm


def main() -> None:
    ensure_llm(label="det_holder")
    time.sleep(7200)


if __name__ == "__main__":
    main()
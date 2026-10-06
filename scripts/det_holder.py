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

import time

# sys.path[0] при запуске "python scripts\det_holder.py" = папка scripts/ —
# менеджер импортируется напрямую (никаких python -c: PS5 Start-Process
# не квотит аргументы с пробелами — обе попытки через -c погибли на этом)
from llm_server_manager import start_llama_server


def main() -> None:
    start_llama_server()
    time.sleep(7200)


if __name__ == "__main__":
    main()
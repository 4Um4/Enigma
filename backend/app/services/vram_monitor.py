"""
path: /project/backend/app/services/vram_monitor.py
Назначение: Заглушка для VRAM-мониторинга (удалён в S142, но импорт остался).
Зависимости: Нет.
Основные сущности: VramMonitor, get_vram_monitor
"""
import logging

logger = logging.getLogger(__name__)

class VramMonitor:
    """Пассивный монитор VRAM (заглушка)."""
    async def start_session(self) -> None:
        """Инициализация сессии мониторинга (заглушка)."""
        pass

    async def get_vram_mb(self) -> int:
        return 0

    async def get_dashboard(self) -> dict:
        return {"vram_used": 0, "vram_total": 0}

    def get_status(self) -> dict:
        return {"vram_used": 0, "vram_total": 0}

_vram_monitor_instance: VramMonitor | None = None

def get_vram_monitor() -> VramMonitor:
    """Возвращает синглтон VramMonitor."""
    global _vram_monitor_instance
    if _vram_monitor_instance is None:
        _vram_monitor_instance = VramMonitor()
    return _vram_monitor_instance
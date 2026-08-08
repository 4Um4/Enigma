# backend/app/services/probes/probe_alerts.py
"""
Подсистема 3: Агрегатор результатов проб для Dashboard и алертов (Этап 3.6).
Хранит последние 100 результатов в памяти. Singleton.
"""
import logging
from collections import deque
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class ProbeAlertManager:
    """In-memory singleton для хранения истории проб."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._history = deque(maxlen=100)
            cls._instance._violations = {}
        return cls._instance

    def record_results(self, tick_id: int, results: List[Any]) -> None:
        """Записывает результаты проб одного тика."""
        _tick_summary = {
            "tick_id": tick_id,
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "errors": [r.details for r in results if not r.passed and r.severity == "ERROR"],
            "warnings": [r.details for r in results if not r.passed and r.severity == "WARN"]
        }
        self._history.append(_tick_summary)
        
        # Считаем топ нарушителей
        for r in results:
            if not r.passed:
                self._violations[r.name] = self._violations.get(r.name, 0) + 1

    def get_dashboard(self) -> Dict[str, Any]:
        """Возвращает данные для /api/probes/dashboard."""
        _history_list = list(self._history)
        _total_ticks = len(_history_list)
        _total_errors = sum(t["failed"] for t in _history_list)
        
        # Топ-5 нарушителей
        _top_violators = sorted(self._violations.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            "total_ticks_recorded": _total_ticks,
            "total_failed_probes": _total_errors,
            "top_violators": [{"name": v[0], "count": v[1]} for v in _top_violators],
            "recent_history": _history_list[-10:]  # Последние 10 тиков
        }

# Глобальный экземпляр
probe_alerts = ProbeAlertManager()
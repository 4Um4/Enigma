"""
frontend/spatial_compilation_gateway.py
Назначение: Тонкий stateless вход для всех потребителей
Зависимости: spatial_compilation_orchestrator.py
Основные сущности: SpatialCompilationGateway

Gateway не содержит логики. Только перенаправляет вызовы к Orchestrator.
UI / Backend / CI / Future NPC — все проходят через эту точку.
Не является god-object — не владеет миром, не принимает решений.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Глобальный singleton orchestrator (ленивая инициализация)
_orchestrator = None


def _get_orchestrator():
    """Ленивая инициализация orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        from spatial_compilation_orchestrator import SpatialCompilationOrchestrator

        _orchestrator = SpatialCompilationOrchestrator()
    return _orchestrator


class SpatialCompilationGateway:
    """Тонкий stateless вход для компиляции мира.

    Все потребители (Editor, Backend, CI, NPC) вызывают только этот класс.
    Gateway не содержит логики — только forward к Orchestrator.

    Методы — статические, не требуют экземпляра.
    """

    @staticmethod
    def request_rebuild(campaign_id: str) -> bool:
        """Запросить перестроение реестра если устарел.
        Editor / Backend / CI вызывают это после изменения локации."""
        try:
            return _get_orchestrator().rebuild_if_needed(campaign_id)
        except Exception as e:
            logger.warning(f"[GATEWAY] Ошибка request_rebuild: {e}")
            return False

    @staticmethod
    def force_rebuild(campaign_id: str):
        """Принудительная компиляция. Для CI / headless."""
        try:
            return _get_orchestrator().rebuild(campaign_id)
        except Exception as e:
            logger.warning(f"[GATEWAY] Ошибка force_rebuild: {e}")
            return None

    @staticmethod
    def get_registry(campaign_id: str):
        """Загрузить SpatialRegistry. None если артефакт отсутствует."""
        try:
            return _get_orchestrator().load_registry(campaign_id)
        except Exception as e:
            logger.warning(f"[GATEWAY] Ошибка get_registry: {e}")
            return None

    @staticmethod
    def get_artifact_path(campaign_id: str) -> Optional[Path]:
        """Путь к артефакту. Для прямого чтения из backend."""
        try:
            return _get_orchestrator().get_artifact_path(campaign_id)
        except Exception as e:
            logger.warning(f"[GATEWAY] Ошибка get_artifact_path: {e}")
            return None

"""
frontend/spatial_compilation_orchestrator.py
Назначение: Единственное место принятия решений о компиляции мира
Зависимости: spatial_registry_builder.py
Основные сущности: SpatialCompilationOrchestrator

Решает КОГДА и ЧТО собрать. Не зависит от pygame, web framework, UI.
Не является god-object — принимает только решения о компиляции,
не владеет миром, не управляет рендерингом, не двигает NPC.
"""
import json
import logging
from pathlib import Path
from typing import Optional

from map_editor.spatial_registry_builder import (
    SpatialRegistryBuilder,
    SpatialRegistryArtifact,
    ARTIFACT_VERSION,
)

logger = logging.getLogger(__name__)


class SpatialCompilationOrchestrator:
    """Единственное место принятия решений о компиляции мира.

    Три роли разделены:
    - Trigger Layer (UI / Backend / CI) — говорит "пересобери если надо"
    - Orchestrator (этот класс) — решает КОГДА и ЧТО собрать
    - Builder (pure) — собирает

    Кеширует загруженные реестры для предотвращения повторных чтений.
    """

    def __init__(self) -> None:
        self._builder = SpatialRegistryBuilder()
        # Кеш загруженных реестров: campaign_id → (artifact_path, registry)
        self._cache: dict[str, tuple[Path, object]] = {}

    def rebuild_if_needed(self, campaign_id: str) -> bool:
        """Перестроить реестр если артефакт устарел.
        Возвращает True если была компиляция."""
        campaign_path = self._find_campaign_path(campaign_id)
        if campaign_path is None:
            logger.warning(f"[ORCHESTRATOR] Кампания не найдена: {campaign_id}")
            return False

        if self._builder.needs_rebuild(campaign_path):
            self._builder.build_and_save(campaign_path)
            # Инвалидируем кеш
            self._cache.pop(campaign_id, None)
            return True

        return False

    def rebuild(self, campaign_id: str) -> Optional[SpatialRegistryArtifact]:
        """Принудительная компиляция. Возвращает артефакт или None."""
        campaign_path = self._find_campaign_path(campaign_id)
        if campaign_path is None:
            logger.warning(f"[ORCHESTRATOR] Кампания не найдена: {campaign_id}")
            return None

        artifact = self._builder.build_and_save(campaign_path)
        self._cache.pop(campaign_id, None)
        return artifact

    def load_registry(self, campaign_id: str) -> Optional[object]:
        """Загрузить SpatialRegistry. None если артефакт отсутствует.
        Кеширует результат."""
        # Проверяем кеш
        if campaign_id in self._cache:
            cached_path, cached_registry = self._cache[campaign_id]
            return cached_registry

        artifact_path = self._find_artifact_path(campaign_id)
        if artifact_path is None:
            return None

        # Ленивый импорт — backend-класс может быть недоступен в pure-frontend контексте
        try:
            # Сначала пробуем backend (полный SpatialRegistry с find_chunks)
            import sys
            project_root = Path(__file__).resolve().parents[1]
            backend_path = project_root / "backend"
            if str(backend_path) not in sys.path:
                sys.path.insert(0, str(backend_path))
            from app.services.spatial.spatial_registry import SpatialRegistry
        except ImportError:
            # Fallback — minimal frontend-only registry
            SpatialRegistry = _MinimalFrontendRegistry

        try:
            registry = SpatialRegistry.load(artifact_path)
            self._cache[campaign_id] = (artifact_path, registry)
            return registry
        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Ошибка загрузки реестра: {e}")
            return None

    def get_artifact_path(self, campaign_id: str) -> Optional[Path]:
        """Путь к артефакту для кампании."""
        return self._find_artifact_path(campaign_id)

    # === Внутренние методы ===

    @staticmethod
    def _find_campaign_path(campaign_id: str) -> Optional[Path]:
        """Находит путь к кампании. Не зависит от caller context."""
        try:
            project_root = Path(__file__).resolve().parents[1]
        except (IndexError, ValueError):
            project_root = Path(".")

        candidate = project_root / "frontend" / "map_editor" / "campaigns" / campaign_id
        if candidate.exists():
            return candidate

        # Альтернативный layout: campaign_path = текущая base_dir
        candidate2 = project_root / "map_editor" / "campaigns" / campaign_id
        if candidate2.exists():
            return candidate2

        return None

    @staticmethod
    def _find_artifact_path(campaign_id: str) -> Optional[Path]:
        """Находит путь к артефакту."""
        try:
            project_root = Path(__file__).resolve().parents[1]
        except (IndexError, ValueError):
            project_root = Path(".")

        candidate = (
            project_root / "frontend" / "map_editor" / "campaigns"
            / campaign_id / "compiled" / "spatial_registry.json"
        )
        if candidate.exists():
            return candidate

        candidate2 = (
            project_root / "map_editor" / "campaigns"
            / campaign_id / "compiled" / "spatial_registry.json"
        )
        if candidate2.exists():
            return candidate2

        return None


class _MinimalFrontendRegistry:
    """Fallback-реестр для pure-frontend контекста (без backend).
    Только данные, без find_chunks/find_nearby."""
    def __init__(self, data: dict):
        self.data = data
        self.campaign_id = data.get("campaign_id", "")

    @classmethod
    def load(cls, path: Path) -> '_MinimalFrontendRegistry':
        with open(path, "r", encoding="utf-8") as f:
            return cls(json.load(f))
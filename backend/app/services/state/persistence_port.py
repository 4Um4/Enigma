from __future__ import annotations

# backend/app/services/state/persistence_port.py
"""
PersistencePort — абстракция сохранения состояния мира.

Принцип: persistence = инфраструктура, не доменная логика.
SceneStateManager использует порт для commit, но не знает КАК сохраняется.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class PersistencePort(ABC):
    """
    Порт сохранения состояния мира.

    Реализации:
    - JsonPersistenceAdapter — JSON файлы (текущий MVP)
    - (будущее) SqlitePersistenceAdapter — SQLite для Iron-Man режима
    """

    # СТАРЫЙ API (deprecate, оставить как shim для перехода)
    @abstractmethod
    def save_scene(self, campaign_id: str, scene_state: Dict[str, Any]) -> None:
        """Сохраняет состояние сцены в campaign_state.json."""
        ...

    @abstractmethod
    def load_scene(self, campaign_id: str) -> Dict[str, Any] | None:
        """Загружает состояние сцены. None если нет сохранения."""
        ...

    # НОВЫЙ API — multi-scene (Дополнение Б, п. Б.5.1)
    @abstractmethod
    def save_scene_at(self, campaign_id: str, location_id: str, scene_state: Dict[str, Any]) -> None:
        """Сохраняет состояние конкретной локации."""
        ...

    @abstractmethod
    def load_scene_at(self, campaign_id: str, location_id: str) -> Dict[str, Any] | None:
        """Загружает состояние конкретной локации. None если нет сохранения."""
        ...

    @abstractmethod
    def load_all_scenes(self, campaign_id: str) -> Dict[str, Dict[str, Any]]:
        """Загружает все локации кампании. Возвращает dict: location_id -> scene_state."""
        ...

    @abstractmethod
    def save_npcs(self, npc_dicts: List[Dict[str, Any]]) -> None:
        """Сохраняет состояния NPC в major_npcs.json. ЗАМЕЧЕНО: смешивает static/runtime."""
        ...

    @abstractmethod
    def save_npc_runtime(
        self, session_id: str, npc_dicts: List[Dict[str, Any]]
    ) -> None:
        """Сохраняет ТОЛЬКО runtime-состояние NPC в сессию (отдельно от статического профиля)."""
        ...

    @abstractmethod
    def load_npc_runtime(self, session_id: str) -> Optional[List[Dict[str, Any]]]:
        """Загружает runtime-состояние NPC из сессии. None если нет сохранения."""
        ...

    @abstractmethod
    def delete_campaign(self, campaign_id: str) -> None:
        """Удаляет все данные кампании (scene + runtime) из persistence.
        Используется при New Game для полной очистки всех слоёв."""
        ...

    @abstractmethod
    def atomic_commit(
        self,
        campaign_id: str,
        scene_state: Dict[str, Any],
        npc_states: Optional[List[Dict[str, Any]]] = None,
        events: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Атомарный коммит всего состояния тика (Устав 4.2.1).

        Единственная точка сохранения за тик. Вызывается из Фазы 10 TickOrchestrator.
        Всё или ничего — при ошибке полный откат.

        Args:
            campaign_id: ID кампании
            scene_state: финальное состояние сцены после всех фаз
            npc_states: runtime-состояния NPC (опционально, пока не проходят через контекст)
            events: события тика для аудита (опционально)

        Returns:
            True если коммит успешен, False если ошибка (откат).
        """
        ...

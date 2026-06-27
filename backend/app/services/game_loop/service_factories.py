"""Ленивая инициализация тяжёлых сервисов с кэшированием.

GameLoop создаёт один экземпляр ServiceFactory и делегирует ему
всю логику загрузки/кэширования SocialEngine, ReputationEngine, EconomyTracker.
Оркестратор не знает HOW — только WHEN.

path: backend/app/services/game_loop/service_factories.py
Назначение: Ленивая инициализация тяжёлых сервисов (SocialEngine, ReputationEngine, EconomyTracker) с кэшированием. Вынесено из GameLoop — оркестратор не должен содержать фабричную логику.
Зависимости: app.services.social.social_engine, app.services.social.reputation_engine, app.services.economy.economy_tracker, app.services.npc.npc_loader
Основные сущности: ServiceFactory
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ServiceFactory:
    """Кэш + ленивые инициализаторы для сервисов, дорогих в создании."""

    def __init__(
        self,
        *,
        load_npcs_func: Callable[[], List[dict]],
        data_dir: Path,
    ) -> None:
        self._load_npcs = load_npcs_func
        # FIX: Гарантируем Path, иначе оператор / падает с TypeError: unsupported operand type(s) for /: 'str' and 'str'
        self._data_dir = Path(data_dir)

        # Кэши — mutable, заполняются при первом обращении
        self._social_engine: Optional[Any] = None
        self._economic_profiles: Dict[str, Dict[str, Any]] = {}
        self._reputation_engine: Optional[Any] = None

        # EconomyTracker — лёгкий, создаём сразу
        from app.services.economy.economy_tracker import EconomyTracker
        self.economy_tracker: EconomyTracker = EconomyTracker()

    # ── Social Engine ────────────────────────────────────────────────────────

    def get_social_engine(self, campaign_id: str) -> Optional[Any]:
        """Ленивая инициализация SocialEngine из config/npc/social/."""
        if self._social_engine is not None:
            return self._social_engine
        try:
            from app.services.npc.npc_loader import load_social_base
            from app.services.social.social_engine import SocialEngine

            _config = load_social_base()
            if not _config.get("relations"):
                logger.info("[SOCIAL] No relations in config, engine disabled")
                return None

            # name_map для continuity_note (npc_id → имя)
            _all_npcs = self._load_npcs()
            _name_map = {
                n.get("id", ""): n.get("name", "")
                for n in _all_npcs if n.get("id")
            }
            self._social_engine = SocialEngine.from_config(_config, name_map=_name_map)
            logger.info(
                "[SOCIAL] Engine initialized (%d NPCs in graph)",
                len(self._social_engine.get_all_npc_ids()),
            )
            return self._social_engine
        except Exception as e:
            logger.warning(f"[SOCIAL] Init failed: {e}")
            return None

    # ── Reputation Engine ────────────────────────────────────────────────────

    def get_reputation_engine(self) -> Optional[Any]:
        """Ленивая инициализация ReputationEngine из config/world/factions.json."""
        if self._reputation_engine is not None:
            return self._reputation_engine
        try:
            from app.services.social.reputation_engine import ReputationEngine

            _config_path = self._data_dir / "config" / "world" / "factions.json"
            # Fallback: ищем в корне проекта
            if not _config_path.exists():
                _config_path = Path("config/world/factions.json")
            if not _config_path.exists():
                logger.info("[REPUTATION] factions.json not found, engine disabled")
                return None
            self._reputation_engine = ReputationEngine(config_path=str(_config_path))
            logger.info("[REPUTATION] Engine initialized")
            return self._reputation_engine
        except Exception as e:
            logger.warning(f"[REPUTATION] Init failed: {e}")
            return None

    # ── Economic Profiles ────────────────────────────────────────────────────

    def get_economic_profile(self, npc_id: str) -> Optional[Any]:
        """Возвращает EconomicProfile для NPC из кэша."""
        for campaign_profiles in self._economic_profiles.values():
            if npc_id in campaign_profiles:
                return campaign_profiles[npc_id]
        return None

    def get_or_create_economic_profiles(self, campaign_id: str) -> Dict[str, Any]:
        """Ленивая инициализация экономических профилей для кампании."""
        if campaign_id in self._economic_profiles:
            return self._economic_profiles[campaign_id]

        _profiles: Dict[str, Any] = {}
        _all_npcs = self._load_npcs()

        from app.services.economy.profile_factory import create_profile_from_npc
        from app.services.world.world_ontology import is_physical_object

        for _npc in _all_npcs:
            _nid = _npc.get("id")
            if not _nid:
                continue

            # Товары из carried_objects (физические предметы)
            _goods = {}
            for _item in _npc.get("carried_objects", []):
                if is_physical_object(_item):
                    _goods[_item] = 1

            _profiles[_nid] = create_profile_from_npc(
                npc_data=_npc,
                goods=_goods,
            )

        self._economic_profiles[campaign_id] = _profiles
        logger.info(f"[ECO] Initialized {len(_profiles)} economic profiles for {campaign_id}")
        return _profiles

    # ── Base Drives ──────────────────────────────────────────────────────────

    def collect_base_drives(self, campaign_id: str) -> Dict[str, Dict[str, float]]:
        """Извлекает базовые драйвы из всех NPC для EconomyTracker."""
        from app.services.npc.npc_loader import load_profile_from_legacy_json

        _all_npcs = self._load_npcs()
        _drives: Dict[str, Dict[str, float]] = {}

        for _npc in _all_npcs:
            _nid = _npc.get("id")
            if not _nid:
                continue
            try:
                _l0 = load_profile_from_legacy_json(_npc)
                _drives[_nid] = _l0.drives_base
            except Exception:
                _drives[_nid] = {"control": 0.25, "desire": 0.25, "fear": 0.25, "significance": 0.25}

        return _drives

    # ── StateApplicator ──────────────────────────────────────────────────────

    _state_applicator: Optional[Any] = None

    def get_state_applicator(
        self,
        relationship_store: Any = None,
    ) -> Any:
        """Ленивая инициализация StateApplicator с ReputationEngine.

        relationship_store: обязательный, из MemoryManager._relationships.
        """
        if self._state_applicator is not None:
            return self._state_applicator

        from app.services.npc.state_applicator import StateApplicator

        _rep_engine = self.get_reputation_engine()
        self._state_applicator = StateApplicator(
            relationship_store=relationship_store,
            reputation_engine=_rep_engine,
        )
        logger.info("[STATE_APPLICATOR] Initialized with ReputationEngine=%s", _rep_engine is not None)
        return self._state_applicator
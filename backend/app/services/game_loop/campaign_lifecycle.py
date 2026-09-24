"""
DEGOD Phase3B: владелец жизненного цикла кампании.
Отвечает на один вопрос: как кампания создаётся/сбрасывается/загружается/мигрирует.
Все операции — публичные API владельцев состояния (seam-волна 3B.0); порядок reset 1→12 = контракт.
Коммит атомарный (SSM.commit); EPOCH-FINAL не трогается.
Назначение: владелец жизненного цикла кампании — create/reset/load/migrate + campaign-level persistence (DEGOD Phase3B extraction).
Зависимости: app.models.world_state_diff (лениво), app.services.state.world_diff_applicator (лениво), app.services.state.save_format_detector (лениво), app.models.schemas.CampaignLoadResponse
Основные сущности: CampaignLifecycle
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional

from app.models.schemas import CampaignLoadResponse

if TYPE_CHECKING:
    from app.models.world_continuity import WorldContinuityMode
    from app.models.world_state_diff import WorldStateDiff

logger = logging.getLogger(__name__)


class CampaignLifecycle:
    def __init__(
        self,
        *,
        scene_manager,
        rel_store,
        memory_manager,
        tick_orch,
        avatar_service,
        mvp_controller,
        get_life_engine,
        load_npcs,
        saves_dir: Path,
    ) -> None:
        self.scene_manager = scene_manager
        self.rel_store = rel_store
        self.memory_manager = memory_manager
        self._tick_orch = tick_orch
        self.avatar_service = avatar_service
        self.mvp_controller = mvp_controller
        self._get_life_engine = get_life_engine
        self._load_npcs = load_npcs
        self._saves_dir = Path(saves_dir)
        # Campaign-owned state (переехало из GameLoop)
        self._campaign_diffs: Dict[str, "WorldStateDiff"] = {}
        self._diffs_path = self._saves_dir / "_world_diffs.json"
        self._campaign_world_index: dict[str, str] = {}

    # ── diff IO (P7-13) ───────────────────────────────────────────────────

    def save_diff_to_disk(self, campaign_id: str, diff: "WorldStateDiff") -> None:
        """Сохраняет WorldStateDiff на диск, чтобы он пережил рестарт бэкенда."""
        import json
        from dataclasses import asdict

        try:
            all_diffs = {}
            if self._diffs_path.exists():
                with open(self._diffs_path, "r", encoding="utf-8") as f:
                    all_diffs = json.load(f)
            all_diffs[campaign_id] = asdict(diff)
            self._diffs_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._diffs_path, "w", encoding="utf-8") as f:
                json.dump(all_diffs, f, ensure_ascii=False, indent=2)
            logger.info(f"[WORLD_DIFF] Saved diff for '{campaign_id}' to disk.")
        except Exception as e:
            logger.error(f"[WORLD_DIFF] Failed to save diff for '{campaign_id}': {e}")

    def load_diff_from_disk(self, campaign_id: str) -> Optional["WorldStateDiff"]:
        """Загружает WorldStateDiff с диска, если он там есть."""
        import json

        from app.models.world_state_diff import WorldStateDiff

        try:
            if not self._diffs_path.exists():
                return None
            with open(self._diffs_path, "r", encoding="utf-8") as f:
                all_diffs = json.load(f)
            diff_data = all_diffs.get(campaign_id)
            if diff_data:
                return WorldStateDiff(**diff_data)
            return None
        except Exception as e:
            logger.error(f"[WORLD_DIFF] Failed to load diff for '{campaign_id}': {e}")
            return None

    def record_campaign_diff(self, campaign_id: str, diff: "WorldStateDiff") -> None:
        """Публичный seam для routes (ранее: game_loop._campaign_diffs[cid] = diff + _save_diff_to_disk)."""
        self._campaign_diffs[campaign_id] = diff
        self.save_diff_to_disk(campaign_id, diff)

    def get_diff(self, campaign_id: str) -> Optional["WorldStateDiff"]:
        """Diff кампании: RAM → disk fallback."""
        source_diff = self._campaign_diffs.get(campaign_id)
        if not source_diff:
            source_diff = self.load_diff_from_disk(campaign_id)
        return source_diff


    def load_campaign(self, campaign_id: str, world_id: str) -> CampaignLoadResponse:
        # ADR-O-146: AdventureLoader удалён. Файлов world_lore/npc.json/locations.json не существует.
        loaded: dict = {"status": "not_found", "files": {}}
        self._campaign_world_index[campaign_id] = world_id

        # Дополнение Б (п. Б.12): Детектор старых сейвов
        try:
            from app.services.state.save_format_detector import detect_legacy_saves
            _legacy_campaigns = detect_legacy_saves(self._saves_dir)
            if campaign_id in _legacy_campaigns:
                logger.warning(f"[SAVE_MIGRATION] Обнаружен сейв старого формата для кампании '{campaign_id}'. Удаление...")
                _old_save_file = self._saves_dir / campaign_id / "campaign_state.json"
                if _old_save_file.exists():
                    _old_save_file.unlink()
        except Exception as _migr_err:
            logger.error(f"[SAVE_MIGRATION] Ошибка при удалении старого сейва: {_migr_err}")
        for filename, payload in loaded.get("files", {}).items():
            self.memory_manager.persist_world_canon(
                world_id,
                campaign_id=campaign_id,
                source=filename,
                payload=payload,
            )
        self.memory_manager.persist_campaign_event(
            campaign_id,
            event="campaign_loaded",
            world_id=world_id,
            data={
                "loaded_files": list(loaded.get("files", {})),
                "status": loaded["status"],
            },
        )
        return CampaignLoadResponse(
            campaign_id=campaign_id,
            world_id=world_id,
            status=loaded["status"],
            loaded_files=list(loaded.get("files", {})),
        )

    def resolve_world_id(self, campaign_id: str) -> str:
        if campaign_id in self._campaign_world_index:
            return self._campaign_world_index[campaign_id]
        history = self.memory_manager.read_campaign_history(campaign_id, limit=100)
        for item in reversed(history):
            if item.get("event") == "campaign_loaded" and item.get("world_id"):
                self._campaign_world_index[campaign_id] = item["world_id"]
                return str(item["world_id"])
        return "manual"


    def reset_campaign(
        self,
        campaign_id: str,
        continuity_mode: Optional["WorldContinuityMode"] = None,
        source_campaign_id: Optional[str] = None
    ) -> dict:
        """Сбрасывает runtime состояние кампании к чистому static.
        Опционально применяет WorldStateDiff из source_campaign_id (если continuity_mode == CONTINUOUS).

        Полная очистка: SQLite + JSON + все кэши.
        Переинициализация: сцена из editor JSON + NPC со здоровым body_state.
        Источник чистого мира: config/npc/ + map_editor/campaigns/
        Оставляет: characters.json, character_profiles.json (выбор персонажа)

        Returns: {"reset": True, "campaign_id": str, "files_removed": [str]}
        """
        from app.models.world_continuity import WorldContinuityMode
        if continuity_mode is None:
            continuity_mode = WorldContinuityMode.ISOLATED


        removed = []
        saves_campaign = self._saves_dir / campaign_id

        # === 1. ОЧИСТКА PERSISTENCE (SQLite: scene + runtime) ===
        # КОРЕНЬ БАГА: раньше не чистили SQLite → LifeEngine читал старый runtime
        try:
            if self.scene_manager.reset_campaign_persistence(campaign_id):
                removed.append("sqlite:scene+runtime")
                logger.info(f"[NEW_GAME] SQLite cleared for '{campaign_id}'")
        except Exception as e:
            logger.warning(f"[NEW_GAME] SQLite cleanup failed: {e}")

        # === 2. ОЧИСТКА JSON ФАЙЛОВ в saves/<campaign_id>/ ===
        runtime_files = [
            "npc_runtime.json",
            "campaign_state.json",
            "player_avatar.json",
            "npc_relationships.json",
            "campaign_meta.json",
        ]
        for fname in runtime_files:
            fpath = saves_campaign / fname
            if fpath.exists():
                try:
                    fpath.unlink()
                except Exception as e:
                    logger.error(f"[NEW_GAME] Atomic commit: Failed to remove {fpath}: {e}")
                    continue
                removed.append(fname)
                logger.info(f"[NEW_GAME] Removed: {fpath}")

        # === 3. СБРОС ОТНОШЕНИЙ (RelationshipStore: кэш + диск) ===
        try:
            self.rel_store.reset_campaign(campaign_id)
            removed.append("relationships")
        except Exception as e:
            logger.warning(f"[NEW_GAME] RelationshipStore reset failed: {e}")

        # === 3b. СБРОС УБЕЖДЕНИЙ L2.5 (FIX-RC3 / P3: old memories = 0) ===
        # enigma_memory.db не чистился NEW_GAME: убеждения прошлых сессий
        # переживали рестарт и душили драйвы нового мира.
        try:
            _belief_store = getattr(self._tick_orch, "crystallized_belief_store", None)
            if _belief_store is not None:
                _belief_store.reset_campaign(campaign_id)
                removed.append("sqlite:crystallized_beliefs")
                logger.info(f"[NEW_GAME] BeliefStore cleared for '{campaign_id}'")
        except Exception as e:
            logger.warning(f"[NEW_GAME] BeliefStore reset failed: {e}")

        # === 4. СБРОС СЕССИИ ===
        try:
            from app.services.player_session_service import player_session_service

            player_session_service.deactivate_player(campaign_id)
            player_session_service._delete_session_from_disk(campaign_id)
        except Exception as e:
            logger.warning(f"[NEW_GAME] Session reset failed: {e}")

        # === 5. СБРОС + ПЕРЕИНИЦИАЛИЗАЦИЯ NPC (healthy body_state) ===
        # КОРЕНЬ БАГА: раньше только чистили кэш → NPC грузились без body_state
        # → Normalization Gate инжектил BODY_STATE_DISABLED (shock=1.0, pain=100)
        _npcs_for_commit = []
        try:
            engine = self._get_life_engine()
            _npcs_for_commit = engine.reset_campaign(campaign_id) or []
        except Exception as e:
            logger.warning(f"[NEW_GAME] LifeEngine NPC reset failed: {e}")

        # === 5.1 WORLD CONTINUITY (P7-13) ===
        # Если режим CONTINUOUS, применяем WorldStateDiff из source-кампании к чистым NPC до коммита
        if continuity_mode == WorldContinuityMode.CONTINUOUS and source_campaign_id and _npcs_for_commit:
            source_diff = self._campaign_diffs.get(source_campaign_id)
            if not source_diff:
                source_diff = self.load_diff_from_disk(source_campaign_id)
            if source_diff:
                from app.services.state.world_diff_applicator import WorldStateApplicator
                _applicator = WorldStateApplicator(mode=continuity_mode)
                # Превращаем list[dict] в dict[npc_id, dict] для мутации
                _npc_cache = {n.get("npc_id"): n for n in _npcs_for_commit if n.get("npc_id")}
                _applicator.apply(diff=source_diff, npc_cache=_npc_cache)
                _npcs_for_commit = list(_npc_cache.values())
                logger.info(f"[NEW_GAME] Applied WorldStateDiff from '{source_campaign_id}' to {campaign_id}")

        # === 6. ПЕРЕИНИЦИАЛИЗАЦИЯ СЦЕНЫ из editor JSON ===
        # КОРЕНЬ БАГА: раньше сцена не пересоздавалась → get_scene_state() = None
        _scene_for_commit = None
        try:
            _scene_for_commit = self.scene_manager.reinit_campaign(campaign_id)
            # FIX-WALLS-2: seed авторитета локации игрока при new_game.
            # Без current_location в metadata idle-путь угадывает активную
            # локацию («первую попавшуюся», sqlite:206) → ротация сцен →
            # фронтенд получает снапшот чужой локации («NPC сквозь стену»).
            # Стартовая локация = где заспавнен игрок (reinit возвращает её).
            try:
                if isinstance(_scene_for_commit, dict) and _scene_for_commit.get("location_id"):
                    from app.services.campaign_state_service import get_campaign_state_service

                    _cs = get_campaign_state_service().get_campaign_state(campaign_id)
                    if _cs:
                        _cs.metadata["current_location"] = _scene_for_commit["location_id"]
                        logger.info(
                            f"[NEW_GAME] current_location seeded: {_scene_for_commit['location_id']}"
                        )
            except Exception as _seed_err:
                logger.warning(f"[NEW_GAME] current_location seed failed: {_seed_err}")
        except Exception as e:
            logger.warning(f"[NEW_GAME] Scene reinit failed: {e}")

        # === 7. АТОМАРНЫЙ КОММИТ (scene + npcs) ===
        # BUG-AUDIT-13: Сохраняем сцену и NPC в одной транзакции, чтобы избежать рассинхрона.
        if _scene_for_commit and _npcs_for_commit:
            try:
                self.scene_manager.commit(
                    campaign_id=campaign_id,
                    scene_state=_scene_for_commit,
                    npc_dicts=_npcs_for_commit,
                    events=[],
                    significant_events=[],
                )
                logger.info(f"[NEW_GAME] Atomic commit OK for {campaign_id}")
            except Exception as e:
                logger.error(f"[NEW_GAME] Atomic commit FAILED for {campaign_id}: {e}")

        # === 7. СБРОС LRU-КЭША загрузчика ===
        if hasattr(self._load_npcs, "cache_clear"):
            self._load_npcs.cache_clear()

        # === 9. СБРОС MemoryManager (narrative_cache + dialogue sessions) ===
        try:
            _mem_reset = self.memory_manager.reset_campaign_state(campaign_id)
        except Exception as e:
            logger.warning(f"[NEW_GAME] MemoryManager reset failed: {e}")

        # === 10. СБРОС TemporalEngine (tick=0 + удаление world_tick.json) ===
        try:
            engine_temporal = self._get_life_engine()._temporal
            engine_temporal.reset_campaign(campaign_id)
            removed.append("world_tick.json")
        except Exception as e:
            logger.warning(f"[NEW_GAME] TemporalEngine reset failed: {e}")

        # === 11. СБРОС СЕССИИ АВАТАРА (player body_state из предыдущей игры) ===
        try:
            # DEGOD Phase3B.0-Seam5: сброс у владельца (устранён DOUBLE TRUTH пути —
            # старый код удалял player_avatar.json по чужому пути, настоящий переживал new_game)
            if self.avatar_service.reset_campaign(campaign_id):
                removed.append("player_avatar.json")
        except Exception as e:
            logger.warning(f"[NEW_GAME] Avatar session reset failed: {e}")

        # === 12. СБРОС ПАМЯТИ NPC (narrative_cache + campaign history) ===
        try:
            # Очистить все dialogue sessions (STM)
            _cleared_npcs = self._get_life_engine().clear_runtime_caches(campaign_id)
        except Exception as e:
            logger.warning(f"[NEW_GAME] Memory reset failed: {e}")

        # === 12. ОЧИСТКА SQLITE ПАМЯТИ (старые воспоминания) ===
        removed.append(f"sqlite:memories({_mem_reset['sqlite_rows']})")
        logger.info(f"[NEW_GAME] SQLite memories cleared: {_mem_reset['sqlite_rows']} rows")

        # P-MVP-1: Инициализация эпистемического фасада для новой кампании
        if self.mvp_controller:
            try:
                self.mvp_controller.init_campaign(campaign_id)
                logger.info(f"[NEW_GAME] MVP controller initialized for '{campaign_id}'")
            except Exception as e:
                logger.error(f"[NEW_GAME] MVP controller init failed: {e}")

        logger.info(
            f"[NEW_GAME] Campaign '{campaign_id}' fully reset. Removed: {removed}"
        )
        return {"reset": True, "campaign_id": campaign_id, "files_removed": removed}

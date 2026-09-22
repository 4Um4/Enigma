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

if TYPE_CHECKING:
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

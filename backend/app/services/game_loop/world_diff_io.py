"""
DEGOD ITER5: I/O WorldStateDiff (перенос из game_loop/__init__.py).
Назначение: I/O WorldStateDiff на диск (межкампанийная непрерывность P7-13). DEGOD ITER5: перенос из game_loop/init.py (:638–676); путь — явный параметр.
Зависимости: json, pathlib, app.models.world_state_diff (лениво)
Основные сущности: save_diff_to_disk, load_diff_from_disk
"""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.world_state_diff import WorldStateDiff

logger = logging.getLogger(__name__)


def save_diff_to_disk(diffs_path: Path, campaign_id: str, diff: "WorldStateDiff") -> None:
    """Сохраняет WorldStateDiff на диск, чтобы он пережил рестарт бэкенда."""
    from dataclasses import asdict

    try:
        all_diffs = {}
        if diffs_path.exists():
            with open(diffs_path, "r", encoding="utf-8") as f:
                all_diffs = json.load(f)

        all_diffs[campaign_id] = asdict(diff)

        diffs_path.parent.mkdir(parents=True, exist_ok=True)
        with open(diffs_path, "w", encoding="utf-8") as f:
            json.dump(all_diffs, f, ensure_ascii=False, indent=2)
        logger.info(f"[WORLD_DIFF] Saved diff for '{campaign_id}' to disk.")
    except Exception as e:
        logger.error(f"[WORLD_DIFF] Failed to save diff for '{campaign_id}': {e}")


def load_diff_from_disk(diffs_path: Path, campaign_id: str) -> "WorldStateDiff | None":
    """Загружает WorldStateDiff с диска, если он там есть."""
    from app.models.world_state_diff import WorldStateDiff

    try:
        if not diffs_path.exists():
            return None
        with open(diffs_path, "r", encoding="utf-8") as f:
            all_diffs = json.load(f)

        diff_data = all_diffs.get(campaign_id)
        if diff_data:
            return WorldStateDiff(**diff_data)
        return None
    except Exception as e:
        logger.error(f"[WORLD_DIFF] Failed to load diff for '{campaign_id}': {e}")
        return None

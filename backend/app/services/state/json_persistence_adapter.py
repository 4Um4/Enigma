from __future__ import annotations
# backend/app/services/state/json_persistence_adapter.py
"""
JsonPersistenceAdapter — JSON реализация PersistencePort.

Сохраняет:
- scene_state -> campaigns/{id}/campaign_state.json
- npc_runtime -> campaigns/{id}/npc_runtime.json (только runtime-состояние)
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.services.state.persistence_port import PersistencePort

logger = logging.getLogger(__name__)


class JsonPersistenceAdapter(PersistencePort):
    """
    JSON реализация порта сохранения.
    Совместима с текущей структурой данных ENIGMA.
    """

    def __init__(self, data_dir: Path, saves_dir: Optional[Path] = None) -> None:
        # ADR-O-146: _campaigns_dir удалён — мёртвый путь. Runtime через _saves_dir.
        self._saves_dir = Path(saves_dir) if saves_dir else data_dir / "saves"
        # TODO: временная заглушка — save_npcs пишет в major_npcs.json (legacy путь)
        # будет удалено после: полного отказа от save_npcs в пользу save_npc_runtime
        self._npcs_path = data_dir / "npcs" / "major_npcs.json"

    def save_scene(self, campaign_id: str, scene_state: Dict[str, Any]) -> None:
        """Сохраняет scene_state в campaign_state.json."""
        campaign_file = self._saves_dir / campaign_id / "campaign_state.json"
        try:
            campaign_file.parent.mkdir(parents=True, exist_ok=True)
            data: Dict[str, Any] = {}
            if campaign_file.exists():
                with open(campaign_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data["scene_state"] = scene_state
            with open(campaign_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"[PERSISTENCE] Scene saved: {campaign_id}")
        except OSError as e:
            logger.error(f"[PERSISTENCE] Error saving scene: {e}")

    def load_scene(self, campaign_id: str) -> Dict[str, Any] | None:
        """Загружает scene_state из campaign_state.json. None если нет."""
        campaign_file = self._saves_dir / campaign_id / "campaign_state.json"
        if not campaign_file.exists():
            return None
        try:
            with open(campaign_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("scene_state")
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"[PERSISTENCE] Error loading scene: {e}")
            return None

    def save_npcs(self, npc_dicts: List[Dict[str, Any]]) -> None:
        """Сохраняет NPC в major_npcs.json."""
        try:
            self._npcs_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._npcs_path, "w", encoding="utf-8") as f:
                json.dump(npc_dicts, f, ensure_ascii=False, indent=2)
            logger.debug(f"[PERSISTENCE] NPCs saved: {len(npc_dicts)} records")
        except OSError as e:
            logger.error(f"[PERSISTENCE] Error saving NPCs: {e}")

    def save_npc_runtime(
        self, session_id: str, npc_dicts: List[Dict[str, Any]]
    ) -> None:
        """Сохраняет runtime-состояние NPC в сессию (отдельно от статического профиля)."""
        if not session_id:
            logger.warning(
                "[PERSISTENCE] save_npc_runtime вызван без session_id — пропуск"
            )
            return
        runtime_path = self._saves_dir / session_id / "npc_runtime.json"
        try:
            runtime_path.parent.mkdir(parents=True, exist_ok=True)
            with open(runtime_path, "w", encoding="utf-8") as f:
                json.dump(npc_dicts, f, ensure_ascii=False, indent=2)
            logger.debug(
                f"[PERSISTENCE] NPC runtime saved: {session_id} ({len(npc_dicts)} records)"
            )
        except OSError as e:
            logger.error(f"[PERSISTENCE] Error saving NPC runtime: {e}")

    def load_npc_runtime(self, session_id: str) -> Optional[List[Dict[str, Any]]]:
        """Загружает runtime-состояние NPC из сессии. None если нет сохранения."""
        if not session_id:
            return None
        runtime_path = self._saves_dir / session_id / "npc_runtime.json"
        if not runtime_path.exists():
            return None
        try:
            with open(runtime_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"[PERSISTENCE] Error loading NPC runtime: {e}")
            return None

    def delete_campaign(self, campaign_id: str) -> None:
        """Удаляет все данные кампании (JSON файлы в saves/<campaign_id>/).
        New Game: полная очистка persistence-слоя."""
        campaign_dir = self._saves_dir / campaign_id
        if not campaign_dir.exists():
            return
        removed = []
        for fname in [
            "campaign_state.json",
            "npc_runtime.json",
            "npc_relationships.json",
            "campaign_meta.json",
            "player_avatar.json",
        ]:
            fpath = campaign_dir / fname
            if fpath.exists():
                fpath.unlink()
                removed.append(fname)
        logger.info(
            f"[PERSISTENCE] Campaign deleted: {campaign_id}, removed: {removed}"
        )

    def atomic_commit(
        self,
        campaign_id: str,
        scene_state: Dict[str, Any],
        npc_states: Optional[List[Dict[str, Any]]] = None,
        events: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Фоллбэк: раздельные JSON-записи (нет транзакции на уровне файлов).

        Устав 4.2.1 предупреждение: JSON не даёт атомарности.
        Events не сохраняются в JSON (нет целевой таблицы) — только warning.
        """
        try:
            self.save_scene(campaign_id, scene_state)
            if npc_states is not None:
                self.save_npc_runtime(campaign_id, npc_states)
            if events is not None:
                logger.warning(
                    "[PERSISTENCE] JSON adapter: events dropped (нет аудит-таблицы)"
                )
            logger.debug(f"[PERSISTENCE] Atomic commit (best-effort): {campaign_id}")
            return True
        except OSError as e:
            logger.error(f"[PERSISTENCE] Atomic commit FAILED ({campaign_id}): {e}")
            return False

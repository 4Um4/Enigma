# -*- coding: utf-8 -*-
"""path: backend/app/services/game_loop/dialogue_log.py
Назначение: UX-DLG-LOG (Тай): внешний авто-журнал всех диалогов хода —
    реплика игрока, ответ DM, NPC-реакции + компактная проекция понимания
    (semantic_action / акты / readiness) — для диагностики адекватности
    ответов. Файл ВНЕ папки игры: env ENIGMA_DIALOGUE_LOG, по умолчанию
    <родитель игры>/EnigmaDialogueLog/dialogue_log.jsonl.
    JSONL, append-only. Отказ записи не роняет ход (громкий warning,
    ADR-O-308 — не тихий). wall_ts — телеметрия (§15.2-1).
Зависимости: stdlib.
Основные сущности: log_turn.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# .../Enigma/backend/app/services/game_loop/dialogue_log.py -> parents[4]=Enigma
_GAME_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_DIR = _GAME_ROOT.parent / "EnigmaDialogueLog"  # вне папки игры


def _log_path() -> Path:
    _env = os.environ.get("ENIGMA_DIALOGUE_LOG", "")
    if _env:
        return Path(_env)
    return _DEFAULT_DIR / "dialogue_log.jsonl"


def log_turn(
    campaign_id: str,
    location: str,
    player_text: str,
    dm_response: str,
    npc_reactions: List[str],
    understanding: Dict[str, Any] | None,
) -> None:
    """Append-only запись хода диалога во внешний файл."""
    _entry = {
        "wall_ts": datetime.now(timezone.utc).isoformat(),
        "campaign": campaign_id,
        "location": location,
        "player": player_text,
        "dm": dm_response,
        "npc_reactions": list(npc_reactions or []),
        "understanding": understanding or {},
    }
    try:
        _p = _log_path()
        _p.parent.mkdir(parents=True, exist_ok=True)
        with _p.open("a", encoding="utf-8") as _f:
            _f.write(json.dumps(_entry, ensure_ascii=False) + "\n")
    except Exception as _e:  # noqa: ENIGMA002 — громкий отказ, не тихий
        logger.warning(f"[DIALOGUE_LOG] запись не удалась: {_e}")

# backend/app/services/npc/reaction_priority.py
"""
ReactionPriority — кто из NPC реагирует на событие и в каком порядке (Phase S.4.2)

Принцип: Python считает приоритет (роль + расстояние + психика + обязанности).
LLM только озвучивает. Никакого хардкода имён.

Вызывается из PythonEngines ПОСЛЕ apply_changes (SceneState уже обновлён).
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 1. Настройки
# ─────────────────────────────────────────────────────────────────────────────
THRESHOLD_MUST_REACT = 60   # NPC обязан вмешаться
THRESHOLD_WILL_REACT = 30   # NPC хочет отреагировать
MAX_SPEAKERS_PER_TURN = 3   # максимум NPC говорят за один ход

# ─────────────────────────────────────────────────────────────────────────────
# 2. Таблица обязанностей по роли (расширяется легко)
#    Ключ — префикс id NPC
# ─────────────────────────────────────────────────────────────────────────────
_DUTY_TABLE: dict[str, dict[str, int]] = {
    "tavern_keeper": {"stop_theft": 70, "stop_violence": 65, "protect_worker": 75,
                      "stop_disrespect": 50, "stop_disorder": 55, "stop_danger": 60},
    "innkeeper":     {"stop_theft": 70, "stop_violence": 65, "protect_worker": 75,
                      "stop_disrespect": 50, "stop_disorder": 55, "stop_danger": 60},
    "guard":         {"stop_theft": 85, "stop_violence": 85, "stop_disorder": 70,
                      "stop_disrespect": 45, "stop_danger": 75},
    "merchant":      {"stop_theft": 80, "protect_goods": 80, "stop_disorder": 30},
    "priest":        {"stop_violence": 55, "heal_wounded": 65, "stop_danger": 50,
                      "stop_disrespect": 35},
    "maid":          {"stop_violence": 20, "protect_worker": 40},
    "barmaid":       {"stop_violence": 20, "protect_worker": 40},
    "soldier":       {"stop_violence": 75, "stop_disorder": 60, "stop_danger": 70},
    "bandit":        {"join_violence": 40, "stop_theft": -20},
    "thief":         {"stop_theft": -30, "join_violence": 20},
}

# ─────────────────────────────────────────────────────────────────────────────
# 3. Graceful import SceneChange (чтобы не падало при рефакторинге)
# ─────────────────────────────────────────────────────────────────────────────
try:
    from app.services.scene_change import SceneChange, ChangeType
    _SCENE_CHANGE_AVAILABLE = True
except ImportError:
    SceneChange = None
    ChangeType = None
    _SCENE_CHANGE_AVAILABLE = False


@dataclass
class ReactionScore:
    npc_id: str
    npc_name: str
    score: int = 0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "npc_id": self.npc_id,
            "npc_name": self.npc_name,
            "score": self.score,
            "reason": " | ".join(self.reasons) if self.reasons else "наблюдает",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ─────────────────────────────────────────────────────────────────────────────
def _get_npc_distance(npc: dict, scene_state: dict) -> float:
    """Расстояние из SceneState (player_distances)."""
    if not scene_state:
        return 999.0
    distances = scene_state.get("player_distances", {})
    npc_id = npc.get("id", "")
    if npc_id in distances:
        return float(distances[npc_id])
    return 999.0


def _is_incapacitated(npc: dict) -> bool:
    """NPC не может реагировать."""
    state = str(npc.get("state", "")).lower()
    status = str(npc.get("status", "")).lower()
    conditions = [str(c).lower() for c in npc.get("conditions", [])]
    incap = {"sleeping", "unconscious", "captured", "dead", "спит", "без сознания", "захвачен", "мёртв"}
    return any(w in state or w in status or w in conditions for w in incap)


def _classify_change(change: Any) -> set[str]:
    """Возвращает теги события для сопоставления с _DUTY_TABLE."""
    if not _SCENE_CHANGE_AVAILABLE or not isinstance(change, SceneChange):
        return set()

    tags = set()
    if change.type == ChangeType.NPC_STATE and change.field in ("hp", "psyche_state"):
        tags.add("stop_violence")
    if change.type == ChangeType.OBJECT_REMOVE and "steal" in str(change.cause or ""):
        tags.add("stop_theft")
        tags.add("protect_goods")
    if change.type == ChangeType.OBJECT_STATE and change.value in ("damaged", "broken"):
        tags.add("stop_disorder")
    if change.cause in ("player_taunt", "player_intimidate"):
        tags.add("stop_disrespect")
    if change.type == ChangeType.EFFECT_ADD:
        tags.add("stop_danger")
    return tags


def _get_role(npc: dict) -> str:
    """Роль по префиксу id."""
    npc_id = npc.get("id", "")
    for role in _DUTY_TABLE:
        if npc_id.startswith(role):
            return role
    return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# Основная логика
# ─────────────────────────────────────────────────────────────────────────────
def _score_npc(
    npc: dict,
    scene_state: dict,
    scene_changes: list,
    actor_id: str = "player",
) -> ReactionScore:
    rs = ReactionScore(npc_id=npc.get("id", "unknown"), npc_name=npc.get("name", "NPC"))

    if _is_incapacitated(npc):
        rs.score = -99
        rs.reasons.append("недееспособен")
        return rs

    distance = _get_npc_distance(npc, scene_state)

    # Пространственные факторы
    if distance <= 5.0:
        rs.score += 20
        rs.reasons.append(f"рядом ({distance:.1f}м)")

    # Роль + обязанности
    role = _get_role(npc)
    duties = _DUTY_TABLE.get(role, {})
    for change in scene_changes:
        tags = _classify_change(change)
        for tag in tags:
            bonus = duties.get(tag, 0)
            rs.score += bonus
            if bonus > 0:
                rs.reasons.append(f"{tag} (+{bonus})")

    # Психология
    psyche = npc.get("psyche", {})
    stress = psyche.get("stress", 0)
    if stress >= 70:
        rs.score += 10
        rs.reasons.append(f"стресс {stress}")

    drives = npc.get("drives", {})
    if drives.get("control", 0) >= 0.5:
        rs.score += 15

    return rs


def get_reaction_order(
    npcs: list[dict],
    scene_state: dict,
    scene_changes: list,
    actor_id: str = "player",
    min_score: int = 10,
) -> list[dict]:
    """
    Публичный API. Возвращает отсортированный список реакций.
    Вызывается из PythonEngines после apply_changes.
    """
    if not npcs or not scene_changes:
        return []

    scores = []
    for npc in npcs:
        try:
            rs = _score_npc(npc, scene_state, scene_changes, actor_id)
            if rs.score >= min_score:
                scores.append(rs)
        except Exception as e:
            logger.error(f"[REACTION_PRIORITY] Ошибка NPC {npc.get('id')}: {e}")

    scores.sort(key=lambda x: x.score, reverse=True)
    result = [rs.to_dict() for rs in scores[:MAX_SPEAKERS_PER_TURN]]

    if result:
        logger.info(
            f"[REACTION_PRIORITY] Порядок: "
            f"{[(r['npc_name'], r['score'], r['reason']) for r in result]}"
        )

    return result
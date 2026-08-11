"""
app/services/player_cognition/attention_layer.py
Attention Layer — deterministic core + stochastic edge, dual control (player + system).

Видно ≠ замечено. Замечено ≠ осознано.

path: /backend/app/services/player_cognition/attention_layer.py
Назначение: Определяет, на что игрок обращает внимание — deterministic core + stochastic edge, hybrid control
Зависимости: types, math, random
Основные сущности: PlayerFocus, apply_attention()
"""

from dataclasses import dataclass
from typing import List, Optional

from app.services.player_cognition.types import PerceivedEntity

# === Пороги детерминизма ===
# > HARD — всегда замечено (95%)
# < SOFT — никогда не замечено (95%)
# между — probabilistic roll
_HARD_ATTENTION_THRESHOLD = 0.70
_SOFT_ATTENTION_THRESHOLD = 0.30

# === Множители внимания ===
_MOTION_BONUS = 0.20  # движение привлекает внимание
_SALIENT_TYPE_BONUS = 0.15  # оружие, опасные объекты
_THREAT_STRESS_PENALTY = 0.01  # стресс сужает периферию (за каждую единицу)
_STRESS_TUNNEL_MAX = 0.30  # максимальное сужение от стресса
_SIZE_BONUS_PER_M2 = 0.005  # крупные объекты заметнее

# Типы с повышенной заметностью (оружие, опасность)
_SALIENT_TYPES = {"weapon", "door", "passage"}


@dataclass
class PlayerFocus:
    """Текущий фокус внимания игрока — управляется гибридно"""

    focus_entity_id: Optional[str] = None  # на что смотрит (игрок задаёт)
    focus_direction: tuple[float, float] = (
        0.0,
        -1.0,
    )  # куда смотрит (нормализованный вектор)
    focus_zone_radius: float = 1.5  # радиус зоны фокуса в метрах


def _base_attention_score(
    entity: PerceivedEntity,
    focus: PlayerFocus,
    stress: float,
) -> float:
    """
    Детерминированная база: clarity + proximity + focus + modifiers.
    Возвращает 0.0 – 1.0
    """
    if not entity.visible:
        return 0.0

    # Чёткость восприятия — фундамент
    score = entity.clarity

    # Близость — ближе = заметнее
    if entity.distance < 3.0:
        score += 0.15
    elif entity.distance < 6.0:
        score += 0.05

    # Фокус игрока — в зоне фокуса = бонус
    if focus.focus_entity_id == entity.entity_id:
        score += 0.30  # прямой фокус — сильный бонус
    # TODO: вычислить угол между focus_direction и направлением на сущность
    # для периферийного зрения — пока используем упрощённую модель

    # Размер объекта — крупные заметнее
    raw = entity._raw_data
    size = raw.get("size") or {}
    area = abs(size.get("w", 0.0)) * abs(size.get("h", 0.0))
    score += min(area * _SIZE_BONUS_PER_M2, 0.10)

    # Тип с повышенной заметностью
    obj_type = raw.get("type", "")
    if obj_type in _SALIENT_TYPES:
        score += _SALIENT_TYPE_BONUS

    # Движение (activity у NPC)
    if entity.entity_type == "npc" and raw.get("activity"):
        score += _MOTION_BONUS

    # Стресс сужает внимание — штраф для НЕ фокусных сущностей
    if focus.focus_entity_id != entity.entity_id:
        tunnel_penalty = min(stress * _THREAT_STRESS_PENALTY, _STRESS_TUNNEL_MAX)
        score -= tunnel_penalty

    return max(0.0, min(1.0, score))


def _stochastic_roll(score: float) -> bool:
    """
    Deterministic base + stochastic edge.
    0–0.3: не замечено (95%)
    0.3–0.7: зона неопределённости (roll)
    0.7–1.0: замечено (95%)
    """
    import random

    # Фикс L2: Детерминированный RNG на основе score (stateless функция без доступа к tick)
    from app.services.npc.kernel_rng import KernelRNG
    _rng = KernelRNG(tick=0, npc_id="player_attention", salt=str(score))
    
    if score >= _HARD_ATTENTION_THRESHOLD:
        return _rng.random() < 0.95
    elif score <= _SOFT_ATTENTION_THRESHOLD:
        return _rng.random() < 0.05
    else:
        # Линейная интерполяция в зоне неопределённости
        # 0.3 → 5%, 0.7 → 95%
        probability = (
            0.05
            + (score - _SOFT_ATTENTION_THRESHOLD)
            / (_HARD_ATTENTION_THRESHOLD - _SOFT_ATTENTION_THRESHOLD)
            * 0.90
        )
        return _rng.random() < probability


def apply_attention(
    entities: List[PerceivedEntity],
    focus: PlayerFocus,
    stress: float = 0.0,
) -> List[PerceivedEntity]:
    """
    Применяет Attention Layer — отфильтровывает невнимаемые сущности.
    Фокусная сущность ВСЕГДА проходит (игрок сознательно смотрит).

    Мутирует entities in-place, возвращает отфильтрованный список.
    """
    noticed: List[PerceivedEntity] = []

    for entity in entities:
        # Фокусная сущность — всегда в внимании, без броска
        if focus.focus_entity_id == entity.entity_id:
            entity.in_attention = True
            entity.attention_score = 1.0
            noticed.append(entity)
            continue

        # Невидимые — не в внимании
        if not entity.visible:
            entity.in_attention = False
            entity.attention_score = 0.0
            continue

        # Детерминированный скор
        score = _base_attention_score(entity, focus, stress)
        entity.attention_score = score

        # Stochastic edge
        if _stochastic_roll(score):
            entity.in_attention = True
            noticed.append(entity)
        else:
            entity.in_attention = False

    return noticed

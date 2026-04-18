"""
app/services/player_cognition/recognition_layer.py
Recognition Layer — идентификация сущностей игроком.

confidence → display_name:
  1.0 → "Торнин"
  0.6 → "кажется, Торнин"
  0.2 → "кто-то знакомый"
  0.0 → "женщина с фартуком" (из visible_markers)

path: /backend/app/services/player_cognition/recognition_layer.py
Назначение: Определяет, как игрок идентифицирует сущность — имя, описание, уверенность
Зависимости: types, scene_state_manager (_npc_id_to_display для имён)
Основные сущности: EncounterHistory, apply_recognition()
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from app.services.player_cognition.types import PerceivedEntity
from app.services.scene_state_manager import _npc_id_to_display


@dataclass
class EncounterHistory:
    """
    История встреч с NPC — in-memory, без персистенции.
    TODO: после реализации PlayerMemory — заменить на persisted версию.
    """
    _encounters: Dict[str, int] = field(default_factory=dict)
    _known_ids: Set[str] = field(default_factory=set)

    def record_encounter(self, npc_id: str) -> None:
        """Записывает встречу с NPC"""
        self._encounters[npc_id] = self._encounters.get(npc_id, 0) + 1
        self._known_ids.add(npc_id)

    def encounter_count(self, npc_id: str) -> int:
        return self._encounters.get(npc_id, 0)

    def is_known(self, npc_id: str) -> bool:
        return npc_id in self._known_ids


# === Описания по visible_markers ===
# Используются когда имя неизвестно
_MARKER_DESCRIPTIONS: Dict[str, str] = {
    "apron": "фартук",
    "keys": "ключи",
    "armor": "доспех",
    "sword": "меч",
    "weapon": "оружие",
    "helmet": "шлем",
    "cloak": "плащ",
    "robe": "мантия",
    "uniform": "униформа",
    "badge": "значок",
}

# Род по маркерам — грубая эвристика
_FEMININE_MARKERS = {"apron", "dress", "skirt", "heels"}
_MASCULINE_MARKERS = {"armor", "sword", "helmet", "beard"}


def _generic_description(npc_id: str, raw: dict) -> str:
    """
    Генерирует описание незнакомого NPC по visible_markers и id.
    "женщина с фартуком", "стражник в доспехе"
    """
    markers: List[str] = raw.get("visible_markers") or []
    described_markers: List[str] = []

    gender_word: Optional[str] = None
    for m in markers:
        if m in _FEMININE_MARKERS and not gender_word:
            gender_word = "женщина"
        elif m in _MASCULINE_MARKERS and not gender_word:
            gender_word = "мужчина"

    if not gender_word:
        gender_word = "человек"

    for m in markers:
        desc = _MARKER_DESCRIPTIONS.get(m)
        if desc:
            described_markers.append(desc)

    if described_markers:
        return f"{gender_word} с {', '.join(described_markers)}"
    return gender_word


def _compute_recognition_confidence(
    clarity: float,
    encounter_count: int,
    is_focused: bool,
) -> float:
    """
    Вычисляет уверенность в идентификации.
    Множество встреч повышает уверенность, низкая clarity снижает.
    """
    # Базовая уверенность от чёткости восприятия
    confidence = clarity

    # Бонус от количества встреч (logarithmic — насыщается)
    if encounter_count > 0:
        import math
        encounter_bonus = min(math.log2(encounter_count + 1) * 0.2, 0.3)
        confidence += encounter_bonus

    # Фокус — гарантированный минимум
    if is_focused and encounter_count > 0:
        confidence = max(confidence, 0.5)

    return max(0.0, min(1.0, confidence))


def _format_display_name(
    true_name: str,
    confidence: float,
    generic_desc: str,
) -> str:
    """
    Форматирует имя по confidence.
    1.0 → "Торнин"
    0.6 → "кажется, Торнин"
    0.2 → "кто-то знакомый"
    0.0 → generic_desc
    """
    if confidence >= 0.85:
        return true_name
    elif confidence >= 0.5:
        return f"кажется, {true_name}"
    elif confidence >= 0.25:
        return "кто-то знакомый"
    else:
        return generic_desc


def apply_recognition(
    entities: List[PerceivedEntity],
    encounter_history: Optional[EncounterHistory] = None,
) -> None:
    """
    Заполняет Recognition Layer на каждой PerceivedEntity.
    Для невидимых/audio_only — пропускает.

    Мутирует entities in-place.
    """
    if encounter_history is None:
        encounter_history = EncounterHistory()

    for entity in entities:
        # Невидимые — не распознаются визуально
        if not entity.visible:
            continue

        # Объекты — показываем имя напрямую без системы узнавания
        if entity.entity_type == "object":
            raw = entity._raw_data
            entity.display_name = raw.get("name", entity.entity_id)
            entity.recognition_confidence = entity.clarity
            continue

        # NPC — полная система распознавания
        if entity.entity_type == "npc":
            raw = entity._raw_data
            true_name = _npc_id_to_display(entity.entity_id)
            generic_desc = _generic_description(entity.entity_id, raw)

            encounters = encounter_history.encounter_count(entity.entity_id)
            confidence = _compute_recognition_confidence(
                clarity=entity.clarity,
                encounter_count=encounters,
                is_focused=entity.in_attention,
            )

            display = _format_display_name(true_name, confidence, generic_desc)

            entity.display_name = display
            entity.recognition_confidence = confidence

            # Записываем встречу если распознан хотя бы немного
            if confidence >= 0.3:
                encounter_history.record_encounter(entity.entity_id)
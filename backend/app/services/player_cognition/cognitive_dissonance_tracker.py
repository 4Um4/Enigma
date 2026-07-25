"""
Файл: backend/app/services/player_cognition/cognitive_dissonance_tracker.py
Назначение: Обнаружение противоречий на основе истории действий.
Зависимости: typing, app.models.cognitive_dissonance, app.models.player_action
"""

from typing import List, Set, Tuple

from app.models.cognitive_dissonance import Contradiction
from app.models.player_action import ActionType, PlayerAction


class CognitiveDissonanceTracker:
    """Отслеживает противоречия в действиях игрока (Moral Choices)."""

    # Жёстко заданные правила противоречий (MVP)
    # Формат: (Action A, Action B, Description, Weight)
    _CONTRADICTION_RULES = [
        (ActionType.HELP, ActionType.ATTACK, "Ты помог одному и напал на другого в один день", 0.8),
        (ActionType.HELP, ActionType.BLACKMAIL, "Ты проявил милосердие и тут же прибег к шантажу", 0.7),
        (ActionType.BRIBE, ActionType.ATTACK, "Ты пытался подкупить и перешёл к насилию", 0.5)
    ]

    def __init__(self) -> None:
        self._contradictions: List[Contradiction] = []
        self._processed_pairs: Set[Tuple[str, str]] = set()

    def detect_contradictions(self, actions: List[PlayerAction]) -> List[Contradiction]:
        """Проверяет список действий на наличие противоречий."""
        new_contradictions = []

        for i, action_a in enumerate(actions):
            for action_b in actions[i+1:]:
                # Пропускаем пары с одинаковыми ID или разными акторами (хотя пока только player)
                if action_a.action_id == action_b.action_id:
                    continue

                # Формируем ключ идемпотентности (сортировка ID, чтобы порядок не влиял)
                pair_key = tuple(sorted((action_a.action_id, action_b.action_id)))
                if pair_key in self._processed_pairs:
                    continue

                # Проверяем правила
                for rule_a, rule_b, desc, weight in self._CONTRADICTION_RULES:
                    is_match = (action_a.action_type == rule_a and action_b.action_type == rule_b) or \
                               (action_a.action_type == rule_b and action_b.action_type == rule_a)

                    if is_match:
                        # Проверяем, что действия направлены на разных NPC (иначе это просто смена настроения)
                        if action_a.target_id != action_b.target_id:
                            contradiction = Contradiction(
                                contradiction_id=f"con_{len(self._contradictions) + len(new_contradictions) + 1}",
                                action_a_id=action_a.action_id,
                                action_b_id=action_b.action_id,
                                description=desc,
                                emotional_weight=weight
                            )
                            new_contradictions.append(contradiction)
                            self._processed_pairs.add(pair_key)
                            break # Одно противоречие на пару действий достаточно

        self._contradictions.extend(new_contradictions)
        return new_contradictions

    def get_all_contradictions(self) -> List[Contradiction]:
        return list(self._contradictions)

    @property
    def has_critical_dissonance(self) -> bool:
        """True, если 3+ противоречий (особое сообщение на End-Screen)."""
        return len(self._contradictions) >= 3

# backend/app/services/game/physics_validator.py
"""
Physics Validator — проверяет физическую и магическую возможность действия игрока.
Работает мгновенно (<1 мс) до любого LLM и Python-движка.
Python считает — LLM только рассказывает последствия.
"""

import re
import logging
from typing import NamedTuple, Dict, Any, Callable, Optional

logger = logging.getLogger(__name__)


class ValidationResult(NamedTuple):
    """Результат проверки физики мира."""

    valid: bool
    reason: str = ""  # почему запрещено
    alternative: str = ""  # реалистичная альтернатива (для DM)


class PhysicsValidator:
    """
    Список правил нарушений.
    Формат: (regex_паттерн, bypass_condition, объяснение)
    bypass_condition может быть:
        - lambda char, game_state: bool
        - False (всегда запрещено)
        - True (всегда разрешено — не используется)
    """

    VIOLATION_RULES: list[tuple[str, Callable[[Dict, Dict], bool] | bool, str]] = [
        # === МАГИЯ И СВЕРХЪЕСТЕСТВЕННОЕ ===
        (
            r"лета|полет|полёт|левитир|взлета|парю|парю в воздухе",
            lambda char, _: any(
                s.lower() in ["полёт", "fly", "левитация"]
                for s in char.get("spells", [])
            ),
            "Нельзя летать без заклинания «Полёт» (или аналогичного)",
        ),
        (
            r"телепорт|перемещ|мгновенно перемещ|появляюсь в",
            lambda char, _: any(
                s.lower()
                in ["телепортация", "misty step", "dimension door", "перемещение"]
                for s in char.get("spells", [])
            ),
            "Телепортация требует заклинания (Misty Step / Dimension Door / Teleport)",
        ),
        (
            r"вижу сквозь стен|сквозь стену|рентген|через стены",
            lambda char, _: any(
                ab.lower()
                in ["темновидение", "darkvision", "истинное зрение", "true sight"]
                for ab in char.get("abilities", [])
            ),
            "Нельзя видеть сквозь стены без способности Темновидение или Истинное зрение",
        ),
        (
            r"мгновенно исцеляюсь|полностью восстанавливаю здоровье|hp full|исцеление полностью",
            lambda char, _: any(
                s.lower() in ["лечение", "heal", "cure wounds", "зелье исцеления"]
                for s in char.get("spells", []) + char.get("items", [])
            ),
            "Мгновенное полное исцеление требует заклинания или зелья",
        ),
        (
            r"создаю золото|золото из воздуха|материализую деньги|бесконечное золото",
            False,  # всегда запрещено
            "Создание золота из воздуха невозможно (даже магией иллюзий)",
        ),
        # === ФИЗИЧЕСКАЯ НЕВОЗМОЖНОСТЬ ===
        (
            r"убиваю всех|убить всех в городе|уничтожаю город одним ударом|всех одним ударом",
            False,
            "Невозможно убить всех жителей одним ударом",
        ),
        (
            r"поднимаю (\d+) кг|поднимаю (\d+) килограмм|несу (\d+) кг",
            lambda char, _: self._check_lifting_capacity(char, 500),  # пример 500 кг
            "Слишком тяжёлый вес. Максимум — Сила × 15 фунтов (примерно Сила × 7 кг)",
        ),
        (
            r"поднимаю 500 кг|поднимаю полтонны|несу тонну",
            lambda char, _: (
                char.get("strength", 10) * 15 >= 1102
            ),  # 500 кг ≈ 1102 фунта
            "Невозможно поднять 500 кг без сверхъестественной силы",
        ),
        # === ДОПОЛНИТЕЛЬНЫЕ ПРАВИЛА (можно расширять) ===
        (
            r"дыхание под водой|дышу под водой без заклинания",
            lambda char, _: any(
                s.lower() in ["water breathing", "дыхание под водой"]
                for s in char.get("spells", [])
            ),
            "Дыхание под водой требует заклинания",
        ),
        (
            r"становлюсь невидимым|исчезаю|становлюсь невидим",
            lambda char, _: any(
                s.lower() in ["невидимость", "invisibility"]
                for s in char.get("spells", [])
            ),
            "Невидимость требует заклинания",
        ),
    ]

    @staticmethod
    def _check_lifting_capacity(character: Dict[str, Any], weight_kg: int) -> bool:
        """Проверка подъёмной способности по D&D 5e (Сила × 15 фунтов)."""
        strength = character.get("strength", 10)
        max_pounds = strength * 15
        max_kg = max_pounds * 0.453592  # перевод в кг
        return weight_kg <= max_kg

    def validate(
        self,
        action: str,
        character: Dict[str, Any],
        game_state: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """
        Основной метод.
        Проверяет действие по всем правилам последовательно.
        """
        if not action or not action.strip():
            return ValidationResult(valid=True)

        lower_action = action.lower()
        game_state = game_state or {}

        for pattern, bypass, explanation in self.VIOLATION_RULES:
            if re.search(pattern, lower_action):
                # bypass может быть bool или callable
                if callable(bypass):
                    can_bypass = bypass(character, game_state)
                else:
                    can_bypass = bool(bypass)

                if not can_bypass:
                    alt = self._suggest_alternative(pattern, character)
                    logger.debug(
                        f"PHYSICS VIOLATION: {explanation} | action: {action[:60]}..."
                    )
                    return ValidationResult(
                        valid=False, reason=explanation, alternative=alt
                    )

        # Всё в порядке
        return ValidationResult(valid=True)

    def _suggest_alternative(self, pattern: str, character: Dict[str, Any]) -> str:
        """Предлагает реалистичную альтернативу для DM."""
        if "лета" in pattern or "полет" in pattern:
            return "Можно залезть на крышу, использовать лестницу или дождаться заклинания Полёт."
        if "телепорт" in pattern:
            return "Можно пойти пешком или использовать портал (если есть)."
        if "убиваю всех" in pattern:
            return "Можно атаковать по одному или использовать AoE-заклинание."
        if "поднимаю" in pattern:
            return f"Максимум {character.get('strength', 10) * 7} кг (по правилам D&D)."
        return "Можно сделать похожим, но реалистичным способом."


# Для удобного импорта
validator = PhysicsValidator()

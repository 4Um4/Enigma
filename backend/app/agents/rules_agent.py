# backend/app/agents/rules_agent.py
#
# RulesAgent v2.0 — переработан под архитектуру v8.1
#
# Принцип: чистый Python, 0 мс, никакого LLM.
# Отвечает ровно за одно: определить игромеханические параметры действия.
#
# Что изменилось vs v1:
#   - Возвращает структурированный RulesResult вместо голого dict
#   - Skill check определяется по ActionType (из classifier), не по keywords
#   - DC калиброван по реальным правилам D&D 5e (PHB)
#   - Добавлены advantage/disadvantage условия
#   - Добавлен ability_used — DM знает какую характеристику проверять
#   - Готов к интеграции с EventBus (Phase 3B.1): result совместим со SceneChange

import random
from dataclasses import dataclass, field
from typing import Optional
from app.models.schemas import PlayerAction
from enum import Enum

class ActionType(str, Enum):
    COMBAT            = "COMBAT"
    SANDBOX_PHYSICAL  = "SANDBOX_PHYSICAL"
    SANDBOX_SOCIAL    = "SANDBOX_SOCIAL"
    SANDBOX_MILD      = "SANDBOX_MILD"
    ROMANCE           = "ROMANCE"
    CAPTURE           = "CAPTURE"
    FLEE              = "FLEE"
    LIFE_CHOICE       = "LIFE_CHOICE"
    EXPLORE           = "EXPLORE"
    UNKNOWN           = "UNKNOWN"


# ─── Таблица DC по D&D 5e PHB ───────────────────────────────────────────────
# Trivial=5, Easy=10, Medium=12, Hard=15, VeryHard=20, NearlyImpossible=25
_DC_BY_ACTION_TYPE: dict[str, int] = {
    ActionType.COMBAT.value:          12,   # Атака — AC цели перекрывает, но базово 12
    ActionType.SANDBOX_PHYSICAL.value: 12,  # Физические действия — Easy/Medium
    ActionType.SANDBOX_SOCIAL.value:   14,  # Социальные — Medium (Persuasion/Deception)
    ActionType.SANDBOX_MILD.value:     10,  # Лёгкие действия — Easy
    ActionType.ROMANCE.value:          14,  # Убеждение/обаяние — Medium
    ActionType.CAPTURE.value:          15,  # Захват — Hard (Athletics vs Athletics)
    ActionType.FLEE.value:             12,  # Побег — Medium (Athletics)
    ActionType.LIFE_CHOICE.value:      10,  # Простые решения — Easy
    ActionType.EXPLORE.value:           0,  # Исследование — обычно без броска
    ActionType.UNKNOWN.value:          12,  # Неизвестное — Medium по умолчанию
}

# Какую характеристику/навык использует тип действия
_ABILITY_BY_ACTION_TYPE: dict[str, str] = {
    ActionType.COMBAT.value:           "strength",      # или dexterity для финессе
    ActionType.SANDBOX_PHYSICAL.value: "strength",
    ActionType.SANDBOX_SOCIAL.value:   "charisma",
    ActionType.SANDBOX_MILD.value:     "dexterity",
    ActionType.ROMANCE.value:          "charisma",
    ActionType.CAPTURE.value:          "strength",
    ActionType.FLEE.value:             "dexterity",
    ActionType.LIFE_CHOICE.value:      "wisdom",
    ActionType.EXPLORE.value:          "perception",
    ActionType.UNKNOWN.value:          "intelligence",
}

# Навык D&D 5e по типу действия (для промпта DM)
_SKILL_BY_ACTION_TYPE: dict[str, str] = {
    ActionType.COMBAT.value:           "Athletics",
    ActionType.SANDBOX_PHYSICAL.value: "Athletics",
    ActionType.SANDBOX_SOCIAL.value:   "Persuasion",
    ActionType.SANDBOX_MILD.value:     "Sleight of Hand",
    ActionType.ROMANCE.value:          "Persuasion",
    ActionType.CAPTURE.value:          "Athletics",
    ActionType.FLEE.value:             "Acrobatics",
    ActionType.LIFE_CHOICE.value:      "Insight",
    ActionType.EXPLORE.value:          "Perception",
    ActionType.UNKNOWN.value:          "Intelligence",
}

# Типы действий которые никогда не требуют броска
_NO_ROLL_TYPES = {
    ActionType.EXPLORE.value,
    ActionType.LIFE_CHOICE.value,
}


@dataclass
class SkillCheckResult:
    """Результат одной проверки навыка."""
    player:       str
    action:       str
    action_type:  str
    needs_roll:   bool
    dc:           int         # 0 если броска нет
    ability:      str         # strength / dexterity / charisma / etc.
    skill:        str         # Athletics / Persuasion / etc.
    advantage:    bool = False
    disadvantage: bool = False
    result:       str = ""    # "автоматический успех" / "" если нужен бросок

    def to_dict(self) -> dict:
        return {
            "player":       self.player,
            "action":       self.action,
            "action_type":  self.action_type,
            "needs_roll":   self.needs_roll,
            "dc":           self.dc,
            "ability":      self.ability,
            "skill":        self.skill,
            "advantage":    self.advantage,
            "disadvantage": self.disadvantage,
            "result":       self.result,
        }


class RulesAgent:
    """
    Игромеханика D&D 5e — чистый Python, 0 мс.

    Определяет:
    - нужен ли бросок d20
    - DC (сложность)
    - какую характеристику/навык проверять
    - advantage/disadvantage условия

    НЕ вызывает LLM. НЕ принимает решения за игрока.
    Результат используется DM агентом для нарратива.
    """

    def needs_roll(self, action_type: str) -> bool:
        """
        Нужен ли бросок для данного типа действия.
        EXPLORE и LIFE_CHOICE — автоматический успех.
        Все остальные — проверка навыка.
        """
        return action_type not in _NO_ROLL_TYPES

    def get_dc(self, action_type: str, character: dict | None = None) -> int:
        """
        DC по таблице D&D 5e.
        character — для будущей модификации DC по уровню противника (Phase 3D).
        """
        return _DC_BY_ACTION_TYPE.get(action_type, 12)

    def get_ability(self, action_type: str) -> str:
        return _ABILITY_BY_ACTION_TYPE.get(action_type, "intelligence")

    def get_skill(self, action_type: str) -> str:
        return _SKILL_BY_ACTION_TYPE.get(action_type, "Intelligence")

    def check_advantage(self, action_type: str, character: dict) -> tuple[bool, bool]:
        """
        Возвращает (advantage, disadvantage).
        Правила D&D 5e:
          - advantage при помощи союзника / удачных условиях
          - disadvantage при ослаблении / враждебных условиях
        Сейчас читаем из conditions персонажа.
        Phase 3B.3 расширит это через WorldState.
        """
        conditions = character.get("conditions", [])

        advantage    = "helped" in conditions or "inspired" in conditions
        disadvantage = any(c in conditions for c in [
            "prone", "blinded", "frightened", "poisoned", "exhausted",
            "restrained", "лежит", "ослеплён", "напуган", "отравлен",
        ])

        # Advantage и disadvantage одновременно — нейтрализуют друг друга
        if advantage and disadvantage:
            return False, False

        return advantage, disadvantage

    def resolve(self, dice_roll: int, dc: int) -> str:
        """
        Разрешает проверку навыка по результату броска.
        Возвращает: "критический успех" / "успех" / "частичный успех" / "провал"
        """
        if dice_roll == 20:
            return "критический успех"
        if dice_roll >= dc:
            return "успех"
        if dice_roll >= dc - 3:
            return "частичный успех"
        return "провал"

    def run(
        self,
        actions: list[PlayerAction],
        shared_context: dict | None = None,
    ) -> dict:
        """
        Основной метод — оценивает все действия за ход.

        Возвращает:
            {
                "checks": [SkillCheckResult.to_dict(), ...],
                "summary": "краткая строка для DM промпта"
            }
        """
        checks = []

        for action in actions:
            action_type = ActionType.UNKNOWN.value
            # Берём тип из shared_context если есть (classifier уже отработал)
            if shared_context:
                for cls in shared_context.get("classification", []):
                    if cls.get("player") == action.player_name:
                        action_type = cls.get("type", ActionType.UNKNOWN.value)
                        break

            character = {}
            if shared_context:
                python_engines = shared_context.get("python_engines", {})
                character = python_engines.get(action.player_name, {})

            roll_needed = self.needs_roll(action_type)
            dc          = self.get_dc(action_type, character) if roll_needed else 0
            ability     = self.get_ability(action_type)
            skill       = self.get_skill(action_type)
            adv, dis    = self.check_advantage(action_type, character)

            check = SkillCheckResult(
                player      = action.player_name,
                action      = action.action,
                action_type = action_type,
                needs_roll  = roll_needed,
                dc          = dc,
                ability     = ability,
                skill       = skill,
                advantage   = adv,
                disadvantage = dis,
                result      = self.resolve(
                    random.randint(2, 20) if not adv and not dis
                    else max(random.randint(2, 20), random.randint(2, 20)) if adv
                    else min(random.randint(2, 20), random.randint(2, 20)),
                    dc
                ) if roll_needed else "автоматический успех",
            )
            checks.append(check)

        # Краткий summary для DM промпта (одна строка, не эссе)
        summary_parts = []
        for c in checks:
            if c.needs_roll:
                adv_str = " (advantage)" if c.advantage else (" (disadvantage)" if c.disadvantage else "")
                summary_parts.append(
                    f"{c.player}: {c.skill} DC{c.dc}{adv_str}"
                )
            else:
                summary_parts.append(f"{c.player}: автоуспех")

        return {
            "checks":  [c.to_dict() for c in checks],
            "summary": " | ".join(summary_parts),
        }

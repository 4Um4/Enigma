"""
npc_response_validator.py — валидатор для NPC речи.

Принцип: если NPC-промпт нарушен — используем intent-specific fallback.
Это лучше чем "Ничего не произошло" для NPC.

ЗАЧЕМ:
- NPC всегда говорит/действует согласно intent
- Fallback-шаблоны выглядят естественно
- Критично для 7B моделей

Путь: backend/app/services/verbalization/npc_response_validator.py
Назначение: Валидация NPC-речи с fallback по intent
Зависимости: response_validator, state_interpreter (INTENT_DESCRIPTIONS)
Основные сущности: NPCResponseValidator

TODO: можно расширить на разные типы нарушений (не только empty/dialog для немых NPC), добавив больше шаблонов в _MUTED_FALLBACKS и отдельные методы валидации.
"""

from typing import Optional

from app.services.verbalization.response_validator import ResponseValidator, ValidationResult
from app.services.verbalization.state_interpreter import INTENT_DESCRIPTIONS


# Fallback-шаблоны по intent — человекочитаемые, естественные
_INTENT_FALLBACKS: dict[str, str] = {
    "flee": "{name} вскрикивает и отступает назад.",
    "attack": "{name} встаёт в боевую стойку.",
    "talk": "{name} поднимает руку, привлекая внимание.",
    "warn": "{name} указывает в сторону опасности.",
    "intimidate": "{name} делает шаг вперёд, нависая над тобой.",
    "help": "{name} протягивает руку.",
    "observe": "{name} внимательно смотрит на тебя.",
    "explain": "{name} собирается с мыслями.",
    "hide": "{name} прижимается к стене, стараясь не шевелиться.",
    "trade": "{name} достаёт что-то из-за пазухи.",
    "report": "{name} озирается по сторонам.",
    "block_path": "{name} расставляет ноги шире, преграждая путь.",
    "ambush": "{name} замирает в тени.",
    "seek_ally": "{name} оглядывается в поисках кого-то.",
    "offer_job": "{name} склоняет голову набок, оценивая.",
    "request_service": "{name} смеётся, готовясь к просьбе.",
    "spread_rumor": "{name} наклоняется ближе, понижая голос.",
    "call_for_help": "{name} делает глубокий вдох.",
    "idle": "{name} стоит безучастно.",
    "approach": "{name} делает несколько шагов навстречу.",
}

# Fallback когда can_speak=False
_MUTED_FALLBACKS: dict[str, str] = {
    "flee": "{name} бледнеет и пятится назад.",
    "attack": "{name} сжимает кулаки.",
    "talk": "{name} открывает рот, но не издаёт звука.",
    "warn": "{name} дёргается, указывая в сторону опасности.",
    "intimidate": "{name} хмурится, делая угрожающий жест.",
    "help": "{name} кивает в поддержку.",
    "observe": "{name} пристально смотрит.",
    "approach": "{name} молча подходит ближе.",
}


class NPCResponseValidator(ResponseValidator):
    """
    Валидатор для NPC-речи с intent-specific fallback.
    """
    
    def __init__(
        self,
        contract: "NarrativeContractProtocol",
        npc_name: str,
        intent: str,
    ) -> None:
        super().__init__(contract)
        self._npc_name = npc_name
        self._intent = intent.lower()
    
    def _get_fallback_text(self) -> str:
        """Возвращает fallback по intent и can_speak."""
        # Для неслучайных intents — специфичный fallback
        specific = _INTENT_FALLBACKS.get(self._intent)
        if specific:
            return specific.format(name=self._npc_name)
        
        # Fallback на базовый intent-описание
        intent_desc = INTENT_DESCRIPTIONS.get(self._intent, "наблюдает")
        return f"{self._npc_name} {intent_desc}."
    
    def validate_muted(self, raw_response: str) -> ValidationResult:
        """
        Валидация для NPC без возможности говорить.
        Использует отдельный набор fallback'ов.
        """
        text = raw_response.strip() if raw_response else ""
        
        if not text:
            return self._muted_fallback("empty")
        
        if self._contains_dialog(text):
            # Попытка убрать диалог
            cleaned = self._force_action(text)
            if cleaned and not self._contains_dialog(cleaned):
                return ValidationResult(text=cleaned, is_fallback=False)
            return self._muted_fallback("dialog_when_muted")
        
        return ValidationResult(text=text, is_fallback=False)
    
    def _muted_fallback(self, reason: str) -> ValidationResult:
        """Fallback для немого NPC."""
        fallback = _MUTED_FALLBACKS.get(self._intent, f"{self._npc_name} молча реагирует.")
        return ValidationResult(
            text=fallback.format(name=self._npc_name),
            is_fallback=True,
            violation=reason,
        )
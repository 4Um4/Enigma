"""
response_validator.py — валидация ответа LLM + fallback.

Принцип: LLM — ненадёжный компонент. Каждый ответ проверяется.
При нарушении контракта — мгновенный fallback, никаких retry.

ЗАЧЕМ:
- Стабильность на 7B моделях
- Гарантия что NPC не скажет то, что не должен
- Предсказуемый output для game loop

Путь: backend/app/services/verbalization/response_validator.py
Назначение: Проверка и исправление ответа LLM согласно контракту
Зависимости: contract_base (NarrativeContractProtocol)
Основные сущности: ValidationResult, ResponseValidator
"""

from dataclasses import dataclass
from typing import Optional

from app.services.verbalization.contract_base import NarrativeContractProtocol


@dataclass
class ValidationResult:
    """Результат валидации."""
    text: str
    is_fallback: bool
    violation: Optional[str] = None  # описание нарушения


class ResponseValidator:
    """
    Валидирует ответ LLM по контракту.
    
    Инварианты:
    1. Пустой ответ → fallback
    2. Превышен лимит предложений → обрезать
    3. can_speak=False + диалог → превратить в действие
    4. can_move=False + движение → превратить в статичную реакцию
    5. Повтор → fallback
    """
    
    def __init__(self, contract: NarrativeContractProtocol) -> None:
        self._contract = contract
        self._max_chars = contract.max_sentences * 120  # ~120 симв/предложение
    
    def validate(
        self,
        raw_response: str,
        can_speak: bool = True,
        can_move: bool = True,
        recent_text: Optional[str] = None,
    ) -> ValidationResult:
        """Основной метод валидации."""
        text = raw_response.strip() if raw_response else ""
        
        # 1. Пустой ответ
        if not text:
            return self._fallback("empty")
        
        # 2. Повтор недавнего текста
        if recent_text and self._is_repeat(text, recent_text):
            return self._fallback("repeat")
        
        # 3. Слишком длинно
        if len(text) > self._max_chars:
            text = self._truncate(text)
        
        # 4. can_speak=False но есть диалог
        if not can_speak and self._contains_dialog(text):
            text = self._force_action(text)
            if not text:
                return self._fallback("cannot_speak")
        
        # 5. can_move=False но есть движение
        if not can_move and self._contains_movement(text):
            text = self._force_static(text)
            if not text:
                return self._fallback("cannot_move")
        
        # 6. Проверка forbidden actions
        violation = self._check_forbidden(text)
        if violation:
            return self._fallback(violation)
        
        return ValidationResult(
            text=text,
            is_fallback=False,
        )
    
    def _is_repeat(self, text: str, recent: str) -> bool:
        """Простая проверка повтора (нормализация + совпадение начала)."""
        norm_text = text.lower()[:50]
        norm_recent = recent.lower()[:50]
        return norm_text == norm_recent
    
    def _truncate(self, text: str) -> str:
        """Обрезает до лимита предложений."""
        max_sent = self._contract.max_sentences
        sentences = text.replace('!', '.').replace('?', '.').split('.')
        truncated = '. '.join(s.strip() for s in sentences[:max_sent] if s.strip())
        return truncated + '.' if not truncated.endswith('.') else truncated
    
    def _contains_dialog(self, text: str) -> bool:
        """Проверяет наличие диалога."""
        return '"' in text or '«' in text or '—' in text[:10]
    
    def _force_action(self, text: str) -> str:
        """Убирает диалог, превращает в действие."""
        # Убираем кавычки и прямую речь
        result = text
        for char in ['"', '«', '»']:
            result = result.replace(char, '')
        # Убираем паттерн "— Слова"
        if '—' in result[:15]:
            result = result[result.index('—') + 1:].strip()
        # Если после очистки ничего нет — fallback
        if len(result) < 10:
            return ""
        return result
    
    def _contains_movement(self, text: str) -> bool:
        """Проверяет наличие описания движения."""
        movement_words = (
            "подходит", "отходит", "бегает", "убегает", "идёт", "идет",
            "подошёл", "подошел", "отошёл", "отошел", "побежал", "встаёт",
            "встает", "садится", "присел", "наклонился", "поднялся",
        )
        lower = text.lower()
        return any(w in lower for w in movement_words)
    
    def _force_static(self, text: str) -> str:
        """Заменяет движение на статичную реакцию."""
        replacements = {
            "подходит": "смотрит на",
            "отходит": "отворачивается",
            "бегает": "мечется взглядом",
            "убегает": "жмётся к месту",
            "идёт": "стоит",
            "идет": "стоит",
            "встаёт": "сидит/лежит",
            "встает": "сидит/лежит",
            "побежал": "дернулся",
        }
        result = text
        for old, new in replacements.items():
            result = result.replace(old, new)
        return result
    
    def _check_forbidden(self, text: str) -> Optional[str]:
        """Проверяет forbidden actions из контракта."""
        lower = text.lower()
        for forbidden in self._contract.forbidden_actions:
            if forbidden in lower:
                return forbidden
        return None
    
    def _fallback(self, reason: str) -> ValidationResult:
        """Возвращает fallback результат."""
        # Универсальный fallback — можно переопределить через наследование
        fallback_text = self._get_fallback_text()
        return ValidationResult(
            text=fallback_text,
            is_fallback=True,
            violation=reason,
        )
    
    def _get_fallback_text(self) -> str:
        """Базовый fallback. Переопределяется в подклассах по intent."""
        return "Ничего не произошло."
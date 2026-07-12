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

import re
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

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
        allowed_moving_npcs: Optional[set] = None,
    ) -> ValidationResult:
        """Основной метод валидации."""
        text = raw_response.strip() if raw_response else ""

        # 1. Пустой ответ
        if not text:
            return self._fallback("empty")

        # 2. Не-русский текст (китайские иероглифы, мусор)
        if self._contains_non_russian(text):
            return self._fallback("non_russian")

        # 3. Повтор недавнего текста
        if recent_text and self._is_repeat(text, recent_text):
            return self._fallback("repeat")

        # 3.5 4-я стена (Hardcoded Invariant)
        if self._breaks_fourth_wall(text):
            return self._fallback("fourth_wall")

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
            # B5-FIX: Вызов _force_static удалён, так как метод deprecated (no-op).
            if not text:
                return self._fallback("cannot_move")

        # 5.5 Инвариант 2: Движение без подтверждения (Hallucination Guard)
        # Применяем только если есть список двигавшихся NPC. Иначе мы не можем верифицировать.
        if allowed_moving_npcs:
            text = self._filter_unauthorized_movement(text, allowed_moving_npcs)
            if not text:
                return self._fallback("unauthorized_movement_only")

        # 6. Проверка forbidden actions
        violation = self._check_forbidden(text)
        if violation:
            return self._fallback(violation)

        # 7. Очистка системных маркеров (whisper, [internal], *thought*)
        # Frontend определяет DeliveryType по ним, но сами маркеры не должны попадать в текст реплики.
        text = self._strip_delivery_markers(text)

        return ValidationResult(
            text=text,
            is_fallback=False,
        )

    _CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uff00-\uffef]")
    _FOURTH_WALL_WORDS = [
        "игрок",
        "игроки",
        "симуляция",
        "система",
        "механика",
        "интерфейс",
    ]
    _DELIVERY_MARKERS_RE = re.compile(
        r"^\s*[\(\[\*]\s*(whisper|internal|thought|шёпот|мысль|шепчет)\s*[\)\]\*]\s*[:\-]?\s*",
        re.IGNORECASE,
    )
    # BUG-P1-10: Word boundaries, чтобы не резать "игроков" или "системой"
    _FOURTH_WALL_RE = re.compile(
        r"\b(?:" + "|".join(_FOURTH_WALL_WORDS) + r")\b", re.IGNORECASE
    )

    def _strip_delivery_markers(self, text: str) -> str:
        """Удаляет маркеры доставки (whisper, [internal], *thought*) из начала текста."""
        return self._DELIVERY_MARKERS_RE.sub("", text).strip()

    def _breaks_fourth_wall(self, text: str) -> bool:
        """Жёсткий запрет на упоминание игровой механики (4-я стена)."""
        return bool(self._FOURTH_WALL_RE.search(text))

    def _contains_non_russian(self, text: str) -> bool:
        """A6-FIX: Отклоняет CJK, Mock-утечки и некириллический мусор."""
        if self._CJK_PATTERN.search(text):
            return True
        if "[Mock]" in text or "[mock]" in text:
            return True

        alpha_total = sum(1 for c in text if c.isalpha())
        if alpha_total <= 10:
            return False

        cyrillic_chars = sum(1 for c in text if "\u0400" <= c <= "\u04ff")
        # Если кириллицы меньше 50% — текст не русский (отсеивает англ. мусор, пропуская термины)
        if cyrillic_chars / alpha_total < 0.5:
            return True

        return False

    def _is_repeat(self, text: str, recent: str) -> bool:
        """Простая проверка повтора (нормализация + совпадение начала)."""
        norm_text = text.lower()[:50]
        norm_recent = recent.lower()[:50]
        return norm_text == norm_recent

    def _truncate(self, text: str) -> str:
        """Обрезает до лимита предложений."""
        max_sent = self._contract.max_sentences
        sentences = text.replace("!", ".").replace("?", ".").split(".")
        truncated = ". ".join(s.strip() for s in sentences[:max_sent] if s.strip())
        return truncated + "." if not truncated.endswith(".") else truncated

    def _contains_dialog(self, text: str) -> bool:
        """A5-FIX: убрано ложное срабатывание на тире (DM-нарратив)."""
        return '"' in text or "«" in text

    def _force_action(self, text: str) -> str:
        """Убирает диалог, превращает в действие."""
        # Убираем кавычки и прямую речь
        result = text
        for char in ['"', "«", "»"]:
            result = result.replace(char, "")
        # Убираем паттерн "— Слова"
        if "—" in result[:15]:
            result = result[result.index("—") + 1 :].strip()
        # Если после очистки ничего нет — fallback
        if len(result) < 10:
            return ""
        return result

    def _contains_movement(self, text: str) -> bool:
        """Проверяет наличие описания движения."""
        movement_words = (
            "подходит",
            "отходит",
            "бегает",
            "убегает",
            "идёт",
            "идет",
            "подошёл",
            "подошел",
            "отошёл",
            "отошел",
            "побежал",
            "встаёт",
            "встает",
            "садится",
            "присел",
            "наклонился",
            "поднялся",
            "направился",
            "пошел",
            "пошёл",
            "двинулся",
            "шагнул",
        )
        lower = text.lower()
        return any(w in lower for w in movement_words)

    def _filter_unauthorized_movement(self, text: str, allowed_npcs: set) -> str:
        """Инвариант 2: Вырезает предложения с движением NPC, если их нет в allowed_npcs."""
        import re

        sentences = re.split(r"(?<=[.!?])\s+", text)
        valid_sentences = []

        for sent in sentences:
            lower_sent = sent.lower()
            if self._contains_movement(lower_sent):
                # Проверяем, есть ли в предложении имя разрешённого NPC
                is_allowed = any(
                    npc_name.lower() in lower_sent for npc_name in allowed_npcs
                )
                if not is_allowed:
                    # Если NPC не разрешён, вырезаем предложение (переводим в намерение)
                    # Пока просто вырезаем, чтобы не ломать грамматику
                    continue
            valid_sentences.append(sent)

        return " ".join(valid_sentences).strip()

    def _force_static(self, text: str) -> str:
        """B5-FIX: DEPRECATED. Убраны replacements — они ломают Инвариант 2.

        Раньше: заменял 'подходит' → 'смотрит на', если can_move=False.
        Проблема: DM-контракт содержит РЕАЛЬНЫЕ перемещения NPC (через SceneChange).
        Замена маскировала реальное движение.

        Теперь: no-op. Если NPC не может двигаться, SceneChange не создаётся,
        и DM-контракт не содержит информации о движении.
        """
        return text

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

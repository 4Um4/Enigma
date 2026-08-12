"""
Файл: backend/app/services/input/intent_compressor.py
Назначение: Извлечение IntentSemanticField из сырого текста. Fast Path (детерминированный) + Slow Path (LLM).
Зависимости: domain.intent_profile, services.input.llm_compressor_client
Основные сущности: IntentCompressor

TODO: В будущем IntentCompressor может быть расширен для поддержки более сложных схем извлечения, таких как использование нескольких моделей (например, специализированные модели для разных типов интентов), адаптивные стратегии промптинга (например, уточняющие вопросы при высокой неопределенности) и более богатые семантические поля (например, социальные интенты, скрытые мотивы). Но для MVP достаточно базового компрессора с детерминированным Fast Path и LLM Slow Path.

"""

import re
from typing import Any, Dict, Optional

from app.domain.intent_profile import (
    ActionType,
    ConfidenceVector,
    EmotionalVector,
    IntentSemanticField,
    SemanticAmbiguity,
    TargetZone,
)
from app.services.input.llm_compressor_client import LLMCompressorClient

try:
    import pymorphy3

    MORPH = pymorphy3.MorphAnalyzer()
    PYMORPHY_AVAILABLE = True
except ImportError:
    MORPH = None
    PYMORPHY_AVAILABLE = False

# Словари лемм для детерминированного матчера (оба вида глаголов)
_ACTION_LEMMAS = {
    ActionType.MOVE: {
        "пойти",
        "идти",
        "подойти",
        "подходить",
        "перейти",
        "переходить",
        "бежать",
        "бегать",
        "шагнуть",
        "шагать",
        "приблизиться",
        "приближаться",
        "сопровождать",
        "сопровождай",
        "следовать",
        "следуй",
        "выйти",
        "выходить",
        "покинуть",
        "войти",
        "входить",
        "отойди",
        "отступить",
        "отступай",
        "посторониться",
        "посторонись",
    },
    ActionType.OBSERVE: {
        "осмотреть",
        "осматривать",
        "изучить",
        "изучать",
        "посмотреть",
        "смотреть",
        "оглядеть",
        "оглядывать",
        "увидеть",
        "видеть",
        "заметить",
        "замечать",
        "рассмотреть",
        "рассматривать",
    },
    ActionType.INTERACT: {
        "взять",
        "брать",
        "открыть",
        "открывать",
        "использовать",
        "пользоваться",
        "положить",
        "класть",
        "дать",
        "давать",
        "поднять",
        "поднимать",
    },
    ActionType.ATTACK: {
        "бить",
        "выбить",
        "побить",
        "избить",
        "отбить",
        "пробить",
        "разбить",
        "забить",
        "добить",
        "отколотить",
        "наказать",
        "прикончить",
        "замахнуться",
        "ударить",
        "ударять",
        "атаковать",
        "врезать",
        "убить",
        "убивать",
        "поразить",
        "поражать",
        "рубить",
        "колоть",
        "расправиться",
        "калечить",
        "покалечить",
        "искалечить",
        "укусить",
        "кусать",
        "откусить",
        "откусывать",
        "покусать",
        "отгрызть",
        "грызть",
        "цапнуть",
        "расцарапать",
        "царапать",
        "душить",
        "задушить",
        "толкнуть",
        "толкать",
        "пнуть",
        "пинать",
        "плевать",
        "оплевать",
        "стукнуть",
        "шлёпнуть",
        "дать",
        "заехать",
        "вмазать",
    },
    ActionType.THREATEN: {
        "угрожать",
        "пригрозить",
        "пугать",
        "напугать",
        "запугивать",
        "запугать",
        "шантажировать",
        "пристрастить",
        "устрашить",
        "устрашать",
    },
    ActionType.PERSUADE: {
        "уговаривать",
        "уговорить",
        "убеждать",
        "убедить",
        "просить",
        "попросить",
        "умолять",
    },
}

# Плоский словарь всех лемм действий, чтобы не принять слово "удар" за цель
_ACTION_LEMMAS_FLAT = set(lemma for s in _ACTION_LEMMAS.values() for lemma in s)

_INTENSITY_LEMMAS = {
    # ИСПРАВЛЕНО: убраны 'весь' (местоимение — 'весь день' давало false positive
    # high intensity) и 'дурь' (существительное — 'дурь прошла' давало false positive).
    # Добавлены реальные маркеры высокой интенсивности.
    "high": {
        "резко",
        "сильно",
        "мощно",
        "яростно",
        "немедленно",
        "живо",
        "приказываю",
        "быстро",
        "исступлённо",
        "неистово",
        "бешено",
        "стремительно",
        "мгновенно",
        "беспощадно",
    },
    "low": {
        "осторожно",
        "медленно",
        "тихо",
        "аккуратно",
        "слегка",
        "немного",
        "плавно",
        "мягко",
    },
}


class IntentCompressor:
    """Слой 1: Сжатие языка в IntentSemanticField."""

    def __init__(self, llm_client: LLMCompressorClient):
        self._llm_client = llm_client

    async def compress(
        self, raw_text: str, scene_context: Dict[str, Any]
    ) -> IntentSemanticField:
        fast_result = self._fast_path_parse(raw_text)
        if fast_result is not None:
            return fast_result
        return await self._slow_path_parse(raw_text, scene_context)

    def _lemmatize(self, text: str) -> set:
        """Разбивает текст на токены и приводит к начальной форме (лемме)."""
        if not PYMORPHY_AVAILABLE:
            return set(text.lower().split())
        tokens = re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", text.lower())
        lemmas = set()
        for token in tokens:
            parsed = MORPH.parse(token)
            if parsed:
                lemmas.add(parsed[0].normal_form)
            else:
                lemmas.add(token)
        return lemmas

    def _fast_path_parse(self, raw_text: str) -> Optional[IntentSemanticField]:
        lemmas = self._lemmatize(raw_text)

        matched_action = None
        for action_type, action_lemmas in _ACTION_LEMMAS.items():
            if not lemmas.isdisjoint(action_lemmas):
                matched_action = action_type
                break

        if not matched_action:
            return None

        physical = 0.4
        emotional = 0.1
        if not lemmas.isdisjoint(_INTENSITY_LEMMAS["high"]):
            physical = 0.9
            emotional = 0.6
        elif not lemmas.isdisjoint(_INTENSITY_LEMMAS["low"]):
            physical = 0.2

        # Извлечение цели: ищем строго существительное (NOUN), игнорируя местоимения (мне/тебя)
        target_ref = None
        if PYMORPHY_AVAILABLE:
            tokens_raw = re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", raw_text)
            for token in tokens_raw:
                parsed = MORPH.parse(token.lower())
                # NOUN = существительное. Исключаем глаголы-существительные (например, "удар")
                if (
                    parsed
                    and parsed[0].tag.POS == "NOUN"
                    and parsed[0].normal_form not in _ACTION_LEMMAS_FLAT
                ):
                    target_ref = (
                        token.lower()
                    )  # Нормализуем в нижний регистр для fuzzy matching
                    break

            # GAP11 FIX: Если NOUN не найден, но есть наречия/местоимения 1-го лица -> цель "player"
            if not target_ref:
                _player_indicators = {"сюда", "ко", "мне", "меня", "нас", "нами"}
                if not lemmas.isdisjoint(_player_indicators):
                    target_ref = "player"

        # ADR-035 FIX: Fast Path обязан генерировать вектор эмоций, иначе Труба Воли мертва
        _semantic = EmotionalVector()  # дефолт
        if matched_action == ActionType.ATTACK:
            _semantic = EmotionalVector(aggression=0.8, confidence=0.8)
        elif matched_action == ActionType.THREATEN:
            _semantic = EmotionalVector(aggression=0.5, fear=0.3, confidence=0.7)
        elif matched_action == ActionType.MOVE:
            _semantic = EmotionalVector(confidence=0.6)

        # ADR-O-315: Fast path по умолчанию считает актора игроком ("я"),
        # если в тексте нет явного указания на 3-е лицо ("пусть торнин уйдёт").
        _actor_ref = "player"
        _third_person_indicators = {"он", "она", "оно", "они", "пусть"}

        # S97 FIX: Обработка прямых обращений ("Торнин, отойди к двери")
        # Если текст содержит запятую и первое слово — существительное, это обращение к NPC.
        if "," in raw_text:
            tokens_raw = re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", raw_text)
            if tokens_raw:
                first_token = tokens_raw[0]
                if PYMORPHY_AVAILABLE:
                    parsed = MORPH.parse(first_token.lower())
                    if parsed and parsed[0].tag.POS == "NOUN":
                        # Первое слово — имя/существительное, значит актор — этот NPC
                        _actor_ref = first_token.lower()

        if not lemmas.isdisjoint(_third_person_indicators):
            _actor_ref = target_ref if target_ref else _actor_ref

        return IntentSemanticField(
            action_type=matched_action,
            actor_reference=_actor_ref,
            target_reference=target_ref,
            raw_text=raw_text,
            physical_force=physical,
            emotional_charge=emotional,
            semantic=_semantic,  # ИНЪЕКЦИЯ ЖИВОГО ВЕКТОРА
            confidence=ConfidenceVector(
                action=0.9, parse=1.0, target=0.8 if target_ref else 0.3, emotion=0.5
            ),
            ambiguity=SemanticAmbiguity.PARTIAL,
        )

    async def _slow_path_parse(
        self, raw_text: str, scene_context: Dict[str, Any]
    ) -> IntentSemanticField:
        llm_response = await self._llm_client.compress_intent(raw_text, scene_context)

        if llm_response is None:
            # S97 FIX: Fallback если LLM недоступна (502 Bad Gateway) — пытаемся извлечь актора локально
            _fast_result = self._fast_path_parse(raw_text)
            if _fast_result:
                return _fast_result

            return IntentSemanticField(
                action_type=ActionType.UNCERTAIN,
                raw_text=raw_text,
                confidence=ConfidenceVector(
                    parse=0.1, target=0.0, emotion=0.0, action=0.1
                ),
                ambiguity=SemanticAmbiguity.AMBIGUOUS,
            )

        try:
            return IntentSemanticField(
                action_type=llm_response.get("action_type", ActionType.UNCERTAIN),
                actor_reference=llm_response.get("actor_reference"),
                target_reference=llm_response.get("target_reference"),
                target_zone=llm_response.get("target_zone", TargetZone.UNDEFINED),
                physical_force=float(llm_response.get("physical_force", 0.5)),
                emotional_charge=float(llm_response.get("emotional_charge", 0.5)),
                social_pressure=float(llm_response.get("social_pressure", 0.0)),
                commitment_level=float(llm_response.get("commitment_level", 0.8)),
                tool_reference=llm_response.get("tool_reference"),
                semantic=EmotionalVector(**llm_response.get("semantic", {})),
                raw_text=raw_text,
                confidence=ConfidenceVector(
                    parse=0.8, target=0.6, emotion=0.7, action=0.8
                ),
            )
        except Exception as _parse_err:
            # ИСПРАВЛЕНО: раньше except Exception: pass молча возвращал UNCERTAIN.
            # Любая ошибка в структуре LLM-ответа (KeyError, TypeError, pydantic
            # ValidationError) → теряли весь LLM-ответ без WARN-лога. Теперь логируем
            # raw response + тип ошибки.
            import logging

            _logger = logging.getLogger(__name__)
            _logger.warning(
                f"[INTENT_COMPRESSOR] slow_path_parse failed: "
                f"{type(_parse_err).__name__}: {_parse_err}. "
                f"Raw LLM response: {llm_response}"
            )
            return IntentSemanticField(
                action_type=ActionType.UNCERTAIN,
                raw_text=raw_text,
                confidence=ConfidenceVector(
                    parse=0.3, target=0.1, emotion=0.1, action=0.3
                ),
                ambiguity=SemanticAmbiguity.AMBIGUOUS,
            )

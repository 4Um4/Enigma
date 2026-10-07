"""
Нормализатор декомпозиции хроники (ADR-O-420, CCH-2).

Файл: backend/app/services/chronicle/decomposition_normalizer.py
Назначение: сырой ответ LLM → валидированный BiographyDecomposition.
            Прецедент DMResponseNormalizer (снятие markdown, depth-1 decode).
            ЗАПРЕТ silent fallback (DTO Registry, поток 1): невалидный ответ —
            DecompositionError, не "пустой разбор".
Зависимости: app.domain.chronicle
Основные сущности: ChronicleDecompositionNormalizer, DecompositionError
"""
from __future__ import annotations

import json
import re
from typing import Any, Final, List, Mapping

from app.domain.chronicle import (
    ClarificationOption,
    ClarificationQuestion,
    DecompositionItem,
    EntryKind,
)

_MD_JSON: Final[re.Pattern] = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_BARE_JSON: Final[re.Pattern] = re.compile(r"\{.*\}", re.DOTALL)

_ALLOWED_KEYS: Final[frozenset] = frozenset(
    {"items", "schema_version", "chronicle_id", "fragment_ord"}
)

# Закрытый реестр маркеров неточной связи (ADR-O-420): модель, уверенная в
# расплывчатой связи, переоценивает себя — мембрана требует решения автора.
# Расширение реестра = ревизия ADR (не молча).
_VAGUE_RELATION_MARKERS: Final[tuple] = (
    "дальний родственник",
    "дальняя родственница",
    "какой-то человек",
    "некий человек",
    "знакомый семьи",
    "знакомая семьи",
    "какой-то знакомый",
    "человек со стороны",
)


class DecompositionError(ValueError):
    """Невалидный ответ LLM-декомпозитора. Retry-политика — вызывающий (API)."""


class ChronicleDecompositionNormalizer:
    """Чистый трансформер: str|dict → BiographyDecomposition. Без LLM, без I/O."""

    @staticmethod
    def normalize(raw: Any, *, chronicle_id: str, fragment_ord: int) -> List[DecompositionItem]:
        """
        Возвращает список DecompositionItem. Бросает DecompositionError:
        - non-JSON / пустой ответ;
        - items отсутствует / не список / пуст;
        - kind вне EntryKind-реестра;
        - draft_payload не dict;
        - confidence вне [0,1] (None → 0.0 не допускается — модель обязана оценить).
        """
        data = ChronicleDecompositionNormalizer._extract_json(raw)

        if not isinstance(data, dict):
            raise DecompositionError(f"Ответ не объект: {type(data).__name__}")
        unknown = set(data.keys()) - _ALLOWED_KEYS
        if unknown:
            raise DecompositionError(f"Неизвестные ключи ответа: {sorted(unknown)}")

        items_raw = data.get("items")
        if not isinstance(items_raw, list) or not items_raw:
            raise DecompositionError("items отсутствует/пуст/не список")

        items: List[DecompositionItem] = []
        for idx, it in enumerate(items_raw):
            if not isinstance(it, dict):
                raise DecompositionError(f"items[{idx}]: не объект")
            kind_raw = it.get("kind")
            try:
                kind = EntryKind(kind_raw)
            except ValueError:
                raise DecompositionError(
                    f"items[{idx}]: kind '{kind_raw}' вне реестра {sorted(k.value for k in EntryKind)}"
                ) from None
            payload = it.get("draft_payload", {})
            if not isinstance(payload, dict):
                raise DecompositionError(f"items[{idx}]: draft_payload не dict")
            conf = it.get("confidence")
            if conf is None:
                # LLM забыл поле → честная деградация: 0.5 + подтверждение
                # автора (needs_confirmation форсирует вопрос). Не silent:
                # автор увидит флаг.
                conf = 0.5
                it["needs_confirmation"] = True
            elif not isinstance(conf, (int, float)) or isinstance(conf, bool) or not (0.0 <= conf <= 1.0):
                # Число вне диапазона = нарушение схемы → fail-loud (иначе)
                raise DecompositionError(f"items[{idx}]: confidence {conf!r} вне [0,1]")
            question_raw = it.get("question")
            # Явный if вместо тернарника (§1.1)
            if question_raw is not None:
                question = ChronicleDecompositionNormalizer._normalize_question(question_raw, idx)
            else:
                question = None
            # Мембрана неточной связи (INV-LLM-NOT-SSOT): маркер в target_hint/
            # summary при model-confidence=1.0 → понижение до 0.4 + канонический
            # вопрос о связи (4 опции, П3), если модель его не задала.
            blob = " ".join(
                str(v) for v in (payload.get("target_hint"), payload.get("summary")) if v
            ).lower()
            if not question and any(m in blob for m in _VAGUE_RELATION_MARKERS):
                conf = min(float(conf), 0.4)
                question = ClarificationQuestion(
                    question_id=f"vague_relation_{idx}",
                    target_span=payload.get("target_hint") or payload.get("summary") or "",
                    options=(
                        ClarificationOption.SELECT_EXISTING_NPC,
                        ClarificationOption.CREATE_NEW_NPC,
                        ClarificationOption.UNKNOWN_PERSON,
                        ClarificationOption.LEAVE_WHITE_SPOT,
                    ),
                )
            needs_conf = bool(it.get("needs_confirmation") or question is not None)
            items.append(
                DecompositionItem(
                    kind=kind,
                    draft_payload=payload,
                    confidence=float(conf),
                    needs_confirmation=needs_conf,
                    question=question,
                )
            )
        return items

    @staticmethod
    def _normalize_question(question_raw: Any, idx: int) -> ClarificationQuestion:
        if not isinstance(question_raw, dict):
            raise DecompositionError(f"items[{idx}].question: не объект")
        qid = question_raw.get("question_id")
        if not isinstance(qid, str) or not qid:
            raise DecompositionError(f"items[{idx}].question: question_id пуст")
        span = question_raw.get("target_span", "")
        if not isinstance(span, str):
            raise DecompositionError(f"items[{idx}].question: target_span не строка")
        opts_raw = question_raw.get("options")
        if not isinstance(opts_raw, list) or not opts_raw:
            raise DecompositionError(f"items[{idx}].question: options пусты")
        # Деградация вместо смерти item (калибровка S336): мусорная опция LLM
        # ('guardianship', 'tavern') выбрасывается ПОИМЕННО; реестровые опции +
        # обязательное LEAVE_WHITE_SPOT (П3) сохраняют вопрос живым. Полная
        # потеря опций → DecompositionError (fail-loud сохранён).
        options = []
        for o in opts_raw:
            try:
                opt = ClarificationOption(o)
            except ValueError:
                continue
            options.append(opt)
        if ClarificationOption.LEAVE_WHITE_SPOT not in options:
            options.append(ClarificationOption.LEAVE_WHITE_SPOT)
        return ClarificationQuestion(
            question_id=qid,
            target_span=span,
            options=tuple(options),
        )

    @staticmethod
    def _extract_json(raw: Any) -> Any:
        if isinstance(raw, Mapping):
            return dict(raw)  # уже распарсено провайдером-тестом
        if not isinstance(raw, str):
            raise DecompositionError(f"Ответ LLM не строка и не объект: {type(raw).__name__}")
        text = raw.strip()
        if not text:
            raise DecompositionError("Пустой ответ LLM")
        m = _MD_JSON.search(text)
        if m:
            text = m.group(1)
        else:
            m2 = _BARE_JSON.search(text)
            if m2:
                text = m2.group(0)
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise DecompositionError(f"JSON-парсинг: {e}; фрагмент: {text[:120]!r}") from e

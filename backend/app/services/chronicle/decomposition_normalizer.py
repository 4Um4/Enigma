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
import logging
import re
from typing import Any, Final, List, Mapping, Optional

from app.domain.chronicle import (
    ClarificationOption,
    ClarificationQuestion,
    DecompositionItem,
    EntityRef,
    EntityRefKind,
    EntryKind,
)

logger = logging.getLogger(__name__)

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

# S367: identity-resolution options. LEAVE_WHITE_SPOT присутствует в каждом
# вопросе (инвариант ClarificationQuestion.__post_init__), поэтому подпроверка
# identity-options сейчас вакуумно True — защитная на будущие типы вопросов с
# другими опциями. Эффективная логика — exact target_span==hint.
_IDENTITY_OPTIONS: Final[frozenset] = frozenset({
    ClarificationOption.SELECT_EXISTING_NPC,
    ClarificationOption.CREATE_NEW_NPC,
    ClarificationOption.UNKNOWN_PERSON,
    ClarificationOption.LEAVE_WHITE_SPOT,
})


def _matches_roster_exact(hint: Any, roster: Mapping[str, str]) -> bool:
    """S367: exact case-insensitive match hint против roster display names + ids.
    Type-guarded: non-str hint/name/id -> False (НЕ mismatch, а skip).
    Exact (не fuzzy, не падежная морфология) — заявленное ограничение."""
    if not isinstance(hint, str):
        return False
    h = hint.strip().lower()
    if not h:
        return False
    for npc_id, name in roster.items():
        if isinstance(name, str) and h == name.strip().lower():
            return True
        if isinstance(npc_id, str) and h == npc_id.strip().lower():
            return True
    return False


def _is_identity_question_for(question: Any, hint: Any) -> bool:
    """S367: True если question уже спрашивает об идентичности hint-сущности.
    Подпроверка identity-options сейчас вакуумно True (LEAVE_WHITE_SPOT-инвариант);
    защитная на будущие не-identity типы. Эффективная логика — exact span==hint.
    ОГРАНИЧЕНИЕ: инфлектированный/форматный span от LLM не совпадёт -> возможен
    дубль-вопрос (не катастрофично — автор резолвит оба)."""
    if question is None:
        return False
    opts = getattr(question, "options", None) or ()
    if not any(o in _IDENTITY_OPTIONS for o in opts):
        return False
    span = getattr(question, "target_span", None)
    if not isinstance(span, str) or not isinstance(hint, str):
        return False
    return span.strip().lower() == hint.strip().lower()


def resolve_object_ref_from_roster(
    hint: Any, roster: Mapping[str, str]
) -> Optional[EntityRef]:
    """COV-10.4: Exact-match resolution of target_hint → EntityRef(RESOLVED, npc_id).

    Когда _matches_roster_exact возвращает True, normalizer не создаёт
    ClarificationQuestion. Без object_id запись оставалась бы «застрявшей» —
    без object_id И без open_questions (seeder skip'ает, resolver не может
    разрешить, так как нечего разрешать).

    Возвращает EntityRef(ref_kind=RESOLVED, npc_id=<matched>) если hint
    точно совпадает (case-insensitive) с roster display name или npc_id.
    None в остальных случаях (non-string, пустой, нет совпадения).

    Type-guarded, exact match (не fuzzy) — зеркалит _matches_roster_exact.
    """
    if not isinstance(hint, str):
        return None
    h = hint.strip().lower()
    if not h:
        return None
    for npc_id, name in roster.items():
        if isinstance(name, str) and h == name.strip().lower():
            return EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=npc_id)
        if isinstance(npc_id, str) and h == npc_id.strip().lower():
            return EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=npc_id)
    return None


class DecompositionError(ValueError):
    """Невалидный ответ LLM-декомпозитора. Retry-политика — вызывающий (API)."""


class ChronicleDecompositionNormalizer:
    """Чистый трансформер: str|dict → BiographyDecomposition. Без LLM, без I/O."""

    @staticmethod
    def normalize(
        raw: Any,
        *,
        chronicle_id: str,
        fragment_ord: int,
        roster: Optional[Mapping[str, str]] = None,
    ) -> List[DecompositionItem]:
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
                try:
                    question = ChronicleDecompositionNormalizer._normalize_question(question_raw, idx)
                except DecompositionError as qe:
                    # S365: bad question (пустой question_id, пустые options) НЕ убивает item.
                    # Урок прогона: LLM иногда фантазирует вопрос без question_id — это
                    # не повод терять весь факт. Логируем, выбрасываем вопрос.
                    logger.warning("normalize[%s]: вопрос невалиден (%s) — отброшен, item сохранён", idx, qe)
                    question = None
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
            # S367: roster backstop — contract-gated, type-guarded.
            # Только RELATIONSHIP.target_hint (всегда NPC) и EFFECT.target_hint
            # при non-null (контракт "null|<имя>"). name_hint=place, observed_hint=
            # "имя/явление", about_hint=тема — НЕ обрабатываются (LLM rule 3).
            # roster=None -> backstop отключён (backward-compat).
            # Exact target_span==hint — ЗАЯВЛЕННОЕ ОГРАНИЧЕНИЕ (не fuzzy):
            # инфлектированный span от LLM может дать дубль-вопрос — не катастрофично.
            if roster is not None:
                hint = None
                if kind is EntryKind.RELATIONSHIP:
                    hint = payload.get("target_hint")
                elif kind is EntryKind.EFFECT:
                    h = payload.get("target_hint")
                    if isinstance(h, str) and h.strip():
                        hint = h
                if (
                    isinstance(hint, str)
                    and hint.strip()
                    and not _matches_roster_exact(hint, roster)
                    and not _is_identity_question_for(question, hint)
                ):
                    conf = min(float(conf), 0.4)
                    question = ClarificationQuestion(
                        question_id=f"roster_mismatch_{idx}",
                        target_span=hint,
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
                # L4: деградация видима — мусорная опция LLM не глотается молча
                logger.warning(
                    "normalize[%s]: мусорная опция вопроса отброшена: %r",
                    idx, o,
                )
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

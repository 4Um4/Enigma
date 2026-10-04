"""path: /project/backend/app/services/npc/act_consumer.py

Назначение: Шаг 4 (вердикт Мастера) — NPC Act Consumer v0: чистая функция
    «что означает эта реплика для данного NPC». Вход: semantic_acts +
    эпистемическое состояние (name-записи Store) + provenance. Выход:
    ResponsePlan (frozen). Образец: decide_disclosure (пороговая лестница,
    A/A-детерминизм). ГРАНИЦА (поправка Мастера): challenge НЕ мутирует
    belief — только обнаруживает существующий claim и возвращает
    challenged-план. CLAIM ≠ BELIEF ≠ TRUTH.
Зависимости: app.services.npc.epistemic_store (read-only).
Основные сущности: ActAttitude, ResponsePlan, consume_npc_acts.
"""

import logging
from dataclasses import dataclass
from typing import Any, List

logger = logging.getLogger(__name__)


class ActAttitude:
    """Закрытый набор вердиктов consumer'а v0."""
    FRESH = "fresh_intro"              # первая name-запись
    CONFLICTING = "conflicting_intro"  # конкурирующая name-запись (без overwrite)
    PROVENANCE_QUERY = "provenance_query"
    DOUBT_REGISTERED = "doubt_registered"  # challenge: БЕЗ мутации belief
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class ResponsePlan:
    """Детерминированный план реакции на акты игрока (для cognition-канала)."""
    attitude: str
    provenance_hint: str = ""      # source_id существующей name-записи
    belief_confidence: float = 0.0
    challenged_claim_object: str = ""  # имя/содержимое оспариваемого claim'а
    claimed_name: str = ""             # имя из текущего SELF_INTRODUCTION


def _name_records(store: Any, listener_id: str) -> List[Any]:
    """name-записи listener'а (read-only; Store может отсутствовать — sandbox)."""
    try:
        return [
            r for r in (store.get_all_for_agent(listener_id) or [])
            if getattr(getattr(r, "proposition", None), "predicate", None) is not None  # noqa: ENIGMA002
            and getattr(r.proposition, "predicate").value == "name"
        ]
    except Exception as e:  # noqa: BLE001 — sandbox/тесты без Store
        logger.debug(f"[ACT_CONSUMER] store read failed: {e}")
        return []


def consume_npc_acts(
    listener_id: str,
    acts: List[dict],
    store: Any,
) -> ResponsePlan:
    """Детерминированный вердикт по актам текущей реплики игрока.

    Лестница первого совпадения (прецедент decide_disclosure):
    1. SELF_INTRODUCTION: fresh / conflicting (по существующим name-записям)
    2. QUESTION(name-тема) при наличии записи → provenance_query
    3. QUESTION-достоверность + существующая запись → doubt_registered
       (БЕЗ мутации Store — поправка Мастера)
    4. иначе neutral
    """
    _records = _name_records(store, listener_id)

    for act in acts or []:
        if not isinstance(act, dict):
            continue  # type: ignore[unreachable]  # S313: runtime-гвард (cast лжёт на мусоре)
        act_type = str(act.get("type") or "").upper()
        params = act.get("params") or {}

        if act_type == "SELF_INTRODUCTION":
            name = str(params.get("name") or "").strip()
            if not name:
                continue
            # Конфликт = состояние эпистемики NPC (несколько конкурирующих
            # name-записей), а не новизна имени: переповтор одного из
            # конкурирующих имён — тоже конфликтное состояние (выбор стороны).
            _distinct = {
                getattr(r.proposition, "object_id", "") for r in _records  # noqa: ENIGMA002
            }
            _is_conflicting = len(_distinct) > 1 or (
                _records and name not in _distinct
            )
            if _is_conflicting:
                return ResponsePlan(
                    attitude=ActAttitude.CONFLICTING,
                    belief_confidence=max(
                        (getattr(r, "confidence", 0.0) for r in _records), default=0.0
                    ),
                    claimed_name=name,
                )
            _existing = next(
                (r for r in _records
                 if getattr(r.proposition, "object_id", "") == name),  # noqa: ENIGMA002
                None,
            )
            return ResponsePlan(
                attitude=ActAttitude.FRESH,
                claimed_name=name,
                belief_confidence=(
                    _existing.confidence if _existing else 0.0
                ),
            )

        # Шаг 4/RC8 (вердикт Мастера): provenance — КАНОНИЧЕСКИЙ тип акта
        # (ASK_PROVENANCE из Understanding), не keyword-детектор по prose-topic.
        # Regression lock: consumer НЕ ИМЕЕТ ПРАВА извлекать provenance-смысл
        # из слов topic — скрытый второй parser удалён.
        # Semantic classification ≠ epistemic relevance: отсутствие записи
        # НЕ превращает intent обратно в обычный вопрос (boundaries раздельны).
        if act_type == "ASK_PROVENANCE":
            _latest = max(_records, key=lambda r: getattr(r, "last_updated_tick", 0)) if _records else None  # noqa: ENIGMA001
            return ResponsePlan(
                attitude=ActAttitude.PROVENANCE_QUERY,
                provenance_hint=getattr(_latest, "source_id", "") if _latest else "",  # noqa: ENIGMA002
                belief_confidence=getattr(_latest, "confidence", 0.0) if _latest else 0.0,
                challenged_claim_object=(
                    getattr(_latest.proposition, "object_id", "") if _latest else ""  # noqa: ENIGMA002
                ),
            )
        # challenge: пока остаётся keyword-веткой ВРЕМЕННО (RC3 — отдельный
        # canonicalization-пакет по вердикту; не объединять).
        if act_type == "QUESTION" and _records:
            topic = str(params.get("topic") or "").lower()
            if any(
                kw in topic for kw in (
                    "соврал", "совру", "обманул", "врал", "врёшь", "врешь",
                    "не правда", "неправда", "ложь", "шутка", "пошутил",
                )
            ):
                _latest = max(_records, key=lambda r: getattr(r, "last_updated_tick", 0))
                return ResponsePlan(
                    attitude=ActAttitude.DOUBT_REGISTERED,
                    provenance_hint=getattr(_latest, "source_id", ""),  # noqa: ENIGMA002
                    belief_confidence=getattr(_latest, "confidence", 0.0),
                    challenged_claim_object=getattr(  # noqa: ENIGMA002
                        _latest.proposition, "object_id", ""
                    ),
                )

    return ResponsePlan(attitude=ActAttitude.NEUTRAL)


def plan_to_cognition_line(plan: ResponsePlan) -> str:
    """Сериализация плана в cognition-строку DMFrame (без чисел в тексте)."""
    if plan.attitude == ActAttitude.FRESH:
        return f"игрок впервые представился как «{plan.claimed_name}»"
    if plan.attitude == ActAttitude.CONFLICTING:
        return (
            f"игрок назвал новое имя «{plan.claimed_name}» — "
            f"конкурирует с ранее услышанным (уверенность прежней записи была выше нуля)"
        )
    if plan.attitude == ActAttitude.PROVENANCE_QUERY:
        src = "сам игрок" if plan.provenance_hint == "player" else plan.provenance_hint
        return f"игрок спрашивает, откуда NPC знает имя — источник записи: {src}"
    if plan.attitude == ActAttitude.DOUBT_REGISTERED:
        return (
            f"игрок поставил под сомнение ранее услышанное имя "
            f"«{plan.challenged_claim_object}» (источник: {plan.provenance_hint}) — "
            f"достоверность под вопросом, NPC сам решает как реагировать"
        )
    return ""

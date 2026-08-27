"""
path: /project/backend/app/domain/action_priority.py
Назначение: S203.4 (Stage 2A, ADR-O-365) — приоритетная политика арбитража
    поведенческих обязательств: кандидат получает право просить прерывание
    инкумбента при candidate_priority > incumbent_priority + INTERRUPT_THRESHOLD.
    Приоритет — РЕЗУЛЬТАТ policy конкретной версии (вердикт D-5 Мастера:
    калибруемая шкала, НЕ онтология): смена PRIORITY_POLICY_VERSION без
    мини-ADR с миграцией replay-семантики запрещена (D-5b — новая шкала
    меняет будущие вердикты при том же прошлом).
Зависимости: typing (чистый домен — без сервисов и моделей, §1.2)
Основные сущности: PRIORITY_POLICY_VERSION, INTERRUPT_THRESHOLD,
    PRIORITY_* (шкала v1), resolve_candidate_priority
"""

from __future__ import annotations

from typing import Dict

# ── Версия политики (D-5 / D-5b) ───────────────────────────────────────────
# Commitment хранит приоритет-результат + эту версию; replay читает записанное
# число (пересчёт запрещён). Приоритет НЕ входит в commitment_id: смена шкалы
# не меняет ретроактивно идентичности, но меняет будущие вердикты — поэтому
# новая версия политики = мини-ADR с миграционной семантикой.
PRIORITY_POLICY_VERSION: str = "s203.4.v1"

# ── Шкала v1 (калибровочные стартовые значения, НЕ онтология) ──────────────
# Порядок заявленной важности: исследование < рутина < социальное <
# сон = выживание < windowed-действия. SLEEP=SURVIVAL: физиологическая власть
# (конфликт доменов — S203.6, закон №19); спящий инкумбент всё равно закрыт
# executor-boundary (INCUMBENT_PROTECTED). WINDOWED (attack|steal, S209):
# окно подготовки 2 тика — высшая заявка на немедленность исполнения.
PRIORITY_EXPLORATION: int = 1
PRIORITY_ROUTINE: int = 2
PRIORITY_SOCIAL: int = 3
PRIORITY_SLEEP: int = 6
PRIORITY_SURVIVAL: int = 6
PRIORITY_WINDOWED: int = 7

# ANTIFLAP-порог (ТЗ 2.5 §6.4): INTERRUPT разрешён только при
# candidate > incumbent + INTERRUPT_THRESHOLD. Равные и близкие приоритеты
# НЕ прерывают инкумбента — стабилизирующая асимметрия. Часть шкалы версии
# v1: перекалибровка = новая версия policy + мини-ADR.
INTERRUPT_THRESHOLD: int = 3

# IntentDomain (dom/movement.py, ADR-O-137) → приоритет шкалы v1.
_DOMAIN_TO_PRIORITY: Dict[str, int] = {
    "EXPLORATION": PRIORITY_EXPLORATION,
    "ROUTINE": PRIORITY_ROUTINE,
    "SOCIAL": PRIORITY_SOCIAL,
    "SURVIVAL": PRIORITY_SURVIVAL,
}

# Windowed-действия (windup-класс, S209): окно подготовки 2 тика.
_WINDOWED_ACTIONS: frozenset[str] = frozenset({"attack", "steal"})


def resolve_candidate_priority(
    intent_type: str = "",
    intent_domain: object = None,
) -> int:
    """Pure function: приоритет кандидата по шкале PRIORITY_POLICY_VERSION.

    intent_domain принимает IntentDomain Enum | str | None (гейты читают
    getattr(intent, "domain", None)); нормализация внутри: Enum → .name
    (str(Enum) ненадёжен между версиями Python), None/чужой тип → fallback.

    Детерминизм: результат зависит только от аргументов — одинаковый вход
    всегда даёт одинаковый приоритет (INV-REPLAY-DETERMINISM; приоритет
    НЕ входит в commitment_id — инвариант D-5, тест
    test_commitment_id_independent_of_priority).

    Разрешение: windowed-тип > sleep-тип > домен > ROUTINE. Неизвестный
    кандидат получает консервативный базовый уровень: приоритета 2 не
    хватает, чтобы прервать даже ROUTINE-инкумбента (нужно > 2 + 3 = 5).
    """
    if intent_type in _WINDOWED_ACTIONS:
        return PRIORITY_WINDOWED
    if intent_type == "sleep":
        return PRIORITY_SLEEP
    # Нормализация: на входе IntentDomain Enum (гейты передают getattr(intent,
    # "domain")) либо строка; str(Enum) ненадёжен между версиями Python —
    # каноничен .name. Чистый домен — без распознавания типов сервисов.
    _domain = intent_domain if intent_domain is not None else ""
    _domain = getattr(_domain, "name", _domain)
    if not isinstance(_domain, str):
        _domain = str(_domain)
    domain = _domain.strip().upper()
    if domain in _DOMAIN_TO_PRIORITY:
        return _DOMAIN_TO_PRIORITY[domain]
    return PRIORITY_ROUTINE

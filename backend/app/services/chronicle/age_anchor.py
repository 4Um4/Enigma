"""CCH-12 Point 1: типизированные возрастные якоря.

Плоский List[int] не различал CURRENT_AGE / DURATION / AT_AGE / SINCE_AGE.
Fallback S368 (1 anchor + 1 EVENT) не срабатывал при множественных anchors.
LLM получала [146, 57] без различения, что приводило к потере длительности
и путанице текущего возраста с возрастом события.

AgeAnchor — frozen dataclass с kind и source_span. extract_age_anchors
возвращает List[AgeAnchor], LLM получает типизированные подсказки.

Не делает: regex под конкретную фразу; правило 146-57; универсальное
распределение anchors по EVENT'ам.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List


class AgeAnchorKind(str, Enum):
    """Семантика возрастного якоря (CCH-15 P0: 4 формы времени)."""

    # Точка в прошлом
    CURRENT_AGE = "current_age"   # «N лет» — текущий возраст на game_start
    AT_AGE = "at_age"              # «в N лет» — возраст на момент события
    SINCE_AGE = "since_age"       # «с N лет» — возраст начала периода
    YEARS_AGO = "years_ago"       # «N лет назад» / «N лет тому назад» — точка в прошлом от game_start
    # Длительность события
    DURATION = "duration"          # «уже N лет» / «в течение N лет» / «из которых N лет» — длительность
    # Временной интервал (между событиями)
    INTERVAL = "interval"          # «через N лет» / «N лет спустя» / «год спустя» — интервал
    # Конец периода (относительная точка)
    END_OF_PERIOD = "end_of_period"  # «к концу того года» / «к концу периода» — конец периода (value=0, маркер)
    # Повторяемость события
    REPEAT = "repeat"              # «каждый год» / «каждые N лет» / «регулярно» / «постоянно» — повтор (value=0=N лет, 0=без периода)
    # Неоднозначное
    AMBIGUOUS = "ambiguous"       # «N лет» без контекста — нельзя классифицировать


@dataclass(frozen=True)
class AgeAnchor:
    """Типизированный возрастной якорь с provenance."""

    value: int
    kind: AgeAnchorKind
    source_span: str  # подстрока оригинального текста (для трассировки)


# Упорядоченные паттерны: более специффичные — первыми (DURATION_AT_AGE не смешивать)
_PATTERNS: List[tuple[re.Pattern, AgeAnchorKind]] = [
    # YEARS_AGO (приоритет): «N лет назад», «N лет тому назад» — точка в прошлом.
    # Не DURATION (не длительность интервала).
    (
        re.compile(
            r"(\d{1,3})\s*(?:лет|год|года)\s*(?:тому\s+)?назад\b",
            re.IGNORECASE,
        ),
        AgeAnchorKind.YEARS_AGO,
    ),
    # DURATION: «уже N лет», «в течение N лет», «из которых N лет», «на протяжении N лет»
    (
        re.compile(
            r"(?:уже|в\s+течение|из\s+которых|на\s+протяжении)\s+(\d{1,3})\s*лет",
            re.IGNORECASE,
        ),
        AgeAnchorKind.DURATION,
    ),
    # AT_AGE: «в N лет», «в N года», «в N год», «в N годам»
    (
        re.compile(r"в\s+(\d{1,3})\s*лет\b", re.IGNORECASE),
        AgeAnchorKind.AT_AGE,
    ),
    (
        re.compile(r"в\s+(\d{1,3})\s*год(а|у|ом)?\b", re.IGNORECASE),
        AgeAnchorKind.AT_AGE,
    ),
    # SINCE_AGE: «с N лет», «к N годам»
    (
        re.compile(r"с\s+(\d{1,3})\s*лет\b", re.IGNORECASE),
        AgeAnchorKind.SINCE_AGE,
    ),
    (
        re.compile(r"к\s+(\d{1,3})\s*годам\b", re.IGNORECASE),
        AgeAnchorKind.SINCE_AGE,
    ),
    # INTERVAL: «через N лет», «через год», «N лет спустя», «год спустя», «N лет после»
    # (интервал между событиями, не точка и не длительность)
    # «через год» = INTERVAL(1); «через N лет» = INTERVAL(N)
    (
        re.compile(r"через\s+(?:(\d{1,3})\s*)?(?:лет|год|года)\b", re.IGNORECASE),
        AgeAnchorKind.INTERVAL,
    ),
    (
        re.compile(r"(\d{1,3})\s*(?:лет|год|года)\s+спустя\b", re.IGNORECASE),
        AgeAnchorKind.INTERVAL,
    ),
    (
        re.compile(r"спустя\s+(\d{1,3})\s*(?:лет|год|года)\b", re.IGNORECASE),
        AgeAnchorKind.INTERVAL,
    ),
    # END_OF_PERIOD: «к концу того года», «к концу периода», «к концу N года»
    # value=0 — маркер (без конкретного числа); LLM вычисляет age = SINCE_AGE + DURATION
    (
        re.compile(r"к\s+концу\s+(?:того\s+)?(?:года|периода|времени)\b", re.IGNORECASE),
        AgeAnchorKind.END_OF_PERIOD,
    ),
    # REPEAT: «каждый год», «каждые N лет», «регулярно», «постоянно», «ежегодно»
    # value=0 — без конкретного периода; value=N — каждые N лет
    (
        re.compile(r"каждые\s+(\d{1,3})\s*(?:лет|год|года)\b", re.IGNORECASE),
        AgeAnchorKind.REPEAT,
    ),
    (
        re.compile(r"каждый\s+год\b|ежегодно\b|регулярно\b|постоянно\b", re.IGNORECASE),
        AgeAnchorKind.REPEAT,
    ),
    # AMBIGUOUS: голое «N лет» — без маркера контекста, классифицировать нельзя
    (
        re.compile(r"\b(\d{1,3})\s*лет\b", re.IGNORECASE),
        AgeAnchorKind.AMBIGUOUS,
    ),
]


def extract_age_anchors_typed(text: str) -> List[AgeAnchor]:
    """Извлекает типизированные возрастные якоря.

    Порядок паттернов важен: DURATION проверяется раньше AMBIGUOUS, чтобы
    «уже 57 лет» классифицировалось как DURATION, а не как AMBIGUOUS.
    Перекрытия match'ей устраняются: каждое число потребляется один раз.

    «146 лет» без контекста → AMBIGUOUS (не CURRENT_AGE автоматически —
    CURRENT_AGE определяется через game_start_age канон-хроники, не regex).
    """
    anchors: List[AgeAnchor] = []
    consumed_spans: List[tuple[int, int]] = []

    for pattern, kind in _PATTERNS:
        for m in pattern.finditer(text):
            # Проверка перекрытия с уже потреблённым span
            ms, me = m.span()
            if any(cs <= ms < ce or cs < me <= ce for cs, ce in consumed_spans):
                continue
            # REPEAT/END_OF_PERIOD/INTERVAL(«через год») могут не иметь group(1)
            # или group(1)=None (опциональная группа) — value=0 (маркер) или 1 («через год»)
            try:
                raw = m.group(1) if m.groups() else None
            except IndexError:
                raw = None
            if raw is None or raw == "":
                # Паттерн без группы или None — маркер.
                # Для INTERVAL «через год» = 1 (по умолчанию 1 год).
                n = 1 if kind is AgeAnchorKind.INTERVAL else 0
            else:
                try:
                    n = int(raw)
                except (TypeError, ValueError):
                    n = 0
            if 0 <= n <= 1000:  # гном может жить 146 лет; потолок 1000 (для эльфов)
                anchors.append(
                    AgeAnchor(
                        value=n,
                        kind=kind,
                        source_span=text[ms:me],
                    )
                )
                consumed_spans.append((ms, me))

    return anchors


def age_anchors_to_hint(anchors: List[AgeAnchor]) -> str:
    """Типизированная подсказка для LLM-промпта.

    Заменяет плоский «Возрастные якоря: [146, 57]» на семантически явную форму.

    CCH-12 anti-hallucination (Fix 1): для AMBIGUOUS якорей («N лет» без
    маркера «назад»/«уже»/«в течение») добавляет предупреждение — LLM
    НЕ должна создавать EVENT с years_ago=N или duration_years=N без
    явного маркера в тексте. «146 лет» — это, вероятно, текущий
    возраст, а не «146 лет назад».
    """
    if not anchors:
        return ""
    lines = ["Возрастные якоря фрагмента (типизированные):"]
    for a in anchors:
        lines.append(f"  - {a.kind.value}: {a.value} («{a.source_span}»)")
        # CCH-12 Fix 1: AMBIGUOUS без контекста — НЕ years_ago/duration_years
        if a.kind is AgeAnchorKind.AMBIGUOUS:
            lines.append(
                f"    ВНИМАНИЕ: «{a.value} лет» без явного маркера "
                f"(«назад»/«уже»/«в течение»/«в N лет»/«с N лет») — "
                f"это, вероятно, текущий возраст или упоминание возраста "
                f"в описании. НЕ создавай EVENT с years_ago={a.value} "
                f"или duration_years={a.value} без явного маркера в тексте."
            )
        # CCH-15 P0: INTERVAL — интервал между событиями
        elif a.kind is AgeAnchorKind.INTERVAL:
            lines.append(
                f"    INTERVAL: интервал {a.value} лет между событиями. "
                f"Используй для указания «через N лет после [события]». "
                f"НЕ years_ago (не точка от game_start), НЕ duration_years "
                f"(не длительность). Если нужно привязать к событию — "
                f"используй causes со ссылкой на предыдущее событие."
            )
        # CCH-15 P0: END_OF_PERIOD — конец периода
        elif a.kind is AgeAnchorKind.END_OF_PERIOD:
            lines.append(
                "    END_OF_PERIOD: конец периода (маркер, value=0). "
                "Вычисли age = (предыдущий SINCE_AGE) + (DURATION если есть), "
                "либо age = (предыдущий AT_AGE) + 1. "
                "Используй для EVENT с age=вычисленное значение, "
                "НЕ years_ago, НЕ duration_years."
            )
        # CCH-15 P0: REPEAT — повторяемость
        elif a.kind is AgeAnchorKind.REPEAT:
            if a.value > 0:
                lines.append(
                    f"    REPEAT: повтор каждые {a.value} лет. "
                    f"Создавай EVENT с повторяющимся характером — "
                    f"в summary укажи «регулярно / каждый год». "
                    f"НЕ years_ago, НЕ duration_years (это паттерн повторения)."
                )
            else:
                lines.append(
                    "    REPEAT: повторяемое событие (без конкретного периода). "
                    "Создавай EVENT с summary, отражающим регулярность "
                    "(«регулярно», «постоянно», «каждый год»). "
                    "НЕ years_ago, НЕ duration_years."
                )
    return "\n".join(lines) + "\n\n"


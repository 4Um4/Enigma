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
    """Семантика возрастного якоря."""

    CURRENT_AGE = "current_age"   # «N лет» — текущий возраст на game_start
    AT_AGE = "at_age"              # «в N лет» — возраст на момент события
    SINCE_AGE = "since_age"       # «с N лет» — возраст начала периода
    DURATION = "duration"          # «уже N лет» / «в течение N лет» / «из которых N лет» — длительность
    AMBIGUOUS = "ambiguous"       # «N лет» без контекста — нельзя классифицировать


@dataclass(frozen=True)
class AgeAnchor:
    """Типизированный возрастной якорь с provenance."""

    value: int
    kind: AgeAnchorKind
    source_span: str  # подстрока оригинального текста (для трассировки)


# Упорядоченные паттерны: более специффичные — первыми (DURATION_AT_AGE не смешивать)
_PATTERNS: List[tuple[re.Pattern, AgeAnchorKind]] = [
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
            raw = m.group(1)
            n = int(raw)
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
    """
    if not anchors:
        return ""
    lines = ["Возрастные якоря фрагмента (типизированные):"]
    for a in anchors:
        lines.append(f"  - {a.kind.value}: {a.value} («{a.source_span}»)")
    return "\n".join(lines) + "\n\n"
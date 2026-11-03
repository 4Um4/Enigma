# backend/tests/micro/test_s380_age_anchor_forms.py
"""S380 (CCH-15 P0): 4 формы времени в age_anchor.

Вердикт Мастера: сохранить различие:
- конкретная точка прошлого (AT_AGE, SINCE_AGE, YEARS_AGO)
- длительность события (DURATION)
- временной интервал (INTERVAL)
- конец периода (END_OF_PERIOD)
- повторяемость события (REPEAT)

Тесты на реальные языковые формулировки.
"""
from __future__ import annotations

from app.services.chronicle.age_anchor import (
    AgeAnchor,
    AgeAnchorKind,
    age_anchors_to_hint,
    extract_age_anchors_typed,
)


def _kinds(anchors):
    return [a.kind for a in anchors]


def _values(anchors):
    return [a.value for a in anchors]


# =========================================================================
# INTERVAL — «через N лет», «N лет спустя», «спустя N лет»
# =========================================================================

class TestIntervalForm:
    def test_cherez_n_let(self):
        anchors = extract_age_anchors_typed("Через 5 лет он уехал из города.")
        intervals = [a for a in anchors if a.kind is AgeAnchorKind.INTERVAL]
        assert len(intervals) == 1
        assert intervals[0].value == 5

    def test_n_let_spustya(self):
        anchors = extract_age_anchors_typed("5 лет спустя он вернулся.")
        intervals = [a for a in anchors if a.kind is AgeAnchorKind.INTERVAL]
        assert len(intervals) == 1
        assert intervals[0].value == 5

    def test_spustya_n_let(self):
        anchors = extract_age_anchors_typed("Спустя 3 года они поженились.")
        intervals = [a for a in anchors if a.kind is AgeAnchorKind.INTERVAL]
        assert len(intervals) == 1
        assert intervals[0].value == 3

    def test_cherez_god(self):
        """«через год» = INTERVAL(1)."""
        anchors = extract_age_anchors_typed("Через год он женился.")
        intervals = [a for a in anchors if a.kind is AgeAnchorKind.INTERVAL]
        assert len(intervals) == 1
        assert intervals[0].value == 1


# =========================================================================
# END_OF_PERIOD — «к концу того года», «к концу периода»
# =========================================================================

class TestEndOfPeriodForm:
    def test_k_koncu_togo_goda(self):
        """Борко п.11: «К концу того года он стал начальником»."""
        anchors = extract_age_anchors_typed("К концу того года он стал начальником.")
        eops = [a for a in anchors if a.kind is AgeAnchorKind.END_OF_PERIOD]
        assert len(eops) == 1
        assert eops[0].value == 0  # маркер

    def test_k_koncu_perioda(self):
        anchors = extract_age_anchors_typed("К концу периода он устал.")
        eops = [a for a in anchors if a.kind is AgeAnchorKind.END_OF_PERIOD]
        assert len(eops) == 1

    def test_borko_fragment_11(self):
        """Полный фрагмент п.11 Борко: SINCE_AGE(23) + END_OF_PERIOD."""
        text = "Ещё с 23 лет познакомился с Гораном. К концу того года он стал начальником."
        anchors = extract_age_anchors_typed(text)
        kinds = _kinds(anchors)
        assert AgeAnchorKind.SINCE_AGE in kinds
        assert AgeAnchorKind.END_OF_PERIOD in kinds
        since = [a for a in anchors if a.kind is AgeAnchorKind.SINCE_AGE]
        assert since[0].value == 23


# =========================================================================
# REPEAT — «каждый год», «каждые N лет», «регулярно», «постоянно»
# =========================================================================

class TestRepeatForm:
    def test_kazhdyj_god(self):
        anchors = extract_age_anchors_typed("Каждый год он ходил в храм.")
        repeats = [a for a in anchors if a.kind is AgeAnchorKind.REPEAT]
        assert len(repeats) == 1
        assert repeats[0].value == 0  # маркер (без периода)

    def test_kazhdye_n_let(self):
        anchors = extract_age_anchors_typed("Каждые 5 лет они собирались.")
        repeats = [a for a in anchors if a.kind is AgeAnchorKind.REPEAT]
        assert len(repeats) == 1
        assert repeats[0].value == 5

    def test_regulyarno(self):
        """Люси п.6: «регулярно избивал»."""
        anchors = extract_age_anchors_typed("регулярно избивал её")
        repeats = [a for a in anchors if a.kind is AgeAnchorKind.REPEAT]
        assert len(repeats) == 1
        assert repeats[0].value == 0

    def test_postoyanno(self):
        anchors = extract_age_anchors_typed("постоянно угрожал ей")
        repeats = [a for a in anchors if a.kind is AgeAnchorKind.REPEAT]
        assert len(repeats) == 1

    def test_ezhegodno(self):
        anchors = extract_age_anchors_typed("ежегодно проводили праздник")
        repeats = [a for a in anchors if a.kind is AgeAnchorKind.REPEAT]
        assert len(repeats) == 1


# =========================================================================
# Регрессия существующих форм
# =========================================================================

class TestExistingFormsRegression:
    def test_at_age_still_works(self):
        anchors = extract_age_anchors_typed("В 14 лет она потеряла семью.")
        assert len(anchors) == 1
        assert anchors[0].kind is AgeAnchorKind.AT_AGE

    def test_since_age_still_works(self):
        anchors = extract_age_anchors_typed("С 12 лет работала в таверне.")
        assert len(anchors) == 1
        assert anchors[0].kind is AgeAnchorKind.SINCE_AGE

    def test_duration_still_works(self):
        anchors = extract_age_anchors_typed("Уже 57 лет он куёт.")
        durations = [a for a in anchors if a.kind is AgeAnchorKind.DURATION]
        assert len(durations) == 1
        assert durations[0].value == 57

    def test_years_ago_still_works(self):
        anchors = extract_age_anchors_typed("100 лет тому назад учился.")
        ya = [a for a in anchors if a.kind is AgeAnchorKind.YEARS_AGO]
        assert len(ya) == 1
        assert ya[0].value == 100

    def test_ambiguous_still_works(self):
        anchors = extract_age_anchors_typed("Ему 146 лет.")
        assert len(anchors) == 1
        assert anchors[0].kind is AgeAnchorKind.AMBIGUOUS


# =========================================================================
# Hint — подсказки для новых kinds
# =========================================================================

class TestHintForNewKinds:
    def test_hint_interval(self):
        anchors = [AgeAnchor(value=5, kind=AgeAnchorKind.INTERVAL, source_span="через 5 лет")]
        hint = age_anchors_to_hint(anchors)
        assert "INTERVAL" in hint
        assert "интервал" in hint.lower()

    def test_hint_end_of_period(self):
        anchors = [AgeAnchor(value=0, kind=AgeAnchorKind.END_OF_PERIOD, source_span="к концу того года")]
        hint = age_anchors_to_hint(anchors)
        assert "END_OF_PERIOD" in hint
        assert "конец периода" in hint.lower()

    def test_hint_repeat_with_value(self):
        anchors = [AgeAnchor(value=5, kind=AgeAnchorKind.REPEAT, source_span="каждые 5 лет")]
        hint = age_anchors_to_hint(anchors)
        assert "REPEAT" in hint
        assert "5" in hint

    def test_hint_repeat_without_value(self):
        anchors = [AgeAnchor(value=0, kind=AgeAnchorKind.REPEAT, source_span="регулярно")]
        hint = age_anchors_to_hint(anchors)
        assert "REPEAT" in hint
        assert "паттерн" in hint.lower() or "повтор" in hint.lower()


# =========================================================================
# Комбинированные кейсы из реальных биографий
# =========================================================================

class TestRealBiographyFragments:
    def test_borko_11_full(self):
        """Борко п.11: SINCE_AGE(23) + END_OF_PERIOD (без years_ago=-1)."""
        text = "Ещё с 23 лет познакомился с Гораном, помогал ему скрывать контрабанду. К концу того года он стал начальником на городских воротах."
        anchors = extract_age_anchors_typed(text)
        kinds = _kinds(anchors)
        # Нет YEARS_AGO с -1 (sentinel не появляется — END_OF_PERIOD ловится)
        ya = [a for a in anchors if a.kind is AgeAnchorKind.YEARS_AGO]
        assert len(ya) == 0  # не должно быть YEARS_AGO
        assert AgeAnchorKind.SINCE_AGE in kinds
        assert AgeAnchorKind.END_OF_PERIOD in kinds

    def test_lusya_6_repeat(self):
        """Люси п.6: «регулярно, когда Торнин напивался, он периодически избивал её»."""
        text = "регулярно, когда Торнин напивался, он периодически избивал её"
        anchors = extract_age_anchors_typed(text)
        repeats = [a for a in anchors if a.kind is AgeAnchorKind.REPEAT]
        assert len(repeats) >= 1  # «регулярно» или «периодически»
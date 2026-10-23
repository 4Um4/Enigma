"""S365: regression на возраст (S2) и резолюцию вопросов (S4).
Запуск: python -m pytest backend/tests/micro/test_s365_age_and_resolution.py -v
"""
from app.services.chronicle.biography_decomposer import BiographyDecomposer
from app.services.chronicle.decomposition_normalizer import ChronicleDecompositionNormalizer


# ── S2-A: regex ловит все формы возраста ─────────────────────────────────────

def test_age_anchors_basic_forms():
    """Базовые формы «в N лет», «с N лет», «[N лет]»."""
    d = BiographyDecomposer()
    assert d.extract_age_anchors("В 16 лет Борко поступил на службу.") == [16]
    assert d.extract_age_anchors("С 22 лет он работал в таверне.") == [22]
    assert d.extract_age_anchors("В 8 лет [8 лет] она узнала правду.") == [8, 8]


def test_age_anchors_year_forms():
    """S365: «В 24 года», «К 23 годам» — формы с «год»."""
    d = BiographyDecomposer()
    assert 24 in d.extract_age_anchors("В 24 года он пережил событие.")
    assert 23 in d.extract_age_anchors("К 23 годам понял: он добряк.")


def test_age_anchors_bare_number():
    """S365: «В 24 застал…» — число без слова «лет»/«год»."""
    d = BiographyDecomposer()
    anchors = d.extract_age_anchors("В 24 застал изнасилование Люси Ормом.")
    assert 24 in anchors, f"Ожидали 24 в anchors, получили {anchors}"


def test_age_anchors_negative():
    """Negative: без возраста → пустой список."""
    d = BiographyDecomposer()
    assert d.extract_age_anchors("Он поступил на службу в городскую стражу.") == []


# ── S2-D: CoT-leak заблокирован ──────────────────────────────────────────────

def test_cot_leak_blocked():
    """S365: фраза «Возрастных якорей не найдено» НЕ протекает в prompt."""
    d = BiographyDecomposer()
    prompt_no_anchors = d.build_user_prompt("Он поступил на службу.", [])
    assert "Возрастных якорей не найдено" not in prompt_no_anchors, (
        "CoT-фраза протекла в prompt — LLM повторит её в summary"
    )
    assert "ФРАГМЕНТ:" in prompt_no_anchors

    prompt_with_anchors = d.build_user_prompt("В 16 лет поступил.", [16])
    assert "Возрастные якоря фрагмента: [16]" in prompt_with_anchors


# ── S2-C: age из draft_payload проходит в ChronicleEntry (через route) ──────

def test_age_passthrough_via_normalizer():
    """S365: normalizer сохраняет age в draft_payload (route прокидывает в
    ChronicleEntry.historical_age — это в routes_chronicle.py:249)."""
    raw = '{"items": [{"kind": "EVENT", "draft_payload": {"summary": "поступил", "age": 24}, "confidence": 0.9}]}'
    items = ChronicleDecompositionNormalizer.normalize(raw, chronicle_id="t", fragment_ord=0)
    assert items[0].draft_payload.get("age") == 24


def test_age_passthrough_legacy_day_key():
    """S365: legacy-модели выводят 'day' — route fallback читает и его."""
    raw = '{"items": [{"kind": "EVENT", "draft_payload": {"summary": "поступил", "day": 24}, "confidence": 0.9}]}'
    items = ChronicleDecompositionNormalizer.normalize(raw, chronicle_id="t", fragment_ord=0)
    # normalizer не выкидывает day; route в _age возьмёт его как fallback
    assert items[0].draft_payload.get("day") == 24
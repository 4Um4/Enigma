"""path: /project/backend/tests/micro/test_prov_class_x2.py

Назначение: замок X2 (вердикт Мастера): дословные probe-фразы корпуса в
    контракте ASK_PROVENANCE/QUESTION убираются ТОЛЬКО env ENIGMA_PROV_X2=1;
    семантическая граница класса в обоих состояниях неизменна; дифф
    промпта A→X2 — ровно одна строка контракта. Default = baseline (A).
Зависимости: app.services.input.llm_compressor_client
Основные сущности: LlamaCppCompressorClient._build_prompts

Запуск: cd backend; python -m pytest tests/micro/test_prov_class_x2.py -v; cd ..
"""

from app.services.input.llm_compressor_client import LlamaCppCompressorClient

_PROBE_MARKERS = (
    '("кто с ней разговаривал" — это QUESTION)',
    '"Кто тебе сказал, что я Мю?" -> acts:',
)
_BOUNDARY_MARKERS = (
    "ASK_PROVENANCE",
    "ПРОИСХОЖДЕНИИ знания/информации",
    "НЕ использовать для вопросов о том, кто что-то сделал с третьим лицом",
)


def test_prov_x2_baseline_contains_contract_and_examples(monkeypatch):
    """Baseline (default OFF): граница класса + контаминирующие примеры на месте."""
    monkeypatch.delenv("ENIGMA_PROV_X2", raising=False)
    client = LlamaCppCompressorClient()
    sys_a, _ = client._build_prompts("тест", {})
    for m in _BOUNDARY_MARKERS:
        assert m in sys_a, f"граница класса потеряна в baseline: {m}"
    for m in _PROBE_MARKERS:
        assert m in sys_a, f"baseline изменился без флага: {m}"


def test_prov_x2_on_removes_probe_phrases_keeps_boundary(monkeypatch):
    """X2 (ON): probe-фразы корпуса отсутствуют, граница класса цела."""
    monkeypatch.setenv("ENIGMA_PROV_X2", "1")
    client = LlamaCppCompressorClient()
    sys_x2, _ = client._build_prompts("тест", {})
    for m in _PROBE_MARKERS:
        assert m not in sys_x2, f"probe-фраза пережила X2: {m}"
    for m in _BOUNDARY_MARKERS:
        assert m in sys_x2, f"граница класса потеряна в X2: {m}"


def test_prov_x2_diff_is_single_contract_line(monkeypatch):
    """Дифф A→X2: ровно одна строка изменена, остальной промпт идентичен."""
    monkeypatch.delenv("ENIGMA_PROV_X2", raising=False)
    client = LlamaCppCompressorClient()
    sys_a, _ = client._build_prompts("тест", {})
    monkeypatch.setenv("ENIGMA_PROV_X2", "1")
    sys_x2, _ = client._build_prompts("тест", {})
    removed = set(sys_a.splitlines()) - set(sys_x2.splitlines())
    added = set(sys_x2.splitlines()) - set(sys_a.splitlines())
    assert len(removed) == 1, f"X2 меняет более одной строки (removed): {removed}"
    assert len(added) == 1, f"X2 меняет более одной строки (added): {added}"
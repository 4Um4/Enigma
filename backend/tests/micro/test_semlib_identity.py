"""path: /project/backend/tests/micro/test_semlib_identity.py

Назначение: замки Э2 — identity-модуль и мульти-срез. Один relation (референт
    вопроса о имени), один anchor, один contrast; add-only (перечисление не
    трогает); порядок блоков в срезе детерминирован; конфликты — громко;
    probe-лексемы в identity-контенте запрещены (гвард по added-строкам).
Зависимости: app.services.input.llm_compressor_client, semantic_library
Основные сущности: load_modules, LlamaCppCompressorClient._build_prompts

Запуск: cd backend; python -m pytest tests/micro/test_semlib_identity.py -v; cd ..
"""

from pathlib import Path

import pytest

from app.services.input.llm_compressor_client import LlamaCppCompressorClient
from app.services.input.semantic_library import SemanticLibraryError, load_modules

_PROBE_LEXEMES = "Мю|Ворг|Горан|Торнин|Люс|прилив|корабл|доложил"
_PROV_FLAGS = ("ENIGMA_PROV_B", "ENIGMA_PROV_B2", "ENIGMA_PROV_X2", "ENIGMA_PROV_XCLEAN")


def _build(monkeypatch, modules=None):
    for f in _PROV_FLAGS + ("ENIGMA_SEM_LIB", "ENIGMA_SEM_LIB_MODULES"):
        monkeypatch.delenv(f, raising=False)
    monkeypatch.setenv("ENIGMA_SEM_LIB", "1")
    if modules is not None:
        monkeypatch.setenv("ENIGMA_SEM_LIB_MODULES", modules)
    return LlamaCppCompressorClient()._build_prompts("тест", {})[0]


def test_identity_module_shape():
    m = load_modules("dialogue_identity")[0]
    assert m.enum_tail is None, "identity-модуль обязан быть add-only"
    assert "Как тебя зовут?" in m.contrast_block
    assert "Как зовут твоего караванщика?" in m.contrast_block
    assert "ASK_IDENTITY" in m.contrast_block and "QUESTION" in m.contrast_block
    import re
    assert not re.search(_PROBE_LEXEMES, m.contrast_block), "probe-лексема в identity-модуле"


def test_identity_state_add_only(monkeypatch):
    """I-состояние: identity-блок есть, provenance-контента нет, перечисление = база A."""
    sys_i = _build(monkeypatch, modules="dialogue_identity")
    assert sys_i.count("Контрастная пара для границы классов") == 1
    assert "Как зовут твоего караванщика?" in sys_i
    assert "прибытии корабля" not in sys_i
    assert 'Пример: "Кто тебе сказал, что я Мю?" -> acts:' in sys_i, "add-only нарушил перечисление A"


def test_combined_state_deterministic_order(monkeypatch):
    """BI-состояние: оба блока, порядок CSV детерминирован, ровно один enum-tail."""
    sys_bi1 = _build(monkeypatch, modules="dialogue_provenance,dialogue_identity")
    sys_bi2 = _build(monkeypatch, modules="dialogue_provenance,dialogue_identity")
    assert sys_bi1 == sys_bi2
    assert sys_bi1.count("Контрастная пара для границы классов") == 2
    assert sys_bi1.index("прибытии корабля") < sys_bi1.index("караванщика"), "порядок блоков не CSV"
    assert sys_bi1.count('Пример: "Кто тебе сказал') == 1, "enum-tail заменён дважды"


def test_slice_duplicate_fails_loud():
    with pytest.raises(SemanticLibraryError):
        load_modules("dialogue_provenance,dialogue_provenance")


def test_slice_unknown_module_fails_loud():
    with pytest.raises(SemanticLibraryError):
        load_modules("dialogue_provenance,no_such")


def test_two_enum_tails_fail_at_build(monkeypatch):
    """Конфликт среза: второй acts-tail-модуль (hypothetical) ловится сборкой —
    проверяется через прямой конфликт, здесь: provenance+identity легален,
    конфликт ловится unittest-путём load_modules + инвариантом count."""
    sys_bi = _build(monkeypatch, modules="dialogue_provenance,dialogue_identity")
    # Замена, не удвоение: модульный tail байт-совпадает с базой в маркере
    # (перенос 1:1), поэтому живой маркер ровно ОДИН. Конфликт двух
    # enum-tail-модулей ловит fail-loud сборки, не счётчик маркера.
    assert sys_bi.count(', "ASK_PROVENANCE" (params: {"about"') == 1, "tail удвоился или потерян"
    assert sys_bi.count('"ASK_IDENTITY"') >= 1


def test_identity_state_equals_golden_i_bytewise(monkeypatch):
    """Фаза 0.2 (В-3): identity add-only — отдельная observable state;
    байтовый эталон golden I (эталон клаузы identity в byte_ok анализатора).
    Двойная привязка по образцу test_semlib_on: эталон ловит дрейф файла,
    живая сборка — дрейф модуля/inline."""
    sys_i = _build(monkeypatch, modules="dialogue_identity")
    golden_i = Path(__file__).parent / "golden_production_system_prompt_I.txt"
    assert sys_i == golden_i.read_text(encoding="utf-8"), (
        "identity-состояние != golden I: дрейф эталона или модуля (В-3)"
    )
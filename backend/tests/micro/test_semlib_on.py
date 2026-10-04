"""path: /project/backend/tests/micro/test_semlib_on.py

Назначение: приёмка Э0 ON. Библиотечный промпт байт-в-байт равен golden
    состояния B и живому inline-состоянию B (двойная привязка: golden ловит
    дрейф библиотеки, живое сравнение — дрейф inline); prov-флаги при ON
    игнорируются (библиотека — единственный владелец региона); B2 dormant.
Зависимости: app.services.input.llm_compressor_client, golden_production_system_prompt_B.txt
Основные сущности: LlamaCppCompressorClient._build_prompts

Запуск: cd backend; python -m pytest tests/micro/test_semlib_on.py -v; cd ..
"""

from pathlib import Path

from app.services.input.llm_compressor_client import LlamaCppCompressorClient

_PROV_FLAGS = ("ENIGMA_PROV_B", "ENIGMA_PROV_B2", "ENIGMA_PROV_X2", "ENIGMA_PROV_XCLEAN")
_GOLDEN_B = Path(__file__).parent / "golden_production_system_prompt_B.txt"


def _build(monkeypatch, **env):
    for flag in _PROV_FLAGS + ("ENIGMA_SEM_LIB",):
        monkeypatch.delenv(flag, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return LlamaCppCompressorClient()._build_prompts("тест", {})[0]


def test_semlib_on_equals_golden_b_bytewise(monkeypatch):
    lib_on = _build(monkeypatch, ENIGMA_SEM_LIB="1")
    assert lib_on == _GOLDEN_B.read_text(encoding="utf-8"), (
        "библиотечный промпт != golden состояния B (Э0 acceptance: byte-for-byte)"
    )


def test_semlib_on_equals_inline_b_state_bytewise(monkeypatch):
    lib_on = _build(monkeypatch, ENIGMA_SEM_LIB="1")
    inline_b = _build(monkeypatch, ENIGMA_PROV_B="1")
    assert lib_on == inline_b


def test_semlib_on_ignores_prov_flags(monkeypatch):
    lib_alone = _build(monkeypatch, ENIGMA_SEM_LIB="1")
    lib_all = _build(
        monkeypatch,
        ENIGMA_SEM_LIB="1",
        ENIGMA_PROV_B="1",
        ENIGMA_PROV_B2="1",
        ENIGMA_PROV_X2="1",
        ENIGMA_PROV_XCLEAN="1",
    )
    assert lib_all == lib_alone


def test_semlib_on_b2_content_dormant(monkeypatch):
    lib_on = _build(monkeypatch, ENIGMA_SEM_LIB="1")
    assert "прилив" not in lib_on
"""path: /project/backend/tests/micro/test_semlib_router.py

Назначение: приёмка Phase 1 (SR-1 Oracle Isolation, GO Мастера A).
    ОБЯЗАТЕЛЬНОЕ УСЛОВИЕ Мастера: пустой срез — НАСТОЯЩИЙ ноль модулей:
    ON+router(NONE) == golden A БАЙТ-В-БАЙТ на финальном канонизационном
    промпте («∅ = PROV по умолчанию» исключается замком, не мнением).
    ON+router(PROV) == golden B (шов не искажает сборку). router(ID) —
    не A и не B, содержит identity-контраст-блок. Семья не активана
    (оружие рук) и неизвестная фраза -> пустой срез (= A). Router off ->
    прежний CSV-путь (замок test_semlib_on не тронут).
Зависимости: app.services.input.llm_compressor_client, semantic_router,
    golden A/B.
Основные сущности: LlamaCppCompressorClient._build_prompts.

Запуск: cd backend; python -m pytest tests/micro/test_semlib_router.py -v; cd ..
"""

import json
from pathlib import Path

import pytest

from app.services.input.llm_compressor_client import LlamaCppCompressorClient

_GOLDEN_A = Path(__file__).parent / "golden_production_system_prompt_A.txt"
_GOLDEN_B = Path(__file__).parent / "golden_production_system_prompt_B.txt"

_ROUTER_ENV = (
    "ENIGMA_SEM_LIB",
    "ENIGMA_SEM_ROUTER",
    "ENIGMA_SEM_ROUTER_ORACLE_LABELS",
    "ENIGMA_SEM_ROUTER_ORACLE_FAMILIES",
    "ENIGMA_SEM_LIB_MODULES",
)


@pytest.fixture()
def labels_file(tmp_path):
    fixture = {
        "тест пров": "PROV",
        "тест идент": "ID",
        "тест пусто": "EMPTY",
    }
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _build(monkeypatch, labels_path, raw_text, families="PROV,ID"):
    for flag in _ROUTER_ENV:
        monkeypatch.delenv(flag, raising=False)
    monkeypatch.setenv("ENIGMA_SEM_LIB", "1")
    monkeypatch.setenv("ENIGMA_SEM_ROUTER", "oracle")
    monkeypatch.setenv("ENIGMA_SEM_ROUTER_ORACLE_LABELS", labels_path)
    monkeypatch.setenv("ENIGMA_SEM_ROUTER_ORACLE_FAMILIES", families)
    return LlamaCppCompressorClient()._build_prompts(raw_text, {})[0]


def test_router_empty_equals_golden_a_bytewise(monkeypatch, labels_file):
    prompt = _build(monkeypatch, labels_file, "тест пусто")
    assert prompt == _GOLDEN_A.read_text(encoding="utf-8"), (
        "ON+router(NONE) != golden A: пустой срез не настоящий (вердикт Мастера)"
    )


def test_router_prov_equals_golden_b_bytewise(monkeypatch, labels_file):
    prompt = _build(monkeypatch, labels_file, "тест пров")
    assert prompt == _GOLDEN_B.read_text(encoding="utf-8"), (
        "ON+router(PROV) != golden B: шов роутера искажает сборку"
    )


def test_router_identity_is_neither_a_nor_b(monkeypatch, labels_file):
    from app.services.input.semantic_library import load_module

    prompt = _build(monkeypatch, labels_file, "тест идент")
    assert prompt != _GOLDEN_A.read_text(encoding="utf-8")
    assert prompt != _GOLDEN_B.read_text(encoding="utf-8")
    assert load_module("dialogue_identity").contrast_block.strip() in prompt


def test_router_family_disabled_routes_empty(monkeypatch, labels_file):
    # Оружие рук: ORC-B (FAMILIES=PROV) — identity-фраза получает пустой срез (= A).
    prompt = _build(monkeypatch, labels_file, "тест идент", families="PROV")
    assert prompt == _GOLDEN_A.read_text(encoding="utf-8")


def test_router_unknown_text_routes_empty(monkeypatch, labels_file):
    # INV-SR-1: неизвестная фраза — fail-open в пустой срез, не в дефолт-модуль.
    prompt = _build(monkeypatch, labels_file, "фраза вне меток")
    assert prompt == _GOLDEN_A.read_text(encoding="utf-8")


def test_router_off_keeps_csv_path(monkeypatch):
    # Router off: прежний CSV-путь (default provenance) — замок test_semlib_on цел.
    for flag in _ROUTER_ENV:
        monkeypatch.delenv(flag, raising=False)
    monkeypatch.setenv("ENIGMA_SEM_LIB", "1")
    prompt = LlamaCppCompressorClient()._build_prompts("тест", {})[0]
    assert prompt == _GOLDEN_B.read_text(encoding="utf-8")
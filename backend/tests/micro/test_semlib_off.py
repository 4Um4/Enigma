"""path: /project/backend/tests/micro/test_semlib_off.py

Назначение: приёмка Э0 OFF. Флаг отсутствует → loader-путь мёртв (import не
    исполняется — перехват load_module обязан не сработать), промпт байт-в-байт
    равен golden текущего production (A); сборка детерминирована.
Зависимости: app.services.input.llm_compressor_client, golden_production_system_prompt_A.txt
Основные сущности: LlamaCppCompressorClient._build_prompts

Запуск: cd backend; python -m pytest tests/micro/test_semlib_off.py -v; cd ..
"""

from pathlib import Path

from app.services.input.llm_compressor_client import LlamaCppCompressorClient

_GOLDEN_A = Path(__file__).parent / "golden_production_system_prompt_A.txt"


def test_semlib_off_loader_never_invoked(monkeypatch):
    import app.services.input.semantic_library as semlib

    def _boom(*args, **kwargs):
        raise AssertionError("loader вызван при OFF — путь не мёртв, OFF-гарантия сломана")

    monkeypatch.setattr(semlib, "load_module", _boom)
    monkeypatch.delenv("ENIGMA_SEM_LIB", raising=False)
    sys_prompt, _ = LlamaCppCompressorClient()._build_prompts("тест", {})
    assert "ASK_PROVENANCE" in sys_prompt


def test_semlib_off_equals_golden_production_bytewise(monkeypatch):
    monkeypatch.delenv("ENIGMA_SEM_LIB", raising=False)
    sys_prompt, _ = LlamaCppCompressorClient()._build_prompts("тест", {})
    assert sys_prompt == _GOLDEN_A.read_text(encoding="utf-8"), (
        "OFF-промпт дрейфанул от golden production (Э0 acceptance: byte-for-byte)"
    )


def test_semlib_build_deterministic(monkeypatch):
    monkeypatch.delenv("ENIGMA_SEM_LIB", raising=False)
    client = LlamaCppCompressorClient()
    first, _ = client._build_prompts("тест", {})
    second, _ = client._build_prompts("тест", {})
    assert first == second
"""Integration tests for ТЗ-5 LLM Contract Repair.

Запуск: cd backend; python -m pytest tests/test_tz5_llm_contract.py -v --tb=short; cd ..
"""
import pytest
from pathlib import Path

class TestPatchA_NormalizerAndValidator:
    def test_dm_response_normalizer_recovers_npc_schema(self):
        from app.services.verbalization.dm_response_normalizer import DMResponseNormalizer
        r = DMResponseNormalizer.normalize('{"speech": "Привет!"}')
        assert r.dm_text == "Привет!"
        assert r.schema_type == "npc_schema"

    def test_dm_response_normalizer_parses_plain_text(self):
        from app.services.verbalization.dm_response_normalizer import DMResponseNormalizer
        r = DMResponseNormalizer.normalize("Просто текст без JSON")
        assert r.dm_text == "Просто текст без JSON"
        assert r.schema_type == "unknown"

    def test_dm_response_normalizer_parses_valid_dm_json(self):
        from app.services.verbalization.dm_response_normalizer import DMResponseNormalizer
        r = DMResponseNormalizer.normalize('{"dm_response": "Тестовый ответ"}')
        assert r.dm_text == "Тестовый ответ"
        assert r.schema_type == "dm_response"

    def test_contains_dialog_no_dash(self):
        from app.services.verbalization.response_validator import ResponseValidator
        from app.services.verbalization.dm_contract_builder import DMContractBuilder
        validator = ResponseValidator(DMContractBuilder().build())
        assert validator._contains_dialog("— Это просто нарратив") == False
        assert validator._contains_dialog('Он сказал: "Привет"') == True

    def test_non_russian_rejects_mock_and_cjk(self):
        from app.services.verbalization.response_validator import ResponseValidator
        from app.services.verbalization.dm_contract_builder import DMContractBuilder
        validator = ResponseValidator(DMContractBuilder().build())
        assert validator._contains_non_russian("中文 текст") == True
        assert validator._contains_non_russian("[Mock] Что-то произошло") == True
        assert validator._contains_non_russian("The quick brown fox") == True

    def test_non_russian_allows_russian_with_english_terms(self):
        from app.services.verbalization.response_validator import ResponseValidator
        from app.services.verbalization.dm_contract_builder import DMContractBuilder
        validator = ResponseValidator(DMContractBuilder().build())
        assert validator._contains_non_russian("Игрок открыл Inventory меню") == False

class TestPatchA_Settings:
    def test_dm_max_tokens_exists(self):
        from app.core.config import Settings
        s = Settings()
        assert hasattr(s, "dm_max_tokens")
        assert isinstance(s.dm_max_tokens, int)

class TestPatchA_DMAgent:
    def test_get_last_dm_response_method_exists(self):
        from app.agents.dm_agent import DmAgent
        assert hasattr(DmAgent, "_get_last_dm_response")
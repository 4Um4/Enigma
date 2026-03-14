# backend/tests/test_run_terminal_dm.py
import pytest

# Корректные импорты через sys.path из conftest.py
from run_terminal_dm import build_prompt, _normalize_subcommand, _truncate_str

# ----------------------------------------
# Фикстуры (данные для контекста)
# ----------------------------------------
@pytest.fixture
def example_context():
    return {
        "world_canon": [{"text": "Мир полон магии"}],
        "campaign_memory": [{"event": "Битва с драконом"}],
        "session_memory": [{"player_text": "Атакую дракона"}]
    }

# ----------------------------------------
# Тесты
# ----------------------------------------
def test_build_prompt_truncation(example_context):
    user_text = "Что я делаю дальше?"
    prompt = build_prompt(user_text, example_context)
    assert "Ты ИИ-мастер D&D 5e" in prompt
    assert user_text in prompt
    assert "Битва с драконом" in prompt

def test_normalize_subcommand():
    assert _normalize_subcommand("добавить") == "add"
    assert _normalize_subcommand("Add") == "add"
    assert _normalize_subcommand("-") == "del"
    assert _normalize_subcommand("удалить") == "del"
    assert _normalize_subcommand("unknown") is None

def test_truncate_str():
    s = "1234567890"
    assert _truncate_str(s, 5) == "12345 [...]"
    assert _truncate_str(s, 20) == s
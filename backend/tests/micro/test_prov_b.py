"""path: /project/backend/tests/micro/test_prov_b.py

Назначение: замок B (вердикт Мастера): база A + одна контрастная пара на
    чужом контенте ТОЛЬКО env ENIGMA_PROV_B=1; default OFF = baseline
    байт-неизменен; корпусные лексемы в B-блоке запрещены (grep-гвард по
    скоупу блока, не всего промпта — few-shot/actor/addressee-зоны
    production легальны); дифф A→B = 1 добавленная строка, 0 удалённых.
Зависимости: app.services.input.llm_compressor_client
Основные сущности: LlamaCppCompressorClient._build_prompts

Запуск: cd backend; python -m pytest tests/micro/test_prov_b.py -v; cd ..
"""

import re

from app.services.input.llm_compressor_client import LlamaCppCompressorClient

# Лексемы probe-корпуса (стемы): Мю/Ворг/Горан/Торнин/Люс(и|ей|е|ю).
# Слова самой B-пары («доложил», «корабль») сюда НЕ входят — они чужие
# корпусу по ФАЗА-1-гварду и легальны в блоке.
_PROBE_LEXEMES = "Мю|Ворг|Горан|Торнин|Люс"


def test_prov_b_off_baseline_intact(monkeypatch):
    """Default OFF: B-блока нет, production дрейфа не имеет."""
    monkeypatch.delenv("ENIGMA_PROV_B", raising=False)
    client = LlamaCppCompressorClient()
    sys_a, _ = client._build_prompts("тест", {})
    assert "Контрастная пара для границы классов" not in sys_a
    assert "ASK_PROVENANCE" in sys_a  # production контракт жив


def test_prov_b_on_single_contrast_pair(monkeypatch):
    """ON: ровно одна контрастная пара, отношение, не ключевые слова."""
    monkeypatch.setenv("ENIGMA_PROV_B", "1")
    client = LlamaCppCompressorClient()
    sys_b, _ = client._build_prompts("тест", {})
    assert sys_b.count("Контрастная пара для границы классов") == 1
    assert "Кто тебе доложил о прибытии корабля?" in sys_b
    assert "Кто разгружает корабль?" in sys_b
    assert "ASK_PROVENANCE" in sys_b and "QUESTION" in sys_b


def test_prov_b_block_no_corpus_lexemes(monkeypatch):
    """Grep-гвард по СКОПУ БЛОКА: корпусные лексемы в B-блоке запрещены."""
    monkeypatch.setenv("ENIGMA_PROV_B", "1")
    client = LlamaCppCompressorClient()
    sys_b, _ = client._build_prompts("тест", {})
    sys_off = _off_prompt(monkeypatch)
    added_lines = [l for l in sys_b.splitlines() if l not in set(sys_off.splitlines())]
    assert len(added_lines) == 1, f"B меняет не ровно 1 строку: {added_lines}"
    assert not re.search(_PROBE_LEXEMES, added_lines[0]), f"корпусная лексема в B-блоке: {added_lines[0]}"


def _off_prompt(monkeypatch):
    monkeypatch.delenv("ENIGMA_PROV_B", raising=False)
    client = LlamaCppCompressorClient()
    sys_off, _ = client._build_prompts("тест", {})
    return sys_off
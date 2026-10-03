"""path: /project/backend/tests/micro/test_prov_b2.py

Назначение: замок B2 (вердикт Мастера): база A + ВТОРАЯ контрастная пара
    (откуда-знаешь vs когда-случается, контент «прилив/расписание») ТОЛЬКО
    env ENIGMA_PROV_B2=1; default OFF = baseline байт-неизменен; пары B и B2
    никогда не сосуществуют (независимые флаги, один якорь на состояние);
    контент B2 чужой корпусу и паре B (grep-гварды по скоупу added-строк —
    урок XCLEAN: уникальность по count, не только присутствие).
Зависимости: app.services.input.llm_compressor_client
Основные сущности: LlamaCppCompressorClient._build_prompts

Запуск: cd backend; python -m pytest tests/micro/test_prov_b2.py -v; cd ..
"""

import re

from app.services.input.llm_compressor_client import LlamaCppCompressorClient

# Корпусные лексемы + якорь пары B: в B2-блоке запрещены.
_PROBE_LEXEMES = r"Мю|Ворг|Горан|Торнин|Люс|корабл|доложил"


def test_prov_b2_off_baseline_intact(monkeypatch):
    """Default OFF: B2-блока нет, production байт-неизменен."""
    monkeypatch.delenv("ENIGMA_PROV_B2", raising=False)
    monkeypatch.delenv("ENIGMA_PROV_B", raising=False)
    monkeypatch.delenv("ENIGMA_PROV_X2", raising=False)
    monkeypatch.delenv("ENIGMA_PROV_XCLEAN", raising=False)
    client = LlamaCppCompressorClient()
    sys_a, _ = client._build_prompts("тест", {})
    assert "расписании приливов" not in sys_a
    assert "Когда приходит прилив?" not in sys_a
    assert sys_a.count("Контрастная пара для границы классов") == 0
    assert "ASK_PROVENANCE" in sys_a  # production контракт жив


def test_prov_b2_on_single_contrast_pair(monkeypatch):
    """ON: ровно одна контрастная пара, отношение, не ключевые слова."""
    monkeypatch.setenv("ENIGMA_PROV_B2", "1")
    client = LlamaCppCompressorClient()
    sys_b2, _ = client._build_prompts("тест", {})
    assert sys_b2.count("Контрастная пара для границы классов") == 1
    assert "Откуда ты знаешь расписание приливов?" in sys_b2
    assert "Когда приходит прилив?" in sys_b2
    assert "ASK_PROVENANCE" in sys_b2 and "QUESTION" in sys_b2
    # Пара B не контаминирует B2-состояние (независимые флаги).
    assert "Кто тебе доложил о прибытии корабля?" not in sys_b2


def test_prov_b2_b_state_has_no_b2_content(monkeypatch):
    """Симметрия: состояние B не содержит контента B2 (пары не сосуществуют)."""
    monkeypatch.delenv("ENIGMA_PROV_B2", raising=False)
    monkeypatch.setenv("ENIGMA_PROV_B", "1")
    client = LlamaCppCompressorClient()
    sys_b, _ = client._build_prompts("тест", {})
    assert sys_b.count("Контрастная пара для границы классов") == 1
    assert "расписании приливов" not in sys_b
    assert "Когда приходит прилив?" not in sys_b


def test_prov_b2_diff_is_single_added_line_and_content_guard(monkeypatch):
    """Дифф A→B2 = ровно 1 added-строка, 0 removed; grep-гварды по скоупу блока."""
    monkeypatch.delenv("ENIGMA_PROV_B2", raising=False)
    client = LlamaCppCompressorClient()
    sys_off, _ = client._build_prompts("тест", {})
    monkeypatch.setenv("ENIGMA_PROV_B2", "1")
    client2 = LlamaCppCompressorClient()
    sys_b2, _ = client2._build_prompts("тест", {})
    added = [l for l in sys_b2.splitlines() if l not in set(sys_off.splitlines())]
    removed = [l for l in sys_off.splitlines() if l not in set(sys_b2.splitlines())]
    assert len(removed) == 0, f"B2 удаляет строки: {removed}"
    assert len(added) == 1, f"B2 меняет не ровно 1 строку: {added}"
    assert not re.search(_PROBE_LEXEMES, added[0]), f"чужой контент в B2-блоке: {added[0]}"
    # Якорь живёт ровно в паре: 2 вопроса × (фраза + params) = 4 вхождения
    # (паттерн легальной B-пары: «корабл» тоже ×4). В baseline «прилив»
    # отсутствует целиком — контаминация промпта = 0, гвард самодостаточен.
    assert sys_off.count("прилив") == 0, "якорь B2 протёк в baseline-промпт"
    assert added[0].count("прилив") == 4, "якорь B2 должен появляться ровно в паре (4 = 2 вопроса × фраза+params)"
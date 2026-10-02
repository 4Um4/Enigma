"""path: /project/backend/tests/micro/test_rc8_ab_state.py

Назначение: замок RC8 A/B-переключателя (вердикт Мастера): env ENIGMA_RC8_STATE
    управляет ТОЛЬКО тремя few-shot-строками ASK_PROVENANCE в системном промпте
    компрессора. STATE-A ('A') — строки удалены; default/STATE-B — присутствуют.
    Всё остальное содержимое промпта байт-идентично (запрет «не менять
    одновременно ничего другого»), контракт типа ASK_PROVENANCE живёт в обоих.
Зависимости: app.services.input.llm_compressor_client
Основные сущности: LlamaCppCompressorClient._build_prompts

Запуск: cd backend; python -m pytest tests/micro/test_rc8_ab_state.py -v; cd ..
"""

from app.services.input.llm_compressor_client import LlamaCppCompressorClient

_MARKERS = (
    'Ввод: "Кто тебе сказал, что меня зовут Мю?" ->',
    'Ввод: "Откуда ты знаешь, что я Мю?" ->',
    'Ввод: "Кто разговаривал с Люсей?" ->',
)


def test_rc8_state_a_removes_only_fewshot_lines(monkeypatch):
    """STATE-A: удалены РОВНО 3 few-shot-строки, ничего не добавлено, контракт жив."""
    monkeypatch.setenv("ENIGMA_RC8_STATE", "A")
    client = LlamaCppCompressorClient()
    sys_a, _ = client._build_prompts("тест", {})

    monkeypatch.delenv("ENIGMA_RC8_STATE", raising=False)
    sys_b, _ = client._build_prompts("тест", {})

    for m in _MARKERS:
        assert m in sys_b, f"few-shot-строка отсутствует в STATE-B: {m}"
        assert m not in sys_a, f"few-shot-строка пережила STATE-A: {m}"

    # Контракт типа (не few-shot) обязан жить в обоих состояниях
    assert "ASK_PROVENANCE" in sys_a and "ASK_PROVENANCE" in sys_b

    # Ровно 3 строки удалено, ноль добавлено — переменная эксперимента изолирована
    removed = set(sys_b.splitlines()) - set(sys_a.splitlines())
    added = set(sys_a.splitlines()) - set(sys_b.splitlines())
    assert len(removed) == 3, f"ожидалось 3 удалённые строки, удалено: {len(removed)}"
    assert not added, f"STATE-A добавил строки (запрещено): {added}"
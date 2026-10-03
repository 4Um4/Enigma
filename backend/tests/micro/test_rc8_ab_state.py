"""path: /project/backend/tests/micro/test_rc8_ab_state.py

Назначение: замок RC8-вердикта: три few-shot-строки ASK_PROVENANCE удалены
    из production-baseline (доказанный отрицательный эффект: STATE-B 0/27
    ASK_PROVENANCE в 9 прогонах против 2-3/27 в STATE-A, контрбаланс).
    Легаси-состояние B восстанавливается ТОЛЬКО env ENIGMA_RC8_STATE='B'
    (воспроизведение эксперимента); дифф промпта — ровно 3 строки, ничего
    другого; контракт типа ASK_PROVENANCE живёт в обоих состояниях.
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


def test_rc8_baseline_removed_fewshot_lines(monkeypatch):
    """Production baseline (default): few-shot-строки отсутствуют, контракт типа жив."""
    monkeypatch.delenv("ENIGMA_RC8_STATE", raising=False)
    client = LlamaCppCompressorClient()
    sys_base, _ = client._build_prompts("тест", {})
    for m in _MARKERS:
        assert m not in sys_base, f"RC8 few-shot-строка пережила удаление: {m}"
    # Контракт типа (не few-shot) обязан жить в baseline
    assert "ASK_PROVENANCE" in sys_base


def test_rc8_legacy_state_b_restores_exactly_three_lines(monkeypatch):
    """Легаси STATE-B: ровно 3 строки возвращаются, ничего другого не меняется."""
    monkeypatch.setenv("ENIGMA_RC8_STATE", "B")
    client = LlamaCppCompressorClient()
    sys_b, _ = client._build_prompts("тест", {})

    monkeypatch.delenv("ENIGMA_RC8_STATE", raising=False)
    sys_base, _ = client._build_prompts("тест", {})

    for m in _MARKERS:
        assert m in sys_b, f"легаси-строка отсутствует в STATE-B: {m}"

    removed = set(sys_b.splitlines()) - set(sys_base.splitlines())
    added = set(sys_base.splitlines()) - set(sys_b.splitlines())
    assert len(removed) == 3, f"ожидалось 3 легаси-строки, diff: {len(removed)}"
    assert not added, f"STATE-B изменил что-то кроме 3 строк: {added}"
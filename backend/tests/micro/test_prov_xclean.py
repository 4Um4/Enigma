"""path: /project/backend/tests/micro/test_prov_xclean.py

Назначение: замок X-clean (вердикт Мастера, второй GO): ASK_PROVENANCE
    извлечён из строки-перечисления в собственную структурную строку
    контракта ТОЛЬКО env ENIGMA_PROV_XCLEAN=1 (приоритет над X2);
    probe-примеры отсутствуют; граница с QUESTION живёт в структурной
    строке; дифф A→X-clean = 1 строка перечисления + 1 строка блока.
    Default = production baseline (A), байт-неизменный.
Зависимости: app.services.input.llm_compressor_client
Основные сущности: LlamaCppCompressorClient._build_prompts

Запуск: cd backend; python -m pytest tests/micro/test_prov_xclean.py -v; cd ..
"""

from app.services.input.llm_compressor_client import LlamaCppCompressorClient

_ENUM_ITEM = ', "FAREWELL", "ASK_PROVENANCE" (params: {"about": "о чём спрашивают происхождение"}). ASK_PROVENANCE = вопрос о ПРОИСХОЖДЕНИИ'
_EXAMPLE_MARKER = 'Пример: "Кто тебе сказал, что я Мю?" -> acts:'
_BLOCK_MARKER = '- Допустимый type "ASK_PROVENANCE": вопрос об ИСТОЧНИКЕ ЗНАНИЯ СОБЕСЕДНИКА'
_BLOCK_QUESTION_EDGE = 'ГРАНИЦА с QUESTION: вопрос о событиях, фактах или действиях третьих лиц в мире = QUESTION'


def test_xclean_off_baseline_intact(monkeypatch):
    """Default: перечисление с ASK_PROVENANCE и примерами, структурного блока нет."""
    monkeypatch.delenv("ENIGMA_PROV_XCLEAN", raising=False)
    monkeypatch.delenv("ENIGMA_PROV_X2", raising=False)
    client = LlamaCppCompressorClient()
    sys_a, _ = client._build_prompts("тест", {})
    assert _ENUM_ITEM in sys_a, "baseline-перечисление дрейфнуло после рефактора сборки"
    assert _EXAMPLE_MARKER in sys_a
    assert _BLOCK_MARKER not in sys_a
    assert sys_a.count(', "ASK_PROVENANCE" (params: {"about"') == 1, "дубликат элемента перечисления в OFF — сборка сломана"


def test_xclean_on_extracts_class(monkeypatch):
    """X-clean: тип извлечён из перечисления, структурная строка с границей, примеров нет."""
    monkeypatch.setenv("ENIGMA_PROV_XCLEAN", "1")
    client = LlamaCppCompressorClient()
    sys_x, _ = client._build_prompts("тест", {})
    assert _BLOCK_MARKER in sys_x
    assert _BLOCK_QUESTION_EDGE in sys_x
    assert _EXAMPLE_MARKER not in sys_x, "probe-пример пережил X-clean"
    assert ', "FAREWELL", "ASK_PROVENANCE"' not in sys_x, "тип не извлечён из перечисления"
    assert '"FAREWELL". Для одиночного действия' in sys_x, "перечисление закрылось с артефактом"
    assert sys_x.count(', "ASK_PROVENANCE" (params: {"about"') == 0, "элемент перечисления пережил X-clean"


def test_xclean_diff_enum_line_plus_block(monkeypatch):
    """Дифф A→X-clean: 1 строка перечисления изменена + 1 строка блока добавлена."""
    monkeypatch.delenv("ENIGMA_PROV_XCLEAN", raising=False)
    monkeypatch.delenv("ENIGMA_PROV_X2", raising=False)
    client = LlamaCppCompressorClient()
    sys_a, _ = client._build_prompts("тест", {})
    monkeypatch.setenv("ENIGMA_PROV_XCLEAN", "1")
    sys_x, _ = client._build_prompts("тест", {})
    removed = set(sys_a.splitlines()) - set(sys_x.splitlines())
    added = set(sys_x.splitlines()) - set(sys_a.splitlines())
    assert len(removed) == 1, f"ожидалась 1 изменённая строка (removed): {removed}"
    assert len(added) == 2, f"ожидались 2 строки (перечисление + блок): {added}"
"""path: /project/backend/tests/micro/test_dm_json_wrapper.py

Назначение: R18-замок (вердикт Мастера). Контракт DMResponseNormalizer:
    таблица входов -> всегда чистый текст БЕЗ подстроки dm_response.
    Ключевой фальсификатор — double-encoded JSON (json-in-json), выживавшая
    форма R18 на retry-пути dm_agent. Плюс комбинация слоёв: markdown
    поверх double-encoded. Depth guard: ровно один дополнительный decode.
Зависимости: app.services.verbalization.dm_response_normalizer.
Основные сущности: test_dm_json_wrapper_table.

Запуск: cd backend; python -m pytest tests/micro/test_dm_json_wrapper.py -v; cd ..
"""

import json

import pytest
from app.services.verbalization.dm_response_normalizer import DMResponseNormalizer

_INNER = '{"dm_response": "Горан кивает."}'
_DOUBLE_ENCODED = json.dumps(_INNER)  # '"{\"dm_response\": ...}"' — строка JSON


@pytest.mark.parametrize(
    "case, raw, expected",
    [
        ("plain text", "Привет, Михаил", "Привет, Михаил"),
        ("single JSON", _INNER, "Горан кивает."),
        ("markdown JSON", "```json\n" + _INNER + "\n```", "Горан кивает."),
        ("double-encoded JSON", _DOUBLE_ENCODED, "Горан кивает."),
        ("dict input", {"dm_response": "Горан кивает."}, "Горан кивает."),
        (
            "markdown + double-encoded",
            "```json\n" + _DOUBLE_ENCODED + "\n```",
            "Горан кивает.",
        ),
    ],
    ids=str,
)
def test_dm_json_wrapper_table(case, raw, expected):
    out = DMResponseNormalizer.normalize(raw)
    assert out.dm_text == expected, f"[{case}] got {out.dm_text!r}"
    # Инвариант Мастера: обёртка не доезжает до текста игрока ни в каком виде.
    assert "dm_response" not in out.dm_text, f"[{case}] wrapper leaked"


def test_plain_text_with_brace_stays_text():
    """Depth-guard: строка с '{' но не валидный JSON — не разваливается,
    поведение прежнее (декодирование не рекурсивное)."""
    raw = "{непонятно что"
    out = DMResponseNormalizer.normalize(raw)
    assert out.dm_text == raw
    assert out.schema_type == "unknown"
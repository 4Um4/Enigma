"""
path: /project/backend/tests/micro/test_adr_parser_dotted_id.py
Назначение: Регрессия парсера ADR-Net: ID с точкой (ADR-310.1) не теряются.
Зависимости: app.services.adr_net.adr_parser
Основные сущности: test_dotted_id_parsed, test_atlas_line_formats
"""

from app.services.adr_net.adr_parser import _ADR_LINE_REGEX


def test_dotted_id_parsed():
    # Регрессия №65: [A-Za-z0-9\-] без точки терял ADR-310.1/S82.0/S96.1
    m = _ADR_LINE_REGEX.search("`ADR-310.1` [STANDARD] **IMPACT**")
    assert m and m.group(1) == "ADR-310.1"


def test_id_boundary_not_greedy():
    # Точка не съедает следующую группу: TYPE остаётся отдельным
    m = _ADR_LINE_REGEX.search("`ADR-S96.1` [STANDARD] **IMPACT**")
    assert m and m.group(2) == "STANDARD" and m.group(3) == "IMPACT"


def test_plain_id_unchanged():
    m = _ADR_LINE_REGEX.search("`ADR-O-410` [ONTO] **Title**")
    assert m and m.group(1) == "ADR-O-410" and m.group(2) == "ONTO"

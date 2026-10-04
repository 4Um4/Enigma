"""path: /project/backend/tests/micro/test_semlib_loader.py

Назначение: замки loader'а semantic library (Э0): детерминизм, fail-loud
    (L4 — без fallback), BOM-толерантность (уроки серии), закрытая схема
    (неизвестная секция = громкий отказ), валидация имени файла vs декларации.
Зависимости: app.services.input.semantic_library
Основные сущности: load_module, list_modules, SemanticLibraryError

Запуск: cd backend; python -m pytest tests/micro/test_semlib_loader.py -v; cd ..
"""

import pytest

from app.services.input.semantic_library import (
    SemanticLibraryError,
    list_modules,
    load_module,
)


def test_load_deterministic_and_frozen():
    m1 = load_module("dialogue_provenance")
    m2 = load_module("dialogue_provenance")
    assert m1 == m2
    assert m1.name == "dialogue_provenance"
    assert m1.enum_tail.startswith(', "ASK_PROVENANCE" (params:')
    assert m1.contrast_block.startswith("\n- Контрастная пара для границы классов")
    assert m1.meta.get("family") == "provenance"


def test_list_modules_deterministic_and_schema_hidden():
    names = list_modules()
    assert names == tuple(sorted(names))
    assert "dialogue_provenance" in names
    assert all(not n.startswith("_") for n in names)


def test_missing_module_fails_loud(tmp_path):
    with pytest.raises(SemanticLibraryError):
        load_module("no_such_module", base_path=tmp_path)


def test_missing_required_section_fails_loud(tmp_path):
    (tmp_path / "bad.md").write_text(
        "# semantic-module: bad\n## enum-tail\nx\n", encoding="utf-8"
    )
    with pytest.raises(SemanticLibraryError):
        load_module("bad", base_path=tmp_path)


def test_unknown_section_fails_loud(tmp_path):
    (tmp_path / "bad2.md").write_text(
        "# semantic-module: bad2\n## enum-tail\nx\n## contrast-block\n\ny\n## magic\nz\n",
        encoding="utf-8",
    )
    with pytest.raises(SemanticLibraryError):
        load_module("bad2", base_path=tmp_path)


def test_bom_tolerated_deterministically(tmp_path):
    body = "# semantic-module: bommod\n## enum-tail\n, \"X\"\n## contrast-block\n\n- c\n"
    (tmp_path / "bommod.md").write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    m = load_module("bommod", base_path=tmp_path)
    assert m.enum_tail == ', "X"'
    assert m.contrast_block == "\n- c"


def test_declared_name_mismatch_fails_loud(tmp_path):
    (tmp_path / "declared.md").write_text(
        "# semantic-module: other\n## enum-tail\nx\n## contrast-block\n\ny\n",
        encoding="utf-8",
    )
    with pytest.raises(SemanticLibraryError):
        load_module("declared", base_path=tmp_path)
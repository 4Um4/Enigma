import py_compile
import sys
from pathlib import Path

import pytest

# Добавляем frontend в sys.path для импорта i18n и constants
_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"
sys.path.insert(0, str(_FRONTEND_DIR))

from i18n import L

# Файлы, которые мы изменяли
UI_FILES_TO_CHECK = [
    _FRONTEND_DIR / "scene_renderer.py",
    _FRONTEND_DIR / "game_screen.py",
    _FRONTEND_DIR / "campaign_select.py",
    _FRONTEND_DIR / "character_select.py",
    _FRONTEND_DIR / "map_editor" / "sprite_registry.py",
]

REQUIRED_I18N_KEYS = [
    "ui:campaign_select_title",
    "ui:campaign_not_found",
    "ui:btn_back",
    "ui:btn_play",
    "ui:char_select_title",
    "ui:char_not_found",
    "ui:btn_create_char",
    "ui:btn_select",
    "ui:new_char_title",
    "ui:field_name",
    "ui:field_archetype",
    "ui:field_temperament",
    "ui:btn_create",
    "ui:btn_cancel",
    "ui:char_level",
    "ui:sys_binding",
    "ui:sys_system",
    "ui:male_unknown",
    "ui:female_unknown",
    "ui:unknown_speaker",
    "ui:death_title",
    "ui:death_subtitle",
    "ui:journal_title",
    "ui:journal_empty",
    "ui:narrator",
    "ui:npc_label",
    "ui:nothing_happened",
    "ui:going_to",
    "intent:observe",
    "intent:talk",
    "dir:north",
    "dir:south",
]

REQUIRED_CONSTANTS = [
    "COLOR_TEXT_DEFAULT",
    "COLOR_TEXT_DIM",
    "COLOR_TEXT_MUTED",
    "COLOR_TEXT_DARK",
    "COLOR_TEXT_OBS_TITLE",
    "COLOR_TEXT_OBS_LINE",
    "COLOR_TEXT_SCALE_HIGHLIGHT",
    "COLOR_TEXT_SYS_MSG",
    "COLOR_DEATH_TITLE",
    "COLOR_DEATH_SUB",
    "COLOR_JOURNAL_TITLE",
    "COLOR_NARRATOR",
    "COLOR_NPC_NAME",
    "COLOR_MANIFEST_DEFAULT",
    "RENDER_COLORS",
    "AGGRESSION_COLORS",
    "FONT_NAME_MAIN",
    "FONT_NAME_UI",
    "FONT_SIZE_SMALL",
    "FONT_SIZE_AUDIO",
    "FONT_SIZE_BODY",
    "FONT_SIZE_TOOLTIP",
    "SCALE_PIXELS_PER_METER",
]


def test_ui_files_compile():
    """Проверяет, что все измененные UI файлы не содержат синтаксических ошибок."""
    for file_path in UI_FILES_TO_CHECK:
        assert file_path.exists(), f"Файл не найден: {file_path}"
        try:
            py_compile.compile(str(file_path), doraise=True)
        except py_compile.PyCompileError as e:
            pytest.fail(f"Синтаксическая ошибка в {file_path.name}:\n{e}")


def test_i18n_keys_exist():
    """Проверяет, что все необходимые ключи локализации добавлены в i18n.py."""
    missing_keys = [key for key in REQUIRED_I18N_KEYS if key not in L]
    assert not missing_keys, f"Отсутствуют ключи i18n: {missing_keys}"


def test_constants_exist():
    """Проверяет, что все необходимые константы добавлены в constants.py."""
    import constants

    missing_consts = [c for c in REQUIRED_CONSTANTS if not hasattr(constants, c)]
    assert not missing_consts, f"Отсутствуют константы: {missing_consts}"


def test_no_russian_string_literals_in_render():
    """Точная проверка через AST, что в scene_renderer.py не осталось хардкодов (исключая docstrings)."""
    import ast
    import re

    file_path = _FRONTEND_DIR / "scene_renderer.py"
    content = file_path.read_text(encoding="utf-8")

    bad_strings = []
    tree = ast.parse(content)

    # Собираем все AST-узлы, которые являются docstrings, чтобы их игнорировать
    docstring_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Module)):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                docstring_nodes.add(node.body[0].value)

    for node in ast.walk(tree):
        # Ищем только строковые константы
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node in docstring_nodes:
                continue
            val = node.value
            # Если строка содержит кириллицу
            if re.search(r"[А-Яа-яЁё]", val):
                bad_strings.append(val)

    assert not bad_strings, f"Найдены русские строки (возможные хардкоды) в scene_renderer.py: {bad_strings}"


def test_sprite_registry_has_get_entity_sprite():
    """Проверяет, что метод get_entity_sprite перенесен в sprite_registry.py."""
    file_path = _FRONTEND_DIR / "map_editor" / "sprite_registry.py"
    content = file_path.read_text(encoding="utf-8")
    assert "def get_entity_sprite" in content, "Метод get_entity_sprite не найден в sprite_registry.py"
    assert "ENTITY_SPRITE_MAP" in content, "Словарь ENTITY_SPRITE_MAP не найден в sprite_registry.py"
    assert "sprite_registry = SpriteRegistry()" in content, "Глобальный инстанс не найден"


def test_sprite_resolver_deleted():
    """Проверяет, что старый файл sprite_resolver.py удален."""
    file_path = _FRONTEND_DIR / "sprite_resolver.py"
    assert not file_path.exists(), f"Файл {file_path} должен быть удален"

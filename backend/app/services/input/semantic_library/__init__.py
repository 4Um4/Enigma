"""path: /project/backend/app/services/input/semantic_library/__init__.py

Назначение: Semantic Library v0 (Э0, вердикт Мастера). Семантическое знание
    хранится модульно на диске; активный промпт получает ограниченный срез.
    Production source of truth остаётся inline (миграция — отдельный вердикт);
    OFF-путь мёртв, ON — байт-эквивалент состоянию B (замки test_semlib_*).
    Router отсутствует by design (Э0-Э2): шов router'а — выбор модуля между
    list_modules() и load_module(); отсутствие выбора — осознанная граница.
Зависимости: stdlib (pathlib, dataclasses, typing)
Основные сущности: SemanticModule (frozen), SemanticLibraryError, load_module, list_modules

Формат модуля — _schema.md (закрытая схема). Ключевое: utf-8-sig (BOM-уроки
серии), контент секции verbatim (хвостовые пустые строки срезаются, ВЕДУЩИЕ
пустые строки сохраняются — они несут ведущий '\n' контраст-блока), отказ
громкий (L4): fallback на inline запрещён.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

_LIBRARY_DIR = Path(__file__).resolve().parent
_MODULE_DECL_PREFIX = "# semantic-module: "
_SECTION_PREFIX = "## "
# Закрытый реестр секций (схема v1, Э2-вердикт). Расширение = правка схемы +
# лоадера + вердикт Мастера — неизвестная секция громко падает, не игнорируется.
# enum-tail опционален: модуль без него — add-only (не заменяет перечисление).
_REQUIRED_SECTIONS = ("contrast-block",)
_OPTIONAL_SECTIONS = ("enum-tail", "notes")
_ALLOWED_SECTIONS = frozenset(_REQUIRED_SECTIONS + _OPTIONAL_SECTIONS)


class SemanticLibraryError(Exception):
    """Громкий отказ библиотеки (L4): отсутствие/порча модуля — не fallback."""


@dataclass(frozen=True)
class SemanticModule:
    """Иммутабельный модуль семантического знания (детерминированный парс)."""

    name: str
    enum_tail: Optional[str]  # None = add-only модуль (перечисление не заменяет)
    contrast_block: str
    meta: Dict[str, str]


def _parse_module(text: str, source: Path) -> SemanticModule:
    lines = text.splitlines()
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx >= len(lines) or not lines[idx].startswith(_MODULE_DECL_PREFIX):
        raise SemanticLibraryError(
            f"{source}: первая значащая строка обязана быть '{_MODULE_DECL_PREFIX}<name>'"
        )
    declared_name = lines[idx][len(_MODULE_DECL_PREFIX):].strip()
    if not declared_name:
        raise SemanticLibraryError(f"{source}: пустое имя модуля в декларации")
    idx += 1

    meta: Dict[str, str] = {}
    sections: Dict[str, str] = {}
    current: Optional[str] = None
    buf: List[str] = []

    def _flush() -> None:
        if current is None:
            return
        while buf and buf[-1] == "":
            buf.pop()
        sections[current] = "\n".join(buf)

    for line in lines[idx:]:
        if line.startswith(_SECTION_PREFIX):
            _flush()
            current = line[len(_SECTION_PREFIX):].strip()
            if current in sections:
                raise SemanticLibraryError(f"{source}: дубликат секции '{current}'")
            buf = []
        elif current is not None:
            buf.append(line)
        elif line.startswith("> "):
            key, _, value = line[2:].partition(":")
            meta[key.strip()] = value.strip()
        elif line.strip():
            raise SemanticLibraryError(
                f"{source}: строка вне секций и метаданных: {line[:60]!r}"
            )
    _flush()

    missing = [s for s in _REQUIRED_SECTIONS if s not in sections]
    if missing:
        raise SemanticLibraryError(f"{source}: отсутствуют обязательные секции {missing}")
    unknown = set(sections) - _ALLOWED_SECTIONS
    if unknown:
        raise SemanticLibraryError(
            f"{source}: неизвестные секции {sorted(unknown)} (схема закрыта)"
        )
    return SemanticModule(
        name=declared_name,
        enum_tail=sections.get("enum-tail"),
        contrast_block=sections["contrast-block"],
        meta=meta,
    )


def load_module(name: str, base_path: Optional[Union[str, Path]] = None) -> SemanticModule:
    """Детерминированная загрузка модуля. Отказ — громкий (L4), без fallback."""
    base = Path(base_path) if base_path is not None else _LIBRARY_DIR
    path = base / f"{name}.md"
    if not path.is_file():
        raise SemanticLibraryError(f"модуль не найден: {path}")
    module = _parse_module(path.read_text(encoding="utf-8-sig"), path)
    if module.name != name:
        raise SemanticLibraryError(
            f"{path}: декларация '{module.name}' != имени файла '{name}'"
        )
    return module


def load_modules(names_csv: str) -> Tuple[SemanticModule, ...]:
    """Детерминированная загрузка среза по CSV имён (порядок = порядок блоков).

    Отказ — громкий: неизвестное имя, дубликат (SemanticLibraryError).
    Конфликт двух enum-tail-модулей в одном срезе ловит вызывающий (сборка).
    """
    names = [n.strip() for n in names_csv.split(",") if n.strip()]
    if not names:
        raise SemanticLibraryError("пустой срез модулей")
    seen = set()
    for n in names:
        if n in seen:
            raise SemanticLibraryError(f"дубликат модуля в срезе: {n}")
        seen.add(n)
    return tuple(load_module(n) for n in names)


def list_modules() -> Tuple[str, ...]:
    """Детерминированный список модулей (sorted); '_'-файлы (schema) скрыты."""
    return tuple(sorted(p.stem for p in _LIBRARY_DIR.glob("*.md") if not p.name.startswith("_")))

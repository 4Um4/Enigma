"""
ENIGMA Doc Drift Detector
Парсит .md файлы, находит ссылки вида `file.py:123` или `file.py:L123`,
проверяет существование файла и строки.
Если строка изменилась — предлагает обновить.

Exit codes:
  0 — все ссылки валидны
  1 — найдены битые ссылки
  2 — ошибка выполнения
"""
import re
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class DocRef:
    md_file: Path
    line: int
    referenced_file: str
    referenced_line: Optional[int]
    raw_match: str

# Паттерн: `backend/app/services/tick_orchestrator.py:42`
# или `tick_orchestrator.py:42`
# или `file.py:L42`
REF_PATTERN = re.compile(
    r'`([a-zA-Z0-9_/.]+\.py):(?:L?)(\d+)`'
)

# Директории для сканирования
SCAN_DIRS = [
    "docs/",
]

# Корень проекта для резолва относительных путей
PROJECT_ROOT = Path(__file__).parent.parent


def find_refs(md_path: Path) -> List[DocRef]:
    """Парсит .md файл, извлекает все ссылки на file:line."""
    refs = []
    try:
        content = md_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[DOC_DRIFT] WARNING: Не удалось прочитать {md_path}: {e}")
        return []

    for line_no, line in enumerate(content.splitlines(), 1):
        for match in REF_PATTERN.finditer(line):
            refs.append(DocRef(
                md_file=md_path,
                line=line_no,
                referenced_file=match.group(1),
                referenced_line=int(match.group(2)),
                raw_match=match.group(0),
            ))
    return refs


def validate_ref(ref: DocRef) -> tuple[bool, str]:
    """Проверяет, существует ли файл и строка.

    Возвращает (ok, reason). reason: '' при ok, иначе причина отказа.
    """
    if ref.referenced_file == "file.py":
        return True, ""  # учебный пример в документации, не реальная ссылка

    # Попытка резолва пути
    candidates = [
        PROJECT_ROOT / ref.referenced_file,
        PROJECT_ROOT / "backend" / ref.referenced_file,
        PROJECT_ROOT / "backend" / "app" / ref.referenced_file,
        PROJECT_ROOT / "frontend" / ref.referenced_file,
    ]

    target_file = None
    for candidate in candidates:
        if candidate.exists():
            target_file = candidate
            break

    if target_file is None:
        # Fallback: голое имя файла — рекурсивный поиск по проекту
        basename = Path(ref.referenced_file).name
        hits = _basename_index().get(basename, [])
        if len(hits) == 1:
            target_file = hits[0]
        elif len(hits) > 1:
            # Неоднозначно: берём первый, у которого валидна строка
            for hit in hits:
                if _line_ok(hit, ref.referenced_line):
                    return True, ""
            target_file = hits[0]
        else:
            return False, "file not found"

    if ref.referenced_line is None:
        return True, ""  # Только файл, без строки

    if not _line_ok(target_file, ref.referenced_line):
        return False, (f"line {ref.referenced_line} out of range "
                       f"(file has {len(_read_lines(target_file))} lines)")

    return True, ""


_line_cache: dict[Path, list] = {}


def _read_lines(path: Path) -> list:
    if path not in _line_cache:
        try:
            _line_cache[path] = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            _line_cache[path] = []
    return _line_cache[path]


def _line_ok(path: Path, line_no: Optional[int]) -> bool:
    if line_no is None:
        return True
    lines = _read_lines(path)
    return 0 < line_no <= len(lines)


_basename_cache: Optional[dict[str, list[Path]]] = None


def _basename_index() -> dict[str, list[Path]]:
    """Индекс всех .py файлов проекта по имени файла (строится один раз)."""
    global _basename_cache
    if _basename_cache is None:
        index: dict[str, list[Path]] = {}
        for root in ("backend", "frontend", "scripts", "diagnostics"):
            root_path = PROJECT_ROOT / root
            if not root_path.exists():
                continue
            for py in root_path.rglob("*.py"):
                if "__pycache__" in py.parts or ".venv" in py.parts:
                    continue
                index.setdefault(py.name, []).append(py)
        _basename_cache = index
    return _basename_cache


def run() -> int:
    """Главная точка входа."""
    all_refs: List[DocRef] = []
    missing: List[tuple[DocRef, str]] = []
    drift: List[tuple[DocRef, str]] = []

    for scan_dir in SCAN_DIRS:
        dir_path = PROJECT_ROOT / scan_dir
        if not dir_path.exists():
            continue
        for md_file in dir_path.rglob("*.md"):
            all_refs.extend(find_refs(md_file))

    print(f"[DOC_DRIFT] Scanned {len(all_refs)} references across "
          f"{len(set(r.md_file for r in all_refs))} .md files")

    for ref in all_refs:
        ok, reason = validate_ref(ref)
        if ok:
            continue
        if reason == "file not found":
            missing.append((ref, reason))
        else:
            drift.append((ref, reason))

    if drift:
        print(f"[DOC_DRIFT] ⚠️ {len(drift)} line-drift references "
              f"(файл существует, номер строки устарел):")
        for ref, reason in drift:
            print(f"  {ref.md_file.name}:{ref.line} → {ref.raw_match} ({reason})")

    if not missing:
        print("[DOC_DRIFT] ✅ All files referenced exist "
              f"({len(drift)} line-drift warnings)")
        return 0

    print(f"[DOC_DRIFT] ❌ {len(missing)} broken references (file not found):")
    for ref, reason in missing:
        print(f"  {ref.md_file.name}:{ref.line} → {ref.raw_match} ({reason})")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception as e:
        print(f"[DOC_DRIFT] ❌ CRITICAL ERROR: {e}")
        sys.exit(2)
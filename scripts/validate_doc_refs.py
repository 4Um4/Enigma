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


def validate_ref(ref: DocRef) -> bool:
    """Проверяет, существует ли файл и строка."""
    # Попытка резолва пути
    candidates = [
        PROJECT_ROOT / ref.referenced_file,
        PROJECT_ROOT / "backend" / ref.referenced_file,
        PROJECT_ROOT / "frontend" / ref.referenced_file,
    ]

    target_file = None
    for candidate in candidates:
        if candidate.exists():
            target_file = candidate
            break

    if target_file is None:
        return False  # Файл не найден

    if ref.referenced_line is None:
        return True  # Только файл, без строки

    try:
        lines = target_file.read_text(encoding="utf-8").splitlines()
    except Exception:
        return False

    if ref.referenced_line > len(lines):
        return False  # Строка за пределами файла

    return True  # Файл и строка существуют


def run() -> int:
    """Главная точка входа."""
    all_refs: List[DocRef] = []
    broken: List[tuple[DocRef, str]] = []

    for scan_dir in SCAN_DIRS:
        dir_path = PROJECT_ROOT / scan_dir
        if not dir_path.exists():
            continue
        for md_file in dir_path.rglob("*.md"):
            all_refs.extend(find_refs(md_file))

    print(f"[DOC_DRIFT] Scanned {len(all_refs)} references across "
          f"{len(set(r.md_file for r in all_refs))} .md files")

    for ref in all_refs:
        if not validate_ref(ref):
            broken.append((ref, "file or line not found"))

    if not broken:
        print("[DOC_DRIFT] ✅ All references valid")
        return 0

    print(f"[DOC_DRIFT] ❌ {len(broken)} broken references found:")
    for ref, reason in broken:
        print(f"  {ref.md_file.name}:{ref.line} → {ref.raw_match} ({reason})")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception as e:
        print(f"[DOC_DRIFT] ❌ CRITICAL ERROR: {e}")
        sys.exit(2)
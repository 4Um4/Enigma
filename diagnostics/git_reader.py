"""
path: diagnostics/git_reader.py
Назначение: Читает git log (последние 5 коммитов) и MUTATIONS.md (последние 3 записи)
            для заполнения секции #1 LAST_SESSION.md.
            При отсутствии git или MUTATIONS — возвращает заглушки, не падает.
Зависимости: subprocess, pathlib (stdlib)
Основные сущности: GitReader, GitInfo
"""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class GitInfo:
    """Данные из git и MUTATIONS для секции #1."""
    recent_commits: List[str] = field(default_factory=list)   # строки "hash message"
    mutations_last: List[str] = field(default_factory=list)   # последние 3 записи MUTATIONS.md
    current_architect_action: str = ""                         # строка "Сейчас делает:"
    todo_files: List[str] = field(default_factory=list)        # файлы с TODO/FIXME


class GitReader:
    """
    Читает метаданные проекта из git и документации.
    Все операции изолированы в try/except — сбой не роняет CDS.
    """

    def __init__(self, project_root: Optional[str] = None) -> None:
        if project_root is None:
            self._root = Path(__file__).parent.parent  # корень Enigma/
        else:
            self._root = Path(project_root)
        self._mutations_path = self._root / "docs" / "Tasks" / "MUTATIONS.md"

    def read(self) -> GitInfo:
        info = GitInfo()
        info.recent_commits = self._read_git_log()
        info.mutations_last = self._read_mutations()
        info.current_architect_action = self._extract_current_action(info.mutations_last)
        info.todo_files = self._scan_todos()
        return info

    # ------------------------------------------------------------------

    def _read_git_log(self) -> List[str]:
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-5"],
                cwd=str(self._root),
                capture_output=True,
                text=True,
                timeout=5,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0:
                return [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except Exception:
            pass
        return ["(git log недоступен)"]

    def _read_mutations(self) -> List[str]:
        """Читает последние 3 непустые строки из MUTATIONS.md."""
        try:
            if not self._mutations_path.exists():
                return ["(MUTATIONS.md не найден)"]
            lines = self._mutations_path.read_text(encoding="utf-8", errors="replace").splitlines()
            # Берём непустые строки снизу
            non_empty = [l.strip() for l in lines if l.strip()]
            return non_empty[-3:] if len(non_empty) >= 3 else non_empty
        except Exception as exc:
            return [f"(ошибка чтения MUTATIONS.md: {exc})"]

    def _extract_current_action(self, mutations: List[str]) -> str:
        """Последняя строка MUTATIONS = самое свежее действие архитектора."""
        if mutations and mutations[-1] != "(MUTATIONS.md не найден)":
            return mutations[-1]
        return "(не определено — обнови MUTATIONS.md)"

    def _scan_todos(self) -> List[str]:
        """
        Ищет файлы с TODO/FIXME/HACK в backend/ и frontend/.
        Возвращает до 10 уникальных путей.
        """
        try:
            result = subprocess.run(
                ["grep", "-rl", "--include=*.py",
                 "-e", "TODO", "-e", "FIXME", "-e", "HACK",
                 "backend/", "frontend/"],
                cwd=str(self._root),
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0:
                files = [l.strip() for l in result.stdout.splitlines() if l.strip()]
                return files[:10]
        except Exception:
            # grep может не быть на Windows — используем PowerShell fallback
            pass

        # Windows fallback через PowerShell
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-ChildItem -Path 'backend/','frontend/' -Filter '*.py' -Recurse "
                 "| Select-String -Pattern 'TODO|FIXME|HACK' "
                 "| Select-Object -ExpandProperty Path -Unique"],
                cwd=str(self._root),
                capture_output=True,
                text=True,
                timeout=15,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0:
                files = [l.strip() for l in result.stdout.splitlines() if l.strip()]
                return files[:10] or ["(TODO не найдены)"]
        except Exception as exc:
            return [f"(TODO-скан ошибка: {exc})"]
        return ["(TODO-скан: нет результатов)"]

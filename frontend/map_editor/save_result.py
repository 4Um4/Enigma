"""
P3-01 (контракт D.6, вариант B): единый результат операции сохранения.

Назначение:

`__bool__` возвращает `ok`, поэтому существующие проверки `if dm.save(...)`
сохраняют прежнюю семантику и не требуют одновременной миграции потребителей.
Отдельный модуль — из-за цикла импортов data_manager ↔ schema_validator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SaveResult:
    """Результат сохранения: одиночного (ok/errors) или пакетного (count/failed)."""

    ok: bool = False
    errors: List[str] = field(default_factory=list)
    count: int = 0
    failed: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok

    @classmethod
    def success(cls, count: int = 1) -> "SaveResult":
        return cls(ok=True, count=count)

    @classmethod
    def failure(
        cls,
        errors: List[str],
        failed: Optional[List[str]] = None,
        count: int = 0,
    ) -> "SaveResult":
        return cls(ok=False, errors=list(errors), count=count, failed=list(failed or []))

    def reason_text(self, limit: int = 3) -> str:
        """Первые `limit` причин одной строкой; остаток — счётчиком."""
        if not self.errors:
            return "причина не указана"
        head = "; ".join(self.errors[:limit])
        rest = len(self.errors) - limit
        if rest > 0:
            head += f" (+ещё {rest})"
        return head

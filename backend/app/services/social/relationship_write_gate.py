"""
path: /project/backend/app/services/social/relationship_write_gate.py
Назначение: RelationshipWriteGate — ЕДИНСТВЕННЫЙ write-путь для пяти скаляров
    отношений (ADR-O-371 / M1b.2; вердикт Мастера: D2-инвариант
    «ALL RELATIONSHIP STATE WRITES → ONE GATE → STORE»).
    АРХИТЕКТУРНЫЙ ПРИНЦИП (ратифицирован дословно):
      Writer не знает, где живёт состояние. Writer знает только Gate.
      Gate знает текущий backend. Backend меняется на cutover — writers
      повторно не мигрируют.
    Гейт — routing/write-policy слой: НЕ третье хранилище и НЕ второй источник
    истины — состояния не хранит, только валидирует вход и делегирует backend'у.
    Backend-ы: M1b.2 — legacy RelationshipStore.update() (поведение идентично
    текущему; паритет доказан сеткой D3); M1b.4 (cutover) —
    RelationshipStateStore v2; переключение = смена внутренней строки гейта,
    подписчики не меняются.
    ВХОДНОЙ КОНТРАКТ (ужесточение Мастера): whitelist ровно пяти скаляров
    {trust, fear, debt, respect, attraction}; посторонние ключи / NaN /
    нечисловые значения → ContractValidationError — через гейт не протекают
    новые сущности RE. cause — provenance/наблюдаемость (L4-лог), НЕ часть
    состояния.
    LEGACY-СЕМАНТИКА backend (контракт D3, переносится ДОСЛОВНО): headroom-
    сатурация Δ×(100−|v|)/100, clamp −100..100; round НЕ в write (read-
    контракт get_pair). Эквивалентность SAME INPUT + SAME PRIOR + SAME Δ →
    LEGACY RESULT == GATE RESULT доказывается паритет-тестом до переноса
    первого writer-сайта.
Зависимости: app.services.memory.relationship_store (legacy backend M1b.2),
    app.errors, typing. V2-backend (M1b.4) будет импортирован на cutover.
Основные сущности: RelationshipWriteGate, SCALAR_WHITELIST.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Final, FrozenSet, Optional

logger = logging.getLogger(__name__)

# Whitelist Мастера: ровно пять скаляров. Расширение = вердикт GPT + ADR
# (контракт ТЗ-RE-01 §5.2; новые RE-сущности через гейт не протекают).
SCALAR_WHITELIST: Final[FrozenSet[str]] = frozenset(
    {"trust", "fear", "debt", "respect", "attraction"}
)


class RelationshipWriteGate:
    """Единый write-гейт пяти скаляров. Routing-слой без собственного состояния.

    Прямой вызов backend.update() / v2-apply мимо гейта из writer-сайтов
    после M1b.2.7 = ArchitecturalViolation (доказывается греп-инвариантом).
    """

    def __init__(self, relationship_store: Any) -> None:
        """relationship_store — legacy backend (M1b.2). На cutover (M1b.4)
        сюда инжектируется v2-адаптер с тем же интерфейсом update()."""
        self._backend = relationship_store

    @property
    def backend(self) -> Any:
        """Read-only доступ к backend'у (для тестов паритета и диагностики)."""
        return self._backend

    def apply(
        self,
        campaign_id: str,
        source: str,
        target: str,
        deltas: Dict[str, float],
        cause: Optional[str] = None,
    ) -> None:
        """Применить дельты пяти скаляров source→target через текущий backend.

        Политика: (1) валидация входа ДО делегирования (whitelist/NaN/тип/
        пустые id); (2) пустой deltas после фильтрации — no-op с наблюдаемым
        логом (legacy update() с пустым delta тоже no-op — паритет);
        (3) делегирование backend'у — сатурация/clamp выполняет backend
        (M1b.2: legacy; M1b.4: v2-адаптер обязан воспроизвести дословно —
        гарантируется паритет-тестом, который не меняется на cutover);
        (4) cause — только лог (L4), не состояние.

        Caller-guard НЕ здесь: гейт — публичный API writers; защита от
        двойного писателя — M1b.2.7 греп-инвариант (никто, кроме гейта,
        не вызывает backend.update).
        """
        if not campaign_id or not source or not target:
            raise ValueError(
                f"WriteGate.apply: campaign_id/source/target обязательны "
                f"({campaign_id!r}, {source!r}, {target!r})"
            )
        if not isinstance(deltas, dict):
            raise ValueError(f"WriteGate.apply: deltas — dict, получен {type(deltas).__name__}")
        clean: Dict[str, float] = {}
        for key, value in deltas.items():
            if key not in SCALAR_WHITELIST:
                raise ValueError(
                    f"WriteGate.apply: ключ '{key}' вне whitelist пяти скаляров "
                    f"{sorted(SCALAR_WHITELIST)} — новые RE-сущности через гейт "
                    f"не протекают (расширение = вердикт GPT + ADR)"
                )
            try:
                d = float(value)
            except (TypeError, ValueError) as e:
                raise ValueError(f"WriteGate.apply: deltas['{key}'] не число: {value!r}") from e
            if d != d:  # NaN
                raise ValueError(f"WriteGate.apply: deltas['{key}'] NaN запрещён")
            if d != 0.0:  # нулевые дельты — no-op, не гоняем в backend (паритет legacy)
                clean[key] = d
        if not clean:
            logger.debug("[WRITE_GATE] no-op: пустые/нулевые дельты %s→%s", source, target)
            return
        if cause:
            logger.debug("[WRITE_GATE] %s→%s %s cause=%s", source, target, clean, cause)
        self._backend.update(
            campaign_id=campaign_id,
            source=source,
            target=target,
            delta=clean,
        )

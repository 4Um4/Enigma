# -*- coding: utf-8 -*-
"""
path: backend/app/services/drf_bus.py
Назначение: Изоляция Dynamic Recompression Field Bus (DRFBus) и Scoped Causal Ledger (DRFExecutionContext) из God-object TickOrchestrator. Обеспечивает аддитивный каузальный скоринг (ADR-135).
Зависимости: typing, logging
Основные сущности: DRFBus, DRFExecutionContext, _DRF_PRESSURE_WEIGHTS

"""

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DRFBus:
    """Dynamic Recompression Field Bus: единая шина причинных напряжений тика.
    Системы пишут сюда претензии (emit), наблюдатель читает и схлопывает (drain).
    """

    def __init__(self):
        self.stream: list[dict] = []

    def emit(self, claim: dict):
        self.stream.append(claim)

    def drain(self) -> list[dict]:
        data = self.stream
        self.stream = []
        return data


@dataclass
class DRFExecutionContext:
    """Scoped causal ledger: привязка претензий к tick+npc frame.
    Pipeline получает drf_ctx, а не голый drf_bus.
    Claim автоматически наследует npc_id и tick_id из контекста.
    """

    tick_id: int
    bus: Any  # DRFBus — разделяемая шина тика
    npc_id: Optional[str] = None  # None = frame-level (pre-loop)

    def for_npc(self, npc_id: str) -> "DRFExecutionContext":
        """Создаёт scoped контекст для конкретного NPC (тот же bus, тот же tick)."""
        return DRFExecutionContext(tick_id=self.tick_id, npc_id=npc_id, bus=self.bus)

    def emit(self, claim: dict):
        """Испускает претензию с авто-привязкой npc_id и tick_id."""
        _enriched = {**claim}
        if self.npc_id and "target_npc" not in _enriched:
            _enriched["target_npc"] = self.npc_id
        _enriched["tick_id"] = self.tick_id
        if self.npc_id:
            _enriched["npc_id"] = self.npc_id
        self.bus.emit(_enriched)
        logger.info(
            f"[DRF_EMIT_BUS] bus_id={id(self.bus)} stream_size={len(self.bus.stream)} npc={self.npc_id} tick={self.tick_id}"
        )

    def drain(self) -> list[dict]:
        """Схлопывает шину — делегирует bus. Вызывать только на frame-level."""
        return self.bus.drain()


# ── DRF Causal Scoring Weights (ДОЛГ 4.2) ──────────────────────────
# Давление определяет допустимость намерений, не только приоритет.
# Аддитивный скоринг: final = base + Σ(energy × weight × alignment)
_DRF_PRESSURE_WEIGHTS = {
    "SURVIVAL": 0.15,  # Критическое (flee) — радикальный бонус
    "SOCIAL": 0.10,  # Социальное (approach) — средний бонус
    "ROUTINE": 0.02,  # Рутина (schedule) — минимальный
}
# V8-PSY-23 FIX: Мёртвые константы удалены.
# Канонические значения (_DRF_ALIGNED = 1.2, _DRF_MISALIGNED = 0.8) определены локально в tick_orchestrator.py::_apply_drf_scoring_overlay

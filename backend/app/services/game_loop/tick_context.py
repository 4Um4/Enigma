"""Контекст одного тика пайплайна.

Три контракта разделяют поток данных:
- TickInput   — readonly, что пришло извне
- TickBuffer  — mutable, что накапливается между фазами
- TickOutput  — readonly, итоговый результат до DM-агента

Закон: фазы принимают TickInput + TickBuffer, возвращают TickBuffer.
Единственная точка мутации мира — TickOrchestrator.finalize_and_commit (читает TickBuffer).

path: backend/app/services/game_loop/tick_context.py
Назначение: Типы контекста одного тика — Input (readonly), Buffer (mutable), Output (result)
Зависимости: dataclasses, typing
Основные сущности: TickInput, TickBuffer, TickOutput

TODO: при экстракции фаз из монолитного _run_pipeline — наполнить TickOutput результатами, которые сейчас мутируются в Buffer, и постепенно перенести их в Output.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TickInput:
    """Входные данные тика — только readonly.

    Формируется один раз в начале _run_pipeline, не меняется.
    """

    campaign_id: str
    world_id: str
    location: str
    actions: list
    is_session_start: bool = False
    campaign_state: Any = None


@dataclass
class TickBuffer:
    """Мутабельный накопитель между фазами.

    Каждая фаза читает из TickInput + TickBuffer,
    пишет результаты в TickBuffer.
    """

    # ── NPC state ──
    all_npcs_raw: list[dict] = field(default_factory=list)
    dirty_npcs: set[int] = field(default_factory=set)

    # ── Dirty flags для единого коммита ──
    # Stage 0 Task 0.10: wt_dirty упразднён. Параллельный WorldTick-путь закрыт.
    prop_dirty: bool = False

    # ── Event context (CharacterFilter может занулить) ──
    hub_event: Any = None

    # ── Salience: максимальный стресс среди NPC для фильтрации объектов ──
    max_npc_stress: float = 0.0

    # ── NPC контексты для вербализации (накапливаются в NPC loop) ──
    npc_contexts: list[dict] = field(default_factory=list)

    # ── Социальные дельты (накапливаются в SocialPropagation) ──
    social_results: list = field(default_factory=list)

    # ── ENIGMA SELF-HEALING: For probes (Level 1) ──
    mvp_controller: Any = None


@dataclass(frozen=True)
class TickOutput:
    """Итоговый результат пайплайна до DM-агента.

    Формируется в phase_7_outcome, передаётся в DM-промпт.
    Пока пустой — будет наполнен при экстракции фаз.
    """

    pass


# Обратная совместимость: _TickContext = TickBuffer
_TickContext = TickBuffer

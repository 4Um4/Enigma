# -*- coding: utf-8 -*-
# C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\state\context_builder.py
"""
context_builder.py — единственное место сборки контекста для DM и NPC агентов.

Принцип: все данные о мире собираются здесь один раз.
DM и NPC получают одинаковый срез реальности — рассинхронизация невозможна.

Вызывается из orchestrator после всех Python-движков, до агентов.
"""

from typing import Optional
from app.services.simulation.world_state import get_world_state


def build_context(
    campaign_id:          str,
    world_id:             str,
    location:             str,
    player:               str,
    scene_state:          dict,
    python_engines:       dict,
    recent_memory:        list | None  = None,
    reaction_order:       list | None  = None,
    forced_first_speaker: Optional[str] = None,
) -> dict:
    """
    Собирает единый context dict для DM и NPC агентов.

    Возвращает dict который кладётся в shared_context и передаётся
    в dm_agent._build_prompt() и npc_agent._build_phase3a_prompt().
    """
    if recent_memory is None:
        recent_memory = []
    if reaction_order is None:
        reaction_order = []

    # npc_contexts живут в python_engines — выносим на верхний уровень
    # чтобы DM и NPC агенты могли обращаться напрямую без python_engines["npc_contexts"]
    npc_contexts = python_engines.get("npc_contexts", [])

    # recent_session — последние 2 хода для NPC continuity
    # Уже посчитан в _run_python_engines → просто пробрасываем
    recent_session = python_engines.get("recent_session", [])

    return {
        # ── Идентификаторы ──────────────────────────────────────────
        "campaign_id":  campaign_id,
        "world_id":     world_id,
        "location":     location,
        "player_state": {player: {}},

        # ── Состояние мира (единственный источник правды) ────────────
        "scene_state":        scene_state,
        "world_context_slice": get_world_state().build_context_slice(scene_state),

        # ── Результаты Python-движков ─────────────────────────────────
        "python_engines":     python_engines,
        "npc_contexts":       npc_contexts,

        # ── Память и сессия ───────────────────────────────────────────
        "recent_memory":  recent_memory,
        "recent_session": recent_session,

        # ── Реакции NPC (S.4.2) ───────────────────────────────────────
        "reaction_order":       reaction_order,
        "forced_first_speaker": forced_first_speaker,

        # ── Пустые слоты (заполняются движками если нужны) ───────────
        "threat":     {},
        "perception": {},
        "psyche":     {},
        "life":       {},
        "karma":      {},
    }


def patch_scene_state(context: dict, scene_state: dict) -> None:
    """
    Обновляет scene_state внутри уже собранного контекста.
    Вызывается после apply_changes() если SceneState мутировал.
    In-place — ссылка та же, агенты увидят изменение автоматически.
    """
    context["scene_state"] = scene_state


def get_npc_context(context: dict, npc_id: str) -> Optional[dict]:
    """
    Возвращает контекст конкретного NPC по его id.
    Используется npc_agent вместо поиска по списку вручную.
    """
    for ctx in context.get("npc_contexts", []):
        if ctx.get("npc_id") == npc_id:
            return ctx
    return None

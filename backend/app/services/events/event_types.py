from __future__ import annotations

# backend/app/services/events/event_types.py
#
# Phase 3B.1 — Event Foundation
#
# EventType описывает что произошло в мире (не намерение игрока).
# PLAYER_ATTACKED — не PLAYER_CHOSE_ATTACK.
#
# Совместимость с существующим scene_change.py:
#   Старый SceneChange (ChangeType) — атомарные изменения полей объектов.
#   Новый EventDTO (EventType.value) — событие в мире, видимое NPC и системам.
#   Они дополняют друг друга:
#     sandbox_handler создаёт list[SceneChange] (как раньше)
#     action/processor.py оборачивает их в EventDTO и публикует в EventBus
#   Старый код продолжает работать без изменений.
from enum import Enum


class EventType(str, Enum):
    DREAM = "dream"
    NIGHTMARE = "nightmare"
    SLEEPWALK = "sleepwalk"
    PROPHECY_VISION = "prophecy_vision"
    # ── Эпистемический слой ──────────────────
    COMMUNICATION_CLAIM = "communication_claim"  # S188: Передача Proposition (ClaimEvent)

    # ── Физический мир ────────────────────────────────────────────────────
    OBJECT_MOVED = "object_moved"
    OBJECT_DESTROYED = "object_destroyed"
    OBJECT_CHANGED = "object_changed"
    LIGHT_CHANGED = "light_changed"
    SOUND_EMITTED = "sound_emitted"
    SMELL_EMITTED = "smell_emitted"

    # ── Игрок ─────────────────────────────────────────────────────────────
    PLAYER_MOVED = "player_moved"
    PLAYER_ATTACKED = (
        "PLAYER_ATTACKED"  # сохранено для совместимости со старыми строками
    )
    PLAYER_SPOKE = "PLAYER_SPOKE"  # сохранено для совместимости со старыми строками
    PLAYER_USED_ITEM = "player_used_item"
    PLAYER_CAST_SPELL = "player_cast_spell"

    # ── NPC ───────────────────────────────────────────────────────────────
    NPC_STATE_CHANGED = "npc_state_changed"
    NPC_MOVED = "npc_moved"
    NPC_SPOKE = "npc_spoke"

    # ── Мир ───────────────────────────────────────────────────────────────
    TIME_PASSED = "time_passed"
    TICK_COMPLETED = "tick_completed"  # N2 FIX: Событие завершения тика для подписки трекеров (M-03)
    # EMRL E2.0-b: трасса причинного изменения состояния — потребляется
    # Chronicaler'ом (cross-cutting); observation-only (Закон XI)
    EXPERIENCE_DELTA_COMMITTED = "experience_delta_committed"
    # BC-1/ADR-O-381: трасса сформированного вывода — observation-only
    # (Закон XI); эмиттер conclusion_gate.apply. Семантически ≠ delta:
    # EXPERIENCE_DELTA_COMMITTED (вход опыта) ≠ CONCLUSION_FORMED (вывод).
    CONCLUSION_FORMED = "conclusion_formed"
    WEATHER_CHANGED = "weather_changed"
    FACTION_EVENT = "faction_event"
    WORLD_TICK = "world_tick"  # проактивный тик мира (Фаза 3.4)

    # ── NPC-NPC взаимодействия (Фаза 3.4) ───────────────────────────────
    NPC_PROXIMITY_CLOSE = "npc_proximity_close"  # NPC подошёл к другому NPC
    NPC_PROXIMITY_LEAVE = "npc_proximity_leave"  # NPC отошёл от другого NPC
    NPC_INTERACTS_NPC = "npc_interacts_npc"  # NPC инициирует контакт с NPC

    # ── Легаси-события (из EventContext и старых JSON) ────────────────────
    # Унифицированы здесь для устранения разрывов (R1.6)
    THEFT = "theft"
    COMBAT = "combat"
    HELP = "help"
    IDLE = "idle"
    ACTOR_ATTACKS = "actor_attacks"  # ADR-O-112: Универсальная атака (NPC→Player, NPC→NPC)
    INTIMIDATION = "intimidation"
    DIALOGUE = "dialogue"
    BETRAYAL = "betrayal"
    SAVED_LIFE = "saved_life"
    MOVEMENT = "movement"
    PLAYER_ASKS_WHY = "player_asks_why"
    PLAYER_INTERACTS = "player_interacts"
    PLAYER_ATTACKS = "player_attacks"
    
    # ── S4: Semantic Pipeline — социальные/экономические интенты ──────────
    OFFER_JOB = "offer_job"
    REQUEST_SERVICE = "request_service"
    SPREAD_RUMOR = "spread_rumor"
    CALL_FOR_HELP = "call_for_help"
    CHANGE_ROLE = "change_role"
    WARN = "warn"
    TRADE = "trade"
    REPORT = "report"
    # ── Траектория (Внешний анализ для DM/Мира) ─────────────────────────
    FATE_EVENT = "fate_event"  # Классификация жизненного пути NPC (Rising/Stable/Declining/Collapsed)
    WILL_CONFLICT = "will_conflict"
    PLAYER_ATTACK = "player_attack"
    PLAYER_INSULTS = "player_insults"
    PLAYER_TALKS = "player_talks"
    PLAYER_THREATENS = "player_threatens"
    PLAYER_HELPERS = "player_helpers"
    PROXIMITY_CLOSE = "proximity_close"
    PROXIMITY_LEAVE = "proximity_leave"
    UNKNOWN = "unknown"

    # ── S201: Social Act Materialization ─────────────────────────────────
    SOCIAL_ACTION = "social_action"  # Канонический канал социальных событий

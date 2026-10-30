"""
path: /project/backend/tests/micro/test_intent_tick_guard.py
Назначение: W2 regression — intent_tick=0 guard в StateApplicator._apply_deltas.
    8 контрактов различения отсутствующего значения (None) и валидного нулевого tick.
    Баг: `int(deltas.intent_tick or 0)` маскировал default=0 как «не задано» и
    перезатирал валидный past formed_at при смене intent без intent_tick.
Зависимости: app.models.state_delta, app.services.npc.state_applicator
Основные сущности: тесты battery 1-8
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.models.npc_state import Intent
from app.models.state_delta import StateDeltas
from app.services.npc.state_applicator import StateApplicator


# ── Helpers ──────────────────────────────────────────────────────────────


def _applicator() -> StateApplicator:
    """StateApplicator с замоканным relationship_store (по образцу test_intent_roundtrip)."""
    _store = MagicMock()
    _store.get_pair.return_value = {"trust": 0.0, "fear": 0.0}
    _store.update.return_value = None
    return StateApplicator(relationship_store=_store)


def _empty_npc() -> list:
    """NPC dict без intent-блока (initial state)."""
    return [{"npc_id": "npc_test", "id": "npc_test", "psyche": {}, "social_stats": {}}]


def _npc_with_intent(
    intent: str = "flee",
    target: str = "player",
    formed_at: int = 99,
    duration: int = 5,
    progress: int = 3,
) -> list:
    """NPC dict с pre-set intent-блоком (для тестов preservation)."""
    return [{
        "npc_id": "npc_test",
        "id": "npc_test",
        "psyche": {},
        "social_stats": {},
        "intent": intent,
        "intent_target": target,
        "intent_formed_at": formed_at,
        "intent_duration": duration,
        "intent_progress_ticks": progress,
        "last_intent_change": formed_at,
    }]


def _apply(deltas: StateDeltas, dicts: list) -> None:
    """Применяет одну дельту через apply_batch."""
    _applicator().apply_batch([deltas], dicts, "test")


# ── Контракт 1: валидный intent_tick=0 ──────────────────────────────────


def test_1_valid_zero_tick_writes_zero():
    """intent_tick=0 — валидный тик 0, должен записаться как 0.

    До W2: int(0 or 0) = 0 — случайно корректно, но маскировало None.
    После W2: 0 проходит guard `is not None` → записывается как 0.
    """
    dicts = _empty_npc()
    _apply(
        StateDeltas(
            npc_id="npc_test",
            intent=Intent.FLEE,
            target="player",
            intent_tick=0,
            source="decision_hub",
        ),
        dicts,
    )
    assert dicts[0]["intent"] == "flee"
    assert dicts[0]["intent_formed_at"] == 0
    assert dicts[0]["last_intent_change"] == 0


# ── Контракт 2: валидный положительный tick ─────────────────────────────


def test_2_valid_positive_tick_writes_tick():
    """intent_tick=5 — валидный тик 5, должен записаться как 5."""
    dicts = _empty_npc()
    _apply(
        StateDeltas(
            npc_id="npc_test",
            intent=Intent.FLEE,
            target="player",
            intent_tick=5,
            source="decision_hub",
        ),
        dicts,
    )
    assert dicts[0]["intent_formed_at"] == 5
    assert dicts[0]["last_intent_change"] == 5


# ── Контракт 3: отсутствующий intent_tick (default None) ────────────────


def test_3_missing_intent_tick_preserves_formed_at():
    """intent_tick не задан (default None) — formed_at не трогать.

    Сцена: NPC на тике 99 имеет intent=FLEE, formed_at=99.
    DecisionHub возвращает дельту с новым intent=TALK, но фабрика
    не штампует intent_tick (default None). Прежний код перезатирал
    formed_at в 0 (false negative). W2: guard пропускает, formed_at=99.
    """
    dicts = _npc_with_intent(intent="flee", formed_at=99)
    _apply(
        StateDeltas(
            npc_id="npc_test",
            intent=Intent.TALK,
            target="player",
            source="decision_hub",
        ),
        dicts,
    )
    assert dicts[0]["intent"] == "talk"
    assert dicts[0]["intent_formed_at"] == 99  # preserved
    assert dicts[0]["last_intent_change"] == 99  # preserved


# ── Контракт 4: явный None ──────────────────────────────────────────────


def test_4_explicit_none_intent_tick_preserves_formed_at():
    """intent_tick=None — явно отсутствует, formed_at не трогать.

    Семантически идентичен контракт 3, но проверяет явную передачу None
    (не путать с default). Контракт: None = «не трогать».
    """
    dicts = _npc_with_intent(intent="flee", formed_at=99)
    _apply(
        StateDeltas(
            npc_id="npc_test",
            intent=Intent.TALK,
            target="player",
            intent_tick=None,
            source="decision_hub",
        ),
        dicts,
    )
    assert dicts[0]["intent"] == "talk"
    assert dicts[0]["intent_formed_at"] == 99
    assert dicts[0]["last_intent_change"] == 99


# ── Контракт 5: повтор того же intent ───────────────────────────────────


def test_5_same_intent_does_not_touch_formed_at():
    """Тот же intent — инерция: duration+1, formed_at не трогать.

    _apply_deltas L771-776 (same-intent branch): только duration += 1
    и progress = min(progress+1, duration). formed_at не обновляется.
    intent_tick в дельте игнорируется (не доходит до guard).
    """
    dicts = _npc_with_intent(intent="flee", formed_at=99, duration=5, progress=3)
    _apply(
        StateDeltas(
            npc_id="npc_test",
            intent=Intent.FLEE,
            target="player",
            intent_tick=10,
            source="decision_hub",
        ),
        dicts,
    )
    assert dicts[0]["intent"] == "flee"
    assert dicts[0]["intent_formed_at"] == 99  # preserved (same-intent branch)
    assert dicts[0]["last_intent_change"] == 99
    assert dicts[0]["intent_duration"] == 6  # 5 + 1


# ── Контракт 6: смена intent с tick ─────────────────────────────────────


def test_6_intent_change_with_tick_updates_formed_at():
    """Смена intent + intent_tick=10 → formed_at=10, last_change=10."""
    dicts = _npc_with_intent(intent="flee", formed_at=99)
    _apply(
        StateDeltas(
            npc_id="npc_test",
            intent=Intent.TALK,
            target="player",
            intent_tick=10,
            source="decision_hub",
        ),
        dicts,
    )
    assert dicts[0]["intent"] == "talk"
    assert dicts[0]["intent_formed_at"] == 10
    assert dicts[0]["last_intent_change"] == 10


# ── Контракт 7: смена intent БЕЗ tick — duration/progress всё равно сбрасываются ──


def test_7_intent_change_without_tick_still_resets_duration():
    """Смена intent + intent_tick=None → formed_at preserved,
    но duration=0 и progress*0.3 (guard защищает только formed_at/last_change).

    W2 guard: `if deltas.intent_tick is not None:` защищает ТОЛЬКО
    intent_formed_at и last_intent_change. duration=0 и progress*0.3
    выполняются ВСЕГДА при смене intent (вне guard).
    """
    dicts = _npc_with_intent(intent="flee", formed_at=99, duration=5, progress=3)
    _apply(
        StateDeltas(
            npc_id="npc_test",
            intent=Intent.TALK,
            target="player",
            intent_tick=None,
            source="decision_hub",
        ),
        dicts,
    )
    assert dicts[0]["intent"] == "talk"
    assert dicts[0]["intent_formed_at"] == 99  # preserved (guard)
    assert dicts[0]["last_intent_change"] == 99  # preserved (guard)
    assert dicts[0]["intent_duration"] == 0  # reset (outside guard)
    assert dicts[0]["intent_progress_ticks"] == 0  # int(3 * 0.3) = 0


# ── Контракт 8: last_intent_change зеркалит intent_formed_at ────────────


def test_8_last_intent_change_mirrors_intent_formed_at():
    """При любом обновлении formed_at, last_intent_change = same value.

    W2 guard записывает оба поля из единой _w2_tick переменной.
    Параметризация по нескольким значениям (включая 0).
    """
    for tick_val in [0, 1, 42, 100]:
        dicts = _empty_npc()
        _apply(
            StateDeltas(
                npc_id="npc_test",
                intent=Intent.FLEE,
                target="player",
                intent_tick=tick_val,
                source="decision_hub",
            ),
            dicts,
        )
        assert dicts[0]["intent_formed_at"] == tick_val, f"tick={tick_val}"
        assert dicts[0]["last_intent_change"] == tick_val, f"tick={tick_val}"
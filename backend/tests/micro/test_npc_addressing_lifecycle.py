"""C3-A2-UI-2: NPC addressing indicator lifecycle.

Жизненный цикл индикаторов обращений NPC:
- Актуальное обращение сохраняется
- Изменение intent_formed_at → устаревшее обращение удаляется
- Отсутствие NPC в npc_coords не удаляет событие
- Несколько NPC обрабатываются независимо
- Несколько событий одного NPC не смешиваются (по event_id)
- Повторная доставка не создаёт дубликатов
- Переключение кампании сбрасывает индикаторы
- Неизвестная актуальность не приводит к удалению
- ACK и delivery queue остаются неизменными

Ограничение (Phase A, Q3): в системе нет достоверного сигнала удаления NPC
из мира. Отсутствие NPC в npc_coords может означать: NPC покинул сцену,
NPC вне восприятия, NPC за стеной, Temporal Delay, смена локации игроком.
Поэтому индикаторы НЕ удаляются по отсутствию NPC — только по смене intent
(через intent_formed_at в payload) или по переключению кампании.
"""
from __future__ import annotations

from pathlib import Path


# ── Source inspection helpers ──────────────────────────────────────────────

def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in [p.parent, p.parent.parent, p.parent.parent.parent, p.parent.parent.parent.parent]:
        if (parent / "backend" / "app").exists() and (parent / "frontend").exists():
            return parent
    return p.parent.parent.parent.parent


def _frontend_dir() -> Path:
    return _repo_root() / "frontend"


def _read_game_screen_source() -> str:
    p = _frontend_dir() / "game_screen.py"
    assert p.exists(), f"game_screen.py not found at {p}"
    return p.read_text(encoding="utf-8")


def _read_focus_renderer_source() -> str:
    p = _frontend_dir() / "focus_renderer.py"
    assert p.exists(), f"focus_renderer.py not found at {p}"
    return p.read_text(encoding="utf-8")


# ── Simulated lifecycle logic (mirrors game_screen.py parsing block) ───────
# Воспроизводит логику C3-A2-UI-2 для поведенческих тестов без запуска
# полного GameScreen (требует pygame, backend wiring и т.д.).

def apply_addressing_event(
    indicators: dict,
    addr: dict,
) -> tuple[dict, list[str]]:
    """Применить одно addressing-событие к индикаторам.

    Возвращает (new_indicators, removed_event_ids).
    ACK не симулируется — тестируется отдельно через source inspection.
    """
    indicators = dict(indicators)
    addr_npc = addr.get("npc_id", "")
    addr_eid = addr.get("event_id", "")
    addr_formed = addr.get("intent_formed_at")

    if not addr_npc or not addr_eid:
        return indicators, []

    removed: list[str] = []
    skip_add = False

    # Stale re-delivery guard
    if addr_formed is not None:
        has_newer = any(
            ex.get("npc_id") == addr_npc
            and ex.get("intent_formed_at") is not None
            and ex.get("intent_formed_at") > addr_formed
            for ex in indicators.values()
        )
        if has_newer:
            skip_add = True

    if not skip_add:
        # Intent change detection — remove older events for same NPC
        if addr_formed is not None:
            to_remove = [
                eid
                for eid, ex in indicators.items()
                if ex.get("npc_id") == addr_npc
                and eid != addr_eid
                and ex.get("intent_formed_at") is not None
                and ex.get("intent_formed_at") < addr_formed
            ]
            for old_eid in to_remove:
                del indicators[old_eid]
                removed.append(old_eid)
        # Dedup by event_id
        if addr_eid not in indicators:
            indicators[addr_eid] = addr

    return indicators, removed


# ── Behavioral tests ───────────────────────────────────────────────────────

def test_1_actual_addressing_preserved():
    """Актуальное обращение сохраняется (нет нового события для того же NPC)."""
    indicators = {
        "evt_A": {"npc_id": "npc_1", "event_id": "evt_A", "intent": "talk", "intent_formed_at": 5},
    }
    new_indicators, removed = apply_addressing_event(indicators, {
        "npc_id": "npc_2", "event_id": "evt_B", "intent": "warn", "intent_formed_at": 10,
    })
    assert "evt_A" in new_indicators, (
        "Existing addressing for npc_1 must be preserved when event for different NPC arrives"
    )
    assert removed == []


def test_2_intent_formed_at_change_removes_stale():
    """Изменение intent_formed_at делает обращение устаревшим + stale re-delivery не восстанавливает."""
    indicators = {
        "evt_A": {"npc_id": "npc_1", "event_id": "evt_A", "intent": "talk", "intent_formed_at": 5},
    }
    # Newer event arrives → older removed
    new_indicators, removed = apply_addressing_event(indicators, {
        "npc_id": "npc_1", "event_id": "evt_B", "intent": "warn", "intent_formed_at": 10,
    })
    assert "evt_A" not in new_indicators, "Stale event (older intent_formed_at) must be removed"
    assert "evt_B" in new_indicators
    assert removed == ["evt_A"]

    # Stale re-delivery of evt_A (older) must NOT re-add it
    new_indicators_2, removed_2 = apply_addressing_event(new_indicators, {
        "npc_id": "npc_1", "event_id": "evt_A", "intent": "talk", "intent_formed_at": 5,
    })
    assert "evt_A" not in new_indicators_2, "Stale re-delivery must not re-add removed event"
    assert "evt_B" in new_indicators_2, "Newer event must be preserved"
    assert removed_2 == []


def test_3_npc_absence_preserves_event():
    """Отсутствие NPC в npc_coords не удаляет событие.

    draw_addressing_indicators итерирует dict индикаторов (не npc_coords);
    отсутствие NPC только пропускает рендер, никогда не удаляет из хранения.
    """
    fr_src = _read_focus_renderer_source()
    # Итерация по dict индикаторов (не по npc_coords)
    assert "for _eid, _addr in addressing_indicators.items()" in fr_src, (
        "draw_addressing_indicators must iterate indicators dict — "
        "preserves events when NPC absent from npc_coords"
    )
    # Никаких операций удаления в focus_renderer
    assert "addressing_indicators.pop" not in fr_src
    assert "addressing_indicators.clear" not in fr_src
    assert "del addressing_indicators" not in fr_src


def test_4_multiple_npcs_independent():
    """Несколько NPC обрабатываются независимо."""
    indicators = {
        "evt_A": {"npc_id": "npc_1", "event_id": "evt_A", "intent": "talk", "intent_formed_at": 5},
        "evt_B": {"npc_id": "npc_2", "event_id": "evt_B", "intent": "warn", "intent_formed_at": 5},
    }
    new_indicators, removed = apply_addressing_event(indicators, {
        "npc_id": "npc_1", "event_id": "evt_C", "intent": "trade", "intent_formed_at": 10,
    })
    assert "evt_B" in new_indicators, "Event for npc_2 must be preserved when new event for npc_1 arrives"
    assert "evt_A" not in new_indicators, "Old event for npc_1 must be removed (intent changed)"
    assert "evt_C" in new_indicators
    assert removed == ["evt_A"]


def test_5_multiple_events_per_npc_tracked_by_event_id():
    """Несколько событий одного NPC не смешиваются (по event_id).

    Событие без intent_formed_at (неизвестная актуальность) сохраняется
    рядом с новым событием — не сливается, не удаляется.
    """
    indicators = {
        "evt_A": {"npc_id": "npc_1", "event_id": "evt_A", "intent": "talk"},  # no intent_formed_at
    }
    new_indicators, removed = apply_addressing_event(indicators, {
        "npc_id": "npc_1", "event_id": "evt_B", "intent": "warn", "intent_formed_at": 10,
    })
    assert "evt_A" in new_indicators, "Event with unknown actuality must be preserved"
    assert "evt_B" in new_indicators
    assert removed == [], "Event with missing intent_formed_at must not be removed"
    # Tracked separately by event_id
    assert new_indicators["evt_A"]["event_id"] == "evt_A"
    assert new_indicators["evt_B"]["event_id"] == "evt_B"


def test_6_redelivery_no_duplicates():
    """Повторная доставка того же event_id не создаёт дубликатов."""
    indicators = {
        "evt_A": {"npc_id": "npc_1", "event_id": "evt_A", "intent": "talk", "intent_formed_at": 5},
    }
    new_indicators, removed = apply_addressing_event(indicators, {
        "npc_id": "npc_1", "event_id": "evt_A", "intent": "talk", "intent_formed_at": 5,
    })
    assert len(new_indicators) == 1, "Re-delivery of same event_id must not create duplicate"
    assert "evt_A" in new_indicators
    assert removed == []


def test_7_campaign_switch_resets():
    """Переключение кампании сбрасывает индикаторы.

    run() должен сбрасывать npc_addressing_indicators наравне с
    npc_speech_bubbles и npc_manifest_indicators.
    """
    src = _read_game_screen_source()
    run_start = src.find("def run(self, campaign_folder:")
    assert run_start >= 0, "run() method not found"
    run_body = src[run_start:run_start + 2000]
    assert "self.npc_addressing_indicators = {}" in run_body, (
        "run() must reset npc_addressing_indicators (campaign switch isolation)"
    )
    # Регрессия: manifest/speech resets тоже на месте
    assert "self.npc_speech_bubbles = {}" in run_body
    assert "self.npc_manifest_indicators = {}" in run_body


def test_8_unknown_actuality_preserved():
    """Неизвестная актуальность (нет intent_formed_at) не приводит к удалению."""
    indicators = {
        "evt_A": {"npc_id": "npc_1", "event_id": "evt_A", "intent": "talk"},  # no intent_formed_at
        "evt_B": {"npc_id": "npc_1", "event_id": "evt_B", "intent": "warn", "intent_formed_at": 5},
    }
    # New event with intent_formed_at — removes evt_B (older) but NOT evt_A (unknown)
    new_indicators, removed = apply_addressing_event(indicators, {
        "npc_id": "npc_1", "event_id": "evt_C", "intent": "trade", "intent_formed_at": 10,
    })
    assert "evt_A" in new_indicators, "Event with unknown actuality must be preserved"
    assert "evt_B" not in new_indicators, "Event with older intent_formed_at must be removed"
    assert "evt_C" in new_indicators
    assert removed == ["evt_B"]


def test_9_ack_and_delivery_queue_unchanged():
    """Контракт #9: ACK всегда выполняется (включая stale re-delivery).

    Source-inspection: ACK вызов не вложен в тело guard 'if not _skip_add'.
    Если ACK внутри guard, то при _skip_add=True (stale re-delivery) ACK
    пропускается -> delivery queue пересылает событие каждый цикл.

    Проверяем структурную вложенность, а не raw indent: ACK может быть
    обёрнут в try/except на том же уровне, что и guard (sibling statement).
    В этом случае raw indent вызова (32) > guard indent (28), но структурно
    ACK вне guard body (try/except — sibling guard'а).
    """
    from pathlib import Path

    _gs = Path(__file__).resolve().parents[3] / "frontend" / "game_screen.py"
    assert _gs.exists(), f"game_screen.py not found at {_gs}"
    _src = _gs.read_text(encoding="utf-8")
    _lines = _src.split("\n")

    # Guard 'if not _skip_add'
    _skip_idx = None
    _skip_indent = None
    for _i, _line in enumerate(_lines):
        _stripped = _line.lstrip()
        if _stripped.startswith("if not _skip_add") and not _stripped.startswith("#"):
            _skip_idx = _i
            _skip_indent = len(_line) - len(_stripped)
            break
    assert _skip_idx is not None, "guard 'if not _skip_add' not found in game_screen.py"

    # ACK call (skip imports, comments, def)
    _ack_idx = None
    for _i, _line in enumerate(_lines):
        _stripped = _line.lstrip()
        if (
            "ack_addressing" in _line
            and not _stripped.startswith("#")
            and not _stripped.startswith(("from ", "import ", "def "))
        ):
            _ack_idx = _i
            break
    assert _ack_idx is not None, "ack_addressing call not found in game_screen.py"
    assert _ack_idx > _skip_idx, (
        f"ACK (L{_ack_idx + 1}) must be below guard (L{_skip_idx + 1})"
    )

    _ack_indent = len(_lines[_ack_idx]) - len(_lines[_ack_idx].lstrip())

    # If ACK at indent <= guard indent -> outside guard body (sibling or above)
    if _ack_indent <= _skip_indent:
        return  # PASS

    # ACK at deeper indent. Check if a sibling statement (indent <= guard)
    # separates guard from ACK -> ACK is in a sibling block, not guard body.
    # Comments and empty lines don't count (they don't end Python blocks).
    _sibling_found = False
    for _i in range(_skip_idx + 1, _ack_idx):
        _line = _lines[_i]
        if not _line.strip() or _line.lstrip().startswith("#"):
            continue
        _ind = len(_line) - len(_line.lstrip())
        if _ind <= _skip_indent:
            _sibling_found = True
            break

    assert _sibling_found, (
        f"ACK call (L{_ack_idx + 1}, indent={_ack_indent}) is inside the body "
        f"of 'if not _skip_add' (L{_skip_idx + 1}, indent={_skip_indent}): "
        f"no sibling statement at indent <= {_skip_indent} found between "
        f"guard and ACK. ACK must execute even when _skip_add=True "
        f"(stale re-delivery), otherwise delivery queue re-sends the "
        f"event every cycle."
    )
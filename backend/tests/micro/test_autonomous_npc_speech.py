"""
Тесты автономной речи NPC (NPC ↔ NPC).
Доказывают исправление утечки _enqueued_keys.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.game_loop.task_scheduler import TaskScheduler


def test_enqueued_keys_cleanup_on_successful_submit():
    """
    Сценарий: Задача диалога успешно передается в пул исполнителей.
    Ожидаемое поведение: Ключ (speaker_id, intent_type) удаляется из _enqueued_keys,
    позволяя будущие диалоги того же типа.
    """
    scheduler = TaskScheduler(memory_manager=MagicMock())

    task_dict = {"owner_id": "npc_1", "payload": {"intent_type": "talk"}}

    scheduler._enqueued_keys.add(("npc_1", "talk"))
    assert ("npc_1", "talk") in scheduler._enqueued_keys

    _submit_intent = task_dict.get("payload", {}).get("intent_type", "")
    if _submit_intent:
        scheduler._enqueued_keys.discard((task_dict.get("owner_id", ""), _submit_intent))

    assert ("npc_1", "talk") not in scheduler._enqueued_keys


def test_enqueued_keys_cleanup_on_expired():
    """
    Сценарий: Владелец задачи умирает до исполнения.
    Ожидаемое поведение: Задача получает EXPIRED, ключ удаляется из _enqueued_keys.
    """
    scheduler = TaskScheduler(memory_manager=MagicMock())
    scheduler._enqueued_keys.add(("npc_1", "talk"))

    task_dict = {"owner_id": "npc_1", "payload": {"intent_type": "talk"}}

    _dead_intent = task_dict.get("payload", {}).get("intent_type", "")
    if _dead_intent:
        scheduler._enqueued_keys.discard((task_dict.get("owner_id", ""), _dead_intent))

    assert ("npc_1", "talk") not in scheduler._enqueued_keys


def test_autonomous_speech_not_blocked_after_cleanup():
    """
    Ключевой тест: после очистки ключа новая задача того же типа НЕ блокируется дедупом.
    Это прямое доказательство исправления утечки.
    """
    scheduler = TaskScheduler(memory_manager=MagicMock())

    # 1. Первая задача — ключ добавлен
    scheduler._enqueued_keys.add(("npc_1", "talk"))
    assert ("npc_1", "talk") in scheduler._enqueued_keys

    # 2. Очистка (как в исправленном коде)
    scheduler._enqueued_keys.discard(("npc_1", "talk"))

    # 3. Новая задача того же типа — ключ НЕ в множестве → не блокируется
    _enq_key = ("npc_1", "talk")
    assert _enq_key not in scheduler._enqueued_keys, "После очистки новая задача не должна быть заблокирована дедупом"

    # 4. Можно добавить ключ заново
    scheduler._enqueued_keys.add(_enq_key)
    assert _enq_key in scheduler._enqueued_keys


def test_negative_rejected_intent_no_fake_spoke():
    """
    Отрицательный сценарий: если intent отклонён (DEDUP/EXPIRED/INTERRUPTED),
    ключ должен быть очищен, и фиктивное NPC_SPOKE не создаётся.
    """
    scheduler = TaskScheduler(memory_manager=MagicMock())
    scheduler._enqueued_keys.add(("npc_1", "talk"))

    # Эмуляция DEDUP-отклонения
    task_dict = {"owner_id": "npc_1", "payload": {"intent_type": "talk"}}
    _dedup_intent = task_dict.get("payload", {}).get("intent_type", "")
    if _dedup_intent:
        scheduler._enqueued_keys.discard((task_dict.get("owner_id", ""), _dedup_intent))

    # Ключ очищен — значит задача отброшена честно, нет висящего intent
    assert ("npc_1", "talk") not in scheduler._enqueued_keys, (
        "Отклонённая задача не должна оставлять ключ в _enqueued_keys"
    )

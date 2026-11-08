"""
path: /project/backend/tests/micro/test_intent_identity.py
Назначение: Regression battery для next_intent_identity + intent_id_str
    (Stage 2.1 Commit 1 — Intent Identity Infrastructure).
    Проверки: повторяемость (replay-safe), монотонность, уникальность
    при разных владельцах и разных действиях, восстановление счётчиков
    из сохранения, формат ID, отсутствие UUID/hash/timestamp.
    Вердикт Мастера №1: счётчик по owner ID, action в ID, но не в ключе.
Зависимости: app.services.events.event_identity
Основные сущности: тесты battery
"""

import copy
import re

from app.services.events.event_identity import (
    intent_id_str,
    next_intent_identity,
)


def _fresh_scene(tick: int = 0) -> dict:
    """Свежая scene_state с пустыми счётчиками."""
    return {"tick": tick}


# ── Повторяемость ID (replay-safe) ──────────────────────────────────


def test_replay_same_sequence_same_ids():
    """Два прогона одинаковой последовательности → одинаковые ID."""
    seq = [("player", "attack"), ("player", "dialogue"), ("maid_lusya", "attack")]

    scene_a = _fresh_scene(tick=10)
    ids_a = []
    for owner, action in seq:
        tick, ordinal = next_intent_identity(scene_a, owner, action)
        ids_a.append(intent_id_str(tick, owner, action, ordinal))

    scene_b = _fresh_scene(tick=10)
    ids_b = []
    for owner, action in seq:
        tick, ordinal = next_intent_identity(scene_b, owner, action)
        ids_b.append(intent_id_str(tick, owner, action, ordinal))

    assert ids_a == ids_b, f"Replay determinism broken: {ids_a} != {ids_b}"


def test_replay_after_save_load_same_ids():
    """Сохранение → загрузка → продолжение → тот же ordinal, что и без паузы."""
    # Прогон без паузы
    scene_full = _fresh_scene(tick=5)
    next_intent_identity(scene_full, "player", "attack")
    next_intent_identity(scene_full, "player", "dialogue")
    _, ord3_full = next_intent_identity(scene_full, "player", "attack")

    # Прогон с "паузой" (save → load через deepcopy)
    scene_save = _fresh_scene(tick=5)
    next_intent_identity(scene_save, "player", "attack")
    next_intent_identity(scene_save, "player", "dialogue")
    scene_loaded = copy.deepcopy(scene_save)
    assert scene_loaded["intent_ordinals"]["player"] == 2
    _, ord3_loaded = next_intent_identity(scene_loaded, "player", "attack")

    assert ord3_full == ord3_loaded, \
        f"Save/load broke ordinal: {ord3_full} != {ord3_loaded}"


# ── Монотонность ────────────────────────────────────────────────────


def test_ordinal_monotonic_per_owner():
    """Ordinal монотонно возрастает для одного owner."""
    scene = _fresh_scene(tick=0)
    _, ord1 = next_intent_identity(scene, "player", "attack")
    _, ord2 = next_intent_identity(scene, "player", "dialogue")
    _, ord3 = next_intent_identity(scene, "player", "move")
    assert ord1 == 1
    assert ord2 == 2
    assert ord3 == 3
    assert ord1 < ord2 < ord3


# ── Уникальность при разных владельцах ──────────────────────────────


def test_different_owners_independent_ordinals():
    """Разные владельцы имеют независимые счётчики."""
    scene = _fresh_scene(tick=0)
    _, ord_p1 = next_intent_identity(scene, "player", "attack")
    _, ord_l1 = next_intent_identity(scene, "maid_lusya", "attack")
    _, ord_p2 = next_intent_identity(scene, "player", "dialogue")
    _, ord_l2 = next_intent_identity(scene, "maid_lusya", "talk")

    assert ord_p1 == 1 and ord_p2 == 2  # player: 1, 2
    assert ord_l1 == 1 and ord_l2 == 2  # maid_lusya: 1, 2 (независимо от player)


# ── Уникальность при разных действиях одного владельца ─────────────


def test_same_owner_different_actions_shared_ordinal():
    """Один owner, разные actions — ordinal сквозной (не отдельный счётчик
    на action).

    Вердикт Мастера №1, уточнение 2: action участвует в ID, но НЕ создаёт
    отдельную последовательность счётчиков для каждого типа действия.
    """
    scene = _fresh_scene(tick=0)
    _, ord1 = next_intent_identity(scene, "player", "attack")
    _, ord2 = next_intent_identity(scene, "player", "dialogue")
    _, ord3 = next_intent_identity(scene, "player", "attack")  # тот же action

    # ordinal сквозной: 1, 2, 3 (не 1, 1, 2 — не отдельный счётчик на action)
    assert ord1 == 1
    assert ord2 == 2
    assert ord3 == 3

    # IDs различаются (action в ID, ordinal в ID)
    id1 = intent_id_str(0, "player", "attack", ord1)
    id3 = intent_id_str(0, "player", "attack", ord3)
    assert id1 != id3, \
        "Same action different ordinal should produce different IDs"


# ── Восстановление счётчиков из сохранения ──────────────────────────


def test_save_load_preserves_ordinals():
    """Save → load → счётчики сохранены."""
    scene = _fresh_scene(tick=42)
    next_intent_identity(scene, "player", "attack")
    next_intent_identity(scene, "player", "dialogue")
    next_intent_identity(scene, "maid_lusya", "talk")

    loaded = copy.deepcopy(scene)
    assert loaded["intent_ordinals"]["player"] == 2
    assert loaded["intent_ordinals"]["maid_lusya"] == 1


def test_old_save_without_intent_keys_self_heals():
    """Старый сейв без intent_ordinals → setdefault создаёт пустой, не крашит."""
    old_scene = {"tick": 100}  # без intent_ordinals, без intent_lifecycle
    tick, ordinal = next_intent_identity(old_scene, "player", "attack")
    assert tick == 100
    assert ordinal == 1
    assert old_scene["intent_ordinals"] == {"player": 1}


# ── Формат ID ───────────────────────────────────────────────────────


def test_intent_id_str_format():
    """ID имеет детерминированный формат: intent:{tick}:{owner}:{action}:{ordinal}."""
    id_str = intent_id_str(42, "player", "attack", 7)
    assert id_str == "intent:42:player:attack:7"


def test_intent_id_str_no_uuid_no_hash_no_timestamp():
    """ID не содержит UUID, hash(), timestamp — только детерминированные
    компоненты (вердикт Мастера №1, уточнение 3)."""
    id_str = intent_id_str(100, "maid_lusya", "dialogue", 3)
    # Формат: intent:int:str:str:int — никаких hex UUID, никаких timestamp
    assert re.match(
        r"^intent:\d+:[a-zA-Z_][a-zA-Z0-9_]*:[a-zA-Z_][a-zA-Z0-9_]*:\d+$",
        id_str,
    ), f"ID format violation: {id_str}"
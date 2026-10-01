"""
Файл: backend/tests/test_g3_executor.py
Назначение: G3 (ADR-O-410) Этап 1 — юнит-сьют исполнителя объектных действий
    (первый runtime-writer WorldObjectStore). Секции: статус-словарь;
    OFF=no-op; SKIP-семантика (D7a); вердикты PASS/NO_OP/REJECT (D1–D5);
    Г4 caller-guard DENY (замок экзамена).
Зависимости: pytest, app.services.world.g3_executor,
    app.services.world.world_object_store, app.domain.action_commitment
Основные сущности: G3Status, G3Outcome, execute_object_action,
    TestG3StatusVocabulary, TestG3DisabledNoop, TestG3SkipSemantics,
    TestG3Verdicts, TestG4Guard
Запуск: cd backend; python -m pytest tests/test_g3_executor.py -v -s; cd ..
"""

from typing import Any, Dict

import pytest
from app.services.world.g3_executor import (
    G3Status,
    execute_object_action,
)


def _scene() -> Dict[str, Any]:
    """Минимальная живая сцена без world_objects (легитимный дефолт W1)."""
    return {"location_id": "tavern_silver_wolf", "npc_positions": {}}


class TestG3StatusVocabulary:
    def test_members_distinct_and_canonical(self):
        assert {s.value for s in G3Status} == {
            "G3_PASS",
            "G3_NO_OP",
            "G3_REJECT",
            "G3_SKIP",
        }

    def test_skip_is_not_pass(self):
        # Вердикт Мастера: G3_SKIP ≠ G3_PASS — отказ от ownership,
        # не исполнение.
        assert G3Status.G3_SKIP is not G3Status.G3_PASS


class TestG3DisabledNoop:
    def test_off_returns_skip_disabled_and_preserves_scene(self, monkeypatch):
        monkeypatch.delenv("W3_G3_ENABLED", raising=False)
        scene = _scene()
        out = execute_object_action(scene, "steal", "thief_shadow", "wo_x", tick=7)
        assert out.status is G3Status.G3_SKIP
        assert out.reason == "disabled"
        # No-op ДО вычислений: subtree даже не инициализирован.
        assert "world_objects" not in scene


class TestG3SkipSemantics:
    def test_unresolved_target_skips_without_mutation(self, monkeypatch):
        monkeypatch.setenv("W3_G3_ENABLED", "1")
        scene = _scene()  # цели-нет → store.get → None
        out = execute_object_action(
            scene, "steal", "thief_shadow", "guard_borko", tick=9
        )
        assert out.status is G3Status.G3_SKIP
        assert out.reason == "object_unresolved"
        assert "world_objects" not in scene

    def test_no_mapping_skips(self, monkeypatch):
        monkeypatch.setenv("W3_G3_ENABLED", "1")
        out = execute_object_action(_scene(), "use", "thief_shadow", "wo_x", tick=1)
        assert out.status is G3Status.G3_SKIP
        assert out.reason.startswith("no_mapping")

    def test_no_target_skips(self, monkeypatch):
        monkeypatch.setenv("W3_G3_ENABLED", "1")
        out = execute_object_action(_scene(), "steal", "thief_shadow", "", tick=2)
        assert out.status is G3Status.G3_SKIP
        assert out.reason == "no_target"

from app.errors import ArchitecturalViolationError
from app.services.world.world_object_store import WorldObjectStore


def _scene_with(object_id: str, archetype: str, state: str = "INTACT") -> Dict[str, Any]:
    """Мини-мир с одним объектом; рождение — ТОЛЬКО через фабрику стора
    (§13.4, паттерн _spawn_tavern из W1)."""
    scene = _scene()
    WorldObjectStore.spawn(
        scene, object_id, archetype, "tavern_silver_wolf", (5.0, 3.0), state=state
    )
    return scene


class TestG3Verdicts:
    def test_pass_mutates_world(self, monkeypatch):
        """PASS: FREE-стул + steal → HELD_BY актора. Мир ИЗМЕНИЛСЯ."""
        monkeypatch.setenv("W3_G3_ENABLED", "1")
        scene = _scene_with("chair_1", "chair")
        out = execute_object_action(
            scene, "steal", "thief_shadow", "chair_1", tick=11
        )
        assert out.status is G3Status.G3_PASS
        assert out.object_id == "chair_1"
        _held = WorldObjectStore.get(scene, "chair_1")
        assert _held is not None and _held.holder == "thief_shadow"

    def test_reject_container_target(self, monkeypatch):
        """REJECT: контейнер не держит TAKE (INSERT/REMOVE — W6) —
        событие публиковать нельзя (D4)."""
        monkeypatch.setenv("W3_G3_ENABLED", "1")
        scene = _scene_with("chest_1", "container", state="CLOSED")
        out = execute_object_action(
            scene, "steal", "thief_shadow", "chest_1", tick=12
        )
        assert out.status is G3Status.G3_REJECT
        assert out.reason.startswith("INVALID_TRANSITION")
        # Мир не изменился: контейнер цел.
        _chest = WorldObjectStore.get(scene, "chest_1")
        assert _chest is not None and _chest.holder is None


class TestG4Guard:
    def test_foreign_caller_denied(self):
        """Г4-замок: write из модуля вне цензуса → ArchitecturalViolationError.
        Экзаменационный паттерн (D-атака); test_g3_executor в цензусе —
        поэтому атака идёт из синтетического чужого модуля."""
        import types

        scene = _scene()
        _foreign = types.ModuleType("g4_foreign_attacker")
        _foreign.__dict__["scene"] = scene
        _code = (
            "from app.services.world.world_object_store import WorldObjectStore\n"
            "WorldObjectStore.spawn(scene, 'chair_x', 'chair', "
            "'tavern_silver_wolf', (1.0, 1.0))\n"
        )
        with pytest.raises(ArchitecturalViolationError):
            exec(_code, _foreign.__dict__)  # noqa: S102 — экзамен Г4
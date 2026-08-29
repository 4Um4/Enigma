"""
path: /project/backend/tests/test_world_object_topology.py
Назначение: W1 (ADR-O-371) — контракт семантической объектной топологии.
    Секции: (A) domain-контракт WorldObject и pure-переходы; (B) store-
    операции WorldObjectStore над scene_state["world_objects"]; (C) DoD-цикл
    Мастера через РЕАЛЬНЫЙ SqlitePersistenceAdapter (создали -> relation ->
    atomic_commit_all -> load_scene_at -> ТОТ ЖЕ объект) + второй
    commit-цикл мутации; (D) мост WorldSnapshot (заморозка + immutability).
    Fixtures: door/chair/container/carried_item — ТОЛЬКО тестовые
    (вердикт Мастера S226: production-spawner вне W1).
    Объекты создаются фабриками build_world_object / WorldObjectStore.spawn
    (§13.4 — никаких конструктор-мечтаний); прямой конструктор — только
    там, где тест-цель сам guard __post_init__.
Зависимости: pytest, app.domain.world_object, app.services.world,
    app.services.state.sqlite_persistence_adapter, app.models.world_snapshot
Основные сущности: TestDomainContract, TestStoreOperations,
    TestPersistenceDoD, TestSnapshotBridge
"""
import tempfile
from pathlib import Path

import pytest
from app.domain.exceptions import OntologyViolationError
from app.domain.world_object import (
    CarrierMode,
    ObjectRelationKind,
    WorldObject,
    apply_relation_transition,
    build_world_object,
    relocate_object,
)
from app.models.world_snapshot import build_snapshot
from app.services.state.sqlite_persistence_adapter import SqlitePersistenceAdapter
from app.services.world import WorldObjectStore

# ═══ Fixtures: мини-мир таверны (только тестовые объекты) ═══

def _spawn_tavern(scene: dict) -> dict:
    """Мини-мир: дверь, стол + миска (опора), сундук + монета (вложение),
    кружка (свободная). Рождение — ТОЛЬКО через фабрику стора."""
    WorldObjectStore.spawn(scene, "door_1", "door", "tavern", (0.0, 5.0), state="CLOSED")
    WorldObjectStore.spawn(scene, "table_1", "table", "tavern", (5.0, 3.0))
    WorldObjectStore.spawn(scene, "bowl_1", "bowl", "tavern", (5.3, 3.0))
    WorldObjectStore.spawn(scene, "chest_1", "container", "tavern", (2.0, 2.0), state="CLOSED")
    WorldObjectStore.spawn(scene, "coin_1", "coin", "tavern", (2.0, 2.0))
    WorldObjectStore.spawn(scene, "cup_1", "cup", "tavern", (6.0, 4.0))
    return scene


# ═══ A. Domain-контракт (pure) ═══

class TestDomainContract:

    def test_birth_is_free(self):
        """Объект рождается в FREE без отношений — связывание отдельно."""
        obj = build_world_object("chair_1", "chair", "tavern", (5.0, 3.0))
        assert obj.carrier_mode == CarrierMode.FREE
        assert obj.holder is None and obj.container_id is None
        assert obj.attachment is None and obj.supported_by is None

    def test_carrier_exclusivity_at_construction(self):
        """Тест-цель — сам guard: мульти-carrier объект непостроим."""
        with pytest.raises(OntologyViolationError):
            WorldObject(
                object_id="bad_1", archetype="chair", location_id="tavern",
                position=(0.0, 0.0), state="INTACT",
                holder="npc_1", container_id="chest_1",
            )

    def test_empty_id_rejected(self):
        with pytest.raises(OntologyViolationError):
            build_world_object("", "chair", "tavern", (0.0, 0.0))

    def test_damage_bounds(self):
        with pytest.raises(OntologyViolationError):
            build_world_object("bad_1", "chair", "tavern", (0.0, 0.0), damage=1.5)

    def test_attachment_atomicity(self):
        """ATTACHED_TO = (host, slot) вместе; slot обязателен."""
        obj = build_world_object("sword_1", "sword", "tavern", (1.0, 1.0))
        with pytest.raises(OntologyViolationError):
            apply_relation_transition(obj, ObjectRelationKind.ATTACHED_TO, "npc_1")
        ok = apply_relation_transition(
            obj, ObjectRelationKind.ATTACHED_TO, "npc_1", slot="belt_sheath")
        assert ok.attachment == ("npc_1", "belt_sheath")

    def test_strict_release(self):
        """Release неустановленного отношения — громко (не silent no-op)."""
        obj = build_world_object("chair_1", "chair", "tavern", (5.0, 3.0))
        with pytest.raises(OntologyViolationError):
            apply_relation_transition(obj, ObjectRelationKind.HELD_BY, None)

    def test_no_auto_release(self):
        """Никакого авто-сброса: явная цепочка release -> establish."""
        obj = build_world_object("bowl_1", "bowl", "tavern", (5.0, 3.0))
        obj = apply_relation_transition(obj, ObjectRelationKind.SUPPORTED_BY, "table_1")
        with pytest.raises(OntologyViolationError):
            apply_relation_transition(obj, ObjectRelationKind.HELD_BY, "npc_1")
        obj = apply_relation_transition(obj, ObjectRelationKind.SUPPORTED_BY, None)
        obj = apply_relation_transition(obj, ObjectRelationKind.HELD_BY, "npc_1")
        assert obj.holder == "npc_1" and obj.supported_by is None

    def test_relocate_requires_free(self):
        obj = build_world_object("chair_1", "chair", "tavern", (5.0, 3.0))
        obj = apply_relation_transition(obj, ObjectRelationKind.HELD_BY, "npc_1")
        with pytest.raises(OntologyViolationError):
            relocate_object(obj, "tavern", (1.0, 1.0))

    def test_relocate_blocked_by_support(self):
        obj = build_world_object("bowl_1", "bowl", "tavern", (5.0, 3.0))
        obj = apply_relation_transition(obj, ObjectRelationKind.SUPPORTED_BY, "table_1")
        with pytest.raises(OntologyViolationError):
            relocate_object(obj, "tavern", (1.0, 1.0))

    def test_roundtrip_all_relations(self):
        """Сериализация сохраняет все отношения (§12 WARA)."""
        obj = build_world_object("bowl_1", "bowl", "tavern", (5.3, 3.0))
        obj = apply_relation_transition(obj, ObjectRelationKind.SUPPORTED_BY, "table_1")
        obj = apply_relation_transition(obj, ObjectRelationKind.USED_BY, "npc_17")
        restored = WorldObject.from_dict(obj.to_dict())
        assert restored == obj
        kinds = {r.kind for r in restored.project_relations()}
        assert {ObjectRelationKind.LOCATED_AT,
                ObjectRelationKind.SUPPORTED_BY,
                ObjectRelationKind.USED_BY} <= kinds

    def test_roundtrip_attachment(self):
        obj = build_world_object("sword_1", "sword", "tavern", (1.0, 1.0))
        obj = apply_relation_transition(
            obj, ObjectRelationKind.ATTACHED_TO, "npc_1", slot="belt_sheath")
        restored = WorldObject.from_dict(obj.to_dict())
        assert restored.attachment == ("npc_1", "belt_sheath")
        assert restored == obj

    def test_w0_no_presentation_fields(self):
        """W0-инвариант: ни одного renderer-слова в сериализации."""
        obj = build_world_object("door_1", "door", "tavern", (0.0, 5.0))
        forbidden = ("sprite", "mesh", "texture", "animation", "model")
        for key in obj.to_dict():
            assert not any(f in key.lower() for f in forbidden), key


# ═══ B. Store-операции ═══

class TestStoreOperations:

    def test_duplicate_spawn(self):
        scene = _spawn_tavern({})
        with pytest.raises(OntologyViolationError):
            WorldObjectStore.spawn(scene, "table_1", "table", "tavern", (1.0, 1.0))

    def test_ghost_target(self):
        scene = _spawn_tavern({})
        with pytest.raises(OntologyViolationError):
            WorldObjectStore.establish_relation(
                scene, "cup_1", ObjectRelationKind.SUPPORTED_BY, "ghost_table")

    def test_cross_location_support(self):
        scene = _spawn_tavern({})
        WorldObjectStore.spawn(scene, "table_2", "table", "cellar", (1.0, 1.0))
        with pytest.raises(OntologyViolationError):
            WorldObjectStore.establish_relation(
                scene, "cup_1", ObjectRelationKind.SUPPORTED_BY, "table_2")

    def test_non_free_support_target(self):
        """Опора обязана владеть своей позицией (FREE)."""
        scene = _spawn_tavern({})
        WorldObjectStore.establish_relation(
            scene, "chest_1", ObjectRelationKind.HELD_BY, "npc_17")
        with pytest.raises(OntologyViolationError):
            WorldObjectStore.establish_relation(
                scene, "cup_1", ObjectRelationKind.SUPPORTED_BY, "chest_1")

    def test_cycle_rejected(self):
        scene = _spawn_tavern({})
        WorldObjectStore.establish_relation(
            scene, "coin_1", ObjectRelationKind.CONTAINED_BY, "chest_1")
        with pytest.raises(OntologyViolationError):
            WorldObjectStore.establish_relation(
                scene, "chest_1", ObjectRelationKind.CONTAINED_BY, "coin_1")

    def test_existing_cycle_detected_loud(self):
        """Уже существующий цикл (повреждение извне) — громко на следующей
        операции, не маскировка."""
        scene = {}
        WorldObjectStore.spawn(scene, "a_1", "box", "tavern", (0.0, 0.0))
        WorldObjectStore.spawn(scene, "b_1", "box", "tavern", (1.0, 1.0))
        # прямая dict-хирургия = имитация повреждённых данных
        scene["world_objects"]["a_1"]["container_id"] = "b_1"
        scene["world_objects"]["b_1"]["container_id"] = "a_1"
        WorldObjectStore.spawn(scene, "c_1", "box", "tavern", (2.0, 2.0))
        with pytest.raises(OntologyViolationError):
            WorldObjectStore.establish_relation(
                scene, "c_1", ObjectRelationKind.CONTAINED_BY, "a_1")

    def test_relocate_blocked_then_released(self):
        scene = _spawn_tavern({})
        WorldObjectStore.establish_relation(
            scene, "bowl_1", ObjectRelationKind.SUPPORTED_BY, "table_1")
        with pytest.raises(OntologyViolationError):
            WorldObjectStore.relocate(scene, "table_1", "tavern", (7.0, 7.0))
        WorldObjectStore.release_relation(
            scene, "bowl_1", ObjectRelationKind.SUPPORTED_BY)
        WorldObjectStore.relocate(scene, "table_1", "tavern", (7.0, 7.0))
        assert WorldObjectStore.get(scene, "table_1").position == (7.0, 7.0)

    def test_relocate_with_contained_dependents_allowed(self):
        """Перенос сундука с содержимым легален: позиция вложенных —
        производная владельца (онтология carrier, ADR-O-371)."""
        scene = _spawn_tavern({})
        WorldObjectStore.establish_relation(
            scene, "coin_1", ObjectRelationKind.CONTAINED_BY, "chest_1")
        WorldObjectStore.relocate(scene, "chest_1", "tavern", (8.0, 8.0))
        assert WorldObjectStore.get(scene, "chest_1").position == (8.0, 8.0)
        assert WorldObjectStore.get(scene, "coin_1").container_id == "chest_1"

    def test_query_objects_at_free_only(self):
        scene = _spawn_tavern({})
        WorldObjectStore.establish_relation(
            scene, "bowl_1", ObjectRelationKind.SUPPORTED_BY, "table_1")
        WorldObjectStore.establish_relation(
            scene, "coin_1", ObjectRelationKind.CONTAINED_BY, "chest_1")
        at = WorldObjectStore.query_objects_at(scene, "tavern", (5.0, 3.0), radius=0.5)
        # bowl FREE+SUPPORTED — включён; coin CONTAINED — исключён
        assert "table_1" in at and "bowl_1" in at
        assert "coin_1" not in at
        # radius=0.0 — точное совпадение (контракт ТЗ §20.2)
        assert WorldObjectStore.query_objects_at(
            scene, "tavern", (5.0, 3.0), radius=0.0) == ("table_1",)

    def test_container_contents_inverse(self):
        """Содержимое контейнера — ЗАПРОС, не хранимое mirror-поле."""
        scene = _spawn_tavern({})
        WorldObjectStore.establish_relation(
            scene, "coin_1", ObjectRelationKind.CONTAINED_BY, "chest_1")
        assert [o.object_id for o in
                WorldObjectStore.query_container_contents(scene, "chest_1")] == ["coin_1"]
        assert WorldObjectStore.query_container_contents(scene, "table_1") == ()

    def test_used_by_atomic_transfer(self):
        """USED_BY — независимое отношение: атомарная замена = передача."""
        scene = _spawn_tavern({})
        WorldObjectStore.establish_relation(
            scene, "cup_1", ObjectRelationKind.USED_BY, "npc_a")
        WorldObjectStore.establish_relation(
            scene, "cup_1", ObjectRelationKind.USED_BY, "npc_b")
        assert WorldObjectStore.get(scene, "cup_1").used_by == "npc_b"

    def test_used_by_compatible_with_held(self):
        """USED_BY совместим с carrier (онтология: независимая ось)."""
        scene = _spawn_tavern({})
        WorldObjectStore.establish_relation(
            scene, "cup_1", ObjectRelationKind.HELD_BY, "npc_a")
        WorldObjectStore.establish_relation(
            scene, "cup_1", ObjectRelationKind.USED_BY, "npc_a")
        obj = WorldObjectStore.get(scene, "cup_1")
        assert obj.holder == "npc_a" and obj.used_by == "npc_a"

    def test_read_never_mutates_scene(self):
        """Lazy-init ТОЛЬКО на write-пути (Pure Reducer Фазы 5, M1a)."""
        scene = {"npc_positions": {}}
        assert WorldObjectStore.get(scene, "door_1") is None
        assert WorldObjectStore.get_all(scene) == ()
        assert WorldObjectStore.query_object_relations(scene, "door_1") is None
        assert WorldObjectStore.query_container_contents(scene, "chest_1") == ()
        assert WorldObjectStore.query_objects_at(scene, "tavern", (0.0, 0.0)) == ()
        assert "world_objects" not in scene

    def test_corrupted_subtree_loud(self):
        """Повреждённая структура — громкий отказ, не дефолт."""
        scene = {"world_objects": [1, 2, 3]}
        with pytest.raises(OntologyViolationError):
            WorldObjectStore.get(scene, "door_1")


# ═══ C. DoD-цикл Мастера: персистенция через реальный адаптер ═══

class TestPersistenceDoD:

    def test_spawn_relation_save_load_same_object(self):
        """DoD W1: создали -> relation -> сохранили -> перезагрузили ->
        получили ТОТ ЖЕ семантический объект. Ноль специального
        persistence-кода: subtree едет на диск внутри scene_state
        (Foundation Freeze, atomic_commit_all)."""
        with tempfile.TemporaryDirectory() as tmp:
            adapter = SqlitePersistenceAdapter(Path(tmp) / "w1_dod.sqlite")
            scene = {"location_id": "tavern", "tick": 7, "game_time_seconds": 70.0}
            _spawn_tavern(scene)
            WorldObjectStore.establish_relation(
                scene, "bowl_1", ObjectRelationKind.SUPPORTED_BY, "table_1")
            WorldObjectStore.establish_relation(
                scene, "coin_1", ObjectRelationKind.CONTAINED_BY, "chest_1")
            WorldObjectStore.establish_relation(
                scene, "bowl_1", ObjectRelationKind.USED_BY, "npc_17")

            assert adapter.atomic_commit_all(
                campaign_id="w1_campaign", all_scenes={"tavern": scene})

            loaded = adapter.load_scene_at("w1_campaign", "tavern")
            assert loaded is not None
            # ТОТ ЖЕ объект (frozen-равенство всех полей)
            assert WorldObjectStore.get(loaded, "bowl_1") == WorldObjectStore.get(scene, "bowl_1")
            assert WorldObjectStore.get(loaded, "bowl_1").supported_by == "table_1"
            assert WorldObjectStore.get(loaded, "bowl_1").used_by == "npc_17"
            assert WorldObjectStore.get(loaded, "coin_1").container_id == "chest_1"
            assert WorldObjectStore.get(loaded, "door_1").state == "CLOSED"
            # inverse-запрос работает на загруженной сцене
            assert [o.object_id for o in WorldObjectStore.query_container_contents(
                loaded, "chest_1")] == ["coin_1"]
            adapter.close()

    def test_mutation_survives_second_commit(self):
        """Полный lifecycle W3-писателя: load -> mutate via store ->
        commit -> load. Доказывает паттерн будущего causal writer."""
        with tempfile.TemporaryDirectory() as tmp:
            adapter = SqlitePersistenceAdapter(Path(tmp) / "w1_dod2.sqlite")
            scene = {"location_id": "tavern", "tick": 1}
            _spawn_tavern(scene)
            WorldObjectStore.establish_relation(
                scene, "coin_1", ObjectRelationKind.CONTAINED_BY, "chest_1")
            adapter.atomic_commit_all(campaign_id="w1_c2", all_scenes={"tavern": scene})

            loaded = adapter.load_scene_at("w1_c2", "tavern")
            WorldObjectStore.release_relation(
                loaded, "coin_1", ObjectRelationKind.CONTAINED_BY)
            adapter.atomic_commit_all(campaign_id="w1_c2", all_scenes={"tavern": loaded})

            reloaded = adapter.load_scene_at("w1_c2", "tavern")
            assert WorldObjectStore.get(reloaded, "coin_1").container_id is None
            adapter.close()


# ═══ D. Мост WorldSnapshot ═══

class TestSnapshotBridge:

    def test_freeze_and_immutability(self):
        """Заморозка: мутация живой сцены после снимка не проходит."""
        scene = {"npc_positions": {}, "active_traversals": {}}
        _spawn_tavern(scene)
        WorldObjectStore.establish_relation(
            scene, "bowl_1", ObjectRelationKind.SUPPORTED_BY, "table_1")
        snap = build_snapshot(tick=7, campaign_id="c", location_id="tavern",
                              spatial_service=None, scene_state=scene)
        assert snap.world_objects is not None
        assert snap.world_objects["bowl_1"]["supported_by"] == "table_1"
        scene["world_objects"]["bowl_1"]["supported_by"] = "ghost"
        assert snap.world_objects["bowl_1"]["supported_by"] == "table_1"

    def test_empty_scene_legitimate(self):
        """Production до спавнера: пустая сцена -> {} — честно."""
        snap = build_snapshot(tick=1, campaign_id="c", location_id="tavern",
                              spatial_service=None, scene_state={})
        assert snap.world_objects == {}
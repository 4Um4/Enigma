"""
python -m pytest tests/test_player_cognition_pipeline.py -v -s
tests/test_player_cognition_pipeline.py
End-to-end тест player_cognition pipeline на реальных данных из campaign_state.json.

path: /backend/tests/test_player_cognition_pipeline.py
Назначение: End-to-end тест player_cognition pipeline на реальных данных
Зависимости: app.services.player_cognition, json
Основные сущности: test_pipeline_low_stress, test_pipeline_high_stress, test_pipeline_injured
"""
import json
from pathlib import Path

import pytest

from app.services.player_cognition import (
    build_perceived_scene,
    PerceptionConfig,
    PlayerFocus,
)


@pytest.fixture
def real_scene_state() -> dict:
    """Загружает реальный SceneState из Open_road, сливая npc_positions с верхнего уровня"""
    path = Path(__file__).parent.parent / "data" / "campaigns" / "Open_road" / "campaign_state.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    scene = data.get("scene_state")
    # В сохранённом файле npc_positions на верхнем уровне,
    # но в runtime game_loop кладёт их внутрь scene_state
    if "npc_positions" in data and "npc_positions" not in scene:
        scene["npc_positions"] = data["npc_positions"]
    return scene


def _print_result(result, label: str) -> None:
    """Отладочная печать результата pipeline"""
    print(f"\n=== {label} ===")
    print(f"Location: {result.location_id}")
    print(f"Entities total: {len(result.entities)}")
    visible = [e for e in result.entities if e.visible]
    print(f"Entities visible: {len(visible)}")
    print(f"Audio events: {len(result.audio_events)}")
    print(f"Environment light: {result.environment.light_perceived}")
    print(f"Body state: {result.player_body_state}")
    print("---")
    for e in result.entities:
        if e.visible or e.audio_only:
            print(
                f"  {e.entity_id} | vis={e.visible} attn={e.in_attention} "
                f"name=\"{e.display_name}\" conf={e.final_confidence:.2f} "
                f"dist={e.distance:.1f}m los={e.los}"
            )
            for inf in e.inferences:
                print(f"    -> {inf.inference_type} ({inf.tier.name}) conf={inf.confidence:.2f}")
    for a in result.audio_events:
        print(f"  [AUDIO] \"{a.description}\" dir={a.direction} dist={a.approximate_distance:.1f}m")


class TestPipelineLowStress:
    """Игрок спокоен, фокус на maid_lusya — должен хорошо видеть и узнавать"""

    def test_visible_entities_exist(self, real_scene_state):
        config = PerceptionConfig(
            player_focus=PlayerFocus(focus_entity_id="maid_lusya"),
            player_stress=20.0,
            player_hp=90,
            player_max_hp=100,
        )
        result = build_perceived_scene(real_scene_state, config)
        _print_result(result, "Low stress, focus on maid_lusya")

        visible = [e for e in result.entities if e.visible]
        assert len(visible) > 0, "Должны быть видимые сущности"

    def test_focused_entity_always_in_attention(self, real_scene_state):
        config = PerceptionConfig(
            player_focus=PlayerFocus(focus_entity_id="maid_lusya"),
            player_stress=20.0,
        )
        result = build_perceived_scene(real_scene_state, config)

        lusya = next((e for e in result.entities if e.entity_id == "maid_lusya"), None)
        assert lusya is not None, "maid_lusya должна быть в entities"
        assert lusya.in_attention, "Фокусная сущность всегда в внимании"
        assert lusya.attention_score == 1.0, "Фокусная сущность имеет score 1.0"

    def test_no_body_state_when_healthy(self, real_scene_state):
        config = PerceptionConfig(
            player_focus=PlayerFocus(),
            player_stress=0.0,
            player_hp=100,
            player_max_hp=100,
            player_fatigue=0.0,
        )
        result = build_perceived_scene(real_scene_state, config)
        assert len(result.player_body_state) == 0, "Здоровый спокойный игрок не имеет телесных ощущений"

    def test_objects_have_names(self, real_scene_state):
        config = PerceptionConfig(player_focus=PlayerFocus())
        result = build_perceived_scene(real_scene_state, config)

        visible_objects = [e for e in result.entities if e.visible and e.entity_type == "object"]
        assert len(visible_objects) > 0, "Должны быть видимые объекты"
        for obj in visible_objects:
            assert obj.display_name, f"Объект {obj.entity_id} должен иметь display_name"


class TestPipelineHighStress:
    """Высокий стресс — сужение внимания, искажение окружения"""

    def test_fewer_entities_attended(self, real_scene_state):
        """При высоком стрессе меньше сущностей в внимании (tunnel vision)"""
        config_low = PerceptionConfig(
            player_focus=PlayerFocus(focus_entity_id="maid_lusya"),
            player_stress=10.0,
        )
        config_high = PerceptionConfig(
            player_focus=PlayerFocus(focus_entity_id="maid_lusya"),
            player_stress=80.0,
        )

        # Строгий seed для воспроизводимости stochastic edge
        import random
        random.seed(42)
        result_low = build_perceived_scene(real_scene_state, config_low)

        random.seed(42)
        result_high = build_perceived_scene(real_scene_state, config_high)

        attended_low = sum(1 for e in result_low.entities if e.in_attention)
        attended_high = sum(1 for e in result_high.entities if e.in_attention)

        _print_result(result_low, "Low stress")
        _print_result(result_high, "High stress")

        assert attended_high <= attended_low, \
            f"Высокий стресс должен сужать внимание: {attended_high} <= {attended_low}"

    def test_environment_darkens(self, real_scene_state):
        config = PerceptionConfig(player_stress=70.0)
        result = build_perceived_scene(real_scene_state, config)
        assert result.environment.light_perceived in ("приглушённо", "темно"), \
            "Высокий стресс делает мир темнее"

    def test_body_state_appears(self, real_scene_state):
        config = PerceptionConfig(player_stress=60.0)
        result = build_perceived_scene(real_scene_state, config)
        assert len(result.player_body_state) > 0, "Высокий стресс даёт телесные ощущения"


class TestPipelineInjured:
    """Раненый игрок — усиление угрозы, телесные ощущения"""

    def test_threat_amplification(self, real_scene_state):
        config = PerceptionConfig(
            player_focus=PlayerFocus(),
            player_hp=30,
            player_max_hp=100,
        )
        result = build_perceived_scene(real_scene_state, config)
        _print_result(result, "Injured (30/100 HP)")

        # Все видимые сущности должны иметь threat_bias > 0
        for e in result.entities:
            if e.visible:
                assert e.threat_bias > 0, f"{e.entity_id} должен иметь threat_bias при низком HP"

    def test_body_state_injured(self, real_scene_state):
        config = PerceptionConfig(player_hp=20, player_max_hp=100)
        result = build_perceived_scene(real_scene_state, config)
        assert any("боль" in s for s in result.player_body_state), \
            "Раненый игрок должен чувствовать боль"


def _make_scene_with_visible_npc(npc_id: str = "test_npc", distance: float = 3.0) -> dict:
    """Создаёт минимальный SceneState с одним NPC в прямой видимости"""
    return {
        "location_id": "test_room",
        "environment": {"light_level": "bright", "noise_level": "quiet"},
        "environment_modifiers": {"light": 1.0, "noise": 0.0, "density": 0.0, "danger": 0.0},
        "player_spatial": {"location_id": "test_room", "position": "", "local_position": {"x": 5.0, "y": 5.0}},
        "objects": {},
        "spatial_walls": [
            {"x1": 0, "y1": 0, "x2": 10, "y2": 0},
            {"x1": 0, "y1": 0, "x2": 0, "y2": 10},
            {"x1": 10, "y1": 0, "x2": 10, "y2": 10},
            {"x1": 0, "y1": 10, "x2": 10, "y2": 10},
        ],
        "spatial_obstacles": [],
        "npc_positions": {
            npc_id: {
                "location_id": "test_room",
                "position": "",
                "activity": "talking",
                "visible": True,
                "local_position": {"x": 5.0 + distance, "y": 5.0},
            }
        },
    }


class TestPipelineSynthetic:
    """Синтетические данные — полный контроль над layout"""

    def test_visible_npc_recognized(self):
        scene = _make_scene_with_visible_npc("guard_1", distance=3.0)
        config = PerceptionConfig(
            player_focus=PlayerFocus(focus_entity_id="guard_1"),
        )
        import random
        random.seed(42)
        result = build_perceived_scene(scene, config)
        _print_result(result, "Synthetic: visible NPC at 3m")

        guard = next((e for e in result.entities if e.entity_id == "guard_1"), None)
        assert guard is not None, "NPC должен быть в entities"
        assert guard.visible, "NPC на открытом пространстве должен быть видим"
        assert guard.in_attention, "Фокусный NPC должен быть в внимании"
        assert guard.display_name, "NPC должен иметь display_name"
        assert guard.recognition_confidence > 0, "Узнавание должно быть > 0"

    def test_npc_with_activity_gets_interpretation(self):
        scene = _make_scene_with_visible_npc("guard_1", distance=2.0)
        scene["npc_positions"]["guard_1"]["activity"] = "fighting"
        config = PerceptionConfig(
            player_focus=PlayerFocus(focus_entity_id="guard_1"),
        )
        import random
        random.seed(42)
        result = build_perceived_scene(scene, config)
        _print_result(result, "Synthetic: fighting NPC")

        guard = next((e for e in result.entities if e.entity_id == "guard_1"), None)
        inference_types = [inf.inference_type for inf in guard.inferences]
        assert "combat" in inference_types, "fighting activity должен дать combat inference"

    def test_npc_behind_wall_not_visible(self):
        scene = _make_scene_with_visible_npc("guard_1", distance=3.0)
        # Ставим стену между игроком и NPC
        scene["spatial_walls"].append({"x1": 6.0, "y1": 0.0, "x2": 6.0, "y2": 10.0})
        config = PerceptionConfig(
            player_focus=PlayerFocus(focus_entity_id="guard_1"),
        )
        result = build_perceived_scene(scene, config)
        _print_result(result, "Synthetic: NPC behind wall")

        guard = next((e for e in result.entities if e.entity_id == "guard_1"), None)
        assert guard is not None, "NPC должен быть в entities"
        assert not guard.visible, "NPC за стеной не должен быть видим"
        assert guard.los_blocked_by == "wall", "LOS должен быть заблокирован стеной"

    def test_armed_npc_gets_physical_inference(self):
        scene = _make_scene_with_visible_npc("guard_1", distance=3.0)
        scene["npc_positions"]["guard_1"]["visible_markers"] = ["sword", "armor"]
        scene["npc_positions"]["guard_1"]["activity"] = ""
        config = PerceptionConfig(
            player_focus=PlayerFocus(focus_entity_id="guard_1"),
        )
        import random
        random.seed(42)
        result = build_perceived_scene(scene, config)
        _print_result(result, "Synthetic: armed NPC")

        guard = next((e for e in result.entities if e.entity_id == "guard_1"), None)
        inference_types = [inf.inference_type for inf in guard.inferences]
        assert "armed" in inference_types, "NPC с мечом должен иметь armed inference"
        assert "armored" in inference_types, "NPC в доспехе должен иметь armored inference"            
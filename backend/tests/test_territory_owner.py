"""
Юнит-тесты ADR-O-386 (шаг 2): owner как факт мира.

path: /backend/tests/test_territory_owner.py
Назначение: владение переживает путь editor-JSON → compile_graph → NodeRef →
    SpatialService.zone_owner(). Узел без owner даёт None (обратная
    совместимость: существующие кампании не задеты).
Запуск: cd backend && python -m pytest tests/test_territory_owner.py -v

Зависимости: app.services.spatial.graph_compiler, app.services.spatial.spatial_service
Основные сущности: TestTerritoryOwnerCompilation
"""

from app.services.spatial.graph_compiler import compile_graph
from app.services.spatial.spatial_event_detector import SpatialEventDetector
from app.services.spatial.spatial_service import SpatialService

_EDITOR_DATA = {
    "nodes": {
        "bar_area": {
            "x": 4.5,
            "y": 6.5,
            "label": "У стойки",
            "role": "bar",
            "owner": "tavern_keeper_tornin",
            "connections": ["hall"],
        },
        "hall": {
            "x": 6.5,
            "y": 5.5,
            "label": "Центр зала",
            "role": "default",
            "connections": ["bar_area"],
        },
    },
    "rooms": [],
}


class TestTerritoryOwnerCompilation:

    def test_owner_survives_compilation(self):
        graph = compile_graph(_EDITOR_DATA, "tavern")[0]
        assert graph["tavern:bar_area"].owner == "tavern_keeper_tornin"
        assert graph["tavern:hall"].owner is None  # без owner — None (совместимость)

    def test_zone_owner_full_path(self):
        svc = SpatialService.build_for_location(
            campaign_id="test",
            location_id="tavern",
            scene_state={},
            editor_data_override=_EDITOR_DATA,
        )
        assert svc is not None
        assert svc.zone_owner("tavern:bar_area") == "tavern_keeper_tornin"
        assert svc.zone_owner("tavern:hall") is None
        assert svc.zone_owner("tavern:missing_node") is None  # несуществующий узел


class TestTrespassedDetection:
    """ADR-O-386, шаг 3: TRESPASSED за флагом TERRITORY_ENABLED (default OFF = no-op)."""

    _NEW_STATE = {
        "npc_positions": {
            "thief_shadow": {
                "local_position": {"x": 4.5, "y": 6.5},
                "position": "tavern:bar_area",
            }
        }
    }

    def _detect(self, zone_owner):
        return SpatialEventDetector().detect_and_publish(
            old_positions={"thief_shadow": (1.0, 1.0, "tavern:hall")},
            new_scene_state=self._NEW_STATE,
            zone_owner=zone_owner,
        )

    def test_trespassed_emitted_for_non_owner(self, monkeypatch):
        monkeypatch.setenv("TERRITORY_ENABLED", "1")
        events = self._detect(
            lambda node: "tavern_keeper_tornin" if node == "tavern:bar_area" else None
        )
        assert [e for e in events if e.type == "npc_moved"], "переход узла должен эмититься"
        trespassed = [e for e in events if e.type == "trespassed"]
        assert len(trespassed) == 1
        t = trespassed[0]
        assert t.source == "thief_shadow"
        assert t.payload["trespasser"] == "thief_shadow"
        assert t.payload["owner"] == "tavern_keeper_tornin"
        assert t.payload["node"] == "tavern:bar_area"

    def test_no_trespass_for_owner_entering_own_zone(self, monkeypatch):
        monkeypatch.setenv("TERRITORY_ENABLED", "1")
        events = self._detect(lambda node: "thief_shadow" if node == "tavern:bar_area" else None)
        assert not [e for e in events if e.type == "trespassed"]

    def test_no_trespass_when_flag_off(self, monkeypatch):
        monkeypatch.delenv("TERRITORY_ENABLED", raising=False)
        events = self._detect(
            lambda node: "tavern_keeper_tornin" if node == "tavern:bar_area" else None
        )
        assert not [e for e in events if e.type == "trespassed"]

    def test_no_trespass_for_unowned_node(self, monkeypatch):
        monkeypatch.setenv("TERRITORY_ENABLED", "1")
        events = self._detect(lambda node: None)
        assert not [e for e in events if e.type == "trespassed"]

    def test_no_trespass_without_lookup(self, monkeypatch):
        monkeypatch.setenv("TERRITORY_ENABLED", "1")
        events = self._detect(None)
        assert not [e for e in events if e.type == "trespassed"]


class TestTerritoryAuthorityGate:
    """ADR-O-386, шаг 4: территориальный authority в гейте (L-A1: территория ИЛИ роль)."""

    def _gate(self, role: str, intent_name: str, territory_pass: bool) -> bool:
        from app.models.npc_state import Intent, NPCStateAdapter
        from app.services.npc.decision_hub import DecisionHub

        _intent = (
            Intent.BLOCK_PATH.value
            if intent_name == "block_path"
            else Intent.AMBUSH.value
        )
        _state = NPCStateAdapter.from_legacy(
            {
                "npc_id": "gate_test_npc",
                "psyche": {"state": "free", "stress": 5.0},
                "status_profile": {"title": role},
                "social_stats": {},
            }
        )
        # Unbound-вызов с dummy-self: в достижимых ветках (не-BROKEN, stress<90,
        # block_path/ambush) метод не обращается к self/personality/opportunity —
        # юнит не тянет RNG-конфигурацию хаба. Если будущее обращение к self
        # появится — упадёт громко (AttributeError), честный сторож.
        return DecisionHub._is_intent_available(
            object(), _intent, _state, None, None, territory_pass=territory_pass
        )

    def test_peaceful_role_with_pass_unlocks(self):
        # «Торнин не пустит Тень за стойку»: мирная роль + владение территорией
        assert self._gate("Хозяин таверны", "block_path", True) is True
        assert self._gate("Хозяин таверны", "ambush", True) is True

    def test_peaceful_role_without_pass_stays_blocked(self):
        # Без территории — как до PROTECT: мирные роли не перехватывают
        assert self._gate("Хозяин таверны", "block_path", False) is False
        assert self._gate("Хозяин таверны", "ambush", False) is False

    def test_combat_role_without_pass_allowed(self):
        assert self._gate("Стражник города", "block_path", False) is True

    def test_empty_role_not_blocked(self):
        # «пустая роль = не блокируем» — существующая семантика сохранена
        assert self._gate("", "block_path", False) is True
import sys
import tempfile
import unittest
from pathlib import Path

# Windows/VSCode-friendly import bootstrap:
# allows running this file directly without setting PYTHONPATH.
CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.world_sim_agent import WorldSimulationAgent
from app.services.combat_service import CombatService
from app.services.knowledge_ingest import KnowledgeIngestService
from app.services.memory import JsonMemoryStore, LayeredMemory
from app.services.system_requirements import RequirementReport, SystemRequirements
from app.services.world_scheduler import WorldScheduler

try:
    from app.services.readiness import ReadinessService
except ModuleNotFoundError:
    ReadinessService = None

try:
    from app.models.schemas import CharacterSheet
    from app.services.character_service import CharacterService
except ModuleNotFoundError:
    CharacterSheet = None
    CharacterService = None


class MemoryTests(unittest.TestCase):
    def test_layered_memory_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(tmp)
            layers = LayeredMemory(store)

            layers.write_world_canon("w1", {"lore": "test"})
            layers.write_campaign_memory("c1", {"event": "quest done"})
            layers.write_session_memory("c1", {"location": "inn"})

            ctx = layers.build_context("w1", "c1")
            self.assertEqual(ctx["world_canon"][0]["lore"], "test")
            self.assertEqual(ctx["campaign_memory"][0]["event"], "quest done")
            self.assertEqual(ctx["session_memory"][0]["location"], "inn")

    def test_recent_cache_invalidation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(tmp)
            store.append("campaign_memory_c1", {"n": 1})
            first = store.recent("campaign_memory_c1", limit=5)
            self.assertEqual(len(first), 1)
            store.append("campaign_memory_c1", {"n": 2})
            second = store.recent("campaign_memory_c1", limit=5)
            self.assertEqual(len(second), 2)


class RequirementsTests(unittest.TestCase):
    def test_check_returns_report(self) -> None:
        req = SystemRequirements(min_physical_cores=1, min_ram_gb=1)
        result = req.check()
        self.assertIsInstance(result, RequirementReport)
        self.assertIn("cpu_model", result.details)
        self.assertIn("detector", result.details)


class WorldSchedulerTests(unittest.TestCase):
    def test_tick_interval_respected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            layers = LayeredMemory(JsonMemoryStore(tmp))
            scheduler = WorldScheduler(layers, WorldSimulationAgent())
            first = scheduler.maybe_tick("w1", every_minutes=15)
            second = scheduler.maybe_tick("w1", every_minutes=15)
            self.assertTrue(first["triggered"])
            self.assertFalse(second["triggered"])


class CombatServiceTests(unittest.TestCase):
    def test_start_attack_and_next_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = CombatService(root=tmp)
            state = service.start(
                "c1",
                "fight-1",
                [
                    {"name": "Aria", "initiative": 16, "hp": 18, "ac": 14},
                    {"name": "Goblin", "initiative": 12, "hp": 10, "ac": 13},
                ],
            )
            self.assertEqual(state.order[0]["name"], "Aria")
            attacked = service.resolve_attack("c1", "fight-1", "Aria", "Goblin", 15, 5, 13, 6)
            goblin = [p for p in attacked.participants if p["name"] == "Goblin"][0]
            self.assertEqual(goblin["hp"], 4)
            turned = service.next_turn("c1", "fight-1")
            self.assertEqual(turned.turn_index, 1)


class KnowledgeIngestTests(unittest.TestCase):
    def test_ingest_txt_to_world(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            layers = LayeredMemory(JsonMemoryStore(tmp))
            svc = KnowledgeIngestService(layers)
            result = svc.ingest(
                world_id="w1",
                campaign_id="c1",
                kind="world",
                filename="lore.txt",
                raw="Древний город на холме".encode("utf-8"),
            )
            self.assertGreater(result.extracted_chars, 0)
            ctx = layers.build_context("w1", "c1")
            self.assertTrue(ctx["world_canon"])


@unittest.skipIf(ReadinessService is None, "pydantic dependency is unavailable in environment")
class ReadinessTests(unittest.TestCase):
    def test_readiness_report_structure(self) -> None:
        report = ReadinessService().report()
        self.assertGreaterEqual(len(report.checks), 5)
        self.assertIsInstance(report.score_percent, float)
        self.assertTrue(any(item.status in {"missing", "partial", "done"} for item in report.checks))


@unittest.skipIf(CharacterService is None or CharacterSheet is None, "pydantic dependency is unavailable in environment")
class CharacterServiceTests(unittest.TestCase):
    def test_upsert_and_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = CharacterService(root=tmp)
            service.upsert_character(
                "c1",
                CharacterSheet(
                    name="Aria",
                    race="Elf",
                    class_name="Rogue",
                    level=3,
                    stats={"dex": 16},
                ),
            )
            chars = service.list_characters("c1")
            self.assertEqual(len(chars), 1)
            self.assertEqual(chars[0].name, "Aria")


if __name__ == "__main__":
    unittest.main()

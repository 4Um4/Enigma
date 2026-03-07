import os
import tempfile
import unittest
from pathlib import Path

from app.agents.dm_agent import DmAgent
from app.agents.rules_agent import RulesAgent
from app.agents.world_sim_agent import WorldSimulationAgent
from app.models.schemas import PlayerAction
from app.models.schemas import ModelProvider, ModelSelection
from app.services.memory import JsonMemoryStore, LayeredMemory
from app.services.system_requirements import RequirementReport, SystemRequirements
from app.services.world_scheduler import WorldScheduler
from app.services.knowledge_ingest import KnowledgeIngestService
from app.services.combat_service import CombatService
from app.services.orchestrator import GameOrchestrator
from app.services.llama_cpp import LlamaCppAdapter
from app.services.llm_manager import LlmManager

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






class RulesAgentTests(unittest.TestCase):
    def test_requires_physical_d20_if_result_is_missing(self) -> None:
        agent = RulesAgent()
        result = agent.evaluate_actions([
            PlayerAction(player_name="Aria", action="Осмотреть зал", dice_result=None)
        ])
        self.assertEqual(result["checks"][0]["instruction"], "Сделайте бросок d20")


class OrchestratorSessionStateTests(unittest.TestCase):
    def test_resolves_world_from_campaign_memory_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GameOrchestrator(data_dir=tmp)
            orchestrator.layered_memory.write_campaign_memory(
                "c1",
                {"event": "campaign_loaded", "world_id": "w-history", "status": "loaded", "loaded_files": []},
            )
            state = orchestrator.session_state("c1")
            self.assertEqual(state.world_id, "w-history")

class DmAgentTests(unittest.TestCase):
    def test_requires_canon_clarification_when_missing(self) -> None:
        agent = DmAgent()
        result = agent.narrate(
            location="Таверна",
            actions=[],
            rules_result={"checks": []},
            npc_result={"npc_reactions": []},
            world_result={"world_events": []},
            world_canon_exists=False,
        )
        self.assertIn("Канон мира ещё не загружен", result["dm_response"])
        self.assertIn("отложена", result["world_changes"][0])


class LlamaCppIntegrationTests(unittest.TestCase):
    def test_llama_cpp_run_with_local_binary_and_model(self) -> None:
        adapter = LlamaCppAdapter()
        model_env = Path((os.environ.get("LLAMA_TEST_MODEL") or "")).expanduser()

        if not (model_env and model_env.exists()):
            self.skipTest("LLAMA_TEST_MODEL is not configured or does not exist")

        try:
            adapter.resolve_executable()
        except RuntimeError:
            self.skipTest("llama.cpp executable is not available in PATH/LLAMA_CPP_EXECUTABLE")

        manager = LlmManager()
        manager.switch_model(
            ModelSelection(
                provider=ModelProvider.llama_cpp,
                model_name=model_env.name,
            )
        )
        output = manager.run("Здравствуй")
        self.assertIsInstance(output, str)
        self.assertTrue(output.strip())

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

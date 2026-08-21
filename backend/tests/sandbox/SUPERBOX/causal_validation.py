"""
ENIGMA Causal Validation — Проверка каузальной цепи L1/L2/L3 и физики.
Весь вывод пишется в causal_validation.log в корне проекта.
Запуск:
  cd backend
  python -m tests.sandbox.SUPERBOX.run causal
"""
import asyncio
import sys
import os
import shutil
import tempfile
import traceback
import logging
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.services.game_loop_builder import build_game_loop
from app.models.schemas import ChatTurnRequest, PlayerAction, ModelSelection, ModelProvider
from app.core.config import settings

# Путь к логу в корне проекта (Enigma/)
LOG_FILE = str(Path(__file__).resolve().parents[4] / "causal_validation.log")

class CausalValidator:
    def __init__(self):
        self.game_loop = None
        self.temp_dir = None
        self.passed = 0
        self.failed = 0
        self.log_buffer = []

    def log(self, msg: str):
        self.log_buffer.append(msg)

    def setup(self):
        self.temp_dir = tempfile.mkdtemp(prefix="causal_val_")
        temp_path = Path(self.temp_dir)
        _project_root = Path(__file__).resolve().parents[3]
        campaign_id = "Open_road"
        
        data_src = _project_root / "frontend" / "map_editor" / "campaigns" / campaign_id
        data_dst = temp_path / "data" / campaign_id
        if data_src.exists():
            data_dst.mkdir(parents=True, exist_ok=True)
            for loc_dir in data_src.iterdir():
                if loc_dir.is_dir():
                    dst_loc = data_dst / "locations" / loc_dir.name
                    dst_loc.mkdir(parents=True, exist_ok=True)
                    for f in loc_dir.iterdir():
                        if f.is_file(): shutil.copy2(f, dst_loc / f.name)

        npc_src = _project_root / "backend" / "data" / "campaigns" / campaign_id
        npc_dst = temp_path / "campaigns" / campaign_id
        if npc_src.exists():
            npc_dst.mkdir(parents=True, exist_ok=True)
            for f in npc_src.iterdir():
                if f.is_file(): shutil.copy2(f, npc_dst / f.name)

        saves_src = _project_root / "saves"
        saves_dst = temp_path / "saves"
        if saves_src.exists(): shutil.copytree(saves_src, saves_dst, dirs_exist_ok=True)

        settings.saves_dir = str(saves_dst)
        self.game_loop = build_game_loop(data_dir=temp_path / "data")

    def teardown(self):
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def get_trace(self, npc_id: str):
        return self.game_loop._tick_orch.l1_chronicle.query_raw(npc_id)

    def assert_event_chain(self, trace, required_types: list[str]):
        for t in required_types:
            assert any(t in e.event_type for e in trace), f"Missing event: {t}"

    def get_npc(self, npc_id: str) -> dict:
        npcs = self.game_loop._resolve_npcs_snapshot("Open_road")
        for n in npcs:
            if n.get("npc_id") == npc_id:
                return n
        return {}

    def print_npc_state(self, npc_id: str, label: str = ""):
        npc = self.get_npc(npc_id)
        if not npc: return
        bs = npc.get("body_state", {})
        pk = npc.get("perceptual_kernel", {})
        psy = npc.get("psyche", {})
        self.log(f"  [{label}] {npc_id}: HP={bs.get('current_hp', '?')}, Threat={pk.get('threat_gradient', 0):.2f}, "
              f"AffLoad={npc.get('affective_load', 0):.2f}, Will={psy.get('state', '?')}, Integ={psy.get('identity_integrity', 1.0):.2f}")

    async def run_action(self, action_text: str):
        self.log(f"\n> Игрок: {action_text}")
        req = ChatTurnRequest(
            world_id="manual", campaign_id="Open_road", location="tavern_silver_wolf",
            model=ModelSelection(provider=ModelProvider.llama_cpp, model_name="fallback", endpoint=settings.llama_cpp_server_url),
            actions=[PlayerAction(player_name="Tester", action=action_text)],
            player_position=(0.0, 0.0),
        )
        try:
            result = await self.game_loop.run_turn(req)
            if result and hasattr(result, 'dm_response'):
                self.log(f"  [DM]: {result.dm_response}")
            return result
        except Exception as e:
            self.log(f"  [ACTION CRASH]: {e}")
            return None

    def run_idle_ticks(self, count: int, silent: bool = False):
        if not silent: self.log(f"  ...ожидание {count} тиков...")
        for _ in range(count):
            self.game_loop.idle_tick("Open_road")

    async def test_command(self):
        self.log("\n[1] COMMAND TEST")
        self.print_npc_state("maid_lusya", "BEFORE")
        await self.run_action("Люся, подойди ко мне")
        self.run_idle_ticks(15, silent=True)
        self.print_npc_state("maid_lusya", "AFTER")
        
        npc_after = self.get_npc("maid_lusya")
        pk = npc_after.get("perceptual_kernel", {})
        
        assert pk.get("compliance_bias", 0.0) > 0.0 or pk.get("recent_directive") is not None, "No compliance"
        
        trace = self.get_trace("maid_lusya")
        self.assert_event_chain(trace, ["directive", "memory"])

    async def test_combat(self):
        self.log("\n[2] COMBAT TEST")
        self.print_npc_state("tavern_keeper_tornin", "BEFORE")
        await self.run_action("атаковать трактирщика")
        self.run_idle_ticks(2, silent=True)
        self.print_npc_state("tavern_keeper_tornin", "AFTER")
        
        npc_after = self.get_npc("tavern_keeper_tornin")
        bs = npc_after.get("body_state", {})
        pk = npc_after.get("perceptual_kernel", {})
        
        assert len(bs.get("injuries", [])) > 0 or len(npc_after.get("wounds", [])) > 0, "No wounds"
        assert pk.get("threat_gradient", 0.0) > 0.0, "No threat"
        assert npc_after.get("affective_load", 0.0) > 0.0, "No affect"
        
        # L1Chronicle хранит только события идентичности (will, pressure).
        # Боёвка проверяется через body_state (HP, wounds).
        trace = self.get_trace("tavern_keeper_tornin")
        assert len(trace) > 0, "Empty L1 trace"

    async def test_recovery(self):
        self.log("\n[3] RECOVERY TEST")
        self.print_npc_state("tavern_keeper_tornin", "BEFORE")
        self.run_idle_ticks(100, silent=True)
        self.print_npc_state("tavern_keeper_tornin", "AFTER")
        
        npc_after = self.get_npc("tavern_keeper_tornin")
        pk = npc_after.get("perceptual_kernel", {})
        
        assert pk.get("threat_gradient", 0.0) < 0.1, "Threat not decayed"
        assert len(npc_after.get("body_state", {}).get("injuries", [])) > 0, "Wounds not persisted"
        
        # L1Chronicle не хранит physiology decay. Проверяем только затухание threat.
        trace = self.get_trace("tavern_keeper_tornin")
        assert len(trace) > 0, "Empty L1 trace"

    async def test_social(self):
        self.log("\n[4] SOCIAL TEST")
        await self.run_action("отдать деньги стражнику")
        self.run_idle_ticks(5, silent=True)
        
        rel_store = self.game_loop.memory_manager._relationships
        rels = rel_store.get_all("Open_road")
        borko_rels = rels.get("guard_borko", {}).get("player", {})
        
        assert borko_rels.get("trust", 0.0) > 0.0, f"Trust not increased ({borko_rels.get('trust', 0.0)})"
        
        trace = self.get_trace("guard_borko")
        self.assert_event_chain(trace, ["dialogue", "trust", "memory"])

    async def test_love(self):
        self.log("\n[5] LOVE TEST")
        for _ in range(3):
            await self.run_action("сделать комплимент трактирщику")
            self.run_idle_ticks(5, silent=True)
            
        rels = self.game_loop.memory_manager._relationships.get_all("Open_road").get("tavern_keeper_tornin", {}).get("player", {})
        assert rels.get("attraction", 0.0) > 0.0 or rels.get("trust", 0.0) > 10.0, "No attraction/trust"
        
        trace = self.get_trace("tavern_keeper_tornin")
        self.assert_event_chain(trace, ["dialogue", "affection", "behavior_mask"])

    async def test_trade(self):
        self.log("\n[6] TRADE TEST")
        avatar_before = self.game_loop.avatar_service.load_state("Open_road", "Tester")
        money_before = avatar_before.body_state.get("money", 0) if avatar_before else 0
        self.log(f"  [BEFORE] Money: {money_before}")
        
        await self.run_action("купить кружку эля")
        self.run_idle_ticks(2, silent=True)
        
        avatar_after = self.game_loop.avatar_service.load_state("Open_road", "Tester")
        money_after = avatar_after.body_state.get("money", 0) if avatar_after else 0
        self.log(f"  [AFTER] Money: {money_after}")
        
        assert money_after < money_before, f"Money not decreased"

    async def test_time_skip(self):
        self.log("\n[7] TIME SKIP TEST")
        self.run_idle_ticks(3000, silent=True)
        self.print_npc_state("tavern_keeper_tornin", "AFTER 30 DAYS")
        
        npc_after = self.get_npc("tavern_keeper_tornin")
        pk = npc_after.get("perceptual_kernel", {})
        
        assert pk.get("threat_gradient", 0.0) <= 0.01, "Threat not fully decayed"
        
        # L1Chronicle не хранит decay/wounds. Проверяем только затухание threat.
        trace = self.get_trace("tavern_keeper_tornin")
        assert len(trace) > 0, "Empty L1 trace"

    async def test_break(self):
        self.log("\n[8] BREAK TEST")
        for i in range(10):
            await self.run_action(f"угрожать трактирщику ножом (попытка {i+1})")
            self.run_idle_ticks(2, silent=True)
            self.print_npc_state("tavern_keeper_tornin", f"STEP {i+1}")
            
        npc = self.get_npc("tavern_keeper_tornin")
        psy = npc.get("psyche", {})
        
        assert psy.get("identity_integrity", 1.0) < 1.0 or psy.get("state") in ["STRAIN", "BROKEN"], "Will not degraded"
        
        trace = self.get_trace("tavern_keeper_tornin")
        self.assert_event_chain(trace, ["pressure", "will", "identity"])

    async def test_l1_persistence(self):
        self.log("\n[9] L1 PERSISTENCE TEST")
        chronicle = self.game_loop._tick_orch.l1_chronicle
        events_before = chronicle.query_raw("tavern_keeper_tornin")
        self.log(f"  [BEFORE RESTART] Events: {len(events_before)}")
        
        temp_path = Path(self.temp_dir)
        self.game_loop = build_game_loop(data_dir=temp_path / "data")
        
        # ADR-L1-PERSIST: Триггерим загрузку из SQLite
        chronicle_new = self.game_loop._tick_orch.l1_chronicle
        chronicle_new.bind_campaign("Open_road")
        
        events_after = chronicle_new.query_raw("tavern_keeper_tornin")
        self.log(f"  [AFTER RESTART] Events: {len(events_after)}")
        
        assert len(events_after) == len(events_before), f"L1 lost"

    async def test_double_truth(self):
        self.log("\n[10] DOUBLE TRUTH TEST")
        npc = self.get_npc("tavern_keeper_tornin")
        
        hp_legacy = npc.get("hp", 0)
        hp_canon = npc.get("body_state", {}).get("current_hp", 0)
        self.log(f"  HP: legacy={hp_legacy}, canon={hp_canon}")
        assert hp_legacy == hp_canon, "HP double truth"
        
        drives = npc.get("drives", {})
        if drives:
            total = sum(float(v) for v in drives.values() if isinstance(v, (int, float)))
            self.log(f"  Drives sum: {total}")
            assert abs(total - 1.0) < 0.01, "Drives sum != 1.0"

    async def run_all(self):
        print("="*60)
        print("CAUSAL VALIDATION SUITE")
        print("="*60)
        
        # Оставляем логирование и print включёнными, чтобы видеть внутренние ошибки
        # logging.disable(logging.CRITICAL)
        # _real_stdout = sys.stdout
        # sys.stdout = io.StringIO()
        _real_stdout = sys.stdout

        test_methods = [
            ("COMMAND", self.test_command), ("COMBAT", self.test_combat),
            ("RECOVERY", self.test_recovery), ("SOCIAL", self.test_social),
            ("LOVE", self.test_love), ("TRADE", self.test_trade),
            ("TIME SKIP", self.test_time_skip), ("BREAK", self.test_break),
            ("L1 PERSISTENCE", self.test_l1_persistence), ("DOUBLE TRUTH", self.test_double_truth)
        ]

        try:
            self.setup()
            
            for name, test in test_methods:
                # sys.stdout = io.StringIO() # чистим буфер перед тестом
                try:
                    await test()
                    _real_stdout.write(f"[PASS] {name}\n")
                    self.log(f"[PASS] {name}")
                    self.passed += 1
                except AssertionError as ae:
                    _real_stdout.write(f"[FAIL] {name}: {ae}\n")
                    self.log(f"[FAIL] {name}: {ae}")
                    self.failed += 1
                except Exception as te:
                    _real_stdout.write(f"[ERR ] {name}: {type(te).__name__}: {te}\n")
                    self.log(f"[ERR ] {name}: {type(te).__name__}: {te}")
                    self.failed += 1
            
            # sys.stdout = io.StringIO()
            self.log("\n[CAUSAL INTEGRITY CHECK]")
            for npc_id in ["tavern_keeper_tornin", "guard_borko"]:
                trace = self.get_trace(npc_id)
                assert len(trace) > 0, "Empty causal history"
                assert any(e.tick_id for e in trace), "Missing temporal axis"
                _real_stdout.write(f"[PASS] INTEGRITY: {npc_id}\n")
                self.log(f"[PASS] INTEGRITY: {npc_id}")
                self.passed += 1
                
        except Exception as e:
            _real_stdout.write(f"[FATAL] {e}\n")
            self.log(f"[FATAL] {e}")
            self.failed += 1
        finally:
            # sys.stdout = _real_stdout
            self.teardown()

        # Save log
        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(self.log_buffer))
            _real_stdout.write(f"\nDetailed log saved to: {LOG_FILE}\n")
        except Exception as e:
            _real_stdout.write(f"\nFailed to save log: {e}\n")
        
        print("\n" + "="*60)
        print(f"RESULT: {self.passed} passed, {self.failed} failed")
        print("="*60)
        return self.failed == 0

if __name__ == "__main__":
    try:
        validator = CausalValidator()
        success = asyncio.run(validator.run_all())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        sys.exit(130)
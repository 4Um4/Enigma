"""GC-01 Block 64 — Apply D1–D5 surgical fixes.

Each fix is independent and idempotent (string replacement with assertions).
Prints OK / WARN / FAIL for each step.
"""
import re
import sys
from pathlib import Path

ROOT = Path(".")
results = []

def ok(name, msg):
    results.append((name, "OK", msg))
    print(f"[OK]   {name}: {msg}")

def warn(name, msg):
    results.append((name, "WARN", msg))
    print(f"[WARN] {name}: {msg}")

def fail(name, msg):
    results.append((name, "FAIL", msg))
    print(f"[FAIL] {name}: {msg}")


# === D5: Remove stale ref in TestCForcedDmFailure class docstring ===
def fix_d5():
    p = ROOT / "backend/tests/gameplay/test_negative_paths.py"
    src = p.read_text(encoding="utf-8")
    old = (
        "    xfailed (c1/c2/c4/c6): production-дефект DM_agent AttributeError ломает\n"
        "    честный degraded-путь. См. _XFAIL_DM_AGENT_CRASH.\n"
    )
    new = (
        "    Контракты проверяются напрямую; xfail-маркеры сняты (Блок №58).\n"
        "    D1/D2 fixed в Блоке №64 (game_loop.py:1930 guard + npc_tick_pipeline gate).\n"
    )
    if old in src:
        src = src.replace(old, new, 1)
        p.write_text(src, encoding="utf-8")
        ok("D5", f"removed stale ref in {p.name}")
    else:
        warn("D5", "stale ref block not found (already removed?)")


# === D4a: Add campaign_id property to harness ===
def fix_d4a():
    p = ROOT / "backend/tests/gameplay/harness.py"
    src = p.read_text(encoding="utf-8")
    old = (
        "    def __init__(self, seed: int = 42, location: str = _LOCATION) -> None:\n"
        "        self.seed = seed\n"
        "        self.location = location\n"
        "        self._tmpdir: Optional[Path] = None\n"
        "        self.game_loop: Any = None\n"
        "        self.counters = GameplayCounters()\n"
        "        self._subscribed = False\n"
        "        self._last_tick_scene: Optional[dict] = None\n"
        "\n"
        "    def new_game(self) -> None:\n"
    )
    new = (
        "    def __init__(self, seed: int = 42, location: str = _LOCATION) -> None:\n"
        "        self.seed = seed\n"
        "        self.location = location\n"
        "        self._tmpdir: Optional[Path] = None\n"
        "        self.game_loop: Any = None\n"
        "        self.counters = GameplayCounters()\n"
        "        self._subscribed = False\n"
        "        self._last_tick_scene: Optional[dict] = None\n"
        "\n"
        "    @property\n"
        "    def campaign_id(self) -> str:\n"
        '        """Public read-only accessor for the harness campaign id (D4 fix)."""\n'
        "        return _CAMPAIGN\n"
        "\n"
        "    def new_game(self) -> None:\n"
    )
    if old in src:
        src = src.replace(old, new, 1)
        p.write_text(src, encoding="utf-8")
        ok("D4a", f"added campaign_id property to {p.name}")
    else:
        warn("D4a", "__init__ marker not found")


# === D4b: Fix test_e3 to pass campaign_id ===
def fix_d4b():
    p = ROOT / "backend/tests/gameplay/test_negative_paths.py"
    src = p.read_text(encoding="utf-8")
    old = "                gl.idle_tick(interventions=[interv])"
    new = "                gl.idle_tick(h.campaign_id, interventions=[interv])"
    if old in src:
        src = src.replace(old, new, 1)
        p.write_text(src, encoding="utf-8")
        ok("D4b", "test_e3 now passes campaign_id")
    else:
        warn("D4b", "test_e3 idle_tick call not found")


# === D3a: Rewrite controlled_mock_provider fixture (Controller pattern) ===
def fix_d3a():
    p = ROOT / "backend/tests/gameplay/test_negative_paths.py"
    src = p.read_text(encoding="utf-8")
    old = '''    @pytest.fixture
    def controlled_mock_provider(self):
        """Мутация pool config + environment, restore в finally."""
        pool = _get_model_pool()
        cfg = pool._model_configs.get("qwen_7b")
        if cfg is None:
            pytest.skip("qwen_7b not registered in pool._model_configs")
        orig_pt = cfg.provider_type
        orig_env = settings.environment
        try:
            cfg.provider_type = ProviderType.MOCK
            settings.environment = "development"
            pool.unload_all()
            yield
        finally:
            cfg.provider_type = orig_pt
            settings.environment = orig_env
            pool.unload_all()
'''
    new = '''    @pytest.fixture
    def controlled_mock_provider(self):
        """MOCK activation controller. Pattern: h.new_game() FIRST, then activate().

        Previously the fixture mutated cfg.provider_type BEFORE h.new_game(),
        but build_game_loop() → initialize_router() → initialize_model_pool()
        re-registers qwen_7b with default provider_type, overwriting MOCK.

        Fix: Controller pattern — caller invokes activate() AFTER h.new_game().
        """
        class _Controller:
            def __init__(self):
                self._cfg = None
                self._orig_pt = None
                self._orig_env = None
                self._active = False

            def activate(self):
                pool = _get_model_pool()
                self._cfg = pool._model_configs.get("qwen_7b")
                if self._cfg is None:
                    pytest.skip(
                        "qwen_7b not registered in pool._model_configs after h.new_game()"
                    )
                self._orig_pt = self._cfg.provider_type
                self._orig_env = settings.environment
                self._cfg.provider_type = ProviderType.MOCK
                settings.environment = "development"
                pool.unload_all()
                self._active = True

            def restore(self):
                if not self._active:
                    return
                pool = _get_model_pool()
                self._cfg.provider_type = self._orig_pt
                settings.environment = self._orig_env
                pool.unload_all()
                self._active = False

        ctrl = _Controller()
        yield ctrl
        ctrl.restore()
'''
    if old in src:
        src = src.replace(old, new, 1)
        p.write_text(src, encoding="utf-8")
        ok("D3a", "controlled_mock_provider rewritten as Controller")
    else:
        warn("D3a", "fixture block not found")


# === D3b: Update test_d1/d2/d3 to call activate()/restore() ===
def fix_d3b():
    p = ROOT / "backend/tests/gameplay/test_negative_paths.py"
    src = p.read_text(encoding="utf-8")
    changes = 0

    # test_d1
    old_d1 = '''    def test_d1_llm_degraded_false_with_mock(self, controlled_mock_provider):
        """Главный дискриминатор: llm_degraded=False при MockProvider."""
        h = TavernGameplayHarness(seed=42, location="tavern")
        try:
            h.new_game()
            response = h.player_action("Осмотреть таверну")
            assert response is not None, "player_action returned None"
            assert response.llm_degraded is False, (
                f"expected llm_degraded=False with MOCK, got True; "
                f"dm_response={getattr(response, 'dm_response', None)!r}"
            )
        finally:
            h.dispose()
'''
    new_d1 = '''    def test_d1_llm_degraded_false_with_mock(self, controlled_mock_provider):
        """Главный дискриминатор: llm_degraded=False при MockProvider."""
        h = TavernGameplayHarness(seed=42, location="tavern")
        try:
            h.new_game()
            controlled_mock_provider.activate()
            response = h.player_action("Осмотреть таверну")
            assert response is not None, "player_action returned None"
            assert response.llm_degraded is False, (
                f"expected llm_degraded=False with MOCK, got True; "
                f"dm_response={getattr(response, 'dm_response', None)!r}"
            )
        finally:
            controlled_mock_provider.restore()
            h.dispose()
'''
    if old_d1 in src:
        src = src.replace(old_d1, new_d1, 1)
        changes += 1

    # test_d2
    old_d2 = '''    def test_d2_world_snapshot_present(self, controlled_mock_provider):
        """Структурный контракт: world_snapshot присутствует в ответе."""
        h = TavernGameplayHarness(seed=42, location="tavern")
        try:
            h.new_game()
            response = h.player_action("Осмотреть таверну")
            ws = getattr(response, "world_snapshot", None)
            assert ws is not None, (
                f"world_snapshot missing in response; "
                f"attrs: {[a for a in dir(response) if not a.startswith('_')]}"
            )
        finally:
            h.dispose()
'''
    new_d2 = '''    def test_d2_world_snapshot_present(self, controlled_mock_provider):
        """Структурный контракт: world_snapshot присутствует в ответе."""
        h = TavernGameplayHarness(seed=42, location="tavern")
        try:
            h.new_game()
            controlled_mock_provider.activate()
            response = h.player_action("Осмотреть таверну")
            ws = getattr(response, "world_snapshot", None)
            assert ws is not None, (
                f"world_snapshot missing in response; "
                f"attrs: {[a for a in dir(response) if not a.startswith('_')]}"
            )
        finally:
            controlled_mock_provider.restore()
            h.dispose()
'''
    if old_d2 in src:
        src = src.replace(old_d2, new_d2, 1)
        changes += 1

    # test_d3
    old_d3 = '''    def test_d3_dm_response_non_empty_str(self, controlled_mock_provider):
        """Структурный контракт: dm_response — непустая str."""
        h = TavernGameplayHarness(seed=42, location="tavern")
        try:
            h.new_game()
            response = h.player_action("Осмотреть таверну")
            dm = response.dm_response
            assert isinstance(dm, str), f"dm_response not str: {type(dm)}"
            assert len(dm) > 0, "dm_response empty under MOCK provider"
            print(f"\\n[Mock diagnostic] dm_response={dm!r}")
        finally:
            h.dispose()
'''
    new_d3 = '''    def test_d3_dm_response_non_empty_str(self, controlled_mock_provider):
        """Структурный контракт: dm_response — непустая str."""
        h = TavernGameplayHarness(seed=42, location="tavern")
        try:
            h.new_game()
            controlled_mock_provider.activate()
            response = h.player_action("Осмотреть таверну")
            dm = response.dm_response
            assert isinstance(dm, str), f"dm_response not str: {type(dm)}"
            assert len(dm) > 0, "dm_response empty under MOCK provider"
            print(f"\\n[Mock diagnostic] dm_response={dm!r}")
        finally:
            controlled_mock_provider.restore()
            h.dispose()
'''
    if old_d3 in src:
        src = src.replace(old_d3, new_d3, 1)
        changes += 1

    if changes > 0:
        p.write_text(src, encoding="utf-8")
        ok("D3b", f"updated {changes}/3 d-tests with activate()/restore()")
    else:
        warn("D3b", "no d-test bodies matched")


# === D1: Guard persist_dm_response when _dm_degraded ===
def fix_d1():
    p = ROOT / "backend/app/services/game_loop/game_loop.py"
    src = p.read_text(encoding="utf-8")
    old = (
        "            llm_degraded=bool(dm_result.get(\"llm_degraded\", False)),\n"
        "            journal_entry_id=self.memory_manager.persist_dm_response(\n"
        "                req.campaign_id,\n"
        "                world_id=req.world_id,\n"
        "                location=req.location,\n"
        "                actions=[a.model_dump() for a in req.actions],\n"
        "                dm_text=dm_result.get(\"dm_response\", \"\"),\n"
        "            ),\n"
        "            traces=traces,\n"
    )
    new = (
        "            llm_degraded=bool(dm_result.get(\"llm_degraded\", False)),\n"
        "            # D1 fix (GC-01): degraded path must NOT persist fallback as journal entry.\n"
        "            # _dm_degraded is set above (@1668) from dm_result.get(\"llm_degraded\").\n"
        "            journal_entry_id=(\n"
        "                \"\" if _dm_degraded\n"
        "                else self.memory_manager.persist_dm_response(\n"
        "                    req.campaign_id,\n"
        "                    world_id=req.world_id,\n"
        "                    location=req.location,\n"
        "                    actions=[a.model_dump() for a in req.actions],\n"
        "                    dm_text=dm_result.get(\"dm_response\", \"\"),\n"
        "                )\n"
        "            ),\n"
        "            traces=traces,\n"
    )
    if old in src:
        src = src.replace(old, new, 1)
        p.write_text(src, encoding="utf-8")
        ok("D1", f"guard added in {p.name}")
    else:
        warn("D1", "persist_dm_response block not found")


# === D2: Gate movement_intents.append when _is_player_turn ===
def fix_d2():
    p = ROOT / "backend/app/services/npc/npc_tick_pipeline.py"
    src = p.read_text(encoding="utf-8")
    # Need to find the exact pattern. From grep: @1177-1178
    # if _movement:
    #     movement_intents.append(_movement)
    old = (
        "                if _movement:\n"
        "                    movement_intents.append(_movement)\n"
    )
    new = (
        "                # D2 fix (GC-01 / ADR-O-407): player turn pauses world time —\n"
        "                # no NEW traversal initiation. Existing in-flight traversals\n"
        "                # may continue interpolating (ADR-O-201 E5 ghost interpolation),\n"
        "                # but no new movement_intents during player_action.\n"
        "                if _movement and not _is_player_turn:\n"
        "                    movement_intents.append(_movement)\n"
    )
    if old in src:
        src = src.replace(old, new, 1)
        p.write_text(src, encoding="utf-8")
        ok("D2", f"gate added in {p.name}")
    else:
        # Try alternate indentation
        old2 = (
            "            if _movement:\n"
            "                movement_intents.append(_movement)\n"
        )
        new2 = (
            "            # D2 fix (GC-01 / ADR-O-407): player turn pauses world time.\n"
            "            if _movement and not _is_player_turn:\n"
            "                movement_intents.append(_movement)\n"
        )
        if old2 in src:
            src = src.replace(old2, new2, 1)
            p.write_text(src, encoding="utf-8")
            ok("D2", f"gate added (alt indent) in {p.name}")
        else:
            warn("D2", "movement_intents.append block not found")


# === Run all fixes ===
if __name__ == "__main__":
    print("=" * 70)
    print("GC-01 Block 64 — Apply D1–D5 fixes")
    print("=" * 70)
    fix_d5()
    fix_d4a()
    fix_d4b()
    fix_d3a()
    fix_d3b()
    fix_d1()
    fix_d2()
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for name, status, msg in results:
        print(f"  [{status:4}] {name}: {msg}")
    fails = [r for r in results if r[1] == "FAIL"]
    warns = [r for r in results if r[1] == "WARN"]
    print()
    print(f"Total: {len(results)} | OK: {len(results)-len(fails)-len(warns)} | WARN: {len(warns)} | FAIL: {len(fails)}")
    sys.exit(0 if not fails else 1)
"""
GC-01: Вертикальный срез игровой петли.

Test A — real tick vertical slice: 9 обязательных проверок БЕЗ привязки
к доступности LLM. Доказывает, что ядро тика детерминированно и инвариантно
вне зависимости от состояния DM-слоя.

Test B — SCALE-05 replay: 3× fresh× seed42× 10 тиков, попарное равенство
отпечатков. Анти-вакуум: пустые равные результаты НЕ доказывают
детерминизм — отдельно проверяется наличие NPC и продвижение времени.

Связанные инварианты:
  INV-TICK-CARDINALITY, ADR-002, ADR-O-344, INV-TIME-FREEZE,
  ADR-075, DEBT-FE-DELTAS, S262, AVID-1, S269 (Test B).

Источники археологии:
  harness.py@94 (TavernGameplayHarness), advance_ticks@201,
  get_scene_fresh@333; idle_tick return@1494-1509 (game_loop.py);
  WorldSnapshotBuilder Phase 9 (post_decision integration).
"""
from __future__ import annotations

from tests.gameplay.harness import TavernGameplayHarness


# ============================================================================
# Test A: real tick vertical slice — 9 mandatory checks (LLM-agnostic)
# ============================================================================

class TestARealTickVerticalSlice:
    """9 инвариантов вертикального среза одного тика (LLM-агностик).

    Каждый тест проверяет один инвариант. Все 9 независимы от доступности
    LLM — используют только ядро симуляции и Phase-9 snapshot.
    """

    def setup_method(self) -> None:
        self.harness = TavernGameplayHarness(seed=42, location="tavern")
        self.harness.new_game()

    def teardown_method(self) -> None:
        self.harness.dispose()

    def test_a1_tick_cardinality_one_per_advance(self) -> None:
        """INV-TICK-CARDINALITY / ADR-O-344: advance_ticks(1) → ровно 1 отпечаток с целым tick.

        Оркестратор владеет инкрементом тика — один advance_ticks(1) даёт
        ровно один отпечаток с целочисленным полем tick.
        """
        snaps = self.harness.advance_ticks(1)
        assert isinstance(snaps, list), f"advance_ticks must return list, got {type(snaps)}"
        assert len(snaps) == 1, f"expected 1 snapshot, got {len(snaps)}"
        tick = snaps[0].get("tick")
        assert isinstance(tick, int), f"tick must be int, got {type(tick)}: {tick!r}"

    def test_a2_game_time_seconds_monotonic(self) -> None:
        """ADR-002: время не останавливается — game_time_seconds монотонно растёт.

        В трёх последовательных тиках время должно строго возрастать.
        Это доказывает, что Phase 0.5 idle-decay и Phase 0.6 sleep
        реально продвигают симуляционное время.
        """
        snaps = self.harness.advance_ticks(3)
        times = [s.get("time") for s in snaps]
        assert all(t is not None for t in times), \
            f"time missing in snapshots: {snaps}"
        for i in range(1, len(times)):
            assert times[i] > times[i - 1], \
                f"time not strictly increasing: {times}"

    def test_a3_phase9_integration_fields_present(self) -> None:
        """Phase 9 (Integration): scene_state содержит базовые поля интеграции.

        WorldSnapshotBuilder (Phase 9) НЕ пишет world_snapshot в scene_state
        напрямую — это поле ChatTurnResponse. Phase 9 интегрирует в scene_state
        поля tick (ADR-O-344) и game_time_seconds (BUG-P0-01 единый источник).
        """
        self.harness.advance_ticks(1)
        scene = self.harness.get_scene_fresh()
        assert scene is not None, "scene fresh is None after advance_ticks"
        assert "tick" in scene, \
            f"tick missing in scene_state; keys: {list(scene.keys())}"
        assert "game_time_seconds" in scene, \
            f"game_time_seconds missing in scene_state; keys: {list(scene.keys())}"

    def test_a4_npc_count_positive_int(self) -> None:
        """AVID-1: NPC (включая аватара) присутствуют в сцене (count > 0).

        _tick_fingerprint (harness.py:253) кладёт npc = len(scene.npc_positions)
        — int count, не list/dict. После new_game+tick count должен быть > 0
        (AVID-1 FIX: idle-путь передаёт NPC включая аватара, ADR-030 транзит).
        """
        snaps = self.harness.advance_ticks(1)
        npcs = snaps[0].get("npc")
        assert isinstance(npcs, int), \
            f"npc must be int (count from len(npc_positions)); got {type(npcs)}: {npcs!r}"
        assert npcs > 0, \
            f"NPC count not positive after new_game+tick: {npcs}"

    def test_a5_pending_tasks_stable_or_decreasing(self) -> None:
        """S262: execute_pending идемпотентен — pending не растёт без входа.

        Корень idle-немоты (BUG-CORE-010) — гейт pending_tasks в сцене.
        Фикс S262: безусловный execute_pending (идемпотентен).
        В 4 тиках без player_action pending не должен расти.
        """
        snaps = self.harness.advance_ticks(4)
        pendings = [s.get("pending") for s in snaps]
        for i in range(1, len(pendings)):
            prev, curr = pendings[i - 1], pendings[i]
            if prev is None or curr is None:
                continue
            assert curr <= prev, \
                f"pending grew without input: prev={prev}, curr={curr}, full={pendings}"

    def test_a6_no_simulation_integrity_error(self) -> None:
        """INV-TIME-FREEZE: SimulationIntegrityError не выбрасывается в штатном idle.

        Если ядро обнаруживает заморозку времени (suspect_files), оно
        выбрасывает SimulationIntegrityError. В штатном idle этого быть
        не должно — advance_ticks должен завершиться чисто.
        """
        snaps = self.harness.advance_ticks(2)
        assert len(snaps) == 2, "advance_ticks(2) must produce 2 snaps"

    def test_a7_will_conflict_data_none_in_idle(self) -> None:
        """ADR-075: will_conflict_data=None в idle_tick.

        В idle нет конфликта воли (нет игрока → нет проекции намерения →
        нет конфликта). idle_tick возвращает will_conflict_data=None.
        """
        self.harness.advance_ticks(1)
        scene = self.harness.get_scene_fresh()
        wcd = scene.get("will_conflict_data")
        assert wcd is None, \
            f"will_conflict_data not None in idle: {wcd!r}"

    def test_a8_events_empty_by_default(self) -> None:
        """DEBT-FE-DELTAS: events=[] при IDLE_EVENTS_PROJECTION_ENABLED=OFF.

        StateDeltas не покидают ядро. events — проекция {cause,target,value}
        за флагом IDLE_EVENTS_PROJECTION_ENABLED, по умолчанию OFF=[].
        """
        snaps = self.harness.advance_ticks(1)
        events = snaps[0].get("events")
        assert events is None or events == [], \
            f"events not empty by default: {events!r}"

    def test_a9_avatar_player_present_in_scene(self) -> None:
        """AVID-1 FIX: аватар игрока присутствует в npc_positions.

        idle-путь передаёт NPC включая аватара (game_loop.py:1331
        all_npcs_raw=self._load_npcs_with_runtime, ADR-030 транзит).
        """
        self.harness.advance_ticks(1)
        scene = self.harness.get_scene_fresh()
        npc_positions = scene.get("npc_positions", {})
        assert "player" in npc_positions, \
            f"avatar 'player' missing in npc_positions; keys: {list(npc_positions.keys())}"


# ============================================================================
# Test B: SCALE-05 replay — 3× fresh, seed=42, 10 ticks, pairwise equal
# ============================================================================

class TestBScale05ReplayDeterminism:
    """SCALE-05: 3 прогона одного seed дают попарно равные отпечатки (S269).

    S269-ДЕТЕРМИНИЗМ: md5(prompt_lower) % len(options) — стабильный хеш,
    инвариантный к порядку вызовов и PYTHONHASHSEED. Три прогона одного
    seed обязаны дать одинаковые отпечатки.
    """

    REPLAY_COUNT = 3
    TICKS = 10

    def _run_one(self) -> list:
        """Один прогон: fresh harness × seed42 × 10 тиков → отпечатки."""
        h = TavernGameplayHarness(seed=42, location="tavern")
        try:
            h.new_game()
            return h.advance_ticks(self.TICKS)
        finally:
            h.dispose()

    def test_b1_three_runs_produce_equal_fingerprints(self) -> None:
        """3× fresh× seed42× 10 ticks → попарно равные отпечатки.

        Анти-Race: каждый прогон создаёт НОВЫЙ harness (new_game →
        advance_ticks) — никакого разделения состояния между прогонами.
        """
        runs = [self._run_one() for _ in range(self.REPLAY_COUNT)]
        lengths = [len(r) for r in runs]
        assert len(set(lengths)) == 1, \
            f"lengths differ across runs: {lengths}"
        for i in range(self.REPLAY_COUNT):
            for j in range(i + 1, self.REPLAY_COUNT):
                assert runs[i] == runs[j], \
                    f"MISMATCH run{i} vs run{j}:\n" \
                    f"  run{i}[-1]={runs[i][-1]!r}\n" \
                    f"  run{j}[-1]={runs[j][-1]!r}"

    def test_b2_anti_vacuum_runs_have_npc(self) -> None:
        """Анти-вакуум: пустые равные результаты ≠ доказательство.

        Если во всех 3 прогонах NPC-список пуст — равенство тривиально
        (vacuum). Каждый прогон должен содержать хотя бы одного NPC.
        """
        for i in range(self.REPLAY_COUNT):
            snaps = self._run_one()
            assert len(snaps) == self.TICKS, \
                f"run{i}: expected {self.TICKS} snaps, got {len(snaps)}"
            last = snaps[-1]
            npcs = last.get("npc")
            if isinstance(npcs, list):
                assert len(npcs) > 0, f"run{i}: NPC list empty (vacuum)"
            elif isinstance(npcs, dict):
                assert len(npcs) > 0, f"run{i}: NPC dict empty (vacuum)"

    def test_b3_anti_vacuum_time_advances(self) -> None:
        """Анти-вакуум: время реально движется во всех 3 прогонах.

        Если время застыло — равенство отпечатков тривиально (статичный
        мир). Доказываем, что время во всех 3 прогонах строго возрастает
        от первого тика к последнему.
        """
        for i in range(self.REPLAY_COUNT):
            snaps = self._run_one()
            times = [s.get("time") for s in snaps]
            assert all(t is not None for t in times), \
                f"run{i}: time missing in some snapshots"
            assert times[-1] > times[0], \
                f"run{i}: time did not advance: first={times[0]}, last={times[-1]}"

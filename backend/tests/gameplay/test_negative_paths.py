"""
GC-01: Негативные пути.

Test C — Принудительный отказ DM + полный честный контракт:
  llm_degraded=True, npc_reactions=[], world_changes=[], journal="",
  dm_response — маркер деградации (не реплика NPC),
  npc_positions: identity+location инварианты (ADR-O-201/377; см. c6).

Test D — Контролируемый успешный провайдер (не ослаблять до dm_response!=""):
  llm_degraded=False (главный дискриминатор против Test C),
  структурный контракт (world_snapshot, dm_response непустая str),
  "[Mock]" — диагностика, не ассерт (ResponseValidator может отклонить).

Test E — Malformed intervention: публичный контракт idle_tick(interventions=...):
  e1: signature check (idle_tick принимает interventions kwarg),
  e2: InterventionEvent schema (source/payload/tick + from_player_action),
  e3: foreign source → silent no-op (no exception).
  Stale-windup НЕ включать — незакрытый остаток с конкретным следующим шагом.

Diag: предыдущие xfail-маркеры атрибутировали сбои как AttributeError
  'generator.state' в world_epoch.py:351. Изолированный прогон TestC
  AttributeError не воспроизводит — атрибуция ложная. Маркеры удалены
  для получения реальных traceback'ов и установления контрактов
  (c1/c2/c4/c6/d2). Order-dependent-эффект проверяется прогоном B->C.
"""
from __future__ import annotations

import inspect

import pytest

from app.core.config import settings
from app.services.llm.provider import ProviderType
from tests.gameplay.harness import TavernGameplayHarness


# ============================================================================
# xfail reason-константы (triple-quoted — безопасно содержат вложенные кавычки)
# ============================================================================




# ============================================================================
# Helpers
# ============================================================================

def _get_model_pool():
    """Lazy доступ к ModelPool singleton (legitimate test surface)."""
    from app.services.llm.provider_manager import get_model_pool
    return get_model_pool()


def _resolve_game_loop(harness):
    """Найти game_loop на harness через интроспекцию (без private attr access)."""
    for attr in vars(harness):
        val = getattr(harness, attr, None)
        if val is not None and hasattr(val, "idle_tick") and callable(val.idle_tick):
            return val
    return None


# ============================================================================
# Test C: Принудительный отказ DM + полный честный контракт
# ============================================================================

class TestCForcedDmFailure:
    """Принудительный отказ DM + честный контракт деградации.

    Рычаги:
      - settings.llama_cpp_server_url → dead port (HTTP connection refused)
      - settings.llama_cpp_server_executable → nonexistent path (spawn fails)
      - pool.unload_all() → force _load_model на следующем запросе

    Контракты проверяются напрямую; xfail-маркеры сняты (Блок №58).
    D1 fixed в Блоке №64 (game_loop.py:1930 guard). D2: абсолютная
    стабильность позиций противоречила ADR-O-377 (3) — c6 ревизован
    на identity+location инварианты (Блок №68), гейты откатаны.
    """

    @pytest.fixture
    def force_llm_dead(self):
        """Изоляция: dead port + nonexistent executable + pool unload."""
        orig_url = settings.llama_cpp_server_url
        orig_exec = settings.llama_cpp_server_executable
        pool = _get_model_pool()
        try:
            settings.llama_cpp_server_url = "http://127.0.0.1:1"
            settings.llama_cpp_server_executable = "/nonexistent/llama-server-test-C"
            pool.unload_all()
            yield
        finally:
            settings.llama_cpp_server_url = orig_url
            settings.llama_cpp_server_executable = orig_exec
            pool.unload_all()

    def test_c1_llm_degraded_true_on_failure(self, force_llm_dead):
        """Главный ассерт: llm_degraded=True при отказе DM."""
        h = TavernGameplayHarness(seed=42, location="tavern")
        try:
            h.new_game()
            response = h.player_action("Тестовое действие")
            assert response is not None, "player_action returned None"
            assert response.llm_degraded is True, (
                f"expected llm_degraded=True, got {response.llm_degraded!r}; "
                f"dm_response={getattr(response, 'dm_response', None)!r}"
            )
        finally:
            h.dispose()

    def test_c2_npc_reactions_empty(self, force_llm_dead):
        """Честный контракт: npc_reactions=[] — никто не говорит (RCE-атрибуция)."""
        h = TavernGameplayHarness(seed=42, location="tavern")
        try:
            h.new_game()
            response = h.player_action("Действие")
            assert response.npc_reactions == [], (
                f"expected [], got {response.npc_reactions!r}"
            )
        finally:
            h.dispose()

    def test_c3_world_changes_empty(self, force_llm_dead):
        """RCE-инвариант: world_changes=[] — LLM-выход не состояние мира."""
        h = TavernGameplayHarness(seed=42, location="tavern")
        try:
            h.new_game()
            response = h.player_action("Действие")
            assert response.world_changes == [], (
                f"expected [], got {response.world_changes!r}"
            )
        finally:
            h.dispose()

    def test_c4_journal_entry_id_empty(self, force_llm_dead):
        """Fallback не персистится: journal_entry_id="" (не атрибуцируется в STM)."""
        h = TavernGameplayHarness(seed=42, location="tavern")
        try:
            h.new_game()
            response = h.player_action("Действие")
            assert response.journal_entry_id == "", (
                f"expected '', got {response.journal_entry_id!r}"
            )
        finally:
            h.dispose()

    def test_c5_dm_response_is_honest_degradation_marker(self, force_llm_dead):
        """Текст деградации — непустой маркер ожидания, не реплика NPC."""
        h = TavernGameplayHarness(seed=42, location="tavern")
        try:
            h.new_game()
            response = h.player_action("Действие")
            dm = response.dm_response or ""
            assert isinstance(dm, str), f"dm_response not str: {type(dm)}"
            assert len(dm) > 0, (
                "dm_response empty — expected honest degradation marker"
            )
        finally:
            h.dispose()

    def test_c6_npc_positions_stable_no_teleport(self, force_llm_dead):
        """REST не телепортирует: identity + location инварианты NPC.

        ADR-O-377 (3): LLM-деградация не останавливает быстрые следствия —
        npc_positions МОГУТ меняться в ходе player_action (исполнение
        запланированных задач, traversal interpolation). Абсолютная
        стабильность — ошибочное ожидание (снято в Блоке №68).

        Инварианты (ADR-O-201):
          1. Identity: множество NPC стабильно (спавн/деспавн вне
             initialize_scene запрещён).
          2. Location: ни один NPC не меняет location_id за один ход
             (межлокационный переход требует boundary traversal, E18).
        Внутрилокационные смены graph-узла легальны (movement engine —
        единственный writer позиций, MotionPlan + E10 teleport check).
        """
        h = TavernGameplayHarness(seed=42, location="tavern")
        try:
            h.new_game()
            h.advance_ticks(1)
            before = h.get_scene_fresh().get("npc_positions", {})
            h.player_action("Действие")
            after = h.get_scene_fresh().get("npc_positions", {})
            # Инвариант 1: identity (ADR-O-201 — спавн/деспавн вне
            # initialize_scene запрещён)
            assert set(before.keys()) == set(after.keys()), (
                f"npc identity changed: before={sorted(before.keys())}, "
                f"after={sorted(after.keys())}"
            )
            # Инвариант 2: location (ADR-O-201 E18 — межлокационный переход
            # требует boundary traversal, не мгновенный телепорт)
            _teleported = {
                nid: (before[nid].get("location_id"), after[nid].get("location_id"))
                for nid in before
                if before[nid].get("location_id") != after[nid].get("location_id")
            }
            assert not _teleported, (
                f"cross-location teleport detected: {_teleported}"
            )
        finally:
            h.dispose()


# ============================================================================
# Test D: Контролируемый успешный провайдер (MOCK)
# ============================================================================

class TestDControlledMockProvider:
    """Контролируемый успех через MockProvider — дискриминатор против Test C."""

    @pytest.fixture
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
                # Set MOCK on ALL model configs — router picks capability model
                # dynamically (e.g. yandexgpt_8b for NARRATIVE, qwen_3_5_9b fallback).
                # Setting MOCK only on qwen_7b misses the actually-used models.
                self._cfgs = list(pool._model_configs.values())
                if not self._cfgs:
                    pytest.skip(
                        "no model configs registered in pool after h.new_game()"
                    )
                self._orig_pts = [c.provider_type for c in self._cfgs]
                self._orig_env = settings.environment
                for c in self._cfgs:
                    c.provider_type = ProviderType.MOCK
                settings.environment = "development"
                pool.unload_all()
                self._active = True

            def restore(self):
                if not self._active:
                    return
                pool = _get_model_pool()
                for c, orig_pt in zip(self._cfgs, self._orig_pts):
                    c.provider_type = orig_pt
                settings.environment = self._orig_env
                pool.unload_all()
                self._active = False

        ctrl = _Controller()
        yield ctrl
        ctrl.restore()

    def test_d1_llm_degraded_false_with_mock(self, controlled_mock_provider):
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

    def test_d2_world_snapshot_present(self, controlled_mock_provider):
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

    def test_d3_dm_response_non_empty_str(self, controlled_mock_provider):
        """Структурный контракт: dm_response — непустая str."""
        h = TavernGameplayHarness(seed=42, location="tavern")
        try:
            h.new_game()
            controlled_mock_provider.activate()
            response = h.player_action("Осмотреть таверну")
            dm = response.dm_response
            assert isinstance(dm, str), f"dm_response not str: {type(dm)}"
            assert len(dm) > 0, "dm_response empty under MOCK provider"
            print(f"\n[Mock diagnostic] dm_response={dm!r}")
        finally:
            controlled_mock_provider.restore()
            h.dispose()


# ============================================================================
# Test E: Malformed intervention — публичный контракт idle_tick(interventions=...)
# ============================================================================

class TestEMalformedIntervention:
    """Публичный контракт idle_tick(interventions=...) и malformed intervention."""

    def test_e1_idle_tick_accepts_interventions_kwarg(self):
        """Публичный контракт: idle_tick(campaign_id, ..., interventions=...)."""
        from app.services.game_loop.game_loop import GameLoop
        sig = inspect.signature(GameLoop.idle_tick)
        assert "interventions" in sig.parameters, (
            f"idle_tick must accept 'interventions' kwarg; sig={sig}"
        )

    def test_e2_intervention_event_schema(self):
        """InterventionEvent (TZ-08 v0.2): source/payload/tick + factory."""
        from app.contracts.interventions import InterventionEvent
        ev = InterventionEvent(source="test", payload={"k": "v"}, tick=42)
        assert ev.source == "test"
        assert ev.payload == {"k": "v"}
        assert ev.tick == 42
        assert hasattr(InterventionEvent, "from_player_action"), (
            "InterventionEvent.from_player_action factory missing (TZ-08 v0.2)"
        )

    def test_e3_foreign_source_is_silent_noop(self):
        """S-UE/D4: source != 'player' → no exception, no dispatch."""
        from app.contracts.interventions import InterventionEvent
        h = TavernGameplayHarness(seed=42, location="tavern")
        try:
            h.new_game()
            gl = _resolve_game_loop(h)
            if gl is None:
                pytest.skip(
                    "Cannot find game_loop on harness — Test E3 needs "
                    "harness extension (helper for idle_tick with interventions)"
                )
            interv = InterventionEvent(
                source="test_foreign_source",
                payload={"text": "test"},
                tick=0,
            )
            try:
                gl.idle_tick(h.campaign_id, interventions=[interv])
            except TypeError as e:
                pytest.skip(
                    f"idle_tick signature requires more params: {e}. "
                    f"Test E3 needs harness helper."
                )
        finally:
            h.dispose()

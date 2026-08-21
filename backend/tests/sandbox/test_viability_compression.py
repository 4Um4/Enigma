# backend/tests/sandbox/test_viability_compression.py
# Назначение: Верификация ДОЛГ 4.3 — Viability Pre-Generation Gate (ADR-O-137)
# Зависимости: pytest, app.services.npc.life_engine, app.domain.movement
# Основные сущности: LifeEngine, IntentDomain, _compute_viability_mask
"""
Назначение:

Запуск: python -m pytest backend/tests/sandbox/test_viability_compression.py -v --tb=short 2>&1 | Select-Object -Last 30


TODO:

"""

import pytest
from unittest.mock import MagicMock, patch
from app.services.npc.life_engine import LifeEngine, MINOR_TICK_INTERVAL
from app.domain.movement import MovementIntent, IntentDomain


# ── Фикстуры ──────────────────────────────────────────────────────────────

@pytest.fixture
def engine():
    le = LifeEngine()
    le._spatial_service = MagicMock()
    return le


@pytest.fixture
def npc_calm():
    """NPC без угрозы — все домены жизнеспособны."""
    return {
        "id": "guard_1",
        "tier": "minor",
        "perceptual_kernel": {"threat_gradient": 0.1, "initiative_suppression": 0.0},
        "position": "barracks",
        "location": "tavern_silver_wolf",
        "routine": {
            "current": "sleep",
            "_last_life_tick": 0,
            "schedule": {"06:00-18:00": "patrol", "18:00-06:00": "sleep"},
        },
    }


@pytest.fixture
def npc_threatened():
    """NPC под угрозой — ROUTINE не жизнеспособен (threat > 0.3)."""
    return {
        "id": "guard_1",
        "tier": "minor",
        "perceptual_kernel": {"threat_gradient": 0.6, "initiative_suppression": 0.0},
        "position": "barracks",
        "location": "tavern_silver_wolf",
        "routine": {
            "current": "sleep",
            "_last_life_tick": 0,
            "schedule": {"06:00-18:00": "patrol", "18:00-06:00": "sleep"},
        },
    }


@pytest.fixture
def npc_paralyzed():
    """NPC с параличом воли — только SURVIVAL жизнеспособен."""
    return {
        "id": "guard_1",
        "tier": "minor",
        "perceptual_kernel": {"threat_gradient": 0.6, "initiative_suppression": 0.8},
        "position": "barracks",
        "location": "tavern_silver_wolf",
        "routine": {
            "current": "sleep",
            "_last_life_tick": 0,
            "schedule": {"06:00-18:00": "patrol", "18:00-06:00": "sleep"},
        },
    }


# ── Тесты Viability Mask ─────────────────────────────────────────────────

class TestComputeViabilityMask:
    """ДОЛГ 4.3: _compute_viability_mask — проекция PerceptualKernel в пространство допустимых действий."""

    def test_calm_npc_all_domains_viable(self, engine, npc_calm):
        """Без угрозы — все 4 домена жизнеспособны."""
        viable = engine._compute_viability_mask(npc_calm)
        assert IntentDomain.SURVIVAL in viable
        assert IntentDomain.SOCIAL in viable
        assert IntentDomain.ROUTINE in viable
        assert IntentDomain.EXPLORATION in viable

    def test_threatened_npc_routine_pruned(self, engine, npc_threatened):
        """Угроза > 0.3 — ROUTINE исключён из пространства генерации."""
        viable = engine._compute_viability_mask(npc_threatened)
        assert IntentDomain.ROUTINE not in viable, "БАГ: ROUTINE жизнеспособен при threat=0.6"
        assert IntentDomain.SURVIVAL in viable, "SURVIVAL всегда жизнеспособен"
        assert IntentDomain.SOCIAL in viable

    def test_paralyzed_npc_only_survival(self, engine, npc_paralyzed):
        """initiative_suppression > 0.7 — только SURVIVAL жизнеспособен."""
        viable = engine._compute_viability_mask(npc_paralyzed)
        assert IntentDomain.SURVIVAL in viable
        assert IntentDomain.ROUTINE not in viable
        assert IntentDomain.EXPLORATION not in viable
        assert IntentDomain.SOCIAL not in viable

    def test_no_kernel_all_domains_viable(self, engine):
        """Без perceptual_kernel — нет давления, все домены жизнеспособны (VACUUM = NEUTRAL, §ENIGMA-003)."""
        npc = {"id": "npc_1"}
        viable = engine._compute_viability_mask(npc)
        assert IntentDomain.ROUTINE in viable

    def test_threat_exact_threshold(self, engine):
        """threat = 0.3 точно — ROUTINE ещё жизнеспособен (порог строгий >)."""
        npc = {
            "id": "npc_1",
            "perceptual_kernel": {"threat_gradient": 0.3, "initiative_suppression": 0.0},
        }
        viable = engine._compute_viability_mask(npc)
        assert IntentDomain.ROUTINE in viable, "threat=0.3 не должен исключать ROUTINE (порог > 0.3)"


# ── Тесты Pre-Generation Gate ────────────────────────────────────────────

class TestViabilityPreGenerationGate:
    """ДОЛГ 4.3: Viability Gate ДО генерации — ROUTINE не рождается при SURVIVAL давлении."""

    def test_calm_npc_generates_routine_intent(self, engine, npc_calm):
        """Без угрозы — расписание генерирует ROUTINE intent."""
        with patch.object(engine, '_resolve_position', return_value=("tavern_silver_wolf", "gate", "patrolling")):
            changes, intents = engine._simulate_minor(npc_calm, current_time="08:00", tick=MINOR_TICK_INTERVAL + 1)

        assert len(intents) > 0, "БАГ: Спокойный NPC не сгенерировал ROUTINE intent"
        assert intents[0].domain == IntentDomain.ROUTINE, f"ОШИБКА: domain={intents[0].domain}, ожидается ROUTINE"

    def test_threatened_npc_no_routine_intent(self, engine, npc_threatened):
        """Угроза > 0.3 — ROUTINE intent НЕ генерируется (pre-generation gate)."""
        with patch.object(engine, '_resolve_position', return_value=("tavern_silver_wolf", "gate", "patrolling")):
            changes, intents = engine._simulate_minor(npc_threatened, current_time="08:00", tick=MINOR_TICK_INTERVAL + 1)

        _routine_intents = [i for i in intents if getattr(i, 'domain', None) == IntentDomain.ROUTINE]
        assert len(_routine_intents) == 0, (
            f"БАГ ДОЛГ 4.3: ROUTINE intent сгенерирован при threat=0.6! "
            f"Viability gate не работает. Intents: {[(i.reason, getattr(i,'domain',None)) for i in intents]}"
        )

    def test_paralyzed_npc_no_intents_at_all(self, engine, npc_paralyzed):
        """Паралич воли — ни ROUTINE, ни EXPLORATION не генерируются."""
        with patch.object(engine, '_resolve_position', return_value=("tavern_silver_wolf", "gate", "patrolling")):
            changes, intents = engine._simulate_minor(npc_paralyzed, current_time="08:00", tick=MINOR_TICK_INTERVAL + 1)

        assert len(intents) == 0, (
            f"БАГ: Парализованный NPC сгенерировал intents: "
            f"{[(i.reason, getattr(i,'domain',None)) for i in intents]}"
        )


# ── Тесты Domain типизации ──────────────────────────────────────────────

class TestIntentDomainTyping:
    """ДОЛГ 4.3: Каждый MovementIntent имеет типизированный domain."""

    def test_schedule_intent_is_routine(self, engine, npc_calm):
        """Schedule intent должен иметь domain=ROUTINE."""
        with patch.object(engine, '_resolve_position', return_value=("tavern_silver_wolf", "gate", "patrolling")):
            changes, intents = engine._simulate_minor(npc_calm, current_time="08:00", tick=MINOR_TICK_INTERVAL + 1)

        _sched = [i for i in intents if "schedule" in i.reason]
        if _sched:
            assert _sched[0].domain == IntentDomain.ROUTINE, f"Schedule intent domain={_sched[0].domain}"

    def test_default_domain_is_routine(self):
        """MacroMovementGoal по умолчанию имеет domain=ROUTINE."""
        intent = MovementIntent(npc_id="test", target_node_id="bar")
        assert intent.domain == IntentDomain.ROUTINE

    def test_flee_is_survival(self):
        """FLEE intent должен иметь domain=SURVIVAL."""
        flee = MovementIntent(npc_id="test", target_node_id="exit", reason="decision:flee_stay=player", domain=IntentDomain.SURVIVAL)
        assert flee.domain == IntentDomain.SURVIVAL
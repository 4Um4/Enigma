# backend/tests/test_build_npc_snapshots.py
"""
Тесты _build_npc_snapshots — мост NPC dict → NPCStateSnapshot.

Критический маппинг:
  social_stats.trust         → relationship_cache["player"]["trust"]
  social_stats.fear_of_player → relationship_cache["player"]["fear"]
  psyche.loyalty_true        → base_values["player"]
  status_profile.faction_rank → faction_affiliations

Без этого маппинга SocialDecayHandler получает пустой кэш → нулевой дрейф.

path: backend/tests/test_build_npc_snapshots.py
Назначение: Тесты _build_npc_snapshots — маппинг NPC dict → NPCStateSnapshot
Зависимости: pytest, app.services.tick_orchestrator
Основные сущности: TestBuildNpcSnapshots

TODO:
- протестировать на реальных NPC из игры, чтобы убедиться, что маппинг работает в боевых условиях и не ломается на неожиданных данных (напр. NPC без social_stats или с нестандартными статусами).
- добавить тесты на edge cases, например, когда social_stats есть, но trust/fear_of_player отсутствуют, или когда loyalty_true выходит за пределы 0-100. Убедиться, что маппинг корректно обрабатывает эти случаи (напр. default к 50 для loyalty_true).
"""

from __future__ import annotations

import pytest

from app.services.tick_orchestrator import TickOrchestrator


# ── Хелперы ───────────────────────────────────────────────────────────────

def _make_npc(
    npc_id: str = "npc_1",
    trust: float = 30.0,
    fear_of_player: float = 10.0,
    debt: float = 0.0,
    stress: float = 25.0,
    loyalty_true: float = 50.0,
    faction_rank: dict | None = None,
) -> dict:
    """Создаёт NPC dict в формате load_npcs_merged."""
    npc: dict = {
        "id": npc_id,
        "psyche": {
            "stress": stress,
            "willpower": 50.0,
            "loyalty_true": loyalty_true,
        },
        "social_stats": {
            "trust": trust,
            "fear_of_player": fear_of_player,
            "debt": debt,
        },
    }
    if faction_rank is not None:
        npc["status_profile"] = {"faction_rank": faction_rank}
    return npc


# ── Базовый маппинг ──────────────────────────────────────────────────────

class TestSocialStatsMapping:
    """social_stats → relationship_cache["player"]."""

    def test_trust_mapped_to_player_trust(self):
        npc = _make_npc(trust=40.0)
        snapshots = TickOrchestrator._build_npc_snapshots([npc])
        assert snapshots[0]["relationship_cache"]["player"]["trust"] == 40.0

    def test_fear_mapped_to_player_fear(self):
        npc = _make_npc(fear_of_player=15.0)
        snapshots = TickOrchestrator._build_npc_snapshots([npc])
        assert snapshots[0]["relationship_cache"]["player"]["fear"] == 15.0

    def test_debt_mapped_to_player_debt(self):
        npc = _make_npc(debt=200.0)
        snapshots = TickOrchestrator._build_npc_snapshots([npc])
        assert snapshots[0]["relationship_cache"]["player"]["debt"] == 200.0

    def test_zero_social_stats_no_player_entry(self):
        """Все нули → нет записи "player" (нет данных для дрейфа)."""
        npc = _make_npc(trust=0.0, fear_of_player=0.0, debt=0.0)
        snapshots = TickOrchestrator._build_npc_snapshots([npc])
        assert "player" not in snapshots[0]["relationship_cache"]

    def test_non_dict_skipped(self):
        """Не-dict элементы пропускаются."""
        snapshots = TickOrchestrator._build_npc_snapshots(["not_a_dict", 42])
        assert len(snapshots) == 0


# ── Base values ──────────────────────────────────────────────────────────

class TestBaseValuesMapping:
    """loyalty_true → base_values["player"]."""

    def test_loyalty_mapped_to_base_player(self):
        npc = _make_npc(loyalty_true=60.0)
        snapshots = TickOrchestrator._build_npc_snapshots([npc])
        assert snapshots[0]["base_values"]["player"] == 60.0

    def test_missing_loyalty_defaults_to_50(self):
        npc = _make_npc()
        del npc["psyche"]["loyalty_true"]
        snapshots = TickOrchestrator._build_npc_snapshots([npc])
        assert snapshots[0]["base_values"]["player"] == 50.0

    def test_existing_base_values_preserved(self):
        npc = _make_npc()
        npc["base_values"] = {"player": 70.0, "npc_other": 30.0}
        snapshots = TickOrchestrator._build_npc_snapshots([npc])
        assert snapshots[0]["base_values"]["player"] == 70.0
        assert snapshots[0]["base_values"]["npc_other"] == 30.0


# ── Faction affiliations ─────────────────────────────────────────────────

class TestFactionAffiliations:
    """faction_rank → faction_affiliations."""

    def test_faction_rank_to_affiliations(self):
        npc = _make_npc(faction_rank={"гильдия_воров": -1, "городская_стража": 2})
        snapshots = TickOrchestrator._build_npc_snapshots([npc])
        fa = snapshots[0]["faction_affiliations"]
        assert "гильдия_воров" in fa
        assert "городская_стража" in fa

    def test_no_faction_rank_empty_affiliations(self):
        npc = _make_npc()
        snapshots = TickOrchestrator._build_npc_snapshots([npc])
        assert snapshots[0]["faction_affiliations"] == []

    def test_existing_affiliations_preserved(self):
        npc = _make_npc()
        npc["faction_affiliations"] = ["test_faction"]
        snapshots = TickOrchestrator._build_npc_snapshots([npc])
        assert snapshots[0]["faction_affiliations"] == ["test_faction"]


# ── Stress mapping ───────────────────────────────────────────────────────

class TestStressMapping:
    """psyche.stress → NPCStateSnapshot.stress."""

    def test_stress_from_psyche(self):
        npc = _make_npc(stress=45.0)
        snapshots = TickOrchestrator._build_npc_snapshots([npc])
        assert snapshots[0]["stress"] == 45.0

    def test_missing_stress_defaults_to_zero(self):
        npc = {"id": "minimal"}
        snapshots = TickOrchestrator._build_npc_snapshots([npc])
        assert snapshots[0]["stress"] == 0.0


# ── Вложенный relationship_cache ─────────────────────────────────────────

class TestExistingNestedCache:
    """Если relationship_cache уже во вложенном формате — используется как есть."""

    def test_nested_cache_preserved(self):
        npc = _make_npc()
        npc["relationship_cache"] = {
            "player": {"trust": 50.0, "fear": 10.0},
            "npc_other": {"trust": 30.0, "fear": 5.0},
        }
        snapshots = TickOrchestrator._build_npc_snapshots([npc])
        rc = snapshots[0]["relationship_cache"]
        assert "player" in rc
        assert "npc_other" in rc
        assert rc["player"]["trust"] == 50.0

    def test_flat_cache_replaced_by_social_stats(self):
        """Плоский кэш {trust: ..., fear: ...} → маппинг из social_stats."""
        npc = _make_npc(trust=25.0, fear_of_player=8.0)
        npc["relationship_cache"] = {"trust": 25.0, "fear": 8.0}  # плоский, не вложенный
        snapshots = TickOrchestrator._build_npc_snapshots([npc])
        rc = snapshots[0]["relationship_cache"]
        # Должен быть во вложенном формате
        assert "player" in rc
        assert rc["player"]["trust"] == 25.0


# ── Интеграция с SocialDecayHandler ──────────────────────────────────────

class TestSocialDecayIntegration:
    """Snapshots с правильным маппингом → SocialDecayHandler производит дрейф."""

    def test_decay_produces_deltas_with_mapped_data(self):
        from app.services.social.social_decay_handler import SocialDecayHandler

        npc = _make_npc(trust=30.0, loyalty_true=50.0)
        snapshots = TickOrchestrator._build_npc_snapshots([npc])

        handler = SocialDecayHandler()
        deltas = handler.handle(snapshots, "test", 1)

        # trust=30, base=50 → дрейф к 50 должен быть
        trust_deltas = [d for d in deltas if d.trust_delta != 0.0]
        assert len(trust_deltas) > 0, (
            f"Ожидался дрейф trust (current=30, base=50), но дельт нет. "
            f"snapshots={snapshots}"
        )

    def test_no_decay_when_trust_equals_base(self):
        from app.services.social.social_decay_handler import SocialDecayHandler

        npc = _make_npc(trust=50.0, loyalty_true=50.0)
        snapshots = TickOrchestrator._build_npc_snapshots([npc])

        handler = SocialDecayHandler()
        deltas = handler.handle(snapshots, "test", 1)

        # trust=base → нет дрейфа
        trust_deltas = [d for d in deltas if d.trust_delta != 0.0]
        assert len(trust_deltas) == 0
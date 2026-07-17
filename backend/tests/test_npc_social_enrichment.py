# backend/tests/test_npc_social_enrichment.py
"""
Тесты обогащения NPC→NPC связей из village_relations.json.

Конвейер: village_relations.json → _enrich_with_social_relations() →
          _build_npc_snapshots() → SocialDecayHandler

Ключевой контракт:
  - Шкала 0-1 в JSON → 0-100 в relationship_cache/base_values
  - SocialDecayHandler производит NPC→NPC дрейф
  - Player entry из social_stats НЕ теряется при наличии NPC→NPC записей

path: backend/tests/test_npc_social_enrichment.py
Назначение: Тесты обогащения NPC→NPC связей из village_relations.json
Зависимости: pytest, app.services.npc.npc_loader, app.services.tick_orchestrator
Основные сущности: TestEnrichWithSocialRelations, TestEnrichedSnapshotIntegration

TODO:
- Добавить тесты для edge cases (отсутствие base_trust, некорректные форматы данных в JSON и т.д.)
- В будущем: интеграционные тесты с реальными данными из village_relations.json
"""

from __future__ import annotations

from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.services.npc.npc_loader import _enrich_with_social_relations
from app.services.tick_orchestrator import TickOrchestrator
from app.services.tick_utils import build_npc_snapshots

# ── Хелперы ───────────────────────────────────────────────────────────────


def _make_npc(
    npc_id: str = "npc_1",
    trust: float = 30.0,
    fear_of_player: float = 10.0,
    debt: float = 0.0,
    stress: float = 25.0,
    loyalty_true: float = 50.0,
) -> dict:
    """Создаёт NPC dict в формате load_npcs_merged."""
    return {
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


# ── Юнит-тесты _enrich_with_social_relations ─────────────────────────────


class TestEnrichWithSocialRelations:
    """Обогащение NPC dict связями из village_relations.json."""

    def test_basic_enrichment_populates_cache(self):
        """Базовая связь → relationship_cache + base_values заполнены."""
        npcs = [{"id": "tavern_keeper_tornin"}]
        relations = {
            "tavern_keeper_tornin": {
                "maid_lusya": {
                    "nature": "employer_employee",
                    "base_trust": 0.3,
                    "base_affection": 0.2,
                }
            }
        }

        _enrich_with_social_relations(npcs, relations)

        rc = npcs[0]["relationship_cache"]
        assert "maid_lusya" in rc
        assert rc["maid_lusya"]["trust"] == 30.0  # 0.3 * 100
        assert rc["maid_lusya"]["fear"] == 0.0
        assert rc["maid_lusya"]["base_trust"] == 30.0
        assert rc["maid_lusya"]["nature"] == "employer_employee"

        bv = npcs[0]["base_values"]
        assert bv["maid_lusya"] == 30.0

    def test_scale_conversion_0_to_100(self):
        """Шкала 0-1 из JSON → 0-100 в кэше."""
        npcs = [{"id": "npc_a"}]
        relations = {"npc_a": {"npc_b": {"nature": "friend", "base_trust": 0.85}}}

        _enrich_with_social_relations(npcs, relations)

        assert npcs[0]["relationship_cache"]["npc_b"]["trust"] == 85.0
        assert npcs[0]["base_values"]["npc_b"] == 85.0

    def test_zero_base_trust(self):
        """base_trust=0.0 → корректная запись с нулевым доверием."""
        npcs = [{"id": "npc_a"}]
        relations = {"npc_a": {"npc_b": {"nature": "enemy", "base_trust": 0.0}}}

        _enrich_with_social_relations(npcs, relations)

        rc = npcs[0]["relationship_cache"]
        assert "npc_b" in rc
        assert rc["npc_b"]["trust"] == 0.0
        assert rc["npc_b"]["base_trust"] == 0.0

    def test_no_overwrite_existing_relationship_cache(self):
        """Существующие записи в relationship_cache НЕ перезаписываются."""
        npcs = [
            {
                "id": "npc_a",
                "relationship_cache": {
                    "npc_b": {"trust": 99.0, "fear": 5.0, "base_trust": 50.0},
                },
                "base_values": {"npc_b": 50.0},
            }
        ]
        relations = {"npc_a": {"npc_b": {"nature": "friend", "base_trust": 0.3}}}

        _enrich_with_social_relations(npcs, relations)

        # Runtime данные сохранены
        assert npcs[0]["relationship_cache"]["npc_b"]["trust"] == 99.0
        assert npcs[0]["base_values"]["npc_b"] == 50.0

    def test_missing_source_npc_skipped(self):
        """Источник не найден в NPC списке → пропуск без ошибки."""
        npcs = [{"id": "npc_a"}]
        relations = {"nonexistent_npc": {"npc_b": {"nature": "friend", "base_trust": 0.5}}}

        _enrich_with_social_relations(npcs, relations)

        # NPC не найден — enrichment пропущен
        rc = npcs[0].get("relationship_cache", {})
        assert "npc_b" not in rc

    def test_multiple_targets_for_one_source(self):
        """Несколько целей для одного NPC → все обогащены."""
        npcs = [{"id": "tavern_keeper_tornin"}]
        relations = {
            "tavern_keeper_tornin": {
                "maid_lusya": {"nature": "employer_employee", "base_trust": 0.3},
                "guard_borko": {"nature": "acquaintance", "base_trust": 0.2},
                "merchant_goran": {"nature": "business_partner", "base_trust": 0.4},
            }
        }

        _enrich_with_social_relations(npcs, relations)

        rc = npcs[0]["relationship_cache"]
        assert len(rc) == 3
        assert rc["maid_lusya"]["trust"] == 30.0
        assert rc["guard_borko"]["trust"] == 20.0
        assert rc["merchant_goran"]["trust"] == 40.0

    def test_multiple_sources_enriched(self):
        """Несколько источников → каждый обогащён своими связями."""
        npcs = [
            {"id": "tavern_keeper_tornin"},
            {"id": "maid_lusya"},
        ]
        relations = {
            "tavern_keeper_tornin": {
                "maid_lusya": {"nature": "employer_employee", "base_trust": 0.3},
            },
            "maid_lusya": {
                "thief_shadow": {"nature": "handler_agent", "base_trust": 0.1},
            },
        }

        _enrich_with_social_relations(npcs, relations)

        assert "maid_lusya" in npcs[0]["relationship_cache"]
        assert "thief_shadow" in npcs[1]["relationship_cache"]

    def test_empty_relations_no_op(self):
        """Пустой relations → NPC не изменён."""
        npcs = [{"id": "npc_a"}]

        _enrich_with_social_relations(npcs, {})

        # relationship_cache не добавлен (нет связей)
        assert "relationship_cache" not in npcs[0] or npcs[0].get("relationship_cache") == {}

    def test_non_dict_rel_data_skipped(self):
        """Некорректный формат rel_data → пропуск без ошибки."""
        npcs = [{"id": "npc_a"}]
        relations = {"npc_a": {"npc_b": "not_a_dict"}}

        _enrich_with_social_relations(npcs, relations)

        rc = npcs[0].get("relationship_cache", {})
        assert "npc_b" not in rc

    def test_missing_base_trust_defaults_to_zero(self):
        """base_trust отсутствует → default 0.0."""
        npcs = [{"id": "npc_a"}]
        relations = {"npc_a": {"npc_b": {"nature": "stranger"}}}

        _enrich_with_social_relations(npcs, relations)

        rc = npcs[0]["relationship_cache"]
        assert rc["npc_b"]["trust"] == 0.0
        assert rc["npc_b"]["base_trust"] == 0.0


# ── Интеграция _build_npc_snapshots + обогащение ─────────────────────────


class TestEnrichedSnapshotIntegration:
    """Обогащённый NPC → _build_npc_snapshots → корректный snapshot."""

    def test_enriched_npc_has_both_player_and_npc_entries(self):
        """После обогащения snapshot содержит и player, и NPC→NPC записи."""
        npc = _make_npc(npc_id="tavern_keeper_tornin", trust=30.0, loyalty_true=60.0)
        # Симуляция обогащения
        npc["relationship_cache"] = {
            "maid_lusya": {
                "trust": 30.0,
                "fear": 0.0,
                "base_trust": 30.0,
                "nature": "employer_employee",
            },
        }
        npc["base_values"] = {"maid_lusya": 30.0}

        snapshots = build_npc_snapshots([npc])
        rc = snapshots[0]["relationship_cache"]
        bv = snapshots[0]["base_values"]

        # NPC→NPC записи сохранены
        assert "maid_lusya" in rc
        assert rc["maid_lusya"]["trust"] == 30.0

        # Player entry добавлен из social_stats (даже при наличии NPC→NPC)
        assert "player" in rc
        assert rc["player"]["trust"] == 30.0
        assert rc["player"]["fear"] == 10.0

        # Player base из loyalty_true
        assert "player" in bv
        assert bv["player"] == 60.0

        # NPC→NPC base сохранена
        assert "maid_lusya" in bv
        assert bv["maid_lusya"] == 30.0

    def test_existing_player_entry_not_overwritten_by_social_stats(self):
        """Если player entry уже в relationship_cache — не перезаписывается."""
        npc = _make_npc(npc_id="npc_a", trust=30.0, loyalty_true=60.0)
        npc["relationship_cache"] = {
            "player": {"trust": 50.0, "fear": 15.0, "base_trust": 55.0},
            "npc_b": {"trust": 20.0, "fear": 5.0, "base_trust": 25.0},
        }
        npc["base_values"] = {"player": 55.0, "npc_b": 25.0}

        snapshots = build_npc_snapshots([npc])
        rc = snapshots[0]["relationship_cache"]
        bv = snapshots[0]["base_values"]

        # Player entry из кэша, НЕ из social_stats (social_stats.trust=30 не перезаписал 50)
        assert rc["player"]["trust"] == 50.0
        assert rc["player"]["fear"] == 15.0
        # Player base из кэша, НЕ из loyalty_true
        assert bv["player"] == 55.0

    def test_player_base_added_when_missing_after_enrichment(self):
        """После обогащения NPC→NPC, base_values может не иметь player → добавляется."""
        npc = _make_npc(npc_id="npc_a", loyalty_true=70.0)
        npc["relationship_cache"] = {
            "npc_b": {"trust": 20.0, "fear": 0.0, "base_trust": 25.0},
        }
        npc["base_values"] = {"npc_b": 25.0}

        snapshots = build_npc_snapshots([npc])
        bv = snapshots[0]["base_values"]

        # Player base добавлена из loyalty_true
        assert "player" in bv
        assert bv["player"] == 70.0
        # NPC→NPC base сохранена
        assert bv["npc_b"] == 25.0


# ── Интеграция с SocialDecayHandler ──────────────────────────────────────


class TestNpcToNpcDecayIntegration:
    """Обогащённый NPC → SocialDecayHandler производит NPC→NPC дрейф."""

    def test_npc_to_npc_drift_produced(self):
        """NPC→NPC: current≠base → SocialDecayHandler считает дрейф."""
        from app.services.social.social_decay_handler import SocialDecayHandler

        npc = _make_npc(npc_id="tavern_keeper_tornin", trust=30.0, loyalty_true=60.0)
        # Текущий trust к lusya = 20, base = 30 → дрейф к 30
        npc["relationship_cache"] = {
            "maid_lusya": {
                "trust": 20.0,
                "fear": 0.0,
                "base_trust": 30.0,
                "nature": "employer_employee",
            },
        }
        npc["base_values"] = {"maid_lusya": 30.0}

        snapshots = build_npc_snapshots([npc])
        handler = SocialDecayHandler()
        deltas = handler.handle(snapshots, "test", 1)

        # NPC→NPC дрейф: current=20, base=30 → положительный дрейф
        npc_deltas = [d for d in deltas if d.social_target == "maid_lusya"]
        assert len(npc_deltas) == 1
        assert npc_deltas[0].trust_delta > 0.0
        assert npc_deltas[0].npc_id == "tavern_keeper_tornin"

    def test_player_drift_preserved_after_enrichment(self):
        """После обогащения NPC→NPC, player drift НЕ теряется."""
        from app.services.social.social_decay_handler import SocialDecayHandler

        npc = _make_npc(npc_id="tavern_keeper_tornin", trust=30.0, loyalty_true=60.0)
        # NPC→NPC: trust=30, base=30 → нет дрейфа
        npc["relationship_cache"] = {
            "maid_lusya": {
                "trust": 30.0,
                "fear": 0.0,
                "base_trust": 30.0,
                "nature": "employer_employee",
            },
        }
        npc["base_values"] = {"maid_lusya": 30.0}

        snapshots = build_npc_snapshots([npc])
        handler = SocialDecayHandler()
        deltas = handler.handle(snapshots, "test", 1)

        # Player drift: current=30, base=60 → дрейф к 60
        player_deltas = [d for d in deltas if d.social_target == "player"]
        assert len(player_deltas) == 1
        assert player_deltas[0].trust_delta > 0.0

    def test_no_npc_to_npc_drift_when_trust_equals_base(self):
        """NPC→NPC: current=base → нет дрейфа."""
        from app.services.social.social_decay_handler import SocialDecayHandler

        npc = _make_npc(npc_id="npc_a")
        npc["relationship_cache"] = {
            "npc_b": {"trust": 40.0, "fear": 0.0, "base_trust": 40.0},
        }
        npc["base_values"] = {"npc_b": 40.0}

        snapshots = build_npc_snapshots([npc])
        handler = SocialDecayHandler()
        deltas = handler.handle(snapshots, "test", 1)

        # NPC→NPC: trust=base → нет дрейфа
        npc_deltas = [d for d in deltas if d.social_target == "npc_b"]
        assert len(npc_deltas) == 0

    def test_full_pipeline_enrich_to_decay(self):
        """Полный конвейер: enrichment → snapshot → decay → NPC→NPC дельты."""
        from app.services.social.social_decay_handler import SocialDecayHandler

        # Шаг 1: Создаём NPC (как после load_npcs_merged без runtime)
        npcs = [_make_npc(npc_id="tavern_keeper_tornin", trust=30.0, loyalty_true=60.0)]

        # Шаг 2: Обогащаем (как _enrich_with_social_relations)
        relations = {
            "tavern_keeper_tornin": {
                "maid_lusya": {"nature": "employer_employee", "base_trust": 0.3},
                "guard_borko": {"nature": "acquaintance", "base_trust": 0.2},
            }
        }
        _enrich_with_social_relations(npcs, relations)

        # Шаг 3: Строим snapshot
        snapshots = build_npc_snapshots(npcs)

        # Шаг 4: SocialDecayHandler
        handler = SocialDecayHandler()
        deltas = handler.handle(snapshots, "test", 1)

        # NPC→NPC дрейф: maid_lusya (current=30, base=30 → нет дрейфа)
        # guard_borko (current=20, base=20 → нет дрейфа)
        # Player drift: current=30, base=60 → дрейф к 60
        player_deltas = [d for d in deltas if d.social_target == "player"]
        assert len(player_deltas) == 1
        assert player_deltas[0].trust_delta > 0.0

        # NPC→NPC: current=base → нет дрейфа (оба на базовом уровне)
        lusya_deltas = [d for d in deltas if d.social_target == "maid_lusya"]
        borko_deltas = [d for d in deltas if d.social_target == "guard_borko"]
        assert len(lusya_deltas) == 0
        assert len(borko_deltas) == 0

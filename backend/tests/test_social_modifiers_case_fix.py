"""
Юнит-тесты case-фикса ADR-O-386 (шаг 1): социальные модификаторы.

path: /backend/tests/test_social_modifiers_case_fix.py
Назначение: инвариант Мастера для case-фикса social_engine:
    (1) модификаторы jealousy/protect/fear/debt выходят каноническими
        lowercase-ключами и реально применяются к скорам;
    (2) protect-канал (бывший THREATEN) ремапится в "intimidate" (решение а);
    (3) баланс не меняется: без триггеров модификаторов нет, все ключи
        лежат в существующем Intent-пространстве, чужие скоры не тронуты.
Запуск: cd backend && python -m pytest tests/test_social_modifiers_case_fix.py -v

Зависимости: app.models.social, app.services.social.social_engine,
    app.models.npc_state (Intent), app.services.npc.decision_hub
Основные сущности: TestSocialModifiersCaseFix
"""

import pytest

from app.models.npc_state import Intent
from app.models.social import Relationship
from app.services.npc.decision_hub import DecisionHub
from app.services.social.social_engine import SocialEngine


@pytest.fixture
def engine() -> SocialEngine:
    """Граф напрямую: from_config не несёт fear/debt (только конструктор).

    Связи в ОБЕ стороны с одинаковыми значениями: направление get_connections
    не читалось — симметричный граф корректен при любом прочтении и
    зеркалит авто-реверс from_config.
    """
    beloved_fwd = Relationship(nature="friend", base_trust=0.7, base_affection=0.8, fear=0.5)
    beloved_rev = Relationship(nature="friend", base_trust=0.7, base_affection=0.8, fear=0.5)
    debtor_fwd = Relationship(nature="business_partner", base_trust=0.5, base_affection=0.0, debt=75.0)
    debtor_rev = Relationship(nature="business_partner", base_trust=0.5, base_affection=0.0, debt=75.0)
    graph = {
        ("npc_guardian", "npc_beloved"): beloved_fwd,
        ("npc_beloved", "npc_guardian"): beloved_rev,
        ("npc_creditor", "npc_debtor"): debtor_fwd,
        ("npc_debtor", "npc_creditor"): debtor_rev,
    }
    return SocialEngine(graph=graph, name_map=None)


class TestSocialModifiersCaseFix:
    """ADR-O-386, шаг 1: восстановление чтения модификаторов без изменения баланса."""

    def test_jealousy_key_lowercase_and_applied(self, engine):
        # ревность: affection 0.8 > 0.3, игрок рядом (2.0 < 3.0), player_interacts
        mods = engine.compute_social_modifiers(
            npc_id="npc_guardian",
            player_distances={"npc_beloved": 2.0},
            event_type="player_interacts",
        )
        assert mods.get("intimidate") == pytest.approx(0.32)  # 0.4 * 0.8
        assert "INTIMIDATE" not in mods

    def test_protect_remapped_to_intimidate_and_fear_fires(self, engine):
        # защита союзника (бывший THREATEN) и страх — оба от player_attacks по цели
        mods = engine.compute_social_modifiers(
            npc_id="npc_guardian",
            player_distances={"npc_beloved": 2.0},
            event_type="player_attacks",
            event_target="npc_beloved",
        )
        assert mods.get("intimidate") == pytest.approx(0.21)  # 0.3 * trust 0.7
        assert mods.get("flee") == pytest.approx(0.15)  # 0.3 * fear 0.5
        assert "THREATEN" not in mods
        assert "threaten" not in mods

    def test_debt_lever_key_observe(self, engine):
        # долговой рычаг: debt 75, игрок рядом (2.0 < 4.0) — событие не требуется
        mods = engine.compute_social_modifiers(
            npc_id="npc_creditor",
            player_distances={"npc_debtor": 2.0},
            event_type="idle",
        )
        assert mods.get("observe") == pytest.approx(0.2)  # 0.2 * min(75/50, 1.0)

    def test_balance_no_modifiers_without_triggers(self, engine):
        # инвариант «фикс ≠ баланс»: без триггеров модификаторов нет
        mods = engine.compute_social_modifiers(
            npc_id="npc_guardian",
            player_distances={},
            event_type="idle",
        )
        assert mods == {}

    def test_balance_all_keys_within_existing_intent_space(self, engine):
        # инвариант: новых интентов не создаётся — ключи ⊆ Intent-enum
        valid = {i.value for i in Intent}
        fired = engine.compute_social_modifiers(
            npc_id="npc_guardian",
            player_distances={"npc_beloved": 2.0},
            event_type="player_attacks",
            event_target="npc_beloved",
        )
        fired.update(
            engine.compute_social_modifiers(
                npc_id="npc_creditor",
                player_distances={"npc_debtor": 2.0},
                event_type="idle",
            )
        )
        assert set(fired)  # хотя бы один канал сработал
        assert set(fired) <= valid

    def test_apply_modifiers_end_to_end(self, engine):
        # сквозная: модификаторы прибавляются к скорам, чужие скоры не тронуты
        mods = engine.compute_social_modifiers(
            npc_id="npc_guardian",
            player_distances={"npc_beloved": 2.0},
            event_type="player_attacks",
            event_target="npc_beloved",
        )
        scores = {"intimidate": 0.20, "flee": 0.15, "observe": 0.10, "attack": 0.50}
        result = DecisionHub.apply_modifiers(dict(scores), social_modifiers=mods)
        assert result["intimidate"] == pytest.approx(0.41)  # 0.20 + 0.21
        assert result["flee"] == pytest.approx(0.30)  # 0.15 + 0.15
        assert result["attack"] == pytest.approx(0.50)
        assert result["observe"] == pytest.approx(0.10)
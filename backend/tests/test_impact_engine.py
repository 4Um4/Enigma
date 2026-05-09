# -*- coding: utf-8 -*-
"""
Тесты Impact Propagation Engine (Violence Simulation).

Полный Запуск: cd backend; python -m pytest tests/test_impact_engine.py -v

Файл: backend/tests/test_impact_engine.py
Назначение: Детерминированные тесты Impact Propagation Engine.
Зависимости: pytest, app.services.combat.impact_engine, app.models.*

Проверяют:
1. Contact Resolution (уклонение, глансинг, солид)
2. Zone Modifiers (голова, пах, конечности)
3. Damage Type Modifiers (slash vs blunt)
4. Injury Generation (порог structural_damage)
5. Determinism (один seed = один результат)
"""
import pytest
from app.services.combat.impact_engine import resolve_physical_impact
from app.models.impact import ImpactIntentDTO, ContactLevel
from app.models.idle_tick import NPCStateSnapshot
from app.models.state_delta import DeltaDomain
from app.models.delta_payloads import PhysiologyPayload


def _make_snapshot(
    npc_id: str = "npc_1", 
    dexterity: float = 10.0, 
    pain: float = 0.0, 
    fatigue: float = 0.0,
    blood_loss: float = 0.0
) -> NPCStateSnapshot:
    """Фабрика снапшотов для изолированных тестов."""
    return NPCStateSnapshot(
        npc_id=npc_id,
        stress=0.0,
        relationship_cache={},
        base_values={},
        faction_affiliations=[],
        hp=100.0,
        max_hp=100.0,
        pain=pain,
        fatigue=fatigue,
        blood_loss=blood_loss,
        consciousness=1.0,
        injuries_by_zone={},
        base_abilities={"dexterity": dexterity, "strength": 10.0},
        modifiers={}
    )


def _make_intent(
    actor_id: str = "player",
    target_id: str = "npc_1",
    force: float = 30.0,
    damage_type: str = "slash",
    target_zone: str = None
) -> ImpactIntentDTO:
    return ImpactIntentDTO(
        actor_id=actor_id,
        target_id=target_id,
        damage_type=damage_type,
        target_zone=target_zone,
        force=force
    )


class TestContactResolution:
    """Проверка модели контакта (уклонение vs попадание)."""
    
    def test_high_dexterity_dodge(self):
        """Ловкий NPC с высокой dexterity уклоняется (seed 42 дает dodge)."""
        attacker = _make_snapshot(npc_id="attacker")
        defender = _make_snapshot(npc_id="defender", dexterity=90.0) # 90% dodge base
        intent = _make_intent(actor_id="attacker", target_id="defender", force=30.0)
        
        results = resolve_physical_impact(attacker, defender, intent, rng_seed=42)
        
        # Должны быть дельты (атакующий устает), но без урона защитнику
        defender_deltas = [d for d in results if d.npc_id == "defender"]
        attacker_deltas = [d for d in results if d.npc_id == "attacker"]
        
        assert len(defender_deltas) == 0, "Ловкий защитник уклонился, дельт урона быть не должно"
        assert len(attacker_deltas) == 1
        assert attacker_deltas[0].payload.fatigue_delta > 0.0

    def test_low_dexterity_hit(self):
        """Неповоротливый NPC получает полный удар."""
        attacker = _make_snapshot(npc_id="attacker")
        defender = _make_snapshot(npc_id="defender", dexterity=2.0) # Почти нет шанса уклониться
        intent = _make_intent(actor_id="attacker", target_id="defender", force=30.0)
        
        results = resolve_physical_impact(attacker, defender, intent, rng_seed=42)
        
        defender_deltas = [d for d in results if d.npc_id == "defender"]
        assert len(defender_deltas) == 1
        assert defender_deltas[0].domain == DeltaDomain.PHYSIOLOGY
        assert defender_deltas[0].payload.hp_delta < 0.0

    def test_pain_reduces_dodge(self):
        """Боль снижает способность уклоняться (Functional Capacity)."""
        # Здоровый ловкий NPC
        defender_healthy = _make_snapshot(npc_id="def_1", dexterity=50.0, pain=0.0)
        # Израненный ловкий NPC
        defender_hurt = _make_snapshot(npc_id="def_2", dexterity=50.0, pain=80.0)
        
        intent = _make_intent(force=30.0)
        
        # Запускаем несколько раз, чтобы проверить статистику (упрощенно)
        hits_healthy = 0
        hits_hurt = 0
        for seed in range(10):
            res_h = resolve_physical_impact(_make_snapshot("a"), defender_healthy, intent, rng_seed=seed)
            if any(d.npc_id == "def_1" for d in res_h): hits_healthy += 1
            
            res_d = resolve_physical_impact(_make_snapshot("a"), defender_hurt, intent, rng_seed=seed)
            if any(d.npc_id == "def_2" for d in res_d): hits_hurt += 1
                
        assert hits_hurt >= hits_healthy, "Израненный NPC должен получать больше попаданий"


class TestZoneModifiers:
    """Проверка зональных модификаторов боли и кровопотери."""
    
    def test_head_hit_high_pain(self):
        """Удар в голову дает х2 боль."""
        intent_body = _make_intent(target_zone="torso_chest", force=30.0)
        intent_head = _make_intent(target_zone="head_skull", force=30.0)
        defender = _make_snapshot(dexterity=2.0) # Гарантируем попадание
        
        res_body = resolve_physical_impact(_make_snapshot("a"), defender, intent_body, rng_seed=1)
        res_head = resolve_physical_impact(_make_snapshot("a"), defender, intent_head, rng_seed=1)
        
        pain_body = res_body[0].payload.pain_delta
        pain_head = res_head[0].payload.pain_delta
        
        assert pain_head > pain_body
        assert abs(pain_head - pain_body * 2.0) < 0.1  # x2 множитель

    def test_groin_hit_massive_pain_low_bleed(self):
        """Удар в пах дает х2.5 боль, но мало кровопотери."""
        intent_groin = _make_intent(target_zone="torso_groin", force=30.0)
        intent_chest = _make_intent(target_zone="torso_chest", force=30.0)
        defender = _make_snapshot(dexterity=2.0)
        
        res_groin = resolve_physical_impact(_make_snapshot("a"), defender, intent_groin, rng_seed=1)
        res_chest = resolve_physical_impact(_make_snapshot("a"), defender, intent_chest, rng_seed=1)
        
        assert res_groin[0].payload.pain_delta > res_chest[0].payload.pain_delta * 2.0
        assert res_groin[0].payload.blood_loss_delta < res_chest[0].payload.blood_loss_delta


class TestDamageTypes:
    """Проверка модификаторов типа урона."""
    
    def test_slash_high_bleed(self):
        """Рубящий урон вызывает сильное кровотечение."""
        intent_slash = _make_intent(damage_type="slash", force=40.0, target_zone="arm_r")
        intent_blunt = _make_intent(damage_type="blunt", force=40.0, target_zone="arm_r")
        defender = _make_snapshot(dexterity=2.0)
        
        res_slash = resolve_physical_impact(_make_snapshot("a"), defender, intent_slash, rng_seed=1)
        res_blunt = resolve_physical_impact(_make_snapshot("a"), defender, intent_blunt, rng_seed=1)
        
        assert res_slash[0].payload.blood_loss_delta > res_blunt[0].payload.blood_loss_delta
        
    def test_blunt_high_pain(self):
        """Дробящий урон вызывает больше боли."""
        intent_blunt = _make_intent(damage_type="blunt", force=40.0, target_zone="torso_chest")
        intent_slash = _make_intent(damage_type="slash", force=40.0, target_zone="torso_chest")
        defender = _make_snapshot(dexterity=2.0)
        
        res_blunt = resolve_physical_impact(_make_snapshot("a"), defender, intent_blunt, rng_seed=1)
        res_slash = resolve_physical_impact(_make_snapshot("a"), defender, intent_slash, rng_seed=1)
        
        assert res_blunt[0].payload.pain_delta > res_slash[0].payload.pain_delta


class TestInjuryGeneration:
    """Проверка генерации структурных травм."""
    
    def test_weak_hit_no_injury(self):
        """Слабый удар не генерирует InjuryDTO."""
        intent = _make_intent(force=10.0, target_zone="torso_chest")
        defender = _make_snapshot(dexterity=2.0)
        
        res = resolve_physical_impact(_make_snapshot("a"), defender, intent, rng_seed=1)
        assert len(res[0].payload.add_injuries) == 0
        
    def test_strong_hit_generates_injury(self):
        """Сильный удар генерирует InjuryDTO с кровотечением."""
        intent = _make_intent(force=60.0, damage_type="slash", target_zone="arm_l")
        defender = _make_snapshot(dexterity=2.0)
        
        res = resolve_physical_impact(_make_snapshot("a"), defender, intent, rng_seed=1)
        injuries = res[0].payload.add_injuries
        
        assert len(injuries) == 1
        assert injuries[0].target_zone == "arm_l"
        assert injuries[0].structural_damage > 0.0
        assert "bleeding" in injuries[0].critical_effects


class TestDeterminism:
    """Проверка что одинаковый seed дает идентичный результат."""
    
    def test_same_seed_same_result(self):
        attacker = _make_snapshot("a")
        defender = _make_snapshot("d", dexterity=30.0)
        intent = _make_intent(force=50.0)
        
        res1 = resolve_physical_impact(attacker, defender, intent, rng_seed=999)
        res2 = resolve_physical_impact(attacker, defender, intent, rng_seed=999)
        
        d1 = res1[0].payload
        d2 = res2[0].payload
        
        assert d1.hp_delta == d2.hp_delta
        assert d1.pain_delta == d2.pain_delta
        assert d1.blood_loss_delta == d2.blood_loss_delta
        assert d1.shock_impulse == d2.shock_impulse
"""
path: /project/backend/tests/test_avatar_status.py
Назначение: Тесты для NeedPresentationMapper и AvatarStatusBuilder
Зависимости: pytest, app.domain.presentation, app.models.economy
Основные сущности: test_need_mapper, test_avatar_status_builder
"""
import pytest

from app.domain.presentation import NeedSeverity
from app.models.economy import EconomicProfile, Need, NeedType
from app.services.economy.need_presentation_mapper import NeedPresentationMapper
from app.services.integration.avatar_status_builder import AvatarStatusBuilder


@pytest.fixture
def mapper() -> NeedPresentationMapper:
    return NeedPresentationMapper()

@pytest.fixture
def builder(mapper: NeedPresentationMapper) -> AvatarStatusBuilder:
    return AvatarStatusBuilder(mapper)

def _make_need(need_type: NeedType, neglected_ticks: int) -> Need:
    """Создает потребность с neglected_ticks для рассчёта effective_urgency."""
    return Need(
        need_type=need_type,
        base_urgency=0.0,
        budget_share=0.1,
        neglected_ticks=neglected_ticks,
    )

def test_mapper_hides_minor_needs(mapper: NeedPresentationMapper):
    """Потребности ниже 0.2 должны быть скрыты."""
    # FOOD decay_rate = 0.08. 2 ticks = 0.16 urgency
    needs = [_make_need(NeedType.FOOD, 2)]
    dtos = mapper.map_needs(needs)
    assert len(dtos) == 0

def test_mapper_maps_severity(mapper: NeedPresentationMapper):
    """Проверка правильности перевода urgency в NeedSeverity."""
    # FOOD decay_rate = 0.08
    # 5 ticks = 0.40 urgency -> MODERATE (т.к. 0.40 < 0.6)
    # 11 ticks = 0.88 urgency -> CRITICAL (т.к. 0.88 < 0.95)
    
    needs = [
        _make_need(NeedType.FOOD, 5),  # 0.40
        _make_need(NeedType.SOCIAL, 140), # decay 0.005 * 140 = 0.70 -> MAJOR (т.к. 0.70 < 0.8)
    ]
    dtos = mapper.map_needs(needs)
    assert len(dtos) == 2
    
    food_dto = next(d for d in dtos if d.id == "food")
    assert food_dto.severity == NeedSeverity.MODERATE
    
    social_dto = next(d for d in dtos if d.id == "social")
    assert social_dto.severity == NeedSeverity.MAJOR

def test_builder_returns_empty_on_none(builder: AvatarStatusBuilder):
    """Если профиль не передан, билдер должен вернуть пустой DTO, а не None."""
    dto = builder.build(None)
    assert dto is not None
    assert dto.gold == 0.0
    assert dto.food_count == 0.0
    assert dto.current_weight == 0.0
    assert dto.max_weight == 0.0
    assert len(dto.active_needs) == 0

def test_builder_assembles_profile(builder: AvatarStatusBuilder):
    """Проверка сборки DTO из реального профиля."""
    profile = EconomicProfile(npc_id="player", gold=42.5, goods={"food": 3.0})
    # 9 ticks * 0.08 = 0.72 urgency -> MAJOR (т.к. 0.72 < 0.8)
    profile.base_needs.append(_make_need(NeedType.FOOD, 9))
    _topo = {"stats": {"current_weight": 45.5, "max_weight": 120.0}}

    dto = builder.build(profile, _topo)
    
    assert dto.gold == 42.5
    assert dto.food_count == 3.0
    assert dto.current_weight == 45.5
    assert dto.max_weight == 120.0
    assert len(dto.active_needs) == 1
    assert dto.active_needs[0].id == "food"
    assert dto.active_needs[0].severity == NeedSeverity.MAJOR
# backend/tests/test_social_homeostasis.py
"""
Тесты социального гомеостаза: SocialInputProjector, HomeostasisProjector, SocialTargetResolver.
Проверка: EMA-накопление, дрейф насыщения, выбор цели для разговора.
Запуск: python -m pytest backend/tests/test_social_homeostasis.py -v -s
"""
import pytest
import types
from app.services.npc.homeostasis_projector import HomeostasisProjector
from app.services.events.social_input_projector import SocialInputProjector
from app.services.npc.social_target_resolver import SocialTargetResolver
from app.services.npc.decision_hub import DecisionHub, EventContext
from app.services.events.event_types import EventType
from app.domain.events import EventDTO
from app.models.phase8 import Phase8Context
from app.models.npc_state import Intent

class FakeSpatialQuery:
    """Мок пространственного сервиса для тестирования выбора цели."""
    def distance(self, a: str, b: str) -> float:
        if a == 'npc_1' and b == 'npc_2': return 5.0
        if a == 'npc_1' and b == 'npc_3': return 15.0
        return 999.0

    def get_nearest_npc(self, source_id: str, npc_ids: list) -> str:
        _min_dist = float('inf')
        _nearest = None
        for nid in npc_ids:
            if nid == source_id: continue
            _d = self.distance(source_id, nid)
            if _d < _min_dist:
                _min_dist = _d
                _nearest = nid
        return _nearest

class FakeEventBus:
    def subscribe(self, et, fn): pass

def make_event_dto(event_type, source, payload):
    return EventDTO(
        id="test", type=event_type, source=source, timestamp=0.0,
        payload=payload, visibility="public", radius=10.0, persistence_level="working"
    )

# ===================================================================
# 1. ТЕСТЫ FIELD LAYER (HomeostasisProjector)
# ===================================================================

def test_homeostasis_isolation_drops_satiation():
    """Экстраверт в изоляции должен терять насыщение."""
    npc_data = [{'npc_id': 'npc_1', 'psyche': {'gregariousness': 0.8}, 'social_input_ema': 0.1}]
    deltas = HomeostasisProjector.compute_isolation_decay(npc_data)
    
    assert len(deltas) == 1
    payload = deltas[0].payload
    # setpoint = 0.68, actual = 0.1 -> pressure = 0.58 -> delta = -1.16
    assert payload.social_satiation_delta < 0.0, "Изоляция должна понижать насыщение"

def test_homeostasis_overload_rises_satiation():
    """Интроверт в толпе должен повышать насыщение (перегруз)."""
    npc_data = [{'npc_id': 'npc_1', 'psyche': {'gregariousness': 0.2}, 'social_input_ema': 0.9}]
    deltas = HomeostasisProjector.compute_isolation_decay(npc_data)
    
    assert len(deltas) == 1
    payload = deltas[0].payload
    # setpoint = 0.32, actual = 0.9 -> pressure = -0.58 -> delta = +1.16
    assert payload.social_satiation_delta > 0.0, "Перегруз должен повышать насыщение"

# ===================================================================
# 2. ТЕСТЫ SENSOR LAYER (SocialInputProjector)
# ===================================================================

def test_social_input_projector_generates_ema_deltas():
    """Событие разговора должно генерировать EMA-дельты для спикера и слушателей."""
    event = make_event_dto(
        EventType.NPC_SPOKE, 
        source="npc_1", 
        payload={'speaker_id': 'npc_1', 'listener_ids': ['npc_2']}
    )
    
    proj = SocialInputProjector(FakeEventBus())
    proj._on_event(event)
    events = proj.drain_events()
    
    ctx = Phase8Context(all_npcs_raw=[], all_npc_contexts=[], shared_context=None, campaign_id='test', tick_ctx=None)
    result = proj.handle(events, ctx)
    
    assert len(result.deltas) == 2, "Должно быть 2 дельты (спикер + слушатель)"
    ema_deltas = {d.npc_id: d.payload.social_input_ema_delta for d in result.deltas}
    
    assert ema_deltas.get('npc_1', 0) > 0, "Спикер должен получить EMA-вход"
    assert ema_deltas.get('npc_2', 0) > 0, "Слушатель должен получить EMA-вход"

# ===================================================================
# 3. ТЕСТЫ TARGET RESOLUTION (SocialTargetResolver)
# ===================================================================

def test_social_target_resolver_picks_nearest_when_hungry():
    """Голодный NPC должен выбрать ближайшего NPC для общения."""
    state = types.SimpleNamespace(
        npc_id='npc_1', 
        social_satiation=10.0, # Очень голоден
        relationship_cache={},
        perceptual_kernel=types.SimpleNamespace(threat_gradient=0.0, uncertainty=0.0, anomaly_score=0.0, somatic_urgency=0.0),
        drives_runtime={'desire': 0.8, 'control': 0.1, 'fear': 0.1, 'significance': 0.1},
        emotion='NEUTRAL',
        body_state={'life_status': 'ALIVE', 'shock_impulse': 0.0},
        will_state='COMPLY',
        identity=None
    )
    
    spatial = FakeSpatialQuery()
    npc_ids = ['npc_1', 'npc_2', 'npc_3']
    
    # 1. Прямой тест резолвера
    target = SocialTargetResolver.resolve(state, spatial, npc_ids)
    assert target == 'npc_2', f"Должен выбрать npc_2, выбрал {target}"
    
    # 2. Тест через DecisionHub._resolve_target
    hub = DecisionHub(rng=None)
    event = EventContext(event_type=EventType.WORLD_TICK, actor_id='npc_1', target_id=None)
    
    talk_target = hub._resolve_target(
        intent=Intent.TALK.value, 
        event=event, 
        state=state, 
        spatial_query=spatial, 
        all_npc_ids=npc_ids
    )
    assert talk_target == 'npc_2', f"DecisionHub должен выбрать npc_2 для TALK, выбрал {talk_target}"
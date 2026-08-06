import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from app.services.perception.narrative_projector import NarrativeProjector
from app.domain.presentation import PerceptionContext

def test_telepathy_barrier():
    '''Projector должен затемнять текст, если NPC находится далеко (dist > 15.0).'''
    
    raw_dialogue = [{
        "speaker_id": "npc_fearful",
        "text": "Я так боюсь!",
        "event_id": "evt_001"
    }]
    
    # Игрок в (0,0), NPC в (20.0, 20.0) - dist > 15
    context = PerceptionContext(
        player_position=(0.0, 0.0),
        speaker_positions={
            "npc_fearful": (20.0, 20.0)
        }
    )
    
    projector = NarrativeProjector()
    narratives = projector.project(raw_dialogue, context)
    
    assert len(narratives) == 1
    n = narratives[0]
    
    # Игрок не должен слышать чистый текст
    assert n.visible_text == "*невнятно*"
    assert n.perception_certainty == 0.0
    assert n.auditory_clarity == 0.0
    assert n.event_id == "evt_001" # Проверяем, что event_id не генерируется внутри

if __name__ == '__main__':
    test_telepathy_barrier()
    print('✅ Telepathy Test PASSED')
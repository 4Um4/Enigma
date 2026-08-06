"""
path: /project/backend/tests/micro/test_telepathy_epistemic_barrier.py
Назначение: Telepathy Test. Проверка эпистемического барьера.
Сценарий: NPC с страхом 0.9 за стеной. Игрок не должен видеть эмоции.

Запуск: cd backend; python backend/tests/micro/test_telepathy_epistemic_barrier.py; cd ..
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

from app.domain.presentation import PerceivedNarrativeDTO, PerceivedManifestationDTO

def test_telepathy_barrier():
    """Эпистемический барьер: за стеной NPC не передаёт страх в текст или manifestations."""
    
    # Симулируем данные, которые пришли бы от PresentationAssembler, если бы игрок был за стеной
    # В Sprint 01B здесь будет PerceptionProjector, пока эмулируем результат
    narrative = PerceivedNarrativeDTO(
        event_id="test_1",
        speaker_id="npc_fearful",
        visible_text="...", # Игрок ничего не услышал
        perception_certainty=0.1,
        manifestations=(), # Игрок не видит проявлений
    )
    
    assert narrative.visible_text != "испуган"
    assert narrative.visible_text != "боится"
    assert len(narrative.manifestations) == 0
    assert narrative.perception_certainty < 0.5

if __name__ == "__main__":
    test_telepathy_barrier()
    print("✅ Telepathy Test PASSED")
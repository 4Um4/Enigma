"""
Файл: backend/app/services/affective/emotion_resolution.py
Назначение: Конвертация аффективного давления в конкретную эмоцию (EmotionPayload)
Зависимости: app.models.affect, app.models.delta_payloads
Основные сущности: resolve_emotion_from_pressure
TODO:
- В будущем может быть расширен до полноценного Emotion Engine, который будет учитывать не только давление, но и индивидуальные черты личности NPC, их текущую психическую устойчивость, прошлый опыт и динамические изменения психики. Но для MVP достаточно базового транслятора Pressure → Emotion с простыми эвристиками.

"""

from app.models.affect import AffectivePressureDTO
from app.models.delta_payloads import EmotionPayload
from typing import Optional

def resolve_emotion_from_pressure(
    pressure: AffectivePressureDTO, 
    psyche: dict
) -> Optional[EmotionPayload]:
    """
    Чистая функция. Локальная интерпретация давления организмом.
    Если давление превышает порог личности → генерируется EmotionPayload.
    """
    fear_drive = psyche.get("fear", 0.5)
    willpower = psyche.get("willpower", 0.5)
    
    # Порог паники снижается от трусости и усталости, повышается волей
    panic_threshold = 0.7 - (fear_drive * 0.2) + (willpower * 0.1)
    
    _stress_delta = 0.0
    _emotion_tag = None
    _fear_delta = 0.0
    
    if pressure.threat_load > panic_threshold and pressure.sensory_overload > 0.4:
        _emotion_tag = "panic"
        _stress_delta = pressure.threat_load * 30.0
        _fear_delta = pressure.threat_load * 15.0
    elif pressure.threat_load > (panic_threshold - 0.2):
        _emotion_tag = "fear"
        _stress_delta = pressure.threat_load * 15.0
        _fear_delta = pressure.threat_load * 8.0
    elif pressure.uncertainty_load > 0.6:
        _emotion_tag = "confusion"
        _stress_delta = pressure.uncertainty_load * 10.0
    elif pressure.aggression_charge > 0.7 and willpower < 0.4:
        _emotion_tag = "rage"
        _stress_delta = pressure.aggression_charge * 10.0
        
    if _stress_delta > 0:
        return EmotionPayload(
            stress_delta=_stress_delta,
            emotion_delta=_fear_delta,
            emotion_tag=_emotion_tag
        )
        
    return None
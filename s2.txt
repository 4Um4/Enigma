"""
Файл: backend/app/services/affective/pressure_derivation.py
Назначение: Вывод аффективного давления из обновленного PerceptualKernel и физиологии
Зависимости: app.models.affect, app.models.cfrm
Основные сущности: derive_affective_pressure

python


"""

from app.models.affect import AffectivePressureDTO
from app.models.npc_state import PerceptualKernel

def derive_affective_pressure(
    kernel: PerceptualKernel, 
    body_state: dict
) -> AffectivePressureDTO:
    """
    Чистая функция. Транслирует феноменологическое восприятие и физиологию 
    в вектор аффективного давления.
    """
    # Угроза модулируется болью (раненый зверь или жертва)
    _threat = kernel.threat_gradient * 0.7 + body_state.get("pain", 0) / 100.0 * 0.3
    
    # Неопределенность + аномалия = когнитивная перегрузка
    _uncertainty = (kernel.uncertainty + kernel.anomaly_score) / 2.0
    
    # Подчинение = склоность к комплаенсу + внешний градиент
    _submission = kernel.compliance_bias * 0.6 + kernel.threat_gradient * 0.4
    
    # Агрессия = подавленная воля (инверсия inhibition) + аномалия
    _aggression = max(0.0, (1.0 - kernel.aggression_inhibition)) * 0.5 + kernel.anomaly_score * 0.5
    
    # Сенсорная перегрузка = боль + усталость
    _sensory = (body_state.get("pain", 0) / 100.0 + body_state.get("fatigue", 0) / 100.0) / 2.0

    return AffectivePressureDTO(
        threat_load=min(1.0, _threat),
        uncertainty_load=min(1.0, _uncertainty),
        social_submission=min(1.0, _submission),
        aggression_charge=min(1.0, _aggression),
        sensory_overload=min(1.0, _sensory)
    )
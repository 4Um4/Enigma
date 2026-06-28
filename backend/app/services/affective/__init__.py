"""
Affective Domain: Динамика внутреннего состояния субъекта.
ADR-049: От реактивных эмоций к аффективному аккумулятору (Интеграл угрозы по времени).
"""
from app.services.affective.affective_integrator import integrate_affective_pressure
from app.services.affective.emotion_transition import resolve_emotion_transition
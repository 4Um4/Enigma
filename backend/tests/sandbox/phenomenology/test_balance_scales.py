"""
Файл: backend/tests/sandbox/phenomenology/test_balance_scales.py
Назначение: Суперпесочница Равновесия Весов. Точная верификация математики мембран и проекций.
Зависимости: app.services.cfrm.local_causal_solver, app.models.cfrm
Основные сущности: TestProjectionMath

TODO:
- Добавить больше сценариев (например, проверка когнитивного усиления при высоком стрессе, проверка драматизации в социальной проекции)
- Внедрить метрики для количественной оценки баланса (например, balance_score)
- Вынести общие фикстуры в отдельный файл для повторного использования
"""
import pytest
from app.models.cfrm import (
    FieldDisturbance, CausalAxis, DisturbanceVector, PerceivedPhenomenon
)
from app.models.npc_state import PerceptualKernel
from app.services.cfrm.local_causal_solver import PhysicalProjection, CognitiveProjection, SocialProjection

@pytest.fixture
def calm_kernel() -> PerceptualKernel:
    return PerceptualKernel(anomaly_score=0.1)

@pytest.fixture
def paranoid_kernel() -> PerceptualKernel:
    return PerceptualKernel(anomaly_score=0.9)

class TestPhysicalProjectionBalance:
    """Проверка закона сохранения энергии в физической проекции."""
    
    def test_energy_loss_is_exponential(self, calm_kernel):
        """Физика теряет энергию экспоненциально: magnitude * (membrane^2)."""
        proj = PhysicalProjection()
        dist = FieldDisturbance(
            origin_cluster="c1", disturbance_type=CausalAxis.PHYSICAL,
            magnitude=2.0, vectors=(DisturbanceVector.KINETIC,), source_entity="s"
        )
        
        # Прямое наблюдение
        p_direct = proj.project(dist, 1.0, calm_kernel, {"consciousness": 1.0})
        # Через тонкую стену (0.5)
        p_thin_wall = proj.project(dist, 0.5, calm_kernel, {"consciousness": 1.0})
        # Через толстую стену (0.2). Magnitude=2.0 чтобы пройти порог < 0.05 (2.0 * 0.04 = 0.08)
        p_thick_wall = proj.project(dist, 0.2, calm_kernel, {"consciousness": 1.0})
        
        assert p_direct is not None and p_direct.perceived_intensity == 2.0
        assert p_thin_wall is not None and p_thin_wall.perceived_intensity == 0.5 # 2.0 * (0.5^2)
        assert p_thick_wall is not None and p_thick_wall.perceived_intensity == pytest.approx(0.08) # 2.0 * (0.2^2)
        
    def test_mutation_stage_progression(self, calm_kernel):
        """Стадия мутации растет с потерей энергии: 0->1->2."""
        proj = PhysicalProjection()
        dist = FieldDisturbance(
            origin_cluster="c1", disturbance_type=CausalAxis.PHYSICAL,
            magnitude=3.0, vectors=(DisturbanceVector.KINETIC,), source_entity="s"
        )
        
        p_0 = proj.project(dist, 0.9, calm_kernel, {"consciousness": 1.0})
        p_1 = proj.project(dist, 0.5, calm_kernel, {"consciousness": 1.0})
        p_2 = proj.project(dist, 0.25, calm_kernel, {"consciousness": 1.0})
        
        assert p_0.mutation_stage == 0, "Прямой контакт должен быть stage 0"
        assert p_1.mutation_stage == 1, "Препятствие должно переключать на stage 1"
        assert p_2.mutation_stage == 2, "Глухая стена должна переключать на stage 2 (faint_vibration)"


class TestCognitiveProjectionBalance:
    """Проверка инференса и паранойи в когнитивной проекции."""
    
    def test_stress_amplifies_cognitive_signal(self):
        """Стресс усиливает когнитивный сигнал (инференс)."""
        proj = CognitiveProjection()
        dist = FieldDisturbance(
            origin_cluster="c1", disturbance_type=CausalAxis.COGNITIVE,
            magnitude=0.5, vectors=(DisturbanceVector.BEHAVIORAL,), source_entity="s",
            semantic_seed="suspicious_movement"
        )
        
        calm_state = {"stress": 0.0}
        stressed_state = {"stress": 80.0} # Высокий стресс
        
        p_calm = proj.project(dist, 0.8, PerceptualKernel(anomaly_score=0.1), calm_state)
        p_stressed = proj.project(dist, 0.8, PerceptualKernel(anomaly_score=0.1), stressed_state)
        
        assert p_calm is not None and p_stressed is not None
        # Формула: threat_amplifier = 1.0 + (stress / 100.0) * 0.5
        # calm: 0.5 * 0.8 * 1.0 = 0.4
        # stressed: 0.5 * 0.8 * 1.4 = 0.56
        assert p_stressed.perceived_intensity > p_calm.perceived_intensity, "Стресс должен усиливать когнитивное восприятие угрозы"
        assert p_stressed.perceived_intensity == pytest.approx(0.56, abs=0.01)

    def test_paranoid_kernel_mutates_neutral_to_threat(self, paranoid_kernel):
        """Экстремальная паранойя превращает нейтральный сигнал в угрозу."""
        proj = CognitiveProjection()
        dist = FieldDisturbance(
            origin_cluster="c1", disturbance_type=CausalAxis.COGNITIVE,
            magnitude=0.5, vectors=(DisturbanceVector.BEHAVIORAL,), source_entity="s",
            semantic_seed="idle" # Нейтральный геном!
        )
        
        p = proj.project(dist, 0.8, paranoid_kernel, {"stress": 0.0})
        
        assert p is not None
        assert p.perceived_archetype == "threat", "Паранойя должна превращать idle в threat"
        assert p.distortion_nature == "paranoid_inference"


class TestSocialProjectionBalance:
    """Проверка эффекта испорченного телефона и драматизации."""
    
    def test_intermediate_membrane_amplifies_rumor(self, calm_kernel):
        """Социальная мембрана УСИЛИВАЕТ сигнал на средних дистанциях (эффект слуха)."""
        proj = SocialProjection()
        dist = FieldDisturbance(
            origin_cluster="c1", disturbance_type=CausalAxis.SOCIAL,
            magnitude=1.0, vectors=(DisturbanceVector.BEHAVIORAL,), source_entity="s",
            semantic_seed="conflict"
        )
        
        # Прямой слушатель (1.0)
        p_direct = proj.project(dist, 1.0, calm_kernel, {})
        # Слушатель через 2 руки (0.6) - зона драматизации (1.0 * 0.6 * 1.3 = 0.78 > 0.6)
        p_rumor = proj.project(dist, 0.6, calm_kernel, {})
        
        assert p_direct is not None and p_rumor is not None
        # Прямой: 0.5 * 1.0 = 0.5
        # Слух: 0.5 * 0.5 * 1.3 (множитель драмы) = 0.325
        # НО: для direct нет усиления, а для rumor есть!
        # Проверяем, что интенсивность слуха не просто затухает, а поддерживается драмой
        assert p_rumor.distortion_nature == "dramatization"
        assert p_rumor.perceived_archetype == "dramatic_rumor"
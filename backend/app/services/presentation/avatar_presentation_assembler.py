from __future__ import annotations
# path: backend/app/services/presentation/avatar_presentation_assembler.py
# Назначение: Перевод Simulation Truth (body_state, psyche) в Frontend Phenomenological Projection (AvatarStateDTO).
# Зависимости: app.domain.snapshot, typing
# Основные сущности: assemble_avatar_presentation
"""
TODO: В будущем этот слой может быть расширен до полноценного Avatar Presentation Engine, который будет учитывать не только текущие параметры здоровья и психики, но и динамические эффекты травм, психологических состояний и даже внешних факторов (например, освещение, окружение) для создания более богатой и адаптивной визуальной проекции. Но для MVP достаточно базового транслятора параметров в дискретные состояния и простые визуальные эффекты.

"""


from typing import Any, Dict

from app.domain.snapshot import (
    AvatarStateDTO,
    MentalPresentationState,
    PhysicalPresentationState,
)


def assemble_avatar_presentation(player_dict: Dict[str, Any]) -> AvatarStateDTO:
    """Переводит сырой стейт аватара в феноменологическую проекцию для фронтенда.

    НЕ использует хардкор чисел. Только пороговые переходы в визуальные состояния.
    Если аватара нет — возвращает дефолтный (здоровый) стейт.
    """
    if not player_dict:
        return AvatarStateDTO()

    body = player_dict.get("body_state", {})
    psyche = player_dict.get("psyche", {})

    # --- Извлечение сырых данных с безопасными дефолтами ---
    # ADR-094: pain и fatigue хранятся в 0-100 (StateApplicator SSOT).
    # Все пороги в этом ассемблере — 0-1. Нормализация обязательна.
    pain = float(body.get("pain", 0.0)) / 100.0
    fatigue = float(body.get("fatigue", 0.0)) / 100.0
    blood_loss = float(body.get("blood_loss", 0.0))
    consciousness = float(body.get("consciousness", 1.0))
    life_status = str(body.get("life_status", "ALIVE"))  # ADR-127: feedback смерти

    fear = float(psyche.get("fear", 0.0))
    stress = float(psyche.get("stress", 0.0))
    willpower = float(psyche.get("willpower", 1.0))

    # --- 1. Физическая проекция ---
    phys_state = PhysicalPresentationState.HEALTHY
    if consciousness < 0.3:
        phys_state = PhysicalPresentationState.DYING
    elif blood_loss > 0.5:
        phys_state = PhysicalPresentationState.BLEEDING
    elif pain > 0.8:
        phys_state = PhysicalPresentationState.CRIPPLED
    elif pain > 0.5 or fatigue > 0.7:
        phys_state = PhysicalPresentationState.WOUNDED

    # --- 2. Ментальная проекция ---
    mental_state = MentalPresentationState.CALM
    mental_strain = stress + fear

    if willpower < 0.2:
        mental_state = MentalPresentationState.BROKEN
    elif mental_strain > 1.5:
        mental_state = MentalPresentationState.DISSOCIATING
    elif fear > 0.8:
        mental_state = MentalPresentationState.PANICKED
    elif mental_strain > 0.7:
        mental_state = MentalPresentationState.STRESSED

    # --- 3. Феноменологические скаляры (Непрерывные векторы для оптического рендера) ---
    # Бэкенд вычисляет структурное давление, Фронтенд генерирует кино.

    # Стабильность восприятия: чистота сенсорного потока (1.0 = идеальное зрение/слух)
    perceptual_stability = max(
        0.0, min(1.0, consciousness - (pain * 0.2) - (blood_loss * 0.3))
    )

    # Когнитивная когерентность: хватка за реальность (1.0 = полное понимание происходящего)
    cognitive_coherence = max(
        0.0,
        min(
            1.0,
            willpower - (fear * 0.3) - (stress * 0.3) - ((1.0 - consciousness) * 0.5),
        ),
    )

    # Сенсорный шум: галлюцинаторный/болевой фон
    sensory_noise = max(
        0.0, min(1.0, (pain * 0.4) + (blood_loss * 0.5) + ((1.0 - consciousness) * 0.6))
    )

    # Моторное расстройство: тремор, замедление
    motor_disruption = max(
        0.0, min(1.0, (pain * 0.5) + (fatigue * 0.4) + ((1.0 - consciousness) * 0.8))
    )

    # Перцептивная задержка: время сборки реальности (шок, диссоциация)
    perceptual_latency = max(
        0.0,
        min(1.0, ((1.0 - cognitive_coherence) * 0.7) + ((1.0 - consciousness) * 0.5)),
    )

    # Скорость возврата в норму (инерция восстановления сознания)
    reality_reconciliation_rate = max(
        0.05, min(1.0, willpower * 0.7 + (1.0 - fatigue) * 0.3)
    )

    # Визуальные маркеры
    blood_visibility = min(1.0, blood_loss * 1.5)

    # --- 4. Аудио и Нарратив ---
    if consciousness < 0.3:
        breathing_profile = "gasping"
        posture_state = "collapsed"
    elif pain > 0.7:
        breathing_profile = "heavy"
        posture_state = "hunched"
    elif mental_strain > 1.2:
        breathing_profile = "hyperventilating"
        posture_state = "hunched"
    else:
        breathing_profile = "calm"
        posture_state = "upright"

    # --- DEATH OVERRIDE (ADR-127) — смерть перекрывает ВСЕ проекции ---
    if life_status == "DEAD":
        phys_state = PhysicalPresentationState.DEAD
        mental_state = MentalPresentationState.BROKEN
        perceptual_stability = 0.0
        cognitive_coherence = 0.0
        sensory_noise = 1.0
        motor_disruption = 1.0
        perceptual_latency = 1.0
        reality_reconciliation_rate = 0.0
        breathing_profile = "none"
        posture_state = "collapsed"

    # ADR-039: Извлечение конфликта воли (если StateApplicатор его записал)
    will_data = player_dict.get("will_conflict_data", {})

    return AvatarStateDTO(
        physical_state=phys_state,
        mental_state=mental_state,
        perceptual_stability=perceptual_stability,
        cognitive_coherence=cognitive_coherence,
        sensory_noise=sensory_noise,
        motor_disruption=motor_disruption,
        perceptual_latency=perceptual_latency,
        reality_reconciliation_rate=reality_reconciliation_rate,
        blood_visibility=blood_visibility,
        breathing_profile=breathing_profile,
        posture_state=posture_state,
        will_resistance=float(will_data.get("resistance", 0.0)),
        embodied_vector=will_data.get("embodied_vector"),
        life_status=life_status,
    )

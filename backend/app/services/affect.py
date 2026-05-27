# path: backend/app/services/affect.py
# Назначение: Аффективная Резонансная Система (ADR-031 Extension).
# Зависимости: app.domain.intent, app.models.will, app.models.affect, app.models.cfrm
# Основные сущности: scan_affective_resonance, distort_pressure

"""
Система Аффекта — это не эмоциональный бафф.
Это искажение интерпретации давления реальности через призму прошлого опыта.

Архитектурный принцип:
Detection (Resonance) и Mutation (Distortion) разделены.
Иначе мы теряем explainability и убиваем future AI introspection.

TODO:
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

from app.domain.intent import IntentDTO
from app.models.affect import AffectiveImprint, ResonanceProfile, ResponseBias
from app.models.cfrm import PerceivedPhenomenon, PsychologicalPressure
from app.models.will import IntentPressureProfile, WillState

logger = logging.getLogger(__name__)


# --- СЛОЙ 1: RESONANCE DETECTION (PURE FUNCTION) ---

def scan_affective_resonance(
    intent: IntentDTO,
    psych_pressure: Optional[PsychologicalPressure],
    phenomenon: Optional[PerceivedPhenomenon],
    imprints: Tuple[AffectiveImprint, ...],
) -> ResonanceProfile:
    """Сканирует аффективную память на резонанс с текущим контекстом.
    
    НЕ мутирует давление. Только фиксирует совпадение смысловых паттернов.
    Работает на PerceivedPhenomenon и PsychologicalPressure, а не только на Intent.
    """
    if not imprints:
        return ResonanceProfile()

    triggered_ids = []
    max_trigger_strength = 0.0
    
    acc_fear = 0.0
    acc_humiliation = 0.0
    acc_domination = 0.0
    acc_violence = 0.0
    acc_abandonment = 0.0
    
    # Сбор семантического контекста текущего момента
    # ADR-035: Приоритет semantic_action из parameters. Защита от AttributeError и None.
    _action = (getattr(intent, 'parameters', None) and intent.parameters.semantic_action 
               or getattr(intent, 'action', "") or "").lower()
    _target = (getattr(intent, 'parameters', None) and intent.parameters.target_reference 
               or getattr(intent, 'target', "") or "").lower()
    context_tags = set()
    if _action:
        context_tags.add(_action)
    if _target:
        context_tags.add(_target)
    if phenomenon:
        if phenomenon.perceived_archetype:
            context_tags.add(phenomenon.perceived_archetype.lower())
        if phenomenon.distortion_nature:
            context_tags.add(phenomenon.distortion_nature.lower())
    # Добавляем теги из давления реальности (если есть)
    if psych_pressure:
        if psych_pressure.fear > 0.5: context_tags.add("threatening")
        if psych_pressure.aggression_trigger > 0.5: context_tags.add("hostile")
        if psych_pressure.dominance_shift > 0.5: context_tags.add("dominant")

    for imprint in imprints:
        # Вычисление перекрытия триггеров и контекста
        overlap = len(set(imprint.trigger_tags) & context_tags)
        if overlap == 0:
            continue
            
        # Сила триггера зависит от количества совпадений и давности
        match_ratio = overlap / len(imprint.trigger_tags) if imprint.trigger_tags else 0
        # Свежие и подкрепленные травмы резонируют сильнее
        reinforcement_factor = 1.0 + imprint.reinforcement
        
        current_strength = match_ratio * reinforcement_factor
        if current_strength > max_trigger_strength:
            max_trigger_strength = current_strength
            
        triggered_ids.append(imprint.source_entity_id)
        
        # Аккумуляция сигнатур давления
        acc_fear += imprint.fear_signature * match_ratio
        acc_humiliation += imprint.humiliation_signature * match_ratio
        # Боль может резонировать как насилие или доминирование
        acc_violence += imprint.pain_signature * match_ratio
        acc_domination += imprint.humiliation_signature * match_ratio * 0.5
        # Потеря доверия может резонировать как покинутость
        if imprint.trust_shift < -0.3:
            acc_abandonment += abs(imprint.trust_shift) * match_ratio

    if not triggered_ids:
        return ResonanceProfile()

    # Определение certainty и dissociation
    certainty_mod = -max_trigger_strength * 0.2  # Травма снижает уверенность
    dissociation_risk = max_trigger_strength * 0.3 if acc_humiliation > 0.5 else 0.0

    # Clamp значений
    max_trigger_strength = min(1.0, max_trigger_strength)

    return ResonanceProfile(
        triggered_imprints=tuple(triggered_ids),
        fear_resonance=min(1.0, acc_fear),
        humiliation_resonance=min(1.0, acc_humiliation),
        domination_resonance=min(1.0, acc_domination),
        violence_resonance=min(1.0, acc_violence),
        abandonment_resonance=min(1.0, acc_abandonment),
        certainty_modifier=certainty_mod,
        dissociation_risk=dissociation_risk,
        trigger_strength=max_trigger_strength,
        dominant_bias=ResponseBias.FEAR # Базовый bias, переопределяется в distort_pressure на основе психики
    )


# --- СЛОЙ 2: PRESSURE DISTORTION (PURE FUNCTION) ---

def distort_pressure(
    base_pressure: IntentPressureProfile,
    resonance: ResonanceProfile,
    psyche: Dict[str, float],
) -> IntentPressureProfile:
    """Искажает базовое давление через призму травматического резонанса.
    
    Травма ≠ страх. Одна и та же травма может породить ярость, ступор или подчинение.
    Зависит от Personality Matrix (psyche).
    """
    if resonance.trigger_strength < 0.01:
        return base_pressure

    # Извлечение черт личности для определения ResponseBias
    fear = psyche.get("fear", 0.5)
    aggression = psyche.get("aggression", 0.5)
    identity_rigidity = psyche.get("identity_rigidity", 0.5)
    shame = psyche.get("shame", 0.5)

    # Определение доминирующего паттерна искажения
    dominant_bias = _determine_response_bias(resonance, fear, aggression, identity_rigidity, shame)

    # Базовый множитель искажения
    distortion_amp = 1.0 + resonance.trigger_strength

    # Применение искажения в зависимости от Bias
    d_violence = base_pressure.violence
    d_humiliation = base_pressure.humiliation
    d_self_risk = base_pressure.self_risk
    d_social = base_pressure.social_exposure
    d_moral = base_pressure.moral_violation
    d_identity = base_pressure.identity_deviation
    d_taboo = base_pressure.taboo_intensity

    if dominant_bias == ResponseBias.FEAR:
        d_self_risk *= distortion_amp * (1 + resonance.fear_resonance)
        d_violence *= distortion_amp * (1 + resonance.violence_resonance * 0.5)
        
    elif dominant_bias == ResponseBias.AGGRESSION:
        # Страх конвертируется в гнев (насилие)
        d_violence *= distortion_amp * (1 + resonance.violence_resonance)
        d_identity *= distortion_amp * 0.8 # Агрессия защищает идентичность, но создает риск
        d_self_risk *= 0.7 # Агрессия снижает восприятие риска
        
    elif dominant_bias == ResponseBias.FREEZE:
        # Паралич воли, усиление давления со всех сторон
        d_humiliation *= distortion_amp * (1 + resonance.humiliation_resonance)
        d_social *= distortion_amp
        d_self_risk *= distortion_amp
        
    elif dominant_bias == ResponseBias.SUBMISSION:
        # Смирение, усиление морального давления и идентичности
        d_moral *= distortion_amp * (1 + resonance.domination_resonance)
        d_identity *= distortion_amp * (1 + resonance.humiliation_resonance * 0.5)
        d_social *= distortion_amp
        
    elif dominant_bias == ResponseBias.DISSOCIATION:
        # Отстранение, потеря моральных ограничителей, рост идентитетного урона
        d_identity *= distortion_amp * 1.5 # Риск распада личности
        d_moral *= 0.5 # Мораль больше не ограничивает
        d_taboo *= distortion_amp # Табу рушатся

    # Влияние certainty и dissociation_risk
    if resonance.certainty_modifier < 0:
        d_self_risk *= (1 + abs(resonance.certainty_modifier)) # Неуверенность повышает риск

    return IntentPressureProfile(
        violence=min(1.0, d_violence),
        humiliation=min(1.0, d_humiliation),
        self_risk=min(1.0, d_self_risk),
        social_exposure=min(1.0, d_social),
        moral_violation=min(1.0, d_moral),
        identity_deviation=min(1.0, d_identity),
        trauma_trigger=min(1.0, base_pressure.trauma_trigger + resonance.trigger_strength * 0.5),
        taboo_intensity=min(1.0, d_taboo)
    )


def _determine_response_bias(
    resonance: ResonanceProfile,
    fear: float,
    aggression: float,
    identity_rigidity: float,
    shame: float,
) -> ResponseBias:
    """Определяет, как психика трансформирует резонанс в реакцию."""
    if resonance.dissociation_risk > 0.7 and identity_rigidity < 0.3:
        return ResponseBias.DISSOCIATION

    # Высокая агрессия конвертирует страх/насилие в ярость
    if aggression > 0.7 and resonance.violence_resonance > 0.3:
        return ResponseBias.AGGRESSION

    # Высокий стыд + ригидность = ступор
    if shame > 0.7 and identity_rigidity > 0.7 and resonance.humiliation_resonance > 0.3:
        return ResponseBias.FREEZE

    # Высокий страх + покинутость = подчинение
    if fear > 0.7 and resonance.abandonment_resonance > 0.5:
        return ResponseBias.SUBMISSION

    # Дефолтный паттерн
    if fear > aggression:
        return ResponseBias.FEAR


# --- СЛОЙ 3: AFFECTIVE DECAY (PHASE 0.5) ---

def decay_affective_imprints(
    imprints: Tuple[AffectiveImprint, ...], 
    delta_time: float,
    current_game_time: int
) -> Tuple[AffectiveImprint, ...]:
    """Phase 0.5: Leaky integrator для аффективной памяти.
    
    Травмы затухают со временем, если не подкрепляются.
    reinforcement -= decay_rate * delta_time.
    """
    surviving = []
    for imp in imprints:
        # Травмы теряют силу, если не резонируют
        new_reinforcement = imp.reinforcement - (imp.decay_rate * 0.05 * delta_time)
        if new_reinforcement < 0.05:
            continue # Травма зажила или забыта
            
        new_imp = replace(imp, reinforcement=max(0.0, new_reinforcement))
        surviving.append(new_imp)
        
    return tuple(surviving)


# --- СЛОЙ 4: AFFECTIVE CONDITIONING (PHASE 1) ---

def apply_conditioning(
    imprints: Tuple[AffectiveImprint, ...],
    resonance: ResonanceProfile,
    will_response: WillResponseDTO,
    intent: IntentDTO,
    current_game_time: int
) -> Tuple[AffectiveImprint, ...]:
    """Phase 1: Reinforce triggered imprints or create new ones.
    
    Conditioning = обучение через боль. 
    Если травма резонировала и вола была подавлена — травма укрепляется (PTSD/Conditioning).
    Если травма новая — создаётся импринт.
    """
    from dataclasses import replace as dc_replace
    
    updated_imprints = list(imprints)
    triggered_ids = set(resonance.triggered_imprints)
    
    # 1. Sensitization: Укрепление существующих травм при резонансе
    if will_response.identity_damage > 0:
        for i, imp in enumerate(updated_imprints):
            if imp.source_entity_id in triggered_ids:
                # Травма подтверждена опытом: reinforcement растёт, decay замедляется
                new_reinforcement = min(1.0, imp.reinforcement + 0.15 * will_response.identity_damage)
                new_decay_rate = max(0.01, imp.decay_rate - 0.05) # Травма забывается медленнее
                updated_imprints[i] = dc_replace(imp, 
                    reinforcement=new_reinforcement, 
                    decay_rate=new_decay_rate,
                    last_triggered_at=current_game_time
                )
                
    # 2. New Trauma: Создание импринта при свежем уроне идентичности без резонанса
    if will_response.identity_damage > 0.2 and resonance.trigger_strength < 0.1:
        # Это новое переживание, которого не было в памяти
        
        # ИНФЕРЕНС УНИЖЕНИЯ: Унижение = подавление воли под социальным давлением или угрозой
        # Если воля была сломлена (подчинение, неохота, диссоциация) — это унизительно
        is_submissive_state = will_response.state in (WillState.RELUCTANT, WillState.SUBMISSION, WillState.BROKEN, WillState.CONDITIONED)
        
        humiliation = 0.0
        if is_submissive_state:
            humiliation = 0.5 # Базовое унижение от подчинения
            # Угрозы и оскорбления усиливают унижение
            if "threaten" in _action or "insult" in _action:
                humiliation += 0.3
                
        # Проверка эмоций: если есть стыд или позор — тоже унижение
        for emo in will_response.generated_emotions:
            if hasattr(emo, 'emotion_tag') and emo.emotion_tag in ("shame", "humiliation", "mortification"):
                humiliation += 0.4
                
        new_imp = AffectiveImprint(
            source_entity_id=_target or "unknown",
            trigger_tags=(_action,), # Базовый тег
            pain_signature=0.5 if "attack" in _action else 0.1,
            fear_signature=will_response.fear_delta,
            humiliation_signature=round(min(1.0, humiliation), 2), # Унижение выведено из состояния воли
            trust_shift=-0.2,
            reinforcement=0.3, # Базовая сила
            decay_rate=0.1,   # Будет затухать, если не повторится
            created_at=current_game_time,
            last_triggered_at=current_game_time
        )
        updated_imprints.append(new_imp)
        
    return tuple(updated_imprints)
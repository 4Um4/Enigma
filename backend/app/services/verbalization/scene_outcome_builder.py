"""
SceneOutcomeBuilder — компрессор реальности для DM.

Назначение: Компрессор реальности — превращает DecisionResult[] в SceneOutcome для DM
Зависимости: decision_hub.py (DecisionResult, StateDeltas), npc_state.py (EmotionTag, WillState)
Основные сущности: SceneOutcome, NpcOutcome, TensionOutcome, PlayerOutcome

НЕ генерирует текст.
НЕ вызывает LLM.
ПРЕВРАЩАЕТ: DecisionResult[] → SceneOutcome (переживаемая проекция)

Принцип: DecisionResult = причина, SceneOutcome = результат.
DM получает результат — он станет рассказчиком, не аналитиком.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from app.services.npc.decision_hub import DecisionResult, StateDeltas
from app.models.npc_state import EmotionTag, WillState
from app.services.verbalization.verbal_stance import VerbalStance, stance_from_decision


# ─────────────────────────────────────────────────────────────────────────────
# Выходные структуры (SceneOutcome)
# ─────────────────────────────────────────────────────────────────────────────

class TensionTrend(str, Enum):
    """Направление напряжения в сцене."""
    RISING = "rising"
    FALLING = "falling"
    SPIKE = "spike"       # резкий скачок (травма, угроза)
    STABLE = "stable"


class Visibility(str, Enum):
    """Насколько NPC заметен для игрока."""
    DIRECT = "direct"           # игрок видит NPC и его действия
    INDIRECT = "indirect"       # игрок видит следствие (звук, тень)
    HIDDEN = "hidden"           # NPC скрыт, DM может намекнуть


class LatentSignalType(str, Enum):
    """Типы скрытых сигналов — категоризация для DM."""
    TRAUMA = "trauma"                    # новая травма
    WILL_OVERRIDE = "will_override"      # смена воли (слом)
    INTEGRITY_CRACK = "integrity_crack"  # трещины в личности
    BREAK_IMMINENT = "break_imminent"    # скорый слом
    BETRAYAL_RISK = "betrayal_risk"      # риск предательства (future)


@dataclass(frozen=True)
class LatentSignal:
    """Структурированный скрытый сигнал — DM видит, игрок нет."""
    signal_type: LatentSignalType
    intensity: float                     # 0.0-1.0, насколько критично
    source: str                          # npc_id
    description: str                     # человекочитаемое описание


@dataclass(frozen=True)
class TensionOutcome:
    level: float
    trend: TensionTrend
    focus: str
    sources: Dict[str, float]            # npc_id → вклад в напряжение
    raw_stress_sum: float                # для отладки


class PsychologicalRegime(str, Enum):
    """Базовый поведенческий паттерн NPC — детерминированная проекция психики."""
    DEFENSIVE     = "defensive"       # защищает границы/территорию
    HOSTILE       = "hostile"         # открытая враждебность
    COOPERATIVE   = "cooperative"     # открыт к взаимодействию
    NEUTRAL       = "neutral"         # без выраженной позиции
    WITHDRAWN     = "withdrawn"       # замкнулся, избегает
    UNSTABLE      = "unstable"        # непредсказуем, на грани
    MANIPULATIVE  = "manipulative"    # скрытые мотивы, двойная игра


@dataclass(frozen=True)
class PsychologicalSignature:
    """Структурированная проекция психики — не текст, а вектор для нарратива."""
    regime: PsychologicalRegime
    intensity: float    # 0.0-1.0 — насколько выражен режим
    stability: float    # 0.0-1.0 — устойчивость режима (низкая = на грани смены)


@dataclass(frozen=True)
class NpcOutcome:
    npc_id: str
    intent: str
    emotion: Optional[str] = None
    salience: float = 0.0
    visibility: Visibility = Visibility.DIRECT
    visibility_confidence: float = 1.0   # 0.0-1.0, уверенность в видимости
    voice_constraints: Dict[str, str] = field(default_factory=dict)
    latent_signals: List[LatentSignal] = field(default_factory=list)
    psychological: Optional[PsychologicalSignature] = None
    stance: Optional["VerbalStance"] = None  # B.2: поведенческая форма для DM


@dataclass(frozen=True)
class PlayerOutcome:
    """Проекция действия игрока — что он пытался и что получилось."""
    intent: str                              # что игрок пытался сделать
    outcome: str                             # "success" / "fail" / "mixed"
    perceived_effect: str = ""               # что игрок ВИДИТ как результат


@dataclass(frozen=True)
class SceneOutcome:
    """
    Итоговый выход SceneOutcomeBuilder.

    Это НЕ список решений. Это проживаемая реальность для DM.
    """
    player: PlayerOutcome
    actors: List[NpcOutcome]                 # уже отсортированы по salience (высокие первые)
    scene_changes: List[str]                 # наблюдаемые изменения сцены
    tension: TensionOutcome
    latent: List[LatentSignal]               # структурированные скрытые сигналы


# ─────────────────────────────────────────────────────────────────────────────
# Контекст для расчёта (вход builder'а)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SceneContext:
    """
    Минимальный контекст для расчёта salience и visibility.
    НЕ содержит NPCState — только наблюдаемое.
    """
    # расстояния: npc_id -> метры до игрока
    distances: Dict[str, float] = field(default_factory=dict)
    # кто из NPC виден игроку (line_of_sight)
    visible_npcs: set = field(default_factory=set)
    # tier: npc_id -> "major" / "minor"
    npc_tiers: Dict[str, str] = field(default_factory=dict)
    # что пытался сделать игрок (исходный текст)
    player_action_text: str = ""
    # успех действия игрока
    player_success: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# DM Frame — перцептивная модель DM (между симуляцией и промптом)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DMFrame:
    """
    Перцептивная модель DM — то, что DM "видит".
    
    НЕ текст. НЕ промпт. Структура внимания.
    
    Разделяет:
    - focus_npcs: кто доминирует в сцене (top salience)
    - background_npcs: фон
    - tension_line: интерпретированное напряжение
    - hidden_pressure: скрытые сигналы для стиля, не содержания
    """
    focus_npcs: List[NpcOutcome]          # top 1-3 по salience
    background_npcs: List[NpcOutcome]     # остальные
    player_line: PlayerOutcome
    tension_line: str                     # интерпретированная, не число
    scene_line: List[str]                 # наблюдаемые изменения
    hidden_pressure: List[LatentSignal]   # для стиля DM, не для содержания
    voice_map: Dict[str, Dict[str, str]]  # npc_id → voice_constraints


# Порог разделения focus/background
FOCUS_NPC_CAP: int = 2


# ─────────────────────────────────────────────────────────────────────────────
# Константы (СЦЕНАРНЫЕ, НЕ МАГИЧЕСКИЕ)
# ─────────────────────────────────────────────────────────────────────────────

# Веса salience — приоритеты внимания для DM
SALIENCE_PROXIMITY_WEIGHT: float = 0.30      # ближе = заметнее
SALIENCE_EMOTIONAL_WEIGHT: float = 0.30      # сильная эмоция = заметнее
SALIENCE_RELEVANCE_WEIGHT: float = 0.25      # направлен на игрока = важнее
SALIENCE_TIER_WEIGHT: float = 0.15           # MAJOR NPC бонус

# Пороги tension
TENSION_TRAUMA_SPIKE: float = 0.3            # травма вызывает spike
TENSION_WILL_OVERRIDE_SPIKE: float = 0.4     # смена воли — критический spike
TENSION_CAP: float = 1.0                     # потолок

# Порог видимости
HIDDEN_DISTANCE: float = 15.0                # дальше — скрыт


# ─────────────────────────────────────────────────────────────────────────────
# SceneOutcomeBuilder
# ─────────────────────────────────────────────────────────────────────────────

class SceneOutcomeBuilder:
    """
    Компрессор реальности.
    
    Превращает сырые DecisionResult[] в SceneOutcome —
    структуру, готовую для DM промпта.
    
    Инвариант: на выходе НЕТ чисел, которые DM не должен видеть.
    Только: intent (строка), emotion (строка), salience (число для сортировки),
            tension (число 0-1), latent (строки).
    """

    def build(
        self,
        decisions: List[DecisionResult],
        context: SceneContext,
        state_snapshots: Optional[Dict[str, dict]] = None,
        distortion_biases: Optional[Dict[str, "DistortionProfile"]] = None,
    ) -> SceneOutcome:
        """
        Основной метод. Принимает решения + контекст, возвращает проживаемую реальность.
        
        state_snapshots: npc_id → реальное состояние (без искажения)
        distortion_biases: npc_id → bias от CognitiveDistortion
        """
        _snapshots = state_snapshots or {}
        _biases = distortion_biases or {}

        # 1. Собираем NPC исходы с salience + психологической проекцией
        npc_outcomes = [
            self._build_npc_outcome(
                d, context,
                real_state=_snapshots.get(d.npc_id),
                distortion_bias=_biases.get(d.npc_id),
            )
            for d in decisions
        ]
        
        # 2. Сортируем по salience (высокие первые — они получают голос)
        npc_outcomes.sort(key=lambda x: x.salience, reverse=True)
        
        # 3. Собираем изменения сцены из narrative_facts
        scene_changes = self._extract_scene_changes(decisions)
        
        # 4. Считаем tension
        tension = self._compute_tension(decisions)
        
        # 5. Собираем latent сигналы
        latent = self._extract_latent(decisions)
        
        # 6. Player outcome
        player_outcome = self._build_player_outcome(context)
        
        return SceneOutcome(
            player=player_outcome,
            actors=npc_outcomes,
            scene_changes=scene_changes,
            tension=tension,
            latent=latent,
        )

    # ─── DM Frame построение ───

    def build_dm_frame(
        self,
        scene: SceneOutcome,
    ) -> DMFrame:
        """
        Превращает SceneOutcome → DMFrame (перцептивная модель DM).
        
        НЕ форматирует текст.
        НЕ делает промпт.
        Только структурирует внимание DM.
        """
        # Разделяем по salience
        focus = scene.actors[:FOCUS_NPC_CAP]
        background = scene.actors[FOCUS_NPC_CAP:]

        # Интерпретируем tension в строку
        tension_line = self._interpret_tension(scene.tension)

        # Voice map для проксирования
        voice_map = {
            a.npc_id: a.voice_constraints
            for a in scene.actors
            if a.voice_constraints  # только если есть constraints
        }

        return DMFrame(
            focus_npcs=focus,
            background_npcs=background,
            player_line=scene.player,
            tension_line=tension_line,
            scene_line=scene.scene_changes,
            hidden_pressure=scene.latent,
            voice_map=voice_map,
        )

    def _interpret_tension(
        self,
        tension: TensionOutcome,
    ) -> str:
        """
        Интерпретирует tension в человекочитаемую строку для DM.
        
        НЕ числа — это перцептивная модель, не аналитическая.
        """
        if tension.level < 0.1:
            return "Сцена спокойная"
        
        if tension.trend == TensionTrend.SPIKE:
            return "Резкий скачок напряжения — критический момент"
        
        if tension.trend == TensionTrend.RISING:
            if tension.level > 0.6:
                return "Напряжение растёт быстро — близко к кульминации"
            return "Напряжение нарастает"
        
        if tension.trend == TensionTrend.FALLING:
            return "Напряжение спадает"
        
        # STABLE
        if tension.level > 0.4:
            return "Стабильное высокое напряжение — потенциальный конфликт"
        return "Стабильная обстановка"

    def to_dm_prompt_block(
        self,
        frame: DMFrame,
    ) -> str:
        """
        Превращает DMFrame → текстовый блок для DM промпта.
        
        Формат совместим с текущим dm_agent.py:
        - "Что NPC сделали/сказали"
        - "Физические действия NPC"
        """
        blocks = []
        
        # 1. Фокусные NPC — детально + stance + психологическая проекция
        if frame.focus_npcs:
            focus_lines = []
            for npc in frame.focus_npcs:
                line = f"- {npc.npc_id}: {npc.intent}"
                if npc.stance:
                    line += f" [{npc.stance.to_prompt_line()}]"
                if npc.emotion:
                    line += f" ({npc.emotion})"
                # ProjectionLayer — категория, не числа (Fog of War)
                if npc.psychological:
                    p = npc.psychological
                    int_label = "ярко" if p.intensity > 0.7 else "умеренно" if p.intensity > 0.4 else "слабо"
                    stab_label = "стабильно" if p.stability > 0.7 else "на грани" if p.stability > 0.4 else "нестабильно"
                    line += f" [{p.regime.value}, {int_label}, {stab_label}]"
                if npc.visibility == Visibility.HIDDEN:
                    line += " [скрыт, но влияние ощутимо]"
                focus_lines.append(line)
            blocks.append("Ключевые NPC (фокус сцены):\n" + "\n".join(focus_lines))
        
        # 2. Фоновые NPC — кратко
        if frame.background_npcs:
            bg_names = [n.npc_id for n in frame.background_npcs]
            blocks.append(f"Фоновые NPC: {', '.join(bg_names)}")
        
        # 3. Напряжение сцены
        if frame.tension_line != "Сцена спокойная":
            blocks.append(f"Напряжение: {frame.tension_line}")
        
        # 4. Изменения сцены
        if frame.scene_line:
            blocks.append("Изменения в сцене:\n" + "\n".join(f"- {c}" for c in frame.scene_line))
        
        # Скрытое давление — только если критично
        critical_latent = [
            s for s in frame.hidden_pressure
            if s.intensity >= 0.7
        ]
        if critical_latent:
            latent_lines = [f"- {s.description}" for s in critical_latent]
            blocks.append("Скрытое давление (для стиля, не для прямого описания):\n" + "\n".join(latent_lines))
        
        if not blocks:
            return "NPC не предпринимают значимых действий"
        
        result = "\n\n".join(blocks)
        print(f"[DM_PROMPT_BLOCK]\n{result}\n[/DM_PROMPT_BLOCK]")
        return result

    # ─── Внутренние методы ───

    def _project_psychology(
        self,
        real_state: dict,
        distortion_bias: Optional["DistortionProfile"] = None,
        intent: str = "idle",
    ) -> Optional[PsychologicalSignature]:
        """
        ProjectionLayer — субъективная интерпретация объективного состояния.
        
        Числа остаются реальными, интерпретация — искажённая.
        LLM получает regime (категория), не числа (Fog of War).
        """
        if not real_state:
            return None

        psyche = real_state.get("psyche", {})
        social = real_state.get("social_stats", {})

        stress = float(psyche.get("stress", 0))
        trust = float(social.get("trust", 0))
        fear = float(social.get("fear_of_player", 0))
        integrity = float(psyche.get("identity_integrity", 1.0))

        # Искажения от CognitiveDistortion
        threat_bias   = distortion_bias.threat_bias   if distortion_bias else 0.0
        trust_bias    = distortion_bias.trust_bias    if distortion_bias else 0.0
        salience_bias = distortion_bias.salience_bias if distortion_bias else 0.0

        # ── Определение regime (детерминированное, не LLM) ──
        regime = PsychologicalRegime.NEUTRAL

        # Высокая угроза (реальная + искажённая)
        # TODO: пороги снижены для тестирования — вернуть к 30/60 после фикса дельт
        effective_threat = fear + threat_bias * 50
        if effective_threat > 20:
            regime = PsychologicalRegime.HOSTILE
        elif effective_threat > 5:
            regime = PsychologicalRegime.DEFENSIVE

        # Низкое доверие (усиленное искажением)
        effective_trust = trust + trust_bias * 30
        if effective_trust < -10 and regime == PsychologicalRegime.NEUTRAL:
            regime = PsychologicalRegime.WITHDRAWN

        # Высокий стресс + нестабильность
        if stress > 30 and integrity < 0.6:
            regime = PsychologicalRegime.UNSTABLE
        elif stress > 50:
            regime = PsychologicalRegime.UNSTABLE

        # Позитивные состояния
        if effective_trust > 10 and stress < 20:
            regime = PsychologicalRegime.COOPERATIVE

        # Скрытые мотивы: низкая целостность + средний стресс
        if integrity < 0.5 and 20 < stress < 40 and regime == PsychologicalRegime.NEUTRAL:
            regime = PsychologicalRegime.MANIPULATIVE

        # ── Intent override: если числа ещё не накоплены, intent даёт fallback ──
        # Применяется только когда режим всё ещё NEUTRAL (числа не перебили)
        _INTENT_REGIME: dict[str, PsychologicalRegime] = {
            "flee":    PsychologicalRegime.DEFENSIVE,
            "attack":  PsychologicalRegime.HOSTILE,
            "warn":    PsychologicalRegime.DEFENSIVE,
            "report":  PsychologicalRegime.WITHDRAWN,
            "resist":  PsychologicalRegime.HOSTILE,
            "hide":    PsychologicalRegime.DEFENSIVE,
        }
        if regime == PsychologicalRegime.NEUTRAL and intent in _INTENT_REGIME:
            regime = _INTENT_REGIME[intent]

        # ── Intensity (насколько выражен режим) ──
        intensity = min(1.0, (stress / 100.0) + abs(effective_threat - 30) / 70.0 + salience_bias)
        intensity = max(0.0, min(1.0, intensity))

        # ── Stability (на грани ли смены) ──
        stability = integrity
        if stress > 50:
            stability -= (stress - 50) * 0.01
        stability = max(0.0, min(1.0, stability))

        return PsychologicalSignature(
            regime=regime,
            intensity=round(intensity, 2),
            stability=round(stability, 2),
        )

    def _build_npc_outcome(
        self,
        decision: DecisionResult,
        context: SceneContext,
        real_state: Optional[dict] = None,
        distortion_bias: Optional[dict] = None,
    ) -> NpcOutcome:
        """Превращает один DecisionResult в NpcOutcome с salience."""
        npc_id = decision.npc_id
        
        # Salience — ключевой параметр
        salience = self._compute_salience(decision, context)
        
        # Visibility — на основе расстояния и LOS
        visibility = self._compute_visibility(npc_id, context)
        
        # Emotion — из deltas, если есть
        emotion = decision.deltas.emotion_tag.value if decision.deltas.emotion_tag else None
        
        # Latent signals для этого NPC
        npc_latent = self._extract_npc_latent(decision)
        
        # Voice constraints — пока заглушка, будет заполнена из NPC профиля
        voice_constraints = self._build_voice_constraints(npc_id, context)
        
        # ProjectionLayer — субъективная интерпретация психики
        _intent_str = decision.intent.value if hasattr(decision.intent, 'value') else str(decision.intent)
        psychological = self._project_psychology(real_state, distortion_bias or {}, intent=_intent_str)
        
        # B.2: Stance — поведенческая форма для DM prompt
        stance = None
        if real_state:
            _psyche = real_state.get("psyche", {})
            _social = real_state.get("social_stats", {})
            _stress = float(_psyche.get("stress", 0))
            _fear = float(_social.get("fear_of_player", 0))
            _trust = float(_social.get("trust", 0))
            _integrity = float(_psyche.get("identity_integrity", 1.0))
            _collapse = _integrity < 0.3
            stance = stance_from_decision(
                intent=decision.intent.value if hasattr(decision.intent, 'value') else str(decision.intent),
                stress=_stress,
                fear=_fear,
                trust=_trust,
                emotion_tag=emotion,
                collapse=_collapse,
            )
        
        return NpcOutcome(
            npc_id=npc_id,
            intent=decision.intent.value if hasattr(decision.intent, 'value') else str(decision.intent),
            emotion=emotion,
            salience=salience,
            visibility=visibility,
            voice_constraints=voice_constraints,
            latent_signals=npc_latent,
            psychological=psychological,
            stance=stance,
        )

    def _compute_salience(
        self,
        decision: DecisionResult,
        context: SceneContext,
    ) -> float:
        """
        Формула salience — насколько NPC важен в сцене.
        
        Компоненты:
        - proximity: ближе = заметнее
        - emotional_intensity: сильная эмоция = заметнее
        - action_relevance: направлен на игрока = важнее
        - is_major_tier: MAJOR NPC бонус
        """
        npc_id = decision.npc_id
        deltas = decision.deltas
        
        # 1. Proximity (0-1, ближе = выше)
        distance = context.distances.get(npc_id, 10.0)
        proximity = max(0.0, 1.0 - (distance / 15.0))  # 15м = 0, 0м = 1
        
        # 2. Emotional intensity (0-1)
        # Сумма абсолютных изменений стресса и страха
        emotional_raw = abs(deltas.stress_delta) + abs(deltas.fear_delta)
        emotional_intensity = min(1.0, emotional_raw / 0.5)  # 0.5 суммарной дельты = максимум
        
        # 3. Action relevance (0 или 1)
        # NPC направляет intent на игрока
        relevance = 1.0 if decision.intent_target == "player" else 0.0
        
        # 4. Tier bonus (0 или 1)
        tier = context.npc_tiers.get(npc_id, "minor")
        is_major = 1.0 if tier == "major" else 0.0
        
        # Взвешенная сумма
        salience = (
            proximity * SALIENCE_PROXIMITY_WEIGHT +
            emotional_intensity * SALIENCE_EMOTIONAL_WEIGHT +
            relevance * SALIENCE_RELEVANCE_WEIGHT +
            is_major * SALIENCE_TIER_WEIGHT
        )
        
        return round(max(0.0, min(1.0, salience)), 3)

    def _compute_visibility(
        self,
        npc_id: str,
        context: SceneContext,
    ) -> Visibility:
        """Определяет видимость NPC для игрока."""
        is_visible = npc_id in context.visible_npcs
        distance = context.distances.get(npc_id, 10.0)
        
        if not is_visible or distance > HIDDEN_DISTANCE:
            return Visibility.HIDDEN
        elif distance > 8.0:
            return Visibility.INDIRECT
        else:
            return Visibility.DIRECT

    def _compute_tension(
        self,
        decisions: List[DecisionResult],
    ) -> TensionOutcome:
        if not decisions:
            return TensionOutcome(
                level=0.0,
                trend=TensionTrend.STABLE,
                focus="environment",
                sources={},
                raw_stress_sum=0.0,
            )
        
        # Суммируем стресс и страх
        raw_stress = sum(abs(d.deltas.stress_delta) for d in decisions)
        raw_fear = sum(abs(d.deltas.fear_delta) for d in decisions)
        raw_sum = raw_stress + raw_fear
        
        # Нормализация (0.5 суммарной дельты = максимум напряжения)
        level = min(TENSION_CAP, raw_sum / 0.5)
        
        # Определяем trend
        has_trauma = any(d.deltas.new_trauma for d in decisions)
        has_will_override = any(d.deltas.will_state_override for d in decisions)
        
        if has_trauma or has_will_override:
            trend = TensionTrend.SPIKE
        elif raw_sum > 0.3:
            trend = TensionTrend.RISING
        elif raw_sum < 0.05:
            trend = TensionTrend.FALLING
        else:
            trend = TensionTrend.STABLE
        
        # Фокус — кто генерирует больше всего напряжения
        focus = self._compute_tension_focus(decisions)
        
        # Sources — вклад каждого NPC
        sources: Dict[str, float] = {}
        for d in decisions:
            contribution = abs(d.deltas.stress_delta) + abs(d.deltas.fear_delta)
            if contribution > 0.01:  # фильтруем шум
                sources[d.npc_id] = round(contribution, 3)
        
        return TensionOutcome(
            level=round(level, 3),
            trend=trend,
            focus=focus,
            sources=sources,
            raw_stress_sum=round(raw_sum, 3),
        )

    def _compute_tension_focus(
        self,
        decisions: List[DecisionResult],
    ) -> str:
        """Определяет, кто/что фокусирует внимание в сцене."""
        if not decisions:
            return "environment"
        
        # NPC с максимальным вкладом в напряжение
        max_contributor = max(
            decisions,
            key=lambda d: abs(d.deltas.stress_delta) + abs(d.deltas.fear_delta),
        )
        max_contribution = abs(max_contributor.deltas.stress_delta) + abs(max_contributor.deltas.fear_delta)
        
        # Если вклад незначителен — фокус на среде
        if max_contribution < 0.1:
            return "environment"
        
        return max_contributor.npc_id

    def _extract_scene_changes(
        self,
        decisions: List[DecisionResult],
    ) -> List[str]:
        """Извлекает наблюдаемые изменения сцены из narrative_facts."""
        changes = []
        seen: set[str] = set()
        for d in decisions:
            if d.narrative_fact:
                fact_text = d.narrative_fact if isinstance(d.narrative_fact, str) else str(d.narrative_fact)
                if fact_text and fact_text not in seen:
                    seen.add(fact_text)
                    changes.append(fact_text)
        return changes

    def _extract_latent(
        self,
        decisions: List[DecisionResult],
    ) -> List[LatentSignal]:
        """Собирает скрытые сигналы со всех NPC для DM."""
        latent: List[LatentSignal] = []
        for d in decisions:
            npc_latent = self._extract_npc_latent(d)
            latent.extend(npc_latent)
        return latent

    def _extract_npc_latent(
        self,
        decision: DecisionResult,
    ) -> List[LatentSignal]:
        signals: List[LatentSignal] = []
        deltas = decision.deltas
        npc_id = decision.npc_id
        
        if deltas.new_trauma:
            signals.append(LatentSignal(
                signal_type=LatentSignalType.TRAUMA,
                intensity=min(1.0, abs(deltas.stress_delta) / 0.5),
                source=npc_id,
                description=f"новая травма: {deltas.new_trauma}",
            ))
        
        if deltas.will_state_override:
            signals.append(LatentSignal(
                signal_type=LatentSignalType.WILL_OVERRIDE,
                intensity=0.9,  # смена воли всегда критична
                source=npc_id,
                description=f"смена воли на {deltas.will_state_override.value}",
            ))
        
        if deltas.identity_integrity_delta < -0.2:
            crack_intensity = min(1.0, abs(deltas.identity_integrity_delta) / 0.5)
            signals.append(LatentSignal(
                signal_type=LatentSignalType.INTEGRITY_CRACK,
                intensity=crack_intensity,
                source=npc_id,
                description=f"трещины в личности (integrity -{abs(deltas.identity_integrity_delta):.1f})",
            ))
        
        return signals

    def _build_player_outcome(
        self,
        context: SceneContext,
    ) -> PlayerOutcome:
        """Формирует проекцию действия игрока."""
        if context.player_success:
            outcome = "success"
        else:
            outcome = "fail"
        
        return PlayerOutcome(
            intent=context.player_action_text or "действие",
            outcome=outcome,
            perceived_effect="",  # TODO: заполнить из ResolutionEngine
        )

    def _build_voice_constraints(
        self,
        npc_id: str,
        context: SceneContext,
    ) -> Dict[str, str]:
        """
        Формирует voice constraints для DM.
        Пока заглушка — будет заполнена из NPC профиля.
        
        Целевая структура:
        {
            "TONE": "HARSH",
            "STYLE": "SHORT",
            "LEXICON": "rude, direct"
        }
        """
        # TODO: загрузить из NPCProfileL0.voice_profile
        return {}
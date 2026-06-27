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
from typing import Dict, List, Optional, Tuple

from app.services.npc.decision_hub import DecisionResult
from app.services.npc.legacy_delta_adapter import LegacyStateDeltaAdapter
from app.models.npc_profile import NPCProfileL0
from app.services.verbalization.verbal_stance import stance_from_decision


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
    """ADR-131: Векторное напряжение сцены — три оси + арбитраж.
    
    level = composite (для обратной совместимости потребителей).
    Полный вектор (ST/ET/NE) сохранён для NDA Engine (Шаг 2).
    """
    level: float                         # composite после арбитража
    trend: TensionTrend
    focus: str
    sources: Dict[str, float]            # npc_id → вклад в напряжение
    raw_stress_sum: float                # для отладки
    
    # ADR-131: Трёхосевая модель (Шаг 1)
    state_tension: float = 0.0           # ST: mean(affective_load) — интеграл
    event_tension: float = 0.0           # ET: sum(deltas)/0.5 — производная
    narrative_entropy: float = 0.0       # NE: 1.0 - coherence — шум восприятия
    dominant_axis: str = "ST"            # какая реальность управляет сценой
    suppression: Dict[str, float] = field(default_factory=dict)  # подавленные оси


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
    intent: str = ""
    name: str = ""
    emotion: Optional[str] = None
    gender: str = "male"  # для гендерных окончаний в narrative
    description_snippet: str = ""  # первая строка из description для DM промпта
    salience: float = 0.0
    visibility: Visibility = Visibility.DIRECT
    visibility_confidence: float = 1.0   # 0.0-1.0, уверенность в видимости
    voice_constraints: Dict[str, str] = field(default_factory=dict)
    latent_signals: List[LatentSignal] = field(default_factory=list)
    psychological: Optional[PsychologicalSignature] = None
    stance: Optional["VerbalStance"] = None  # B.2: поведенческая форма для DM
    topic: str = ""  # ФАЗА 4: тема из TopicExtractor (Устав 3.2)

    # ФАЗА 0: память и характер — для DM-промпта
    voice_profile: str = ""
    backstory: str = ""
    author_notes: str = ""
    memory_hints: Tuple[str, ...] = ()  # top-3 воспоминаний как текст


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
    # NPC к которому обращается игрок (получает salience boost)
    player_target_id: str = ""


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
        # TODO: Semantic Debt (Backlog). Epistemic Boundary (ADR-TZ08-6) закрыл утечку ментальных объектов выше по потоку.
        # r3_direct_builder передаёт сюда пустые словари. Логика внутри builder работает на дефолтах.
        # Требуется рефакторинг: переименование `real_state` → `observed_state`, удаление мёртвых веток `distortion_bias`.
        # Приоритет: LOW (non-blocking, refactor-only). Не трогать до отдельной архитектурной задачи.
        distortion_biases: Optional[Dict[str, "DistortionProfile"]] = None,
        npc_profiles: Optional[Dict[str, NPCProfileL0]] = None,
        topics: Optional[Dict[str, str]] = None,
        # ADR-131: Трёхосевая модель — вызывающий код извлекает из доменов
        npc_affective_loads: Optional[Dict[str, float]] = None,
        avatar_coherence: float = 1.0,
    ) -> SceneOutcome:
        """
        Основной метод. Принимает решения + контекст, возвращает проживаемую реальность.
        
        state_snapshots: npc_id → реальное состояние (без искажения)
        distortion_biases: npc_id → bias от CognitiveDistortion
        npc_profiles: npc_id → профиль NPC (для voice constraints)
        """
        _snapshots = state_snapshots or {}
        _profiles = npc_profiles or {}
        _biases = distortion_biases or {}
        _topics = topics or {}

        # 1. Собираем NPC исходы с salience + психологической проекцией
        npc_outcomes = [
            self._build_npc_outcome(
                d, context,
                real_state=_snapshots.get(d.npc_id),
                distortion_bias=_biases.get(d.npc_id),
                profile=_profiles.get(d.npc_id),
                topic=_topics.get(d.npc_id, ""),
            )
            for d in decisions
        ]
        
        # 2. Сортируем по salience (высокие первые — они получают голос)
        npc_outcomes.sort(key=lambda x: x.salience, reverse=True)
        
        # 3. Собираем изменения сцены из narrative_facts
        scene_changes = self._extract_scene_changes(decisions)
        
        # 4. Считаем tension (ADR-131: трёхосевая модель)
        tension = self._compute_tension(
            decisions,
            npc_affective_loads=npc_affective_loads,
            avatar_coherence=avatar_coherence,
        )
        
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
        ADR-131: level теперь = composite из TensionSynthesizer (ST/ET/NE арбитраж),
        а не чистый ET. Интерпретация остаётся скалярной — семантика осей
        выносится в ScenePhenomenology (ADR-131 Шаг 2).
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
        
        # 1. Фокусные NPC — только человекочитаемые описания (ФАЗА 3.1-3.2)
        # intent → описание действия, emotion → русское слово с гендерными окончаниями (pymorphy3)
        from app.services.verbalization.state_interpreter import (
            INTENT_DESCRIPTIONS, EMOTION_DESCRIPTIONS, _apply_gender
        )
        
        if frame.focus_npcs:
            focus_lines = []
            for npc in frame.focus_npcs:
                # intent как описание: "observe" → "наблюдает осторожно"
                intent_desc = INTENT_DESCRIPTIONS.get(
                    npc.intent if isinstance(npc.intent, str) else getattr(npc.intent, "value", str(npc.intent)),
                    "наблюдает"
                )
                gender = getattr(npc, "gender", "male")
                # ИСПРАВЛЕНО: npc_id не определён в scope цикла — только npc.
                # Должно быть npc.npc_id. До фикса любой NPC без name → NameError →
                # _dm_frame_block = "" → DM терял блок «Ключевые NPC».
                line = f"- {npc.name or npc.npc_id} {intent_desc}"
                # pronoun-подсказка для 7B — без неё модель галлюцинирует пол
                if gender not in ("male", "female", "мужской", "женский"):
                    line += " [он]"
                # description snippet — даёт модели контекст вместо галлюцинации
                if npc.description_snippet:
                    line += f" ({npc.description_snippet})"
                # ФАЗА 4: topic — якорь для LLM (Устав 3.2)
                if npc.topic:
                    line += f" [тема: {npc.topic}]"
                # emotion с гендерным окончанием через pymorphy3
                if npc.emotion:
                    emotion_key = npc.emotion if isinstance(npc.emotion, str) else getattr(npc.emotion, "value", str(npc.emotion))
                    emotion_base = EMOTION_DESCRIPTIONS.get(emotion_key, "")
                    if emotion_base:
                        emotion_desc = _apply_gender(emotion_base, gender)
                        line += f", {emotion_desc}"
                focus_lines.append(line)
            blocks.append("Ключевые NPC (фокус сцены):\n" + "\n".join(focus_lines))
        
        # ФАЗА 0: Характер и память целевого NPC
        if frame.focus_npcs:
            for npc in frame.focus_npcs:
                _npc_blocks = []
                if npc.voice_profile:
                    _npc_blocks.append(f"Голос: {npc.voice_profile}")
                if npc.backstory:
                    _npc_blocks.append(f"Биография: {npc.backstory}")
                if npc.author_notes:
                    _npc_blocks.append(f"Инструкция: {npc.author_notes}")
                if npc.memory_hints:
                    _npc_blocks.append("Воспоминания:\n" + "\n".join(f"- {m}" for m in npc.memory_hints))
                if _npc_blocks:
                    _npc_name = npc.name or npc.npc_id
                    blocks.append(f"[{ _npc_name} — характер и память]\n" + "\n".join(_npc_blocks))
        
        # 2. Фоновые NPC — кратко
        if frame.background_npcs:
            bg_names = [n.name or n.npc_id for n in frame.background_npcs]
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
            # Фоллбэк: пустой мир ≠ отсутствие контекста. LLM должна знать, что сцена спокойна.
            return "NPC не предпринимают активных действий."
        
        result = "\n\n".join(blocks)
        print(f"[DM_PROMPT_BLOCK]\n{result}\n[/DM_PROMPT_BLOCK]")
        return result

    # ─── Внутренние методы ───

    def _project_psychology(
        self,
        observed_state: dict,
        intent: str = "idle",
        emotion_tag: Optional[str] = None,
    ) -> Optional[PsychologicalSignature]:
        """
        Symbolic Interpretation Layer (Epistemic Boundary).
        
        DM выводит психологию исключительно из наблюдаемых действий (intent + emotion).
        Числовые пороги скрытой каузальности (stress/trust/fear) больше не используются 
        в DM-контуре. Внутренняя динамика остаётся в simulation layer.
        """
        if not observed_state:
            return None

        # ── Определение regime (символьная интерпретация) ──
        regime = PsychologicalRegime.NEUTRAL

        _INTENT_REGIME: dict[str, PsychologicalRegime] = {
            "flee":    PsychologicalRegime.DEFENSIVE,
            "attack":  PsychologicalRegime.HOSTILE,
            "warn":    PsychologicalRegime.DEFENSIVE,
            "report":  PsychologicalRegime.WITHDRAWN,
            "resist":  PsychologicalRegime.HOSTILE,
            "hide":    PsychologicalRegime.DEFENSIVE,
        }
        if intent in _INTENT_REGIME:
            regime = _INTENT_REGIME[intent]

        # Эмоциональная модуляция режима
        if emotion_tag == "angry" and regime == PsychologicalRegime.NEUTRAL:
            regime = PsychologicalRegime.HOSTILE
        elif emotion_tag == "fearful" and regime == PsychologicalRegime.NEUTRAL:
            regime = PsychologicalRegime.DEFENSIVE
        elif emotion_tag == "panic":
            regime = PsychologicalRegime.UNSTABLE

        # ── Intensity & Stability (статические дефолты) ──
        # В будущем могут выводиться из density of narrative_cache, 
        # но не из сырых ментальных чисел.
        intensity = 0.5 if regime != PsychologicalRegime.NEUTRAL else 0.1
        stability = 1.0 if regime == PsychologicalRegime.NEUTRAL else 0.7

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
        profile: Optional[NPCProfileL0] = None,
        topic: str = "",
    ) -> NpcOutcome:
        """Превращает один DecisionResult в NpcOutcome с salience."""
        npc_id = decision.npc_id
        
        # Salience — ключевой параметр
        salience = self._compute_salience(decision, context)
        
        # Visibility — на основе расстояния и LOS
        visibility = self._compute_visibility(npc_id, context)
        
        # Emotion — из deltas, если есть (через деградационный шлюз v2->v1)
        _legacy_d = LegacyStateDeltaAdapter.collapse(decision.deltas)
        emotion = _legacy_d.emotion_tag.value if _legacy_d.emotion_tag else None
        
        # Latent signals для этого NPC
        npc_latent = self._extract_npc_latent(decision)
        
        # Voice constraints из профиля NPC
        voice_constraints = self._build_voice_constraints(npc_id, context, profile)
        
        # Symbolic Interpretation Layer: вывод психологии из наблюдаемых действий
        _intent_str = decision.intent.value if hasattr(decision.intent, 'value') else str(decision.intent)
        psychological = self._project_psychology(real_state, intent=_intent_str, emotion_tag=emotion)
        
        # B.2: Stance — поведенческая форма для DM prompt (без числовых порогов)
        stance = stance_from_decision(intent=_intent_str, emotion_tag=emotion)
        
        # Первое предложение description — даёт модели зацепку вместо пустоты
        _desc_snippet = ""
        if isinstance(real_state, dict):
            _raw_desc = real_state.get("description", "")
            if _raw_desc:
                _first_sent = _raw_desc.split(".")[0].strip()
                if len(_first_sent) > 10:
                    _desc_snippet = _first_sent + "."

        # ФАЗА 0: извлекаем характер и память
        _voice = profile.voice_profile if profile else ""
        _backstory = profile.backstory if profile else ""
        _author_notes = profile.author_notes if profile else ""
        _memory_hints = ()
        if isinstance(real_state, dict):
            _raw_cache = real_state.get("narrative_cache", [])
            if _raw_cache:
                _hints = []
                for _item in _raw_cache[:3]:  # top-3
                    _summary = _item.get("summary", "") if isinstance(_item, dict) else getattr(_item, "summary", "")
                    _is_secret = _item.get("is_secret", False) if isinstance(_item, dict) else getattr(_item, "is_secret", False)
                    # Фильтрация: если тайна скрыта от игрока — не показываем содержание
                    _hidden_from = _item.get("hidden_from", []) if isinstance(_item, dict) else getattr(_item, "hidden_from", ())
                    if isinstance(_hidden_from, tuple):
                        _hidden_from = list(_hidden_from)
                    if _is_secret and "player" in _hidden_from:
                        # LLM знает что тайна есть, но не знает содержания
                        _tags = _item.get("tags", []) if isinstance(_item, dict) else getattr(_item, "tags", ())
                        if isinstance(_tags, tuple):
                            _tags = list(_tags)
                        _hint_tags = ", ".join(t for t in _tags[:2] if t not in ("secret",))
                        _hints.append(f"[СЕКРЕТ — НЕ РАСКРЫВАТЬ] У тебя есть тайна{_hint_tags and f' про {_hint_tags}' or ''}")
                    elif _summary:
                        _prefix = "[ТАЙНА] " if _is_secret else ""
                        _hints.append(f"{_prefix}{_summary}")
                _memory_hints = tuple(_hints)

        return NpcOutcome(
            npc_id=npc_id,
            # FIX: Используем getattr для безопасности, так как может прийти NPCPersonality вместо NPCProfileL0
            name=(getattr(profile, 'name', None) if profile else None) or (real_state.get("name") if isinstance(real_state, dict) else None) or npc_id,
            description_snippet=_desc_snippet,
            intent=decision.intent.value if hasattr(decision.intent, 'value') else str(decision.intent),
            emotion=emotion,
            gender=getattr(profile, 'gender', 'male') if profile else "male",
            salience=salience,
            visibility=visibility,
            voice_constraints=voice_constraints,
            latent_signals=npc_latent,
            psychological=psychological,
            stance=stance,
            topic=topic,
            voice_profile=_voice,
            backstory=_backstory,
            author_notes=_author_notes,
            memory_hints=_memory_hints,
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
        deltas = LegacyStateDeltaAdapter.collapse(decision.deltas)
        
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
        
        # 5. Target boost — игрок обратился к этому NPC
        is_target = 0.4 if context.player_target_id and npc_id == context.player_target_id else 0.0
        
        # Взвешенная сумма
        salience = (
            proximity * SALIENCE_PROXIMITY_WEIGHT +
            emotional_intensity * SALIENCE_EMOTIONAL_WEIGHT +
            relevance * SALIENCE_RELEVANCE_WEIGHT +
            is_major * SALIENCE_TIER_WEIGHT +
            is_target
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
        npc_affective_loads: Optional[Dict[str, float]] = None,
        avatar_coherence: float = 1.0,
    ) -> TensionOutcome:
        """ADR-131: Трёхосевая модель напряжения.
        
        Делегирует в TensionSynthesizer для вычисления ST/ET/NE.
        Сохраняет trend/sources/focus из ET-оси для backward compatibility.
        """
        # ET-компоненты — для trend/sources/focus (legacy логика)
        from app.services.npc.legacy_delta_adapter import LegacyStateDeltaAdapter
        
        if not decisions:
            _loads = npc_affective_loads or {}
            _st = sum(_loads.values()) / len(_loads) if _loads else 0.0
            _ne = max(0.0, min(1.0, 1.0 - avatar_coherence))
            _composite = max(_st, _ne * 0.4) if (_st > 0.001 or _ne > 0.001) else 0.0
            return TensionOutcome(
                level=round(_composite, 3),
                trend=TensionTrend.STABLE,
                focus="environment",
                sources={},
                raw_stress_sum=0.0,
                state_tension=round(_st, 4),
                event_tension=0.0,
                narrative_entropy=round(_ne, 4),
                dominant_axis="ST" if _st >= _ne else "NE",
                suppression={},
            )
        
        # Вычисляем ET-компоненты (legacy)
        raw_stress = sum(abs(LegacyStateDeltaAdapter.collapse(d.deltas).stress_delta) for d in decisions)
        raw_fear = sum(abs(LegacyStateDeltaAdapter.collapse(d.deltas).fear_delta) for d in decisions)
        raw_sum = raw_stress + raw_fear
        ET = min(TENSION_CAP, raw_sum / 0.5)
        
        # Trend (из ET — не зависит от ST/NE)
        has_trauma = any(LegacyStateDeltaAdapter.collapse(d.deltas).new_trauma for d in decisions)
        has_will_override = any(LegacyStateDeltaAdapter.collapse(d.deltas).will_state_override for d in decisions)
        
        if has_trauma or has_will_override:
            trend = TensionTrend.SPIKE
        elif raw_sum > 0.3:
            trend = TensionTrend.RISING
        elif raw_sum < 0.05:
            trend = TensionTrend.FALLING
        else:
            trend = TensionTrend.STABLE
        
        focus = self._compute_tension_focus(decisions)
        
        sources: Dict[str, float] = {}
        for d in decisions:
            _legacy_d = LegacyStateDeltaAdapter.collapse(d.deltas)
            contribution = abs(_legacy_d.stress_delta) + abs(_legacy_d.fear_delta)
            if contribution > 0.01:
                sources[d.npc_id] = round(contribution, 3)
        
        # ADR-131: Трёхосевая модель через TensionSynthesizer
        from app.services.verbalization.tension_synthesizer import TensionSynthesizer
        _synth = TensionSynthesizer()
        _three = _synth.compute(
            npc_affective_loads=npc_affective_loads or {},
            decisions=decisions,
            avatar_coherence=avatar_coherence,
        )
        
        return TensionOutcome(
            level=_three.composite,      # composite после арбитража
            trend=trend,                  # из ET (legacy)
            focus=focus,                  # из ET (legacy)
            sources=sources,              # из ET (legacy)
            raw_stress_sum=round(raw_sum, 3),
            # ADR-131: векторная часть
            state_tension=_three.state_tension,
            event_tension=_three.event_tension,
            narrative_entropy=_three.narrative_entropy,
            dominant_axis=_three.dominant_axis,
            suppression=_three.suppression,
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
            key=lambda d: abs(LegacyStateDeltaAdapter.collapse(d.deltas).stress_delta) + abs(LegacyStateDeltaAdapter.collapse(d.deltas).fear_delta),
        )
        _mc_d = LegacyStateDeltaAdapter.collapse(max_contributor.deltas)
        max_contribution = abs(_mc_d.stress_delta) + abs(_mc_d.fear_delta)
        
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
        deltas = LegacyStateDeltaAdapter.collapse(decision.deltas)
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
        
        action_text = context.player_action_text or "действие"
        if context.player_success:
            effect = f"{action_text} удалось"
        else:
            effect = f"{action_text} не принесло результата"

        return PlayerOutcome(
            intent=action_text,
            outcome=outcome,
            perceived_effect=effect,
        )

    def _build_voice_constraints(
        self,
        npc_id: str,
        context: SceneContext,
        profile: Optional[NPCProfileL0] = None,
    ) -> Dict[str, str]:
        """
        Формирует voice constraints для DM на основе профиля NPC.
        """
        if profile and profile.voice_profile:
            return {"STYLE": profile.voice_profile}
        return {}
# backend/app/models/npc_state.py
"""
Единый источник типов NPC. Жёсткие write-контракты:
  L0 NPCPersonality   — write: NEVER (frozen dataclass)
  L1 NPCIdentityL1    — write: ONLY ResonanceEngine
  L2 NPCState         — write: ONLY StateApplicator
  EventMemory         — write: ONLY MemoryManager

Файл: backend/app/models/npc_state.py
Назначение: Единый источник типов NPC (L0-L2, Enums, Memory)
Зависимости: app.models.behavior_mask (BehaviorMaskState)
Основные сущности: Intent, WillState, EmotionTag, NPCTier, EventMemory, NPCPersonality, NPCIdentityL1, NPCState, DecisionView

R2.1 — NPCState: единый источник правды о динамическом состоянии NPC.
NPCState — центральный узел всей психики.

Принципы:
  - NPCPersonality (frozen) — static, загружается из JSON один раз
  - NPCState (mutable) — dynamic, меняется через StateApplicator
  - DecisionHub читает оба объекта, но пишет только через StateApplicator
  - LLM получает только VerbalizationContext — не сам NPCState
  
"""

from __future__ import annotations

from app.models.affect import AffectiveImprint

import math
_math = math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from app.models.behavior_mask import BehaviorMaskState
from app.models.psychological import CausalEntry
from app.models.physical import ThreatAccumulator
from app.models.npc.beliefs import BeliefState, BeliefFragment

import logging
logger = logging.getLogger(__name__)


# NPIC Sentinel: Отсутствие данных ≠ нейтральное состояние (§ENIGMA-003).
# Если body_state утерян при холодном старте, NPC переходит в DISABLED состояние.
# Это физический инвариант: агент существует как инертная материя, а не как логический призрак.
BODY_STATE_DISABLED = {
    "disabled": True,
    "shock_impulse": 1.0,
    "pain": 100.0,
    "blood_loss": 1.0,
    "consciousness": 0.0,
    "current_hp": 0,
    "fatigue": 100.0
}


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class Intent(str, Enum):
    """Возможные намерения NPC. DecisionHub выбирает одно из них."""
    IDLE          = "idle"           # нет активного намерения
    TALK          = "talk"           # вступить в диалог
    WARN          = "warn"           # предупредить
    INTIMIDATE    = "intimidate"     # запугать
    FLEE          = "flee"           # уйти / сбежать
    ATTACK        = "attack"         # атаковать
    HELP          = "help"           # помочь
    REPORT        = "report"         # донести властям
    TRADE         = "trade"          # предложить сделку
    OBSERVE       = "observe"        # наблюдать, не действовать
    EXPLAIN       = "explain"        # ответить "почему" — для диалога
    APPROACH      = "approach"       # подойти к целевой сущности (игрок/NPC/объект)

    # ── Проактивные интенты (Фаза 3.4: Agenda Loop) ─────────────────────
    BLOCK_PATH    = "block_path"     # преградить дорогу (шаг 9 из Мечты)
    AMBUSH        = "ambush"         # устроить засаду
    SEEK_ALLY     = "seek_ally"      # пойти за союзником
    OFFER_JOB     = "offer_job"      # предложить работу (Economic Engine)
    REQUEST_SERVICE = "request_service"  # попросить об услуге
    SPREAD_RUMOR  = "spread_rumor"   # распространить слух (Social Graph)
    CALL_FOR_HELP = "call_for_help"  # позвать на помощь
    CHANGE_ROLE   = "change_role"    # сменить роль (Role Transition)

class WillState(str, Enum):
    """Состояние воли NPC. Enum защищает от опечаток в строках."""
    FREE      = "free"
    COERCED   = "coerced"
    BROKEN    = "broken"
    DECEPTIVE = "deceptive"
    LOYAL     = "loyal"

class EmotionTag(str, Enum):
    """Текущая эмоция NPC — передаётся в VerbalizationContext."""
    NEUTRAL   = "neutral"
    ANGRY     = "angry"
    FEARFUL   = "fearful"
    HAPPY     = "happy"
    SUSPICIOUS = "suspicious"
    GRATEFUL  = "grateful"
    DISGUSTED = "disgusted"
    SAD       = "sad"


class NPCTier(str, Enum):
    """
    Статический уровень симуляции NPC.
    Назначается при создании кампании — не меняется в runtime.
    MASS  → только флаги присутствия
    MINOR → расписание + редкие события
    MAJOR → полная симуляция DecisionHub
    """
    MASS  = "mass"
    MINOR = "minor"
    MAJOR = "major"


# ─────────────────────────────────────────────────────────────────────────────
# EventMemory — L2: смысловая память NPC (из Память.md R5.1)
# Lifecycle: Fresh → Detailed → Compressed → Abstract → Forgotten
# Не участвует в формуле score() — только для вербализации и EXPLAIN.
# ─────────────────────────────────────────────────────────────────────────────

class MemoryStage(str, Enum):
    """Стадия жизненного цикла события в памяти."""
    FRESH      = "fresh"       # только что произошло — детальная
    DETAILED   = "detailed"    # несколько тиков — ещё точная
    COMPRESSED = "compressed"  # сжатая — детали теряются
    ABSTRACT   = "abstract"    # только смысл — уходит в L3 traits
    FORGOTTEN  = "forgotten"   # importance < threshold — удаляется


class DiscoveryCrack(str, Enum):
    """Уровень трещины в секрете под давлением (Этап 5).
    NONE — NPC держится. CRACK — запинается. PARTIAL — часть правды. BROKEN — сломлен.
    """
    NONE    = "none"
    CRACK   = "crack"
    PARTIAL = "partial"
    BROKEN  = "broken"


@dataclass(frozen=True)
class EventMemory:
    """
    R5.1 — L2: смысловая память о событии.
    Хранит clarity (чёткость восприятия) и confidence (уверенность в деталях).
    Decay переводит из Fresh → Forgotten через промежуточные стадии.
    """
    event_type:         str
    target_id:          str
    emotion_tag:        str
    day:                int
    importance:         float       # 0.0–1.0, затухает со временем
    clarity:            float = 1.0 # насколько чётко NPC воспринял событие
    confidence:         float = 1.0 # уверенность в деталях (снижается при drift)
    decay_rate:         float = 0.05  # потеря importance за тик
    stage:              MemoryStage = MemoryStage.FRESH
    sequence_id:        int = 0
    summary:            str = ""    # R1: текст "игрок избил Люсю кулаками"
    npc_id:             str = ""    # R1: какой NPC это запоминает

    # Фаза 0: Theatre — поля для origin_events и секретов
    tags:                Tuple[str, ...] = ()   # для триггерного поиска (immutable для frozen)
    is_secret:           bool = False
    known_by:            Tuple[str, ...] = ()   # кто знает (immutable для frozen)
    hidden_from:         Tuple[str, ...] = ()   # от кого скрыто (immutable для frozen)
    accessibility:       float = 1.0            # 0..1, падает со временем отдельно от importance

    # Этап 6: контракты и обязательства
    fulfilled:           bool = False           # обещание выполнено / долг погашен
    contract_ref:        str = ""               # ID связанного события (promise_given ↔ fulfilled)

    # Этап 9: сжатие
    is_compressed:       bool = False           # это сжатая абстракция
    compressed_from:     Tuple[str, ...] = ()   # ID исходных событий (immutable для frozen)

    # R8: субъект действия — онтологическая полнота наблюдения (кто совершил)
    actor_id:            str  = ""              # event.source при создании; "" если неизвестен

    def __post_init__(self) -> None:
        # Защита от невалидных значений при загрузке из JSON
        object.__setattr__(self, "importance",  max(0.0, min(1.0, self.importance)))
        object.__setattr__(self, "clarity",     max(0.0, min(1.0, self.clarity)))
        object.__setattr__(self, "confidence",  max(0.0, min(1.0, self.confidence)))
        object.__setattr__(self, "decay_rate",    max(0.0, min(1.0, self.decay_rate)))
        object.__setattr__(self, "accessibility", max(0.0, min(1.0, self.accessibility)))

    def decayed(self, game_days: float = 1.0) -> "EventMemory":
        """
        Возвращает новый EventMemory с применённым decay по игровым дням.
        Используется WorkingMemory.apply_decay() — не мутирует оригинал.
        Формула (Этап 8): importance × exp(-decay_rate × game_days)
        """
        # Экспоненциальное затухание важности
        new_importance = self.importance * (_math.exp(-self.decay_rate * game_days))
        # Уверенность снижается медленнее — детали теряются постепенно
        new_confidence = self.confidence * (_math.exp(-self.decay_rate * 0.5 * game_days))
        # Accessibility падает медленнее importance — вспомнить легче чем оценить значимость
        new_accessibility = self.accessibility * (_math.exp(-self.decay_rate * 0.3 * game_days))
        new_stage      = _resolve_stage(new_importance)

        return EventMemory(
            event_type     = self.event_type,
            target_id      = self.target_id,
            emotion_tag    = self.emotion_tag,
            day            = self.day,
            importance     = round(new_importance, 4),
            clarity        = self.clarity,       # clarity фиксируется в момент восприятия
            confidence     = round(new_confidence, 4),
            decay_rate     = self.decay_rate,
            stage          = new_stage,
            sequence_id    = self.sequence_id,
            summary        = self.summary,
            npc_id         = self.npc_id,
            tags           = self.tags,
            is_secret      = self.is_secret,
            known_by       = self.known_by,
            hidden_from    = self.hidden_from,
            accessibility  = round(new_accessibility, 4),
            fulfilled      = self.fulfilled,
            contract_ref   = self.contract_ref,
            is_compressed  = self.is_compressed,
            compressed_from = self.compressed_from,
            actor_id        = self.actor_id,
        )


    def to_identity_weight(self) -> Optional[tuple[str, float]]:
        """
        R5.3/R6 — конвертирует ABSTRACT память в вес для L3 Identity.
        Вызывается WorkingMemory при вытеснении события.
        Возвращает (trait_name, delta) или None если не конвертируется.
        """
        if self.stage != MemoryStage.ABSTRACT:
            return None
        # Негативные эмоции → накопление resentment
        if self.emotion_tag in ("angry", "fearful", "disgusted"):
            return ("resentment", round(self.importance * 0.1, 4))
        # Позитивные → накопление dependency
        if self.emotion_tag in ("grateful", "happy"):
            return ("dependency", round(self.importance * 0.1, 4))
        return None


    @property
    def is_forgotten(self) -> bool:
        """Событие можно удалить из памяти."""
        return self.stage == MemoryStage.FORGOTTEN


def _resolve_stage(importance: float) -> MemoryStage:
    """
    Определяет стадию памяти по текущей важности.
    Пороги откалиброваны под decay_rate=0.05.
    """
    if importance >= 0.80:
        return MemoryStage.FRESH
    if importance >= 0.55:
        return MemoryStage.DETAILED
    if importance >= 0.30:
        return MemoryStage.COMPRESSED
    if importance >= 0.10:
        return MemoryStage.ABSTRACT
    return MemoryStage.FORGOTTEN


# ─────────────────────────────────────────────────────────────────────────────
# NPCPersonality — static, из JSON, не меняется в сессии
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class NPCPersonality:
    """
    Неизменяемая личность NPC. Загружается из config/npc/ один раз.
    DecisionHub использует как контекст, но не мутирует.
    drives_base — веса для формулы score().
    """
    npc_id:        str
    tier:          NPCTier
    drives_base:   Dict[str, float]   # control, significance, fear, desire
    willpower:     float              # 0–100, сопротивление принуждению
    breakpoint:    float              # порог стресса для слома воли
    loyalty_base:  float              # базовая лояльность (не текущая)
    can_awaken:    bool = False       # может ли Minor стать Major через snapshot

    # Голос персонажа — static из JSON. Не меняется в сессии.
    # Пример: "Говоришь грубо, коротко. Называешь всех 'парень'. Материшься."
    voice_profile: str = ""

    # Биография / backstory — короткие ключевые факты из жизни NPC.
    # Пример: "Жена умерла в войну. Учился у старого кузнеца. Боится собак."
    # Не длинная история, а факты. LLM получает как есть.
    backstory:     str = ""           # ≤ 200 символов

    # Режиссёрская подсказка — instructions для LLM, не показывается NPC.
    # Пример: "Ты не осознаёшь себя жертвой. Думаешь, что контролируешь ситуацию."
    author_notes:  str = ""

    def __post_init__(self) -> None:
        total = sum(self.drives_base.values())
        if not (0.98 <= total <= 1.02):
            raise ValueError(
                f"NPCPersonality '{self.npc_id}': "
                f"drives_base сумма должна быть 1.0, получено {total:.4f}. "
                f"Проверь JSON конфигурацию NPC."
            )




# ═════════════════════════════════════════════════════════
# L1 — IDENTITY (semi-stable, пишет ТОЛЬКО ResonanceEngine)
# ═════════════════════════════════════════════════════════

@dataclass
class NPCIdentityL1:
    """
    L1: Кристаллизованные черты личности из паттернов памяти.
    Накапливается через ResonanceEngine — не изменяется напрямую.
    Overlay поверх NPCPersonality.drives_base — не замена.
    """
    npc_id: str
    # Накопленные черты: ключ = trait_name, значение = накопленный вес
    # Пример: {"resentment": 0.34, "dependency": 0.12}
    # WRITE: только ResonanceEngine.apply_resonance()
    active_traits: Dict[str, float] = field(default_factory=dict)

    def overlay_drives(self, base: Dict[str, float]) -> Dict[str, float]:
        """
        Возвращает drives с наложенными trait-весами.
        Читается DecisionHub через DecisionView — не напрямую.
        """
        result = dict(base)
        for trait, weight in self.active_traits.items():
            if trait in result:
                result[trait] = max(0.0, min(1.0, result[trait] + weight))
        return result


# ═════════════════════════════════════════════════════════
# L2 — STATE (volatile, пишет ТОЛЬКО StateApplicator)
# ═════════════════════════════════════════════════════════


# ───────────────────────────────────────────────────────
# RoleChangeEntry — запись о смене профессии (ФАЗА 4-ROLE)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RoleChangeEntry:
    """Запись о смене роли NPC. Используется в role_history NPCState."""
    from_role: str
    to_role: str
    tick: int
    reason: str


# ───────────────────────────────────────────────────────
# TemporaryDrive — временная цель из эмоционального удара (ФАЗА 4-ROLE.2)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TemporaryDrive:
    """
    Временная цель NPC, порождённая сильным эмоциональным событием.
    Генерируется когда CausalEntry.emotional_impact > 0.7.
    Cap: 3 активных drives (старый удаляется по FIFO).
    Затухает по tick_age > MAX_DRIVE_AGE.
    """
    drive_type: str           # "vengeance", "greed", "desperation", "loyalty_surge"
    urgency: float            # сила мотивации [0..1], затухает со временем
    reason: str               # человекочитаемая причина ("Торнин избил Люсю")
    source_npc_id: str        # кто вызвал (игрок или NPC)
    tick_born: int            # тик создания
    tick_age: int = 0         # тиков с создания (инкрементируется в LifeEngine/WorldTick)

    # Маппинг drive_type → модификаторы intent (для DecisionHub)
    # vengeance → ATTACK+0.3, OBSERVE+0.1
    # greed → TRADE+0.3, REQUEST_SERVICE+0.2
    # desperation → TRADE+0.2, FLEE+0.1
    # loyalty_surge → HELP+0.3, CALL_FOR_HELP+0.2

MAX_ACTIVE_DRIVES: int = 3
MAX_DRIVE_AGE: int = 50      # тиков до автоматического удаления

# Маппинг drive_type → {intent: modifier} (множится на urgency)
DRIVE_INTENT_MODIFIERS: Dict[str, Dict[str, float]] = {
    "vengeance": {
        "attack": 0.30,
        "intimidate": 0.20,
        "observe": 0.10,
        "block_path": 0.15,
    },
    "greed": {
        "trade": 0.30,
        "request_service": 0.20,
        "offer_job": 0.10,
    },
    "desperation": {
        "trade": 0.20,
        "flee": 0.15,
        "seek_ally": 0.15,
    },
    "loyalty_surge": {
        "help": 0.30,
        "call_for_help": 0.20,
        "warn": 0.10,
    },
}


def compute_drive_modifiers(drives: List[TemporaryDrive]) -> Dict[str, float]:
    """
    Вычисляет итоговые модификаторы для DecisionHub из активных драйвов.
    Каждый modifier = base_modifier × drive.urgency.
    Если несколько drives модифицируют один intent — суммируются.
    """
    mods: Dict[str, float] = {}
    for drive in drives:
        if drive.tick_age >= MAX_DRIVE_AGE:
            continue
        intent_map = DRIVE_INTENT_MODIFIERS.get(drive.drive_type, {})
        decay = max(0.0, 1.0 - drive.tick_age / MAX_DRIVE_AGE)
        for intent, base_mod in intent_map.items():
            effective = base_mod * drive.urgency * decay
            mods[intent] = round(mods.get(intent, 0.0) + effective, 4)
    return mods


def age_drives(drives: List[TemporaryDrive]) -> List[TemporaryDrive]:
    """
    Инкрементирует tick_age для всех drives.
    Удаляет просроченные (tick_age >= MAX_DRIVE_AGE).
    Вызывается каждый тик из game_loop.
    """
    surviving: List[TemporaryDrive] = []
    for drive in drives:
        aged = TemporaryDrive(
            drive_type=drive.drive_type,
            urgency=drive.urgency,
            reason=drive.reason,
            source_npc_id=drive.source_npc_id,
            tick_born=drive.tick_born,
            tick_age=drive.tick_age + 1,
        )
        if aged.tick_age < MAX_DRIVE_AGE:
            surviving.append(aged)
    return surviving


# ───────────────────────────────────────────────────────
# NPCState — dynamic, единственный изменяемый объект
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PerceptualKernel:
    """Субъективная модель восприятия NPC. Геометрия пространства решений."""
    threat_gradient: float = 0.0
    trust_gradient: float = 0.0
    uncertainty: float = 0.0
    anomaly_score: float = 0.0
    last_hostile_direction: Optional[str] = None
    dominant_emotion: Optional[str] = None
    # S28: Топология деформации utility-space (накопленное давление)
    aggression_inhibition: float = 0.0     # Сдерживание агрессивных векторов
    initiative_suppression: float = 0.0    # Подавление активных действий (паралич)
    compliance_bias: float = 0.0           # Смещение в сторону подчинения/approach
    # ADR-055: Attention Capture — прерывание когнитивной инерции бытовухи.
    # Не mind-control, а фокус внимания. DecisionHub решает, как реагировать.
    recent_directive: Optional[Dict[str, Any]] = None # {"source": str, "salience": float, "interrupts_routine": bool}

@dataclass
class NPCState:
    """
    Динамическое состояние NPC. Источник правды для DecisionHub.
    Изменяется только через StateApplicator — не напрямую.
    """
    npc_id: str
    gender: str = "male"  # "male", "female", "other" — копируется из NPCProfileL0

    # ── Психика ──────────────────────────────────────────────

    stress: float = 0.0

    # ADR-049: Интеграл аффективного давления среды (0.0 – 1.5+).
    # Накапливает threat/uncertainty с течением времени. Вызывает эмоциональный коллапс при превышении порога.
    affective_load: float = 0.0

    # R6.1 — накопленная скрытая агрессия к источнику давления.
    # Используется при выборе FAKE_SUBMISSION и BETRAYAL.
    resentment: float = 0.0

    # R6.1 — психологическая зависимость от источника давления.
    # Растёт при помощи, спасении и формировании привязки.
    dependency: float = 0.0

    # R6.1 — целостность личности (нормализованная шкала 0.0–1.0).
    # Уменьшается ТОЛЬКО через BreakProgressEngine (R6.4).
    identity_integrity: float = 1.0

    # R6.4 — динамическое сопротивление давлению (Anti-abuse).
    pressure_resistance: float = 0.0

    will_state: WillState = WillState.FREE

    # R6.2 — внешний поведенческий паттерн поверх will_state.
    # Читается OpportunityEngine и EmotionalNuanceEngine.
    # NONE = маска отсутствует, поведение соответствует will_state.
    behavior_mask: BehaviorMaskState = field(default_factory=BehaviorMaskState)

    trauma_markers: Set[str] = field(default_factory=set)

    # R7: Эпистемический слой — что NPC считает истиной о мире.
    # WRITE: только BeliefTransitionEngine.
    # READ: DecisionHub.compute() через beliefs.as_modifiers().
    beliefs: "BeliefState" = field(default_factory=BeliefState)

    # ── Физиология (Physiology Domain / Body LOD Macro) ────────────────────
    # Мастер Тай: body_state — рантайм контейнер ВСЕЙ физиологии (HP, pain, fatigue, injuries, modifiers).
    # Инициализируется из body_profile при загрузке.
    body_state: Dict[str, Any] = field(default_factory=dict)
    # P2: Субъективная каузальная модель NPC (CFRM)
    perceptual_kernel: PerceptualKernel = field(default_factory=PerceptualKernel)
    # Аффективная память (history-shaped entity). Универсально для NPC и Avatar.
    affective_imprints: Tuple["AffectiveImprint", ...] = ()

    # ── Роль (runtime, ФАЗА 4-ROLE) ──────────────────────────────────────────
    # Текущая профессия NPC. Изначально = archetype из config.
    # Может меняться через RoleTransition при определённых условиях.
    current_role: str = ""

    # История смен ролей для отладки и CausalLedger.
    role_history: List["RoleChangeEntry"] = field(default_factory=list)

    # ── Временные драйвы (ФАЗА 4-ROLE.2) ────────────────────────────────────
    # Порождены сильными эмоциональными ударами (emotional_impact > 0.7).
    # Cap: MAX_ACTIVE_DRIVES (3). Затухание по tick_age > MAX_DRIVE_AGE.
    # Модификаторы для DecisionHub вычисляются из drive_type + urgency.
    temporary_drives: List["TemporaryDrive"] = field(default_factory=list)

    # ── Физика (runtime, ШАГ 4 Причинный Слой) ──────────────────────────────
    # НЕОБРАТИМЫЕ изменения: wounds — формируют идентичность NPC.
    # ПОЛУОБРАТИМЫЕ: conditions — затухают, но влияют на решения.
    # ОБРАТИМЫЕ: hp, threat — меняются каждый тик.
    hp: int = 0
    max_hp: int = 0
    conditions: Dict[str, "Condition"] = field(default_factory=dict)
    wounds: List["Wound"] = field(default_factory=list)
    threat_accumulator: "ThreatAccumulator" = field(default_factory=lambda: ThreatAccumulator())
    posture: str = "standing"  # standing, staggered, prone

    # ── Эмоция (накопительная) ────────────────────────────────────────────────
    emotion:        EmotionTag = EmotionTag.NEUTRAL
    emotion_delta:  float      = 0.0

    # volatile-модификаторы состояния: пишутся StateApplicator, затухают по тикам
    state_modifiers: Dict[str, float] = field(default_factory=dict)

    # ── Intent ────────────────────────────────────────────────────────────────
    intent:              Optional[Intent] = None
    intent_target:       Optional[str]    = None
    intent_formed_at:    int              = 0
    intent_duration:     int              = 0   # тиков держится текущий intent
    intent_progress_ticks: int            = 0   # тиков с реальным прогрессом (значимые дельты)
    last_intent_change:  int              = 0   # тик последней смены intent
    pressure_accumulator: Dict[Tuple[str, str], float] = field(default_factory=dict)  # (from, to) → накопленное давление

    # ── Кэш отношений ────────────────────────────────────────────────────────
    relationship_cache: Dict[str, Dict[str, float]] = field(default_factory=dict)
    cache_timestamp:    int              = 0

# ── Narrative facts (max 2 для LLM) ──────────────────────────────────────
    # Только EventMemory — NarrativeFact удалён в Этапе 2.4.
    # verbalization_context использует getattr для доступа к clarity/confidence.
    narrative_cache: Tuple["EventMemory", ...] = field(default_factory=tuple)

    # ── Causal Ledger — паспорт изменений состояния (Шаг 3) ──────────────────
    # Хранит последние N записей CausalEntry для отладки и Social Propagation.
    # Не сохраняется в JSON — только runtime.
    causal_ledger: List["CausalEntry"] = field(default_factory=list)

    # ── Позиция (кэш из SceneState) ───────────────────────────────────────────
    # Удалено: cached_position (ADR-0015 призрачный кэш)
    # Удалено: position_valid (ADR-0015)

    def __post_init__(self) -> None:
        """Защита от повреждённых данных на входе."""
        self.stress = max(0.0, min(100.0, self.stress))

        # R6.1/R6.4 — защита диапазонов параметров личности и сопротивления
        self.resentment = max(0.0, min(100.0, self.resentment))
        self.dependency = max(0.0, min(100.0, self.dependency))
        self.identity_integrity = max(0.0, min(1.0, self.identity_integrity))
        self.pressure_resistance = max(0.0, min(100.0, self.pressure_resistance))

        self.emotion_delta = max(-100.0, min(100.0, self.emotion_delta))
        if self.intent is not None and self.intent_target is None:
            if self.intent not in (Intent.IDLE, Intent.OBSERVE, Intent.FLEE,
                                   Intent.EXPLAIN):
                raise ValueError(
                    f"NPCState '{self.npc_id}': intent={self.intent} требует intent_target"
                )

    # Удалено: _cached_distance_to (ADR-0015)

    def get_top_narrative_facts(self, n: int = 2) -> tuple:
        """Top-N фактов по importance."""
        return tuple(sorted(
            self.narrative_cache, key=lambda f: f.importance, reverse=True
        )[:n])

    def snapshot(self) -> Dict[str, Any]:
        """
        Сериализуемый снимок — для логов калибровки R4.2 и сохранений.
        Только данные, без методов.
        """
        return {
            "npc_id":             self.npc_id,
            "stress":             self.stress,

            # R6.1 — состояние накопленного давления личности
            "resentment":         self.resentment,
            "dependency":         self.dependency,
            "identity_integrity": self.identity_integrity,
            "pressure_resistance": self.pressure_resistance,

            "will_state":         self.will_state.value,

            # R6.2 — поведенческая маска
            "behavior_mask":      self.behavior_mask.mask.value,
            "behavior_mask_intensity": self.behavior_mask.intensity,
            "behavior_mask_applied_at_day": self.behavior_mask.applied_at_day,
            
            "emotion":            self.emotion.value,
            "emotion_delta":      self.emotion_delta,
            "state_modifiers":    dict(self.state_modifiers),
            "trauma_markers":     list(self.trauma_markers),
            "intent":             self.intent.value if self.intent else None,
            "intent_target":      self.intent_target,
            "intent_duration":      self.intent_duration,
            "intent_progress_ticks": self.intent_progress_ticks,
            "last_intent_change":   self.last_intent_change,
            # P1 ARCH: relationship_cache — эфемерный read-cache. НЕ сериализуется.
            # SSOT = RelationshipStore. Персистенция кэша = DOUBLE TRUTH.
        }



    @staticmethod
    def write_to_legacy(state: "NPCState", npc_dict: dict) -> None:
        """
        Записывает NPCState обратно в runtime dict (npc_runtime.json).
        Вызывается ПОСЛЕ StateApplicator.apply() — единственная точка записи.
        Мутирует npc_dict (вызывающий должен сохранить через _save_npcs).
        """
        psyche = npc_dict.setdefault("psyche", {})
        ss     = npc_dict.setdefault("social_stats", {})

        # Идентичность — без этого from_legacy в следующем тике получит "unknown"
        npc_dict["npc_id"] = state.npc_id
        npc_dict["id"]     = state.npc_id

        # Физическое состояние (сохраняется между тиками)
        npc_dict["hp"]     = state.hp
        npc_dict["max_hp"] = state.max_hp

        # Психика
        psyche["stress"]       = state.stress
        psyche["state"]        = state.will_state.value
        psyche["trauma_flags"] = list(state.trauma_markers) if isinstance(state.trauma_markers, (set, list, tuple)) else []

        # Социальные статы (из relationship_cache → player entry)
        rc = state.relationship_cache
        _player_rc = rc.get("player", {})
        ss["trust"]          = _player_rc.get("trust", 0.0)
        ss["fear_of_player"] = _player_rc.get("fear", 0.0)
        ss["debt"]           = _player_rc.get("debt", 0.0)

        # P1 ARCH FIX: НЕ пишем relationship_cache в write_to_legacy.
        # SSOT = RelationshipStore. Персистенция кэша = DOUBLE TRUTH.
        # Социальные статы (trust/fear) сохраняются через StateApplicator → RelationshipStore.update()

        # narrative_cache — сериализация в список dict для JSON
        if state.narrative_cache:
            _cache_list = []
            for _item in state.narrative_cache:
                _d = {**_item.__dict__, "_memory_type": type(_item).__name__}
                # tuple не сериализуется в JSON — конвертируем
                if "tags" in _d and isinstance(_d["tags"], tuple):
                    _d["tags"] = list(_d["tags"])
                if "known_by" in _d and isinstance(_d["known_by"], tuple):
                    _d["known_by"] = list(_d["known_by"])
                if "hidden_from" in _d and isinstance(_d["hidden_from"], tuple):
                    _d["hidden_from"] = list(_d["hidden_from"])
                _cache_list.append(_d)
            npc_dict["narrative_cache"] = _cache_list

        # causal_ledger — сериализация для God Mode и persistence
        if state.causal_ledger:
            npc_dict["causal_ledger"] = [entry.to_dict() for entry in state.causal_ledger]

        # body_state — ВСЯ физиология (pain, blood_loss, shock_impulse, injuries, statuses)
        # ADR-124 / Rule 44: Пишем ВСЕГДА когда body_state не None.
        # Пустой dict {} = здоровое тело, не "нет тела".
        # `if state.body_state:` убито — falsy check на dict = молчаливая потеря данных.
        if state.body_state is not None:
            npc_dict["body_state"] = state.body_state

        # perceptual_kernel — субъективная модель восприятия (ADR-O)
        # Без этого threat_gradient/initiative_suppression теряются между тиками → DOUBLE TRUTH
        if state.perceptual_kernel:
            pk = state.perceptual_kernel
            npc_dict["perceptual_kernel"] = {
                "threat_gradient": pk.threat_gradient,
                "trust_gradient": pk.trust_gradient,
                "uncertainty": pk.uncertainty,
                "anomaly_score": pk.anomaly_score,
                "last_hostile_direction": pk.last_hostile_direction,
                "dominant_emotion": pk.dominant_emotion,
                "aggression_inhibition": pk.aggression_inhibition,
                "initiative_suppression": pk.initiative_suppression,
                "compliance_bias": pk.compliance_bias,
                "recent_directive": pk.recent_directive,
            }

        # affective_load — интеграл давления (ADR-049)
        # Без этого эмоциональный аккумулятор сбрасывается каждый тик
        npc_dict["affective_load"] = state.affective_load

        # emotion — текущая эмоция (ADR-116)
        # Без этого emotion сбрасывается в NEUTRAL каждый тик → DOUBLE TRUTH → _emotion_modifier() = 0.0
        npc_dict["emotion"] = state.emotion.value
        npc_dict["emotion_delta"] = state.emotion_delta


# ─────────────────────────────────────────────────────────────────────────────
# NPCStateAdapter — миграция без большого взрыва
# ─────────────────────────────────────────────────────────────────────────────

def _pk_from_dict(pk_dict: dict) -> PerceptualKernel:
    """Создаёт PerceptualKernel из сериализованного dict.
    
    Без этого from_legacy() создаёт ядро с нулями → DOUBLE TRUTH.
    """
    if not pk_dict:
        return PerceptualKernel()
    return PerceptualKernel(
        threat_gradient=float(pk_dict.get("threat_gradient", 0.0)),
        trust_gradient=float(pk_dict.get("trust_gradient", 0.0)),
        uncertainty=float(pk_dict.get("uncertainty", 0.0)),
        anomaly_score=float(pk_dict.get("anomaly_score", 0.0)),
        last_hostile_direction=pk_dict.get("last_hostile_direction"),
        dominant_emotion=pk_dict.get("dominant_emotion"),
        aggression_inhibition=float(pk_dict.get("aggression_inhibition", 0.0)),
        initiative_suppression=float(pk_dict.get("initiative_suppression", 0.0)),
        compliance_bias=float(pk_dict.get("compliance_bias", 0.0)),
        recent_directive=pk_dict.get("recent_directive"),
    )


def _emotion_from_str(tag_str: str) -> EmotionTag:
    """Безопасная конвертация строки в EmotionTag.
    
    Маппит теги из affective pipeline ("fear", "panic", "rage", "anxious", "confusion")
    в canonical EmotionTag values ("fearful", "angry", "suspicious").
    Без этого строковые теги ломают _emotion_modifier() — str не имеет .value.
    """
    _PIPELINE_TO_CANONICAL = {
        "fear":      "fearful",
        "panic":     "fearful",
        "anxious":   "suspicious",
        "confusion": "suspicious",
        "rage":      "angry",
    }
    canonical = _PIPELINE_TO_CANONICAL.get(tag_str, tag_str)
    try:
        return EmotionTag(canonical)
    except ValueError:
        return EmotionTag.NEUTRAL


class NPCStateAdapter:
    """
    R2.1 — Переходный адаптер от legacy npc dict к NPCState.
    Позволяет мигрировать life_engine и npc_cognition инкрементально.
    Удалить после полного перехода на NPCState.
    """

    @staticmethod
    def from_legacy(npc_dict: dict) -> NPCState:
        """Создаёт NPCState из legacy npc dict."""
        psyche = npc_dict.get("psyche", {})
        ss     = npc_dict.get("social_stats", {})
        return NPCState(
            npc_id            = npc_dict.get("npc_id", npc_dict.get("id", "unknown")),
            stress            = float(psyche.get("stress", 0)),

            # R6.1/R6.4 — новые параметры личности (если отсутствуют — дефолты)
            resentment        = float(psyche.get("resentment", 0.0)),
            dependency        = float(psyche.get("dependency", 0.0)),
            identity_integrity = float(psyche.get("identity_integrity", 1.0)),
            pressure_resistance = float(psyche.get("pressure_resistance", 0.0)),

            will_state        = WillState(psyche.get("state", "free")),
            trauma_markers    = set(psyche.get("trauma_flags", [])),
            # P1 ARCH FIX: relationship_cache — эфемерный read-cache.
            # НЕ восстанавливаем из персистенса. SSOT = RelationshipStore.
            # Заполняется на этапе обогащения в tick_orchestrator / npc_tick_pipeline.
            relationship_cache = {},
            causal_ledger = [
                CausalEntry.from_dict(e) for e in npc_dict.get("causal_ledger", [])
            ],
            # body_state — физиология (pain, blood_loss, shock_impulse, injuries, statuses)
            # Без этого state.body_state всегда пустой → StateApplicator пересоздаёт его каждый раз
            body_state = dict(npc_dict.get("body_state", {})),
            # perceptual_kernel — восстановление из dict (ADR-O)
            # Без этого threat_gradient/initiative_suppression = 0.0 каждый тик
            perceptual_kernel = _pk_from_dict(npc_dict.get("perceptual_kernel", {})),
            # affective_load — восстановление интеграла давления (ADR-049)
            affective_load = float(npc_dict.get("affective_load", 0.0)),
            # emotion — восстановление текущей эмоции (ADR-116)
            # Без этого emotion = NEUTRAL каждый тик → _emotion_modifier() = 0.0
            emotion = _emotion_from_str(npc_dict.get("emotion", "neutral")),
            emotion_delta = float(npc_dict.get("emotion_delta", 0.0)),
        )
        # ADR-128: Диагностика рассинхронизации injuries/blood_loss (понижена до DEBUG)
        _bl = float(state.body_state.get("blood_loss", 0.0))
        _inj_count = len(state.body_state.get("injuries", []))
        if _inj_count == 0 and _bl > 0.01:
            logger.debug(f"[LEGACY_READ_LOST] npc={state.npc_id} injuries=0 BUT blood_loss={_bl:.3f}")
        return state

# ─────────────────────────────────────────────────────────────────────────────
# NPCPersonality builder — из legacy dict
# ─────────────────────────────────────────────────────────────────────────────

def personality_from_legacy(npc_dict: dict) -> NPCPersonality:
    """Создаёт frozen NPCPersonality из legacy npc dict."""
    psyche = npc_dict.get("psyche", {})
    tier_str = npc_dict.get("tier", "major")
    try:
        tier = NPCTier(tier_str)
    except ValueError:
        tier = NPCTier.MAJOR

    return NPCPersonality(
        npc_id        = npc_dict.get("npc_id", npc_dict.get("id", "unknown")),
        tier          = tier,
        drives_base   = dict(npc_dict.get("drives", {
            "control": 0.25, "significance": 0.25,
            "fear": 0.25,    "desire": 0.25,
        })),
        willpower     = float(psyche.get("willpower", 50)),
        breakpoint    = float(psyche.get("breakpoint", 80)),
        loyalty_base  = float(psyche.get("loyalty_true", 50)),
        can_awaken    = bool(npc_dict.get("can_awaken", False)),
        voice_profile = npc_dict.get("voice_profile", ""),
        backstory     = npc_dict.get("backstory", ""),
        author_notes  = npc_dict.get("author_notes", ""),
    )


# ═════════════════════════════════════════════════════════
# DecisionView — read-only контракт для DecisionHub
# Только этот объект передаётся в compute() — не сырые L0/L1/L2
# ═════════════════════════════════════════════════════════

@dataclass(frozen=True)
class DecisionView:
    """
    Контракт чтения для DecisionHub.
    Изолирует ядро решений от прямого доступа к L0/L1/L2.
    Создаётся в game_loop / dm_orchestrator перед вызовом compute().
    """
    profile:  NPCPersonality   # L0 — неизменяемая личность
    identity: NPCIdentityL1    # L1 — накопленные черты
    state:    NPCState         # L2 — текущее состояние


# ═════════════════════════════════════════════════════════
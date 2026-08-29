"""
path: /project/backend/app/domain/relationship_contracts.py
Назначение: Контракты данных Relationship Engine — фаза B / M1a (ТЗ-RE-01 v1.9 §5.1;
    ADR-O-370). Онтология потребностей интимной сферы: NeedSlot (frozen-конфиг),
    NeedLevel (аккумулятор Класса I), PreferenceModel, HardConstraint,
    ExclusivityRequirement — плюс валидаторы и round-trip адаптеры.
    КРАСНЫЙ ИНВАРИАНТ M1a (вердикт Мастера): этот модуль создаёт МЕСТО ХРАНЕНИЯ,
    но НЕ механизм изменения. Ни один контракт не имеет update-методов, динамики,
    писателей или self-computation: NeedLevel — immutable запись состояния,
    изменяемая ТОЛЬКО пересозданием через фабрику (dataclasses.replace) и
    применяемая только RelationshipStateStore (Шаг 2). Значения NeedSlot —
    ПЛЕЙСХОЛДЕРЫ (вердикт GPT №2 / запрет №15): порядок ONTOLOGY → CONTRACT →
    RUNTIME → PARAMETERIZATION → CALIBRATION; NPC-config-authoring — фаза M,
    в M1a секции needs в config/npc НЕ существует.
    Слоты: sexual (первичная) + intimacy (первичная социальная) — вердикт раунда 4;
    attachment НЕ включается (гейт АТ-1..3 — запреты №17/№19; пустых слотов
    «на будущее» не создаём — вердикт Мастера).
    Двойная правда исключена по построению: tombstone-сущности §5.0 (строки 9 и 15)
    и их параметры не воспроизводятся — границу держит реестр запрещённых имён
    линтера ADR-O-369 (запреты №20/№34/№35). Конвенция M1a: докстринги RE-модулей
    НЕ перечисляют tombstone-имена дословно — только ссылки на реестр (греп линтера
    не ослабляется noqa).
Зависимости: dataclasses, typing (чистый домен — Закон 1.2 Устава, ноль импортов models/services).
Основные сущности: NeedSlot, NeedLevel, PreferenceModel, HardConstraint,
    ExclusivityRequirement, RE_NEED_SLOTS (реестр M1a), from_dict/to_dict адаптеры.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Final, FrozenSet

# ═══ Ключи сериализации — КОНСТАНТЫ (Устав §12.1: inline-строки в адаптерах запрещены) ═══

_KEY_NEED_ID: Final[str] = "need_id"
_KEY_CURRENT_INTENSITY: Final[str] = "current_intensity"
_KEY_SATIATION: Final[str] = "satiation"
_KEY_FRUSTRATION: Final[str] = "frustration"
_KEY_TARGET_PRESSURE: Final[str] = "target_pressure"
_KEY_DEFICIT_THRESHOLD: Final[str] = "deficit_threshold"
_KEY_IMPORTANCE: Final[str] = "importance"
_KEY_RIGIDITY: Final[str] = "rigidity"
_KEY_SUBSTITUTABILITY: Final[str] = "substitutability"
_KEY_ADAPTABILITY: Final[str] = "adaptability"
_KEY_SATIATION_CAPACITY: Final[str] = "satiation_capacity"
_KEY_OBJECT_BINDING: Final[str] = "object_binding"
_KEY_HOMEOSTATIC: Final[str] = "homeostatic"
_KEY_CHANGE_RATE: Final[str] = "change_rate"
_KEY_PREF_ID: Final[str] = "pref_id"
_KEY_STRENGTH: Final[str] = "strength"
_KEY_FLEXIBILITY: Final[str] = "flexibility"
_KEY_CONFIDENCE: Final[str] = "confidence"
_KEY_LEARNING_RATE: Final[str] = "learning_rate"
_KEY_CONSTRAINT_ID: Final[str] = "constraint_id"
_KEY_NECESSITY: Final[str] = "necessity"
_KEY_VIOLATION_COST: Final[str] = "violation_cost"
_KEY_NEGOTIABILITY: Final[str] = "negotiability"
_KEY_SUBSTITUTABILITY: Final[str] = "substitutability"  # HardConstraint (совпадает со слотом)
_KEY_SCOPE: Final[str] = "scope"
_KEY_NEEDS: Final[str] = "needs"
_KEY_PREFERENCES: Final[str] = "preferences"
_KEY_CONSTRAINTS: Final[str] = "constraints"
_KEY_EXCLUSIVITY: Final[str] = "exclusivity"

# ═══ Константы домена (значения — ПЛЕЙСХОЛДЕРЫ, вердикт №2; калибровка — фаза M) ═══

NEED_ID_SEXUAL: Final[str] = "sexual"
NEED_ID_INTIMACY: Final[str] = "intimacy"

_OBJECT_BINDINGS: Final[FrozenSet[str]] = frozenset({"any", "class", "specific"})
_EXCLUSIVITY_SCOPES: Final[FrozenSet[str]] = frozenset({"none", "sexual", "emotional", "partial"})

# Способ реализации (§6.3): минимум для M1a — читается будущей динамикой Р18+;
# в M1a — справочник валидных значений, вычисления нет.
_ADAPTATION_STRATEGIES: Final[FrozenSet[str]] = frozenset(
    {"none", "expectation_shift", "substitution", "channel_transfer", "significance_drop", "learning", "renunciation"}
)

# Слоты M1a — закрытый реестр: расширение = вердикт GPT + ADR (запрет №17;
# линтер ADR-O-369 держит канонические узлы). attachment отсутствует ДОБРОВОЛЬНО
# (гипотеза C, АТ-1..3) — «на будущее» пустых слотов не создаём.
RE_NEED_SLOTS: Final[Dict[str, "NeedSlot"]] = {
    NEED_ID_SEXUAL: None,  # заполняется ниже, после определения класса
    NEED_ID_INTIMACY: None,
}


class ContractValidationError(ValueError):
    """Ошибка валидации контракта RE (не мгKTыfabrication: диапазон/порядок/NaN/неизвестный id).

    ValueError — не SimulationIntegrityError: неверные КОНФИГУРНЫЕ данные ловятся
    на границе загрузки/конструирования, а не роняют живой тик (L5-гейт отвечает
    за инварианты РАНТАЙМ-значений; здесь — контрактный вход).
    """


def _require_unit(value: Any, name: str) -> float:
    """Валидация числа в [0,1]: NaN/None/вне диапазона → ContractValidationError."""
    if value is None:
        raise ContractValidationError(f"{name}: отсутствует")
    try:
        v = float(value)
    except (TypeError, ValueError) as e:
        raise ContractValidationError(f"{name}: не число: {value!r}") from e
    if v != v:  # NaN — единственное значение, не равное себе
        raise ContractValidationError(f"{name}: NaN запрещён")
    if not 0.0 <= v <= 1.0:
        raise ContractValidationError(f"{name}: вне [0,1]: {v}")
    return v


def _require_unit_default(value: Any, default: float, name: str) -> float:
    """[0,1]-валидация с дефолтом для опциональных полей (None → default)."""
    if value is None:
        return default
    return _require_unit(value, name)


# ═══ Контракты §5.1 (поля и семантика — дословно ТЗ; комментарии вердиктов) ═══


@dataclass(frozen=True)
class NeedSlot:
    """Слот потребности — стабильная структура личности (Н1; L0-аналог, конфиг).

    frozen по вердикту Н1: конфиг, не аккумулятор. Все значения по умолчанию —
    ПЛЕЙСХОЛДЕРЫ (вердикт GPT №2): реальная параметризация — фаза M.
    """

    need_id: str
    target_pressure: float = 0.3  # [0,1] Ф2: пространство давления; Satisfaction = расстояние до неё
    deficit_threshold: float = 0.9  # [0,1] Ф2: p_i > threshold → HardDeficit; target < threshold (инвариант ниже)
    importance: float = 0.5  # [0,1] Н6: меняется медленно; нормируется по Σ (потребитель)
    rigidity: float = 0.5  # [0,1] С2: в Satisfaction НЕ входит; последствия дефицита + цена адаптации
    substitutability: float = 0.3  # [0,1] способность заместить каналом-суррогатом
    adaptability: float = 0.3  # [0,1] скорость приспособления ожиданий
    satiation_capacity: float = 0.5  # [0,1] Сат1/Ф5: свойство слота, не универсальный таймер
    object_binding: str = "any"  # Н4: any | class | specific (А2: пер-объектные экземпляры)
    homeostatic: bool = False  # Н3: True только для телесных гомеостатических (обе RE-потребности — дефицитные)
    change_rate: float = 0.01  # 1/день Н6: медленное обучение (НЕ [0,1] — проверяется отдельно)

    def __post_init__(self) -> None:
        if self.need_id not in RE_NEED_SLOTS:
            raise ContractValidationError(
                f"NeedSlot.need_id '{self.need_id}' вне закрытого реестра M1a "
                f"{{sexual, intimacy}}: новая потребность — вердикт GPT + ADR (запрет №17)"
            )
        _require_unit(self.target_pressure, "target_pressure")
        _require_unit(self.deficit_threshold, "deficit_threshold")
        _require_unit(self.importance, "importance")
        _require_unit(self.rigidity, "rigidity")
        _require_unit(self.substitutability, "substitutability")
        _require_unit(self.adaptability, "adaptability")
        _require_unit(self.satiation_capacity, "satiation_capacity")
        if not (self.target_pressure < self.deficit_threshold):
            # Инвариант Ф2 (раунд 8): порядок в пространстве давления target < threshold
            raise ContractValidationError(
                f"NeedSlot {self.need_id}: инвариант Ф2 нарушен — "
                f"target_pressure ({self.target_pressure}) < deficit_threshold ({self.deficit_threshold})"
            )
        if self.object_binding not in _OBJECT_BINDINGS:
            raise ContractValidationError(
                f"NeedSlot {self.need_id}: object_binding '{self.object_binding}' вне {sorted(_OBJECT_BINDINGS)}"
            )
        try:
            cr = float(self.change_rate)
        except (TypeError, ValueError) as e:
            raise ContractValidationError(f"NeedSlot {self.need_id}: change_rate не число") from e
        if cr != cr or cr < 0.0:
            raise ContractValidationError(f"NeedSlot {self.need_id}: change_rate ≥ 0 (NaN/отрицательный запрещён)")


@dataclass(frozen=True)
class NeedLevel:
    """Уровень потребности — первичный аккумулятор Класса I (Н1/Н3/О1).

    Три РАЗДЕЛЬНЫХ аккумулятора (аксиома 10 / запреты №20/№21/№23 — три механизма
    не сваливаются в одну величину):
      current_intensity — накопленное давление дефицита; ЕДИНСТВЕННАЯ первичная
        правда потребности (С1/вариант A; Received — TOMBSTONE);
      satiation — краткосрочная готовность получать, ОРТОГОНАЛЬНА давлению
        (Сат1/№21): никогда не меняет current_intensity/Satisfaction/relief;
      frustration — самостоятельная ось «мне плохо от нехватки» (Фр1–Фр6/№23):
        один аккумулятор, два пути изменения (в M1a НЕ реализуются — только место).

    IMMUTABLE по красному инварианту M1a: никаких update-методов и динамики —
    изменение только пересозданием (replace) единым писателем (Шаг 2/3).
    """

    need_id: str
    current_intensity: float = 0.0  # [0,1] Н3: давление, НЕ «сила желания сейчас» (Н5)
    satiation: float = 0.0  # [0,1] Сат1: event-provenance О1
    frustration: float = 0.0  # [0,1] Фр1–Фр6: event-provenance О1

    def __post_init__(self) -> None:
        if self.need_id not in RE_NEED_SLOTS:
            raise ContractValidationError(
                f"NeedLevel.need_id '{self.need_id}' вне закрытого реестра M1a"
            )
        _require_unit(self.current_intensity, "current_intensity")
        _require_unit(self.satiation, "satiation")
        _require_unit(self.frustration, "frustration")


@dataclass(frozen=True)
class PreferenceModel:
    """Предпочтение — ранжирование СПОСОБОВ реализации (Н5; §6.17).

    Обучается из опыта — но МЕХАНИЗМ обучения не в M1a (это субстрат); η_s без
    ускорителей (Р17-Р2 / №34: g-tombstone — линтер ADR-O-369 держит).
    """

    pref_id: str
    strength: float = 0.0  # [-1,1]: >0 притяжение, <0 aversion
    flexibility: float = 0.5  # [0,1] уступчивость при переговорах
    confidence: float = 0.5  # [0,1] уверенность в предпочтении
    learning_rate: float = 0.05  # 1/событие; η_s = это поле, БЕЗ (1+g·I) множителей

    def __post_init__(self) -> None:
        if not self.pref_id:
            raise ContractValidationError("PreferenceModel.pref_id: пустой")
        if self.strength is None:
            raise ContractValidationError("strength: отсутствует")
        try:
            s = float(self.strength)
        except (TypeError, ValueError) as e:
            raise ContractValidationError(f"strength: не число: {self.strength!r}") from e
        if s != s or not -1.0 <= s <= 1.0:
            raise ContractValidationError(f"strength вне [-1,1]: {self.strength}")
        _require_unit(self.flexibility, "flexibility")
        _require_unit(self.confidence, "confidence")
        try:
            lr = float(self.learning_rate)
        except (TypeError, ValueError) as e:
            raise ContractValidationError("learning_rate: не число") from e
        if lr != lr or lr < 0.0:
            raise ContractValidationError(f"learning_rate ≥ 0: {self.learning_rate}")


@dataclass(frozen=True)
class HardConstraint:
    """Жёсткое ограничение — «без X отношения неприемлемы» (§5.1).

    Жёсткость определяется АВТОРИНГОМ/обучением NPC, не архитектурой (§5.1);
    в M1a — контракт + валидация, применение — фазы K/L.
    """

    constraint_id: str
    necessity: float = 1.0  # [0,1] обязательность
    violation_cost: float = 0.8  # [0,1] разовое нарушение → удар по TrustDeep/привязанности
    negotiability: float = 0.0  # [0,1] обсуждаемость
    substitutability: float = 0.0  # [0,1]

    def __post_init__(self) -> None:
        if not self.constraint_id:
            raise ContractValidationError("HardConstraint.constraint_id: пустой")
        _require_unit(self.necessity, "necessity")
        _require_unit(self.violation_cost, "violation_cost")
        _require_unit(self.negotiability, "negotiability")
        _require_unit(self.substitutability, "substitutability")


@dataclass(frozen=True)
class ExclusivityRequirement:
    """Направленная норма эксклюзивности A→B (вердикт GPT №3).

    НЕ свойство пары: A.exclusivity_requirement(B) и B.exclusivity_requirement(A) —
    две независимые модели; совместимость пары = их пересечение (derived, §6.14).
    """

    scope: str = "none"  # none | sexual | emotional | partial
    importance: float = 0.5  # [0,1] 0 → ревности нет (§6.13)
    rigidity: float = 0.5  # [0,1]
    negotiability: float = 0.0  # [0,1]
    violation_cost: float = 0.8  # [0,1]

    def __post_init__(self) -> None:
        if self.scope not in _EXCLUSIVITY_SCOPES:
            raise ContractValidationError(
                f"ExclusivityRequirement.scope '{self.scope}' вне {sorted(_EXCLUSIVITY_SCOPES)}"
            )
        _require_unit(self.importance, "importance")
        _require_unit(self.rigidity, "rigidity")
        _require_unit(self.negotiability, "negotiability")
        _require_unit(self.violation_cost, "violation_cost")


# ═══ Реестр слотов M1a — ДЕФОЛТЫ-ПЛЕЙСХОЛДЕРЫ (вердикт №2; фаза M заменит) ═══
# Значения §5.1 — технические плейсхолдеры для компиляции контракта, НЕ для
# калибровки поведения: до фазы M ни одно из них не читается динамикой.

RE_NEED_SLOTS[NEED_ID_SEXUAL] = NeedSlot(
    need_id=NEED_ID_SEXUAL,
    # sexual — первичная потребность (вердикт раунда 4); дефицитная (Н3), безобъектная по умолчанию (Н4)
)
RE_NEED_SLOTS[NEED_ID_INTIMACY] = NeedSlot(
    need_id=NEED_ID_INTIMACY,
    # intimacy — первичная социальная потребность (вердикт раунда 4)
)


# ═══ Round-trip адаптеры (Устав §12: WARA + ключи-константы + from_dict-фабрика) ═══
# Тесты создают объекты ТОЛЬКО через from_dict реальной структуры — конструкторы
# мечты запрещены §12.3 (кроме прямых юнит-случаев валидации).


def need_level_to_dict(level: NeedLevel) -> Dict[str, Any]:
    """NeedLevel → dict для scene_state (ключи — константы §12.1)."""
    return {
        _KEY_NEED_ID: level.need_id,
        _KEY_CURRENT_INTENSITY: level.current_intensity,
        _KEY_SATIATION: level.satiation,
        _KEY_FRUSTRATION: level.frustration,
    }


def need_level_from_dict(data: Dict[str, Any]) -> NeedLevel:
    """dict → NeedLevel из scene_state/сейва (валидация на границе — ContractValidationError)."""
    return NeedLevel(
        need_id=data.get(_KEY_NEED_ID, ""),
        current_intensity=data.get(_KEY_CURRENT_INTENSITY, 0.0),
        satiation=data.get(_KEY_SATIATION, 0.0),
        frustration=data.get(_KEY_FRUSTRATION, 0.0),
    )


def preference_to_dict(pref: PreferenceModel) -> Dict[str, Any]:
    """PreferenceModel → dict."""
    return {
        _KEY_PREF_ID: pref.pref_id,
        _KEY_STRENGTH: pref.strength,
        _KEY_FLEXIBILITY: pref.flexibility,
        _KEY_CONFIDENCE: pref.confidence,
        _KEY_LEARNING_RATE: pref.learning_rate,
    }


def preference_from_dict(data: Dict[str, Any]) -> PreferenceModel:
    """dict → PreferenceModel."""
    return PreferenceModel(
        pref_id=data.get(_KEY_PREF_ID, ""),
        strength=data.get(_KEY_STRENGTH, 0.0),
        flexibility=data.get(_KEY_FLEXIBILITY, 0.5),
        confidence=data.get(_KEY_CONFIDENCE, 0.5),
        learning_rate=data.get(_KEY_LEARNING_RATE, 0.05),
    )


def hard_constraint_to_dict(constraint: HardConstraint) -> Dict[str, Any]:
    """HardConstraint → dict."""
    return {
        _KEY_CONSTRAINT_ID: constraint.constraint_id,
        _KEY_NECESSITY: constraint.necessity,
        _KEY_VIOLATION_COST: constraint.violation_cost,
        _KEY_NEGOTIABILITY: constraint.negotiability,
        _KEY_SUBSTITUTABILITY: constraint.substitutability,
    }


def hard_constraint_from_dict(data: Dict[str, Any]) -> HardConstraint:
    """dict → HardConstraint."""
    return HardConstraint(
        constraint_id=data.get(_KEY_CONSTRAINT_ID, ""),
        necessity=data.get(_KEY_NECESSITY, 1.0),
        violation_cost=data.get(_KEY_VIOLATION_COST, 0.8),
        negotiability=data.get(_KEY_NEGOTIABILITY, 0.0),
        substitutability=data.get(_KEY_SUBSTITUTABILITY, 0.0),
    )


def exclusivity_requirement_to_dict(req: ExclusivityRequirement) -> Dict[str, Any]:
    """ExclusivityRequirement → dict."""
    return {
        _KEY_SCOPE: req.scope,
        _KEY_IMPORTANCE: req.importance,
        _KEY_RIGIDITY: req.rigidity,
        _KEY_NEGOTIABILITY: req.negotiability,
        _KEY_VIOLATION_COST: req.violation_cost,
    }


def exclusivity_requirement_from_dict(data: Dict[str, Any]) -> ExclusivityRequirement:
    """dict → ExclusivityRequirement (пустой dict → дефолт none — легитимная инициализация)."""
    return ExclusivityRequirement(
        scope=data.get(_KEY_SCOPE, "none"),
        importance=data.get(_KEY_IMPORTANCE, 0.5),
        rigidity=data.get(_KEY_RIGIDITY, 0.5),
        negotiability=data.get(_KEY_NEGOTIABILITY, 0.0),
        violation_cost=data.get(_KEY_VIOLATION_COST, 0.8),
    )

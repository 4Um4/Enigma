# path: backend/app/services/social/relationship_dynamics.py
# Назначение: ADR-O-419 (RE G/H) — чистые функции медленного контура времени:
#   пассивное накопление давления (§6.1 п.4, gen_rate), фон фрустрации
#   (Фр1 путь 1), собственный распад фрустрации (Фр2). Pure: читает
#   scene_state, возвращает дельты; НЕ знает StateApplicator/Store.
# Зависимости: app.core.constants (SECONDS_PER_DAY, SECONDS_PER_HOUR),
#   app.domain.relationship_contracts (NeedSlot/NeedLevel/реестр),
#   app.services.social.relationship_state_store (frozen-read),
#   app.models.delta_payloads, app.models.state_delta.
# Основные сущности: relationship_dynamics_enabled, RE_DYNAMICS_QUANTUM_SECONDS,
#   RE_DYNAMICS_BG_FRUSTRATION_RATE, RE_DYNAMICS_DECAY_FRACTION_PER_DAY,
#   compute_time_driven_deltas, need_dynamics_mark, RELATIONSHIP_DYNAMICS_STATE_KEY.

import os
import uuid
from typing import Any, Dict, List, Tuple

from app.core.constants import SECONDS_PER_DAY, SECONDS_PER_HOUR
from app.domain.relationship_contracts import (
    RE_NEED_SLOTS,
    ContractValidationError,
    NeedLevel,
)
from app.models.delta_payloads import NeedDeltaPayload
from app.models.state_delta import DeltaDomain, StateDeltas
from app.services.social.relationship_state_store import RelationshipStateStore


# Флаг dormant (прецедент RELATIONSHIP_EVENTS_ENABLED / BC1_ENABLED):
# default OFF = полный no-op, байт-идентичный baseline.
def relationship_dynamics_enabled() -> bool:
    return os.environ.get("RELATIONSHIP_DYNAMICS_ENABLED", "").strip().lower() in (
        "1", "true", "yes", "on",
    )

# Квант вычисления — ТЕХНИЧЕСКАЯ дискретизация (вердикт Мастера G/H):
# не онтология («физиология меняется раз в час» — запрещённая интерпретация);
# rate × Δt эквивалентно непрерывной интеграции при линейных ставках.
RE_DYNAMICS_QUANTUM_SECONDS = SECONDS_PER_HOUR  # 3600

# Плейсхолдеры (вердикт GPT №2 / запрет №15): структура Фр1–Фр2 утверждена,
# числа — CALIBRATION_CANDIDATE до Calibration Lab.
RE_DYNAMICS_BG_FRUSTRATION_RATE = 0.02  # 1/день фона фрустрации при p > порога
RE_DYNAMICS_DECAY_FRACTION_PER_DAY = 0.1  # доля собственного распада за день

# Книга контура (служебная, не аккумулятор потребности): отметка кванта.
# Ленивое создание ТОЛЬКО при включённом флаге; census — манифест O-414.
RELATIONSHIP_DYNAMICS_STATE_KEY = "dynamics"


def _ensure_dict(parent: Dict[str, Any], key: str) -> Dict[str, Any]:
    """Ленивое создание + fail-loud на не-dict (§ENIGMA-003: молчаливых фолбэков нет)."""
    value = parent.get(key)
    if value is None:
        value = {}
        parent[key] = value
    if not isinstance(value, dict):
        raise ContractValidationError(
            f"relationship_dynamics: '{key}' в scene_state не dict ({type(value).__name__})"
        )
    return value

def need_dynamics_mark(scene_state: Dict[str, Any]) -> Dict[str, Any]:
    """Доступ к книге контура: ленивое создание, возвращает dict (mutable).
    Структура: relationship_state.dynamics.last_quantum_seconds: float."""
    return _ensure_dict(_ensure_dict(scene_state, "relationship_state"), RELATIONSHIP_DYNAMICS_STATE_KEY)


def _bg_frustration_threshold(rigidity: float) -> float:
    """Порог фона (Фр3-«(а)»): rigidity влияет на ПОРОГ начала накопления.
    Форма — плейсхолдер (структура Фр3 утверждена, форма — параметризация):
    линейная связь «жёстче → порог ниже → фон начинается раньше».
    CALIBRATION_CANDIDATE."""
    return max(0.0, min(1.0, rigidity))


def compute_time_driven_deltas(
    scene_state: Dict[str, Any],
    npc_ids: Tuple[str, ...],
    current_seconds: float,
    tick_number: int,
) -> List[StateDeltas]:
    """Pure-вычисление кванта: время → дельты давления/фрустрации (§6.1 п.4, Фр1-путь1, Фр2-распад).

    Контракт (вердикты Мастера G/H):
    - выполняется для ВСЕХ NPC независимо от сна (сон не останавливает физиологию);
    - кламп до [0,1] ДО сборки дельт; неотрицательные остатки после клампа —
      единственный случай нулевой дельты (глушить стор нельзя — E2);
    - Cause = детерминированный uuid5 (uuid4 в kernel запрещён) от кванта+NPC;
    - отметка кванта обновляется здесь же (один носитель — атомарность с Фазой 10).
    """
    if not npc_ids:
        return []
    # Peek БЕЗ мутации: no-op-квант не имеет права создавать книгу
    # (байт-чистота сцены при OFF-поведении и на коротких elapsed).
    # Однородная цепочка .get + isinstance-guard: сканер ADR-O-414 строит
    # путь по one-hop-алиасам (прецедент — ленивая инициализация стора).
    last = 0.0
    _root = scene_state.get("relationship_state")
    if _root is not None:
        if not isinstance(_root, dict):
            raise ContractValidationError(
                f"relationship_dynamics: scene_state['relationship_state'] "
                f"не dict ({type(_root).__name__})"
            )
        _book = _root.get(RELATIONSHIP_DYNAMICS_STATE_KEY)
        if _book is not None:
            if not isinstance(_book, dict):
                raise ContractValidationError(
                    f"relationship_dynamics: relationship_state['{RELATIONSHIP_DYNAMICS_STATE_KEY}'] "
                    f"не dict ({type(_book).__name__})"
                )
            last = float(_book.get("last_quantum_seconds", 0.0))
    elapsed = current_seconds - last
    if elapsed < RE_DYNAMICS_QUANTUM_SECONDS:
        return []
    book = need_dynamics_mark(scene_state)
    # целое число квантов (детерминизм: остаток переносится в следующую отметку)
    quanta = int(elapsed // RE_DYNAMICS_QUANTUM_SECONDS)
    dt_seconds = quanta * RE_DYNAMICS_QUANTUM_SECONDS
    dt_days = dt_seconds / float(SECONDS_PER_DAY)

    deltas: List[StateDeltas] = []
    for npc_id in npc_ids:
        levels = RelationshipStateStore.get_need_levels(scene_state, npc_id)
        for need_id in RE_NEED_SLOTS:
            slot = RE_NEED_SLOTS.get(need_id)
            if slot is None:
                # fail-loud: мёртвая запись реестра = контрактный разрыв;
                # сужает Optional-значение для mypy (union-attr убит)
                raise ContractValidationError(f"RE_NEED_SLOTS['{need_id}'] is None")
            level: NeedLevel = levels.get(need_id) or NeedLevel(need_id=need_id)
            # §6.1 п.4: пассивный накоп давления (дефицит-модель, Н3)
            dp = slot.gen_rate * dt_days
            # Фр1 путь 1: фон фрустрации при давлении выше порога (порог — rigidity, Фр3)
            bg = 0.0
            if level.current_intensity > _bg_frustration_threshold(slot.rigidity):
                bg = RE_DYNAMICS_BG_FRUSTRATION_RATE * dt_days
            # Фр2: собственный временной распад (пропорциональный, без авто-обнуления)
            decay = level.frustration * (RE_DYNAMICS_DECAY_FRACTION_PER_DAY * dt_days)
            # Кламп ДО сборки (E2: стор клампит сам; нули после клампа отсекаем)
            new_p = max(0.0, min(1.0, level.current_intensity + dp))
            new_f = max(0.0, min(1.0, level.frustration + bg - decay))
            dp_eff = new_p - level.current_intensity
            df_eff = new_f - level.frustration
            if dp_eff == 0.0 and df_eff == 0.0:
                continue
            cause = uuid.uuid5(
                uuid.NAMESPACE_URL, f"rel_dynamics:{tick_number}:{npc_id}:{need_id}"
            )
            deltas.append(
                StateDeltas(
                    npc_id=npc_id,
                    domain=DeltaDomain.RELATIONSHIP,
                    payload=NeedDeltaPayload(
                        need_id=need_id,
                        pressure_delta=round(dp_eff, 6),
                        frustration_delta=round(df_eff, 6),
                        source_event_id=str(cause),
                    ),
                    source="relationship_dynamics",
                )
            )
    book["last_quantum_seconds"] = last + quanta * RE_DYNAMICS_QUANTUM_SECONDS
    return deltas


def wake_transition_deltas(
    npc: Dict[str, Any], tick: int
) -> List[StateDeltas]:
    """Механизм 3 (вердикт Мастера G/H): SLEEP→WAKE = граница личного цикла.

    В G/H — no-op: формы «что сохраняется через сон / что сбрасывается
    частично / что начинает новый цикл» НЕ утверждены раундами (Сат4,
    ставки — плейсхолдеры). Точка закреплена контрактом: сигнатура фиксирует
    (npc, tick) → дельты через ЕДИНСТВЕННЫЙ write-path; реализация появится
    после утверждения форм, pipeline не меняется. Никакого reset().
    """
    return []


# ═══ Derived-readout Satisfaction (Ф1/С5; Класс IV — computed-on-read, не хранится) ═══


def satisfaction_of(p_i: float, target_i: float) -> float:
    """Ф1 (раунд 8): нормированное РАССТОЯНИЕ давления до целевого.
    Кусочно-линейно, без пересыщения (потребность не вознаграждает p < target).
    Край target→1: всегда удовлетворена (без деления на ноль)."""
    if p_i <= target_i:
        return 1.0
    span = 1.0 - target_i
    if span <= 0.0:
        return 1.0
    return max(0.0, 1.0 - (p_i - target_i) / span)


def relief_of(
    relief_capacity: float, quality: float, substitutability: float, p_i: float,
    own_source: bool = True,
) -> float:
    """Ф3/Ф4 (раунд 8): relief = relief_capacity × quality × S с ПОТОЛКОМ p_i.
    quality ∈ [0,1] — «насколько хорошо» (№22); relief_capacity ≥ 0 — «сколько
    давления потенциально снимает» (раздельные семантики); S = 1 для своего
    источника, иначе substitutability слота. Потолок: событие не снимает
    больше накопленного."""
    s_factor = 1.0 if own_source else substitutability
    raw = max(0.0, relief_capacity) * max(0.0, min(1.0, quality)) * max(0.0, min(1.0, s_factor))
    return min(raw, max(0.0, p_i))


def total_satisfaction(levels: Dict[str, NeedLevel]) -> float:
    """С5: Σ w_i·S_i по слотам-плейсхолдерам (веса = slot.importance, нормированы).
    Derived: НЕ хранится, НЕ кэшируется (запрет №6; вердикт Мастера п.5)."""
    from app.domain.relationship_contracts import ContractValidationError

    acc = 0.0
    weights_total = 0.0
    for need_id in RE_NEED_SLOTS:
        slot = RE_NEED_SLOTS[need_id]
        if slot is None:
            # fail-loud: мёртвый реестр = контрактный разрыв (не union-attr в тишине)
            raise ContractValidationError(f"RE_NEED_SLOTS['{need_id}'] is None")
        level = levels.get(need_id)
        if level is None:
            level = NeedLevel(need_id=need_id)
        w = float(slot.importance)
        acc += w * satisfaction_of(level.current_intensity, slot.target_pressure)
        weights_total += w
    if weights_total <= 0.0:
        return 0.0
    return acc / weights_total

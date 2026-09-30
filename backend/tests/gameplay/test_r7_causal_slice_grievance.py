# path: /project/backend/tests/gameplay/test_r7_causal_slice_grievance.py
# Назначение: R7 CAUSAL SLICE 3 (ADR-O-397, CS14-CS16): накопленный
#     вред (trust ≤ -12 осей SSOT) в холодной фазе (threat < 0.35,
#     CS15) → DesiredChange(grievance, behavior, target=addressee=
#     вредитель) → веса (intimidate/warn/spread_rumor/call_for_help).
#     Контрфакты Тай: один вред × разные натуры = разные способы;
#     жертва может молчать (CS16 viability); cf-группа — меняется
#     НАБОР методов от социальных условий (союзники), не только веса.
# Зависимости: app.domain.desired_change, app.services.npc.causal_slice_grievance
# Основные сущности: T1-T3 (пины), W1-W5 (контрфакт), cf×2 (набор
#     методов), test_aa_noop_projection
# Запуск: cd backend; python -m pytest tests/gameplay/test_r7_causal_slice_grievance.py -v -s

from unittest.mock import MagicMock

from app.services.npc.causal_slice_grievance import (
    GrievanceDesiredChangeProducer,
)

A = "victim"
HARMER = "aggressor"


def _state(threat=0.1, drives=None, hp=1.0):
    s = MagicMock()
    s.npc_id = A
    k = MagicMock()
    k.threat_gradient = threat
    s.perceptual_kernel = k
    s.effective_hp = 100.0 * hp
    s.effective_max_hp = 100.0
    d = {"fear": 0.3, "control": 0.3, "significance": 0.3, "desire": 0.3}
    d.update(drives or {})
    s.drives = d
    return s


def _resolve(**ov):
    world = dict(
        who=A,
        state=_state(),
        rel={HARMER: {"trust": -20.0, "fear": 15.0}},   # предательство (-20/+8×модуляция)
        disposition={"warn": 0.3, "intimidate": 0.3},
        allies=0,
    )
    world.update(ov)
    return GrievanceDesiredChangeProducer.resolve(**world)


# ═══ T-группа: пины ═══

def test_t1_no_harm_no_grievance():
    """T1: нет вреда (trust нейтрален) → None (CS14: обида = проекция вреда)."""
    assert _resolve(rel={HARMER: {"trust": 5.0, "fear": 0.0}}) is None

def test_t2_hot_threat_is_r5_territory():
    """T2 (CS15): угроза СЕЙЧАС (threat=0.8) → grievance молчит — R5 владеет."""
    assert _resolve(state=_state(threat=0.8)) is None

def test_t3_contract_fields():
    """T3: reason=grievance, state_type=behavior, target=addressee=HARMER
    (контракт различения хранится полями; здесь совпадают, как в срезе-1)."""
    dc = _resolve()
    assert dc is not None
    assert dc.reason == "grievance"
    assert dc.state_type == "behavior"
    assert dc.target_of_change == HARMER
    assert dc.addressee == HARMER


# ═══ W-группа: контрфакты — один вред, разные натуры ═══

def test_w1_bold_guard_intimidates():
    """W1: храбрый контролирующий стражник, вред глубоко отрицателен
    → intimidate доминирует."""
    dc = _resolve(state=_state(drives={"fear": 0.1, "control": 0.8, "significance": 0.4}))
    w = dc.method_weights
    assert w["intimidate"] > w["warn"]
    assert w["intimidate"] > w.get("spread_rumor", 0.0)

def test_w2_cowardly_maid_gossips():
    """W2: трусливая служанка (fear высок, control низок) — прямой путь
    закрыт → непрямой: spread_rumor (репутационная месть) доминирует
    над intimidate."""
    dc = _resolve(
        state=_state(drives={"fear": 0.7, "control": 0.1, "significance": 0.3}),
        rel={HARMER: {"trust": -25.0, "fear": 30.0}},
    )
    w = dc.method_weights
    assert w["spread_rumor"] > w["intimidate"]

def test_w3_terrified_victim_stays_silent():
    """W3 (CS16): тот же вред, но страх подавляет (fear=0.9, control=0.05,
    союзников нет) → честный None: жертва молчит."""
    dc = _resolve(
        state=_state(drives={"fear": 0.9, "control": 0.05, "significance": 0.1}),
        rel={HARMER: {"trust": -20.0, "fear": 60.0}},
    )
    assert dc is None

def test_w4_social_ally_calls_help():
    """W4: значимый социальный NPC с союзниками → call_for_help жив."""
    dc = _resolve(
        state=_state(drives={"fear": 0.5, "control": 0.3, "significance": 0.8}),
        allies=2,
    )
    assert dc.method_weights.get("call_for_help", 0.0) > 0.1

def test_w5_harm_depth_matters():
    """W5: слабый вред (threat=-8 одной угрозой) → None или малые веса;
    глубокий (предательство -25) → живая цель. Вред градуирован."""
    weak = _resolve(rel={HARMER: {"trust": -8.0, "fear": 5.0}})
    deep = _resolve(rel={HARMER: {"trust": -25.0, "fear": 15.0}})
    assert (deep is not None) and (
        weak is None
        or max(deep.method_weights.values()) > max(weak.method_weights.values())
    )


# ═══ Контрфакты Тай §2: меняется НАБОР методов, не только веса ═══

def test_cf_social_conditions_change_method_set():
    """Одна grievance + разные социальные условия = разные ДОСТУПНЫЕ методы."""
    solo = _resolve(state=_state(drives={"fear": 0.5, "control": 0.3,
                                         "significance": 0.8}), allies=0)
    allied = _resolve(state=_state(drives={"fear": 0.5, "control": 0.3,
                                           "significance": 0.8}), allies=2)
    assert solo.method_weights.get("call_for_help", 0.0) < 0.05
    assert allied.method_weights["call_for_help"] > 0.1
    crushed = _resolve(
        state=_state(drives={"fear": 0.9, "control": 0.05, "significance": 0.1}),
        rel={HARMER: {"trust": -20.0, "fear": 60.0}},
        allies=0,
    )
    assert crushed is None

def test_cf_harm_presence_is_binary_gate():
    """Набор пуст без вреда — гейт до любых весов."""
    assert _resolve(rel={HARMER: {"trust": 10.0, "fear": 0.0}}) is None

# ═══ A/A ═══

def test_aa_noop_projection():
    assert GrievanceDesiredChangeProducer.to_modifiers(None) == {}
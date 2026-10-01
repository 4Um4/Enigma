# path: /project/backend/tests/test_g3_will_integration.py
# Назначение: G3 Этап 2 (ADR-O-410) — Tier-A: юнит-интеграция воли.
#     По вердикту Мастера (S305): T1 «STEAL becomes available» — открытый
#     Opportunity-момент (distance/allies — параметры МИРА, не личности)
#     делает STEAL доступным; при его победе intent_target обязан нести
#     объектную цель (канал G3: воля → цель → интент). Winner НЕ является
#     единственным доказательством (веса production не подгоняются);
#     победа фиксируется в отчётной строке для будущей калибровки.
#     T2 «closed moment» — контроль замка: внимание игрока держит STEAL
#     locked (opportunity отвечает «можно ли», не «хочу ли» — граница
#     слоя, зафиксированная вердиктом: CAN_STEAL ≠ ACCEPT_STEAL/WANT).
# Зависимости: pytest, app.services.npc.decision_hub, app.services.economy,
#     app.models.npc_state, app.models.npc_profile, app.domain.identity_events
# Основные сущности: TestG3WillIntegration
# Запуск: cd backend; python -m pytest tests/test_g3_will_integration.py -v -s; cd ..
from app.domain.identity_events import EffectiveDrives
from app.models.npc_profile import NPCProfileL0, PsycheBase
from app.models.npc_state import NPCState, WillState
from app.services.economy.opportunity_engine import OpportunityContext
from app.services.npc.decision_hub import DecisionHub, EventContext


def _drives() -> EffectiveDrives:
    """Desire-доминанта (L3, ADR-O-208, фабрика from_dict)."""
    return EffectiveDrives.from_dict(
        {"control": 0.05, "significance": 0.05, "fear": 0.05, "desire": 0.85}
    )


def _personality() -> NPCProfileL0:
    """Thief-профиль (affinity-база 1.0 при выборе; архетип НЕ диктует
    выбор — вердикт Мастера: thief → STEAL запрещён)."""
    return NPCProfileL0(
        id="thief_shadow",
        name="Тень",
        tier="mass",
        archetype="thief",
        drives_base={"control": 0.10, "significance": 0.10, "fear": 0.05, "desire": 0.75},
        psyche_base=PsycheBase(willpower=40, breakpoint=75),
        voice_profile="нейтральный",
    )


def _event() -> EventContext:
    """World-tick событие: канонический контекст проактивных интентов
    (STEAL ∈ PROACTIVE_INTENTS — world_tick only, decision_hub:970;
    реактивный вход честно вырезает кражу: NPC не крадёт «в ответ»
    на действие игрока — только по собственному решению в живом тике)."""
    from app.services.events.event_types import EventType

    return EventContext(event_type=EventType.WORLD_TICK, actor_id="world")


def _state() -> NPCState:
    """Воля DECEPTIVE (R6.3: скрытность — натура; S212)."""
    return NPCState(npc_id="thief_shadow", will_state=WillState.DECEPTIVE)


class TestG3WillIntegration:
    def test_open_moment_unlocks_steal_with_target(self):
        """T1: открытый момент → STEAL available; при победе — цель-канал.
        Входы — параметры мира (игрок далеко, двое своих рядом), НЕ
        изменение личности/весов. raw≈0.43+0.14+0.2 > 0.65."""
        _ctx = OpportunityContext(
            player_attention=0.0,
            distance=25.0,
            weapon_access=False,
            allies=2,
            steal_target="wo_g3_tier_a_chair",
        )
        _res = DecisionHub(seed=0).compute(
            _state(),
            _personality(),
            _event(),
            effective_drives=_drives(),
            opportunity_ctx=_ctx,
        )
        _opp_raw = _res.scores_trace.get("opp_raw_score", 0.0)
        _opp_thr = _res.scores_trace.get("opp_threshold", 1.0)
        # Главное доказательство T1: доступность (замок открыт).
        assert _opp_raw >= _opp_thr, (
            f"открытый момент не разблокировал STEAL: "
            f"raw={_opp_raw} < threshold={_opp_thr}"
        )
        assert "steal" in _res.scores_trace or _res.intent.value == "steal", (
            "STEAL разблокирован, но не скорится (не в possible?)"
        )
        # Условная вертикаль: победа STEAL → цель обязана быть объектной.
        if _res.intent.value == "steal":
            assert _res.intent_target == "wo_g3_tier_a_chair", (
                f"STEAL победил, но цель-канал пуст: target={_res.intent_target!r}"
            )
        # Честная фиксация текущих весов (для будущей калибровки; не assert).
        # PEP 701: многострочное выражение внутри f-string допустимо только с 3.12,
        # а CI гоняет матрицу 3.11/3.12 — поэтому top3 считается до подстановки.
        _top3 = sorted(
            ((k, v) for k, v in _res.scores_trace.items()
             if isinstance(v, (int, float)) and k not in (
                 'opp_attention_component', 'opp_distance_component',
                 'opp_weapon_component', 'opp_allies_component',
                 'opp_raw_score', 'opp_threshold')),
            key=lambda x: -x[1])[:3]
        print(
            f"[G3-T1] raw={_opp_raw} winner={_res.intent.value} "
            f"target={_res.intent_target!r} "
            f"top3={_top3}"
        )

    def test_closed_moment_keeps_steal_locked(self):
        """T2: контроль замка — внимание игрока держит STEAL locked.
        Opportunity отвечает «можно ли», не «хочу ли» (граница слоя)."""
        _ctx = OpportunityContext(
            player_attention=1.0,
            distance=2.0,
            weapon_access=False,
            allies=0,
            steal_target="wo_g3_tier_a_chair",
        )
        _res = DecisionHub(seed=0).compute(
            _state(),
            _personality(),
            _event(),
            effective_drives=_drives(),
            opportunity_ctx=_ctx,
        )
        _opp_raw = _res.scores_trace.get("opp_raw_score", 0.0)
        _opp_thr = _res.scores_trace.get("opp_threshold", 1.0)
        assert _opp_raw < _opp_thr, (
            f"замок должен быть закрыт: raw={_opp_raw} >= {_opp_thr}"
        )
        assert "steal" not in _res.scores_trace, (
            "STEAL скорится при закрытом моменте — замок дыряв"
        )
        assert _res.intent.value != "steal"
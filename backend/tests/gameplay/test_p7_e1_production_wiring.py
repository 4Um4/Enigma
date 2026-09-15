# path: /project/backend/tests/gameplay/test_p7_e1_production_wiring.py
"""
Файл: backend/tests/gameplay/test_p7_e1_production_wiring.py
Назначение: DEBT-E1-WIRING (санкция Мастера, сле S259) — замкнуть
    production-путь адресованного вопроса игрока через disclosure-
    контур. До фикса: TaskScheduler строится без epistemic-параметров,
    set_epistemic_wiring не вызывается → DialogueExecutor._discovery_
    bridge is None → вердикт None → при ЛЮБОМ trust уровень игрока не
    меняется (потеря доказана T-W1). После: сквозной путь
    вопрос → retrieve_knowledge → decide_disclosure → директива →
    DIALOGUE_OUTCOME → Bridge (T-W2), без ложных раскрытий (T-W3),
    Vacuum-фолбэк по канону tick_utils (T-W4).
    Один вердикт на реплику · один источник истины · никаких новых
    epistemic-систем (границы санкции).
Зависимости: app.domain.*, app.services.*, tests.gameplay.harness
Основные сущности: _ProbeRouter
Запуск: cd backend && python -m pytest tests/gameplay/test_p7_e1_production_wiring.py -v
"""

import pytest
from app.domain.execution import QueuedTask, TaskKind, TaskPriority
from app.domain.player_epistemics import IDENTIFIED, UNKNOWN
from tests.gameplay.harness import TavernGameplayHarness

_TOPIC_SECRET = "караван"          # канон-тема borko_negligence (E1-тесты)
_TOPIC_NEUTRAL = "погода"          # тема вне знания borko


class _ProbeRouter:
    """Захватывает промпт production-executor'а (контракт А8:
    request_for_agent + _abort_generation). Возвращает валидную русскую
    реплику — текст НЕ источник discovery (PROVENANCE, NOT STRINGS)."""

    def __init__(self) -> None:
        self.prompts: list = []

    def request_for_agent(self, agent_name, prompt, system_prompt, params):
        self.prompts.append(prompt)
        return "Караван остался без прикрытия из-за меня."

    def _abort_generation(self) -> None:
        pass


from contextlib import contextmanager


@contextmanager
def _probe_router_on(harness):
    """Инъекция ProbeRouter в production-executor (тест-двойник по
    образцу set_epistemic_wiring: единственная мутация — поле _router;
    гарантируем восстановление). Без этого RED измеряет доступность
    LLM-сервера, а не wiring-разрыв (инцидент первого прогона)."""
    probe = _ProbeRouter()
    exec_ = _production_executor(harness)
    orig = exec_._router
    exec_._router = probe
    try:
        yield probe
    finally:
        exec_._router = orig


def _dialogue_task(owner: str, topic: str, tick: int) -> QueuedTask:
    """Адресованный вопрос игрока: DialogueRequest с target_id='player' —
    гейт E1 executor'а (D30) достижим в production-формате задачи."""
    from app.domain.communication import DialogueRequest, ExposureLevel

    req = DialogueRequest(
        topic=topic,
        target_id="player",
        exposure=ExposureLevel(semantic="normal"),
        intent_type="talk",
    )
    return QueuedTask(
        task_id=f"w-{owner}-{tick}",
        tick=tick,
        counter=0,
        kind=TaskKind.DIALOGUE,
        priority=TaskPriority.NORMAL,
        creator_system="test",
        owner_id=owner,
        target_ids=["player"],
        campaign_id=_harness_campaign(None),  # D6: production-штамп
        # (execute_pending передаёт cid извне; вердикт читает
        # task.campaign_id — без него провайдеры дают Vacuum → None)
        payload=req,
        created_tick=tick,
    )


@pytest.fixture()
def harness():
    _h = TavernGameplayHarness(seed=42)
    _h.new_game()
    _h.advance_ticks(3)
    yield _h
    _h.dispose()


def _production_executor(harness):
    """Production-исполнитель scheduler'а (НЕ тестовый Double)."""
    sched = harness.game_loop._get_task_scheduler()
    return sched._executors[TaskKind.DIALOGUE]


def _raise_borko_trust(harness, trust: float) -> None:
    """Легальный writer V2-стора (P-10-1): update(cid, borko, player,
    {trust: Δ}) — headroom-сатурация; несколько вызовов для набора
    абсолютного значения, запись создаёт пару при Vacuum."""
    store = harness.game_loop.memory_manager._relationships
    store.update(_harness_campaign(harness), "guard_borko", "player", {"trust": trust})


def _harness_campaign(harness) -> str:
    import tests.gameplay.harness as _harness_mod

    return getattr(_harness_mod, "_CAMPAIGN", "Open_road")


def _dialogue_pressure_seed(harness, npc_id: str, turns: int = 3) -> None:
    """Накопление диадического давления на knower — production-путь:
    session.add_turn → _detect_topic (keyword-реестр) →
    _pressure_by_topic[topic] += 1; читатель get_dialogue_pressure =
    session.get_pressure(session.topic). Текст ходов содержит
    keyword-словарную лексему («подвал») — единственный живой
    production-механизм поднятия pressure (D4-форензика; ограничение
    alpha-механизма: «караван» отсутствует в keyword-реестре —
    зафиксировано в досье как наблюдение, не правится здесь:
    memory-домен вне рамки сессии)."""
    mm = harness.game_loop.memory_manager
    cid = _harness_campaign(harness)
    for i in range(turns):
        mm.add_dialogue_turn(
            campaign_id=cid,
            npc_id=npc_id,
            speaker="player",
            text=f"Говорят, в подвале что-то слышали ({i}).",
            target_id=npc_id,
            intent="question",
            tick=100 + i,
            partner_id="player",
        )


def test_t_w1_wiring_alive(harness):
    """T-W1 (инверсный гвард, судьба оговорена в RED-фазе): до фикса
    этот тест был зелёным на DENY-монокультуре wiring-gap'а (proof-of-
    loss); после — обязан требовать живой контур: bridge wired + полное
    прохождение вердикта до IDENTIFIED. История потери сохранена в
    имени и docstring — тест не удалялся молча."""
    _raise_borko_trust(harness, trust=60.0)
    _dialogue_pressure_seed(harness, "guard_borko")
    state = harness.game_loop.mvp_controller.player_epistemic_state
    truth = harness.game_loop.mvp_controller.truth_state

    # Сам wiring: bridge у production-executor — не None (ядро DEBT-фикса)
    assert _production_executor(harness)._discovery_bridge is not None, (
        "E1-wiring потерян: production-executor без bridge (регресс DEBT-E1-WIRING)"
    )

    with _probe_router_on(harness) as _probe:
        list(_production_executor(harness).execute(
            _dialogue_task("guard_borko", _TOPIC_SECRET, tick=50)
        ))
        assert _probe.prompts, "LLM-зонд не вызван: тест ничего не измерил"

    assert state.level("borko_negligence") == IDENTIFIED
    assert truth.discovered_secrets == {"borko_negligence"}


def test_t_w2_production_reveal_path(harness):
    """T-W2 [RED→GREEN]: сквозной production-путь. borko знает «караван»
    (канон narrative_cache), игрок спрашивает, trust=60 ≥ T_REVEAL,
    давление ≥ 2 (вопросы) → REVEAL-директива в промпте → IDENTIFIED +
    truth.mark_discovered (Р1, монополия Bridge)."""
    _raise_borko_trust(harness, trust=60.0)
    _dialogue_pressure_seed(harness, "guard_borko", turns=5)
    state = harness.game_loop.mvp_controller.player_epistemic_state
    truth = harness.game_loop.mvp_controller.truth_state

    with _probe_router_on(harness):
        artifacts = list(_production_executor(harness).execute(
            _dialogue_task("guard_borko", _TOPIC_SECRET, tick=51)
        ))

    assert artifacts and artifacts[-1].success is True
    assert state.level("borko_negligence") == IDENTIFIED
    assert truth.discovered_secrets == {"borko_negligence"}


def test_t_w3_no_knowledge_no_false_reveal(harness):
    """T-W3 [ПИН]: borko НЕ обладает знанием по теме «погода» →
    retrieve_knowledge пуст → вердикт None → ложного раскрытия НЕТ
    (E2-наследие; зелёный до и после фикса)."""
    _raise_borko_trust(harness, trust=80.0)
    _dialogue_pressure_seed(harness, "guard_borko")
    state = harness.game_loop.mvp_controller.player_epistemic_state
    truth = harness.game_loop.mvp_controller.truth_state

    with _probe_router_on(harness):
        artifacts = list(_production_executor(harness).execute(
            _dialogue_task("guard_borko", _TOPIC_NEUTRAL, tick=52)
        ))

    assert artifacts and artifacts[-1].success is True
    assert state.levels.get("borko_negligence", UNKNOWN) == UNKNOWN
    assert truth.discovered_secrets == set()


def test_t_w4_vacuum_fallback_honest_behavior(harness):
    """T-W4 [ПИН]: пара borko→player отсутствует в сторе (Vacuum) →
    адаптер обязан дать фолбэк social_stats (канон tick_utils:99-116);
    borko без social_stats → trust=0 → DENY честно (не крах, не REVEAL)."""
    state = harness.game_loop.mvp_controller.player_epistemic_state
    truth = harness.game_loop.mvp_controller.truth_state
    _dialogue_pressure_seed(harness, "guard_borko")

    # пара НЕ создана (в отличие от T-W1) — чистый Vacuum
    with _probe_router_on(harness):
        list(_production_executor(harness).execute(
            _dialogue_task("guard_borko", _TOPIC_SECRET, tick=53)
        ))

    # После фикса: уровень по-прежнему UNKNOWN (trust=0 → DENY-ветка),
    # но падения/исключения нет — адаптер обработал Vacuum безмолвно
    # (сохранение DENY, не инверсия).
    assert state.level("borko_negligence") == UNKNOWN
    assert truth.discovered_secrets == set()
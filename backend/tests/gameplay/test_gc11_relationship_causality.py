# path: /project/backend/tests/gameplay/test_gc11_relationship_causality.py
# Назначение: GC-11 — первый обязательный L3-гейт (§5a.9 вердикт Мастера
#   2026-09-05, GAMEPLAY-GATE CANONIZATION). Доказывает причинную истину:
#   relationship-событие → ненулевая запись в V2-RAM → следующий выбор
#   NPC сдвинут относительно бейзлайна. Ловит RE-D2-класс (зелёная
#   архитектура пишет нулевую игровую реальность — юнит-сьютой недоказуемо).
#   Production-only: никаких моков, никаких прямых записей — только
#   player_action (REST run_turn) и idle_tick (§5a.2).
# Зависимости: tests.gameplay.harness (build_game_loop production runtime).
# Основные сущности: test_gc11_compliment_writes_nonzero_ram,
#   test_gc11_event_shifts_decision_landscape.
# Запуск: cd backend; python -m pytest tests/gameplay/test_gc11_relationship_causality.py -v -s

import logging

import pytest
from tests.gameplay.harness import TavernGameplayHarness

logger = logging.getLogger("gameplay.gc11")

# NPC-адресат комплимента: мейд — базовый персонаж таверны
_TARGET_NPC = "maid_lusya"


def _llm_alive() -> bool:
    """Пакет 3 (ТЗ АУДИТ-01, INFRA-D1): живость LLM по каноническому URL
    из settings (порт 8181 — C2 FIX SSOT; прецедент — test_memory_fixation,
    но без хардкода 8080). Классификация отказа ПОЗДНЯЯ: проба зовётся
    только когда ассерт готов упасть — LLM-off = INFRA-skip (§9.13-4),
    LLM-live = настоящий RED. Мок не подставляется никогда (ADR-O-425:
    система не врёт о собственном отказе)."""
    import urllib.request

    from app.core.config import settings
    try:
        urllib.request.urlopen(
            f"{settings.llama_cpp_server_url.rstrip('/')}/health", timeout=1
        )
        return True
    except Exception:
        return False


_LLM_STATE = {"started": False}


def _ensure_llm() -> None:
    """Пакет 3 (ТЗ АУДИТ-01, INFRA-D1): самодостаточность GC-11.

    Принцип Мастера: реальный LLM всегда; не поднят — поднимаем штатным
    менеджером проекта (прецедент: шапка IPT.py — start_llama_server +
    atexit kill; KILLER_SPIRIT: призраков не оставляем). Закрывает
    order-dependence: прежде тест был зелёным в полном сюите только
    потому, что сервер поднимал кто-то до него. Мок не подставляется
    никогда (ADR-O-425: честный отказ, не ложь). Не поднялся — тесты
    честно уйдут в INFRA-skip поздней классификацией (§9.13-4)."""
    import time

    if _llm_alive():
        return
    try:
        from scripts.llm_server_manager import kill_llama_server, start_llama_server
    except Exception as e:
        print(f"[GC11-LMM] scripts.llm_server_manager недоступен: {e}")
        return
    _ok = start_llama_server()
    # Загрузка модели не мгновенна: опрос здоровья до ~30с (страховка).
    _waited = 0
    while not _llm_alive() and _waited < 30:
        time.sleep(1.0)
        _waited += 1
    print(
        f"[GC11-LMM] start_llama_server() → {_ok}; "
        f"health({_waited}s): {_llm_alive()}"
    )
    if _llm_alive() and not _LLM_STATE["started"]:
        import atexit

        atexit.register(kill_llama_server)
        _LLM_STATE["started"] = True


def _v2_rel(harness, npc_id: str, target: str):
    """Чтение trust-пары NPC→player через harness.read_trust (V2-RAM,
    канонический бэкенд; провода game_loop._rel_store — один объект на
    все подписки). None = пара отсутствует (Vacuum); 0.0 = пара есть,
    trust нулевой. Прежний доступ memory_manager._relations с
    _campaign-хаком падал в except → -1.0 на каждом вызове (RED-причина
    2026-09-05: ассерты были слепы, ни одного чтения не происходило)."""
    return harness.read_trust(npc_id, target)


def _npc_intent(harness, npc_id: str):
    """Текущий интент NPC (агрегированное решение) — маркер decision-состояния.
    Возвращает intent-строку или 'UNREACHABLE'."""
    _st = harness.inspect_npc(npc_id) or {}
    _intent = _st.get("intent") or _st.get("last_intent")
    return str(_intent) if _intent else "UNREACHABLE"


@pytest.fixture
def harness():
    """Production runtime; dispose гарантирован; V2-кампания кэшируется
    после new_game (привязка адаптера происходит в первом тике)."""
    # Пакет 3: самодостаточность — реальный LLM поднимается здесь, а не
    # «повезло, что поднял кто-то раньше» (order-dependence, INFRA-D1).
    _ensure_llm()
    _h = TavernGameplayHarness(seed=42)
    _h.new_game()
    # Пакет 3 (чистка): _v2_rel._campaign = "Open_road" удалён — мёртвое
    # присваивание атрибута функции (Pylance reportFunctionMemberAccess).
    # _campaign-хак умер вместе с прежним доступом memory_manager._relations;
    # _v2_rel читает через harness.read_trust (модульная константа _CAMPAIGN).
    yield _h
    _h.dispose()


def test_gc11_compliment_writes_nonzero_ram(harness):
    """GC-11 СТУПЕНЬ 1: player-комплимент → V2-RAM содержит ненулевой
    trust-запись player→maid_lusya (похвала пишет пару игрока к цели —
    social_sub:praise). Нулевой/отсутствующий RAM-запись =
    RE-D2 (событие прошло, игровая реальность не изменилась) = FAIL."""

    harness.advance_ticks(5)  # прогрев: bind V2, stable baseline

    # Пакет 3: направление выровнено с писателем. Прежнее «до» читало
    # maid→player, «после» — player→maid: сравнение разных сторон давало
    # ложный PASS при мёртвой записи (None != value = «изменилось»).
    _before = _v2_rel(harness, "player", _TARGET_NPC)

    _res = harness.player_action(f"подойди к {_TARGET_NPC} и скажи ей комплимент")

    # Событие обязано доехать до RAM: либо сразу, либо после следующего тика
    _after_immediate = _v2_rel(harness, "player", _TARGET_NPC)
    if _after_immediate is None or _after_immediate <= 0.0:
        harness.advance_ticks(3)  # событию нужен тик на оседание
        _after = _v2_rel(harness, "player", _TARGET_NPC)
    else:
        _after = _after_immediate

    print(f"[GC11-STEP1] trust player→maid_lusya: before={_before} "
          f"after={_after}")

    # Пакет 3: классификация только в кандидате на отказ (INFRA-D1).
    if (_after is None or _after <= 0.0) and not _llm_alive():
        pytest.skip(
            "INFRA: LLM недоступен — NARRATIVE-цепь (текст→семантика) мертва, "
            "комплимент не доходит до relationship-события "
            "(правило §9.13-4; Пакет 3 ТЗ АУДИТ-01)"
        )

    # None = пара не создана; 0.0 = создана с нулём. Оба = RE-D2-класс.
    # Диагноз-развилка: без LLM комплимент идёт через NARRATIVE-цепь —
    # DM-краш (GC-24-изоляция, ход жив) может обрывать семантику ДО
    # relationship-события: тогда verdict = requires_llm, не write-баг.
    assert _after is not None and _after > 0.0, (
        f"GC11-STEP1 FAIL: комплимент не записан в V2-RAM "
        f"(before={_before}, after={_after}). RE-D2-класс: событие прошло "
        f"(run_turn вернул {_res is not None}), но игровая реальность "
        f"нулевая. suspect: rules_subscriber → Gate → V2 (RE-D2) либо "
        f"NARRATIVE-обрыв при LLM-off (см. диагноз-развилку)"
    )


def test_gc11_event_shifts_decision_landscape(harness):
    """GC-11 СТУЕНЬ 2: тот же мир+seed, но до/после комплимента —
    decision-состояние NPC (intent/чувствительность к социальному
    давлению) обязано различаться. Одинаковый ответ = событие не
    причинно (двойная история §5a.3 GC-06 логика)."""

    harness.advance_ticks(3)  # baseline

    _intent_before = _npc_intent(harness, _TARGET_NPC)
    # Маркер причинности шины: события целевого NPC до/после — реально
    # наблюдаемый decision-след (counters уже подписан на bus).
    _events_before = dict(harness.counters.events_by_type)
    # Пакет 3: та же правка направления — «до» читает пару, которую
    # пишет похвала (player→target); иначе «до»/«после» — разные пары.
    _trust_before = _v2_rel(harness, "player", _TARGET_NPC)

    harness.player_action(f"скажи {_TARGET_NPC} комплимент")
    harness.advance_ticks(2)  # событие оседает, next-tick decision использует новые входы

    _intent_after = _npc_intent(harness, _TARGET_NPC)
    _trust_after = _v2_rel(harness, "player", _TARGET_NPC)

    print(f"[GC11-STEP2] intent: {_intent_before} → {_intent_after}")
    print(f"[GC11-STEP2] trust: {_trust_before} → {_trust_after}")

    # Причинный минимум: trust изменился ИЛИ intent изменился
    _causal = (_trust_after != _trust_before) or (_intent_after != _intent_before)
    # Пакет 3: классификация только в кандидате на отказ — как в СТУПЕНИ 1.
    if not _causal and not _llm_alive():
        pytest.skip(
            "INFRA: LLM недоступен — событие не осело через NARRATIVE-цепь "
            "(правило §9.13-4; Пакет 3 ТЗ АУДИТ-01)"
        )
    assert _causal, (
        f"GC11-STEP2 FAIL: идентичный мир, доверие и intent НЕ изменились "
        f"после комплимента (trust: {_trust_before}→{_trust_after}; "
        f"intent: {_intent_before}→{_intent_after}). Событие не является "
        f"причинным в runtime. suspect: rider V2-RAM → compute "
        f"(S135-путь) либо/social_modifiers → DecisionHub"
    )
# path: /project/backend/tests/gameplay/test_tavern_vertical.py
# Назначение: GC-00 — детектор живости мира (§5a.3). Не greenwashing: каждый
#   FAIL обязан оставить диагностический след (таблица счётчиков, первый
#   расходящийся тик, подозреваемый узел). Production-фиксы здесь запрещены
#   (правило Мастера: археология → harness → честный baseline → отдельный fix).
# Зависимости: tests.gameplay.harness (production-path ONLY: build_game_loop,
#   idle_tick, run_turn).
# Основные сущности: test_gc00_tick_liveness (блок 1);
#   test_gc00_seed_determinism, test_gc00_probe_97_rest_smoke (блок 2).
# Запуск: cd backend; python -m pytest tests/gameplay/test_tavern_vertical.py -v -s
import json
import logging

import pytest
from tests.gameplay.harness import TavernGameplayHarness

logger = logging.getLogger("gameplay.gc00")

_CAMPAIGN = "Open_road"
_TICKS = 100  # GC-00: 100 LLM-free тиков

_DECISION_EVENT_KEYS = (
    "npc_spoke", "offer_job", "request_service", "spread_rumor",
    "call_for_help", "change_role", "warn", "trade", "report",
)


def _decision_count(counters) -> int:
    """Решенческая активность = сумма decision-класса (зеркало
    ObservabilityTap.DECISION_EVENT_VALUES)."""
    return sum(counters.events_by_type.get(_k, 0) for _k in _DECISION_EVENT_KEYS)


@pytest.fixture
def harness():
    """Production runtime на каждый тест; dispose гарантирован даже при FAIL."""
    _h = TavernGameplayHarness(seed=42)
    _h.new_game()
    print(f"[GC00-SETUP] saves_dir={_h.game_loop.saves_dir}")
    yield _h
    _h.dispose()


def test_gc00_tick_liveness(harness):
    """GC-00 «Game is actually alive»: 100 LLM-free тиков через production
    idle_tick (commit → execute_pending → unlock). Жёсткие инварианты:
    (1) время растёт; (2) 0 TICK_CRASH; (3) ненулевая активность
    (решения/движение/транзиты). Нулевая зона = FAIL с таблицей, не молчание."""
    _crashes = []
    for _i in range(_TICKS):
        try:
            harness.advance_ticks(1)
        except Exception as _e:  # детектор: собираем ВСЕ падения, не прерываем
            _crashes.append((_i, repr(_e)))

    _c = harness.counters
    _scene = harness.get_scene() or {}
    _time_scene = _scene.get("game_time_seconds") or 0
    _time = max(_time_scene, _c.game_time_seconds)

    print("\n[GC00-LIVENESS] ================= BASELINE =================")
    print(f"ticks_ok={_TICKS - len(_crashes)}/{_TICKS}  crashes={len(_crashes)}")
    if _crashes:
        print(f"FIRST CRASH: tick={_crashes[0][0]}: {_crashes[0][1]}")
    print(f"time_scene={_time_scene} time_counters={_c.game_time_seconds} tick={_scene.get('tick')}")
    print(f"decisions={_decision_count(_c)}  npc_spoke={_c.npc_spoke}  moved={_c.npc_moved}")
    print(f"traversals_active={_c.traversals_created}")
    print(f"events_by_type={json.dumps(_c.events_by_type, ensure_ascii=False)}")
    print(f"pending_tail(last10)={_c.pending_tasks_tail[-10:]}")
    print(f"last_event={_c.last_event}")
    print("[GC00-LIVENESS] =================================================\n")

    assert not _crashes, (
        f"GC00: TICK_CRASH {len(_crashes)}/{_TICKS}; первый: tick={_crashes[0][0]} "
        f"{_crashes[0][1]} — suspect: idle_tick-конвейер (trace выше)"
    )
    assert _time > 0, (
        "GC00: game_time_seconds = 0 в ОБОИХ источниках (сцена+счётчик) — "
        "INV-TIME-FREEZE либо idle_tick result-contract не распознан harness'ом; "
        "suspect: Фаза 0.5 / _scene_after_tick"
    )
    _activity = _decision_count(_c) + _c.npc_moved + _c.traversals_created
    assert _activity > 0, (
        "GC00: 100 тиков без решений/движений/транзитов — «пустая симуляция» "
        "(smoke давал 6/6 NPC-решений); счётчики в выводе; suspect: "
        "DecisionHub → Фаза 6 → IntentEventAdapter (события не публикуются?) "
        "или tap-подписка (см. GC00-SETUP warning)"
    )


def test_gc00_seed_determinism():
    """GC-00 «Same seed → same causal history»: 2 независимых прогона
    (свежий harness каждый, seed=42) по 30 тиков; сравнение тик-отпечатков
    сцены. Первое расхождение = диагноз (DEBT-QUIESCE-класс: async
    interleaving), не заглушается."""
    _N = 30
    _runs = []
    for _run_idx in range(2):
        _h = TavernGameplayHarness(seed=42)
        _h.new_game()
        try:
            _fps = _h.advance_ticks(_N)
        finally:
            _h.dispose()
        _runs.append(_fps)
        print(f"[GC00-DET] run{_run_idx + 1}: last_time={_h.counters.game_time_seconds} "
              f"spoke={_h.counters.npc_spoke} moved={_h.counters.npc_moved}")

    _a, _b = _runs
    # Анти-вакуум: PASS на всех-None отпечатках запрещён
    _non_null = sum(1 for _f in _a if _f.get("tick") is not None)
    print(f"[GC00-DET] fingerprints non-null: {_non_null}/{len(_a)}")
    assert _non_null > 0, (
        "GC00-DET: все отпечатки None — контракт результата idle_tick не "
        "распознан harness'ом (_scene_after_tick); сравнение вакуумное"
    )
    _diverge = None
    for _i, (_fa, _fb) in enumerate(zip(_a, _b)):
        if _fa != _fb:
            _diverge = (_i, _fa, _fb)
            break

    print("\n[GC00-DET] ================ DETERMINISM ================")
    print(f"ticks_compared={min(len(_a), len(_b))}  diverge_tick={_diverge[0] if _diverge else None}")
    if _diverge:
        print(f"run1@{_diverge[0]}: {_diverge[1]}")
        print(f"run2@{_diverge[0]}: {_diverge[2]}")
    print("[GC00-DET] ==================================================\n")

    # Baseline №3-урок: offset расхождения = числу тиков прогона →
    # контаминация, не недетерминизм. DEBT-QUIESCE — только при
    # доказанной изоляции (saves+sessions+синглтоны).
    assert _diverge is None, (
        f"GC00-DET: первое расхождение на тике {_diverge[0]}: "
        f"{_diverge[1]} vs {_diverge[2]} — suspect-лестница: (1) контаминация "
        f"состояния (saves/sessions world_tick/синглтоны; признак — offset "
        f"кратен числу тиков прогона), (2) DEBT-QUIESCE (только при "
        f"доказанной изоляции)"
    )


def test_gc00_probe_97_rest_smoke():
    """PROBE 9.7 regression (живая верификация Шага 3): 5 тиков idle →
    REST-ход run_turn → в ЭТОМ же ходу очередь pending_tasks должна
    разбираться (наш фикс :1481). Честные красные: (а) LLM-off →
    LLM-задачи не материализуются (это не наш фикс, это ADR-O-343);
    (б) fast-path события могут не существовать к ходу — тогда
    инвариант «фикс выполняется» проверяется по отсутствию роста
    очереди, а полный реплика-в-памяти smoke переносится в LLM-сессию."""
    _h = TavernGameplayHarness(seed=42)
    _h.new_game()
    try:
        _h.advance_ticks(5)
        _scene_before = _h.get_scene_fresh() or _h.get_scene() or {}
        _pending_before = len(_scene_before.get("pending_tasks", []) or [])

        _resp = _h.player_action("осмотреться")

        _scene_after = _h.get_scene_fresh() or _h.get_scene() or {}
        _pending_after = len(_scene_after.get("pending_tasks", []) or [])
        _recent = getattr(_resp, "world_snapshot", None) or {}
        _recent_d = _recent.get("recent_dialogues", []) if isinstance(_recent, dict) else []

        print("\n[GC00-P97] ============== PROBE 9.7 ==================")
        print(f"pending_before={_pending_before}  pending_after={_pending_after}")
        print(f"resp_type={type(_resp).__name__}  recent_dialogues={len(_recent_d)}")
        print(f"dm_response_len={len(getattr(_resp, 'dm_response', '') or '')}")
        print(f"npc_spoke_counters={_h.counters.npc_spoke}")
        print("[GC00-P97] ==================================================\n")

        # Инвариант Шага 3 (мягкий): очередь не РАСТЁТ после REST-хода —
        # execute_pending отработал. Рост = фикс не выполняется (красный
        # с прямым подозреваемым :1481).
        assert _pending_after <= _pending_before, (
            f"GC00-P97: pending_tasks вырос после REST-хода "
            f"({_pending_before} → {_pending_after}) — PROBE 9.7-фикс "
            f"(game_loop/__init__.py:1481) не разбирает очередь; "
            f"suspect: условие _auth_scene/pending_tasks в блоке фикса"
        )
    finally:
        _h.dispose()


def test_gc00_avid1_avatar_in_idle_pipeline():
    """AVID-1 зонд (Шаг 7, Стадия 2): аватар в idle-тике.

    Археология: инъекция аватара живёт в _load_npcs_with_runtime (:822,
    ADR-030 Actor-Agnostic) — но этот метод вызывается только REST-путём
    (:1332, :1414, :1866); idle-путь собирает NPC иначе. Зонд фиксирует
    ФАКТ (не вердикт): есть ли аватар в кэше, в idle-snapshot, в REST-срезе;
    тело (Шаг 6) — живо ли. Исход определяет вердикт GAP/BY-DESIGN в
    Стадии 3 — зонд сам по себе ни зелёный, ни красный, он диагностический:
    ассертов на «должен присутствовать» нет, есть только печать и мягкая
    проверка непустоты данных для диагностики.
    """
    _h = TavernGameplayHarness(seed=42)
    _h.new_game()
    try:
        _h.advance_ticks(3)
        _engine = _h.game_loop._get_life_engine()
        _cache_ids = sorted(
            {(n.get("id") or n.get("npc_id") or "?") for n in (_engine.get_npc_states("Open_road") or [])}
        )
        _snapshot_ids = sorted(
            {(n.get("id") or n.get("npc_id") or "?") for n in (_h.game_loop._resolve_npcs_snapshot("Open_road") or [])}
        )
        _rest_ids = sorted(
            {(n.get("id") or n.get("npc_id") or "?") for n in (_h.game_loop._load_npcs_with_runtime("Open_road") or [])}
        )
        _av = _h.game_loop.avatar_service.load_state("Open_road", "Tester")

        print("\n[AVID-1] ============== AVATAR IN IDLE ============")
        print(f"lifeengine_cache_ids = {_cache_ids}")
        print(f"resolve_snapshot_ids = {_snapshot_ids}")
        print(f"load_with_runtime_ids = {_rest_ids}")
        print(f"avatar_body_alive = {_av.body_state.get('life_status', '<ABSENT>')}, hp={_av.effective_hp}")
        print("[AVID-1] ===========================================\n")

        # Мягкие диагностические проверки (не ассерты «должен»):
        assert _rest_ids, "AVID-1: _load_npcs_with_runtime вернул пустой список — данные для диагностики отсутствуют"
        assert _av.effective_hp > 0, "AVID-1: регресс AG1-D5 — тело аватара пустое"
    finally:
        _h.dispose()
    """AG1-D5 red/green-зонд (Шаг 6, Этап A — фикс ОТЛОЖЕН, вердикт Мастера).

    Проверка структуры, не логов: STATE APPLIED условен («state changed»),
    [FATE] в headless не стрелял. Цепь: new_game → load_state default-ветка
    (clean-start: файла аватара нет) → body_state → effective_hp →
    life_status → Death Guard input (:2154, get('life_status','ALIVE')).
    Ожидание (онтология): fresh world = здоровое тело, NPC-паритет
    (BODY_STATE_HEALTHY: game_loop:921, life_engine:749, npc_loader:336);
    §ENIGMA-003: отсутствие данных ≠ нейтраль 0.0.
    """
    _h = TavernGameplayHarness(seed=42)
    _h.new_game()
    try:
        _h.advance_ticks(3)  # материализовать dict-сторону (LifeEngine-кэш)

        _av = _h.game_loop.avatar_service.load_state("Open_road", "Tester")
        _bs = dict(getattr(_av, "body_state", None) or {})

        print("\n[AG1-D5] ============= AVATAR BODY ===============")
        print(f"npc_id={_av.npc_id}")
        print(f"body_state keys={sorted(_bs.keys())}")
        print(f"current_hp={_bs.get('current_hp', '<ABSENT>')} "
              f"max_hp={_bs.get('max_hp', '<ABSENT>')}")
        print(f"effective_hp={_av.effective_hp}  "
              f"effective_max_hp={_av.effective_max_hp}")
        print(f"life_status={_bs.get('life_status', '<ABSENT>')} "
              f"money={_bs.get('money', '<ABSENT>')}")

        # Dict-сторона: есть ли ВТОРОЕ тело (DOUBLE TRUTH)?
        for _nid in ("player", "Tester"):
            _d = _h.inspect_npc(_nid)
            if _d:
                _dbs = _d.get("body_state") or {}
                print(f"dict[{_nid}]: body_keys={sorted(_dbs.keys())} "
                      f"current_hp={_dbs.get('current_hp', '<ABSENT>')}")
            else:
                print(f"dict[{_nid}]: <NOT IN SNAPSHOT>")
        print("[AG1-D5] ===========================================\n")

        assert "current_hp" in _bs, (
            "AG1-D5: avatar default body_state без current_hp "
            f"(keys={sorted(_bs.keys())}) — effective_hp падает в 0.0-fallback "
            "(npc_state:796; семантика = BODY_STATE_DISABLED, :66-73) в свежем "
            "мире. NPC получают BODY_STATE_HEALTHY (game_loop:921), аватар — "
            "нет: асимметрия инициализации; §ENIGMA-003: absence != 0.0. "
            "Фикс Stage B: {**BODY_STATE_HEALTHY, 'money': 48} "
            "construction-time (S208-прецедент). NOT fixed here"
        )
        assert _av.effective_hp > 0, "AG1-D5: effective_hp=0.0 в новом мире"
        assert "life_status" in _bs, (
            "AG1-D5: life_status отсутствует — Death Guard видит дефолт 'ALIVE' "
            "(:2154) при неинициализированном теле"
        )
    finally:
        _h.dispose()
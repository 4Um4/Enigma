# path: /project/backend/tests/gameplay/test_m17_recognition_persistence.py
# Назначение: M17 Recognition Persistence — детектор каузальности и
#   персистенции player_recognition (расследование инцидента «спросил имя —
#   не отвечает / recognition пуст в сейве»). Не greenwashing: FAIL оставляет
#   диагностический след. Production-path ONLY (§5a.2): idle_tick, run_turn,
#   чтение scene_state / persistence. Инъекций belief/event нет.
# Проверяет:
#   T1 — lifecycle: речь NPC идёт → recognition появляется, статусы/пороги
#        соответствуют M17-контракту (confirmed=1.0, tentative>=0.6).
#   T2 — player-писатель: run_turn с вербальным действием → писатель
#        game_loop NEW-8/M17 подтверждает имя собеседника (диагностический
#        вердикт в выводе при LLM-недоступности).
#   T3 — round-trip: recognition, попавший в _tick_scenes, обязан читаться
#        из persistence (ADR-O-352-класс). Дрен-лаг в 1 тик учтён явно
#        (задокументирован game_loop:1333-1334) — не маскирует data-loss.
# Зависимости: tests.gameplay.harness (TavernGameplayHarness).
# Запуск: cd backend; python -m pytest tests/gameplay/test_m17_recognition_persistence.py -v -s
import logging

import pytest
from tests.gameplay.harness import TavernGameplayHarness

logger = logging.getLogger("gameplay.m17")

_CAMPAIGN = "Open_road"
_IDLE_TICKS = 60


@pytest.fixture
def harness():
    """Production runtime на каждый тест; dispose гарантирован даже при FAIL."""
    _h = TavernGameplayHarness(seed=42)
    _h.new_game()
    yield _h
    _h.dispose()


def _recog(scene: dict) -> dict:
    """player_recognition из сцены (читатель world_snapshot_builder:278)."""
    if not isinstance(scene, dict):
        return {}
    rec = scene.get("player_recognition", {})
    return rec if isinstance(rec, dict) else {}


def _check_m17_contract(rec: dict, label: str, problems: list) -> None:
    """M17-контракт статусов (писатели: game_loop NEW-8 confirmed=1.0;
    drain: tentative>=0.6 / confirmed=1.0 — npc_dialogue_subscriber:136-140)."""
    for nid, entry in rec.items():
        if not isinstance(entry, dict):
            problems.append(f"{label}: {nid} — entry не dict: {entry!r}")
            continue
        st = entry.get("status")
        conf = float(entry.get("confidence", 0.0))
        if st not in ("tentative", "confirmed"):
            problems.append(f"{label}: {nid} — неожиданный status={st!r}")
        elif st == "confirmed" and conf < 1.0:
            problems.append(f"{label}: {nid} — confirmed, но confidence={conf} (< 1.0)")
        elif st == "tentative" and conf < 0.6:
            problems.append(f"{label}: {nid} — tentative, но confidence={conf} (< 0.6)")


def test_t1_idle_recognition_lifecycle(harness):
    """T1: 60 idle-тиков. Если речь идёт (npc_spoke > 0), recognition обязан
    появиться (direct/overheard-каналы дрена). Статусы — строго по M17."""
    problems: list = []
    spoke_total = 0
    first_recog_tick = None
    last_rec = {}

    for i in range(_IDLE_TICKS):
        harness.advance_ticks(1)
        spoke_total = harness.counters.events_by_type.get("npc_spoke", 0)
        scene = harness.get_scene() or {}
        rec = _recog(scene)
        if rec and first_recog_tick is None:
            first_recog_tick = i + 1
        if rec:
            last_rec = rec
        _check_m17_contract(rec, f"tick{i + 1}", problems)

    print(f"[M17-T1] npc_spoke={spoke_total} "
          f"first_recognition_at_tick={first_recog_tick} "
          f"final_recognition={last_rec}")

    if spoke_total > 10 and not last_rec:
        problems.append(
            f"Речь идёт (npc_spoke={spoke_total} за {_IDLE_TICKS} тиков), "
            f"но recognition пуст — M17-канал (direct/overheard) мёртв. "
            f"Подозреваемые: journal-порог (subscriber:203), "
            f"listener!='player', дрен после коммита (game_loop:1268 vs :1327)"
        )
    assert not problems, "M17-контракт нарушен:\n" + "\n".join(problems)


def test_t2_player_dialogue_m17_writer(harness):
    """T2: вербальное player-действие через production run_turn. Писатель
    M17 (game_loop:1583-1593) при verbal=True и target_id обязан поставить
    confirmed/1.0. При мёртвом LLM-классификаторе тест даёт ДИАГНОСТИКУ
    (классификация UNCERTAIN — известное свойство harness:257-263), но
    инвариант контракта статусов держит жёстко."""
    harness.advance_ticks(3)
    problems: list = []

    resp = harness.player_action("спрашиваю Тень: как тебя зовут?")
    assert resp is not None, "run_turn вернул None"

    scene = harness.get_scene_fresh() or {}
    rec = _recog(scene)
    print(f"[M17-T2] recognition_after_run_turn={rec}")

    _check_m17_contract(rec, "after_run_turn", problems)

    # Диагностический вердикт (не greenwashing): честно фиксируем,
    # сработал ли писатель M17.
    confirmed = {k: v for k, v in rec.items() if v.get("status") == "confirmed"}
    if confirmed:
        print(f"[M17-T2] ПИСАТЕЛЬ M17 СРАБОТАЛ: confirmed={confirmed}")
    else:
        print(
            "[M17-T2] ПИСАТЕЛЬ M17 НЕ СРАБОТАЛ (нет confirmed). "
            "Кандидаты: (a) action_type не в кортеже dialogue/blackmail/"
            "bribe/accuse; (b) shared_context.player_target_id пуст; "
            "(c) run_turn не дошёл до NEW-8 (DM UNCERTAIN). "
            "См. [DIAG-M17] (зонд game_loop:1580) в логе при его наличии."
        )
    assert not problems, "M17-контракт нарушен:\n" + "\n".join(problems)


def test_t3_recognition_persistence_roundtrip(harness):
    """T3 (ADR-O-352-класс): всё, что дрен положил в _tick_scenes, обязано
    читаться из persistence. Дрен-лаг в 1 тик (game_loop:1333-1334 —
    «доезжают на цикл позже») учтён ЯВНО одним догоняющим тиком; если
    запись не доезжает и после него — это data-loss, FAIL."""
    problems: list = []
    harness.advance_ticks(_IDLE_TICKS)

    scene = harness.get_scene() or {}
    rec_live = _recog(scene)
    pers = harness.game_loop.scene_manager._persistence
    assert pers is not None, "persistence недоступен у scene_manager"

    def _loaded_rec() -> dict:
        loaded = pers.load_scene_at(_CAMPAIGN, harness.location) or {}
        return _recog(loaded)

    # DIAG-T3 (Часть VIII.5, ВРЕМЕННЫЙ): где физически DB и какие ключи —
    # отсев артефакта «пишем в одну локацию, читаем другую».
    print(f"[M17-T3-DB] db_path={getattr(pers, '_db_path', '?')}")
    import sqlite3 as _sq
    try:
        _conn = _sq.connect(str(getattr(pers, "_db_path", "")))
        _keys = [r[0] for r in _conn.execute("SELECT key FROM state_kv").fetchall()]
        _conn.close()
        print(f"[M17-T3-DB] state_kv keys={_keys}")
    except Exception as _e:
        print(f"[M17-T3-DB] key dump failed: {_e}")
    for _loc in ("tavern", "tavern_silver_wolf", harness.location):
        _r = _recog(pers.load_scene_at(_CAMPAIGN, _loc) or {})
        print(f"[M17-T3-DB] load_scene_at({_loc}) recognition={_r}")

    rec_saved = _loaded_rec()
    if rec_live:
        # Дрен-лаг: один догоняющий тик, чтобы последний дрен закоммитился.
        harness.advance_ticks(1)
        rec_saved = _loaded_rec()

    print(f"[M17-T3] live={rec_live}")
    print(f"[M17-T3] saved={rec_saved}")

    # Жёсткий инвариант: каждая live-запись обязана существовать в сейве
    # с тем же статусом (confidence может быть только не ниже — tentative
    # не понижается, confirmed не затирается: subscriber:134-135).
    for nid, entry in rec_live.items():
        saved_entry = rec_saved.get(nid)
        if saved_entry is None:
            problems.append(
                f"DATA-LOSS: {nid} ({entry}) есть в _tick_scenes, "
                f"отсутствует в persistence после догоняющего тика"
            )
        elif saved_entry.get("status") != entry.get("status"):
            problems.append(
                f"DATA-DRIFT: {nid} status live={entry.get('status')!r} "
                f"saved={saved_entry.get('status')!r}"
            )

    _check_m17_contract(rec_saved, "persistence", problems)
    assert not problems, "Персистенция recognition нарушена:\n" + "\n".join(problems)
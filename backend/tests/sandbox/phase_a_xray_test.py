"""
Назначение: Фаза A (Шаги 9–10) — живой головной прогон каскада памяти в реальном GameLoop без FastAPI/HTTP/сессий: scripted-ходы → рентген памяти NPC через production-функцию _xray_memory → пересборка GameLoop (имитация рестарта сервера) → повторный рентген и сверка персистентности
Зависимости: app.services.game_loop_builder, app.api.routes._xray_memory, LLM (опционально)
Основные сущности: GameLoop, _xray_memory, ChatTurnRequest

Запуск: python backend/tests/sandbox/phase_a_xray_test.py
"""

from __future__ import annotations

import asyncio
import atexit
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List

# Фаза A 9.10: APP_DIR в path порождал двойной импорт (app.* и services.*
# в sys.modules) → два синглтона EventBus: GameLoop подписывал на одну
# шину, PROBE публиковал в другую. Все импорты — только через корень
# backend (app.*), LLM-менеджер — через корень проекта (scripts.*).
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ROOT_DIR = _BACKEND_DIR.parent
for _p in (str(_BACKEND_DIR), str(_ROOT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# LLM: реплики NPC генерирует llama-server; память действий игрока пишется и без него
try:
    from scripts.llm_server_manager import kill_llama_server, start_llama_server

    if start_llama_server():
        atexit.register(kill_llama_server)
    else:
        print("[XRAY] LLM не запущен — реплики NPC недоступны; память игрока пишется")
except ModuleNotFoundError as _llm_err:
    print(f"[XRAY] LLM-менеджер недоступен ({_llm_err}) — продолжаем без LLM")

from app.services.llm.provider_manager import initialize_model_pool

initialize_model_pool()

from app.api.routes import _xray_memory
from app.models.schemas import ChatTurnRequest, PlayerAction
from app.services.game_loop_builder import build_game_loop

CAMPAIGN_ID = "Open_road"
LOCATION_ID = "tavern"
PLAYER_NAME = "XRayProbe"
NPC_IDS = ["merchant_goran", "maid_lusya", "tavern_keeper_tornin"]

TURNS: List[str] = [
    "осмотреться вокруг",
    "сказать торговцу: привет, я странник с севера, шёл через горный перевал",
    "спросить служанку: что тут происходит?",
]


def _short(value: Any, limit: int = 120) -> str:
    text = str(value).replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _mem_pairs(xray: Dict[str, Any]) -> List[Any]:
    """(summary, importance) SQLite-ветки — для сверки стабильности."""
    return [
        (m.get("summary"), round(float(m.get("importance", 0.0) or 0.0), 4))
        for m in (xray.get("narrative_cache_sqlite") or [])
    ]


async def main() -> int:
    failures: List[str] = []
    observations: List[str] = []
    data_dir = _ROOT_DIR / "data"

    print(f"[XRAY] Сборка GameLoop (кампания {CAMPAIGN_ID})...")
    game_loop = build_game_loop(data_dir=str(data_dir))

    print(f"[XRAY] Прогон {len(TURNS)} scripted-ходов...")
    position = (6.5, 5.5)
    for i, action_text in enumerate(TURNS, start=1):
        req = ChatTurnRequest(
            world_id="default",
            campaign_id=CAMPAIGN_ID,
            location=LOCATION_ID,
            actions=[PlayerAction(player_name=PLAYER_NAME, action=action_text)],
            player_position=position,
        )
        print(f"\n--- Ход {i}: {action_text}")
        try:
            response = await game_loop.run_turn(req)
            print(f"  DM: {_short(response.dm_response)}")
            for react in (response.npc_reactions or [])[:3]:
                print(f"  NPC: {_short(react, 90)}")
        except Exception as exc:  # noqa: ENIGMA001
            print(f"  [ERROR] тик упал: {exc}")
            traceback.print_exc()
            failures.append(f"turn_{i}_crash")


    # ── PROBE 9.12: почему подписчик молчит — прямой пошаговый вызов ──
    _sc = getattr(game_loop._tick_orch, "_shared_context", None)
    print("[PROBE_9_12] _shared_context:", _sc is not None)
    if _sc is not None:
        _anr = getattr(_sc, "all_npcs_raw", None)
        print("[PROBE_9_12] all_npcs_raw:", type(_anr).__name__, "len:", len(_anr) if _anr else 0)
        _snap = getattr(_sc, "all_npcs_raw_snapshot", None)
        print("[PROBE_9_12] snapshot:", type(_snap).__name__, "len:", len(_snap) if _snap else 0)
        _names = [n.get("id") or n.get("npc_id") for n in (_anr or [])][:8]
        print("[PROBE_9_12] ids в all_npcs_raw:", _names)


    # ── PROBE 9.7: живой провод NPC_SPOKE → память (зонд VIII.5) ──────
    # Подписчик доказан автономно (репетиция-2). Публикуем NPC_SPOKE руками:
    # строка появилась → подписан, разрыв выше (publish/RCE-условие);
    # нет → DialogueMemorySubscriber не зарегистрирован в этом wiring.
    # 9.10: шина берётся из модуля GameLoop'а — исключает расщепление
    import app.services.events.event_bus as _probe_bus_mod
    from app.domain.events import EventDTO as _ProbeEvent
    from app.services.events.event_types import EventType as _ProbeType

    _probe_bus = _probe_bus_mod.get_event_bus()

    _probe_bus.publish(
        _ProbeEvent.create(
            event_type=_ProbeType.NPC_SPOKE,
            source="Торнин Серебряная Луна",
            payload={
                "npc_id": "tavern_keeper_tornin",
                "content": "зонд 9.7: провод речи в живом лупе",
                "action_type": "dialogue_key",
            },
        )
    )
    _probe_rows = game_loop.memory_manager._layered.store.query(
        "SELECT npc_id, summary FROM event_memories WHERE event_type='npc_spoke'"
    )
    print(f"[PROBE_9_7] npc_spoke-строк после прямой публикации: {len(_probe_rows)}")
    for _pr in _probe_rows:
        print(f"  · {_pr['npc_id']} | {(_pr['summary'] or '')[:60]}")

    # ── Рентген после сессии ─────────────────────────────────────────
    xray_first: Dict[str, Dict[str, Any]] = {}
    print("\n[XRAY] Рентген после сессии (production _xray_memory):")
    for npc_id in NPC_IDS:
        try:
            xray = _xray_memory(game_loop, CAMPAIGN_ID, npc_id)
            xray_first[npc_id] = xray
        except Exception as exc:  # noqa: ENIGMA001
            print(f"  [ERROR] рентген {npc_id} упал: {exc}")
            traceback.print_exc()
            failures.append(f"xray_{npc_id}_crash")
            continue
        print(f"\n=== РЕНТГЕН [{npc_id}] ===")
        print(json.dumps(xray, ensure_ascii=False, indent=2, default=str)[:3500])
        if xray.get("xray_error"):
            failures.append(f"xray_{npc_id}_error")
        _js = xray.get("json_state") or {}
        if _js.get("narrative_cache_len"):
            print(
                f"  [JSON] narrative_cache_len={_js.get('narrative_cache_len')}, "
                f"affective_load={_js.get('affective_load')}"
            )

    # Шаги 6/7: повторный рентген на том же loop — importance не должна ползти
    print("\n[XRAY] Стабильность importance при повторных загрузках (Шаги 6/7):")
    for npc_id, first in xray_first.items():
        second = _xray_memory(game_loop, CAMPAIGN_ID, npc_id)
        if _mem_pairs(first) != _mem_pairs(second):
            failures.append(f"{npc_id}_importance_drift")
            print(f"  ❌ {npc_id}: importance дрейфует между загрузками")
        else:
            print(f"  ✅ {npc_id}: стабильна ({len(_mem_pairs(first))} записей)")

    # Шаг 4: тексты в воспоминаниях
    print("\n[XRAY] Тексты воспоминаний (Шаг 4):")
    for npc_id, xray in xray_first.items():
        summaries = [m.get("summary") for m in (xray.get("narrative_cache_sqlite") or [])]
        texts = [s for s in summaries if s]
        if not summaries:
            observations.append(f"{npc_id}: SQLite-память пуста после 3 ходов")
            print(f"  ⚠️ {npc_id}: SQLite пуст — фиксируется как наблюдение")
        elif len(texts) < len(summaries):
            failures.append(f"{npc_id}_empty_summaries")
            print(f"  ❌ {npc_id}: {len(summaries) - len(texts)} записей с пустым текстом")
        else:
            print(f"  ✅ {npc_id}: {len(texts)} записей, все с текстом")
            for s in texts[:3]:
                print(f"     · {_short(s, 80)}")

    # ── Имитация рестарта сервера: пересборка GameLoop на тех же сейвах ──
    print("\n[XRAY] ПЕРЕЗАПУСК: пересборка GameLoop...")
    game_loop_2 = build_game_loop(data_dir=str(data_dir))
    print("[XRAY] Рентген после рестарта + сверка персистентности:")
    for npc_id, first in xray_first.items():
        try:
            after = _xray_memory(game_loop_2, CAMPAIGN_ID, npc_id)
        except Exception as exc:  # noqa: ENIGMA001
            failures.append(f"restart_xray_{npc_id}_crash")
            print(f"  ❌ {npc_id}: рестарт-рентген упал: {exc}")
            continue
        if _mem_pairs(first) != _mem_pairs(after):
            failures.append(f"{npc_id}_restart_drift")
            print(f"  ❌ {npc_id}: SQLite-память изменилась после рестарта")
        elif _mem_pairs(first):
            print(f"  ✅ {npc_id}: SQLite-память пережила рестарт ({len(_mem_pairs(first))} записей)")
        t1 = first.get("identity_traits") or {}
        t2 = after.get("identity_traits") or {}
        if t1 != t2:
            failures.append(f"{npc_id}_identity_lost")
            print(f"  ❌ {npc_id}: identity_traits потеряны: {t1} → {t2}")
        elif t1:
            print(f"  ✅ {npc_id}: identity_traits пережили рестарт: {t1}")
        else:
            observations.append(f"{npc_id}: identity_traits пусты (резонанс не срабатывал — ожидаемо на короткой сессии)")
        b1 = (first.get("json_state") or {}).get("beliefs") or {}
        b2 = (after.get("json_state") or {}).get("beliefs") or {}
        if b1 != b2:
            failures.append(f"{npc_id}_beliefs_lost")
            print(f"  ❌ {npc_id}: beliefs изменились после рестарта: {b1} → {b2}")
        elif b1:
            print(f"  ✅ {npc_id}: beliefs пережили рестарт: {b1}")
        else:
            observations.append(f"{npc_id}: psyche.beliefs пусты (дельты не доезжают до write-back — зона B2)")
        r1 = first.get("relationship_to_player")
        if r1:
            print(f"  ℹ️ {npc_id}: отношения к игроку: {r1}")

    # ── Итог ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if observations:
        print(f"НАБЛЮДЕНИЯ ({len(observations)}):")
        for o in observations:
            print(f"  ⚠️ {o}")
    if failures:
        print(f"\n🔴 ПРОВАЛЫ ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\n✅ ФАЗА A (рентген + персистентность): живой прогон чист.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
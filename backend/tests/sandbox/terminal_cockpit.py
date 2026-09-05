"""
path: backend/tests/sandbox/terminal_cockpit.py
Назначение: EMRL E1.4 — кокпит разработчика: живые ходы + рентген памяти
+ время + рестарт, поверх production-GameLoop (не мок).
Зависимости: game_loop_builder, _xray_memory, llm_server_manager
Основные сущности: GameLoop
Запуск: python backend/tests/sandbox/terminal_cockpit.py
"""
from __future__ import annotations

import asyncio
import atexit
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ROOT_DIR = _BACKEND_DIR.parent
for _p in (str(_BACKEND_DIR / "app"), str(_BACKEND_DIR), str(_ROOT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# E1.4: заглушки по умолчанию — если менеджер не импортируется,
# ссылки на start/kill остаются определёнными (Pylance/NameError)
def _llm_noop() -> bool:
    return False

kill_llama_server: Callable[[], Any] = _llm_noop
start_llama_server: Callable[[], Any] = _llm_noop

try:
    import time as _t
    import urllib.request as _ur

    from scripts.llm_server_manager import kill_llama_server, start_llama_server

    _llm_ok = start_llama_server()
    # health-валидация: «запущен» менеджера ≠ «жив» порта (урок 10061:
    # менеджер кеширует состояние умершего чужого сервера)
    if _llm_ok:
        for _ in range(15):
            try:
                _ur.urlopen("http://localhost:8181/health", timeout=2).read()
                break
            except Exception:
                _t.sleep(2)
        else:
            print("[COCKPIT] LLM-порт не отвечает — пробуем переподъём")
            _llm_ok = start_llama_server()
    if _llm_ok:
        atexit.register(kill_llama_server)
    else:
        print("[COCKPIT] LLM не поднят — нарратив будет деградировать")
except ModuleNotFoundError as _e:
    print(f"[COCKPIT] LLM-менеджер недоступен ({_e})")

from app.services.llm.provider_manager import initialize_model_pool

initialize_model_pool()

from app.api.routes import _xray_memory
from app.models.schemas import ChatTurnRequest, PlayerAction
from app.services.game_loop_builder import build_game_loop

# ── Конфигурация ─────────────────────────────────────────────────────
# E1.4: имя из CLI; XRayProbe в сейвах — прошлый аватар, не конфликтуем
# с ним по умолчанию (перезаписывать чужой аватар со старта — дурной тон;
# при несовпадении будет warning, как сейчас, — безвреден)
import sys as _sys

CAMPAIGN = "Open_road"
LOCATION = "tavern"
PLAYER = (
    next((a.split("=", 1)[1] for a in _sys.argv[1:] if a.startswith("--player=")), "XRayProbe")
)
DEFAULT_POS = (6.5, 5.5)

# Адресация: префикс «имя:» или «сказать <имя>» — из карты имён сцены
ADDR_PREFIX_HINT = (
    "горан: | люся: | орм: | борко: | тень: | торнин: — сказать конкретному NPC"
)

HELP = """
── КОМАНДЫ ──────────────────────────────────────────────
mem [npc]     — рентген памяти NPC (по умолчанию все ключевые)
портрет npc   — кристаллы + трейсы + убеждения NPC
wait N        — N idle-тиков (время мира; N≤20)
restart       — пересборка GameLoop на тех же сейвах
день          — тик/день/статус
help          — эта справка
exit          — выход
─────────────────────────────────────────────────────────
Говорить: свободный текст.
Адресовать: «горан: привет» или «сказать горану: привет».
"""

KEY_NPCS = ("merchant_goran", "maid_lusya", "tavern_keeper_tornin")

NAME_MAP = {
    "горан": "merchant_goran",
    "торнин": "tavern_keeper_tornin",
    "люся": "maid_lusya",
    "орм": "blacksmith_orm",
    "борко": "guard_borko",
    "тень": "thief_shadow",
}


def parse_target(text: str) -> Tuple[Optional[str], str]:
    """Выделяет адресата: «горан: ...» или «сказать горану: ...»."""
    lowered = text.lower().strip()
    for name, npc_id in NAME_MAP.items():
        if lowered.startswith(name + ":"):
            return npc_id, text[len(name) + 1 :].strip()
        if lowered.startswith("сказать " + name):
            rest = text[len("сказать " + name) :].lstrip("уая ").strip(" :")
            return npc_id, rest
    return None, text


def _short(v, n=100):
    s = str(v).replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


class Cockpit:
    def __init__(self) -> None:
        self.loop = build_game_loop(data_dir=_ROOT_DIR / "data")
        self.pos = DEFAULT_POS
        self.turn = 0

    async def act(self, text: str, target: Optional[str]) -> None:
        # E1.4: явная адресация — префикс «горан: ...» попадает в текст
        # действия (резолвер Слоя 2 матчит имя; PLAYER_SPOKE.target
        # определяет, КТО запоминает в первую очередь)
        _action = f"[обращаясь к {target}] {text}" if target else text
        req = ChatTurnRequest(
            world_id="default",
            campaign_id=CAMPAIGN,
            location=LOCATION,
            actions=[PlayerAction(player_name=PLAYER, action=_action)],
            player_position=self.pos,
        )
        resp = await self.loop.run_turn(req)
        print(f"\n  DM: {_short(resp.dm_response, 400)}")
        for r in (resp.npc_reactions or [])[:3]:
            print(f"  NPC: {_short(r, 110)}")
        # позиция игрока из снапшота — как в run_terminal_mvp
        snap = resp.world_snapshot or {}
        pp = snap.get("player_position") or (resp.npc_positions or {}).get(
            "player", {}
        ).get("local_position")
        if pp:
            self.pos = (float(pp[0]), float(pp[1]))

    def xray(self, npc_ids: List[str]) -> None:
        for npc in npc_ids:
            try:
                x = _xray_memory(self.loop, CAMPAIGN, npc)
            except Exception as e:  # noqa: ENIGMA001
                print(f"  [mem {npc}] ошибка: {e}")
                continue
            print(f"\n── mem {npc} ──")
            rows = x.get("narrative_cache_sqlite") or []
            print(f"  эпизодов: {len(rows)}")
            for m in rows[:6]:
                print(f"    · imp={m.get('importance', 0):.2f} | {m.get('summary', '')[:70]}")
            cr = x.get("crystals") or []
            if cr:
                print(f"  кристаллов: {len(cr)}")
                for c in cr[:5]:
                    print(f"    · {c}")
            traits = x.get("identity_traits") or {}
            if traits:
                print(f"  identity: {traits}")
            rel = x.get("relationship_to_player")
            if rel:
                print(f"  отношение: {rel}")

    async def wait(self, n: int) -> None:
        """E1.4/ADR-O-373 (cockpit-режим): быстрый мир не ждёт интеллекта.

        Экстракция смысла диалогов (DialogueUpdateExtractor → LLM,
        future.result(60) синхронно в тике) — «медленный консультант»:
        на время wait отцепляем его у потребителя (подписчика), тики
        идут без LLM-шлагбаума. Сырой текст в память пишется и без
        экстракции (Фаза A); смысл доедет позже — через обычные ходы
        или будущий outbox-дренаж (полная форма ADR-O-373 в TaskScheduler).
        """
        import inspect as _inspect

        # E1.4 фикс-2: экстрактор ищем по ТИПУ во всех точках инъекции —
        # прошлое место (memory-подписчик) его не имеет; реальный вызов
        # идёт из TaskScheduler._process_tasks_async → NpcDialogueSubscriber
        # (npc_dialogue_subscriber.py:131) и, возможно, ещё из мест.
        # Надёжно: отключаем сам класс (метод), а не конкретный инстанс.
        # AG1-D8p Шаг 2 — измерительный режим baseline ДО (test-zone, обратимо):
        # D8P_BASELINE_NO_DETACH=1 → wait БЕЗ класс-отцепления экстрактора.
        # R2-ось: сцепка «экстракция ↔ поток публикатора» остаётся живой
        # (cockpit wait = loop-thread → RE-D2 guard → пустой DialogueUpdate).
        # R1-ось: wall-clock печатается в finally независимо от исхода тиков.
        import os as _os
        import time as _wc_time
        _no_detach = bool(_os.environ.get("D8P_BASELINE_NO_DETACH"))
        _wc_t0 = _wc_time.monotonic()
        _orig_extract = None
        if not _no_detach:
            try:
                from app.services.memory import dialogue_update_extractor as _due_mod

                _orig_extract = _due_mod.DialogueUpdateExtractor.extract
                # runtime-патч: заглушка возвращает None — существующее
                # поведение подписчика при отказе экстракции
                # ("Dialogue update failed" уже живёт с None)
                _due_mod.DialogueUpdateExtractor.extract = (  # type: ignore[method-assign]
                    lambda self, stm_before, new_turn, partner: None  # type: ignore[assignment, return-value, no-any-return]
                )
                print("  [wait] медленный интеллект отцеплен (быстрый мир, класс-уровень)")
            except ImportError:
                pass  # модуль не найдён — отцеплять нечего
        else:
            # AG1-D8p Шаг 2, блок 2 (инцидент частичного применения c7a4a644):
            # при D8P_BASELINE_NO_DETACH сцепка НЕ разрывается — fast-path
            # публикации idle-тиков идут в подписчик на потоке петли →
            # RE-D2 guard → наблюдаемая деградация (R2-ось в окне замера,
            # счёт в логе прогона, НЕ в тике).
            print("  [wait] D8P_BASELINE_NO_DETACH=1: экстрактор НЕ отцеплен (baseline ДО, R2 живая)")
        try:
            for i in range(n):
                try:
                    _r = self.loop.idle_tick(CAMPAIGN)
                    if _inspect.iscoroutine(_r):  # type: ignore[unreachable]
                        await _r
                except Exception as e:  # noqa: ENIGMA001
                    print(f"  [wait] тик {i} упал: {e}")
                    return
                if (i + 1) % 5 == 0:
                    print(f"  … тик {i + 1}/{n}")
            print(f"  время: +{n} тиков")
        finally:
            # AG1-D8p Шаг 2 (R1): wall-clock печатается ВСЕГДА — даже при раннем
            # return упавшего тика (метрика = числа, НЕ впечатление).
            print(
                f"  [wait] wall-clock: {_wc_time.monotonic() - _wc_t0:.2f}s"
                f" | no_detach={_no_detach}"
            )
            if _orig_extract is not None:
                from app.services.memory import dialogue_update_extractor as _due_mod

                _due_mod.DialogueUpdateExtractor.extract = _orig_extract  # type: ignore[method-assign]
                print("  [wait] медленный интеллект восстановлен")

    def restart(self) -> None:
        print("  пересборка GameLoop на тех же сейвах…")
        self.loop = build_game_loop(data_dir=_ROOT_DIR / "data")
        print("  рестарт ок (память/кристаллы/убеждения пережили)")
        # E1.4: пул LLM глобален, backoff 300с может жить в нём после
        # падения — health-чек и переподъём (урок прогона с 10061)
        import urllib.request as _ur
        try:
            _ur.urlopen("http://localhost:8181/health", timeout=2).read()
        except Exception:
            print("  LLM мёртв — поднимаю…")
            try:
                start_llama_server()
            except Exception:  # noqa: ENIGMA001
                print("  [restart] LLM не поднялся")

    def status(self) -> None:
        tick = getattr(self.loop, "_current_tick", 0)
        print(f"  тик: {tick} | ходов: {self.turn} | позиция: {self.pos}")


async def main() -> None:
    print("═" * 60)
    print("ENIGMA COCKPIT — живой терминал разработки")
    print(f"кампания: {CAMPAIGN} | игрок: {PLAYER}")
    print(HELP)
    cp = Cockpit()
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        low = line.lower()
        if low in ("exit", "quit", "выход"):
            break
        if low in ("help", "?", "справка"):
            print(HELP)
            continue
        if low == "restart":
            cp.restart()
            continue
        if low == "new":
            # E1.4: чистый старт (ADR-O-146: new_game = сброс к static).
            # Дев-цикл: SQLite-память NPC межсессионна — без сброса каждый
            # эксперимент наследует прошлые прогоны (урок: Торнин помнил
            # тестовые ходы xray). LLM: сброс мира не должен касаться
            # сервера, но сервер мог умереть независимо (урок 10061) —
            # health-чек и подъём здесь же.
            print("  сброс мира к чистому static…")
            try:
                cp.loop.new_game(CAMPAIGN, continuity_mode="isolated")
                cp.pos = DEFAULT_POS
                print("  мир сброшен")
            except TypeError:
                # сигнатура отличается — пробуем позиционно
                try:
                    cp.loop.new_game(CAMPAIGN)
                    cp.pos = DEFAULT_POS
                    print("  мир сброшен (позиц. сигнатура)")
                except Exception as e:  # noqa: ENIGMA001
                    print(f"  [new] new_game: {e}")
                    continue
            except Exception as e:  # noqa: ENIGMA001
                print(f"  [new] new_game: {e}")
                continue
            # LLM-здоровье (инвариант ADR-O-373-neighbor: мир ≠ интеллект)
            import urllib.request as _ur

            try:
                _ur.urlopen("http://localhost:8181/health", timeout=2).read()
                print("  LLM жив")
            except Exception:
                print("  LLM мёртв — поднимаю…")
                try:
                    if start_llama_server():
                        # валидация: ждём health, а не «запущен»
                        import time as _t

                        for _ in range(15):
                            try:
                                _ur.urlopen(
                                    "http://localhost:8181/health", timeout=2
                                ).read()
                                print("  LLM поднят и здоров")
                                break
                            except Exception:
                                _t.sleep(2)
                        else:
                            print("  [new] LLM не отвечает после 30с")
                    else:
                        print("  [new] LLM не поднялся")
                except Exception as llm_e:  # noqa: ENIGMA001
                    print(f"  [new] LLM-подъём: {llm_e}")
            continue
        if low == "день":
            cp.status()
            continue
        if low.startswith("wait"):
            try:
                n = min(int(low.split()[1]), 20)
            except (IndexError, ValueError):
                n = 10
            await cp.wait(n)
            continue
        if low.startswith("mem"):
            arg = line.split(maxsplit=1)
            ids = [NAME_MAP.get(arg[1].lower())] if len(arg) > 1 and arg[1].lower() in NAME_MAP else list(KEY_NPCS)
            cp.xray([i for i in ids if i])
            continue
        if low.startswith("портрет"):
            arg = line.split(maxsplit=1)
            npc = NAME_MAP.get(arg[1].lower()) if len(arg) > 1 else None
            if npc:
                cp.xray([npc])
            continue
        # обычный ход — с адресацией
        target, text = parse_target(line)
        cp.turn += 1
        await cp.act(text if text else line, target)


if __name__ == "__main__":
    asyncio.run(main())
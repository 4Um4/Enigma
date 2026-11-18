# backend\tests\sandbox\SUPERBOX\run_terminal_mvp.py
"""
Интерактивный терминальный клиент для тестирования MVP "Секреты таверны".
Запуск: python backend/tests/sandbox/SUPERBOX/run_terminal_mvp.py
"""

from __future__ import annotations

import asyncio
import atexit
import sys
from pathlib import Path

# Добавляем backend/app в path (вычисляем путь относительно текущего файла)
_BACKEND_DIR = Path(__file__).resolve().parents[3]  # Поднимаемся на 4 уровня вверх до backend/
_ROOT_DIR = _BACKEND_DIR.parent
APP_DIR = _BACKEND_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

# Автоматический запуск/остановка LLM для MVP через Host broker SDK
#
# Этап 4.1.2: migrated to Host broker SDK. ensure_llm(label="superbox_mvp")
# acquire lease через Host broker :8182; release выполняется SDK через
# module-level atexit handler. run_terminal_mvp больше НЕ владеет
# llama-server lifecycle (принцип Мастера: идентификация ≠
# владение). atexit.register(release_lease) уже внутри SDK (client.py:215,
# module-level) — НЕ дублируем. Host/llama-server переживают shutdown runner.
try:
    from app.services.llm.runtime.client import ensure_llm

    ensure_llm(label="superbox_mvp")
except Exception as _e:
    # Любой отказ (CI без Models LLM/, таймаут Host startup, OSError, RuntimeError)
    # — MVP продолжает работу без LLM; нарратив будет недоступен.
    print(f"⚠️ Внимание: LLM недоступна ({_e}). MVP продолжает работу без LLM.")

from app.services.llm.provider_manager import initialize_model_pool

initialize_model_pool()

# ── ISOLATION (прецедент DriftLab S129): изолируем ТОЛЬКО saves_dir
# (runtime-мутации), data_dir остаётся реальным статическим. Open_road
# не загрязняется экспериментальным вводом.
import shutil
import tempfile

from app.core.config import settings as _settings
from app.models.schemas import ChatTurnRequest, PlayerAction
from app.services.game_loop_builder import build_game_loop

_TEMP_DIR = tempfile.mkdtemp(prefix="understanding_probe_")
_SAVES_DST = Path(_TEMP_DIR) / "saves"
_saves_src = Path(_settings.saves_dir)
if _saves_src.exists():
    shutil.copytree(_saves_src, _SAVES_DST, dirs_exist_ok=True)
_settings.saves_dir = str(_SAVES_DST)
atexit.register(lambda: shutil.rmtree(_TEMP_DIR, ignore_errors=True))

CAMPAIGN_ID = "Open_road"
LOCATION_ID = "tavern"
WORLD_ID = "default"
MAX_TURNS = 20

# SUPERBOX production-parity: player_spawn из tavern.json (S1).
# Прежний хардкод (6.5, 5.5) — тестовая позиция, далеко от NPC.
# tavern.json: player_spawn = (58.27, 20.20), NPCs в радиусе 5-12.
# Без этого DM validator отклоняет dialogue («NPC не видит игрока», dist 50+).
import json as _json

_TAVERN_PATH = _ROOT_DIR / "frontend" / "map_editor" / "campaigns" / CAMPAIGN_ID / "locations" / "tavern.json"
_PLAYER_SPAWN: tuple[float, float] = (6.5, 5.5)  # fallback
try:
    _tavern_data = _json.loads(_TAVERN_PATH.read_text(encoding="utf-8-sig"))
    _spawn = _tavern_data.get("player_spawn") or {}
    if _spawn.get("x") is not None and _spawn.get("y") is not None:
        _PLAYER_SPAWN = (float(_spawn["x"]), float(_spawn["y"]))
except (OSError, _json.JSONDecodeError) as _e:
    print(f"⚠️ player_spawn не загружен из tavern.json: {_e}. Fallback=(6.5, 5.5)")


async def main():
    print("🚀 Инициализация ядра симуляции ENIGMA...")
    # data_dir — реальный статический (S129-паритет), saves — temp-копия
    data_dir = _BACKEND_DIR.parent / "data"
    game_loop = build_game_loop(data_dir=str(data_dir))

    print(f"✅ Симуляция запущена. Кампания: {CAMPAIGN_ID}, Локация: {LOCATION_ID}.")
    print(f"[ISOLATION] saves_root={_SAVES_DST} (temp-копия) | original={_saves_src} НЕ ТРОНУТ")
    print("[ISOLATION] NOTE: позиция игрока берётся из копии сейва (если сохранена),")
    print("           а не из _current_player_pos по умолчанию — если удар 'уносит' за порог,")
    print("           это состояние копии, не деградация. Порог Y>=12.5 завершает сессию.")
    print("[ISOLATION] campaign=Open_road (копия) | teardown at exit")
    print("[CORPUS] Разведочные классы ввода: физическое / социальное / речевое / вопрос /")
    print("         утверждение / наблюдение / намерение / составное / двусмысленное.")
    print("Введи своё действие (или 'exit' для выхода). Предел: 20 ходов.\n")

    # UNDERSTANDING-трасса: предыдущий срез beliefs/journal (diff между ходами)
    _prev_beliefs: list = []
    _prev_journal_len: int = 0

    # S1: player_spawn из tavern.json (модуль-уровень _PLAYER_SPAWN).
    # Прежний хардкод (6.5, 5.5) — далеко от NPC, DM validator отклонял диалоги.
    _current_player_pos: tuple[float, float] = _PLAYER_SPAWN
    print(f"[SPAWN] player_position={_current_player_pos} (из tavern.json)")

    turn = 0
    while turn < MAX_TURNS:
        user_input = input(f"> [{turn + 1}/{MAX_TURNS}] ").strip()
        if user_input.lower() in ["exit", "quit", "выход"]:
            break
        if not user_input:
            continue  # пустой ввод не расходует ход
        turn += 1
        print(f"--- Ход {turn}/{MAX_TURNS} ---")

        # MVP WORKAROUND: Мгновенное перемещение к NPC для теста боя
        if "ПОДОЙТИ" in user_input.upper():
            # Мы не знаем позицию NPC до тех пор, пока тик не отработает,
            # поэтому сначала запустим тик с текущей позицией, а затем обновим её.
            pass

        # S5: player_name — production-parity. Прежний хардкод "ВВорг" —
        # не совпадает с avatar в saves (из лога: "имя не совпадает: None != ВВорг"
        # или "имя не совпадает: ВВорг != Dav12"). Используем стабильное
        # тестовое имя "Игрок" — avatar создаётся в new_game автоматически.
        action = PlayerAction(
            player_name="Игрок",  # стабильное тестовое имя
            action=user_input,
        )

        # Формируем запрос
        req = ChatTurnRequest(
            world_id=WORLD_ID,
            campaign_id=CAMPAIGN_ID,
            location=LOCATION_ID,
            actions=[action],
            player_position=_current_player_pos,  # Динамическая позиция игрока
        )

        try:
            # Выполняем тик
            response = await game_loop.run_turn(req)

            # S3: NPC speech отдельно от DM narrative.
            # npc_reactions содержит NPC_SPOKE entries (channel='dialogue'),
            # которые в production рендерятся как speech bubbles.
            # DM narrative (channel='narrative', speaker='Рассказчик') — отдельно.
            print("\n🎭 [DM]:", response.dm_response)

            # NPC speech bubbles — отображаем отдельно, как в production frontend
            if response.npc_reactions:
                print("\n💬 [NPC Реплики]:")
                for react in response.npc_reactions:
                    # react может быть dict или object — унифицируем
                    if hasattr(react, "model_dump"):
                        react = react.model_dump()
                    if isinstance(react, dict):
                        _spk = react.get("speaker_id") or react.get("speaker") or react.get("name") or "?"
                        _txt = react.get("text") or react.get("content") or react.get("line") or ""
                        _tgt = react.get("target_id") or ""
                        _ch = react.get("channel") or "dialogue"
                        if _txt:
                            _tgt_str = f" → {_tgt}" if _tgt and _tgt != "player" else ""
                            print(f"  [{_spk}{_tgt_str}] ({_ch}): {_txt}")
                        else:
                            print(f"  [{_spk}] (без текста — D1 regression?)")
                    else:
                        print(f"  - {react}")
            else:
                # S3 diagnostic: если NPC speech нет, но был PLAYER_SPOKE —
                # указываем, что NPC не ответил (диагност для ROOT FIX проверки)
                _ws = response.world_snapshot or {}
                _journal = _ws.get("dialog_journal") or []
                _has_player_spoke = any(
                    isinstance(e, dict) and e.get("channel") == "self"
                    for e in _journal
                )
                if _has_player_spoke:
                    print("\n  (NPC не ответил — PLAYER_SPOKE опубликован, NPC_SPOKE отсутствует)")

            # Проверяем координату выхода (Y >= 12.5)
            # В ChatTurnResponse координаты игрока могут лежать в world_snapshot или npc_positions
            # Проверяем оба варианта
            player_y = 0.0
            _p_pos = None
            if response.world_snapshot and response.world_snapshot.get("player_position"):
                _p_pos = response.world_snapshot["player_position"]
            elif response.npc_positions and response.npc_positions.get("player"):
                _p_pos = response.npc_positions["player"].get("local_position", {})

            # WorldSnapshotBuilder может возвращать кортеж (x, y) или словарь {"x":.., "y":..}
            if isinstance(_p_pos, (list, tuple)) and len(_p_pos) >= 2:
                player_y = float(_p_pos[1])
            elif isinstance(_p_pos, dict):
                player_y = float(_p_pos.get("y", 0.0))

            print(f"\n[DEBUG] Текущая Y координата игрока: {player_y}")

            # Обновляем позицию игрока для следующего хода
            if isinstance(_p_pos, (list, tuple)) and len(_p_pos) >= 2:
                _current_player_pos = (float(_p_pos[0]), float(_p_pos[1]))
            elif isinstance(_p_pos, dict):
                _current_player_pos = (float(_p_pos.get("x", 0.0)), float(_p_pos.get("y", 0.0)))

            # S4: MVP WORKAROUND — мгновенное перемещение к любому NPC по имени.
            # Прежний код поддерживал только "люся" (maid_lusya). Теперь: при
            # команде "подойти к <имя>" ищем NPC по подстроке имени в user_input
            # и телепортируемся рядом (offset 0.5 по X — в радиусе hearing 5.0).
            if "ПОДОЙТИ" in user_input.upper() or "ПОДОЙТИ" in user_input.lower():
                _snapshot = response.world_snapshot or {}
                _ws_npcs = _snapshot.get("npc_positions", {})

                # Маппинг русских имён → npc_id (canonical из tavern.json)
                _NAME_TO_NPC_ID = {
                    "люся": "maid_lusya",
                    "лус": "maid_lusya",
                    "торнин": "tavern_keeper_tornin",
                    "орм": "blacksmith_orm",
                    "горан": "merchant_goran",
                    "борко": "guard_borko",
                    "тень": "thief_shadow",
                }

                _input_lower = user_input.lower()
                _target_npc_id = None
                for _name_fragment, _npc_id in _NAME_TO_NPC_ID.items():
                    if _name_fragment in _input_lower:
                        _target_npc_id = _npc_id
                        break

                if _target_npc_id:
                    # Извлекаем позицию target NPC из snapshot
                    for _pid, _v in _ws_npcs.items():
                        if _pid != _target_npc_id:
                            continue
                        _npc_pos = getattr(_v, "local_position", None)
                        if _npc_pos is None and isinstance(_v, dict):
                            _npc_pos = _v.get("local_position")
                        elif hasattr(_v, "model_dump"):
                            _npc_pos = _v.model_dump().get("local_position")
                        if isinstance(_npc_pos, dict):
                            _nx = float(_npc_pos.get("x", 0.0)) + 0.5
                            _ny = float(_npc_pos.get("y", 0.0))
                            _current_player_pos = (_nx, _ny)
                            print(f"\n[TELEPORT] Игрок → {_target_npc_id} ({_current_player_pos})")
                        break
                    else:
                        print(f"\n[TELEPORT] NPC '{_target_npc_id}' не найден в snapshot")
                else:
                    print(f"\n[TELEPORT] Имя NPC не распознано в: '{user_input}'")
                    print("  Доступные: люся, торнин, орм, горан, борко, тень")

            # === [UNDERSTANDING] ТРАССА ПОНИМАНИЯ (главный артефакт зонда) ===
            # A=сказано | B=понято | C=сделано | D=рассказано (renderer, НЕ oracle).
            # Только фактически существующие поля; недоступное — NOT_VISIBLE.
            _ws = response.world_snapshot or {}
            _cur_beliefs = (_ws.get("player_beliefs") or []) + (_ws.get("npc_beliefs_about_player") or [])
            _cur_journal = _ws.get("dialog_journal") or []
            print("\n=== [UNDERSTANDING] ===")
            print(f"A (сказано): {user_input!r}")
            _pip = getattr(response, "player_intent_projection", "<NO_FIELD>")
            if isinstance(_pip, dict):
                if _pip:
                    print("B (понято):")
                    for _k in sorted(_pip.keys()):
                        print(f"  {_k}={_pip[_k]!r}")
                else:
                    print("B (понято):  {} (пустой резолв — аномалия)")
            elif _pip is None:
                print("B (понято):  NOT_VISIBLE (интен не резолвился — проекция None)")
            else:
                print("B (понято):  NOT_VISIBLE (поле не в схеме ответа — патч G1 не применён или кэш-фантом)")
            _spoke_entry = next(
                (e for e in reversed(_cur_journal) if isinstance(e, dict) and e.get("channel") == "self"), None
            )
            print("C (сделано):")
            print("  PLAYER_SPOKE:    NOT_VISIBLE из ответа (событие на шине, наружу не проецируется)")
            print(
                f"  journal delta:   {_prev_journal_len} -> {len(_cur_journal)}"
                f" (последняя: ch={_cur_journal[-1].get('channel') if _cur_journal else '?'},"
                f" event_id={'ЕСТЬ' if (_cur_journal and _cur_journal[-1].get('event_id')) else 'НЕТ'})"
            )
            print("  claims игрока:   NOT_IN_SNAPSHOT (ожидаемо — baseline разрыва)")
            _delta = len(_cur_beliefs) - len(_prev_beliefs)
            print(f"  beliefs:         {_prev_beliefs.__len__()} -> {len(_cur_beliefs)} (delta={_delta})")
            if _delta > 0:
                for _nb in _cur_beliefs[-_delta:]:
                    _np = _nb.get("proposition", {}) if isinstance(_nb, dict) else {}
                    print(
                        f"    + [{_nb.get('agent_id', '?')}] {(_np.get('predicate', '?'))}({_np.get('subject_id', '?')}->{_np.get('object_id', '?')}) conf={_nb.get('confidence')}"
                    )
            print(f"D (DM):          {(response.dm_response or '')[:200]!r}  <- renderer, НЕ oracle")
            print("=== END ===\n")
            _prev_beliefs = _cur_beliefs
            _prev_journal_len = len(_cur_journal)

            # === POST-TICK INVARIANT AUDIT ===
            # Ловим тихие деградации, которые ломают каузальность, но не крашат игру
            _audit_errors = []
            _audit_logs = getattr(response, "logs", "") or ""  # поля нет в схеме — честно пусто

            # 1. Проверка применения урона (если был бой)
            _audit_action = (_pip if isinstance(_pip, dict) else {}).get("action", "")
            if _audit_action == "ATTACK":
                # Ищем NPC в npc_positions (ChatTurnResponse не содержит npc_states напрямую)
                _npc_pos = response.npc_positions or {}
                _any_pain = False
                for _pid, _data in _npc_pos.items():
                    if _pid == "player":
                        continue
                    # G3-урок: snapshot-проекция может не нести body_state —
                    # боль проверяем в полной структуре, если она доезжает
                    if isinstance(_data, dict):
                        _body = _data.get("body_state") or {}
                        if not _body and hasattr(_data, "body_state"):
                            _body = getattr(_data, "body_state") or {}
                        # Контракт body_state: pain 0-100, shock_impulse (не "shock")
                        if (
                            float(_body.get("pain", 0.0) or 0) > 0.0
                            or float(_body.get("shock_impulse", 0.0) or 0) > 0.0
                        ):
                            _any_pain = True
                            break
                if not _any_pain:
                    _audit_errors.append(
                        "INV-COMBAT: pain не виден в npc_positions-проекции "
                        "(VITAL_EVAL в логе подтверждает/опровергает урон; "
                        "проекция body_state в snapshot — известный gap зонда)"
                    )
                    # Проверка на галлюцинацию LLM: DM описывает удар, но физика его отклонила
                    _dm_text = (response.dm_response or "").lower()
                    _hallucination_words = ["вздрагивает", "боль", "удар", "щека", "кровь", "стонет", "падает"]
                    if any(word in _dm_text for word in _hallucination_words):
                        _audit_errors.append(
                            "INV-DM-HALLUCINATION: DM описывает физический контакт, но ImpactEngine отклонил удар (дистанция/физика). DM игнорирует правила симуляции."
                        )

            # 2-3. INV-MEMORY/INV-WILL: поле logs отсутствует в ChatTurnResponse
            # (схема: dm_response/npc_reactions/world_changes/traces/...) —
            # проверка переведена в честную NOT_VISIBLE (не молчаливый пропуск).
            if not _audit_logs:
                print("  [AUDIT] INV-MEMORY/INV-WILL: NOT_VISIBLE (logs вне схемы ответа)")

            if _audit_errors:
                print("\n🚨 [AUDIT FAIL] Обнаружены разрывы каузальной цепи:")
                for err in _audit_errors:
                    print(f"  - {err}")
                print("-" * 50)

            # S2: порог Y >= 12.5 удалён — player_spawn (58.27, 20.20) уже выше
            # порога. Прежний testbed constraint — устаревший сценарий "old tavern";
            # теперь SUPERBOX эмулирует production player position, где Y может быть
            # любым. Порог убивал сессию на первом же тике.

        except Exception as e:
            print(f"\n[ERROR] Ошибка во время тика: {e}")
            import traceback

            traceback.print_exc()
            break

    print("\n======================================================")
    print("📊 СЕССИЯ ЗАВЕРШЕНА")
    print("======================================================")
    # Здесь можно добавить вывод метрик из game_loop, если они доступны
    print("Для подробного отчета открой файл reports/LAST_SESSION.md (если был сгенерирован).")


if __name__ == "__main__":
    asyncio.run(main())

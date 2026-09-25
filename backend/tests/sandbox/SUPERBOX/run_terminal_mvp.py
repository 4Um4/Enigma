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
_BACKEND_DIR = Path(__file__).resolve().parents[3] # Поднимаемся на 4 уровня вверх до backend/
_ROOT_DIR = _BACKEND_DIR.parent
APP_DIR = _BACKEND_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

# Автоматический запуск/остановка LLM для MVP
try:
    from scripts.llm_server_manager import kill_llama_server, start_llama_server
    _llm_ok = start_llama_server()
    if not _llm_ok:
        print("⚠️ Внимание: LLM не запущена. Нарратив будет недоступен.")
    atexit.register(kill_llama_server)
except ModuleNotFoundError as e:
    print(f"⚠️ Внимание: Модуль LLM-сервера не найден ({e}). MVP продолжает работу без LLM.")

from app.services.llm.provider_manager import initialize_model_pool

initialize_model_pool()

from app.models.schemas import ChatTurnRequest, PlayerAction
from app.services.game_loop_builder import build_game_loop

# ── ISOLATION (прецедент DriftLab S129): изолируем ТОЛЬКО saves_dir
# (runtime-мутации), data_dir остаётся реальным статическим. Open_road
# не загрязняется экспериментальным вводом.
import shutil
import tempfile
from app.core.config import settings as _settings

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

    _current_player_pos: tuple[float, float] = (6.5, 5.5) # x, y

    turn = 0
    while turn < MAX_TURNS:
        user_input = input(f"> [{turn+1}/{MAX_TURNS}] ").strip()
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

        # Создаём действие игрока
        action = PlayerAction(
            player_name="ВВорг", # Имя игрока
            action=user_input
        )

        # Формируем запрос
        req = ChatTurnRequest(
            world_id=WORLD_ID,
            campaign_id=CAMPAIGN_ID,
            location=LOCATION_ID,
            actions=[action],
            player_position=_current_player_pos # Динамическая позиция игрока
        )

        try:
            # Выполняем тик
            response = await game_loop.run_turn(req)
            
            # Выводим ответ DM
            print("\n🎭 [DM]:", response.dm_response)
            
            if response.npc_reactions:
                print("\n💬 [NPC Реакции]:")
                for react in response.npc_reactions:
                    print(f"  - {react}")

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

            # MVP WORKAROUND: Мгновенное перемещение к NPC для теста боя
            if "ПОДОЙТИ" in user_input.upper():
                _snapshot = response.world_snapshot or {}
                _ws_npcs = _snapshot.get("npc_positions", {})
                # Конвертируем DTO в dict для безопасного чтения
                _npc_positions = {}
                for _k, _v in _ws_npcs.items():
                    if hasattr(_v, "model_dump"): _v = _v.model_dump()
                    elif hasattr(_v, "__dict__"): _v = _v.__dict__
                    _npc_positions[_k] = _v
                
                for _pid, _v in _ws_npcs.items():
                    if _pid == "player":
                        continue
                    # Универсально извлекаем local_position из DTO, dict или dataclass
                    _npc_pos = getattr(_v, "local_position", None)
                    if _npc_pos is None and isinstance(_v, dict):
                        _npc_pos = _v.get("local_position")
                    elif hasattr(_v, "model_dump"):
                        _npc_pos = _v.model_dump().get("local_position")
                    
                    if isinstance(_npc_pos, dict):
                        # MVP FIX: проверяем по ID, так как NPCPositionDTO не хранит name
                        if "люся" in user_input.lower() and _pid == "maid_lusya":
                            _nx = float(_npc_pos.get("x", 0.0)) + 0.5
                            _ny = float(_npc_pos.get("y", 0.0))
                            _current_player_pos = (_nx, _ny)
                            print(f"\n[DEBUG] MVP Workaround: Игрок телепортирован к {_pid} ({_current_player_pos})")
                            break

            # === [UNDERSTANDING] ТРАССА ПОНИМАНИЯ (главный артефакт зонда) ===
            # A=сказано | B=понято | C=сделано | D=рассказано (renderer, НЕ oracle).
            # Только фактически существующие поля; недоступное — NOT_VISIBLE.
            _ws = response.world_snapshot or {}
            _cur_beliefs = (_ws.get("player_beliefs") or []) + (
                _ws.get("npc_beliefs_about_player") or []
            )
            _cur_journal = _ws.get("dialog_journal") or []
            print("\n=== [UNDERSTANDING] ===")
            print(f"A (сказано): {user_input!r}")
            print("B (понято):  intent/semantic/target — NOT_VISIBLE из run_turn-ответа")
            print("             (эти объекты не покидают turn-pipeline; см. карту разрывов)")
            _spoke_entry = next((e for e in reversed(_cur_journal)
                                 if isinstance(e, dict) and e.get("channel") == "self"), None)
            print(f"C (сделано):")
            print(f"  PLAYER_SPOKE:    NOT_VISIBLE из ответа (событие на шине, наружу не проецируется)")
            print(f"  journal delta:   {_prev_journal_len} -> {len(_cur_journal)}"
                  f" (последняя: ch={_cur_journal[-1].get('channel') if _cur_journal else '?'},"
                  f" event_id={'ЕСТЬ' if (_cur_journal and _cur_journal[-1].get('event_id')) else 'НЕТ'})")
            print(f"  claims игрока:   NOT_IN_SNAPSHOT (ожидаемо — baseline разрыва)")
            _delta = len(_cur_beliefs) - len(_prev_beliefs)
            print(f"  beliefs:         {_prev_beliefs.__len__()} -> {len(_cur_beliefs)} (delta={_delta})")
            if _delta > 0:
                for _nb in _cur_beliefs[-_delta:]:
                    _np = _nb.get("proposition", {}) if isinstance(_nb, dict) else {}
                    print(f"    + [{_nb.get('agent_id', '?')}] {(_np.get('predicate', '?'))}({_np.get('subject_id', '?')}->{_np.get('object_id', '?')}) conf={_nb.get('confidence')}")
            print(f"D (DM):          {(response.dm_response or '')[:200]!r}  <- renderer, НЕ oracle")
            print("=== END ===\n")
            _prev_beliefs = _cur_beliefs
            _prev_journal_len = len(_cur_journal)

            # === POST-TICK INVARIANT AUDIT ===
            # Ловим тихие деградации, которые ломают каузальность, но не крашат игру
            _audit_errors = []
            _audit_logs = getattr(response, "logs", "") or ""  # поля нет в схеме — честно пусто
            
            # 1. Проверка применения урона (если был бой)
            if "ATTACK" in user_input.upper() or "УДАР" in user_input.upper():
                # Ищем NPC в npc_positions (ChatTurnResponse не содержит npc_states напрямую)
                _npc_pos = response.npc_positions or {}
                _any_pain = False
                for _pid, _data in _npc_pos.items():
                    if _pid == "player": continue
                    # G3-урок: snapshot-проекция может не нести body_state —
                    # боль проверяем в полной структуре, если она доезжает
                    if isinstance(_data, dict):
                        _body = _data.get("body_state") or {}
                        if not _body and hasattr(_data, "body_state"):
                            _body = getattr(_data, "body_state") or {}
                        # Контракт body_state: pain 0-100, shock_impulse (не "shock")
                        if float(_body.get("pain", 0.0) or 0) > 0.0 or float(
                            _body.get("shock_impulse", 0.0) or 0
                        ) > 0.0:
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
                        _audit_errors.append("INV-DM-HALLUCINATION: DM описывает физический контакт, но ImpactEngine отклонил удар (дистанция/физика). DM игнорирует правила симуляции.")

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

            if player_y >= 12.5:
                print("\n🚪 Игрок пересёк порог таверны (Y >= 12.5)!")
                print("Генерация финального отчета...")
                # Симулируем вызов CausalObserver для генерации LAST_SESSION.md
                # (В реальности он вызывается при завершении игры)
                break

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
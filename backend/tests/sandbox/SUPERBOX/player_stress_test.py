"""
ENIGMA Player Stress Test — Headless тест player path (Tab+Enter).

Выводит ТОЛЬКО краткий отчёт: статус каждого действия и список ошибок.
Запуск:
  cd backend
  python -m tests.sandbox.SUPERBOX.run player_stress
"""

import asyncio
import io
import logging
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

# Добавляем backend/ в path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.core.config import settings
from app.models.schemas import ChatTurnRequest, ModelProvider, ModelSelection, PlayerAction
from app.services.game_loop_builder import build_game_loop

# ─── Тестовые сценарии ────────────────────────────────────────────────
TEST_ACTIONS = [
    "осмотреться",
    "поговорить с трактирщиком",
    "атаковать трактирщика",
    "подойти к столу",
    "взять кружку",
    "открыть дверь",
    "просто стоять",
    "покинуть таверну",
]


def setup_logging_capture():
    """Перехватывает логи в буфер, чтобы не засорять консоль."""
    log_capture_string = io.StringIO()
    ch = logging.StreamHandler(log_capture_string)
    ch.setLevel(logging.ERROR)  # Ловим только ERROR и выше
    formatter = logging.Formatter("%(message)s")
    ch.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.addHandler(ch)
    # Снижаем уровень логирования uvicorn/asyncio
    logging.getLogger("uvicorn").setLevel(logging.CRITICAL)
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)
    return log_capture_string


async def run_player_stress_test():
    print("\n" + "=" * 60)
    print("PLAYER STRESS TEST — Headless Player Path")
    print("=" * 60)

    log_buffer = setup_logging_capture()

    print("\n[SETUP] Инициализация GameLoop...")
    temp_dir = tempfile.mkdtemp(prefix="player_stress_")
    temp_path = Path(temp_dir)

    try:
        _project_root = Path(__file__).resolve().parents[3]
        campaign_id = "Open_road"

        # Копирование данных кампании
        data_src = _project_root / "frontend" / "map_editor" / "campaigns" / campaign_id
        data_dst = temp_path / "data" / campaign_id
        if data_src.exists():
            data_dst.mkdir(parents=True, exist_ok=True)
            for loc_dir in data_src.iterdir():
                if loc_dir.is_dir():
                    dst_loc = data_dst / "locations" / loc_dir.name
                    dst_loc.mkdir(parents=True, exist_ok=True)
                    for f in loc_dir.iterdir():
                        if f.is_file():
                            shutil.copy2(f, dst_loc / f.name)

        npc_src = _project_root / "backend" / "data" / "campaigns" / campaign_id
        npc_dst = temp_path / "campaigns" / campaign_id
        if npc_src.exists():
            npc_dst.mkdir(parents=True, exist_ok=True)
            for f in npc_src.iterdir():
                if f.is_file():
                    shutil.copy2(f, npc_dst / f.name)

        saves_src = _project_root / "saves"
        saves_dst = temp_path / "saves"
        if saves_src.exists():
            shutil.copytree(saves_src, saves_dst, dirs_exist_ok=True)

        settings.saves_dir = str(saves_dst)
        game_loop = build_game_loop(data_dir=temp_path / "data")
        print("[SETUP] GameLoop успешно собран.\n")

        player_name = "Tester"
        location = "tavern_silver_wolf"
        error_stats = {}

        print(f"[RUN] Прогон {len(TEST_ACTIONS)} действий...\n" + "-" * 60)

        for i, action_text in enumerate(TEST_ACTIONS, 1):
            req = ChatTurnRequest(
                world_id="manual",
                campaign_id=campaign_id,
                location=location,
                model=ModelSelection(
                    provider=ModelProvider.llama_cpp, model_name="fallback", endpoint=settings.llama_cpp_server_url
                ),
                actions=[PlayerAction(player_name=player_name, action=action_text)],
                player_position=(0.0, 0.0),
            )

            log_buffer.truncate(0)
            log_buffer.seek(0)

            try:
                result = await game_loop.run_turn(req)

                # Анализируем логи на предмет скрытых ошибок
                log_content = log_buffer.getvalue()
                errors_in_tick = []
                for line in log_content.split("\n"):
                    if "ERROR" in line or "Traceback" in line or "NameError" in line or "AttributeError" in line:
                        errors_in_tick.append(line.strip())

                if result is None:
                    status = "[FAIL] run_turn=None"
                    error_stats["NoneResponse"] = error_stats.get("NoneResponse", 0) + 1
                elif not hasattr(result, "dm_response"):
                    status = "[FAIL] InvalidObject"
                    error_stats["InvalidObject"] = error_stats.get("InvalidObject", 0) + 1
                elif errors_in_tick:
                    status = f"[WARN] Скрытые ошибки ({len(errors_in_tick)})"
                    for err in errors_in_tick:
                        # Группируем по типу ошибки
                        if "NameError" in err:
                            error_stats["NameError"] = error_stats.get("NameError", 0) + 1
                        elif "AttributeError" in err:
                            error_stats["AttributeError"] = error_stats.get("AttributeError", 0) + 1
                        else:
                            error_stats["OtherError"] = error_stats.get("OtherError", 0) + 1
                elif result.dm_response == "Ничего не произошло.":
                    status = "[WARN] Fallback (LLM off)"
                else:
                    status = "[OK]"

                print(f"{i}. {action_text:<25} -> {status}")
                if errors_in_tick:
                    print(f"   └─ {errors_in_tick[0]}")  # Выводим первую ошибку для контекста

            except Exception as e:
                print(f"{i}. {action_text:<25} -> [CRASH] {type(e).__name__}")
                error_stats[type(e).__name__] = error_stats.get(type(e).__name__, 0) + 1

        # Итоги
        print("\n" + "=" * 60)
        print("SUMMARY:")
        if not error_stats:
            print("🟢 Критических ошибок не обнаружено.")
        else:
            print("🔴 Найдены ошибки:")
            for err_type, count in error_stats.items():
                print(f"   - {err_type}: {count} раз")
        print("=" * 60)

        return not error_stats

    except Exception as e:
        print(f"\n[SETUP CRASH] {e}")
        traceback.print_exc()
        return False
    finally:
        if "temp_dir" in locals() and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    try:
        success = asyncio.run(run_player_stress_test())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        sys.exit(130)

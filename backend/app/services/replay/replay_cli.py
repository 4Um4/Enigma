# backend/app/services/replay/replay_cli.py
"""
path: /project/backend/app/services/replay/replay_cli.py
Назначение: CLI для запуска replay сессий из терминала.
Зависимости: app.services.replay.replay_store, app.services.replay.replay_player
Основные сущности: CLI entry point
"""
import argparse
import sys
import os
import tempfile
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="ENIGMA Replay CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    play_parser = subparsers.add_parser("play", help="Воспроизвести записанную сессию")
    play_parser.add_argument("--session", required=True, help="ID сессии для воспроизведения")
    play_parser.add_argument("--start", type=int, default=0, help="Стартовый тик")
    play_parser.add_argument("--end", type=int, default=None, help="Конечный тик (необязательно)")
    play_parser.add_argument("--max-drift", type=int, default=0, help="Максимально допустимый дрейф")

    args = parser.parse_args()

    # Добавляем корень проекта в sys.path для импортов
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    os.chdir(Path(__file__).resolve().parents[4])

    if args.command == "play":
        from app.core.config import settings
        from app.services.game_loop_builder import build_game_loop
        from app.services.replay.replay_store import ReplayStore
        from app.services.replay.replay_player import ReplayPlayer
        
        db_path = f"backend/data/replay/{args.session}.db"
        if not os.path.exists(db_path):
            print(f"[ERROR] Replay DB not found: {db_path}")
            sys.exit(1)
            
        store = ReplayStore(db_path)
        
        # Изолируем saves в темп, чтобы не портить реальные сохранения
        temp_saves = tempfile.mkdtemp(prefix="replay_saves_")
        settings.saves_dir = temp_saves
        data_dir = Path(settings.data_dir)
        
        game_loop = build_game_loop(data_dir)
        
        # Дефолтные параметры кампании (как в IPT)
        campaign_id = "Open_road"
        location_id = "tavern"
        
        player = ReplayPlayer(store, game_loop, args.session, campaign_id, location_id)
        
        print(f"[CLI] Starting replay for session {args.session} (tick {args.start} to {args.end or 'END'})")
        report = player.play(start_tick=args.start, end_tick=args.end, max_drift=args.max_drift)
        
        print("\n--- REPLAY REPORT ---")
        for k, v in report.items():
            print(f"{k}: {v}")
        print("---------------------")
        
        if report["status"] == "SUCCESS":
            sys.exit(0)
        else:
            sys.exit(1)

if __name__ == "__main__":
    main()
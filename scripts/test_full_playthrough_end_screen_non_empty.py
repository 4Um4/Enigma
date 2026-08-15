"""
path: scripts/test_full_playthrough_end_screen_non_empty.py
Назначение: E2E Canary (Уровень 2).
            Прогоняет симуляцию (180 тиков ~ 30 мин) и проверяет, что End-Screen не пустой.
            Инжектирует один секрет, чтобы симулировать прогресс игрока.
Запуск: python scripts/test_full_playthrough_end_screen_non_empty.py
"""
import sys
import tempfile
from pathlib import Path

# Пропатчим sys.path, чтобы из scripts/ запускать без cd
_BACKEND = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(_BACKEND))
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from app.services.game_loop_builder import build_game_loop
from app.core.config import settings

def run_canary():
    print("[CANARY] Запуск E2E Canary (Уровень 2)...")
    
    # Изолируем saves в темп, чтобы не портить реальные сохранения
    temp_saves = tempfile.mkdtemp(prefix="canary_saves_")
    settings.saves_dir = temp_saves
    
    # Указываем путь к данным кампании
    data_dir = _ROOT / "data"
    if not data_dir.exists():
        print(f"❌ [CANARY] Data directory not found: {data_dir}")
        return 1
        
    try:
        print("[CANARY] Инициализация GameLoop...")
        game_loop = build_game_loop(str(data_dir))
        campaign_id = "Open_road"
        
        # Явная инициализация MVP-контроллера (так как мы минуем start_new_game)
        mvp_ctrl = getattr(game_loop, "mvp_controller", None)
        if not mvp_ctrl:
            print("❌ [CANARY] MvpTavernController (mvp_controller) не найден в GameLoop.")
            return 1
            
        try:
            mvp_ctrl.init_campaign(campaign_id)
            print(f"[CANARY] MVP controller initialized for '{campaign_id}'")
        except Exception as e:
            print(f"❌ [CANARY] MVP controller init failed: {e}")
            return 1

        # Прогоняем симуляцию (180 тиков = 30 минут)
        print(f"[CANARY] Прогон 180 тиков для кампании '{campaign_id}'...")
        for i in range(180):
            game_loop.idle_tick(campaign_id)
            if (i + 1) % 30 == 0:
                print(f"  Тик {i + 1}/180 завершён.")
                
        print("[CANARY] Симуляция завершена. Проверка End-Screen...")
        
        # Инжектируем один открытый секрет, чтобы гарантировать непустой End-Screen
        if mvp_ctrl.truth_state and mvp_ctrl.truth_state.secrets:
            first_secret_id = list(mvp_ctrl.truth_state.secrets.keys())[0]
            mvp_ctrl.truth_state.discovered_secrets.add(first_secret_id)
            print(f"[CANARY] Инжектирован секрет: {first_secret_id}")
        else:
            print("❌ [CANARY] TruthState пуст или не загружен.")
            return 1
            
        # Строим End-Screen
        end_screen = mvp_ctrl.build_end_screen()
        if not end_screen:
            print("❌ [CANARY] EndScreenData пуст (None).")
            os._exit(1)
            
        # Проверяем, что End-Screen содержит данные
        has_eval = end_screen.evaluation is not None
        has_fates = len(end_screen.npc_fates) > 0
        has_contras = len(end_screen.contradictions) > 0
        
        print("\n" + "="*50)
        print("📊 ENIGMA END-SCREEN REPORT")
        print("="*50)
        
        # 1. Evaluation
        ev = end_screen.evaluation
        print("\n🏆 EVALUATION:")
        if ev:
            print(f"  Score: {getattr(ev, 'score', 'N/A')}")
            print(f"  Verdict: {getattr(ev, 'verdict', 'N/A')}")
        else:
            print("  No evaluation data.")

        # 2. NPC Fates
        print("\n🎭 NPC FATES:")
        if end_screen.npc_fates:
            for fate in end_screen.npc_fates:
                lw_text = fate.last_word.text if fate.last_word else "No last words."
                print(f"  - {fate.npc_id}: {fate.fate_outcome} | Last Words: \"{lw_text}\"")
        else:
            print("  No fates resolved.")

        # 3. Contradictions
        print("\n⚔️ CONTRADICTIONS:")
        if end_screen.contradictions:
            for contra in end_screen.contradictions:
                npc_id = getattr(contra, 'npc_id', 'Unknown')
                text = getattr(contra, 'text', str(contra))
                print(f"  - {npc_id}: {text}")
        else:
            print("  No contradictions detected.")

        # 4. Relationships (Player <-> NPC & NPC <-> NPC)
        rel_store = getattr(game_loop.memory_manager, "_relationships", None)
        if rel_store:
            all_rels = rel_store.get_all(campaign_id)
            print("\n🤝 RELATIONSHIPS (with Player):")
            player_rels_found = False
            for src, targets in all_rels.items():
                for tgt, vals in targets.items():
                    # Выводим только отношения с участием игрока, чтобы не засорять вывод
                    if src == "player" or tgt == "player":
                        player_rels_found = True
                        trust = vals.get("trust", 0)
                        fear = vals.get("fear", 0)
                        print(f"  {src} ➔ {tgt}: Trust={trust}, Fear={fear}")
            if not player_rels_found:
                print("  No player relationships tracked.")
        else:
            print("  RelationshipStore not available.")
            
        print("="*50 + "\n")
        
        import os
        if has_eval or has_fates or has_contras:
            print("✅ [CANARY] End-Screen не пуст. MVP-пайплайн жив.")
            os._exit(0)
        else:
            print("❌ [CANARY] End-Screen пуст. MVP-пайплайн сломан.")
            os._exit(1)
            
    except Exception as e:
        import traceback
        print(f"❌ [CANARY] Краш во время прогона: {e}")
        traceback.print_exc()
        os._exit(1)

if __name__ == "__main__":
    sys.exit(run_canary())
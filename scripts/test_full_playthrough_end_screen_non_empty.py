"""
path: scripts/test_full_playthrough_end_screen_non_empty.py
Назначение: E2E Canary (Уровень 2).
            Прогоняет симуляцию (180 тиков ~ 30 мин) и проверяет, что End-Screen не пустой.
            Инжектирует один секрет и тестовые отношения, чтобы симулировать прогресс игрока.
            Переводит сухие метрики в живой язык (EndScreenNarrator).
Запуск: python scripts/test_full_playthrough_end_screen_non_empty.py
"""
import os
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

# 8.1 FIX: Канарейка использует production EndScreenNarrator, чтобы проверить живой текст.
from app.services.social.end_screen_narrator import EndScreenNarrator


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

        # 8.1 FIX: Инъекции отношений удалены. 
        # SocialSubscriber теперь имеет детерминированный fallback для NPC_SPOKE.
        rel_store = getattr(game_loop.memory_manager, "_relationships", None)
          
        # Строим End-Screen
        end_screen = mvp_ctrl.build_end_screen()
        if not end_screen:
            print("❌ [CANARY] EndScreenData пуст (None).")
            os._exit(1)
            
        # Проверяем, что End-Screen содержит данные
        has_eval = end_screen.evaluation is not None
        has_fates = len(end_screen.npc_fates) > 0
        has_contras = len(end_screen.contradictions) > 0
        
        narrator = EndScreenNarrator()

        print("\n" + "="*60)
        print("📜 ИТОГОВАЯ ХРОНИКА СЕССИИ (END-SCREEN)")
        print("="*60)
        
        # 1. Evaluation (Вердикт)
        ev = end_screen.evaluation
        print("\n🏆 ИТОГ:")
        if ev:
            score = getattr(ev, 'score', 0)
            verdict_text = narrator.narrate_verdict(score)
            print(f"  Очки: {score}/100")
            print(f"  {verdict_text}")
        else:
            print("  История не оценена.")

        # 2. Discovered Secrets
        print("\n🕵️ РАСКРЫТЫЕ ТАЙНЫ:")
        discovered = getattr(mvp_ctrl.truth_state, "discovered_secrets", set())
        if discovered:
            for sec_id in discovered:
                sec = mvp_ctrl.truth_state.secrets.get(sec_id)
                print(f"  - {sec.canonical_truth if sec else 'Неизвестная тайна'}")
        else:
            print("  Вам не удалось раскрыть ни одной тайны.")

        # 3. NPC Fates (Судьбы)
        print("\n🎭 СУДЬБЫ ПЕРСОНАЖЕЙ:")
        fate_states = mvp_ctrl.fate_tracker.get_all_states()
        if fate_states:
            for fs in fate_states:
                fate_text = narrator.narrate_fate(fs.npc_id, fs)
                print(f"  - {fate_text}")
        else:
            print("  Судьбы персонажей не отслеживались.")

        # 4. Contradictions
        print("\n⚔️ ПРОТИВОРЕЧИЯ И СЛЕДСТВИЯ:")
        if end_screen.contradictions:
            for contra in end_screen.contradictions:
                npc_id = getattr(contra, 'npc_id', 'Неизвестно')
                text = getattr(contra, 'text', str(contra))
                print(f"  - {npc_id}: {text}")
        else:
            print("  Явных противоречий в действиях не выявлено.")

        # 5. Relationships (Graph)
        if rel_store:
            all_rels = rel_store.get_all(campaign_id)
            print("\n🤝 ПЛЕТЕННЫЕ СУДЬБЫ (Отношения):")
            if not all_rels:
                print("  Связи между персонажами не сформировались.")
            else:
                player_rels = []
                npc_rels = []
                for key, vals in all_rels.items():
                    if "→" not in key: continue
                    src, tgt = key.split("→", 1)
                    trust = vals.get("trust", 0.0)
                    fear = vals.get("fear", 0.0)
                    rel_text = narrator.narrate_relationship(src, tgt, trust, fear)
                    
                    if src == "player" or tgt == "player":
                        player_rels.append(rel_text)
                    else:
                        npc_rels.append(rel_text)
                
                print("  [Отношения с Игроком]:")
                if player_rels:
                    for l in player_rels: print(f"    - {l}")
                else:
                    print("    Никто не запомнил Игрока.")
                    
                print("  [Связи между NPC]:")
                if npc_rels:
                    for l in npc_rels: print(f"    - {l}")
                else:
                    print("    Между NPC не возникло значимых связей.")
        else:
            print("  Хранилище отношений недоступно.")
            
        print("\n" + "="*60 + "\n")
        
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
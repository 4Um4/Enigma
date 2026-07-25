# scripts/fix_debug_logs.py
"""
Удаляет forensic spam (traceback.format_stack) и переводит print() в logger.debug()
в scene_state_manager.py (S134.2: Diagnostic Log Hygiene).
"""

import os
from pathlib import Path


def main():
    file_path = Path("backend/app/services/scene_state_manager.py")
    if not file_path.exists():
        print(f"❌ Файл не найден: {file_path}")
        return

    content = file_path.read_text(encoding="utf-8")
    original_content = content

    # 1. Удаление forensic stack-trace
    old_block_1 = """        if self._persistence:
            try:
                _recog = scene_state.get("player_recognition", {})
                import traceback
                _stack = traceback.format_stack(limit=5)
                print(f"[DEBUG_SAVE] campaign={campaign_id} recog_keys={list(_recog.keys())} stack={_stack}")
            except Exception as e:
                print(f"[DEBUG_SAVE] error: {e}")
            self._persistence.save_scene(campaign_id, scene_state)"""
    new_block_1 = """        if self._persistence:
            self._persistence.save_scene(campaign_id, scene_state)"""
    
    if old_block_1 in content:
        content = content.replace(old_block_1, new_block_1)
        print("✅ Патч 1 (Удаление forensic stack-trace) применён.")
    else:
        print("⚠️ Патч 1 не найден (возможно, уже применён).")

    # 2. Замена [DEBUG_LOCK]
    old_block_2 = """                print(f"[DEBUG_LOCK] campaign={campaign_id} recog_keys={list(_recog.keys())}")
            except Exception as e:
                print(f"[DEBUG_LOCK] error: {e}")"""
    new_block_2 = """                logger.debug(f"[LOCK] campaign={campaign_id} recog_keys={list(_recog.keys())}")
            except Exception as e:
                logger.warning(f"[LOCK] error reading recog_keys: {e}")"""
    
    if old_block_2 in content:
        content = content.replace(old_block_2, new_block_2)
        print("✅ Патч 2 ([DEBUG_LOCK]) применён.")
    else:
        print("⚠️ Патч 2 не найден.")

    # 3. Замена [DEBUG_COMMIT]
    old_block_3 = """                print(f"[DEBUG_COMMIT] campaign={campaign_id} recog_keys={list(_recog.keys())}")
            except Exception as e:
                print(f"[DEBUG_COMMIT] error: {e}")"""
    new_block_3 = """                logger.debug(f"[COMMIT] campaign={campaign_id} recog_keys={list(_recog.keys())}")
            except Exception as e:
                logger.warning(f"[COMMIT] error reading recog_keys: {e}")"""
    
    if old_block_3 in content:
        content = content.replace(old_block_3, new_block_3)
        print("✅ Патч 3 ([DEBUG_COMMIT]) применён.")
    else:
        print("⚠️ Патч 3 не найден.")

    # 4. Замена первого [DEBUG_LOAD]
    old_block_4 = """                    print(f"[DEBUG_LOAD] campaign={campaign_id} recog_keys={list(_recog.keys())}")
                except Exception as e:
                    print(f"[DEBUG_LOAD] error: {e}")"""
    new_block_4 = """                    logger.debug(f"[LOAD] campaign={campaign_id} recog_keys={list(_recog.keys())}")
                except Exception as e:
                    logger.warning(f"[LOAD] error reading recog_keys: {e}")"""
    
    # Поскольку блоки [DEBUG_LOAD] идентичны, replace заменит все их (их два)
    if old_block_4 in content:
        content = content.replace(old_block_4, new_block_4)
        print("✅ Патч 4 и 5 ([DEBUG_LOAD]) применены.")
    else:
        print("⚠️ Патч 4/5 не найден.")

    if content != original_content:
        file_path.write_text(content, encoding="utf-8")
        print(f"\n🎉 Файл {file_path} успешно обновлён!")
    else:
        print("\n⚠️ Файл не был изменён (все патчи уже применены или структура кода отличается).")

if __name__ == "__main__":
    main()
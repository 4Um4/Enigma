import os
import re

def fix_silent_failures(filepath):
    if not os.path.exists(filepath):
        print(f"[SKIP] Файл не найден: {filepath}")
        return
        
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        content = f.read()
        
    # Ищем: <отступ>except <Исключение>:\n<отступ>pass <комментарий>
    pattern = re.compile(r'^(\s*except\s+)([^\n:]+)(:\s*\n\s*)pass(\s*(#.*)?)', re.MULTILINE)
    
    def replacer(m):
        prefix = m.group(1)
        exc_type = m.group(2).strip()
        middle = m.group(3)
        comment = m.group(4)
        
        if ' as ' not in exc_type:
            exc_type += " as e"
            log_str = 'logger.warning(f"[B5-FIX] silent failure suppressed: {e}")'
        else:
            var_name = exc_type.split(" as ")[-1]
            log_str = 'logger.warning(f"[B5-FIX] silent failure suppressed: {' + var_name + '}")'
            
        return prefix + exc_type + middle + log_str + comment
        
    new_content = pattern.sub(replacer, content)
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8-sig') as f:
            f.write(new_content)
        print(f"[OK] Fixed silent failures in {filepath}")

print("=== ТЗ-6 ШАГ 9 (B5): Устранение except: pass ===")

files_to_process = [
    "backend/app/main.py",
    "backend/app/agents/dm_agent.py",
    "backend/app/services/tick_orchestrator.py",
    "backend/app/services/action/player_target_extractor.py",
    "backend/app/services/game_loop/agent_runner.py",
    "backend/app/services/game_loop/__init__.py",
    "backend/app/services/llm/llama_cpp_provider.py",
    "backend/app/services/npc/expectation_store.py",
    "backend/app/services/npc/npc_tick_pipeline.py",
    "backend/app/services/scene/r3_direct_builder.py",
    "backend/app/services/temporal/temporal_engine.py",
    "backend/app/services/verbalization/state_interpreter.py",
    "frontend/api_client.py",
    "frontend/game_loop_bridge.py",
    "frontend/text_input.py",
    "frontend/map_editor/data_manager.py"
]

for f in files_to_process:
    fix_silent_failures(f)

print("=== Готово ===")
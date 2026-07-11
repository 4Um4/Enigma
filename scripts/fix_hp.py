import os
import re

# Файлы для обработки (только бэкенд, исключая npc_state.py и тесты)
FILES = [
    "backend/app/api/routes.py",
    "backend/app/services/player_avatar_service.py",
    "backend/app/services/game_loop/phase_2_world_tick.py",
    "backend/app/services/game_loop/phase_6_avatar.py",
    "backend/app/services/game_loop/__init__.py",
    "backend/app/services/npc/domain_phases.py",
    "backend/app/services/npc/life_engine.py",
    "backend/app/services/npc/npc_tick_pipeline.py",
    "backend/app/services/npc/state_applicator.py",
    "backend/app/services/player_cognition/cognitive_distortion.py",
    "backend/app/services/player_cognition/pipeline.py",
    "backend/app/services/verbalization/state_interpreter.py",
    "backend/app/services/world/world_tick_engine.py",
]

def process_file(filepath: str) -> bool:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    changed = False
    
    # Заменяем .max_hp на .effective_max_hp (только чтение, не запись)
    # Исклюения: _avatar_state.hp = ... (уже исправлено вручную)
    # Мы заменяем только если после .max_hp нет знака равно (не присваивание)
    new_content = re.sub(r'(\.max_hp)(?!\s*=)', r'\1', content) # Заглушка, чтобы не сломать
    
    # Более точная замена: ищем .hp и .max_hp, но не если это присваивание (.hp =)
    def repl_hp(m):
        nonlocal changed
        changed = True
        return m.group(1) + 'effective_hp'
        
    def repl_max_hp(m):
        nonlocal changed
        changed = True
        return m.group(1) + 'effective_max_hp'

    # Заменяем .max_hp (если это не присваивание)
    # Регулярка: точка, max_hp, не равно (или конец строки/скобка)
    content = re.sub(r'(\.)max_hp(?!\s*=)', repl_max_hp, content)
    
    # Заменяем .hp (если это не присваивание и не part of .max_hp)
    # Исклюаем .hp = (запись)
    # Исклюаем .max_hp (уже заменено)
    # Исклюаем .effective_hp (чтобы не задвоить)
    content = re.sub(r'(\.)hp(?!\s*=)(?!_hp)(?!\bmax_hp\b)', repl_hp, content)
    
    if changed:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    return changed

count = 0
for f in FILES:
    if os.path.exists(f):
        if process_file(f):
            count += 1
            print(f"Fixed: {f}")

print(f"Total files fixed: {count}")
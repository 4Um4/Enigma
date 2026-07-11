import os
import re

FILES_TO_FIX_GENERICS = [
    "backend/app/models/social.py",
    "backend/app/models/thick_scene_change.py",
    "backend/app/models/world_snapshot.py",
    "backend/app/models/schemas.py",
    "backend/app/models/economy.py",
    "backend/app/models/pipeline_context.py",
    "backend/app/models/phase8.py",
    "backend/app/models/character.py",
    "backend/app/models/physical.py",
]

def ensure_imports(content: str, imports: list[str]) -> str:
    """Добавляет недостающие импорты в строку from typing import ..."""
    if "from typing import" not in content:
        content = f"from typing import {', '.join(imports)}\n" + content
        return content
        
    # Извлекаем текущие импорты
    match = re.search(r'from typing import (.*)', content)
    if not match:
        return content
        
    current_imports_str = match.group(1)
    current_imports = [i.strip() for i in current_imports_str.split(',')]
    
    # Добавляем недостающие
    for imp in imports:
        if imp not in current_imports:
            current_imports.append(imp)
            
    new_imports_str = ', '.join(sorted(set(current_imports)))
    content = content.replace(match.group(0), f"from typing import {new_imports_str}")
    return content

def fix_generics(content: str) -> str:
    """Параметризует голые dict и list."""
    def repl_dict(m):
        return m.group(1) + "Dict[str, Any]" + m.group(2)
        
    def repl_list(m):
        return m.group(1) + "List[Any]" + m.group(2)

    # : dict -> : Dict[str, Any]
    content = re.sub(r'(:\s*)dict(\b)', repl_dict, content)
    # -> dict -> -> Dict[str, Any]
    content = re.sub(r'(->\s*)dict(\b)', repl_dict, content)
    # Optional[dict] -> Optional[Dict[str, Any]]
    content = re.sub(r'(Optional\[)dict(\])', repl_dict, content)
    
    # : list -> : List[Any]
    content = re.sub(r'(:\s*)list(\b)', repl_list, content)
    # -> list -> -> List[Any]
    content = re.sub(r'(->\s*)list(\b)', repl_list, content)
    # Optional[list] -> Optional[List[Any]]
    content = re.sub(r'(Optional\[)list(\])', repl_list, content)
    
    return content

def process_file(filepath: str):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    original = content
    
    # 1. Гарантируем наличие базовых импортов
    content = ensure_imports(content, ["Any", "Dict", "List", "Optional"])
    
    # 2. Фиксим генерики
    content = fix_generics(content)
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Fixed generics: {filepath}")

# --- Специфические фиксы ---

def fix_physical():
    filepath = "backend/app/models/physical.py"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    content = ensure_imports(content, ["Any", "Dict", "List", "Optional"])
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Fixed imports: {filepath}")

def fix_character():
    filepath = "backend/app/models/character.py"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Добавляем TYPE_CHECKING и logger, если их нет
    if "if TYPE_CHECKING:" not in content:
        content = content.replace(
            "from typing import Any, Dict, List, Optional",
            "import logging\nfrom typing import Any, Dict, List, Optional, TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from app.models.front import FrontState\n\nlogger = logging.getLogger(__name__)"
        )
        
    content = fix_generics(content)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Fixed imports & generics: {filepath}")

def fix_npc_state():
    filepath = "backend/app/models/npc_state.py"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Удаляем мёртвый код после return state
    dead_code = """        # ADR-128: Диагностика рассинхронизации injuries/blood_loss (понижена до DEBUG)
        _bl = float(state.body_state.get("blood_loss", 0.0))
        _inj_count = len(state.body_state.get("injuries", []))
        if _inj_count == 0 and _bl > 0.01:
            logger.debug(f"[LEGACY_READ_LOST] npc={state.npc_id} injuries=0 BUT blood_loss={_bl:.3f}")
        return state"""
        
    if dead_code in content:
        content = content.replace(dead_code, "        return state")
        
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Fixed dead code: {filepath}")

def fix_cfrm():
    filepath = "backend/app/models/cfrm.py"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    if "if TYPE_CHECKING:" not in content:
        content = content.replace(
            "from typing import Any, Dict, FrozenSet, List, Optional, Protocol, Set, Tuple",
            "from typing import Any, Dict, FrozenSet, List, Optional, Protocol, Set, Tuple, TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from app.models.npc_state import PerceptualKernel"
        )
        
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Fixed imports: {filepath}")

if __name__ == "__main__":
    print("--- Fixing Generics ---")
    for f in FILES_TO_FIX_GENERICS:
        if os.path.exists(f):
            process_file(f)
            
    print("\n--- Fixing Specifics ---")
    fix_physical()
    fix_character()
    fix_npc_state()
    fix_cfrm()
    
    print("\nDone!")
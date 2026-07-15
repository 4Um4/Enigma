# scripts/fix_compute_calls.py
"""
Скрипт-миграция для добавления effective_drives=_MOCK_DRIVES во все вызовы hub.compute() в тестах.
"""
import re
from pathlib import Path

TESTS_DIR = Path("backend/tests")

# Паттерн для поиска вызовов hub.compute(...) на одной строке
pattern = re.compile(r"(hub\.compute\([^\n]*?)(\))")

def fix_file(filepath: Path):
    content = filepath.read_text(encoding="utf-8")
    original_content = content
    
    # 1. Добавляем импорт, если его нет
    if "EffectiveDrives" not in content:
        # Ищем первый импорт from app.
        import_match = re.search(r"^(from app\..*import .*)$", content, re.MULTILINE)
        if import_match:
            insert_line = import_match.group(1)
            content = content.replace(
                insert_line,
                "from app.domain.identity_events import EffectiveDrives\n" + insert_line,
                1
            )
            # Добавляем мок-драйвы сразу после импортов
            content = content.replace(
                "from app.domain.identity_events import EffectiveDrives",
                "from app.domain.identity_events import EffectiveDrives\n\n_MOCK_DRIVES = EffectiveDrives.from_dict({\"control\": 0.5, \"significance\": 0.5, \"fear\": 0.5, \"desire\": 0.5})\n",
                1
            )

    # 2. Заменяем вызовы
    def replacer(match):
        call_str = match.group(1)
        closing_paren = match.group(2)
        if "effective_drives" in call_str:
            return match.group(0) # Уже есть
        # Если строка заканчивается на ",", убираем её
        call_str = call_str.rstrip(", ")
        return f"{call_str}, effective_drives=_MOCK_DRIVES{closing_paren}"

    content = pattern.sub(replacer, content)

    if content != original_content:
        filepath.write_text(content, encoding="utf-8")
        print(f"✅ Fixed: {filepath}")

for py_file in TESTS_DIR.rglob("*.py"):
    if py_file.name.startswith("__"):
        continue
    fix_file(py_file)

print("Done.")
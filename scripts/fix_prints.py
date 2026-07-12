import os
import re

# Директории для обработки
DIRS = ["backend/app/services", "frontend"]
EXCLUDE_DIRS = ["tests", "sandbox", "map_editor", "__pycache__"]


def process_file(filepath: str) -> bool:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if "print(" not in content:
        return False

    # Заменяем print( на logger.debug(
    # Регулярка ловит print( в начале строки или после пробела
    new_content = re.sub(r"(\s)print\(", r"\1logger.debug(", content)

    # Проверяем, есть ли уже логгер в файле
    if "logger = logging.getLogger" not in new_content:
        lines = new_content.split("\n")
        insert_idx = 0

        # Пропускаем начальный docstring
        if lines and lines[0].startswith('"""'):
            for i in range(1, len(lines)):
                if '"""' in lines[i]:
                    insert_idx = i + 1
                    break
        elif lines and lines[0].startswith("#"):
            insert_idx = 1

        # Вставляем импорты
        lines.insert(insert_idx, "import logging")
        lines.insert(insert_idx + 1, "logger = logging.getLogger(__name__)")
        new_content = "\n".join(lines)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


count = 0
for d in DIRS:
    for root, dirs, files in os.walk(d):
        if any(ex in root for ex in EXCLUDE_DIRS):
            continue
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                if process_file(filepath):
                    count += 1
                    print(f"Fixed: {filepath}")

print(f"Total files fixed: {count}")

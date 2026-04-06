import os
from pathlib import Path
import re

ROOT_DIR = Path(".")
OUTPUT_FILE = "enigma_skeleton_dump_v3.txt"

# Ключевые папки — полный скелет
FULL_SKELETON_DIRS = {
    "backend/app/services/memory/",
    "backend/app/services/npc/",
    "backend/app/services/action/",
    "backend/app/services/events/",
}

# Все services — будут обработаны
SERVICES_DIR = "backend/app/services/"

KEY_DOCS = ["Now.md", "Before.md", "README.md", "РЕЖИМ РАБОТЫ.md", "Слом.md"]

def extract_skeleton_python(content: str, filepath: str, full_mode: bool = False) -> str:
    """Генерирует скелет .py файла"""
    lines = content.splitlines()
    skeleton = []
    skeleton.append(f"# === {filepath} {'(ПОЛНЫЙ СКЕЛЕТ)' if full_mode else '(СКЕЛЕТ)'} ===")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Импорты
        if stripped.startswith(("import ", "from ")):
            skeleton.append(line)
            continue

        # Классы и dataclass
        if re.match(r'^(class |@dataclass)', stripped):
            skeleton.append(line)
            continue

        # Функции и методы
        if re.match(r'^\s*(async )?def ', stripped):
            skeleton.append(line)
            continue

        # Важные константы и формулы
        if any(k in stripped for k in [
            "SCORE_", "DECAY_", "TRAIT_", "SATURATION_", "INTENT_INERTIA",
            "TOKEN_BUDGET", "WORKING_MEMORY_SIZE", "MAX_NARRATIVE_CACHE",
            "score =", "fear ×", "drive_weight", "delta", "bias", "weight",
            "0\\.", "1\\.0", "0\\.0", "formula", "threshold"
        ]):
            skeleton.append(line)
            continue

        # Важные примечания
        if stripped.startswith('#'):
            comment = stripped[1:].strip().lower()
            if any(word in comment for word in [
                "todo", "r5", "r6", "break", "важно", "принцип", "формула", 
                "константа", "решение", "запрещено", "правило", "note", "важное"
            ]):
                skeleton.append(line)
            continue

        # Первые строки docstring
        if stripped.startswith(('"""', "'''")) and len(stripped) > 15:
            skeleton.append("    " + stripped[:120] + ("..." if len(stripped) > 120 else ""))

    return "\n".join(skeleton) + "\n\n"


def main():
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write("# === ENIGMA SKELETON DUMP v3 ===\n")
        out.write("# Все .py в services/ + полный скелет ключевых папок\n")
        out.write(f"# Generated: {os.getcwd()}\n\n")

        # Ключевые документы — только список
        out.write("=== КЛЮЧЕВЫЕ MD ФАЙЛЫ (только список) ===\n")
        for doc in KEY_DOCS:
            if Path(doc).exists():
                out.write(f"• {doc}\n")
        out.write("\n")

        out.write("=== СКЕЛЕТ ФАЙЛОВ В SERVICES/ ===\n")

        services_path = Path(SERVICES_DIR)
        if services_path.exists():
            for file in sorted(services_path.rglob("*.py")):
                try:
                    rel_path = str(file.relative_to(ROOT_DIR))
                    content = file.read_text(encoding="utf-8", errors="ignore")

                    # Полный скелет для ключевых папок
                    full_mode = any(rel_path.startswith(d) for d in FULL_SKELETON_DIRS)
                    
                    skeleton = extract_skeleton_python(content, rel_path, full_mode)
                    out.write(skeleton)
                    print(f"✓ {'[FULL]' if full_mode else '[SHORT]'} {rel_path}")
                except Exception as e:
                    out.write(f"FILE: {rel_path}  [ERROR: {e}]\n\n")

    size_kb = Path(OUTPUT_FILE).stat().st_size / 1024
    print(f"\n✅ Skeleton dump v3 готов: {OUTPUT_FILE}")
    print(f"Размер: {size_kb:.1f} КБ")

if __name__ == "__main__":
    main()
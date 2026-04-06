# C:\DDD\Codex\VSC_Enigma\Enigma\dump_project.py
# Запуск:  python dump_project.py 
import os
from pathlib import Path
import re

ROOT_DIR = Path(".")
OUTPUT_FILE = "enigma_smart_dump.txt"

# Приоритетные папки (то, что важно сейчас)
PRIORITY_DIRS = [
    "backend/app/services/memory/",
    "backend/app/services/npc/",
    "backend/app/services/action/",
    "backend/app/services/events/",
    "backend/app/services/game_loop.py",
    "backend/app/services/game_loop_factory.py",
]

KEY_DOCS = ["Now.md", "Before.md", "README.md", "РЕЖИМ РАБОТЫ.md"]

def extract_important_python(content: str, filepath: str) -> str:
    """Сжимает .py файл до самого важного."""
    lines = content.splitlines()
    important = []
    in_function = False
    function_body_lines = 0

    important.append(f"# === {filepath} ===")
    important.append(f"# Сжатая версия: импорты + сигнатуры + ключевые формулы\n")

    for line in lines:
        stripped = line.strip()

        # Импорты
        if stripped.startswith("import ") or stripped.startswith("from "):
            important.append(line)
            continue

        # Классы и dataclass
        if re.match(r'^(class |@dataclass|@dataclass\(frozen=True\))', stripped):
            important.append(line)
            continue

        # Функции и методы (только сигнатура + первая строка docstring)
        if re.match(r'^\s*(async )?def ', stripped):
            important.append(line)
            in_function = True
            function_body_lines = 0
            continue

        # Docstring в начале функции/класса
        if in_function and function_body_lines < 4:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                important.append("    " + stripped[:120] + ("..." if len(stripped) > 120 else ""))
            function_body_lines += 1
            if function_body_lines > 6:
                in_function = False
            continue

        # Важные константы и формулы
        if any(k in stripped for k in [
            "SCORE_", "DECAY_", "TRAIT_", "SATURATION_", "INTENT_INERTIA",
            "WORKING_MEMORY_SIZE", "TOKEN_BUDGET", "_TOKEN_BUDGET",
            "drive_weight", "fear ×", "score =", "formula", "0.0", "1.0"
        ]):
            important.append(line)
            continue

        # TODO и важные комментарии
        if "TODO" in stripped or "R5." in stripped or "R6." in stripped or "BREAK" in stripped.upper():
            important.append(line)

    # Если файл очень маленький — выводим целиком
    if len(important) < 15 and len(content) < 800:
        return content

    return "\n".join(important) + "\n\n"


def main():
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write("# === ENIGMA SMART DUMP ===\n")
        out.write("# Фокус: R5 Memory Depth + подготовка к R6 Break System\n")
        out.write(f"# Generated: {os.getcwd()}\n\n")

        # 1. Ключевые документы полностью
        out.write("=== КЛЮЧЕВЫЕ ДОКУМЕНТЫ ===\n")
        for doc in KEY_DOCS:
            p = Path(doc)
            if p.exists():
                out.write(f"\n{'='*90}\nFILE: {doc}\n{'='*90}\n\n")
                out.write(p.read_text(encoding="utf-8", errors="ignore"))
                out.write("\n\n")

        # 2. Приоритетные модули — умный режим
        out.write("=== ПРИОРИТЕТНЫЕ МОДУЛИ (сжато) ===\n")
        for pdir in PRIORITY_DIRS:
            dir_path = Path(pdir)
            if not dir_path.exists():
                continue
            if dir_path.is_file():
                files = [dir_path]
            else:
                files = sorted(dir_path.rglob("*.py"))

            for file in files:
                try:
                    content = file.read_text(encoding="utf-8", errors="ignore")
                    smart_content = extract_important_python(content, str(file.relative_to(ROOT_DIR)))
                    out.write(smart_content)
                    out.write("\n" + "="*80 + "\n\n")
                    print(f"✓ Сжат: {file.relative_to(ROOT_DIR)}")
                except Exception as e:
                    out.write(f"FILE: {file}  [ERROR: {e}]\n\n")

    size_mb = Path(OUTPUT_FILE).stat().st_size / (1024*1024)
    print(f"\n✅ Smart dump готов: {OUTPUT_FILE}")
    print(f"Размер: {size_mb:.2f} МБ (значительно меньше полного)")

if __name__ == "__main__":
    main()
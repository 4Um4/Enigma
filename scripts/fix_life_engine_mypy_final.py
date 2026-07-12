# scripts/fix_life_engine_mypy_final.py
"""
Финальная корректировка сигнатур tick и macro_simulate для mypy --strict.
"""
from pathlib import Path

FILE_PATH = Path("backend/app/services/npc/life_engine.py")

def apply_fixes():
    if not FILE_PATH.exists():
        print(f"❌ Файл не найден: {FILE_PATH}")
        return

    content = FILE_PATH.read_text(encoding="utf-8")
    original_content = content

    # 1. Сигнатура tick
    content = content.replace(
        'tuple[list[SceneChange], Optional["MacroMovementGoal"]]',
        'tuple[list[SceneChange], list["MacroMovementGoal"]]'
    )

    # 2. Сигнатура macro_simulate (если она была изменена)
    content = content.replace(
        'tuple[list[SceneChange], list["MacroMovementGoal"]]',
        'tuple[list[SceneChange], list["MacroMovementGoal"]]' # ensure it's a list
    )

    # 3. Возврат macro_simulate (заменяем None на [])
    content = content.replace(
        "        return (\n            all_changes,\n            None,\n        )  # ADR-049: macro_simulate не генерирует intents (только tick) — type fix",
        "        return (\n            all_changes,\n            [],\n        )  # ADR-049: macro_simulate не генерирует intents (только tick)"
    )

    # 4. Замена MovementIntent на MacroMovementGoal в аннотациях внутри файла
    # Это безопасно, так как MovementIntent не импортируется и не существует в domain/movement.py
    content = content.replace("list[MovementIntent]", 'list["MacroMovementGoal"]')
    content = content.replace("MovementIntent | None", 'Optional["MacroMovementGoal"]')
    # На всякий случай, если где-то остался Optional[MovementIntent]
    content = content.replace('Optional[MovementIntent]', 'Optional["MacroMovementGoal"]')

    if content != original_content:
        FILE_PATH.write_text(content, encoding="utf-8")
        print("✅ Файл life_engine.py успешно обновлен (final).")
    else:
        print("⚠️ Замены не применены. Проверьте шаблоны.")

if __name__ == "__main__":
    apply_fixes()
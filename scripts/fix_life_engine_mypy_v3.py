# scripts/fix_life_engine_mypy_v3.py
"""
Точечная корректировка сигнатур update_routine и check_random_events.
"""
from pathlib import Path

FILE_PATH = Path("backend/app/services/npc/life_engine.py")

def apply_fixes():
    if not FILE_PATH.exists():
        return

    content = FILE_PATH.read_text(encoding="utf-8")
    original_content = content

    # 1. Возвращаем update_routine и check_random_events к Optional
    content = content.replace(
        '    ) -> tuple[list[SceneChange], list["MacroMovementGoal"]]:\n        """\n        Обновляет позицию NPC согласно расписанию',
        '    ) -> tuple[list[SceneChange], Optional["MacroMovementGoal"]]:\n        """\n        Обновляет позицию NPC согласно расписанию'
    )
    content = content.replace(
        '    ) -> tuple[list[SceneChange], list["MacroMovementGoal"]]:\n        """\n        С вероятностью RANDOM_EVENT_CHANCE',
        '    ) -> tuple[list[SceneChange], Optional["MacroMovementGoal"]]:\n        """\n        С вероятностью RANDOM_EVENT_CHANCE'
    )

    # 2. Убеждаемся, что _simulate_major возвращает список
    content = content.replace(
        '    ) -> tuple[list[SceneChange], list["MovementIntent"]]:',
        '    ) -> tuple[list[SceneChange], list["MacroMovementGoal"]]:'
    )

    # 3. Убеждаемся, что tick возвращает список
    content = content.replace(
        '    ) -> tuple[list[SceneChange], Optional["MacroMovementGoal"]]:\n        """\n        Главная точка входа',
        '    ) -> tuple[list[SceneChange], list["MacroMovementGoal"]]:\n        """\n        Главная точка входа'
    )

    # 4. Убеждаемся, что macro_simulate возвращает список (пустой)
    # Заменяем все возвраты None на [] в macro_simulate
    content = content.replace(
        '            None,\n        )  # ADR-049: macro_simulate не генерирует intents (только tick) — type fix',
        '            [],\n        )  # ADR-049: macro_simulate не генерирует intents (только tick)'
    )

    if content != original_content:
        FILE_PATH.write_text(content, encoding="utf-8")
        print("✅ Файл life_engine.py успешно обновлен (v3).")
    else:
        print("⚠️ Замены не применены.")

if __name__ == "__main__":
    apply_fixes()
# scripts/fix_life_engine_mypy_v2.py
"""
Финальный проход mypy --strict для life_engine.py.
"""
from pathlib import Path

FILE_PATH = Path("backend/app/services/npc/life_engine.py")

def apply_fixes():
    if not FILE_PATH.exists():
        print(f"❌ Файл не найден: {FILE_PATH}")
        return

    content = FILE_PATH.read_text(encoding="utf-8")
    original_content = content

    # 1. Сигнатура macro_simulate
    content = content.replace(
        'tuple[list[SceneChange], Optional[Dict[str, Any]]]',
        'tuple[list[SceneChange], list["MacroMovementGoal"]]'
    )
    # На случай, если она уже была tuple[list[SceneChange], Any]
    content = content.replace(
        'tuple[list[SceneChange], Any]',
        'tuple[list[SceneChange], list["MacroMovementGoal"]]'
    )

    # 2. Сигнатура tick (ожидаем list[MacroMovementGoal] вместо None)
    content = content.replace(
        'tuple[list[SceneChange], MacroMovementGoal | None]',
        'tuple[list[SceneChange], list["MacroMovementGoal"]]'
    )
    content = content.replace(
        'tuple[list[SceneChange], Optional[MacroMovementGoal]]',
        'tuple[list[SceneChange], list["MacroMovementGoal"]]'
    )

    # 3. current_position: убираем повторное определение типа (no-redef) 
    # и добавляем assert для getattr
    content = content.replace(
        '                        current_position: str = getattr(_ref, "node_id", str(_ref))',
        '                        current_position = getattr(_ref, "node_id", str(_ref))\n                        assert isinstance(current_position, str)'
    )

    # 4. rng.choice type ignore (строка 2466)
    content = content.replace(
        'event_id, changes, movement_intent = rng.choice(events)',
        'event_id, changes, movement_intent = rng.choice(events)  # type: ignore[no-untyped-call]'
    )

    if content != original_content:
        FILE_PATH.write_text(content, encoding="utf-8")
        print("✅ Файл life_engine.py успешно обновлен (v2).")
    else:
        print("⚠️ Замены не применены. Проверьте шаблоны.")

if __name__ == "__main__":
    apply_fixes()
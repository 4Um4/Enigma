from pathlib import Path


def main() -> None:
    target_file = Path("backend/app/services/spatial/movement_engine.py")

    if not target_file.exists():
        print(f"❌ Файл не найден: {target_file}")
        return

    content = target_file.read_text(encoding="utf-8")

    # Точная замена: меняем только обращения через intent.npc_id,
    # чтобы не задеть state.npc_id, decision.npc_id, new_state.npc_id и т.д.
    old_phrase = "intent.npc_id"
    new_phrase = "intent.actor_id"

    if old_phrase not in content:
        print(f"⚠️ '{old_phrase}' не найден в {target_file}. Замена не требуется.")
        return

    occurrences = content.count(old_phrase)
    new_content = content.replace(old_phrase, new_phrase)

    target_file.write_text(new_content, encoding="utf-8")
    print(
        f"✅ Успешно заменено {occurrences} вхождений '{old_phrase}' на '{new_phrase}' в {target_file}"
    )


if __name__ == "__main__":
    main()

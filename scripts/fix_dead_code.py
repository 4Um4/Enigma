import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def fix_file(rel_path: str, replacements: list[tuple[str, str]]):
    file_path = ROOT / rel_path
    if not file_path.exists():
        print(f"[WARN] File not found: {file_path}")
        return
    
    content = file_path.read_text(encoding="utf-8")
    changed = False
    for old_text, new_text in replacements:
        if old_text in content:
            content = content.replace(old_text, new_text)
            changed = True
    
    if changed:
        file_path.write_text(content, encoding="utf-8")
        print(f"[FIXED] {rel_path}")
    else:
        print(f"[SKIP] {rel_path} (patterns not found)")

def delete_file(rel_path: str):
    file_path = ROOT / rel_path
    if file_path.exists():
        file_path.unlink()
        print(f"[DELETED] {rel_path}")
    else:
        print(f"[SKIP] {rel_path} (already deleted)")

# 1. Чистим пробелы в fix_ruff_style.py
fix_file("scripts/fix_ruff_style.py", [
    ("    Один LLM-вызов за раз (single-threaded). Все canonical/eavesdrop/DM \n", "    Один LLM-вызов за раз (single-threaded). Все canonical/eavesdrop/DM\n"),
    ("        12-15:  0.2  (подростковый пик — язык сверстников, \n", "        12-15:  0.2  (подростковый пик — язык сверстников,\n"),
    ("        Метод находит объект, берёт его XY и возвращает ближайший \n", "        Метод находит объект, берёт его XY и возвращает ближайший\n"),
    ("Запуск: \n", "Запуск:\n"),
])

# 2. Удаляем мёртвый код legacy_delta_adapter
delete_file("backend/app/services/npc/legacy_delta_adapter.py")

fix_file("backend/app/services/npc/npc_tick_pipeline.py", [
    ("from app.services.npc.legacy_delta_adapter import LegacyStateDeltaAdapter\n", ""),
])
fix_file("backend/app/services/npc/state_applicator.py", [
    ("from app.services.npc.legacy_delta_adapter import LegacyStateDeltaAdapter\n", ""),
])
fix_file("backend/app/services/verbalization/scene_outcome_builder.py", [
    ("from app.services.npc.legacy_delta_adapter import LegacyStateDeltaAdapter\n", ""),
    ("        from app.services.npc.legacy_delta_adapter import LegacyStateDeltaAdapter\n", ""),
])
fix_file("backend/app/services/verbalization/tension_synthesizer.py", [
    ("            from app.services.npc.legacy_delta_adapter import LegacyStateDeltaAdapter\n", ""),
])

# 3. Удаляем мёртвый комментарий в dto.py
fix_file("backend/app/services/dto.py", [
    ("# TODO: удалить после замены HubEventContext на EventDTO\n\n\n", ""),
])

# 4. Вырезаем блок "фантазийных" TODO из perception_filter.py
fix_file("backend/app/services/npc/perception_filter.py", [
    ('"""\nTODO: после полной миграции на EventDTO удалить поддержку dict и GameEvent в аргументах.\nTODO: после миграции на EventDTO удалить временную заглушку с visible_to/audible_to в GameEvent.\nTODO: расширение функционала — добавить дополнительные факторы в clarity (погода, состояние NPC, тип события и т.д.)\nTODO: оптимизация — кэшировать результаты perception для каждого NPC в течение одного тика, чтобы не пересчитывать для каждого события.\nTODO: расширение функционала — добавить поддержку разных типов восприятия (зрение, слух, обоняние) с разными радиусами и условиями.\nTODO: расширение функционала — добавить поддержку разных типов событий (визуальные, звуковые, тактильные) с разными шаблонами восприятия.\nTODO: расширение функционала — учитывать направление взгляда NPC для более реалистичного восприятия.\nTODO: расширение функционала — учитывать динамические изменения в сцене (движущиеся объекты, открывающиеся двери) при расчёте line of sight.\nTODO: расширение функционала — добавить поддержку "слепых зон" (например, NPC не видит за спиной).\nTODO: расширение функционала — учитывать индивидуальные особенности NPC (например, плохое зрение, глухота) при расчёте восприятия.\nTODO: расширение функционала — добавить поддержку "интуиции" (например, NPC может "чувствовать" присутствие игрока даже если не видит его напрямую).\nTODO: расширение функционала — добавить поддержку "слуховой маскировки" (например, если игрок стоит на ковре, его шаги менее слышны).\nTODO: расширение функционала — добавить поддержку "визуальной маскировки" (например, если игрок прячется в тени, его сложнее заметить).\nTODO: расширение функционала — добавить поддержку "шумовой маскировки" (например, если рядом есть громкий источник звука, NPC с меньшей вероятностью услышит тихое действие).\nTODO: расширение функционала — добавить поддержку "социального восприятия" (например, NPC может заметить изменения в поведении других NPC, даже если не видит игрока напрямую).\nTODO: расширение функционала — добавить поддержку "эмоционального восприятия" (например, NPC может почувствовать страх или агрессию игрока, даже если не видит его напрямую).\nTODO: расширение формулы clarity — добавить нелинейные эффекты (например, очень близкие объекты воспринимаются значительно чётче, чем просто "на 1 метр ближе").\nTODO: расширение формулы clarity — добавить эффект "порогового восприятия" (например, если distance > 15, clarity резко падает до 0, а не плавно).\nTODO: расширение формулы clarity — добавить эффект "насыщения" (например, если свет слишком яркий, clarity может начать снижаться из-за ослепления).\nTODO: расширение формулы clarity — добавить эффект "стрессового искажения" (например, при очень высоком стрессе NPC может начать воспринимать события искажённо, снижая clarity для определённых типов событий).\n"""\n', '"""\n'),
])

# 5. Удаляем мёртвый комментарий в game_loop/__init__.py
fix_file("backend/app/services/game_loop/__init__.py", [
    ("        # TODO: _write_memory удалён — persist_dm_response на строке ниже покрывает запись\n", ""),
])

print("Done.")
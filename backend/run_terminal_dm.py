# C:\DDD\Codex\VSC_Enigma\Enigma\backend\run_terminal_dm.py
from __future__ import annotations
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent  # backend/
APP_DIR = _PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import os
import re
from pathlib import Path

from app.core.config import settings
from app.models.schemas import ModelProvider, ModelSelection
from app.services.knowledge_ingest import KnowledgeIngestService

# GameOrchestrator удалён — заменён на game_loop.py
# from app.services.orchestrator import GameOrchestrator
from app.services.pdf_drop_importer import PdfDropImporter
from app.services.campaign_state_service import get_campaign_state_service
# from app.services.context_builder import build_dynamic_context  # legacy

# Папка data — в корне проекта (родитель backend)
_PROJECT_ROOT = Path(__file__).resolve().parent  # backend/
PDF_DROP_FOLDER = _PROJECT_ROOT / "data" / "pdf_drop"

# Включить отладочный режим (показывает сырой ответ модели)
_DEBUG_MODE = "--debug" in os.sys.argv


# Ограничения контекста: полные PDF = миллионы символов.
_MAX_CHARS_WORLD_ENTRY = 2500
_MAX_WORLD_ENTRIES = 2
_MAX_CHARS_CAMPAIGN_ENTRY = 500
_MAX_CHARS_SESSION_ENTRY = 500


def _truncate_world_entry(entry: dict) -> dict:
    """Обрезает поле text в записи world_canon."""
    out = dict(entry)
    text = out.get("text", "")
    if isinstance(text, str) and len(text) > _MAX_CHARS_WORLD_ENTRY:
        out["text"] = text[:_MAX_CHARS_WORLD_ENTRY] + "\n[... обрезано ...]"
    return out


def _truncate_str(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len] + " [...]"


def _normalize_subcommand(text: str) -> str | None:
    """Нормализует подкоманду к 'add', поддерживая русские варианты."""
    sub = text.lower()
    if sub in ["add", "добавить", "доб", "адд", "+"]:
        return "add"
    if sub in ["del", "удалить", "удал", "-"]:
        return "del"
    return None


def _cleanup_model_response(text: str) -> str:
    """Очищает ответ модели от тегов промпта и лишних символов."""
    cleaned = text

    # 1. Удаляем все теги system, user, assistant
    for tag in ["system", "user", "assistant", "system_prompt", "end_of_prompt"]:
        cleaned = re.sub(
            f"<{tag}>.*?</{tag}>", "", cleaned, flags=re.IGNORECASE | re.DOTALL
        )
        cleaned = re.sub(f"</?{tag}>", "", cleaned, flags=re.IGNORECASE)

    # 2. Удаляем markdown код блоки
    cleaned = re.sub(r"```\w*\n", "\n", cleaned)
    cleaned = re.sub(r"```", "", cleaned)

    # 3. Удаляем повторяющиеся паттерны
    lines = cleaned.split("\n")
    unique_lines = []
    seen = set()
    for line in lines:
        line_stripped = line.strip()
        if line_stripped and line_stripped not in seen:
            unique_lines.append(line)
            seen.add(line_stripped)
    cleaned = "\n".join(unique_lines)

    # 4. Удаляем "Что будете делать?" и подобные фразы
    for pattern in [
        "**Что вы делаете?**",
        "**Что будете делать?**",
        "(или предложите действие)",
        "(или позвольте игрокам действовать)",
    ]:
        cleaned = cleaned.replace(pattern, "")

    # 5. Чистка
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()

    if not cleaned:
        cleaned = "(Мастер ожидает вашего действия...)"

    return cleaned


def build_prompt(user_text: str, context: dict) -> str:
    world_canon = context.get("world_canon", [])[-_MAX_WORLD_ENTRIES:]
    campaign_memory = context.get("campaign_memory", [])[-3:]
    session_memory = context.get("session_memory", [])[-5:]

    world_trunc = [_truncate_world_entry(e) for e in world_canon]
    campaign_trunc = [
        _truncate_str(str(e), _MAX_CHARS_CAMPAIGN_ENTRY) for e in campaign_memory
    ]
    session_trunc = [
        _truncate_str(str(e), _MAX_CHARS_SESSION_ENTRY) for e in session_memory
    ]

    return (
        "Ты ИИ-мастер D&D 5e. Отвечай на русском. "
        "Не выдумывай факты, если их нет в каноне. "
        "Если нужен бросок, обязательно попроси: 'Сделайте бросок d20'.\n\n"
        f"Канон мира (последние записи): {world_trunc}\n"
        f"Память кампании (последние записи): {campaign_trunc}\n"
        f"Память сессии (последние записи): {session_trunc}\n\n"
        f"Сообщение игрока: {user_text}\n"
        "Ответ мастера:"
    )


def main() -> None:
    campaign_id = os.getenv("AIDM_CAMPAIGN_ID", "demo-campaign")
    world_id = os.getenv("AIDM_WORLD_ID", "demo-world")

    data_dir = str(_PROJECT_ROOT / "data")
    orchestrator = GameOrchestrator(data_dir=data_dir)
    campaign_service = get_campaign_state_service()
    ingest = KnowledgeIngestService(orchestrator.layered_memory)
    drop_importer = PdfDropImporter(ingest)

    model_path = (
        os.getenv("LLAMA_CPP_MODEL")
        or os.getenv("LLAMA_TEST_MODEL")
        or settings.llama_cpp_model_path
        or "model.gguf"
    )
    model_name = Path(model_path).name
    model = ModelSelection(provider=ModelProvider.llama_cpp, model_name=model_name)
    orchestrator.llm_manager.switch_model(model)

    use_server = bool(os.getenv("LLAMA_CPP_SERVER_URL"))
    print("=== Local AI DM Terminal ===")
    print("Команды:")
    print(f"  /ingest   -> импортировать PDF/TXT/MD из {PDF_DROP_FOLDER}")
    print("  /state    -> показать краткое состояние памяти")
    print("  /campaign (/кампания) -> состояние кампании")
    print("  /player (/игрок) -> список игроков")
    print("  /fact (/факт) -> факты мира")
    print("  /session (/сессия) -> список сессий")
    print("  /exit     -> выход")
    print(f"Текущая модель: {orchestrator.llm_manager.active_model()}")
    if use_server:
        print("Режим: llama-server (модель в памяти, быстрые ответы)")
    else:
        print("Режим: llama-cli (медленно: загрузка модели при каждом ответе)")
        print("  Подсказка: start_dm_terminal_with_server.bat для быстрых ответов")
    print(f"Кампания: {campaign_id} | Мир: {world_id}\n")

    # История сессии для контекст-билдера (умный поиск фактов)
    session_history: list[dict] = []

    while True:
        text = input("Вы: ").strip()
        if not text:
            continue
        if text == "/exit":
            print("Выход.")
            return

        # /model <1-4> - переключить модель
        if text.startswith("/model "):
            parts = text.split()
            if len(parts) >= 2:
                model_num = parts[1]
                model_map = {
                    "1": "qwen2.5-7b-instruct-q4_k_m.gguf",
                    "2": "Qwen3.5-9B.gguf",
                    "3": "saiga_mistral_7b_model-q4_K.gguf",
                    "4": "YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf",
                }
                if model_num in model_map:
                    new_model = model_map[model_num]
                    ROOT_ENIGMA = _PROJECT_ROOT.parent  # Enigma/
                    model_path = ROOT_ENIGMA / "Models LLM" / new_model
                    model = ModelSelection(
                        provider=ModelProvider.llama_cpp, model_name=new_model
                    )
                    orchestrator.llm_manager.switch_model(model)
                    os.environ["LLAMA_CPP_MODEL"] = model_path
                    print(f"[Смена модели] Загружается: {new_model}")
                    print("[ВНИМАНИЕ] Перезапустите скрипт для применения модели!")
                    continue
                else:
                    print("Использование: /model <1-4>")
                    print("  1 - Qwen2.5-7B (DM)")
                    print("  2 - Qwen3.5-9B (World)")
                    print("  3 - Saiga-7B (Rules)")
                    print("  4 - YandexGPT-8B (NPC)")
                    continue
            continue

        if text == "/model":
            print("Доступные модели:")
            print("  1 - Qwen2.5-7B (DM)")
            print("  2 - Qwen3.5-9B (World)")
            print("  3 - Saiga-7B (Rules)")
            print("  4 - YandexGPT-8B (NPC)")
            print("Использование: /model <номер>")
            continue
        if text == "/ingest":
            folder_path = Path(PDF_DROP_FOLDER)
            if not folder_path.exists():
                print(f"[Ошибка] Папка не найдена: {folder_path.resolve()}")
                continue
            imported = drop_importer.import_from_folder(
                PDF_DROP_FOLDER, world_id=world_id, campaign_id=campaign_id
            )
            if not imported:
                files_in_dir = (
                    list(folder_path.iterdir()) if folder_path.exists() else []
                )
                pdf_count = sum(
                    1
                    for f in files_in_dir
                    if f.suffix.lower() in {".pdf", ".txt", ".md"}
                )
                print(f"Папка: {folder_path.resolve()}")
                print(
                    f"Файлов PDF/TXT/MD: {pdf_count}. Папка пуста или форматы не подходят."
                )
                continue
            print(f"Импортировано файлов: {len(imported)}")
            for item in imported:
                print(
                    f"- {item.filename} [{item.kind}] {item.status}: {item.message} (chars={item.chars})"
                )
            continue
        if text == "/state":
            ctx = orchestrator.layered_memory.build_dynamic_context(
                world_id=world_id, campaign_id=campaign_id
            )
            print(
                "Слои памяти => "
                f"WORLD_CANON={len(ctx['world_canon'])}, "
                f"CAMPAIGN_MEMORY={len(ctx['campaign_memory'])}, "
                f"SESSION_MEMORY={len(ctx['session_memory'])}, "
                f"NPC_MEMORY={len(ctx['npc_memory'])}"
            )
            continue

        # === Новые команды Campaign State ===
        # /campaign или /кампания - состояние кампании
        if text == "/campaign" or text == "/кампания":
            summary = campaign_service.get_summary(campaign_id)
            print("=== Состояние кампании ===")
            print(f"ID: {summary['campaign_id']}")
            print(f"Название: {summary['campaign_name']}")
            print(f"Игроков: {summary['players_count']}")
            print(f"Фактов мира: {summary['facts_count']}")
            print(f"Сессий: {summary['sessions_count']}")
            if summary["categories"]:
                print(f"Категории фактов: {', '.join(summary['categories'])}")
            continue

        # /player или /игрок - игроки
        if text.startswith("/player") or text.startswith("/игрок"):
            # Нормализуем команду
            cmd = text.replace("/игрок", "/player", 1)
            parts = cmd.split(maxsplit=2)
            if len(parts) == 1:
                players = campaign_service.get_players(campaign_id)
                if not players:
                    print("Нет зарегистрированных игроков.")
                else:
                    print("=== Игроки ===")
                    for p in players:
                        print(f"- {p.name} | {p.race} {p.class_name} lvl{p.level}")
                        if p.notes:
                            print(f"  Заметки: {p.notes}")
                continue

            if _normalize_subcommand(parts[1]) == "add" and len(parts) >= 3:
                add_parts = parts[2].split()
                if len(add_parts) < 4:
                    print("Использование: /player add <имя> <раса> <класс> <уровень>")
                    print("Пример: /player add Элар Полуэльф Заклинатель 3")
                    continue
                name, race, class_name, level_str = (
                    add_parts[0],
                    add_parts[1],
                    add_parts[2],
                    add_parts[3],
                )
                try:
                    level = int(level_str)
                except ValueError:
                    level = 1
                player = campaign_service.add_player(
                    campaign_id, name, race, class_name, level
                )
                print(
                    f"Добавлен/обновлён игрок: {player.name} ({player.race} {player.class_name} lvl{player.level})"
                )
                continue

            player_name = parts[1]
            player = campaign_service.get_player(campaign_id, player_name)
            if player:
                print(f"=== {player.name} ===")
                print(f"Раса: {player.race or 'не указана'}")
                print(f"Класс: {player.class_name or 'не указан'}")
                print(f"Уровень: {player.level}")
                print(f"Заметки: {player.notes or 'нет'}")
                print(
                    f"Создан: {player.created_at[:10] if player.created_at else 'неизвестно'}"
                )
            else:
                print(
                    f"Игрок '{player_name}' не найден. Используйте /player add для добавления."
                )
            continue

        # /fact или /факт - факты мира
        if text.startswith("/fact") or text.startswith("/факт"):
            cmd = text.replace("/факт", "/fact", 1)
            parts = cmd.split(maxsplit=2)
            if len(parts) == 1:
                facts = campaign_service.get_world_facts(campaign_id)
                if not facts:
                    print("Нет сохранённых фактов о мире.")
                else:
                    print("=== Факты мира ===")
                    for f in facts:
                        print(
                            f"[{f.category}] {f.text[:100]}{'...' if len(f.text) > 100 else ''}"
                        )
                        if f.tags:
                            print(f"  Теги: {', '.join(f.tags)}")
                continue

            if _normalize_subcommand(parts[1]) == "add" and len(parts) >= 3:
                text_to_add = parts[2]
                category = campaign_service.auto_detect_category(text_to_add)
                fact = campaign_service.add_world_fact(
                    campaign_id, text_to_add, category=category
                )
                print(
                    f"Добавлен факт [{category}]: {fact.text[:80]}{'...' if len(fact.text) > 80 else ''}"
                )
                continue

            category_filter = parts[1]
            facts = campaign_service.get_world_facts(
                campaign_id, category=category_filter
            )
            if not facts:
                print(f"Нет фактов в категории '{category_filter}'")
            else:
                print(f"=== Факты [{category_filter}] ===")
                for f in facts:
                    print(f"- {f.text[:100]}{'...' if len(f.text) > 100 else ''}")
            continue

        # /session или /сессия - сессии
        if text.startswith("/session") or text.startswith("/сессия"):
            cmd = text.replace("/сессия", "/session", 1)
            parts = cmd.split(maxsplit=2)
            if len(parts) == 1:
                sessions = campaign_service.get_session_summaries(campaign_id)
                if not sessions:
                    print("Нет описаний сессий.")
                else:
                    print("=== Сессии ===")
                    for s in sessions:
                        print(
                            f"[{s.date}] {s.summary[:100]}{'...' if len(s.summary) > 100 else ''}"
                        )
                        if s.location:
                            print(f"  Локация: {s.location}")
                continue

            if _normalize_subcommand(parts[1]) == "add" and len(parts) >= 3:
                summary_text = parts[2]
                session = campaign_service.add_session_summary(
                    campaign_id, summary_text
                )
                print(
                    f"Добавлено описание сессии: {session.summary[:80]}{'...' if len(session.summary) > 80 else ''}"
                )
                continue

            print("Использование: /session - показать все | /session add <описание>")
            continue

        # === Используем умный контекст-билдер с поиском релевантных фактов ===
        # Получаем контекст с релевантными фактами из CampaignState
        ctx = orchestrator.layered_memory.build_dynamic_context(
            world_id=world_id, campaign_id=campaign_id
        )

        # Используем build_dynamic_context для умного поиска фактов
        prompt = build_dynamic_context(
            session_history=session_history,
            campaign_id=campaign_id,
            user_query=text,
            world_canon=ctx.get("world_canon", None),
            max_facts=5,  # Увеличили для глубины
            max_recent_messages=15,  # Больше контекста диалога
        )

        try:
            answer = orchestrator.llm_manager.run(prompt)
        except Exception as exc:
            print(f"[Ошибка llama.cpp] {exc}")
            if not os.getenv("LLAMA_CPP_SERVER_URL"):
                print(
                    "Подсказка: для быстрых ответов используйте start_dm_terminal_with_server.bat"
                )
            continue

        # Очищаем ответ от тегов промпта
        cleaned_answer = _cleanup_model_response(answer)

        # Показываем сырой ответ в режиме отладки
        if _DEBUG_MODE:
            print(f"[DEBUG RAW]: {repr(answer)}\n")

        print(f"DM: {cleaned_answer}\n")

        # Добавляем в историю сессии для контекст-билдера
        session_history.append({"player_text": text, "dm_response": answer})

        # Также сохраняем в память кампании (как и раньше)
        orchestrator.layered_memory.write_campaign_memory(
            campaign_id,
            {
                "world_id": world_id,
                "event": "terminal_turn",
                "player_text": text,
                "dm_response": answer,
                "model": orchestrator.llm_manager.active_model(),
            },
        )
        orchestrator.layered_memory.write_session_memory(
            campaign_id,
            {
                "world_id": world_id,
                "player_text": text,
                "dm_response": answer[:1000],
                "dice_input_required": "Сделайте бросок d20" in answer,
            },
        )


if __name__ == "__main__":
    main()

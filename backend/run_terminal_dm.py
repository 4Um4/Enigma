from __future__ import annotations

import os
from pathlib import Path

from app.models.schemas import ModelProvider, ModelSelection
from app.services.knowledge_ingest import KnowledgeIngestService
from app.services.orchestrator import GameOrchestrator
from app.services.pdf_drop_importer import PdfDropImporter

PDF_DROP_FOLDER = "data/pdf_drop"


def build_prompt(user_text: str, context: dict) -> str:
    world_canon = context.get("world_canon", [])[-3:]
    campaign_memory = context.get("campaign_memory", [])[-3:]
    session_memory = context.get("session_memory", [])[-5:]

    return (
        "Ты ИИ-мастер D&D 5e. Отвечай на русском. "
        "Не выдумывай факты, если их нет в каноне. "
        "Если нужен бросок, обязательно попроси: 'Сделайте бросок d20'.\n\n"
        f"Канон мира (последние записи): {world_canon}\n"
        f"Память кампании (последние записи): {campaign_memory}\n"
        f"Память сессии (последние записи): {session_memory}\n\n"
        f"Сообщение игрока: {user_text}\n"
        "Ответ мастера:"
    )


def main() -> None:
    campaign_id = os.getenv("AIDM_CAMPAIGN_ID", "demo-campaign")
    world_id = os.getenv("AIDM_WORLD_ID", "demo-world")

    orchestrator = GameOrchestrator(data_dir="data")
    ingest = KnowledgeIngestService(orchestrator.layered_memory)
    drop_importer = PdfDropImporter(ingest)

    model_path = os.getenv("LLAMA_CPP_MODEL") or os.getenv("LLAMA_TEST_MODEL") or "model.gguf"
    model_name = Path(model_path).name
    model = ModelSelection(provider=ModelProvider.llama_cpp, model_name=model_name)
    orchestrator.llm_manager.switch_model(model)

    print("=== Local AI DM Terminal ===")
    print("Команды:")
    print("  /ingest   -> импортировать PDF/TXT/MD из data/pdf_drop")
    print("  /state    -> показать краткое состояние памяти")
    print("  /exit     -> выход")
    print(f"Текущая модель: {orchestrator.llm_manager.active_model()}")
    print(f"Кампания: {campaign_id} | Мир: {world_id}\n")

    while True:
        text = input("Вы: ").strip()
        if not text:
            continue
        if text == "/exit":
            print("Выход.")
            return
        if text == "/ingest":
            imported = drop_importer.import_from_folder(PDF_DROP_FOLDER, world_id=world_id, campaign_id=campaign_id)
            if not imported:
                print(f"Папка пуста или отсутствует. Добавьте файлы в {PDF_DROP_FOLDER}")
                continue
            print(f"Импортировано файлов: {len(imported)}")
            for item in imported:
                print(f"- {item.filename} [{item.kind}] {item.status}: {item.message} (chars={item.chars})")
            continue
        if text == "/state":
            ctx = orchestrator.layered_memory.build_dynamic_context(world_id=world_id, campaign_id=campaign_id)
            print(
                "Слои памяти => "
                f"WORLD_CANON={len(ctx['world_canon'])}, "
                f"CAMPAIGN_MEMORY={len(ctx['campaign_memory'])}, "
                f"SESSION_MEMORY={len(ctx['session_memory'])}, "
                f"NPC_MEMORY={len(ctx['npc_memory'])}"
            )
            continue

        context = orchestrator.layered_memory.build_dynamic_context(world_id=world_id, campaign_id=campaign_id)
        prompt = build_prompt(text, context)

        try:
            answer = orchestrator.llm_manager.run(prompt)
        except Exception as exc:
            print(f"[Ошибка llama.cpp] {exc}")
            print("Проверьте LLAMA_CPP_EXECUTABLE и LLAMA_CPP_MODEL.")
            continue

        print(f"DM: {answer}\n")
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

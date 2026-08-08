"""
path: /backend/tests/sandbox/micro/test_speech_scheduler.py
Назначение: Тестирование Narrative Arbitration Layer (ADR-O-343).

Запуск: cd backend; python -m tests.sandbox.micro.test_speech_scheduler; cd ..
"""
import sys
import os
import time

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

from app.services.game_loop.speech_scheduler import SpeechScheduler

def test_pacing_and_deduplication():
    """Сценарий: 6 NPC / 11 быстрых idle ticks не должны порождать лавину LLM-вызовов."""
    scheduler = SpeechScheduler()
    
    # Симулируем 11 тиков (каждый тик ~0.5 сек wall-clock, но для теста мгновенно)
    admitted_count = 0
    npc_ids = ["orm", "borko", "lusya", "goran", "tornin", "shadow"]
    
    # 11 тиков, 6 NPC в каждом пытаются сказать "привет"
    for tick in range(11):
        for npc in npc_ids:
            task_dict = {
                "owner_id": npc,
                "kind": "dialogue",
                "payload": {"target_id": "all", "intent_type": "greeting", "topic": "наблюдение"}
            }
            if scheduler.admit(task_dict):
                admitted_count += 1
        time.sleep(0.01) # Эмулируем минимальную задержку тика
        
    # Без арбитража было бы 66 вызовов.
    # С арбитражем: первый тик пропустит всех 6 (т.к. у них нет истории),
    # но последующие 10 тиков должны подавить всех, т.к. pacing (2 сек) не прошел.
    assert admitted_count <= 6, f"Expected <= 6 admissions, got {admitted_count}"
    print(f"✅ PASS: Pacing & Deduplication. Admitted {admitted_count} out of 66 requests.")

def test_dialogue_cadence():
    """Сценарий: A -> B -> A -> B, а не A -> A -> A."""
    scheduler = SpeechScheduler()
    
    task_a = {"owner_id": "A", "kind": "dialogue", "payload": {"target_id": "B", "intent_type": "talk", "topic": "долг"}}
    task_b = {"owner_id": "B", "kind": "dialogue", "payload": {"target_id": "A", "intent_type": "talk", "topic": "долг"}}
    
    # Тик 1: A говорит
    assert scheduler.admit(task_a) == True, "A should speak"
    
    # Тик 2 (сразу после): B пытается ответить. Должен быть допущен, т.к. его pacing не нарушен.
    assert scheduler.admit(task_b) == True, "B should respond"
    
    # Тик 3 (сразу после): A пытается ответить. Должен быть подавлен (pacing 2 сек).
    assert scheduler.admit(task_a) == False, "A should be denied (pacing)"
    
    print("✅ PASS: Dialogue Cadence A->B allowed, A->A denied.")

def test_duplicate_suppression():
    """Сценарий: один и тот же каузальный контекст не порождает несколько вызовов."""
    scheduler = SpeechScheduler()
    
    task = {"owner_id": "Orm", "kind": "dialogue", "payload": {"target_id": "Goran", "intent_type": "request_service", "topic": "молот"}}
    
    assert scheduler.admit(task) == True, "First request should be admitted"
    assert scheduler.admit(task) == False, "Exact duplicate should be denied"
    
    # Изменился контекст (например, topic сменился на "оплата")
    task_new_context = {"owner_id": "Orm", "kind": "dialogue", "payload": {"target_id": "Goran", "intent_type": "request_service", "topic": "оплата"}}
    # pacing всё ещё не прошел (2 сек), поэтому всё равно отказ
    assert scheduler.admit(task_new_context) == False, "Should be denied due to pacing, even if context changed"
    
    print("✅ PASS: Duplicate suppression and context change.")

if __name__ == "__main__":
    test_pacing_and_deduplication()
    test_dialogue_cadence()
    test_duplicate_suppression()
    print("\nAll SpeechScheduler tests passed!")
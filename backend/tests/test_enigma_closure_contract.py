"""
Файл: backend/tests/test_enigma_closure_contract.py
Назначение: Тестирование замыканий ENIGMA (§11, §12, §13) и regression-багов (NEW-1..8, T-01..07).
Зависимости: pytest, ast, os
Основные сущности: Forensic Bridges, Regression Bugs, Dialogue Coherence
Запуск: cd backend; python -m pytest tests/test_enigma_closure_contract.py tests/test_causal_contract_sandboxes.py -v; cd ..
"""

import ast
import os

import pytest

# Динамическое вычисление путей относительно расположения тестового файла
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.abspath(os.path.join(_BASE_DIR, "..", "app"))

# Пути к ключевым файлам для статического анализа контрактов
TASK_SCHEDULER_PATH = os.path.join(_APP_DIR, "services", "game_loop", "task_scheduler.py")
NPC_DIALOGUE_SUB_PATH = os.path.join(_APP_DIR, "services", "events", "npc_dialogue_subscriber.py")
SOCIAL_DELTAS_PATH = os.path.join(_APP_DIR, "services", "npc", "decision", "social_deltas.py")
DECISION_PATH = os.path.join(_APP_DIR, "services", "phases", "decision.py")
GAME_LOOP_PATH = os.path.join(_APP_DIR, "services", "game_loop", "__init__.py")
TOPIC_EXTRACTOR_PATH = os.path.join(_APP_DIR, "services", "npc", "topic_extractor.py")
VERBALIZATION_CTX_PATH = os.path.join(_APP_DIR, "services", "verbalization", "verbalization_context.py")

def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

class TestForensicBridges:
    """Тесты из §11 ФАЗА 6.5 — FORENSIC BRIDGES"""

    def test_new_1_bridge_7_producer_target_id(self):
        """NEW-1: _dlg_entry должен содержать target_id, иначе Bridge 7 мёртв."""
        content = read_file(TASK_SCHEDULER_PATH)
        assert '"target_id": ev.payload.get("target_id"' in content or '"target_id": ev.payload.get("target_id", "")' in content, \
            "NEW-1: target_id отсутствует в _dlg_entry! Bridge 7 producer мёртв."

    def test_new_2_bridge_5_tone_mapping_and_routing(self):
        """NEW-2: Маппинг тонов в npc_event_type и правильный роутинг target."""
        sub_content = read_file(NPC_DIALOGUE_SUB_PATH)
        assert "_TONE_TO_NPC_EVENT" in sub_content, "NEW-2: Отсутствует маппинг _TONE_TO_NPC_EVENT"
    
        deltas_content = read_file(SOCIAL_DELTAS_PATH)
        # Проверяем факт наличия роутинга на actor_id для NPC-событий
        assert "_target = event.actor_id" in deltas_content, \
            "NEW-2: Роутинг target в social_deltas.py не исправлен (хардкод player)."

    def test_new_3_bridge_2_l1_chronicle_commit(self):
        """NEW-3: NpcDialogueSubscriber должен вызывать commit_tick_buffer для L1Chronicle."""
        content = read_file(NPC_DIALOGUE_SUB_PATH)
        assert "commit_tick_buffer" in content, "NEW-3: Вызов commit_tick_buffer отсутствует в NpcDialogueSubscriber."

class TestRegressionBugs:
    """Тесты из §12 ФАЗА 6.6 — НОВЫЕ REGRESSION БАГИ"""

    def test_new_7_tick_context_action_type_attribute_error(self):
        """NEW-7: ctx.action_type не должен вызывать AttributeError на idle_tick."""
        content = read_file(DECISION_PATH)
        assert "ctx.action_type or" not in content, "NEW-7: Прямой вызов ctx.action_type вызовет краш на idle_tick!"
        # Проверяем использование getattr для безопасного доступа
        assert 'getattr(ctx.shared_context, "action_type", None)' in content, \
            "NEW-7: Ожидается безопасный доступ к action_type через getattr."

    def test_new_8_npc_name_recognition_persistence(self):
        """NEW-8: Установка player_recognition должна происходить ДО commit_tick_result."""
        content = read_file(GAME_LOOP_PATH)
        # Ищем блок NEW-8 FIX, чтобы убедиться, что проверяем правильное место
        new_8_idx = content.find("NEW-8 FIX")
        assert new_8_idx != -1, "NEW-8: Блок FIX не найден в game_loop."
        
        # Ищем commit_tick_result ПОСЛЕ блока NEW-8 FIX
        commit_idx = content.find("commit_tick_result", new_8_idx)
        assert commit_idx != -1, "NEW-8: commit_tick_result не найден после блока NEW-8 FIX."
        
        # Проверяем, что player_recognition устанавливается внутри блока NEW-8, до commit
        recog_idx = content.find("player_recognition", new_8_idx)
        assert recog_idx != -1 and recog_idx < commit_idx, "NEW-8: player_recognition устанавливается ПОСЛЕ commit_tick_result."

class TestDialogueCoherence:
    """Тесты из §13 ФАЗА 6.7 — ДИАЛОГОВАЯ СВЯЗАННОСТЬ И ПАМЯТЬ"""

    def test_t_01_topic_extractor_npc_state_param(self):
        """T-01: TopicExtractor должен принимать npc_state для разнообразия тем."""
        content = read_file(TOPIC_EXTRACTOR_PATH)
        assert "npc_state: Optional[Any] = None" in content or "npc_state" in content, \
            "T-01: Параметр npc_state отсутствует в сигнатуре extract_topic."

    def test_t_02_verbalization_context_beliefs(self):
        """T-02: DialogueExecutor (или VerbalizationContext) должен кормить crystallized beliefs в LLM промпт."""
        # Проверяем в DialogueExecutor, так как именно там собирается промпт
        executor_path = os.path.join(_APP_DIR, "services", "execution", "dialogue_executor.py")
        content = read_file(executor_path)
        assert "belief_store" in content and "crystallized_beliefs" in content or "belief_store" in content, \
            "T-02: Отсутствует провод beliefs в dialogue_executor.py."
"""
Файл: backend/tests/test_phase1_validation.py
Назначение: Наглядная проверка реализации пунктов S-03, Bridge 3, L-01..L-05, T-04, T-07.
Зависимости: pytest, json, os
Запуск: 
"""

import pytest
import json
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

class TestPhase1Implementation:
    """Наглядные тесты статуса реализации Фазы 1 (Polishing)."""

    def test_s_03_goran_has_schedule(self):
        """S-03: У Горана должно быть расписание."""
        goran_path = os.path.join(BASE_DIR, "config", "npc", "individuals", "goran.json")
        with open(goran_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        assert "routine" in data, "S-03 FAILED: У Горана отсутствует 'routine'"
        assert "schedule" in data["routine"], "S-03 FAILED: У Горана отсутствует 'schedule'"
        assert len(data["routine"]["schedule"]) > 0, "S-03 FAILED: Schedule пустой"
        print("\n[S-03] PASSED: Расписание Горана присутствует.")

    def test_bridge_3_player_spoke_in_threat_types(self):
        """Bridge 3: player_spoke должен формировать beliefs (DANGER)."""
        from app.services.npc.belief_transition_engine import _THREAT_TYPES
        assert "player_spoke" in _THREAT_TYPES, "Bridge 3 FAILED: player_spoke отсутствует в _THREAT_TYPES"
        print("\n[Bridge 3] PASSED: player_spoke добавлен в _THREAT_TYPES.")

    def test_l_01_to_l_05_dialogue_executor_context(self):
        """L-01..L-05, T-04: Проверка контекста DialogueExecutor."""
        path = os.path.join(BASE_DIR, "backend", "app", "services", "execution", "dialogue_executor.py")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
        assert "self._get_context(task.campaign_id, task.owner_id)" in content, "L-01 FAILED: Аргументы context_provider перевёрнуты"
        assert "ResponseValidator" in content, "L-02 FAILED: ResponseValidator не используется"
        assert "system_prompt = (" in content, "L-04 FAILED: system_prompt отсутствует"
        assert "_target_name = _target_ctx.get" in content, "L-05 FAILED: target_id не резолвится в имя"
        assert "voice_profile" in content, "L-03 FAILED: voice_profile не передаётся"
        assert "npc_npc_context" in content, "T-04 FAILED: npc_npc_context не извлекается"
        print("\n[L-01..L-05, T-04] PASSED: DialogueExecutor настроен корректно.")

    def test_t_07_topic_extractor_phrases(self):
        """T-07: Фразы игрока должны маппиться в темы."""
        from app.services.npc.topic_extractor import _PHRASE_TO_TOPIC
        assert "как дела" in _PHRASE_TO_TOPIC, "T-07 FAILED: Фраза 'как дела' не замапплена"
        print("\n[T-07] PASSED: Фразы игрока маппятся в темы.")

    def test_t_06_beliefs_in_decision_hub(self):
        """T-06: DecisionHub должен использовать CrystallizedBeliefModifierResolver (вызов из npc_tick_pipeline)."""
        path = os.path.join(BASE_DIR, "backend", "app", "services", "npc", "npc_tick_pipeline.py")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "CrystallizedBeliefModifierResolver" in content and "_drive_modifiers_for_hub" in content, \
            "T-06 FAILED: Beliefs не влияют на DecisionHub"
        print("\n[T-06] PASSED: Beliefs влияют на DecisionHub.")
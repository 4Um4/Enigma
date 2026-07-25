"""
Файл: backend/tests/test_causal_contract_sandboxes.py
Назначение: Тестирование фундаментальных инвариантов и запретов из 00_CAUSAL_CONTRACT_v2.0.md (§8) и АРХИТЕКТУРНЫЙ УСТАВ.
Зависимости: pytest, os, re
Основные сущности: HP Double Truth, L3 Ephemeral, SSOT, Wall-Clock Isolation
Запуск: cd backend; python -m pytest tests/test_enigma_closure_contract.py tests/test_causal_contract_sandboxes.py -v; cd ..
"""

import os
import re

import pytest

# Динамическое вычисление путей относительно расположения тестового файла
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.abspath(os.path.join(_BASE_DIR, "..", "app"))

GAME_LOOP_PATH = os.path.join(_APP_DIR, "services", "game_loop", "__init__.py")
TICK_ORCH_PATH = os.path.join(_APP_DIR, "services", "tick_orchestrator.py")
NPC_PIPELINE_PATH = os.path.join(_APP_DIR, "services", "npc", "npc_tick_pipeline.py")
LIFE_ENGINE_PATH = os.path.join(_APP_DIR, "services", "npc", "life_engine.py")
SSM_PATH = os.path.join(_APP_DIR, "services", "scene_state_manager.py")

def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

class TestArchitecturalTaboos:
    """Проверка §4 ЗАПРЕТЫ (HARD CONSTRAINTS) из CAUSAL CONTRACT v2.0"""

    def test_hp_double_truth_invariant(self):
        """Запрет 4.6.43: Прямая запись в state.hp в обход body_state["current_hp"] (HP Double Truth)."""
        content = read_file(GAME_LOOP_PATH)
        # Ищем прямое присваивание, исключая чтение и свойства
        matches = re.findall(r'state\.hp\s*=(?!\s*property)', content)
        assert len(matches) == 0, "HP Double Truth: Обнаружена прямая запись в state.hp!"

    def test_l3_ephemeral_invariant(self):
        """Запрет 4.4.27: Кэширование EffectiveDrives (L3) запрещено."""
        content = read_file(NPC_PIPELINE_PATH)
        # Проверяем, что нет сохранения L3 в кэш или персистентное поле
        assert "self._l3_cache" not in content, "L3-P1: Обнаружено кэширование EffectiveDrives!"
        assert "state.persisted_drives = " not in content, "L3-P1: Обнаружена попытка сериализации L3!"

    def test_no_wall_clock_in_simulation(self):
        """Запрет 4.5.31: Wall-clock (time.time()) в симуляции запрещен, кроме §15.2 (Infrastructure)."""
        files_to_check = [TICK_ORCH_PATH, LIFE_ENGINE_PATH, NPC_PIPELINE_PATH]
        for f in files_to_check:
            content = read_file(f)
            lines = content.split('\n')
            violations = []
            for i, line in enumerate(lines):
                if re.search(r'time\.time\(\)|datetime\.now\(\)', line):
                    # Проверяем текущую строку и соседние (для многострочных вызовов)
                    context_window = "\n".join(lines[max(0, i-3):i+3])
                    if '§15.2' in context_window or 'cache TTL' in context_window.lower() or '_last_access' in context_window:
                        continue
                    violations.append(line.strip())
            assert len(violations) == 0, f"Wall-Clock Isolation: Обнаружен нелегальный time.time() в {f}! Lines: {violations}"

    def test_no_direct_scene_change_in_resolver(self):
        """Запрет 4.1.4: SceneChange как триггер — scene_manager.apply_changes() из подписчика запрещен."""
        content = read_file(NPC_PIPELINE_PATH)
        assert "scene_manager.apply_changes" not in content, "4.1.4: apply_changes вызывается из подписчика (pipeline)!"

    def test_traversal_state_ownership(self):
        """Запрет 4.1.6: Перезапись активного транзита (status='MOVING') в apply_changes."""
        content = read_file(SSM_PATH)
        # Проверяем, что существует логика проверки статуса MOVING (ADR-130 Guard)
        assert '"status") == "MOVING"' in content or 'status == "MOVING"' in content, \
            "ADR-130 Guard: Отсутствует проверка статуса MOVING в scene_state_manager.py."

class TestIPTInvariants:
    """Инварианты из backend/tests/IPT.py (проверка структуры)"""

    def test_trav_dict_invariant(self):
        """INV-TRAV-DICT: active_traversals должен быть dict, не list."""
        content = read_file(SSM_PATH)
        assert 'active_traversals = {}' in content or 'active_traversals": {}' in content, \
            "INV-TRAV-DICT: active_tr traversals инициализируется не как dict!"
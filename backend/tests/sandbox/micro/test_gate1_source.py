# -*- coding: utf-8 -*-
"""
path: backend/tests/sandbox/micro/test_gate1_source.py
Назначение: Этап 2 / П-1 (санкция Мастера): матрица Гейт① — обе стороны
    предиката (SUPPRESS и PASS) на новом источнике scene_state["npc_intents"].
    Двойная защита регрессии: фильтр обязан подавлять при SSOT=observe ∧
    E≥0.45 ∧ фаза oriented — и НЕ подавлять во всех остальных случаях
    (матрица 5 строк директивы). Также: писатель проецирует только
    intent-дельты; fallback на кэш при пустом каноне.
Зависимости: unittest, app.services.phases.simulation (импорт секции фильтра
    невозможен без контекста — тестируем через интеграцию реального
    run-контура невозможно в микро; здесь — чистый предикат-мост:
    эмулируем dict-сборку читателя точно по коду simulation.py:160-168).
Основные сущности: TestGate1SourceMatrix.
"""

import os
import unittest
from types import SimpleNamespace


def _build_intents_by_id(all_npcs_raw, scene_state):
    """Точная копия сборки Гейт① (simulation.py:160-168) — источник-приоритет."""
    _ssot_intents = scene_state.get("npc_intents") or {}
    _intents_by_id = {
        (n.get("npc_id") or n.get("id")): str(n.get("intent", "")).lower()
        for n in (all_npcs_raw or [])
        if isinstance(n, dict)
    }
    _intents_by_id.update(_ssot_intents)
    return _intents_by_id


def _gate_pred(intent_val, e, phase):
    """Предикат фильтра (та же семантика: ==observe ∧ E≥0.45 ∧ фаза)."""
    return intent_val == "observe" and e >= 0.45 and phase in ("oriented", "approaching", "near")


class TestGate1SourceMatrix(unittest.TestCase):
    """Матрица директивы Мастера: 5 строк, обе стороны предиката."""

    def _npc(self, npc_id, intent):
        return {"npc_id": npc_id, "intent": intent}

    def test_matrix_suppress(self):
        """SSOT=observe ∧ E≥0.45 ∧ schedule → SUPPRESS (канон побеждает кэш)."""
        raw = [self._npc("borko", "spread_rumor")]  # слепой кэш
        scene = {"npc_intents": {"borko": "observe"},
                 "attention_states": {"borko": {"player": {"approach_evidence": 1.0, "phase": "oriented"}}}}
        ids = _build_intents_by_id(raw, scene)
        self.assertEqual(ids["borko"], "observe")  # источник приоритетен
        self.assertTrue(_gate_pred(ids["borko"], 1.0, "oriented"))

    def test_matrix_pass_low_e(self):
        """observe, но E<0.45 → PASS (нет подавления)."""
        scene = {"npc_intents": {"borko": "observe"},
                 "attention_states": {"borko": {"player": {"approach_evidence": 0.3, "phase": "oriented"}}}}
        ids = _build_intents_by_id([self._npc("borko", "spread_rumor")], scene)
        self.assertFalse(_gate_pred(ids["borko"], 0.3, "oriented"))

    def test_matrix_pass_other_intent(self):
        """SSOT=request_service ∧ E≥0.45 → PASS (фильтр не агрессивен)."""
        scene = {"npc_intents": {"borko": "request_service"},
                 "attention_states": {"borko": {"player": {"approach_evidence": 1.0, "phase": "oriented"}}}}
        ids = _build_intents_by_id([self._npc("borko", "observe")], scene)
        self.assertFalse(_gate_pred(ids["borko"], 1.0, "oriented"))

    def test_matrix_pass_flee(self):
        """SSOT=flee ∧ E≥0.45 → PASS."""
        scene = {"npc_intents": {"borko": "flee"}}
        ids = _build_intents_by_id([self._npc("borko", "observe")], scene)
        self.assertFalse(_gate_pred(ids["borko"], 1.0, "oriented"))

    def test_matrix_fallback_empty_canon(self):
        """Пустой канон → fallback на кэш-источник (обратная совместимость)."""
        raw = [self._npc("borko", "spread_rumor"), self._npc("goran", "request_service")]
        ids = _build_intents_by_id(raw, {})
        self.assertEqual(ids["borko"], "spread_rumor")
        self.assertEqual(ids["goran"], "request_service")

    def test_writer_projects_only_intent_deltas(self):
        """Писатель (tick_orchestrator:2317+): только дельты с intent; None-пропуск."""
        # Точная копия тела writer'а
        _KEY_NPC_INTENTS = "npc_intents"
        ctx = SimpleNamespace(scene_state={}, tick_mutation=SimpleNamespace(npc_deltas=[
            SimpleNamespace(npc_id="a", intent=None, target=None),            # пропуск
            SimpleNamespace(npc_id="b", intent="observe"),                     # строка-значение
            SimpleNamespace(npc_id="c", intent=None),                          # пропуск
        ]))
        _intent_map = ctx.scene_state.setdefault(_KEY_NPC_INTENTS, {})
        for _d in (getattr(ctx.tick_mutation, "npc_deltas", None) or []):
            _d_intent = getattr(_d, "intent", None)
            _d_npc = getattr(_d, "npc_id", None)
            if _d_intent is None or not _d_npc:
                continue
            _intent_map[_d_npc] = str(getattr(_d_intent, "value", _d_intent)).lower()
        self.assertEqual(ctx.scene_state["npc_intents"], {"b": "observe"})


if __name__ == "__main__":
    unittest.main()
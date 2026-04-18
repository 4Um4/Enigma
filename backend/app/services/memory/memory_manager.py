"""
R1.1 + R5.3 — MemoryManager.
Фасад всей памяти. Теперь поддерживает создание EventMemory с реальным clarity.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

from app.services.memory import LayeredMemory
from app.services.memory.working_memory import WorkingMemory
from app.services.memory.importance_engine import score_event, apply_decay, DECAY_EVERY
from app.services.memory.relationship_store import RelationshipStore
from app.services.memory.contradiction_resolver import resolve_all

from app.models.npc_state import EventMemory, MemoryStage
from app.services.npc.perception_filter import calculate_clarity

from app.services.memory.resonance_engine import ResonanceEngine


class MemoryManager:
    WORKING_MEMORY_SIZE: int = 20

    def __init__(self, layered_memory: LayeredMemory, data_dir: str = "data") -> None:
        self._layered = layered_memory
        self._working = WorkingMemory(maxlen=self.WORKING_MEMORY_SIZE)
        self._relationships = RelationshipStore(data_dir=data_dir)
        self._tick_counters: Dict[str, int] = {}
        self._resonance = ResonanceEngine()
        # Накопленные черты из ResonanceEngine — фактический NPCIdentityL1 (in-memory)
        # Ключ: f"{campaign_id}:{npc_id}", значение: {trait_name: weight}
        # WRITE: только через apply_identity_weights()
        self._identity_cache: Dict[str, Dict[str, float]] = {}

    @property
    def working_memory(self) -> WorkingMemory:
        return self._working

    # ──────────────────────────────────────────────────────────────────────
    # R5.3 — Новый основной метод создания памяти NPC
    # ──────────────────────────────────────────────────────────────────────
    def create_event_memory(
        self,
        campaign_id: str,
        npc_id: str,
        event: Dict[str, Any],
        scene_state: Dict[str, Any],
        npc_stress: float = 0.0,
        emotion_tag: str = "neutral",
        summary: str = "",
    ) -> EventMemory:
        """
        R5.3 — Создаёт EventMemory с правильно рассчитанным clarity.
        
        Использует perception_filter.calculate_clarity() для реалистичного
        восприятия события NPC (дистанция, освещение, стресс).
        """
        # 1. Расстояние от NPC до события (обычно до игрока)
        from app.services.npc.perception_filter import _npc_distance
        distance = _npc_distance(npc_id, scene_state)

        # 2. Освещение
        light_level = scene_state.get("environment", {}).get("light_level", "dim")

        # 3. Clarity восприятия
        clarity = calculate_clarity(
            distance=distance,
            light_level=light_level,
            npc_stress=npc_stress,
        )

        # 4. Важность события (расширенная версия из R5.3)
        importance = score_event(
            event=event,
            npc_clarity=clarity,
            npc_stress=npc_stress,
            emotion_tag=emotion_tag,
        )


        # 5. Негативные эмоции "прилипают" — медленнее затухают в памяти
        _EMOTION_DECAY_RATE: Dict[str, float] = {
            "angry":    0.03,
            "fearful":  0.03,
            "disgusted":0.03,
            "grateful": 0.07,   # позитив уходит быстрее
            "happy":    0.07,
        }
        decay_rate = _EMOTION_DECAY_RATE.get(emotion_tag, 0.05)

        # §9 Память.md: критические события не забываются (спасение, травма)
        _CRITICAL_IMPORTANCE_THRESHOLD: float = 0.90
        if importance >= _CRITICAL_IMPORTANCE_THRESHOLD:
            decay_rate = 0.005


        # 6. Создаём EventMemory
        mem = EventMemory(
            event_type=event.get("type") or event.get("action_type") or "unknown",
            target_id=event.get("target") or event.get("actor") or "player",
            emotion_tag=emotion_tag,
            day=event.get("day", 0),
            importance=importance,
            clarity=clarity,
            confidence=0.95 if clarity > 0.7 else 0.75,  # начальная уверенность
            decay_rate=decay_rate,
            stage=MemoryStage.FRESH,
            summary=summary,
            npc_id=npc_id,
        )

        # 7. Сохраняем в рабочую память (per-NPC ключ) и layered storage
        self._working.push(f"{campaign_id}:{npc_id}", mem)
        self._layered.write_session_memory(campaign_id, {
            "type": "event_memory",
            "npc_id": npc_id,
            **mem.__dict__,
        })

        return mem

    # ──────────────────────────────────────────────────────────────────────
    # Основные методы записи (используются game_loop.py)
    # ──────────────────────────────────────────────────────────────────────
    def record_event(
        self,
        campaign_id: str,
        event: Dict[str, Any],
    ) -> None:
        """Запись события через score_event. Используется game_loop.py."""
        importance = score_event(event)
        event_with_score = {**event, "importance": importance}
        self._working.push(campaign_id, event_with_score)
        self._layered.write_session_memory(campaign_id, event_with_score)

    def update_relationship(
        self,
        campaign_id: str,
        source: str,
        target: str,
        delta: Dict[str, float],
    ) -> None:
        self._relationships.update(campaign_id, source, target, delta)

    def get_relationships(self, campaign_id: str) -> Dict[str, Any]:
        return self._relationships.get_all(campaign_id)

    def update_beliefs(
        self,
        beliefs: List[Dict[str, Any]],
        new_event: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        return resolve_all(beliefs, new_event)

    def get_weights_for_decision(
        self,
        campaign_id: str,
        npc_id: str,
        target_id: str,
    ) -> Dict[str, float]:
        rel = self._relationships.get_pair(campaign_id, npc_id, target_id)
        recent = self._working.get(f"{campaign_id}:{npc_id}")

        recent_pressure = 0.0
        for e in recent:
            if isinstance(e, dict):
                # Legacy формат
                if e.get("actor") == target_id or e.get("target") == target_id:
                    recent_pressure += e.get("importance", 0.0)
            elif hasattr(e, "npc_id") and e.npc_id == npc_id:
                # EventMemory — учитываем все события этого NPC
                recent_pressure += e.importance

        return {
            "trust": rel.get("trust", 0.0),
            "fear": rel.get("fear", 0.0),
            "debt": rel.get("debt", 0.0),
            "recent_pressure": min(recent_pressure, 100.0),
        }

    def run_decay_if_needed(
        self,
        campaign_id: str,
        current_tick: int,
    ) -> List[Tuple[str, float]]:
        """
        R5.3 — запускает decay и возвращает identity weights от ABSTRACT-переходов.
        Обрабатывает как старый campaign-level буфер, так и per-NPC буферы.
        """
        last = self._tick_counters.get(campaign_id, 0)
        if current_tick - last < DECAY_EVERY:
            return []

        all_weights: List[Tuple[str, float]] = []

        # Старый формат: один буфер на кампанию
        if self._working.get(campaign_id):
            all_weights.extend(self._working.apply_decay(campaign_id, ticks=1))

        # Новый формат: per-NPC буферы (campaign_id:npc_id)
        for key in self._working.get_keys_with_prefix(f"{campaign_id}:"):
            all_weights.extend(self._working.apply_decay(key, ticks=1))

        self._tick_counters[campaign_id] = current_tick
        return all_weights


    def detect_resonance(
        self,
        campaign_id: str,
        actor_id: str = "player",
    ) -> List[Tuple[str, float]]:
        """
        R5.4 — детектирует паттерны в WorkingMemory, возвращает trait deltas.
        Вызывается из python_engines после run_decay_if_needed.
        Возвращает List[(trait_name, delta)] — тот же формат что и run_decay_if_needed.
        """
        events = self._working.get(campaign_id)
        if not events:
            return []

        from app.models.npc_state import EventMemory as _EM
        em_events = [e for e in events if isinstance(e, _EM)]

        patterns = self._resonance.detect(em_events, actor_id=actor_id)
        return [(p.trait_name, p.trait_delta) for p in patterns]


    def apply_identity_weights(
            self,
            campaign_id: str,
            npc_id:      str,
            weights:     List[Tuple[str, float]],
        ) -> None:
            """
            Применяет trait-дельты из ResonanceEngine в identity_cache.
            WRITE: только этот метод пишет в _identity_cache.
            """
            key = f"{campaign_id}:{npc_id}"
            cache = self._identity_cache.setdefault(key, {})
            for trait, delta in weights:
                current = cache.get(trait, 0.0)
                cache[trait] = round(max(0.0, min(1.0, current + delta)), 4)
                

    def get_identity_traits(
        self,
        campaign_id: str,
        npc_id:      str,
    ) -> Dict[str, float]:
        """
        Возвращает накопленные черты NPC из identity_cache.
        READ: для DecisionHub через DecisionView.identity.active_traits
        """
        key = f"{campaign_id}:{npc_id}"
        return dict(self._identity_cache.get(key, {}))      

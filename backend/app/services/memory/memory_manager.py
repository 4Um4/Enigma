"""
R1.1 + R5.3 — MemoryManager.
Фасад всей памяти. Теперь поддерживает создание EventMemory с реальным clarity.
"""

from __future__ import annotations
from typing import Any, Dict, List, Tuple

from app.services.memory import LayeredMemory
from app.services.memory.working_memory import WorkingMemory
from app.services.memory.importance_engine import score_event, apply_decay, DECAY_EVERY
from app.services.memory.relationship_store import RelationshipStore
from app.services.memory.contradiction_resolver import resolve_all

from app.models.npc_state import EventMemory, MemoryStage, NPCState
from app.domain.events import EventDTO
from app.services.npc.perception_filter import calculate_clarity

from app.services.memory.resonance_engine import ResonanceEngine
from app.services.memory.dialogue_session import DialogueSession
from app.core.constants import NARRATIVE_CACHE_MAX


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
        # STM-сессии диалогов. Ключ: campaign_id:npc_id (Закон 4.1.1 — per-NPC)
        self._dialogue_sessions: Dict[str, DialogueSession] = {}

    @property
    def working_memory(self) -> WorkingMemory:
        return self._working

    # ──────────────────────────────────────────────────────────────────────
    # STM: кратковременная память диалога (Этап 1)
    # ──────────────────────────────────────────────────────────────────────

    def get_dialogue_session(self, campaign_id: str, npc_id: str) -> DialogueSession:
        """Возвращает сессию диалога для NPC. Создаёт если нет."""
        key = f"{campaign_id}:{npc_id}"
        if key not in self._dialogue_sessions:
            self._dialogue_sessions[key] = DialogueSession(npc_id=npc_id)
        return self._dialogue_sessions[key]

    def add_dialogue_turn(self, campaign_id: str, npc_id: str, speaker: str, text: str) -> None:
        """Добавляет реплику в STM конкретного NPC."""
        session = self.get_dialogue_session(campaign_id, npc_id)
        session.add(speaker, text)

    def clear_dialogue_session(self, campaign_id: str, npc_id: str) -> None:
        """Очищает STM при завершении диалога (NPC ушёл, смена сцены)."""
        key = f"{campaign_id}:{npc_id}"
        session = self._dialogue_sessions.pop(key, None)
        if session is not None:
            session.clear()

    def clear_all_dialogue_sessions(self, campaign_id: str) -> None:
        """Очищает все STM-сессии кампании — игрок ушёл из локации."""
        keys_to_remove = [k for k in self._dialogue_sessions if k.startswith(f"{campaign_id}:")]
        for key in keys_to_remove:
            self._dialogue_sessions.pop(key)

    def get_stm_prompt_block(self, campaign_id: str, npc_id: str) -> str:
        """Возвращает текстуализацию STM для промпта. Пустую строку если нет сессии."""
        key = f"{campaign_id}:{npc_id}"
        session = self._dialogue_sessions.get(key)
        if session is None:
            return ""
        return session.to_prompt_block()

    # ──────────────────────────────────────────────────────────────────────
    # EventBus и фазовая модель
    # ──────────────────────────────────────────────────────────────────────
    # GameEvent.publish() — Фаза 2 (вход в систему, Закон 5.1).
    # MemoryManager.apply() — Фаза 3 (обработка для конкретного NPC).
    # Subscribe невозможен: GameEvent не содержит npc_state,
    # а npc_state доступен только после Фазы 2.
    # Поэтому apply() вызывается напрямую из game_loop после NPC-цикла.

    # ──────────────────────────────────────────────────────────────────────
    # Единственная точка входа события в память (Закон 4.1.2)
    # Фаза 3 Tick Orchestrator: EventDTO → обновлённый NPCState
    # ──────────────────────────────────────────────────────────────────────
    def apply(
        self,
        event: EventDTO,
        npc_state: NPCState,
        *,
        campaign_id: str,
    ) -> NPCState:
        """Принимает EventDTO, создаёт EventMemory, обновляет narrative_cache.
        
        Заменяет прямые вызовы create_event_memory + ручную запись
        в narrative_cache из game_loop.py (нарушение 4.1.2).
        """
        payload = event.payload
        npc_id = payload.get("npc_id", "")

        # 1. Clarity восприятия (расстояние, свет, стресс NPC)
        scene_state = payload.get("scene_state", {})
        from app.services.npc.perception_filter import _npc_distance
        distance = _npc_distance(npc_id, scene_state)
        light_level = scene_state.get("environment", {}).get("light_level", "dim")
        npc_stress = payload.get("npc_stress", getattr(npc_state, "stress", 0.0))

        clarity = calculate_clarity(
            distance=distance,
            light_level=light_level,
            npc_stress=npc_stress,
        )

        # 2. Важность события
        emotion_tag = payload.get("emotion_tag", "neutral")
        importance = payload.get("importance")
        if importance is None:
            importance = score_event(
                event={"type": event.type, **payload},
                npc_clarity=clarity,
                npc_stress=npc_stress,
                emotion_tag=emotion_tag,
            )

        # 3. Decay rate: негативные эмоции "прилипают"
        _EMOTION_DECAY_RATE: dict[str, float] = {
            "angry": 0.03, "fearful": 0.03, "disgusted": 0.03,
            "grateful": 0.07, "happy": 0.07,
        }
        decay_rate = _EMOTION_DECAY_RATE.get(emotion_tag, 0.05)
        if importance >= 0.90:
            decay_rate = 0.005

        # 4. Создаём EventMemory
        mem = EventMemory(
            event_type=event.type,
            target_id=payload.get("target_id", event.source),
            emotion_tag=emotion_tag,
            day=payload.get("day", 0),
            importance=importance,
            clarity=clarity,
            confidence=0.95 if clarity > 0.7 else 0.75,
            decay_rate=decay_rate,
            stage=MemoryStage.FRESH,
            summary=payload.get("summary", ""),
            npc_id=npc_id,
        )

        # 5. STM: per-NPC ключ (Закон 4.1.1)
        self._working.push(f"{campaign_id}:{npc_id}", mem)

        # 6. narrative_cache — ТОЛЬКО через MemoryManager (Закон 4.1.2)
        cache = list(npc_state.narrative_cache)
        cache.append(mem)
        cache.sort(key=lambda f: f.importance, reverse=True)
        npc_state.narrative_cache = tuple(cache[:NARRATIVE_CACHE_MAX])

        return npc_state

    # ──────────────────────────────────────────────────────────────────────
    # Recall — поиск в памяти (Этап 3)
    # Чистая функция от narrative_cache — не лезет в хранилища.
    # ──────────────────────────────────────────────────────────────────────
    def recall(
        self,
        narrative_cache: Tuple[EventMemory, ...],
        *,
        trigger_tags: Tuple[str, ...] = (),
        pressure: int = 0,
        limit: int = 3,
    ) -> List[EventMemory]:
        """Ищет релевантные воспоминания из narrative_cache.

        Два режима:
        1. Триггерный: тег из trigger_tags совпал → accessibility не важен,
           сортировка по importance (Этап 5: секреты раскроются позже).
        2. Случайный: accessibility > 0.2 → сортировка по importance × accessibility.

        pressure зарезервирован для Этапа 5 (discovery_check секретов).
        """
        if not narrative_cache:
            return []

        # Фильтруем забытые
        alive = [m for m in narrative_cache if not m.is_forgotten]
        if not alive:
            return []

        # Триггерный поиск: хотя бы один тег совпал
        triggered: List[EventMemory] = []
        if trigger_tags:
            _tag_set = set(trigger_tags)
            for m in alive:
                if _tag_set.intersection(m.tags):
                    triggered.append(m)

        if triggered:
            # Сортировка по importance — самые значимые триггеры первые
            triggered.sort(key=lambda m: m.importance, reverse=True)
            return triggered[:limit]

        # Случайный recall: только доступные воспоминания
        accessible = [m for m in alive if m.accessibility > 0.2]
        if not accessible:
            return []

        # Сортировка: importance × accessibility — баланс значимости и свежести
        accessible.sort(
            key=lambda m: m.importance * m.accessibility,
            reverse=True,
        )
        return accessible[:limit]

    # ──────────────────────────────────────────────────────────────────────
    # Persistence — единая точка записи в хранилище (Закон 4.1.2)
    # game_loop не вызывает layered_memory напрямую.
    # ──────────────────────────────────────────────────────────────────────
    def persist_world_canon(
        self,
        world_id: str,
        *,
        campaign_id: str,
        source: str,
        payload: Any,
    ) -> str:
        """Запись лора мира в канон. Вызывается при load_campaign."""
        return self._layered.write_world_canon(
            world_id,
            {"campaign_id": campaign_id, "source": source, "payload": payload},
        )

    def persist_campaign_event(
        self,
        campaign_id: str,
        *,
        event: str,
        world_id: str,
        data: Dict[str, Any],
    ) -> str:
        """Запись системного события кампании (load, save, etc)."""
        return self._layered.write_campaign_memory(
            campaign_id,
            {"event": event, "world_id": world_id, **data},
        )

    def persist_npc_note(
        self,
        campaign_id: str,
        *,
        note: str,
        source: str,
    ) -> str:
        """Запись заметки об NPC в журнал кампании."""
        return self._layered.write_npc_memory(
            campaign_id,
            {"note": note, "source": source},
        )

    def read_campaign_history(
        self,
        campaign_id: str,
        *,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """Чтение журнала кампании. Единственная точка чтения из game_loop."""
        return self._layered.read_campaign_memory(campaign_id, limit=limit)

    def persist_campaign_data(
        self,
        campaign_id: str,
        payload: Dict[str, Any],
    ) -> str:
        """Generic запись в журнал кампании. Для специфических случаев
        (DM-ответ, системное событие) использовать именованные методы."""
        return self._layered.write_campaign_memory(campaign_id, payload)

    def persist_dm_response(
        self,
        campaign_id: str,
        *,
        world_id: str,
        location: str,
        actions: List[Any],
        dm_text: str,
    ) -> str:
        """Запись DM-ответа в журнал кампании. Возвращает ID записи."""
        return self._layered.write_campaign_memory(
            campaign_id,
            {
                "world_id": world_id,
                "location": location,
                "actions":  actions,
                "dm":       dm_text,
            },
        )

    # ──────────────────────────────────────────────────────────────────────
    # Основные методы записи (используются game_loop.py) — ЛЕГАСИ, мигрируют на apply()
    # ──────────────────────────────────────────────────────────────────────
    
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

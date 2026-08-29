from __future__ import annotations

# backend\app\services\memory\memory_manager.py
"""
R1.1 + R5.3 — MemoryManager.
Фасад всей памяти. Теперь поддерживает создание EventMemory с реальным clarity.


"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.services.spatial.spatial_query_service import SpatialQueryService

from app.core.constants import DECAY_EVERY, NARRATIVE_CACHE_MAX
from app.domain.events import CONTRACT_TAGS, EventDTO
from app.models.npc_state import DiscoveryCrack, EventMemory, MemoryStage, NPCState
from app.services.memory import LayeredMemory
from app.services.memory.contradiction_resolver import resolve_all
from app.services.memory.dialogue_consolidator import DialogueConsolidator
from app.services.memory.dialogue_session import DialogueSession
from app.services.memory.importance_engine import score_event
from app.services.memory.promotion_engine import MemoryPromotionEngine
from app.services.memory.relationship_store import RelationshipStore
from app.services.memory.resonance_engine import ResonanceEngine
from app.services.memory.working_memory import WorkingMemory
from app.services.npc.perception_filter import calculate_clarity


class MemoryManager:
    WORKING_MEMORY_SIZE: int = 20

    def __init__(self, layered_memory: LayeredMemory, data_dir: str = "data") -> None:
        self._layered = layered_memory
        # V8-MEM-16 FIX: threading.RLock для защиты _identity_cache от race condition
        import threading
        self._identity_lock = threading.RLock()
        self._working = WorkingMemory(maxlen=self.WORKING_MEMORY_SIZE)
        self._relationships = RelationshipStore(data_dir=data_dir)
        # M1b.2.3 (ADR-O-371): write-фасад стора — единый write-маршрут (D2):
        # все обёрточные записи отношений идут через RelationshipWriteGate;
        # на cutover (M1b.4) гейт централизованно получит v2-backend.
        from app.services.social.relationship_write_gate import RelationshipWriteGate
        self._relationship_write_gate = RelationshipWriteGate(self._relationships)
        self._tick_counters: Dict[str, int] = {}
        self._resonance = ResonanceEngine()
        # Накопленные черты из ResonanceEngine — фактический NPCIdentityL1 (in-memory)
        # Ключ: f"{campaign_id}:{npc_id}", значение: {trait_name: weight}
        # WRITE: только через apply_identity_weights()
        # V8-MEM-7 FIX: Загружаем identity_cache из SQLite/JSON при старте
        # Safe call: SqliteMemoryStore может не иметь load_state (legacy gap)
        if hasattr(self._layered.store, "load_state"):
            self._identity_cache: Dict[str, Dict[str, float]] = self._layered.store.load_state("identity_cache")
        else:
            self._identity_cache: Dict[str, Dict[str, float]] = {}
        # STM-сессии диалогов. Ключ: campaign_id:npc_id (Закон 4.1.1 — per-NPC)
        self._dialogue_sessions: Dict[str, DialogueSession] = {}

        # BUG-DL-06: Буфер отложенных диалоговых событий для записи в L2 (narrative_cache).
        # Заполняется в Фазе 6 (NpcDialogueSubscriber), опустошается в Фазе 3 следующего тика.
        self._pending_dialogue_memories: List[EventDTO] = []

        # BUG-DL-07: Экземпляр DialogueConsolidator для суммаризации STM перед очисткой.
        self._dialogue_consolidator = DialogueConsolidator()

    @property
    def working_memory(self) -> WorkingMemory:
        return self._working

    # ──────────────────────────────────────────────────────────────────────
    # STM: кратковременная память диалога (Этап 1)
    # ──────────────────────────────────────────────────────────────────────

    def get_dialogue_session(self, campaign_id: str, npc_id: str, partner_id: str = "player") -> DialogueSession:
        """Возвращает сессию диалога для NPC. Создаёт если нет."""
        # V8-DLG-13 FIX: Используем сортированный ключ для изоляции пар A↔B от A↔C
        pair_key = tuple(sorted((npc_id, partner_id)))
        key = f"{campaign_id}:{pair_key[0]}:{pair_key[1]}"
        if key not in self._dialogue_sessions:
            self._dialogue_sessions[key] = DialogueSession(npc_id=npc_id, partner_id=partner_id)
        return self._dialogue_sessions[key]

    def get_dialogue_session_pair(self, campaign_id: str, npc_a: str, npc_b: str) -> DialogueSession:
        """V8-DLG-13: Явный метод для получения пер-парной сессии."""
        return self.get_dialogue_session(campaign_id, npc_a, npc_b)

    def add_dialogue_turn(
        self, campaign_id: str, npc_id: str, speaker: str, text: str,
        target_id: str = "", intent: str = "", tone: str = "", tick: int = 0,
        partner_id: str = "player"
    ) -> None:
        """Добавляет реплику в STM конкретного NPC."""
        session = self.get_dialogue_session(campaign_id, npc_id, partner_id)
        session.add_turn(
            speaker=speaker, text=text, target_id=target_id,
            intent=intent, tone=tone, tick=tick
        )

    def clear_dialogue_session(self, campaign_id: str, npc_id: str, partner_id: str = "player") -> None:
        """Очищает STM при завершении диалога (NPC ушёл, смена сцены)."""
        # BUG-DLG-007 FIX: Используем симметричный сортированный ключ, как в get_dialogue_session.
        pair_key = tuple(sorted((npc_id, partner_id)))
        key = f"{campaign_id}:{pair_key[0]}:{pair_key[1]}"
        session = self._dialogue_sessions.get(key)
        if session is None:
            return

        # BUG-DL-07: Consolidation в EventMemory перед discard
        if summary := self._dialogue_consolidator.consolidate(session):
            self._pending_dialogue_memories.append(
                EventDTO.create(
                    event_type="dialogue_consolidated",
                    source=npc_id,
                    payload={
                        "npc_id": npc_id,
                        "text": summary,
                        "topic": session.topic or "unknown",
                        "scene_state": {},
                        "npc_stress": 0.0,
                    },
                    visibility="private",
                    radius=0.0,
                    persistence_level="session",
                )
            )

        session.clear()
        self._dialogue_sessions.pop(key, None)

    def clear_all_dialogue_sessions(self, campaign_id: str) -> None:
        """Очищает все STM-сессии кампании — игрок ушёл из локации."""
        keys_to_remove = [
            k for k in self._dialogue_sessions if k.startswith(f"{campaign_id}:")
        ]
        for key in keys_to_remove:
            # BUG-DLG-008 FIX: Извлекаем npc_a и npc_b из ключа "campaign_id:npc_a:npc_b"
            parts = key.split(":")
            if len(parts) >= 3:
                _, npc_a, npc_b = parts[0], parts[1], parts[2]
                self.clear_dialogue_session(campaign_id, npc_a, npc_b)
            else:
                self._dialogue_sessions.pop(key, None)

    def add_pending_dialogue_memory(self, event: EventDTO) -> None:
        """Добавляет событие диалога в буфер отложенной записи в L2."""
        self._pending_dialogue_memories.append(event)

    def drain_pending_dialogue_memories(self) -> List[EventDTO]:
        """Извлекает и очищает буфер отложенных диалоговых событий."""
        if not self._pending_dialogue_memories:
            return []
        drained = self._pending_dialogue_memories
        self._pending_dialogue_memories = []
        return drained

    def get_stm_prompt_block(self, campaign_id: str, npc_id: str, partner_id: str = "player") -> str:
        """Возвращает текстуализацию STM для промпта. Пустую строку если нет сессии."""
        # V8-DLG-13 FIX: Используем get_dialogue_session для консистентности ключей
        session = self.get_dialogue_session(campaign_id, npc_id, partner_id)
        return session.to_prompt_block()

    def get_stm_prompt_block_pair(self, campaign_id: str, npc_a: str, npc_b: str) -> str:
        """Возвращает STM-блок для пары NPC (собственная нить спикера)."""
        return self.get_stm_prompt_block(campaign_id, npc_a, partner_id=npc_b)

    # ──────────────────────────────────────────────────────────────────────
    # EventBus и фазовая модель
    # ──────────────────────────────────────────────────────────────────────
    # EventBus.publish() — Фаза 2 (вход в систему, Закон 5.1).
    # MemoryManager.apply() — Фаза 3 (обработка для конкретного NPC).
    # Subscribe невозможен: EventDTO не содержит npc_state,
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
        spatial_query: Optional["SpatialQueryService"] = None,
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

        distance = _npc_distance(npc_id, spatial_query) if spatial_query else 99.9
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
            )

        # ADR-O-206: Causal Purity. Decay rate определяется важностью (функцией ошибки модели),
        # а не оракулом EmotionTag. Чем важнее событие (больше ошибка), тем медленнее забывается.
        if importance >= 0.90:
            decay_rate = 0.005  # Структурный шок
        elif importance > 0.6:
            decay_rate = 0.03  # Значимая коррекция модели
        else:
            decay_rate = 0.05  # Предсказуемое событие

        # Этап 6: обязательства забываются медленнее (×0.4 от базового)
        _contract_tag_pending = payload.get("contract_tag", "")
        if _contract_tag_pending in CONTRACT_TAGS:
            decay_rate *= 0.4

        # ADR-O-206: Causal Purity. Удаляем наивную классификацию на основе EmotionTag.
        # Семантическую окраску (угроза/социум/аномалия) определяет EventSemanticTagger ниже.
        # Оставляем только базовый механический тег.
        _tags: list[str] = [event.type]

        # R8: EventSemanticTagger — социальный смысл события (изолирован от downstream)
        from app.services.memory.event_semantic_tagger import EventSemanticTagger

        _semantic_tags = EventSemanticTagger().tag(
            event_type=event.type,
            actor_id=event.source or "",
            intensity=getattr(event, "intensity", 1.0),
        )
        _tags.extend(_semantic_tags)

        # 4b. Этап 6: тег контракта — обязательства забываются медленнее
        contract_tag = payload.get("contract_tag", "")
        if contract_tag in CONTRACT_TAGS:
            _tags.append(contract_tag)

        # 5. Создаём EventMemory
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
            # Сохраняем сырую реальность (raw_text), смысл кристаллизуется в LLM
            summary=payload.get("summary")
            or payload.get("raw_input")
            or payload.get("content", ""),
            npc_id=npc_id,
            tags=tuple(_tags),
            is_secret=payload.get("is_secret", False),
            actor_id=event.source or "",
            known_by=tuple(payload.get("known_by", ())),
            hidden_from=tuple(payload.get("hidden_from", ())),
            fulfilled=payload.get("fulfilled", False),
            contract_ref=payload.get("contract_ref", ""),
        )

        # 6. STM: per-NPC ключ (Закон 4.1.1)
        self._working.push(f"{campaign_id}:{npc_id}", mem)

        # 7. narrative_cache — ТОЛЬКО через MemoryManager (Закон 4.1.2)
        cache = list(npc_state.narrative_cache)
        cache.append(mem)
        cache.sort(key=lambda f: f.importance, reverse=True)
        object.__setattr__(npc_state, "narrative_cache", tuple(cache[:NARRATIVE_CACHE_MAX]))

        # 8. SQLite persistence — runtime truth (Закон 4.2.1)
        # event.id как mem_id — трассируемая связь EventDTO → EventMemory
        _store = self._layered.store
        _save_mem = getattr(_store, "save_event_memory", None)  # noqa: ENIGMA002
        if callable(_save_mem):
            _save_mem(
                mem_id=str(event.id),
                campaign_id=campaign_id,
                mem_data=mem,
            )

        # C-16 FIX: assess_beliefs был мёртвым кодом (результат не записывался).
        # Убран, чтобы не вводить в заблуждение. Реально пишет только BeliefTransitionEngine.

        return npc_state

    # ──────────────────────────────────────────────────────────────────────
    # SQLite → RAM: восстановление narrative_cache при старте (Закон 4.2.1)
    # ──────────────────────────────────────────────────────────────────────

    def load_narrative_from_sqlite(
        self,
        campaign_id: str,
        npc_id: str,
    ) -> Optional[Tuple[EventMemory, ...]]:
        """Загружает narrative_cache из SQLite. Возвращает None если нет данных —
        вызывающая сторона fallback'ится на JSON (обратная совместимость)."""
        _store = self._layered.store
        _load_mems = getattr(_store, "load_event_memories", None)  # noqa: ENIGMA002
        if not callable(_load_mems):
            return None

        raw_list: Any = _load_mems(campaign_id, npc_id) or []
        if not raw_list:
            return None

        _result: List[EventMemory] = []
        for _d in raw_list:
            # stage хранится как строка, модель ждёт MemoryStage enum
            _stage_str = _d.pop("stage", "FRESH")
            try:
                _d["stage"] = MemoryStage(_stage_str)
            except ValueError:
                _d["stage"] = MemoryStage.FRESH
            # created_at, id, campaign_id — не поля EventMemory, убираем
            _d.pop("created_at", None)
            _d.pop("id", None)
            _d.pop("campaign_id", None)

            try:
                _mem = EventMemory(**_d)
                # Decay при загрузке — NPC загружается раз в тик
                _mem = _mem.decayed(game_days=1.0)
                if not _mem.is_forgotten:
                    _result.append(_mem)
            except Exception as e:
                logger.warning(
                    f"[MEMORY] Failed to restore EventMemory for {npc_id}: {e}"
                )

        # Сортировка по importance и лимит — как в apply()
        _result.sort(key=lambda f: f.importance, reverse=True)
        return tuple(_result[:NARRATIVE_CACHE_MAX])

    # ──────────────────────────────────────────────────────────────────────
    # Pressure — доступ к счётчику DialogueSession (Этап 5 prep)
    # ──────────────────────────────────────────────────────────────────────
    def get_recent_speech_all_npcs(self, campaign_id: str, limit: int = 5) -> List[str]:
        """Собирает последние реплики из всех NPC-сессий кампании для DM."""
        lines: List[str] = []
        _session_count = 0
        for key, session in self._dialogue_sessions.items():
            if not key.startswith(f"{campaign_id}:"):
                continue
            _session_count += 1
            for turn in session.buffer:
                speaker = "Игрок" if turn.speaker == "player" else turn.speaker
                lines.append(f"{speaker}: {turn.text}")
        logger.debug(
            f"[STM_READ] campaign={campaign_id} sessions={_session_count} total_turns={len(lines)} keys={list(self._dialogue_sessions.keys())}"
        )
        return lines[-limit:]

    def get_dialogue_pressure(self, campaign_id: str, npc_id: str) -> int:
        """Давление по текущей теме диалога."""
        session = self.get_dialogue_session(campaign_id, npc_id)
        return session.get_pressure(session.topic) if session else 0

    # ──────────────────────────────────────────────────────────────────────
    # Suppressed secrets — то что NPC помнит но скрывает (Этап 5.5)
    # ──────────────────────────────────────────────────────────────────────
    def get_suppressed_secrets(
        self,
        narrative_cache: Tuple[EventMemory, ...],
        hidden_from_id: str = "player",
    ) -> List[EventMemory]:
        """Секреты которые NPC помнит но не раскрыл caller."""
        return [
            m
            for m in narrative_cache
            if m.is_secret and hidden_from_id in m.hidden_from and not m.is_forgotten
        ]

    # ──────────────────────────────────────────────────────────────────────
    # Discovery — раскрытие секретов под давлением (Этап 5.2)
    # ──────────────────────────────────────────────────────────────────────
    _PRESSURE_STRENGTH: dict[str, float] = {
        "physical": 0.45,  # пытки, избиение — самый сильный эффект
        "threat": 0.35,  # прямая угроза
        "intimidation": 0.20,  # психологическое давление
        "question": 0.02,  # нудные вопросы — почти ничего
    }

    def discovery_check(
        self,
        memory: EventMemory,
        *,
        pressure_type: str = "question",
        pressure_count: int = 0,
        npc_stress: float = 0.0,
        npc_trust: float = 0.0,
    ) -> DiscoveryCrack:
        """Определяет уровень трещины в секрете под давлением.

        Формула: resistance - pressure_effect - stress_help
        - resistance = importance * 0.8 (глубокий секрет сложнее раскрыть)
        - pressure_effect зависит от ТИПА давления, не от количества вопросов
        - повторение одного типа даёт убывающий бонус (×1.1, ×1.2, max ×1.5)
        - низкий trust → упрямство (+resistance)
        - высокий стресс → хуже врёт (-resistance, но не auto-reveal)
        """
        strength = self._PRESSURE_STRENGTH.get(pressure_type, 0.0)
        if pressure_count > 1:
            strength *= min(1.0 + (pressure_count - 1) * 0.1, 1.5)

        resistance = memory.importance * 0.8
        trust_modifier = max(0.0, -npc_trust) * 0.15 if npc_trust < 0 else 0.0
        stress_modifier = (
            max(0.0, (npc_stress - 0.8)) * 0.15 if npc_stress > 0.8 else 0.0
        )

        total = resistance + trust_modifier - strength - stress_modifier

        if total > 0.5:
            return DiscoveryCrack.NONE
        if total > 0.2:
            return DiscoveryCrack.CRACK
        return DiscoveryCrack.PARTIAL if total > -0.1 else DiscoveryCrack.BROKEN

    def assess_secrets_under_pressure(
        self,
        narrative_cache: Tuple[EventMemory, ...],
        *,
        hidden_from_id: str = "player",
        pressure_type: str = "question",
        pressure_count: int = 0,
        npc_stress: float = 0.0,
        npc_trust: float = 0.0,
    ) -> List[Tuple[EventMemory, DiscoveryCrack]]:
        """Проверяет все секреты под давлением, возвращает треснувшие."""
        result: List[Tuple[EventMemory, DiscoveryCrack]] = []
        for m in narrative_cache:
            if not m.is_secret or m.is_forgotten:
                continue
            if hidden_from_id not in m.hidden_from:
                continue
            crack = self.discovery_check(
                m,
                pressure_type=pressure_type,
                pressure_count=pressure_count,
                npc_stress=npc_stress,
                npc_trust=npc_trust,
            )
            if crack != DiscoveryCrack.NONE:
                result.append((m, crack))
        return result

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
        hidden_from_id: str = "",
        npc_stress: float = 0.0,
        limit: int = 3,
        target_npc_id: str = "",
    ) -> List[EventMemory]:
        """Ищет релевантные воспоминания из narrative_cache.

        Три режима:
        1. Триггерный: тег совпал → сортировка по importance.
        2. По целевому NPC: target_npc_id совпал с target_id → сортировка по importance.
        3. Случайный: accessibility > 0.2 → сортировка по importance × accessibility.

        Секреты ВСЕГДА фильтруются из recall.
        Раскрытие секретов — через assess_secrets_under_pressure() отдельно.
        """
        if not narrative_cache:
            return []

        alive = [m for m in narrative_cache if not m.is_forgotten]
        if hidden_from_id:
            alive = [
                m
                for m in alive
                if not (m.is_secret and hidden_from_id in m.hidden_from)
            ]
        if not alive:
            return []

        # Триггерный поиск: хотя бы один тег совпал
        triggered: List[EventMemory] = []
        if trigger_tags:
            _tag_set = set(trigger_tags)
            triggered.extend(m for m in alive if _tag_set.intersection(m.tags))

        if triggered:
            # Сортировка по importance — самые значимые триггеры первые
            triggered.sort(key=lambda m: m.importance, reverse=True)
            return triggered[:limit]

        # Этап 7: поиск памяти о конкретном NPC (NPC-NPC взаимодействия)
        if target_npc_id:
            if npc_memories := [m for m in alive if m.target_id == target_npc_id]:
                npc_memories.sort(key=lambda m: m.importance, reverse=True)
                return npc_memories[:limit]

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
    # Этап 6: контракты и обязательства
    # ──────────────────────────────────────────────────────────────────────
    def get_unfulfilled_contracts(
        self,
        narrative_cache: Tuple[EventMemory, ...],
        *,
        tag_filter: Tuple[str, ...] = (),
    ) -> List[EventMemory]:
        """Возвращает невыполненные обязательства из narrative_cache.

        Фильтрует по тегам из CONTRACT_TAGS (promise_given, promise_received, debt).
        fulfilled=True — исключается (обязательство выполнено).
        Сортировка: importance DESC — самые pressing первые.
        """
        from app.domain.events import CONTRACT_TAGS

        _filter = set(tag_filter) if tag_filter else CONTRACT_TAGS
        result = [
            m
            for m in narrative_cache
            if not m.is_forgotten and not m.fulfilled and _filter.intersection(m.tags)
        ]
        result.sort(key=lambda m: m.importance, reverse=True)
        return result

    # ──────────────────────────────────────────────────────────────────────
    # Этап 9: сжатие памяти (Закон 4.1.3 — отдельный класс)
    # ──────────────────────────────────────────────────────────────────────
    def compress_narrative_cache(
        self,
        narrative_cache: Tuple[EventMemory, ...],
    ) -> Tuple[EventMemory, ...]:
        """Сжимает группу похожих событий в одну абстракцию.

        Вызывается после decay — события уже потеряли importance.
        Возвращает новый кортеж narrative_cache с заменёнными группами.
        """
        engine = MemoryPromotionEngine()
        results = engine.compress(narrative_cache)

        if not results:
            return narrative_cache

        # Собираем ключи событий, которые были сжаты
        _removed_keys: set = set()
        compressed_mems: List[Any] = []
        for r in results:
            _removed_keys.update(r.removed_ids)
            compressed_mems.append(r.compressed)

        # Строим новый кэш: не сжатые + сжатые абстракции
        # Ключ = sequence_id (EventMemory не имеет UUID)
        kept = [
            m for m in narrative_cache if f"seq_{m.sequence_id}" not in _removed_keys
        ]
        new_cache = kept + compressed_mems
        new_cache.sort(key=lambda m: m.importance, reverse=True)
        return tuple(new_cache)

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
                "actions": actions,
                "dm": dm_text,
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
        # M1b.2.3: делегация гейту (D2). Поведение идентично — гейт валидирует
        # вход (whitelist/NaN) и зовёт тот же backend update(); сатурация
        # выполняется стором (D3-паритет доказан сеткой M1b.2.0).
        self._relationship_write_gate.apply(campaign_id, source, target, delta, cause="memory_manager:update_relationship")

    def get_relationships(self, campaign_id: str) -> Dict[str, Any]:
        return self._relationships.get_all(campaign_id)

    def update_beliefs(
        self,
        beliefs: List[Dict[str, Any]],
        new_event: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        _result = resolve_all(beliefs, new_event)
        # V8-FIX: resolve_all возвращает кортеж (beliefs, resolved), возвращаем первый элемент
        return _result[0] if isinstance(_result, tuple) else _result

    def get_weights_for_decision(
        self,
        campaign_id: str,
        npc_id: str,
        target_ids: List[str],
    ) -> Dict[str, Dict[str, float]]:
        """S128 FIX: Возвращает граф отношений для всех target_ids.
        Шкала: -100.0 .. 100.0 (нормализация выполняется в DecisionHub).
        """
        graph_weights = {}
        for tid in target_ids:
            rel = self._relationships.get_pair(campaign_id, npc_id, tid)
            recent = self._working.get(f"{campaign_id}:{npc_id}")

            recent_pressure = 0.0
            for e in recent:
                if isinstance(e, dict):
                    if e.get("actor") == tid or e.get("target") == tid:
                        recent_pressure += e.get("importance", 0.0)
                # V8-MEM-5 FIX: Фильтруем по target_id или actor_id, а не по npc_id
                elif (hasattr(e, "target_id") and e.target_id == tid) or (hasattr(e, "actor_id") and e.actor_id == tid):
                    recent_pressure += e.importance

            graph_weights[tid] = {
                "trust": rel.get("trust", 0.0),
                "fear": rel.get("fear", 0.0),
                "debt": rel.get("debt", 0.0),
                "recent_pressure": min(recent_pressure, 100.0),
            }
        return graph_weights

    def run_decay_if_needed(
        self,
        campaign_id: str,
        current_tick: int,
        game_days: float = 1.0,
    ) -> List[Tuple[str, float]]:
        """
        R5.3 + Этап 8 — запускает decay по игровым дням, возвращает identity weights.
        Триггер: раз в DECAY_EVERY тиков (частота вызова не меняется),
        но magnitude decay считается в game_days, не в тиках.
        """
        last = self._tick_counters.get(campaign_id, 0)
        if current_tick - last < DECAY_EVERY:
            return []

        all_weights: List[Tuple[str, float]] = []

        # Старый формат: один буфер на кампанию
        if self._working.get(campaign_id):
            all_weights.extend(
                self._working.apply_decay(campaign_id, game_days=game_days)
            )

        # Новый формат: per-NPC буферы (campaign_id:npc_id)
        for key in self._working.get_keys_with_prefix(f"{campaign_id}:"):
            all_weights.extend(self._working.apply_decay(key, game_days=game_days))

        self._tick_counters[campaign_id] = current_tick
        return all_weights

    def detect_resonance(
        self,
        campaign_id: str,
        npc_id: str,
        actor_id: str = "player",
    ) -> List[Tuple[str, float]]:
        """
        R5.4 — детектирует паттерны в WorkingMemory, возвращает trait deltas.
        Вызывается из python_engines после run_decay_if_needed.
        Возвращает List[(trait_name, delta)] — тот же формат что и run_decay_if_needed.
        """
        # V8-MEM-13 FIX: Фильтруем буфер по npc_id, а не по всей кампании
        key = f"{campaign_id}:{npc_id}"
        events = self._working.get(key)
        if not events:
            return []

        from app.models.npc_state import EventMemory as _EM

        em_events = [e for e in events if isinstance(e, _EM)]

        patterns = self._resonance.detect(em_events, actor_id=actor_id)
        return [(p.trait_name, p.trait_delta) for p in patterns]

    def apply_identity_weights(
        self,
        campaign_id: str,
        npc_id: str,
        weights: List[Tuple[str, float]],
    ) -> None:
        """
        Применяет trait-дельты из ResonanceEngine в identity_cache.
        WRITE: только этот метод пишет в _identity_cache.
        """
        key = f"{campaign_id}:{npc_id}"
        # V8-MEM-16 FIX: Обёрнут в RLock для безопасного read-modify-write
        with self._identity_lock:
            cache = self._identity_cache.setdefault(key, {})
            for trait, delta in weights:
                current = cache.get(trait, 0.0)
                cache[trait] = round(max(0.0, min(1.0, current + delta)), 4)

            # V8-MEM-7 FIX: Персистируем обновлённый identity_cache
            self._layered.store.save_state("identity_cache", self._identity_cache)

    def get_identity_traits(
        self,
        campaign_id: str,
        npc_id: str,
    ) -> Dict[str, float]:
        """
        Возвращает накопленные черты NPC из identity_cache.
        READ: для DecisionHub через DecisionView.identity.active_traits
        """
        key = f"{campaign_id}:{npc_id}"
        return dict(self._identity_cache.get(key, {}))

    def check_identity_promotion(
        self,
        campaign_id: str,
        npc_id: str,
    ) -> List[Tuple[str, float]]:
        """Этап 10: проверяет мета-паттерны в накопленных чертах.

        Если комбинация черт удовлетворяет правилу — генерирует новую черту.
        Возвращает список новых (trait_name, delta) для логирования.
        Новые черты сразу применяются в identity_cache.
        """
        current = self.get_identity_traits(campaign_id, npc_id)
        engine = MemoryPromotionEngine()
        new_traits = engine.check_identity(current)
        if new_traits:
            self.apply_identity_weights(campaign_id, npc_id, new_traits)
        return new_traits

"""
path: /project/backend/app/services/events/npc_dialogue_subscriber.py
Назначение: Слушает NPC_SPOKE события, замыкая цикл восприятия для NPC-NPC диалогов
    (эмоции, память, отношения).
Зависимости: app.services.events.event_bus, app.services.memory.memory_manager,
    app.services.memory.relationship_store, app.services.affective.affective_integrator
Основные сущности: NpcDialogueSubscriber
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional, Tuple

from app.domain.communication import SELF_TALK_SENTINEL
from app.domain.player_epistemics import SurfaceEvent, SurfaceKind
from app.services.memory.intelligence_queue import (
    d8p_enabled,
    get_intelligence_queue,
)

logger = logging.getLogger(__name__)


class NpcDialogueSubscriber:
    """Слушает NPC_SPOKE события и замыкает цикл восприятия для NPC-NPC диалогов.

    Для canonical реплик — полная обработка:
        AffectiveIntegrator → WorkingMemory (с текстом) → RelationshipStore

    Для ambient реплик — упрощённая:
        WorkingMemory (абстрактно) → RelationshipStore
    """

    def __init__(
        self,
        memory_manager: Any,
        relationship_store: Any,
        npc_states_provider: Any = None,
        campaign_id_provider: Any = None,  # NEW — callable() -> str
        avatar_service: Any = None,
        spatial_query_provider: Any = None,
        l1_chronicle: Any = None,
        discovery_bridge_provider: Any = None,  # E2 (S256): канал EAVESDROP
        tick_provider: Any = None,  # H-01 FIX: callable() -> int (симуляционный тик)
        dialogue_update_extractor: Any = None,  # BUG-DL-09: Для извлечения claims/questions
        subject_resolver: Any = None,  # P7-B: Callable[[topic], SubjectRef] (симметрия E1)
    ) -> None:
        self.memory = memory_manager
        self.relationships = relationship_store
        # Р-Б1 (M1b.2.4-паритет): седьмой write-маршрут замкнут на единый гейт
        # (D2-инвариант «ALL RELATIONSHIP WRITES → GATE → STORE»). Паттерн
        # StateApplicator:95-96 — wrap-own-gate над инжектированным бекендом;
        # cutover M1b.4 меняет бекенд централизованно, писатель не мигрирует.
        from app.services.social.relationship_write_gate import RelationshipWriteGate

        self._rel_write_gate = RelationshipWriteGate(relationship_store)
        self._get_npc_state = npc_states_provider
        self._get_campaign_id = campaign_id_provider or (lambda: "Open_road")
        self._avatar_service = avatar_service
        # M17 этап 2: pending-буфер подслушанных обращений (адресат → tentative).
        # Прецедент: add_pending_dialogue_memory (применение в drain-границе).
        # NPC_SPOKE публикуется только в drain (ADR-O-399) → подписчик
        # выполняется в main thread → буфер без гонок.
        self._pending_recognition: list = []
        self._get_spatial_query = spatial_query_provider
        self._l1_chronicle = l1_chronicle
        self._get_tick = tick_provider or (lambda: 0)
        self._extractor = dialogue_update_extractor
        self._get_discovery_bridge = discovery_bridge_provider
        self._subject_resolver = subject_resolver

    def _resolve_eavesdrop_label(
        self, speaker: str, topic: str, payload: dict
    ) -> Optional[Tuple[Optional[str], Optional[str]]]:
        """P7-B: провенанс-метка EAVESDROP — знание спикера, не текст
        реплики (PROVENANCE, NOT STRINGS). FULL ⇔ приватная громкость
        {secret, whisper} (единый whisper-класс по materializer:32);
        иначе CLUE; без проводки/знания/при ошибке — (None, None):
        поведение E2 (observation only) сохраняется (fail-open)."""
        if self._subject_resolver is None or self._get_npc_state is None:
            return None, None
        try:
            from app.services.npc.knowledge_retrieval import retrieve_knowledge
            from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

            _states = self._get_npc_state() or []
            _speaker_raw = next(
                (
                    n
                    for n in _states
                    if isinstance(n, dict)
                    and (n.get("npc_id") or n.get("id")) == speaker
                ),
                None,
            )
            if _speaker_raw is None:
                return None, None
            _speaker_state = load_l2_state_from_runtime_dict(_speaker_raw)
            _subject = self._subject_resolver(topic or "")
            _items = retrieve_knowledge(_speaker_state, _subject)
            if not _items:
                return None, None
            _secret_id = _items[0].secret_id
            _content_class = None
            if payload.get("exposure") in ("secret", "whisper"):
                from app.domain.player_epistemics import CONTENT_EAVESDROP_FULL

                _content_class = CONTENT_EAVESDROP_FULL
            return _secret_id, _content_class
        except Exception as _e:
            logger.warning(
                f"[NPC_DIALOGUE_SUB] eavesdrop label failed ({speaker}): {_e}"
            )
            return None, None

    def drain_pending_recognition(self, scene_state: dict) -> None:
        """M17 этап 2: применение pending tentative-записей в drain-границе
        (прецедент drain_commitment_outbox, те же точки вызова).
        confirmed НЕ понижается — предположение никогда не затирает знание."""
        # DIAG-DRAIN (Часть VIII.5, ВРЕМЕННЫЙ): почему recognition пуст.
        print(f"[DIAG-DRAIN] pending={len(self._pending_recognition)} "
              f"items={self._pending_recognition[:5]} scene_id={id(scene_state)}")
        if not self._pending_recognition or not scene_state:
            return
        _recog = scene_state.setdefault("player_recognition", {})
        _batch, self._pending_recognition = self._pending_recognition, []
        for _item in _batch:
            # Элемент: str (tentative, подслышанное обращение) или
            # tuple(npc_id, status) — confirmed из факта прямого диалога.
            if isinstance(_item, tuple):
                _addr_id, _status = _item
            else:
                _addr_id, _status = _item, "tentative"
            _entry = _recog.setdefault(_addr_id, {})
            if _entry.get("status") == "confirmed" and _status != "confirmed":
                continue  # предположение не затирает знание
            _entry["status"] = _status
            if _status == "confirmed":
                _entry["confidence"] = 1.0
            else:
                _entry["confidence"] = max(_entry.get("confidence", 0.0), 0.6)

    def on_npc_spoke(self, event: Any) -> None:
        # Поддержка как EventDTO, так и dict (для тестов)
        if hasattr(event, "payload"):
            speaker = getattr(event, "source", "")  # noqa: ENIGMA002
            payload = getattr(event, "payload", {}) or {}  # noqa: ENIGMA002
        else:
            speaker = event.get("source", "")
            payload = event.get("payload", {})

        # H-01 FIX: Используем каноничный симуляционный тик (ctx.tick_number / scene_state["tick"])
        # вместо event.timestamp (wall-clock time), чтобы удовлетворить контракт L1Chronicle (INTEGER).
        tick = int(self._get_tick())
        # ADR-O-399 Iter1: event_tick — событийное время, назначенное в
        # submit (main thread), приезжает в payload при drain. Fallback на
        # arrival-тик — fail-open (прецедент Р-Б2/S198: dict-события тестов
        # без штампа сохраняют прежнее поведение).
        _event_tick = int(payload.get("event_tick", 0) or 0)

        listener = payload.get("target_id")
        text = payload.get("text", "")
        tone = payload.get("tone", "NEUTRAL")
        topic = payload.get("topic", "")
        # V8-SOC-11 FIX: Распознаём русскую заглушку "[Заглушка]" как ambient
        is_canonical = "Stub LLM" not in text and "[Заглушка]" not in text and text != ""

        if not speaker or not listener or listener == "all":
            return

        # S128: Eavesdrop — если игрок рядом, он подслушивает реплику
        if self._avatar_service and self._get_spatial_query:
            _campaign_id = self._get_campaign_id()
            _spatial_query = self._get_spatial_query()
            if _spatial_query:
                # P1-07 FIX: Совместимость с SpatialService и SpatialQueryService
                _dist_to_player = 999.0
                if hasattr(_spatial_query, "player_distances"):
                    _dist_to_player = _spatial_query.player_distances([speaker]).get(speaker, 999.0)
                elif hasattr(_spatial_query, "_npc_positions"):
                    _player_pos = _spatial_query._npc_positions.get("player", {}).get("local_position", {})
                    _speaker_pos = _spatial_query._npc_positions.get(speaker, {}).get("local_position", {})
                    if _player_pos and _speaker_pos:
                        import math
                        _dist_to_player = math.hypot(
                            _player_pos.get("x", 0.0) - _speaker_pos.get("x", 0.0),
                            _player_pos.get("y", 0.0) - _speaker_pos.get("y", 0.0)
                        )
                # Р-Г (GC-DIALOGUE-01): порог журнала игрока — из event.radius
                # (SpeechExposure SSOT, Р-В): whisper 3 / normal 6 / loud 10 /
                # shout 15 / private 0 — вместо хардкода 8.0 (S128). Фоллбек 8.0
                # сохранён как fail-open-паритет с Р-Б2: dict-события без radius
                # и битые значения (999-дефолт ADR-148, NaN, вне лестницы) не
                # меняют сегодняшнее поведение и не раздувают журнал на сцену.
                # Локальный импорт — прецедент файла (math, PerceptualKernel).
                from app.domain.communication import exposure_radius
                _evt_radius = getattr(event, "radius", None)
                _journal_threshold = 8.0  # легаси-порог S128 (fail-open)
                if (
                    isinstance(_evt_radius, (int, float))
                    and 0.0 <= float(_evt_radius) <= exposure_radius("shout")
                ):
                    _journal_threshold = float(_evt_radius)
                if _dist_to_player < _journal_threshold and is_canonical:
                    # INV-NPC-NAME: журнал игрока хранит наблюдаемое имя, не machine-id.
                    # Резолв через SSOT имён (npc_positions["name"], CAUSAL CONTRACT §2.1).
                    # Источник — тот же _spatial_query, что и для дистанции (прецедент
                    # P1-07 выше). Fail-open: без позиций — speaker как есть (parity).
                    _speaker_name = speaker
                    _npc_positions = getattr(_spatial_query, "_npc_positions", None) or {}
                    if speaker in _npc_positions:
                        _sp_data = _npc_positions[speaker]
                        _resolved = (
                            _sp_data.get("name")
                            if isinstance(_sp_data, dict) else getattr(_sp_data, "name", None)
                        ) or (
                            _sp_data.get("display_name")
                            if isinstance(_sp_data, dict) else getattr(_sp_data, "display_name", None)
                        )
                        if _resolved:
                            _speaker_name = _resolved
                        else:
                            logger.warning(
                                f"[NPC_DIALOGUE_SUB] speaker '{speaker}' без name в "
                                f"npc_positions — journal хранит npc_id (INV-NPC-NAME drift)"
                            )
                    # Эпистемическая метка канала: игрок-адресат (direct) vs
                    # подслушанное (overheard) — известна в момент записи,
                    # проекция слышанного, не новая истина.
                    _channel = "direct" if listener == "player" else "overheard"
                    # Event Identity (ADR-O-404): сквозная идентичность —
                    # journal-запись наследует финальный event.id NPC_SPOKE
                    # (тот же, что получили все подписчики шины) + событийное
                    # время payload["event_tick"] (ADR-O-399).
                    self._avatar_service.append_journal(
                        campaign_id=_campaign_id, speaker=_speaker_name, text=text,
                        channel=_channel,
                        event_id=str(getattr(event, "id", "") or ""),
                        tick=int(_event_tick or tick or 0),
                    )
                    # M17 этап 2 (вердикт Мастера: «всё согласовано с логикой
                    # слышимости и видимости»): tentative адресата — ТОЛЬКО здесь,
                    # внутри блока, где уже пройдены порог слышимости
                    # (_dist_to_player < _journal_threshold) и is_canonical.
                    # Адресат структурный (target_id интента), не парсинг текста.
                    if _channel == "direct":
                        # M17 этап 3: NPC адресует речь игроку — спикер
                        # подтверждён ФАКТОМ разговора (не целеполаганием).
                        self._pending_recognition.append((speaker, "confirmed"))
                    elif _channel == "overheard":
                        _addr_id = listener
                        if (
                            _addr_id
                            and _addr_id != speaker
                            and _addr_id in _npc_positions
                        ):
                            self._pending_recognition.append(_addr_id)
                    # E2 (S256, mini-ADR E2-1..E2-4): реплика ДОСТАВЛЕНА —
                    # мембрана S128/Р-Г пройдена, журнал игрока записан.
                    # Канал EAVESDROP: игрок не адресат (суверенитет E1) и
                    # не говорящий. P7-B (S259): метка по провенансу знания
                    # спикера (secret_id/FULL при приватной громкости);
                    # без проводки/знания -> observation only (E2-наследие).
                    # mark_discovered недостижим вне Bridge (Р1).
                    if listener != "player" and speaker != "player":
                        try:
                            _bridge = (
                                self._get_discovery_bridge()
                                if self._get_discovery_bridge is not None
                                else None
                            )
                            if _bridge is not None:
                                # P7-B: метка по провенансу знания спикера
                                _label = self._resolve_eavesdrop_label(
                                    speaker, topic, payload
                                ) or (None, None)
                                _secret_id, _content_class = _label
                                _bridge.process(
                                    SurfaceEvent(
                                        kind=SurfaceKind.EAVESDROP,
                                        tick=tick,
                                        source_id=speaker,
                                        secret_id=_secret_id,
                                        content_class=_content_class,
                                        subject_hint=(topic or None),
                                    )
                                )
                        except Exception as _e2_err:
                            logger.warning(
                                "[NPC_DIALOGUE_SUB] eavesdrop emit failed "
                                f"({speaker}): {_e2_err}"
                            )

        # Р-А: SELF_TALK_SENTINEL — внешне слышимое бормотание без агента-адресата.
        # Журнал выше СОХРАНЁН: реплика экстернализована, игрок подслушивает легально.
        # Агентная обработка (STM / отношения / L1) для фантома запрещена: адресат
        # не является субъектом. Лог "X heard Y" для фантома не порождается.
        if listener == SELF_TALK_SENTINEL:
            logger.debug(
                f"[NPC_DIALOGUE_SUB] self-talk {speaker}: агентная обработка пропущена (journal-only)"
            )
            return

        # Р-Б2: Мембрана адресата (S192-паритет с ClaimEventSubscriber). Агентная
        # обработка (STM / отношения / L1) — только если адресат физически способен
        # воспринять реплику. ПОСЛЕ журнала игрока (Р-Г — отдельный шаг) и ПОСЛЕ
        # sentinel-гарда Р-А. Fail-open по S198-прецеденту (детерминизм важнее
        # молчания): dict-события (тестовый контракт), адресат без позиции,
        # ошибка дистанции — адресат слышит.
        if hasattr(event, "visibility") and self._get_spatial_query:
            _sq_m = self._get_spatial_query()
            if _sq_m is not None and hasattr(_sq_m, "distance"):
                _positions_m = getattr(_sq_m, "_npc_positions", {})
                if listener in _positions_m:
                    try:
                        _dist_m = _sq_m.distance(speaker, listener)
                        from app.models.npc_state import PerceptualKernel
                        if not PerceptualKernel.can_observe(event, _dist_m, listener, listener):
                            logger.info(
                                f"[NPC_DIALOGUE_SUB] membrane: {listener} не воспринимает "
                                f"реплику {speaker} (dist={_dist_m:.1f}, "
                                f"visibility={getattr(event, 'visibility', '?')})"
                            )
                            return
                    except Exception as _membrane_err:
                        logger.warning(
                            f"[NPC_DIALOGUE_SUB] membrane check failed "
                            f"({listener}/{speaker}): {_membrane_err}"
                        )

        logger.info(
            f"[NPC_DIALOGUE_SUB] {listener} heard {speaker} "
            f"(tone={tone}, topic={topic!r}, canonical={is_canonical})"
        )

        try:
            if is_canonical:
                # AG1-D8p Шаг 3.2 (ADR-O-382): event.id (UUID EventDTO) —
                # ключ Q5-идемпотентности очереди; для dict-событий (тесты)
                # пусто — _process_canonical возьмёт content-hash fallback.
                _event_id = str(getattr(event, "id", "") or "")
                self._process_canonical(
                    speaker, listener, text, tone, topic, tick, event_id=_event_id,
                    event_tick=_event_tick,
                )
            else:
                self._process_ambient(speaker, listener, tone, topic, tick,
                                      event_tick=_event_tick)
        except Exception as e:
            logger.exception(
                f"[NPC_DIALOGUE_SUB] failed for {listener} hearing {speaker}: {e}"
            )

    def _process_canonical(
        self,
        speaker: str,   
        listener: str,
        text: str,
        tone: str,
        topic: str,
        tick: int,
        event_id: str = "",
        event_tick: int = 0,
    ) -> None:
        """Полная обработка canonical реплики (с текстом от LLM)."""
        _campaign_id = self._get_campaign_id()

        # 1. STM (Short-Term Memory) — добавляем реплику (BUG-DL-05: симметричная запись)
        try:
            # BUG-DL-09: Извлекаем structured update (claims, questions) из реплики
            _stm_before = ""
            _update = None
            # AG1-D8p Шаг 3.2 (ADR-O-382): при D8P_ENABLED экстракция НЕ
            # исполняется в потоке публикатора — enqueue IntelligenceTask
            # (неблокирующе), placeholder-ход ниже пишется немедленно
            # (intent="dialogue" — существующая семантика деградации);
            # смысл доедает позже: очередь → STALE-гейт → MemoryManager.
            # Гонка enqueue→placeholder безопасна: ход пишется тем же
            # потоком через микросекунды, LLM-экстракция длится секунды.
            # OFF (default) = elif-ветка дословно прежний inline-путь
            # (INV-D8P-NOOP). Dubl event.id → enqueue=False, повторная
            # экстракция запрещена (Q5).
            if d8p_enabled():
                _session = self.memory.get_dialogue_session(_campaign_id, listener, partner_id=speaker)
                _stm_before = _session.to_prompt_block()
                _queue = get_intelligence_queue()
                _ev_id = event_id or hashlib.md5(
                    f"{_campaign_id}:{speaker}:{listener}:{text}:{tick}".encode("utf-8")
                ).hexdigest()
                if _queue is not None:
                    _queue.enqueue(
                        event_id=_ev_id,
                        campaign_id=_campaign_id,
                        speaker=speaker,
                        listener=listener,
                        text=text,
                        stm_before=_stm_before,
                        parent_tick=tick,
                    )
                else:
                    # INV-LLM-LOOP-EXILE by construction: при ON LLM никогда
                    # не зовётся из потока публикатора — даже при сломанной
                    # проводке (громко, не молча; wiring-баг ловится здесь).
                    logger.warning(
                        "[D8P] D8P_ENABLED=1, IntelligenceQueue не wired — "
                        "экстракция пропущена (placeholder-ход записан)"
                    )
            elif self._extractor:
                _session = self.memory.get_dialogue_session(_campaign_id, listener, partner_id=speaker)
                _stm_before = _session.to_prompt_block()
                _update = self._extractor.extract(_stm_before, text, speaker)

            self.memory.add_dialogue_turn(
                campaign_id=_campaign_id,
                npc_id=listener,
                speaker=speaker,
                text=text,
                target_id=listener,
                intent=_update.last_speaker_intent if _update else "dialogue",
                tick=tick,
                partner_id=speaker,  # BUG-DL-05: Per-pair session
            )
            # BUG-DL-09: Применяем обновления темы, claims и open_questions к per-pair сессии
            # (BUG-DLG-007 FIX: симметричный ключ означает, что listener и speaker делят одну сессию)
            if _update:
                _session = self.memory.get_dialogue_session(_campaign_id, listener, partner_id=speaker)
                if _update.topic:
                    _session.topic = _update.topic
                    _session.topic_confidence = _update.topic_confidence
                for claim in _update.new_claims or []:
                    # Claim Bridge: claims наследуют сквозной event.id
                    # (параметр event_id этой функции — тот же, что у
                    # NPC_SPOKE и journal-записи — позвоночник
                    # provenance, ADR-O-404)
                    _session.add_claim(
                        text=claim.get("text", ""),
                        speaker=speaker,
                        confidence=claim.get("confidence", 0.5),
                        tick=tick,
                        event_id=event_id,
                    )
                for q in _update.raised_questions or []:
                    _session.add_open_question(
                        text=q.get("text", ""),
                        asked_by=speaker,
                        addressed_to=q.get("addressed_to", listener),
                        tick=tick,
                    )
                for q_idx in _update.answered_questions or []:
                    _session.answer_question(q_idx, text, speaker, tick)
        except Exception as mem_err:
            logger.warning(f"[NPC_DIALOGUE_SUB] add_dialogue_turn failed for {listener}/{speaker}: {mem_err}")

            # BUG-DL-06: Отложенная запись в L2 (narrative_cache) через буфер MemoryManager.
            # Фаза 3 следующего тика применит это событие к свежему NPCState.
            from app.domain.events import EventDTO
            _dialogue_event = EventDTO.create(
                event_type="dialogue_line",
                source=speaker,
                payload={
                    "npc_id": listener,  # Тот, кто слышит (для записи в его narrative_cache)
                    "text": text,
                    "topic": topic,
                    "tone": tone,
                    "speaker_id": speaker,
                    "scene_state": {},  # Пустой контекст, apply() использует дефолты
                    "npc_stress": 0.0,
                },
                visibility="public",
                radius=10.0,
                persistence_level="session",
            )
            self.memory.add_pending_dialogue_memory(_dialogue_event)

        # 3. RelationshipStore
        # NEW-2: Маппим tone на event_type из P2-05 (get_base_delta).
        # Если тон не замапплен (напр. NEUTRAL), дельты равны 0 (предотвращает Double Truth со старой шкалой).
        _TONE_TO_NPC_EVENT = {
            "ANGRY": "npc_insults",
            "MANIPULATIVE": "npc_threatens",
            "FRIENDLY": "npc_helps",
            "FEARFUL": "npc_threatens",
            "FLIRTY": "npc_helps",
        }
        _npc_event_type = _TONE_TO_NPC_EVENT.get(tone)
        if _npc_event_type:
            from app.services.npc.decision.social_deltas import get_base_delta
            delta_trust, delta_fear, _ = get_base_delta(_npc_event_type)
        else:
            delta_trust, delta_fear = 0.0, 0.0
        try:
            # Р-Б1: через RelationshipWriteGate (whitelist/NaN-валидация +
            # provenance cause). Гейт делегирует backend.update() — паритет
            # D3: сатурация/clamp в бекенде, поведение идентично прежнему.
            self._rel_write_gate.apply(
                _campaign_id,
                listener,
                speaker,
                {"trust": delta_trust, "fear": delta_fear},
                cause=f"npc_dialogue_sub:{tone.lower()}",
            )
            logger.info(
                f"[NPC_DIALOGUE_SUB] {listener} rel update: "
                f"{speaker} trust={delta_trust:+.1f} fear={delta_fear:+.1f}"
            )

            # NEW-3: Bridge 2 — пишем NPC-NPC диалог в L1Chronicle для BeliefCrystallizationEngine
            if self._l1_chronicle:
                from app.domain.identity_events import TraitDriftEvent
                _drift_event = TraitDriftEvent(
                    tick_id=tick,
                    target_id=listener,
                    source_id=speaker,
                    effect_value=delta_trust,
                    observation_weight=1.0,
                    event_type=f"social_dialogue:{tone}",
                )
                # ADR-O-399 Iter1: L1 — event-time (submit), не arrival
                self._l1_chronicle.commit_tick_buffer([_drift_event], event_tick or tick)

        except Exception as rel_err:
            logger.warning(f"[NPC_DIALOGUE_SUB] relationship update failed: {rel_err}")

    def _process_ambient(
        self,
        speaker: str,
        listener: str,
        tone: str,
        topic: str,
        tick: int,
        event_tick: int = 0,
    ) -> None:
        """Упрощённая обработка ambient реплики (без LLM-конкретики)."""
        _campaign_id = self._get_campaign_id()

        # Ambient — дельты в 5 раз меньше, без записи в STM
        # NEW-2: Маппим tone на event_type из P2-05 (get_base_delta) с множителем 0.2 для ambient.
        # Если тон не замапплен, дельты равны 0.
        _TONE_TO_NPC_EVENT = {
            "ANGRY": "npc_insults",
            "MANIPULATIVE": "npc_threatens",
            "FRIENDLY": "npc_helps",
            "FEARFUL": "npc_threatens",
            "FLIRTY": "npc_helps",
        }
        _npc_event_type = _TONE_TO_NPC_EVENT.get(tone)
        if _npc_event_type:
            from app.services.npc.decision.social_deltas import get_base_delta
            _bt, _bf, _ = get_base_delta(_npc_event_type)
            delta_trust, delta_fear = _bt * 0.2, _bf * 0.2
        else:
            delta_trust, delta_fear = 0.0, 0.0

        try:
            # Р-Б1: через RelationshipWriteGate — аналогично canonical-ветке.
            self._rel_write_gate.apply(
                _campaign_id,
                listener,
                speaker,
                {"trust": delta_trust, "fear": delta_fear},
                cause=f"npc_dialogue_sub:ambient_{tone.lower()}",
            )
            logger.info(
                f"[NPC_DIALOGUE_SUB] {listener} rel update (ambient): "
                f"{speaker} trust={delta_trust:+.1f} fear={delta_fear:+.1f} (event={_npc_event_type or 'fallback'})"
            )
        except Exception as rel_err:
            logger.warning(f"[NPC_DIALOGUE_SUB] relationship update failed: {rel_err}")

        # NEW-3: Bridge 2 — пишем NPC-NPC диалог в L1Chronicle для BeliefCrystallizationEngine
        try:
            if self._l1_chronicle:
                from app.domain.identity_events import TraitDriftEvent
                _drift_event = TraitDriftEvent(
                    tick_id=tick,
                    target_id=listener,
                    source_id=speaker,
                    effect_value=delta_trust,
                    observation_weight=1.0,
                    event_type=f"social_dialogue:{tone}",
                )
                # ADR-O-399 Iter1: L1 — event-time (submit), не arrival
                self._l1_chronicle.commit_tick_buffer([_drift_event], event_tick or tick)
        except Exception as chron_err:
            logger.warning(f"[NPC_DIALOGUE_SUB] L1Chronicle append failed: {chron_err}")

    def _build_interpretation(self, tone: str, text: str, topic: str) -> dict:
        """Строит упрощённую интерпретацию реплики для AffectiveIntegrator.

        AffectiveIntegrator обычно получает интерпретацию из InterpretationEngine,
        но для NPC-NPC диалогов мы строим её напрямую из tone — без отдельного
        LLM-вызова для интерпретации.
        """
        _TONE_TO_AFFECT = {
            "ANGRY": {"anger": 0.3, "fear": 0.1, "sadness": 0.0},
            "FRIENDLY": {"joy": 0.2, "trust": 0.1},
            "FLIRTY": {"joy": 0.15, "embarrassment": 0.2},
            "VENTING": {"sadness": 0.2, "empathy": 0.2},
            "MANIPULATIVE": {"suspicion": 0.2, "fear": 0.1},
            "FEARFUL": {"fear": 0.2, "sympathy": 0.1},
            "NEUTRAL": {},
        }
        return {
            "affect_deltas": _TONE_TO_AFFECT.get(tone, {}),
            "source": f"dialogue:{tone}",
            "text": text,
            "topic": topic,
        }

    def _compute_rel_delta(self, tone: str) -> tuple[float, float]:
        """Конвертирует tone в изменения trust/fear."""
        _BASE = {
            "ANGRY": (-0.10, 0.05),
            "FRIENDLY": (0.05, 0.0),
            "FLIRTY": (0.03, 0.0),
            "VENTING": (0.02, 0.0),
            "MANIPULATIVE": (-0.05, 0.02),
            "FEARFUL": (0.0, 0.03),
            "NEUTRAL": (0.005, 0.0),  # Шкала 0..1: привыкание очень медленное
            "PANIC": (-0.02, 0.08),
            "CURIOUS": (0.01, 0.0),
            "SAD": (-0.01, 0.01),
            "SUSPICIOUS": (-0.03, 0.01),
        }
        return _BASE.get(tone, (0.0, 0.0))

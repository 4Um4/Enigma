"""
path: /project/backend/tests/sandbox/SUPERBOX/scenarios/d8p_intelligence_test.py
Назначение: AG1-D8p/ADR-O-382 — приёмочный фальсификатор Intelligence Queue
    (методология causal_state_test/bc1: группы A–E, громкие падения, метрика
    = session-содержимое + lifecycle-счётчики очереди + трейс extractor'а,
    НЕ intent). Оффлайн-детерминизм: RecordingExtractor вместо LLM (урок
    bc1: доказательство каузальности не требует интеллекта); РЕАЛЬНЫЕ
    DialogueSession/EventDTO/NpcDialogueSubscriber/IntelligenceQueue.
Зависимости: app.domain.events, app.services.events.event_types,
    app.services.events.npc_dialogue_subscriber,
    app.services.memory.dialogue_session,
    app.services.memory.intelligence_queue.
Основные сущности: группы A (ON: placeholder немедленно + deferred APPLIED
    + loop-exile: extractor на worker-потоке ≠ поток публикатора),
    B (OFF: inline-путь — контроль A: тот же поток, эквивалентность
    enrichment), C (STALE по возрасту — наблюдаемый discard, session
    не тронут), D (Q5-идемпотентность: дубль event.id → duplicates+1,
    ≤1 APPLIED — ЗАМОК), E (не-wired при ON: экстракция пропущена,
    placeholder записан, без падения — INV-LLM-LOOP-EXILE by construction).
Запуск: cd backend && python -B -m tests.sandbox.SUPERBOX.scenarios.d8p_intelligence_test
"""

from __future__ import annotations

import logging
import os
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

from app.domain.events import EventDTO
from app.services.events.event_types import EventType
from app.services.events.npc_dialogue_subscriber import NpcDialogueSubscriber
from app.services.memory.dialogue_session import DialogueSession
from app.services.memory.intelligence_queue import (
    _reset_intelligence_queue,
    d8p_enabled,
    wire_intelligence_queue,
)

CAMPAIGN = "T"
SPEAKER = "merchant_goran"
LISTENER = "maid_lusya"
TEXT = "продам меч за сто монет"


# ── Фейки контрактов (§12.4: фабрики/контракты, не конструкторы мечты) ──


class SessionMemory:
    """MemoryManager-контракт (R3-археология): get_dialogue_session
    (create-if-missing — дословно) + add_dialogue_turn. Сессии — РЕАЛЬНЫЕ
    DialogueSession (применение = настоящий session-API)."""

    def __init__(self) -> None:
        self._sessions: Dict[tuple, DialogueSession] = {}

    def get_dialogue_session(
        self, campaign_id: str, npc_id: str, partner_id: str = "player"
    ) -> DialogueSession:
        key = (campaign_id, npc_id, partner_id)
        if key not in self._sessions:
            self._sessions[key] = DialogueSession(npc_id=npc_id, partner_id=partner_id)
        return self._sessions[key]

    def add_dialogue_turn(
        self, campaign_id: str, npc_id: str, speaker: str, text: str,
        target_id: str = "", intent: str = "", tone: str = "",
        tick: int = 0, partner_id: str = "player",
    ) -> None:
        self.get_dialogue_session(campaign_id, npc_id, partner_id).add_turn(
            speaker=speaker, text=text, target_id=target_id,
            intent=intent, tone=tone, tick=tick,
        )


class RecordingRelStore:
    """RelationshipStore-контракт: только запись вызовов (tone-дельты —
    вне D8P-скоупа, но путь обязан исполняться одинаково в ON/OFF)."""

    def __init__(self) -> None:
        self.updates: List[tuple] = []

    def update(self, campaign_id: str, source: str, target: str, delta: dict) -> None:
        self.updates.append((campaign_id, source, target, dict(delta)))


class RecordingExtractor:
    """DialogueUpdateExtractor-контракт: детерминированный update + трасса
    (количество вызовов + поток каждого вызова — доказательство loop-exile)."""

    def __init__(self, update: Any) -> None:
        self.update = update
        self.calls = 0
        self.ran_on_main: List[bool] = []

    def extract(self, stm_before: str, new_turn: str, partner: str) -> Any:
        self.calls += 1
        self.ran_on_main.append(
            threading.current_thread() is threading.main_thread()
        )
        return self.update


def _make_update() -> Any:
    """DialogueUpdate-контракт (экстрактор живой сессии вернул бы это)."""
    return types.SimpleNamespace(
        topic="trade",
        topic_confidence=0.9,
        new_claims=[{"text": "меч стоит сто монет", "confidence": 0.8}],
        raised_questions=[{"text": "кто покупатель?", "addressed_to": LISTENER}],
        answered_questions=[],
        last_speaker_intent="offer",
    )


def _make_subscriber(
    mem: SessionMemory, ext: RecordingExtractor, tick_provider: Callable[[], int]
) -> NpcDialogueSubscriber:
    return NpcDialogueSubscriber(
        memory_manager=mem,
        relationship_store=RecordingRelStore(),
        npc_states_provider=lambda: [
            {"npc_id": SPEAKER}, {"npc_id": LISTENER},
        ],
        campaign_id_provider=lambda: CAMPAIGN,
        avatar_service=None,
        spatial_query_provider=None,
        l1_chronicle=None,
        tick_provider=tick_provider,
        dialogue_update_extractor=ext,
    )


def _publish(sub: NpcDialogueSubscriber, tone: str = "FRIENDLY") -> EventDTO:
    """Живой прод-путь: настоящий EventDTO (UUID id = Q5-ключ) → подписчик."""
    ev = EventDTO.create(
        event_type=EventType.NPC_SPOKE,
        source=SPEAKER,
        payload={
            "npc_id": SPEAKER,
            "target_id": LISTENER,
            "text": TEXT,
            "tone": tone,
            "topic": "trade",
        },
        persistence_level="working",
    )
    sub.on_npc_spoke(ev)
    return ev


def _sess(mem: SessionMemory) -> DialogueSession:
    return mem.get_dialogue_session(CAMPAIGN, LISTENER, partner_id=SPEAKER)


# ── Группы ──


def group_a() -> Dict[str, bool]:
    """A: ON + wired (реальный пул) — placeholder НЕМЕДЛЕННО, смысл
    доезжает ПОЗДНЕЕ на worker-потоке (loop-exile), enrichment живой."""
    os.environ["D8P_ENABLED"] = "1"
    mem, tick, ext = SessionMemory(), [100], RecordingExtractor(_make_update())
    pool = ThreadPoolExecutor(max_workers=1)
    q = wire_intelligence_queue(
        mem, ext, lambda: tick[0],
        npc_states_provider=lambda: [{"npc_id": SPEAKER}, {"npc_id": LISTENER}],
        pool_provider=lambda: pool,
    )
    sub = _make_subscriber(mem, ext, lambda: tick[0])
    _publish(sub)
    sess = _sess(mem)
    placeholder_immediate = any(
        t.speaker == SPEAKER and t.intent == "dialogue" for t in sess.buffer
    )
    deadline = time.time() + 10.0
    while q.stats()["applied"] < 1 and time.time() < deadline:
        time.sleep(0.05)
    st = q.stats()
    pool.shutdown(wait=True)
    return {
        "A1 placeholder немедленно (R1-семантика)": placeholder_immediate,
        "A2 applied=1 (смысл доехал)": st["applied"] == 1,
        "A3 topic=trade": sess.topic == "trade",
        "A4 claim=1": len(sess.claims) == 1,
        "A5 question=1": len(sess.open_questions) == 1,
        "A6 loop-exile: extractor на worker, НЕ main": (
            bool(ext.ran_on_main) and ext.ran_on_main[-1] is False
        ),
    }


def group_b() -> Dict[str, bool]:
    """B: OFF — inline-путь; контроль A: тот же поток, эквивалентность
    enrichment (placeholder-intent — задокументированное отличие)."""
    os.environ.pop("D8P_ENABLED", None)
    _reset_intelligence_queue()
    mem, tick, ext = SessionMemory(), [100], RecordingExtractor(_make_update())
    sub = _make_subscriber(mem, ext, lambda: tick[0])
    _publish(sub)
    sess = _sess(mem)
    return {
        "B1 inline extract calls=1": ext.calls == 1,
        "B2 publisher-thread (контроль A6)": (
            bool(ext.ran_on_main) and ext.ran_on_main[-1] is True
        ),
        "B3 topic=trade (эквивалент A3)": sess.topic == "trade",
        "B4 claim=1 (эквивалент A4)": len(sess.claims) == 1,
        "B5 question=1 (эквивалент A5)": len(sess.open_questions) == 1,
        "B6 intent=offer (inline-семантика)": any(
            t.intent == "offer" for t in sess.buffer
        ),
        "B7 очередь не участвовала": d8p_enabled() is False,
    }


def group_c() -> Dict[str, bool]:
    """C: STALE по возрасту (Q2б) — наблюдаемый discard, session не тронут."""
    os.environ["D8P_ENABLED"] = "1"
    _reset_intelligence_queue()
    mem, tick, ext = SessionMemory(), [100], RecordingExtractor(_make_update())
    q = wire_intelligence_queue(
        mem, ext, lambda: tick[0],
        npc_states_provider=lambda: [{"npc_id": SPEAKER}, {"npc_id": LISTENER}],
        pool_provider=None,
    )
    sub = _make_subscriber(mem, ext, lambda: tick[0])
    _publish(sub)
    tick[0] = 104  # age=4 > N=3 (строго >, вердикт Q2б)
    q.execute_next()
    sess = _sess(mem)
    return {
        "C1 stale_discarded=1": q.stats()["stale_discarded"] == 1,
        "C2 session не обогащён (claims=0)": len(sess.claims) == 0,
        "C3 topic нет": sess.topic is None,
        "C4 placeholder остался (сырой текст жив)": any(
            t.speaker == SPEAKER for t in sess.buffer
        ),
    }


def group_d() -> Dict[str, bool]:
    """D: Q5-идемпотентность — дубль event.id: duplicates+1, ≤1 APPLIED.
    ЗАМОК: applied=2 или двойное обогащение = громкое падение."""
    os.environ["D8P_ENABLED"] = "1"
    _reset_intelligence_queue()
    mem, tick, ext = SessionMemory(), [100], RecordingExtractor(_make_update())
    q = wire_intelligence_queue(
        mem, ext, lambda: tick[0],
        npc_states_provider=lambda: [{"npc_id": SPEAKER}, {"npc_id": LISTENER}],
        pool_provider=None,
    )
    sub = _make_subscriber(mem, ext, lambda: tick[0])
    ev = _publish(sub)
    sub.on_npc_spoke(ev)  # повторная публикация ТОГО ЖЕ event.id
    q.execute_next()
    sess = _sess(mem)
    st = q.stats()
    return {
        "D1 duplicates=1 (дубль отвергнут)": st["duplicates"] == 1,
        "D2 applied=1 (≤1 — инвариант)": st["applied"] == 1,
        "D3 claims=1 (нет двойного обогащения)": len(sess.claims) == 1,
        "D4 enqueued=1 (не 2)": st["enqueued"] == 1,
    }


def group_e() -> Dict[str, bool]:
    """E: не-wired при ON — экстракция пропущена (не inline!), placeholder
    записан, тик не упал: INV-LLM-LOOP-EXILE by construction."""
    os.environ["D8P_ENABLED"] = "1"
    _reset_intelligence_queue()
    mem, tick, ext = SessionMemory(), [100], RecordingExtractor(_make_update())
    sub = _make_subscriber(mem, ext, lambda: tick[0])
    _publish(sub)  # без wire — громкий warning внутри, без исключения
    sess = _sess(mem)
    return {
        "E1 extractor не вызван (0 LLM-вызовов)": ext.calls == 0,
        "E2 placeholder записан": any(
            t.speaker == SPEAKER and t.intent == "dialogue" for t in sess.buffer
        ),
        "E3 не упало (publish вернулся)": True,
    }


_GROUPS = [("A", group_a), ("B", group_b), ("C", group_c), ("D", group_d), ("E", group_e)]


def main() -> int:
    print("=" * 70)
    print("🧠 SUPERBOX d8p_intelligence_test — Intelligence Queue (ADR-O-382)")
    print("Фальсификаторы: R1-семантика (placeholder немедленно) · loop-exile ·")
    print("STALE-наблюдаемость · Q5 ≤1 APPLIED · не-wired деградация.")
    print("=" * 70)
    failed: List[str] = []
    try:
        for name, fn in _GROUPS:
            checks = fn()
            for label, ok in checks.items():
                print(f"[{name}] {'PASS' if ok else 'FAIL'} | {label}")
                if not ok:
                    failed.append(f"{label}")
    finally:
        os.environ.pop("D8P_ENABLED", None)
        os.environ.pop("D8P_MAX_AGE_TICKS", None)
        _reset_intelligence_queue()
    print("-" * 70)
    if failed:
        print(f"ИТОГ D8P: ❌ ПРОВАЛ ({len(failed)}):")
        for f in failed:
            print(f"  🔴 {f}")
        return 1
    print("ИТОГ D8P: ✅ ЗАКРЫТО (A/B/C/D/E все PASS — метрика: session+счётчики+трейс)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
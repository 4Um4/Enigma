# ENIGMA — ДИАЛОГОВАЯ СИСТЕМА: ПАМЯТЬ НИТИ И COMMITMENT-СЛОЙ

**Дата:** 2026-07-28
**Версия:** 1.0
**Цель:** Превратить монологи в диалоги. NPC должен помнить: с кем говорит, о чём, какие claims сделаны, какие open_questions висят, и продолжать нить через 5-10-20 ходов, через переключение темы, через отход и возвращение.

**Принцип:** Контекст диалога = Python-буфер с жёсткой структурой, не «модель сама помнит». LLM только verbalize — не хранит правду. Если STM block не попал в промпт — NPC не может говорить (hard contract).

**Контекст:** Текущий код V.0.5.3.6.2 имеет `DialogueSession` (max 5 реплик, keyword topic), но:
- Реплика игрока **никогда** не пишется в STM (dead code в `dm_phase.py:131`)
- NPC↔NPC `DialogueExecutor` не включает STM в LLM-промпт (write-only)
- `get_stm_prompt_block` — dead code (никто не вызывает)
- Любой «move» action стирает всю STM кампании
- Нет `claims`, `open_questions`, `thread_id`, `dialogue_partner`
- Topic детектируется keyword'ами — «метель» не в словаре → topic=None

---

## §0. ФИЛОСОФИЯ — ПЯТЬ ПРИНЦИПОВ

### Принцип 1: Контекст диалога = Python-буфер, не «модель помнит»

LLM получает в промпте:
- Последние N реплик (кто сказал, что сказал, кому адресовано)
- Текущая тема + confidence
- Открытые claims («вчера была метель»)
- Открытые вопросы («где ключ от подвала?»)
- Кто последний говорил

LLM возвращает реплику. Python извлекает из неё новые claims/questions (через structured-output LLM call, кэшированный). Python хранит. LLM не хранит ничего между вызовами.

### Принцип 2: Hard contract — нет STM в промпте → нельзя говорить

Если для данного dialogue event нет STM block (пустой buffer или не передан) — LLM не вызывается. NPC молчит, ИЛИ fallback на «approach/greeting» intent (установить контакт). Это убирает паттерн «NPC ляпнул случайную тему».

### Принцип 3: Claims и open_questions — структурная память нити

`Claim` — утверждение, сделанное в диалоге: «Торнин знает о тайном ходе», «метель была сильной». С confidence, status (open/contested/confirmed/withdrawn).

`OpenQuestion` — вопрос, на который нет ответа: «Где ключ от подвала?» Со status answered/unanswered.

LLM-промпт включает claims и open_questions. LLM-ответ обновляет их (новые claims, answers на open_questions, новые questions). Нить живёт, пока есть открытые claims/questions, даже после 20 ходов о погоде.

### Принцип 4: Per-pair session, не per-NPC

Сейчас session keyed `campaign_id:npc_id`. Когда NPC A говорит с player, потом с NPC B — topic смешивается. Правильно: `campaign_id:npc_a:npc_b` (сортированный tuple) для NPC↔NPC, `campaign_id:npc_id:player` для player↔NPC. Каждый dialogue partner — своя нить.

### Принцип 5: Dialogue consolidation — STM → EventMemory на завершении

При окончании диалога (ушёл, timeout, явное «пока») — STM не просто стирается. Запускается LLM-суммаризация: «Player и Торнин обсудили подвал 8 ходов; key claim: есть тайный ход; open question: кто имеет ключ». Создаётся EventMemory в `narrative_cache`. NPC может на следующей сессии сказать «мы с тобой вчера про подвал говорили».

---

## §1. ТЕКУЩЕЕ СОСТОЯНИЕ — 12 ТОЧЕК РАЗРЫВА

Аудит V.0.5.3.6.2 нашёл 12 конкретных мест, где нить теряется:

| # | Файл:Line | Что сломано | Эффект |
|---|---|---|---|
| **L1** | `dm_phase.py:122-138` | Player-turn STM write — DEAD CODE. `_sem_payload = {}` инициализирован пустым, `_sem_payload.get("target_id")` → None, `add_dialogue_turn` никогда не вызывается | Реплика игрока НИКОГДА не пишется в STM |
| **L2** | `dm_agent.py:221-226` | DM LLM видит `npc_recent_speech` = mixed last-5 lines от ВСЕХ NPC сессий, не targeted NPC | Контекст размывается другими NPC |
| **L3** | `memory_manager.py:275-289` | `get_recent_speech_all_npcs` смешивает все NPC sessions в flat list | DM не знает, какой NPC сказал что кому |
| **L4** | `dialogue_session.py:53-77` | Topic — keyword-only. «метель», «погода», «снег» не в словаре → topic=None или «наблюдение» | Тема не детектируется |
| **L5** | `dialogue_session.py:98-104`, `dm_phase.py:158-159` | Любой "move"/"stealth" action → `clear_all_dialogue_sessions`. Нет time/distance-based expiry, нет consolidation | Ходьба внутри комнаты стирает всю STM кампании |
| **L6** | `dialogue_executor.py:100-156` | NPC↔NPC LLM call — НЕТ STM block, НЕТ last_speaker, НЕТ topic thread. Только static fields + `npc_npc_context` (всегда "" из-за L7) | NPC↔NPC диалог = монологи |
| **L7** | `task_scheduler.py:266-272` | `DialogueRequest` реконструируется без `npc_npc_context` (поле теряется при JSON roundtrip) | Long-term memory context не доходит до executor |
| **L8** | `npc_dialogue_subscriber.py:108-129` | NPC_A→NPC_B: только STM listener (B) обновляется. Speaker (A) own STM не обновляется | NPC A не помнит, что сам сказал |
| **L9** | `npc_dialogue_subscriber.py:108-176` | NPC↔NPC canonical path НЕ вызывает `MemoryManager.apply()` → нет EventMemory в `narrative_cache` | Диалог evaporates при clear |
| **L10** | `verbalization_context.py:80-87`, `npc_tick_pipeline.py:791-881` | `VerbalizationContext` имеет `stm_buffer`, `recalled_facts`, `npc_npc_context`, `suppressed_secrets` — но `build_verbalization_context` НИКОГДА не вызывается в production | Весь recall() для verbalization wasted |
| **L11** | `dm_contract_builder.py:142-146` | `add_npc_l2_memory` определён, но НИКТО не вызывает — DM никогда не видит `recall()` results | L2 memory не в промпте |
| **L12** | `memory_manager.py:71-76` | `clear_dialogue_session` стирает STM без consolidation в EventMemory | Диалог испаряется без следа |

---

## §2. НОВАЯ АРХИТЕКТУРА — DIALOGUE SESSION v2

### 2.1. Структура данных

```python
# backend/app/services/memory/dialogue_session.py (v2)

from dataclasses import dataclass, field
from typing import Optional, List, Tuple
import time


@dataclass
class Claim:
    """Утверждение, сделанное в диалоге."""
    text: str                          # "Торнин знает о тайном ходе"
    speaker: str                       # кто утверждал
    confidence: float                  # 0..1 — LLM-assigned
    timestamp_tick: int
    status: str = "open"               # "open" | "contested" | "confirmed" | "withdrawn"
    contested_by: Optional[str] = None # кто оспорил


@dataclass
class OpenQuestion:
    """Вопрос, на который нет ответа."""
    text: str                          # "Где ключ от подвала?"
    asked_by: str
    addressed_to: str                  # к кому обращён
    timestamp_tick: int
    answered: bool = False
    answer_text: str = ""
    answered_by: Optional[str] = None
    answer_tick: Optional[int] = None


@dataclass
class DialogueTurn:
    """Расширенная реплика — с target/intent/tone/tick."""
    speaker: str
    text: str
    target_id: str = ""                # кому адресовано
    intent: str = ""                  # "question" | "claim" | "answer" | "reflexive" | "greeting"
    tone: str = ""                     # "ANGRY" | "FRIENDLY" | "NEUTRAL" | "SUSPICIOUS"
    tick: int = 0


@dataclass
class DialogueSession:
    """Сессия диалога с structured thread memory."""
    npc_id: str                        # владелец сессии
    partner_id: str = ""               # текущий партнёр ("player" или npc_id)
    thread_id: str = ""                # ID нити (генерируется при старте диалога)
    
    # Скользящее окно реплик
    buffer: List[DialogueTurn] = field(default_factory=list)
    max_size: int = 8                  # bump с 5 до 8
    
    # Topic
    topic: Optional[str] = None
    topic_confidence: float = 0.0      # LLM-assigned 0..1
    topic_history: List[Tuple[str, int]] = field(default_factory=list)  # [(topic, tick)]
    
    # Structured thread memory — НОВОЕ
    claims: List[Claim] = field(default_factory=list)
    open_questions: List[OpenQuestion] = field(default_factory=list)
    
    # Существующие поля
    _pressure_by_topic: dict = field(default_factory=dict)
    last_pressure_type: str = ""
    emotional_markers: List[str] = field(default_factory=list)
    
    # Lifecycle
    started_tick: int = 0
    last_activity_tick: int = 0
    ended: bool = False
    
    # Методы
    def add_turn(self, speaker: str, text: str, target_id: str = "",
                 intent: str = "", tone: str = "", tick: int = 0):
        self.buffer.append(DialogueTurn(
            speaker=speaker, text=text, target_id=target_id,
            intent=intent, tone=tone, tick=tick
        ))
        if len(self.buffer) > self.max_size:
            self.buffer.pop(0)
        self.last_activity_tick = tick
    
    def add_claim(self, text: str, speaker: str, confidence: float, tick: int):
        self.claims.append(Claim(
            text=text, speaker=speaker, confidence=confidence,
            timestamp_tick=tick
        ))
        # Keep only last 10 open claims
        open_claims = [c for c in self.claims if c.status == "open"]
        if len(open_claims) > 10:
            # Mark oldest as "withdrawn" (forgotten)
            for c in open_claims[:-10]:
                c.status = "withdrawn"
    
    def add_open_question(self, text: str, asked_by: str, addressed_to: str, tick: int):
        self.open_questions.append(OpenQuestion(
            text=text, asked_by=asked_by, addressed_to=addressed_to,
            timestamp_tick=tick
        ))
    
    def answer_question(self, idx: int, answer_text: str, answered_by: str, tick: int):
        if 0 <= idx < len(self.open_questions):
            q = self.open_questions[idx]
            q.answered = True
            q.answer_text = answer_text
            q.answered_by = answered_by
            q.answer_tick = tick
    
    def to_prompt_block_rich(self) -> str:
        """Расширенный блок для LLM-промпта — buffer + topic + claims + open_questions."""
        lines = []
        lines.append("[Краткая память — текущий разговор]")
        if self.partner_id:
            lines.append(f"Партнёр: {self.partner_id}")
        if self.topic:
            lines.append(f"Тема: {self.topic} (confidence: {self.topic_confidence:.2f})")
        if self.topic_history:
            recent = self.topic_history[-3:]
            lines.append(f"Предыдущие темы: {', '.join(t for t, _ in recent)}")
        lines.append("")
        lines.append("Последние реплики:")
        for turn in self.buffer[-5:]:
            target_marker = f" → {turn.target_id}" if turn.target_id else ""
            intent_marker = f" [{turn.intent}]" if turn.intent else ""
            lines.append(f"  {turn.speaker}{target_marker}{intent_marker}: {turn.text}")
        if self.claims:
            open_claims = [c for c in self.claims if c.status == "open"][-5:]
            if open_claims:
                lines.append("")
                lines.append("Активные утверждения (claims):")
                for c in open_claims:
                    lines.append(f"  • {c.text} (от {c.speaker}, confidence {c.confidence:.2f})")
        if self.open_questions:
            unanswered = [q for q in self.open_questions if not q.answered][-3:]
            if unanswered:
                lines.append("")
                lines.append("Открытые вопросы:")
                for q in unanswered:
                    lines.append(f"  ? {q.text} (спросил {q.asked_by} → {q.addressed_to})")
        return "\n".join(lines)
    
    def consolidate_to_event_memory_summary(self) -> str:
        """Для EventMemory на завершении диалога."""
        summary_parts = []
        summary_parts.append(f"Диалог с {self.partner_id} ({len(self.buffer)} реплик)")
        if self.topic:
            summary_parts.append(f"Тема: {self.topic}")
        if self.claims:
            open = [c for c in self.claims if c.status == "open"]
            if open:
                summary_parts.append("Утверждения: " + "; ".join(c.text for c in open[:3]))
        if self.open_questions:
            unanswered = [q for q in self.open_questions if not q.answered]
            if unanswered:
                summary_parts.append("Без ответа: " + "; ".join(q.text for q in unanswered[:2]))
        return ". ".join(summary_parts) + "."
```

### 2.2. Per-pair session keying

```python
# backend/app/services/memory/memory_manager.py (extend)

def get_dialogue_session(self, campaign_id: str, npc_id: str) -> DialogueSession:
    """Player↔NPC session: key = campaign_id:npc_id:player"""
    key = f"{campaign_id}:{npc_id}:player"
    if key not in self._dialogue_sessions:
        session = DialogueSession(npc_id=npc_id, partner_id="player")
        self._dialogue_sessions[key] = session
    return self._dialogue_sessions[key]

def get_dialogue_session_pair(self, campaign_id: str, npc_a: str, npc_b: str) -> DialogueSession:
    """NPC↔NPC session: key = campaign_id:pair:{sorted_a_b}. 
    Sorted for determinism — A→B and B→A share session."""
    a, b = sorted([npc_a, npc_b])
    key = f"{campaign_id}:pair:{a}:{b}"
    if key not in self._dialogue_sessions:
        # Owner is the "primary" NPC (lower id), partner is the other
        session = DialogueSession(npc_id=a, partner_id=b)
        self._dialogue_sessions[key] = session
    return self._dialogue_sessions[key]

def get_stm_prompt_block_for_target(self, campaign_id: str, target_npc_id: str, 
                                      partner_id: str = "player") -> str:
    """Возвращает STM block для конкретного target NPC + partner."""
    session = self.get_dialogue_session(campaign_id, target_npc_id) if partner_id == "player" \
              else self.get_dialogue_session_pair(campaign_id, target_npc_id, partner_id)
    return session.to_prompt_block_rich()
```

### 2.3. Thread ID — генерация и propagation

```python
import uuid

def generate_thread_id() -> str:
    return f"thread-{uuid.uuid4().hex[:8]}"

# Когда начинается новый диалог:
# - Player впервые обратился к NPC (нет session, или session ended=True)
# - NPC инициирует разговор с другим NPC (нет pair session, или pair session ended=True)
# Генерируем thread_id, сохраняем в session.thread_id

# Propagation:
# CommunicationIntent.thread_id → DialogueRequest.thread_id → 
# QueuedTask.payload["thread_id"] → DialogueExecutor → STM block
```

---

## §3. 12 КОНКРЕТНЫХ ФИКСОВ

### BUG-DL-01 ★★★ CRITICAL — Player-turn STM write dead code

**Файл:** `backend/app/services/game_loop/dm_phase.py:122-138`

```python
# Сейчас:
_sem_payload = {}  # line 122 — пустой
# ...
_stm_target_id = _sem_payload.get("target_id")  # line 131 — всегда None
if _raw_type in ("dialogue", "player_interacts") and _stm_target_id:
    game_loop.memory_manager.add_dialogue_turn(...)  # НИКОГДА не вызывается
```

**Fix:**
```python
# Line 131 — REPLACE:
_stm_target_id = shared_context.player_target_id  # уже установлен на line 54

# Line 132-138 — добавить player speech в STM с intent/tone/tick
if _raw_type in ("dialogue", "player_interacts") and _stm_target_id:
    game_loop.memory_manager.add_dialogue_turn(
        campaign_id=campaign_id,
        npc_id=_stm_target_id,
        speaker="player",
        text=action_text,
        target_id=_stm_target_id,
        intent="dialogue",  # TODO: LLM-classify
        tone="",  # TODO: LLM-classify
        tick=current_tick,
    )
```

### BUG-DL-02 ★★★ CRITICAL — NPC↔NPC DialogueExecutor не включает STM

**Файл:** `backend/app/services/execution/dialogue_executor.py:100-156`

```python
# Сейчас: только static fields + npc_npc_context (всегда "" из-за BUG-DL-04)
# NO STM BLOCK
```

**Fix:** Inject STM block через `memory_manager.get_stm_prompt_block`:
```python
def __init__(self, router=None, context_provider=None, belief_store=None, 
             memory_manager=None):  # NEW
    ...
    self._memory_manager = memory_manager

# В _generate_with_router, AFTER npc_npc_context block:
_stm_text = ""
if self._memory_manager is not None and task.campaign_id:
    _stm_text = self._memory_manager.get_stm_prompt_block_pair(
        task.campaign_id, task.owner_id, req.target_id
    )
if _stm_text:
    user_prompt += f"\n{_stm_text}\n\nСкажи свою реплику:"
else:
    # NO STM → не может говорить (Hard contract)
    raise DialogueContractViolation(
        f"NPC {task.owner_id} cannot speak to {req.target_id} without STM block. "
        "Emit approach/greeting intent first."
    )
```

### BUG-DL-03 ★★★ CRITICAL — DM LLM видит mixed speech, не targeted NPC

**Файлы:** `backend/app/agents/dm_agent.py:221-226`, `backend/app/services/game_loop/dm_phase.py:90-93`

```python
# Сейчас:
_recent_speech = (context or {}).get("npc_recent_speech", [])  # mixed from all NPCs
if _recent_speech:
    builder.add_npc_stm("\n".join(_recent_speech))
```

**Fix:** Добавить per-targeted NPC STM block:
```python
# В dm_phase.py, ПОСЛЕ extract_player_target:
_targeted_stm = ""
if shared_context.player_target_id:
    _targeted_stm = game_loop.memory_manager.get_stm_prompt_block_for_target(
        campaign_id, shared_context.player_target_id, partner_id="player"
    )
shared_context.npc_stm_block_targeted = _targeted_stm

# В dm_agent.py, в _build_contract:
_targeted_stm = (context or {}).get("npc_stm_block_targeted", "")
if _targeted_stm:
    builder.add_npc_stm_targeted(shared_context.player_target_id, _targeted_stm)
# Mixed speech — оставить для контекста «что говорят другие NPC», но пометить
if _recent_speech:
    builder.add_npc_stm("\n".join(_recent_speech))  # ambient
```

### BUG-DL-04 ★★ HIGH — `npc_npc_context` теряется при JSON roundtrip

**Файл:** `backend/app/services/game_loop/task_scheduler.py:266-272`

```python
# Сейчас:
req = DialogueRequest(
    topic=payload_dict.get("topic", ""),
    target_id=payload_dict.get("target_id", ""),
    exposure=...,
    intent_type=...,
    emotional_state=...,
    # npc_npc_context НЕ включён
)
```

**Fix:**
```python
req = DialogueRequest(
    topic=payload_dict.get("topic", ""),
    target_id=payload_dict.get("target_id", ""),
    exposure=ExposureLevel(semantic=payload_dict.get("exposure_semantic", "normal")),
    intent_type=payload_dict.get("intent_type", "talk"),
    emotional_state=_emotional_state,
    npc_npc_context=payload_dict.get("npc_npc_context", ""),  # NEW
    thread_id=payload_dict.get("thread_id", ""),  # NEW
)
```

### BUG-DL-05 ★★ HIGH — Speaker STM не обновляется при NPC↔NPC

**Файл:** `backend/app/services/events/npc_dialogue_subscriber.py:108-129`

```python
# Сейчас: только listener's STM
self.memory.add_dialogue_turn(campaign_id, npc_id=listener, speaker, text)
```

**Fix:** Symmetric write — и listener, и speaker STM:
```python
# Pair session для обоих
pair_session = self.memory.get_dialogue_session_pair(_campaign_id, speaker, listener)
pair_session.add_turn(
    speaker=speaker, text=text, target_id=listener,
    intent="dialogue", tick=current_tick
)

# Listener's per-NPC session (для player-facing perception)
self.memory.add_dialogue_turn(
    campaign_id=_campaign_id, npc_id=listener, 
    speaker=speaker, text=text,
    target_id=listener, intent="dialogue", tick=current_tick
)

# Speaker's own session (NEW — чтобы NPC помнил, что сам сказал)
self.memory.add_dialogue_turn(
    campaign_id=_campaign_id, npc_id=speaker,
    speaker=speaker, text=text,
    target_id=listener, intent="dialogue", tick=current_tick
)
```

### BUG-DL-06 ★★ HIGH — NPC_SPOKE не создаёт EventMemory

**Файл:** `backend/app/services/events/npc_dialogue_subscriber.py:108-176`

```python
# Сейчас: только L1Chronicle.commit_tick_buffer, НЕТ MemoryManager.apply()
```

**Fix:** Создать `DialogueMemorySubscriber` (новый файл) который вызывает `MemoryManager.apply()`:
```python
# backend/app/services/events/dialogue_memory_subscriber.py (NEW)
class DialogueMemorySubscriber:
    """Каждая реплика → EventMemory в narrative_cache обоих участников."""
    
    def handle(self, event):
        if event.event_type not in (EventType.NPC_SPOKE, EventType.PLAYER_SPOKE):
            return
        
        speaker = event.source
        listener = event.payload.get("target_id", "")
        text = event.payload.get("content", "")
        topic = event.payload.get("topic", "")
        
        # Создать EventMemory для speaker
        self.memory_manager.apply(EventDTO(
            event_type="dialogue_line",
            source=speaker,
            target=listener,
            summary=text,
            importance=0.3,  # default, LLM может повысить
            tags=("dialogue", topic) if topic else ("dialogue",),
        ), campaign_id=...)
        
        # Создать EventMemory для listener (если есть)
        if listener:
            self.memory_manager.apply(EventDTO(
                event_type="dialogue_line",
                source=listener,
                target=speaker,
                summary=f"Услышал от {speaker}: {text}",
                importance=0.3,
                tags=("dialogue", topic) if topic else ("dialogue",),
            ), campaign_id=...)
```

Зарегистрировать в `game_loop/__init__.py:_register_subscribers` рядом с `NpcDialogueSubscriber`.

### BUG-DL-07 ★★ HIGH — `clear_dialogue_session` без consolidation

**Файл:** `backend/app/services/memory/memory_manager.py:71-76`

```python
# Сейчас:
def clear_dialogue_session(self, campaign_id: str, npc_id: str) -> None:
    session = self._dialogue_sessions.pop(key, None)
    if session is not None:
        session.clear()
```

**Fix:** Consolidation в EventMemory перед discard:
```python
def clear_dialogue_session(self, campaign_id: str, npc_id: str, 
                            partner_id: str = "player") -> None:
    key = f"{campaign_id}:{npc_id}:{partner_id}"
    session = self._dialogue_sessions.get(key)
    if session is None:
        return
    
    # CONSOLIDATION: создать EventMemory summary если было >= 2 реплик
    if session.buffer and len(session.buffer) >= 2:
        summary = session.consolidate_to_event_memory_summary()
        self.apply(EventDTO(
            event_type="dialogue_consolidated",
            source=npc_id,
            target=partner_id,
            summary=summary,
            importance=0.4 + len(session.buffer) * 0.05,  # длинный диалог важнее
            tags=("dialogue", session.topic or "unknown", "consolidated"),
        ), campaign_id=campaign_id)
    
    session.clear()
    self._dialogue_sessions.pop(key, None)
```

### BUG-DL-08 ★★ HIGH — Любой "move" action стирает всю STM кампании

**Файл:** `backend/app/services/game_loop/dm_phase.py:158-159`

```python
# Сейчас:
if _raw_type in ("move", "stealth"):
    game_loop.memory_manager.clear_all_dialogue_sessions(campaign_id)
```

**Fix:** Distance + time-based expiry, не «любой move»:
```python
# Удалить строку 158-159 полностью.
# Добавить в idle_tick конец (раз в N тиков):
def _sweep_stale_dialogue_sessions(self, current_tick: int):
    """Периодически (каждые 30 тиков) чистим session'ы без активности > 60 тиков."""
    for key, session in list(self._dialogue_sessions.items()):
        if current_tick - session.last_activity_tick > 60:
            # consolidation перед clear
            self.clear_dialogue_session(...)
```

Дополнительно: clear только при реальной смене локации (не внутри той же):
```python
# В dm_phase.py:
if _raw_type in ("move", "stealth"):
    _new_loc = scene_state.get("location_id", "")
    _old_loc = (shared_context.scene_state or {}).get("location_id", "")
    if _new_loc and _old_loc and _new_loc != _old_loc:
        # Сцена сменилась — clear all STM с consolidation
        game_loop.memory_manager.clear_all_dialogue_sessions_with_consolidation(campaign_id)
```

### BUG-DL-09 ★★ HIGH — Keyword-only topic, «метель» не в словаре

**Файлы:** `backend/app/services/memory/dialogue_session.py:53-77`, `backend/app/services/npc/topic_extractor.py:85-111`

**Fix 1 (быстрый):** Расширить keyword vocabulary:
```python
# Добавить в _KEYWORDS:
"метель": "weather", "погода": "weather", "снег": "weather", 
"дождь": "weather", "ветер": "weather", "холод": "weather", 
"жара": "weather", "мороз": "weather", "вьюга": "weather",
"еда": "food", "еда": "food", "пить": "food", "вино": "food",
"семья": "family", "жена": "family", "муж": "family", "дети": "family",
"религия": "religion", "бог": "religion", "храм": "religion",
"магия": "magic", "заклинание": "magic",
"политика": "politics", "король": "politics", "власть": "politics",
"оружие": "weapons", "меч": "weapons", "щит": "weapons",
"снаряжение": "gear", "броня": "gear",
# ... +20-30 keywords
```

**Fix 2 (правильный):** LLM-based topic extraction для NPC replies (см. §4.2):
```python
def extract_dialogue_update(stm_before: str, new_turn: str, partner: str) -> DialogueUpdate:
    """LLM structured output: {topic, topic_confidence, new_claims, 
    answered_questions, raised_questions, last_speaker_intent}"""
```

### BUG-DL-10 ★★ HIGH — `VerbalizationContext` dead code

**Файлы:** `backend/app/services/verbalization/verbalization_context.py:80-87`, `backend/app/services/npc/npc_tick_pipeline.py:791-881`

`build_verbalization_context` определён, но никогда не вызывается в production. Comment: «В execution path вызов удалён».

**Fix:** Wire `build_verbalization_context` в `DialogueExecutor._generate_with_router`:
```python
# В dialogue_executor.py, заменить dict-based prompt на VerbalizationContext-based:
_ctx = build_verbalization_context(
    npc_state=task.owner_state,
    memory_manager=self._memory_manager,
    target_id=req.target_id,
    topic=req.topic,
    thread_id=req.thread_id,
)
user_prompt = self._build_prompt_from_context(_ctx)
```

### BUG-DL-11 ★ MEDIUM — `add_npc_l2_memory` никогда не вызывается

**Файл:** `backend/app/services/verbalization/dm_contract_builder.py:142-146`

**Fix:** Wire в `dm_agent._build_contract`:
```python
# После add_npc_stm:
if shared_context.player_target_id:
    _recall_results = game_loop.memory_manager.recall(
        narrative_cache=npc_state.narrative_cache,
        trigger_tags=("dialogue", session.topic or ""),
        target_npc_id=shared_context.player_target_id,
        limit=3,
    )
    if _recall_results:
        _memory_block = "\n".join(f"• {m.summary}" for m in _recall_results)
        builder.add_npc_l2_memory(_memory_block)
```

### BUG-DL-12 ★ MEDIUM — Нет game-time TTL для `_recent_dialogues`

**Файл:** `backend/app/services/game_loop/task_scheduler.py:49, 61-71`

```python
# Сейчас: self._dialogue_ttl = 10.0  # wall-clock seconds
# 10 секунд реального времени истекают независимо от game pace
```

**Fix:** Game-time TTL:
```python
self._dialogue_ttl_game_seconds = 60.0  # 1 минута игрового времени

def get_recent_dialogues(self, current_game_time: float) -> list:
    self._recent_dialogues = [
        d for d in self._recent_dialogues
        if current_game_time - d.get("game_time", 0.0) < self._dialogue_ttl_game_seconds
    ]
    return self._recent_dialogues

# При append (line 234-244):
_dlg_entry = {
    "speaker_id": ev.source,
    "target_id": ev.payload.get("target_id", ""),
    "text": ev.payload.get("text", ""),
    "timestamp": time.time(),  # для UI staleness
    "game_time": scene_state.get("game_time_seconds", 0.0),  # для response_targets
}
```

---

## §4. НОВЫЕ ФАЙЛЫ

### 4.1. `backend/app/services/memory/dialogue_consolidator.py` (NEW)

```python
"""Dialogue consolidation: STM → EventMemory summary при завершении диалога."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class DialogueConsolidator:
    """Создаёт EventMemory summary из законченной DialogueSession."""
    
    def __init__(self, llm_client=None):
        self._llm = llm_client
    
    def consolidate(self, session) -> Optional[str]:
        """Возвращает текст summary для EventMemory.
        
        Если LLM доступен — суммаризирует claims/open_questions/buffer.
        Если нет — fallback на structural summary (без LLM).
        """
        if not session.buffer or len(session.buffer) < 2:
            return None
        
        # Fallback (без LLM) — structural summary
        return session.consolidate_to_event_memory_summary()
    
    def consolidate_with_llm(self, session) -> Optional[str]:
        """LLM-суммаризация — для длинных диалогов (>= 5 реплик)."""
        if not session.buffer or len(session.buffer) < 5:
            return self.consolidate(session)
        
        if self._llm is None:
            return self.consolidate(session)
        
        prompt = self._build_summarization_prompt(session)
        try:
            summary = self._llm.complete(prompt, max_tokens=100)
            return summary.strip()
        except Exception as e:
            logger.warning(f"LLM consolidation failed: {e}, using structural fallback")
            return self.consolidate(session)
    
    def _build_summarization_prompt(self, session) -> str:
        lines = [
            "Суммаризуй диалог в 1-2 предложениях для долгой памяти NPC.",
            "Включи: тему, ключевые утверждения (claims), нерешённые вопросы.",
            "",
            f"Диалог с {session.partner_id}:",
        ]
        for turn in session.buffer:
            lines.append(f"  {turn.speaker}: {turn.text}")
        if session.claims:
            lines.append(f"Claims: {'; '.join(c.text for c in session.claims if c.status == 'open')}")
        if session.open_questions:
            unanswered = [q for q in session.open_questions if not q.answered]
            if unanswered:
                lines.append(f"Open questions: {'; '.join(q.text for q in unanswered)}")
        lines.append("")
        lines.append("Summary:")
        return "\n".join(lines)
```

### 4.2. `backend/app/services/memory/dialogue_update_extractor.py` (NEW)

```python
"""LLM-based extraction of topic/claims/questions из NPC reply."""
import json
import logging
from dataclasses import dataclass
from typing import List, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)


@dataclass
class DialogueUpdate:
    topic: Optional[str] = None
    topic_confidence: float = 0.0
    new_claims: List[dict] = None           # [{text, confidence}]
    answered_questions: List[int] = None   # indices in session.open_questions
    raised_questions: List[dict] = None    # [{text, addressed_to}]
    last_speaker_intent: str = ""           # "question" | "claim" | "answer" | "reflexive"


class DialogueUpdateExtractor:
    """Извлекает structured update из NPC reply через LLM.
    
    Кэшируется по hash(stm_before + new_turn) — одинаковые диалоги не пересчитываются.
    """
    
    def __init__(self, llm_client=None):
        self._llm = llm_client
    
    @lru_cache(maxsize=1000)
    def extract(self, stm_before_hash: str, new_turn: str, partner: str) -> DialogueUpdate:
        """Cached by (stm_before_hash, new_turn, partner)."""
        if self._llm is None:
            return DialogueUpdate()  # empty fallback
        
        prompt = self._build_extraction_prompt(stm_before_hash, new_turn, partner)
        try:
            response = self._llm.complete(
                prompt, 
                max_tokens=200,
                response_format={"type": "json_object"},
            )
            data = json.loads(response)
            return self._parse_update(data)
        except Exception as e:
            logger.warning(f"Dialogue update extraction failed: {e}")
            return DialogueUpdate()
    
    def _build_extraction_prompt(self, stm_before: str, new_turn: str, partner: str) -> str:
        return f"""Проанализируй новую реплику NPC в контексте диалога.
Верни JSON с обновлением STM.

Контекст до:
{stm_before}

Новая реплика (от {partner}):
{new_turn}

Верни JSON:
{{
  "topic": "string|null",
  "topic_confidence": 0.0-1.0,
  "new_claims": [{{"text": "...", "confidence": 0.0-1.0}}],
  "answered_questions": [0, 1, ...],
  "raised_questions": [{{"text": "...", "addressed_to": "..."}}],
  "last_speaker_intent": "question|claim|answer|reflexive|greeting"
}}

JSON:"""
    
    def _parse_update(self, data: dict) -> DialogueUpdate:
        return DialogueUpdate(
            topic=data.get("topic"),
            topic_confidence=float(data.get("topic_confidence", 0.0)),
            new_claims=data.get("new_claims", []),
            answered_questions=data.get("answered_questions", []),
            raised_questions=data.get("raised_questions", []),
            last_speaker_intent=data.get("last_speaker_intent", ""),
        )
```

### 4.3. `backend/app/services/events/dialogue_memory_subscriber.py` (NEW)

```python
"""Подписчик на NPC_SPOKE/PLAYER_SPOKE — создаёт EventMemory в narrative_cache."""
import logging
from app.services.events.event_types import EventType

logger = logging.getLogger(__name__)


class DialogueMemorySubscriber:
    """Каждая реплика → EventMemory в narrative_cache обоих участников.
    
    Без этого подписчика диалог живёт только в STM (RAM), теряется при clear.
    С подписчиком — каждая реплика закрепляется в долгой памяти NPC.
    """
    
    def __init__(self, memory_manager):
        self._mm = memory_manager
    
    def handle(self, event):
        if event.event_type not in (EventType.NPC_SPOKE, EventType.PLAYER_SPOKE):
            return
        
        speaker = event.source
        listener = event.payload.get("target_id", "")
        text = event.payload.get("content", "")
        topic = event.payload.get("topic", "")
        importance = float(event.payload.get("importance", 0.3))
        
        # EventMemory для speaker (я сказал X)
        self._mm.apply(EventDTO(
            event_type="dialogue_line",
            source=speaker,
            target=listener,
            summary=text,
            importance=importance,
            tags=("dialogue", topic) if topic else ("dialogue",),
        ), campaign_id=event.payload.get("campaign_id", ""))
        
        # EventMemory для listener (услышал X от speaker)
        if listener:
            self._mm.apply(EventDTO(
                event_type="dialogue_line",
                source=listener,
                target=speaker,
                summary=f"Услышал от {speaker}: {text}",
                importance=importance,
                tags=("dialogue", topic) if topic else ("dialogue",),
            ), campaign_id=event.payload.get("campaign_id", ""))
```

Регистрация в `game_loop/__init__.py:_register_subscribers`:
```python
# После NpcDialogueSubscriber:
self._event_bus.subscribe(EventType.NPC_SPOKE, self._dialogue_memory_subscriber)
self._event_bus.subscribe(EventType.PLAYER_SPOKE, self._dialogue_memory_subscriber)
```

---

## §5. ПОЛНАЯ СВЯЗКА ПАЙПЛАЙНА (после фиксов)

```
Player types "расскажи о метели"
  ↓
dm_phase.py:
  - extract_player_target → shared_context.player_target_id = "tavern_keeper_tornin"
  - BUG-DL-01 FIX: add_dialogue_turn(campaign, "tavern_keeper_tornin", 
                                       speaker="player", text="расскажи о метели",
                                       target_id="tavern_keeper_tornin", 
                                       intent="question", tick=N)
    → STM tornin:player session now has player's question
  - get_stm_prompt_block_for_target("tavern_keeper_tornin", "player") 
    → "[Краткая память — текущий разговор]\nПартнёр: player\nТема: weather\nПоследние реплики:\n  player → tavern_keeper_tornin [question]: расскажи о метели\n"
  - shared_context.npc_stm_block_targeted = ^^^

TickOrchestrator.execute:
  - Phase 4: response_targets["tavern_keeper_tornin"] = "player"
  - Phase 5: DecisionHub picks TALK intent for tornin
  - Phase 6: CommunicationIntent(thread_id="thread-abc123", target_id="tavern_keeper_tornin") 
    → QueuedTask with thread_id в payload

DialogueExecutor._generate_with_router:
  - BUG-DL-02 FIX: get_stm_prompt_block_pair(campaign, "tavern_keeper_tornin", "player")
    → STM block with player's "метель" question
  - LLM prompt: STM block + voice + backstory + npc_npc_context
  - LLM returns: "Метель? Да, в прошлом году была страшная. Три дня не выходили из домов."
  
DialogueMaterializer → NPC_SPOKE event:
  - BUG-DL-05 FIX: speaker (tornin) STM updated (symmetric)
  - BUG-DL-06 FIX: DialogueMemorySubscriber → EventMemory в narrative_cache tornin и player
  - BUG-DL-04 FIX: thread_id preserved через JSON roundtrip
  - DialogueUpdateExtractor.extract() → topic="weather", topic_confidence=0.9, 
    new_claims=[], raised_questions=[]
  - STM обновляется: topic="weather" (LLM-assigned), last_activity_tick=N

Следующий ход: "и что потом было?"
  - STM tornin:player имеет "метель" + "Метель? Да, в прошлом году..."
  - LLM видит оба turn, продолжает нить

5 ходов о погоде:
  - STM max_size=8 (bump с 5) — все 5 ходов + оригинальная "метель" сохраняются
  - topic_history показывает: [weather, weather, weather, weather, weather]

"так что насчёт той метели?" (6-й ход):
  - LLM видит в STM: оригинальную "метель" + 5 ходов о погоде + claims (если есть)
  - LLM продолжает нить, ссылается на "ту метель"

Player уходит (10 метров от tornin):
  - BUG-DL-08 FIX: distance-based check. Если тот же location — STM НЕ стирается
  - Если сменил location → clear с consolidation (BUG-DL-07 FIX):
    - DialogueConsolidator.consolidate() → 
      "Player и Торнин обсудили метель 6 реплик. Тема: weather. 
       Key claim: три дня не выходили из домов."
    - EventMemory создан в narrative_cache tornin
    - STM очищен

Player возвращается через 50 тиков:
  - recall(narrative_cache, trigger_tags=("dialogue", "weather"), target="player")
    → возвращает EventMemory с суммаризованным диалогом
  - BUG-DL-11 FIX: add_npc_l2_memory включает recall в LLM prompt
  - LLM: "А, мы с тобой о метели говорили. Помню."
```

---

## §6. ПОРЯДОК ВНЕДРЕНИЯ

### Этап 1 (1 день) — Critical fixes

Цель: Реплика игрока доходит до STM, NPC↔NPC executor видит STM.

| Баг | Время |
|---|---|
| **BUG-DL-01** Player-turn STM write | 30 мин |
| **BUG-DL-02** DialogueExecutor STM injection | 1 ч |
| **BUG-DL-03** DM LLM per-targeted STM | 1 ч |
| **BUG-DL-04** npc_npc_context roundtrip | 5 мин |
| **BUG-DL-08** Replace move-clear с distance/time | 30 мин |
| Тест: BUG-DL-01..04 fix verify | 30 мин |
| Тест: «метель» scenario — 5 погода + back to метель | 30 мин |

**Результат после Этапа 1:** Нить не теряется при переключении темы. Player speech в STM. NPC executor видит STM. «Монологи» → «диалоги».

### Этап 2 (1 день) — Structured thread memory

Цель: Claims/open_questions, LLM-based topic extraction.

| Баг | Время |
|---|---|
| Extend `DialogueSession` с Claim/OpenQuestion/DialogueTurn v2 | 1 ч |
| `DialogueUpdateExtractor` (§4.2) — LLM structured output | 1.5 ч |
| Wire extractor в `working_memory_tick` и `npc_dialogue_subscriber` | 1 ч |
| `to_prompt_block_rich()` — включает claims/open_questions | 30 мин |
| Тест: claims/open_questions scenario | 30 мин |

**Результат после Этапа 2:** NPC помнит «что мы установили» (claims) и «что ещё не закрыто» (open_questions).

### Этап 3 (1 день) — Long-term memory linkage

Цель: Диалоги закрепляются в narrative_cache, NPC помнит между сессиями.

| Баг | Время |
|---|---|
| **BUG-DL-06** DialogueMemorySubscriber (§4.3) | 1 ч |
| **BUG-DL-07** DialogueConsolidator (§4.1) + clear with consolidation | 1 ч |
| **BUG-DL-11** wire `add_npc_l2_memory` | 30 мин |
| Тест: dialogue → save → load → NPC помнит | 30 мин |

**Результат после Этапа 3:** NPC может сказать «мы с тобой вчера про подвал говорили» после save/load.

### Этап 4 (1 день) — Per-pair sessions + thread_id

Цель: NPC↔NPC нити изолированы, thread_id propagates.

| Баг | Время |
|---|---|
| `get_dialogue_session_pair` (§2.2) | 30 мин |
| **BUG-DL-05** symmetric write (speaker + listener) | 30 мин |
| Thread ID generation + propagation | 1 ч |
| **BUG-DL-10** wire `build_verbalization_context` | 1 ч |
| **BUG-DL-12** game-time TTL | 30 мин |
| Тест: NPC A↔B thread, NPC A↔C separate | 30 мин |

**Результат после Этапа 4:** NPC A может говорить с B и C параллельно, нити не смешиваются.

### Этап 5 (1 день) — Hard contract + polish

Цель: Hard contract «no STM → can't speak», weather keywords, polish.

| Баг | Время |
|---|---|
| **BUG-DL-09** weather keywords + LLM topic extraction | 1 ч |
| Hard contract в DialogueExecutor | 30 мин |
| Hard contract в dm_agent | 30 мин |
| Topic history display | 30 мин |
| **BUG-DL-12** (если остался) | 30 мин |
| Финальный canary: full dialogue continuity | 30 мин |

**Результат после Этапа 5:** Полная диалоговая система. NPC помнит нить через 20 ходов, через переключение темы, через отход и возвращение, через save/load.

**Итого:** 5 дней, ~25 часов.

---

## §7. CANARY ТЕСТЫ

### Canary 1: «Метель» scenario (главный)

```python
def test_meteor_scenario_thread_continuity():
    """Player спрашивает о метели → 5 ходов о погоде → back to метель → NPC помнит."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_meteor")
    
    # Turn 1: "расскажи о метели"
    response = game.player_action(target="tornin", text="расскажи о метели")
    
    # Verify STM written (BUG-DL-01)
    stm = game.memory_manager.get_dialogue_session("test_meteor", "tavern_keeper_tornin")
    assert any("метел" in t.text for t in stm.buffer if t.speaker == "player"), \
        "Player speech not in STM (BUG-DL-01 not fixed)"
    
    # Turns 2-6: weather talk
    for text in ["и что потом было?", "а сейчас какая погода?", 
                 "холодно сегодня", "будет ли тепло?", "как думаешь, метель закончилась?"]:
        game.player_action(target="tornin", text=text)
    
    # Verify STM has BOTH метель AND recent weather (max_size=8)
    stm = game.memory_manager.get_dialogue_session("test_meteor", "tavern_keeper_tornin")
    texts = [t.text for t in stm.buffer]
    assert any("метел" in t for t in texts), "Метель lost from STM — max_size too small?"
    
    # Turn 7: back to метель
    response = game.player_action(target="tornin", text="так что насчёт той метели?")
    
    # NPC should reference метель (LLM judgment, check via RCE)
    assert "метел" in response.lower() or "вьюг" in response.lower(), \
        "NPC forgot метель topic — STM not in LLM prompt (BUG-DL-02/03 not fixed)"
```

### Canary 2: NPC↔NPC pair thread

```python
def test_npc_npc_pair_thread():
    """NPC A говорит B, A отходит, A возвращается — оба помнят нить."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_pair")
    
    # Tick 1: NPC A (Borko) speaks to NPC B (Tornin)
    game.force_npc_dialogue(speaker="guard_borko", target="tavern_keeper_tornin",
                             text="Слышал, подвал опять шумит?")
    game.idle_tick()
    
    # Verify pair session created
    pair = game.memory_manager.get_dialogue_session_pair(
        "test_pair", "guard_borko", "tavern_keeper_tornin"
    )
    assert len(pair.buffer) > 0, "Pair session not created (BUG-DL-05 not fixed)"
    
    # Tick 2-10: Borko walks away
    for _ in range(10):
        game.idle_tick()
    
    # Tick 11: Borko returns
    # Pair session should still exist (no move-clear on NPC↔NPC)
    pair = game.memory_manager.get_dialogue_session_pair(
        "test_pair", "guard_borko", "tavern_keeper_tornin"
    )
    assert len(pair.buffer) > 0, "Pair session cleared during NPC absence"
    
    # Tornin's next reply should reference "подвал" thread
    response = game.force_npc_dialogue(speaker="tavern_keeper_tornin", 
                                         target="guard_borko", text="...")
    assert "подвал" in response.lower() or "шум" in response.lower(), \
        "Tornin forgot подвал thread — STM not in DialogueExecutor (BUG-DL-02 not fixed)"
```

### Canary 3: Walk away preserves STM (intra-location)

```python
def test_walk_away_preserves_stm():
    """Player ходит внутри таверны — STM НЕ стирается."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_walk")
    
    game.player_action(target="tornin", text="расскажи о метели")
    assert not game.memory_manager.get_dialogue_session("test_walk", "tavern_keeper_tornin").buffer == []
    
    # Player walks to bar counter (same location)
    game.player_action(text="подойду к барной стойке")
    
    # STM should NOT be cleared (BUG-DL-08 fix)
    stm = game.memory_manager.get_dialogue_session("test_walk", "tavern_keeper_tornin")
    assert len(stm.buffer) > 0, "STM cleared on intra-location move (BUG-DL-08 not fixed)"
```

### Canary 4: Cross-session memory

```python
def test_dialogue_survives_save_load():
    """Диалог → save → load → NPC помнит через recall()."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_persist")
    
    game.player_action(target="tornin", text="расскажи о подвал")
    game.player_action(target="tornin", text="что там хранится?")
    
    # Save
    save_data = game.serialize()
    
    # Load
    game2 = GameLoop(test_mode=True)
    game2.deserialize(save_data)
    
    # STM cleared (RAM only), но EventMemory должен быть в narrative_cache
    # (BUG-DL-06 fix: DialogueMemorySubscriber created EventMemory)
    tornin = game2.get_npc("tavern_keeper_tornin")
    basement_memories = [m for m in tornin.narrative_cache 
                          if "подвал" in m.summary.lower()]
    assert len(basement_memories) > 0, \
        "No EventMemory about подвал — BUG-DL-06 not fixed"
    
    # NPC should recall via add_npc_l2_memory (BUG-DL-11)
    response = game2.player_action(target="tornin", text="мы о чём-то говорили?")
    assert "подвал" in response.lower(), \
        "NPC doesn't recall previous session — BUG-DL-11 not fixed"
```

### Canary 5: Claims/OpenQuestions continuity

```python
def test_claims_open_questions_continuity():
    """Player задаёт вопрос → NPC отвечает → 10 ходов о другом → 
    NPC помнит open question."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_claims")
    
    # Turn 1: Player raises open question
    game.player_action(target="tornin", text="где ключ от подвала?")
    
    # Verify open_question registered (через DialogueUpdateExtractor)
    stm = game.memory_manager.get_dialogue_session("test_claims", "tavern_keeper_tornin")
    assert len(stm.open_questions) > 0, "Open question not registered"
    
    # Turns 2-11: about weather
    for _ in range(10):
        game.player_action(target="tornin", text="какая погода?")
    
    # Open question should still be in STM
    stm = game.memory_manager.get_dialogue_session("test_claims", "tavern_keeper_tornin")
    unanswered = [q for q in stm.open_questions if not q.answered]
    assert len(unanswered) > 0, "Open question lost after 10 turns"
    
    # Turn 12: back to ключ
    response = game.player_action(target="tornin", text="так где ключ?")
    assert "ключ" in response.lower(), "NPC forgot open question about ключ"
```

### Canary 6: Per-pair sessions isolation

```python
def test_per_pair_session_isolation():
    """NPC A говорит с B о X, с C о Y — нити изолированы."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_isolation")
    
    # NPC A talks to B about подвал
    game.force_npc_dialogue(speaker="guard_borko", target="tavern_keeper_tornin",
                             text="что в подвале?")
    # NPC A talks to C about trade
    game.force_npc_dialogue(speaker="guard_borko", target="merchant_goran",
                             text="как дела с торговлей?")
    
    # Pair sessions should be separate
    pair_AB = game.memory_manager.get_dialogue_session_pair(
        "test_isolation", "guard_borko", "tavern_keeper_tornin")
    pair_AC = game.memory_manager.get_dialogue_session_pair(
        "test_isolation", "guard_borko", "merchant_goran")
    
    assert pair_AB.topic != pair_AC.topic or \
           pair_AB.thread_id != pair_AC.thread_id, \
        "Pairs share topic/thread — not isolated"
```

### Canary 7: Hard contract — no STM → can't speak

```python
def test_hard_contract_no_stm_no_speak():
    """Если STM пустой — NPC не может говорить canonical dialogue."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_contract")
    
    # Force NPC dialogue without prior STM
    try:
        game.force_npc_dialogue(speaker="guard_borko", 
                                 target="tavern_keeper_tornin",
                                 text="should fail — no STM")
        assert False, "DialogueExecutor allowed dialogue without STM (hard contract not enforced)"
    except DialogueContractViolation:
        pass  # expected
```

### Canary 8: Game-time TTL для response_targets

```python
def test_game_time_ttl():
    """response_targets использует game_time, не wall-clock."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_ttl")
    
    game.player_action(target="tornin", text="привет")
    initial_game_time = game.scene_state["game_time_seconds"]
    
    # Advance 30 game seconds (well within 60s TTL)
    game.advance_game_time(30)
    
    # response_targets should still have tornin → player
    ctx = game.tick_orchestrator._last_ctx
    assert ctx.response_targets.get("tavern_keeper_tornin") == "player", \
        "response_targets expired too early (BUG-DL-12 wall-clock TTL)"
```

---

## §8. СВЯЗЬ С ДРУГИМИ ДОКУМЕНТАМИ

- **ENIGMA_CLOSURE_CONTRACT_v8.md** — основной список багов. Диалоговые баги добавлены как §14 (см. ниже).
- **ENIGMA_SELF_HEALING_SYSTEM.md** — runtime invariants. Hard contract «no STM → can't speak» — это invariant уровня 1.
- **ENIGMA_MAP_EDITOR_SMART_VALIDATION.md** — редактор карт. Не связан с диалоговой системой.

---

## §9. ИТОГ

**Принципы:**
1. Контекст диалога = Python-буфер, не «модель помнит»
2. Hard contract — нет STM в промпте → нельзя говорить
3. Claims и open_questions — структурная память нити
4. Per-pair session, не per-NPC
5. Dialogue consolidation — STM → EventMemory на завершении

**После внедрения:**
- NPC помнит «метель» через 20 ходов о погоде
- NPC↔NPC нить сохраняется, когда A отходит и возвращается
- NPC помнит claims/open_questions через переключение темы
- NPC может сказать «мы с тобой вчера про подвал говорили» после save/load
- Hard contract предотвращает «random topic blurts»
- Per-pair sessions изолируют диалоги NPC A↔B от A↔C

**План:** 5 дней, ~25 часов. Сначала critical fixes (1 день) → «метель» работает. Затем structured memory (1 день) → claims/questions. Затем long-term linkage (1 день) → save/load помнит. Затем per-pair + thread_id (1 день) → NPC↔NPC нити. Затем hard contract + polish (1 день).

---

*Этот документ — спецификация диалоговой системы. Принципы (Python-буфер, hard contract, claims/open_questions, per-pair, consolidation) — неизменны. Реализация может корректироваться.*

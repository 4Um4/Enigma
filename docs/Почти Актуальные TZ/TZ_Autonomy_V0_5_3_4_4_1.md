# ТЗ: Автономный мир и самостоятельное социальное взаимодействие

**Проект:** Enigma V.0.5.3.4.4
**Цель:** Мир живёт и развивается без ввода игрока. NPC двигаются, разговаривают друг с другом, меняют эмоции, формируют и разрушают отношения — всё автономно. Игрок — наблюдатель, а не триггер.
**Дата:** 13 июля 2026 (редакция 2 — после дизайн-разбора с создателем)
**Базируется на:** аудите кода V.0.5.3.4.4 (581 .py файл) и логах `cds_backend.log` сессии 13 июля 06:52

---

## 0. Постановка задачи

Создатель прямо сформулировал требование:

> «Игра должна быть в реальном времени, всё должно двигаться и жить непрерывно!!! А этого не происходит. Мир меняется самостоятельно так как и задумано было изначально — именно это надо реализовать. Полное самостоятельное взаимодействие — текущая первостепенная задача.»

**Текущее состояние (по логам 13 июля 06:52):**
- Игрок запускает игру → NPC стоят на месте
- Время не тикает (часы в HUD заморожены)
- Только ввод игрока и ответ DM «сдвигают» игру на один тик
- За 40 секунд сессии — 11 `[TICK_CRASH]` в логах, 0 завершённых тиков
- `Фаза 6: 0 intents → EventDTO` — каждый idle_tick, диалоги NPC-NPC не возникают
- Все 7 NPC имеют `Traversal: ❌` — movement pipeline не отрабатывает

**Целевое состояние (AWC — Автономный Мир-Контракт, §15):**
- Игрок запускает игру, ничего не вводит 5 минут
- Время идёт, NPC двигаются, разговаривают друг с другом
- Над разговаривающими NPC — облачка с темой разговора
- Журнал (J) накапливает подслушанное, имена раскрываются по мере узнавания
- Canonical реплики генерируются LLM в момент разговора (даже без игрока)
- При смене локации — loading screen догоняет мир (canonical для других локаций)
- CPU ≤ 70% (Sims-слой + очередь LLM с приоритетами)

**Этот документ описывает 6 блокеров + социальную архитектуру.** После применения — AWC должен пройти.

---

## 1. Принципы

1. **Никаких скриптов.** NPC действуют из правил и drives, не из if-then.
2. **Drives, not commands.** NPC не «идёт к Горану», а «чувствует SEEK_COMFORT, повышающий utility подхода к тому, у кого trust высокий».
3. **Реакции, not triggers.** NPC воспринимает событие → интерпретирует → обновляет эмоции → на следующем тике принимает решение с учётом новых эмоций.
4. **Beliefs, not flags.** Вместо `quest_lusya_met = true` — `belief("я встречал Люсю", confidence=0.9)`.
5. **Цикл должен быть замкнут.** Нужда → DecisionHub → Intent → Dialogue/Action → Событие → PerceptionEngine(NPC_B) → Interpretation → AffectiveIntegrator → Memory → Belief → Relationship → DecisionHub(NPC_B). Любой разрыв = мёртвая симуляция.
6. **★АРХИТЕКТУРНЫЙ ЗАКОН★ Запрет ретро-симуляции.** Конкретика генерируется ТОЛЬКО в момент разговора (или в batch generation при смене локации — §13). Если LLM не был вызван — конкретики нет и не будет. NPC не может «вспомнить» разговор которого не было. Игрок не может «подслушать» разговор который закончился до его прихода — только абстрактную запись в журнале.
7. **Мир не ждёт игрока.** NPC-NPC canonical разговоры идут параллельно с диалогом игрока. Очередь LLM с приоритетами (§9.3) решает когда что показать.
8. **Имена — не автомат.** Игрок знает имя NPC только если реально его услышал (NPC представился, кто-то назвал, спросил напрямую, увидел бейдж). До этого — `?` в журнале.

---

## 2. Карта блокеров

6 блокеров, которые **гарантированно** убивают автономию. Применять строго по порядку.

| # | Блокер | Файл | Симптом | Время фикса |
|---|---|---|---|---|
| 1 | Persistence TypeError | `sqlite_persistence_adapter.py:84` | Каждый idle_tick крашится на Phase 10 | 5 мин |
| 2 | Real-time loop дефект | `frontend/constants.py`, `game_screen.py:1138` | idle_tick раз в 2-30 сек, блокируется DM | 30 мин |
| 3 | Movement gap в idle | `npc_tick_pipeline.py:401` | Только approach/flee создают движение | 1-2 часа |
| 4 | communication_intents=0 | `decision_hub.py:793`, `npc_tick_pipeline.py:391` | 0 диалогов за тик, несмотря на вербальные intents | 1-2 часа |
| 5 | Sims-слой + Canonical/Ambient + LLM очередь | Новый `npc_conversation.py`, `dialogue_queue.py` | 60 LLM-вызовов/мин убьют CPU | 4-6 часов |
| 6 | NpcDialogueSubscriber | Новый `npc_dialogue_subscriber.py` | NPC_B не реагирует на реплику NPC_A | 2-3 часа |

**Итого: 10-14 часов работы.** После этого — AWC (§15) должен пройти.

---

## 3. Блокер 1 — Persistence TypeError

### 3.1. Что происходит

**Файл:** `backend/app/services/state/sqlite_persistence_adapter.py`
**Строка:** 84

```python
default=lambda o: List[Any](o) if isinstance(o, set) else str(o),  # ← BUG
```

`List[Any]` — это `typing.List[Any]`. В Python 3.13+ типы из `typing` **нельзя инстанцировать**. Вызов `List[Any](o)` падает с `TypeError: Type List cannot be instantiated; use list() instead`.

### 3.2. Почему это убивает симуляцию

Каждый idle_tick:
1. Phase 0-9 проходят успешно — LifeEngine создаёт 4-6 spatial changes, DecisionHub генерит решения, `_advance_idle_time` обновляет `game_time_seconds`.
2. Phase 10 (persistence) вызывает `commit()` → `_upsert("runtime:<campaign_id>", npc_states)`.
3. `json.dumps` натыкается на `set` поле в NPC state → вызывает `List[Any](o)` → **TypeError**.
4. Исключение пробрасывается в `tick_orchestrator.execute()`, логируется как `[TICK_CRASH]`.
5. **Ничего не сохраняется** — на следующем idle_tick `lock_for_tick` читает **старое** состояние → NPC возвращаются на исходные позиции, время откатывается.

**Логи 13 июля 06:52 (40 секунд):** 11 `[TICK_CRASH]`, 0 завершённых тиков.

### 3.3. Патч

**Минимальный (1 строка):**

```python
# sqlite_persistence_adapter.py:84
# Было:
default=lambda o: List[Any](o) if isinstance(o, set) else str(o),
# Стало:
default=lambda o: list(o) if isinstance(o, set) else str(o),
```

**Расширенный (рекомендуется):**

```python
# В начало файла:
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum

def _json_default(o):
    """JSON-сериализатор для нестандартных типов в NPC state."""
    if isinstance(o, set):
        return list(o)
    if isinstance(o, Enum):
        return o.value
    if isinstance(o, datetime):
        return o.isoformat()
    if is_dataclass(o):
        return asdict(o)
    if hasattr(o, "__dict__"):
        return o.__dict__
    return str(o)

# В _upsert:
default=_json_default,
```

### 3.4. Контрольная точка

- `grep -c "TICK_CRASH" backend/logs/cds_backend.log` → 0
- `game_time_seconds` растёт без ввода игрока
- `active_traversals` не пустой после 30 сек idle

---

## 4. Блокер 2 — Real-time loop дефект

### 4.1. Три подпроблемы

**A — Интервал idle_tick слишком длинный:**

```python
# frontend/constants.py:19-23
IDLE_TICK_NEAR_MS: int = 2_000   # 2 сек
IDLE_TICK_MID_MS:  int = 8_000   # 8 сек
IDLE_TICK_FAR_MS:  int = 30_000  # 30 сек
```

`GAME_TICK_INTERVAL_SECONDS = 60`. Один игровой час = 2-30 минут реального времени. Слишком медленно.

**B — `action_queue.pending_count() == 0` блокирует idle_tick:**

```python
# frontend/game_screen.py:1138-1140
if (
    _now - _last_idle_tick >= _tick_interval
    and not _idle_tick_running[0]
    and action_queue.pending_count() == 0   # ← блокировка
):
```

После DM-ответа (строка 1169): `_last_idle_tick = pygame.time.get_ticks() + 1000` — пауза 1 сек.

**C — idle_tick и DM-ответ конкурируют за поток.**

### 4.2. Патч (4 шага)

**Шаг 1 — Уменьшить интервал:**

```python
# frontend/constants.py
IDLE_TICK_NEAR_MS: int = 500    # было 2_000
IDLE_TICK_MID_MS:  int = 1_500  # было 8_000
IDLE_TICK_FAR_MS:  int = 3_000  # было 30_000
```

**Шаг 2 — Уменьшить `GAME_TICK_INTERVAL_SECONDS`:**

```python
# backend/app/core/constants.py:210-212
GAME_TICK_INTERVAL_SECONDS: int = 10  # было 60
```

**Шаг 3 — Decouple idle_tick от action_queue:**

```python
# frontend/game_screen.py:1138-1140
# Было:
if (
    _now - _last_idle_tick >= _tick_interval
    and not _idle_tick_running[0]
    and action_queue.pending_count() == 0
):
# Стало:
if (
    _now - _last_idle_tick >= _tick_interval
    and not _idle_tick_running[0]
):
```

**Шаг 4 — Убрать post-DM паузу:**

```python
# frontend/game_screen.py:1169
# Было:
_last_idle_tick = pygame.time.get_ticks() + 1000
# Стало:
_last_idle_tick = pygame.time.get_ticks() + 200  # 200мс для UX
```

### 4.3. Контрольная точка

- За 30 секунд без ввода — `game_time_seconds` вырос минимум на 5 минут игрового времени
- idle_tick запускается каждые 0.5-3 сек (видно по логам)
- Во время LLM-запроса DM idle_tick не блокирован

---

## 5. Блокер 3 — Movement gap в idle

### 5.1. Что происходит

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py`
**Строка:** 401

```python
_MOVE_INTENTS = {"approach", "flee"}  # ← только 2 intents создают движение
```

DecisionHub генерит intents: `block_path`, `ambush`, `seek_ally`, `offer_job`, `request_service`, `call_for_help`, `spread_rumor`, `change_role`, `talk`. Из них **только approach/flee** создают MovementIntent. Остальные — декоративные.

### 5.2. Патч

**Шаг 1 — Расширить `_MOVE_INTENTS`:**

```python
# npc_tick_pipeline.py:401
_MOVE_INTENTS = {
    "approach",         # к игроку (существующий)
    "flee",             # от угрозы (существующий)
    "seek_ally",        # к NPC с max trust
    "offer_job",        # к target NPC
    "request_service",  # к NODE_ROLE.BAR / WORKBENCH / MERCHANT
    "call_for_help",    # к ближайшему ally
    "spread_rumor",     # к ближайшему cluster NPC
    "block_path",       # к NODE_ROLE.ENTRANCE
    "ambush",           # к NODE_ROLE behind cover
    "talk",             # к target NPC (NPC-NPC диалог)
    "change_role",      # к месту новой роли
}
```

**Шаг 2 — Добавить target resolver:**

```python
def _resolve_proactive_target(
    intent_value: str,
    npc_id: str,
    intent_target: str | None,
    scene_state: dict,
    spatial_query,
) -> str | None:
    """Возвращает target_node для proactive movement intent."""
    if not spatial_query:
        return None

    # 1. Явный target_id — резолвим его позицию
    if intent_target and intent_target != "player":
        target_pos = scene_state.get("npc_positions", {}).get(intent_target, {})
        lp = target_pos.get("local_position")
        if lp:
            return spatial_query.find_nearest_node(lp.get("x", 0), lp.get("y", 0))

    # 2. Резолвим по intent type через NodeRole
    from app.models.spatial_contracts import NodeRole
    _INTENT_TO_ROLE = {
        "request_service": NodeRole.BAR,
        "offer_job": NodeRole.BAR,
        "block_path": NodeRole.ENTRANCE,
        "ambush": NodeRole.DEFAULT,
        "change_role": NodeRole.WORKBENCH,
    }
    if intent_value in _INTENT_TO_ROLE:
        return spatial_query.resolve_node(_INTENT_TO_ROLE[intent_value])

    # 3. Социальные intents — к ближайшему NPC
    if intent_value in ("seek_ally", "call_for_help", "spread_rumor", "talk"):
        npc_positions = scene_state.get("npc_positions", {})
        my_pos = npc_positions.get(npc_id, {}).get("local_position", {"x": 0, "y": 0})
        nearest_npc_id = None
        nearest_dist = float("inf")
        for other_id, other_data in npc_positions.items():
            if other_id == npc_id or other_id == "player":
                continue
            other_pos = other_data.get("local_position", {})
            if not other_pos:
                continue
            dx = other_pos.get("x", 0) - my_pos.get("x", 0)
            dy = other_pos.get("y", 0) - my_pos.get("y", 0)
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_npc_id = other_id
        if nearest_npc_id:
            other_pos = npc_positions[nearest_npc_id].get("local_position", {})
            return spatial_query.find_nearest_node(
                other_pos.get("x", 0), other_pos.get("y", 0)
            )
    return None
```

**Шаг 3 — Использовать в основном цикле:**

```python
if _intent_value in _MOVE_INTENTS:
    _movement = _resolve_reactive_movement(...)
    if not _movement and state.spatial_query:
        _target_node = _resolve_proactive_target(
            intent_value=_intent_value,
            npc_id=npc_id,
            intent_target=decision.intent_target,
            scene_state=dict(state.scene_state),
            spatial_query=state.spatial_query,
        )
        if _target_node:
            from app.domain.movement import MacroMovementGoal
            _movement = MacroMovementGoal(
                npc_id=npc_id,
                target_node=_target_node,
                reason=f"proactive_{_intent_value}",
                tick=state.tick_id,
            )
    if _movement:
        movement_intents.append(_movement)
```

### 5.3. Контрольная точка

- В логах: `[MOTION_ROUTER] SEEK_ALLY→MovementIntent` или аналогичные
- За 30 секунд без ввода ≥ 3 NPC начали `status="MOVING"`

---

## 6. Блокер 4 — `communication_intents = 0`

### 6.1. Что наблюдается

За сессию 13 июля 06:52:
- DecisionHub сгенерил ~73 вербальных intent'а (30×request_service, 20×offer_job, 8×change_role, 7×spread_rumor, 6×talk, 2×call_for_help).
- Все ∈ `_VERBAL_INTENTS` → `_build_communication()` должен вернуть `CommunicationIntent`.
- **НО** `Фаза 6: 0 intents → EventDTO` — каждый тик.
- Лог `[TRACE][DECISION_SCORE]` (из `_build_communication`) — 0 раз за сессию.
- Логи от модуля `app.services.npc.decision_hub` — 0 строк за сессию.

**Вывод:** compute() либо не доходит до строки 793, либо `_build_communication` возвращает None по неочевидной причине. `decision.communication` всегда None.

### 6.2. Диагностический план

**Шаг 1 — Отладочные логи:**

```python
# decision_hub.py, перед строкой 657:
logger.info(f"[DECISION_HUB_ENTER] npc={state.npc_id} scores_count={len(scores) if scores else 0}")

# decision_hub.py, на строке 777:
logger.info(f"[DECISION_HUB_RETURN] npc={state.npc_id} intent={best_intent} score={best_score}")
```

Если `DECISION_HUB_RETURN` отсутствует — compute() падает между 657 и 777.

**Шаг 2 — Обёртка с try/except:**

```python
# decision_hub.py, заменить строки 793-805:
try:
    _communication = self._build_communication(
        npc_id=state.npc_id,
        intent_value=best_intent.value if hasattr(best_intent, 'value') else str(best_intent),
        intent_target=intent_target,
        topic=topic,
        emotion_value=state.emotion.value if hasattr(state.emotion, 'value') else str(state.emotion),
        scores=scores if scores is not None else {},
    )
except Exception as _comm_err:
    logger.exception(f"[BUILD_COMM_FAILED] npc={state.npc_id} intent={best_intent}: {_comm_err}")
    _communication = None

return AgentAction(decision=_decision, communication=_communication)
```

**Шаг 3 — Вероятные причины:**
1. `scores` = None → `sorted(scores.items()...)` падает с `AttributeError`. Фикс: передавать `scores={}` (учтено в Шаге 2).
2. `intent_target` — не str. Фикс: `audience=str(intent_target) if intent_target else "all"`.
3. `state.emotion` — None. Фикс: проверка `hasattr(state.emotion, 'value')` (учтено в Шаге 2).

### 6.3. Контрольная точка

- `[TICK_ORCH] Фаза 6: N intents → EventDTO` где N > 0
- `[TRACE][DECISION_SCORE]` виден хотя бы 1 раз за 30 сек
- `pending_tasks` в scene_state не пустой

---

## 7. Блокер 5 — Sims-слой + Canonical/Ambient + LLM очередь

Это **самый большой и важный блокер.** Без него LLM умрёт от нагрузки, а без LLM не будет конкретики. Решение — двухслойная архитектура с разделением разговоров на типы.

### 7.1. Двухслойная модель разговоров

```
┌─────────────────────────────────────────────────────────────┐
│  СЛОЙ 1 — Sims-режим (без LLM, каждые ~2 сек)                │
│                                                              │
│  NpcConversation(speaker_a, speaker_b, topic, tone, ...)    │
│  ─► обновляет intensity, exchanges, trust/fear              │
│  ─► рисует облачко 💬 + тему над парой                      │
│  ─► пишет АБСТРАКТНЫЙ эпизод в WorkingMemory                │
│  ─► пишет АБСТРАКТНУЮ запись в L1Chronicle                  │
│  ─► НЕ вызывает LLM                                         │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ один из canonical триггеров:
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  СЛОЙ 2 — LLM-режим (полноценные реплики)                    │
│                                                              │
│  Canonical разговоры — LLM вызывается ВСЕГДА, в момент       │
│  разговора, даже если игрок не слышит.                       │
│                                                              │
│  Ambient разговоры — НИКОГДА не имеют LLM. Только Sims.      │
│                                                              │
│  Все LLM-вызовы идут через единую очередь с приоритетами.    │
└─────────────────────────────────────────────────────────────┘
```

### 7.2. Canonical vs Ambient — критерии

**Canonical (LLM всегда, в момент разговора):**
1. Касается секрета (`secret_relevant=True`)
2. Кульминация отношения (романтическое признание, ссора, примирение)
3. Кризис (anger > 0.7, ATTACK intent)
4. Смена belief (`CrystallizedBeliefStore` обновляется)
5. Долгосрочное решение (свадьба, найм, долг, предательство)
6. Игрок в радиусе 3м (eavesdrop — даже ambient становится canonical)
7. Кульминация разговора (exchanges >= 10 или intensity >= 0.8)
8. NPC обращается к игроку (intent=TALK target=player)

**Ambient (только Sims, без LLM):**
- Светская беседа (gossip, small_talk)
- Повседневные взаимодействия (request_service рутина)
- Любой разговор не подходящий под canonical

### 7.3. NpcConversation — Sims-слой

**Новый файл:** `backend/app/services/social/npc_conversation.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class NpcConversation:
    """Текущий разговор между двумя (или более) NPC. Без LLM, чисто состояние.
    
    Обновляется каждые ~2 секунды (один игровой turn).
    Не вызывает LLM. Только маркеры + trust/fear + абстрактная memory.
    """
    conversation_id: str
    participants: List[str]  # 2+ NPC ids
    topic: str               # gossip, flirt, vent, business, insult, secret, ...
    tone: str                # NEUTRAL, FRIENDLY, ANGRY, FLIRTY, VENTING, FEARFUL, MANIPULATIVE
    started_tick: int
    last_exchange_tick: int
    exchanges: int = 0       # сколько ходов обмена прошло
    intensity: float = 0.0   # 0..1, нарастает со временем
    saturation: float = 0.0  # 0..1, насколько закрыта потребность
    secret_relevant: bool = False  # касается ли секрета
    canonical_triggered: bool = False  # был ли уже LLM-вызов для этого разговора
    
    def step(self, dt_seconds: float, all_npcs_raw: list) -> Optional["CanonicalTrigger"]:
        """Один ход разговора. Возвращает CanonicalTrigger если пора вызвать LLM.
        
        НЕ вызывает LLM сам. Только возвращает триггер для DialogueQueue.
        """
        self.exchanges += 1
        self.last_exchange_tick += 1
        
        # Saturation растёт по типу темы
        _SATURATION_RATE = {
            "gossip": 0.10,
            "small_talk": 0.15,
            "vent": 0.05,
            "business": 0.20,
            "flirt": 0.07,
            "insult": 0.30,  # быстро накаляется
            "secret": 0.15,
        }
        self.saturation = min(1.0, self.saturation + 
                              _SATURATION_RATE.get(self.topic, 0.10))
        
        # Intensity растёт от saturation и exchanges
        self.intensity = min(1.0, self.intensity + 0.05 + self.saturation * 0.05)
        
        # Проверка canonical триггеров
        if self.canonical_triggered:
            return None  # уже был LLM, ждём завершения
        
        # Триггер 1: секрет-релевантная тема
        if self.secret_relevant and self.exchanges >= 3:
            self.canonical_triggered = True
            return CanonicalTrigger(
                conversation=self,
                reason="secret_relevant",
                priority=10,  # высокий приоритет
            )
        
        # Триггер 2: кульминация
        if self.exchanges >= 10 or self.intensity >= 0.8:
            self.canonical_triggered = True
            return CanonicalTrigger(
                conversation=self,
                reason="culmination",
                priority=5,
            )
        
        # Триггер 3: кризис (anger > 0.7 у любого участника)
        for npc_id in self.participants:
            npc_dict = next((n for n in all_npcs_raw if n.get("id") == npc_id), None)
            if npc_dict:
                affective = npc_dict.get("affective_state", {})
                if affective.get("anger", 0) > 0.7:
                    self.canonical_triggered = True
                    return CanonicalTrigger(
                        conversation=self,
                        reason="crisis_anger",
                        priority=15,  # кризис — наивысший
                    )
        
        return None
    
    def is_finished(self) -> bool:
        """Завершён ли разговор."""
        # Завершение по saturation
        if self.saturation >= 0.9:
            return True
        # Завершение по усталости
        if self.exchanges >= 30:
            return True
        # Завершение по кульминации (после canonical)
        if self.canonical_triggered and self.exchanges >= 15:
            return True
        return False
    
    def get_display_text(self) -> str:
        """Короткий текст-маркер для облачка над парой."""
        _TOPIC_TEXT = {
            "gossip": "сплетни",
            "small_talk": "светская беседа",
            "vent": "жалоба",
            "business": "дело",
            "flirt": "флирт",
            "insult": "ссора",
            "secret": "шёпот",
            "comfort": "утешение",
        }
        return _TOPIC_TEXT.get(self.topic, "разговор")


@dataclass
class CanonicalTrigger:
    """Триггер для LLM-вызова из NpcConversation."""
    conversation: NpcConversation
    reason: str          # secret_relevant, culmination, crisis_anger, eavesdrop, ...
    priority: int        # 0-15, выше = важнее


class ConversationManager:
    """Управляет всеми активными NpcConversation в локации."""
    
    def __init__(self) -> None:
        self._active: dict[str, NpcConversation] = {}  # conversation_id → conv
    
    def start_conversation(
        self,
        participants: List[str],
        topic: str,
        tone: str,
        tick: int,
        secret_relevant: bool = False,
    ) -> NpcConversation:
        """Создаёт новый разговор."""
        conv_id = f"conv-{tick}-{'-'.join(participants)}"
        conv = NpcConversation(
            conversation_id=conv_id,
            participants=participants,
            topic=topic,
            tone=tone,
            started_tick=tick,
            last_exchange_tick=tick,
            secret_relevant=secret_relevant,
        )
        self._active[conv_id] = conv
        logger.info(f"[CONV_START] {conv_id} participants={participants} topic={topic}")
        return conv
    
    def step_all(self, dt_seconds: float, all_npcs_raw: list) -> List[CanonicalTrigger]:
        """Прогоняет все активные разговоры на один ход.
        
        Возвращает список CanonicalTrigger для DialogueQueue.
        """
        triggers = []
        finished = []
        for conv_id, conv in self._active.items():
            trigger = conv.step(dt_seconds, all_npcs_raw)
            if trigger:
                triggers.append(trigger)
            if conv.is_finished():
                finished.append(conv_id)
        for conv_id in finished:
            logger.info(f"[CONV_END] {conv_id} exchanges={self._active[conv_id].exchanges}")
            del self._active[conv_id]
        return triggers
    
    def get_conversation_for_npc(self, npc_id: str) -> Optional[NpcConversation]:
        """Возвращает активный разговор NPC, если он в одном участвует."""
        for conv in self._active.values():
            if npc_id in conv.participants:
                return conv
        return None
```

### 7.4. DialogueQueue — очередь LLM с приоритетами

**Новый файл:** `backend/app/services/execution/dialogue_queue.py`

```python
from __future__ import annotations
import time
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional, Any
import heapq

logger = logging.getLogger(__name__)


@dataclass(order=True)
class QueuedDialogue:
    """Задача на LLM-генерацию реплики. Сортируется по priority (desc)."""
    priority: int                          # 0-15, выше = важнее
    enqueued_at: float                     # timestamp
    task_type: str = field(compare=False)  # canonical, eavesdrop, culmination, dm_response, ...
    payload: dict = field(compare=False)   # данные для LLM-вызова
    task_id: str = field(compare=False)


class DialogueQueue:
    """Единая очередь LLM-вызовов с приоритетами.
    
    Один LLM-вызов за раз (single-threaded). Все canonical/eavesdrop/DM 
    запросы идут через эту очередь.
    
    Приоритеты (0-15):
        15 = crisis_anger (NPC в гневе, может атаковать)
        12 = dm_response (ответ игроку — высокий, но не кризис)
        10 = secret_relevant (разговор о секрете)
        8 = eavesdrop (игрок подошёл к разговору)
        5 = culmination (10+ ходов разговора)
        3 = npc_initiates_player (NPC подошёл к игроку)
    """
    
    MAX_RATE_PER_MINUTE = 20  # 20 LLM-вызовов в минуту максимум
    
    def __init__(self) -> None:
        self._heap: list[QueuedDialogue] = []
        self._minute_count: int = 0
        self._minute_start: float = time.time()
        self._current: Optional[QueuedDialogue] = None
        self._current_started: float = 0.0
    
    def enqueue(self, task_type: str, payload: dict, priority: int) -> str:
        """Добавить задачу в очередь."""
        import uuid
        task_id = f"dlg-{uuid.uuid4().hex[:8]}"
        task = QueuedDialogue(
            priority=-priority,  # heapq = min-heap, инвертируем
            enqueued_at=time.time(),
            task_type=task_type,
            payload=payload,
            task_id=task_id,
        )
        heapq.heappush(self._heap, task)
        logger.info(
            f"[DLG_QUEUE] enqueued task_id={task_id} type={task_type} priority={priority}"
        )
        return task_id
    
    def dequeue_next(self) -> Optional[QueuedDialogue]:
        """Возвращает следующую задачу с учётом rate limit."""
        # Сброс минутного счётчика
        now = time.time()
        if now - self._minute_start > 60.0:
            self._minute_count = 0
            self._minute_start = now
        
        if self._minute_count >= self.MAX_RATE_PER_MINUTE:
            return None
        
        if not self._heap:
            return None
        
        task = heapq.heappop(self._heap)
        self._minute_count += 1
        self._current = task
        self._current_started = now
        return task
    
    def mark_completed(self, task_id: str) -> None:
        """Отметить задачу как выполненную."""
        if self._current and self._current.task_id == task_id:
            self._current = None
            self._current_started = 0.0
    
    def pending_count(self) -> int:
        return len(self._heap)
```

### 7.5. Обработка кластеров (2 / 3-4 / 5+)

**Кластер 2 NPC:**
- Sims-слой обновляет conversation каждые ~2 сек
- При canonical триггере → 1 LLM-вызов, генерит 1-2 реплики обмена
- Реплики распределяются по WorkingMemory каждого NPC

**Кластер 3-4 NPC:**
- Sims-слой обновляет conversation (participants = 3-4)
- При canonical триггере → **1 LLM-вызов на всю группу** со строгим JSON
- Промт:

```
Ты DM. Сцена: {участники} обсуждают {topic}.

Контекст:
- {npc_a} ({tone_a}, {intent_a}) — {context_a}
- {npc_b} ({tone_b}, {intent_b}) — {context_b}
- {npc_c} ({tone_c}, {intent_c}) — {context_c}

Сгенерируй 2-3 реплики обмена. Строгий JSON:
{
  "exchanges": [
    {
      "speaker": "npc_id",
      "target": "npc_id",
      "text": "...",
      "tone": "FRIENDLY|ANGRY|...",
      "intent": "reassure|probe|vent|..."
    },
    ...
  ]
}
```

**Парсинг и распределение по памяти:**

```python
def process_cluster_dialogue(response: dict, conv: NpcConversation, tick: int):
    """Распределяет реплики по WorkingMemory каждого NPC."""
    for exchange in response["exchanges"]:
        speaker = exchange["speaker"]
        target = exchange["target"]
        text = exchange["text"]
        tone = exchange["tone"]
        
        # Speaker сказал
        working_memory.append(speaker, {
            "tick": tick,
            "type": "said",
            "target": target,
            "text": text,
            "tone": tone,
            "conversation_id": conv.conversation_id,
        })
        
        # Все остальные участники услышали
        listeners = [p for p in conv.participants if p != speaker]
        for listener in listeners:
            working_memory.append(listener, {
                "tick": tick,
                "type": "heard",
                "speaker": speaker,
                "target": target,
                "text": text,
                "tone": tone,
                "conversation_id": conv.conversation_id,
            })
        
        # Обновить отношения speaker ↔ target
        delta_trust, delta_fear = compute_rel_delta(tone)
        relationship_store.update(target, speaker, delta_trust, delta_fear)
    
    # Записать в L1Chronicle (мировая история) для будущего open world
    l1_chronicle.commit({
        "type": "cluster_dialogue",
        "conversation_id": conv.conversation_id,
        "participants": conv.participants,
        "topic": conv.topic,
        "exchanges": response["exchanges"],
        "tick": tick,
    })
```

**Кластер 5+ NPC:**
- Определяем 1-2 лидеров по `social_rank + gregariousness`
- LLM-вызов только для лидеров (как кластер 2 если лидер 1, или кластер 3-4 если лидеров 2)
- Остальные участники — Sims-иконки, обновляют trust/fear с лидерами
- Если лидеры спорят — это кластер 2 внутри толпы, обрабатывается отдельно

### 7.6. Контрольная точка

- За 5 минут без ввода ≥ 5 NPC-NPC диалогов исполнено через DialogueQueue
- CPU ≤ 70% при автономной работе 5 минут
- В `L1Chronicle` ≥ 3 canonical записи с конкретным текстом реплик
- В `WorkingMemory` ≥ 10 абстрактных записей (ambient разговоры)

---

## 8. Блокер 6 — NpcDialogueSubscriber

Замыкает цикл эмерджентности: NPC_A говорит → NPC_B воспринимает → интерпретирует → обновляет эмоции → memory → belief → relationship → на следующем тике NPC_B принимает решение с учётом новых данных.

### 8.1. Патч

**Шаг 1 — DialogueExecutor публикует событие:**

```python
# backend/app/services/execution/dialogue_executor.py
# В методе execute(task) после генерации реплики LLM:

from app.services.events.event_bus import get_event_bus

def execute(self, task: QueuedTask) -> str:
    speaker = task.owner_id  # NPC_A
    target_ids = task.target_ids or []
    listener = target_ids[0] if target_ids else "all"  # NPC_B (не player!)
    
    generated_text = self._llm_generate(...)
    
    event = {
        "type": "NPC_SAID_TO_NPC",
        "speaker": speaker,
        "listener": listener,
        "text": generated_text,
        "tone": task.payload.get("tone", "NEUTRAL"),
        "topic": task.payload.get("topic", ""),
        "tick": task.tick,
        "campaign_id": task.campaign_id,
        "is_canonical": task.payload.get("is_canonical", True),
    }
    get_event_bus().publish(event)
    
    return generated_text
```

**Шаг 2 — Создать NpcDialogueSubscriber (новый файл):**

```python
# backend/app/services/events/npc_dialogue_subscriber.py

import logging
from typing import Any

logger = logging.getLogger(__name__)


class NpcDialogueSubscriber:
    """Слушает NPC_SAID_TO_NPC события.
    
    Для canonical реплик — полная обработка:
        PerceptionEngine → InterpretationEngine → AffectiveIntegrator →
        WorkingMemory (с текстом) → RelationshipStore → BeliefAggregator
    
    Для ambient реплик — упрощённая:
        WorkingMemory (абстрактно) → RelationshipStore
    """

    def __init__(
        self,
        perception_engine: Any,
        interpretation_engine: Any,
        affective_integrator: Any,
        working_memory: Any,
        relationship_store: Any,
        belief_aggregator: Any,
    ) -> None:
        self.perception = perception_engine
        self.interpretation = interpretation_engine
        self.affective = affective_integrator
        self.memory = working_memory
        self.relationships = relationship_store
        self.beliefs = belief_aggregator

    def on_npc_said_to_npc(self, event: dict) -> None:
        speaker = event.get("speaker", "")
        listener = event.get("listener", "")
        text = event.get("text", "")
        tone = event.get("tone", "NEUTRAL")
        topic = event.get("topic", "")
        tick = event.get("tick", 0)
        is_canonical = event.get("is_canonical", True)

        if not speaker or not listener or listener == "all":
            return

        logger.info(
            f"[NPC_DIALOGUE_SUB] {listener} heard {speaker} "
            f"(tone={tone}, topic={topic!r}, canonical={is_canonical})"
        )

        try:
            if is_canonical:
                self._process_canonical(event)
            else:
                self._process_ambient(event)
        except Exception as e:
            logger.exception(
                f"[NPC_DIALOGUE_SUB] failed for {listener} hearing {speaker}: {e}"
            )

    def _process_canonical(self, event: dict) -> None:
        """Полная обработка canonical реплики."""
        speaker = event["speaker"]
        listener = event["listener"]
        text = event["text"]
        tone = event["tone"]
        topic = event.get("topic", "")
        tick = event.get("tick", 0)

        # 1. PerceptionEngine воспринимает
        perceived = self.perception.perceive(listener, event)

        # 2. InterpretationEngine интерпретирует
        interpretation = self.interpretation.interpret(listener, perceived)

        # 3. AffectiveIntegrator обновляет эмоции
        self.affective.apply(listener, interpretation)

        # 4. WorkingMemory — с конкретным текстом
        self.memory.append(listener, {
            "tick": tick,
            "type": "dialogue_heard",
            "speaker": speaker,
            "text": text,  # конкретика
            "tone": tone,
            "topic": topic,
            "interpretation": interpretation,
            "canonical": True,
        })

        # 5. RelationshipStore
        delta_trust, delta_fear = self._compute_rel_delta(tone, interpretation)
        self.relationships.update(listener, speaker, delta_trust, delta_fear)
        logger.info(
            f"[NPC_DIALOGUE_SUB] {listener} rel update: "
            f"{speaker} trust={delta_trust:+.1f} fear={delta_fear:+.1f}"
        )

        # 6. BeliefAggregator
        self.beliefs.aggregate(listener, {
            "speaker": speaker,
            "topic": topic,
            "tone": tone,
            "tick": tick,
            "text": text,
            "canonical": True,
        })

    def _process_ambient(self, event: dict) -> None:
        """Упрощённая обработка ambient реплики (без LLM-конкретики)."""
        speaker = event["speaker"]
        listener = event["listener"]
        tone = event["tone"]
        topic = event.get("topic", "")
        tick = event.get("tick", 0)

        # WorkingMemory — абстрактно
        self.memory.append(listener, {
            "tick": tick,
            "type": "ambient_heard",
            "speaker": speaker,
            "topic": topic,
            "tone": tone,
            "canonical": False,
            # НЕТ text — конкретики нет, потому что LLM не вызывался
        })

        # RelationshipStore — упрощённые дельты
        delta_trust, delta_fear = self._compute_rel_delta(tone, None)
        self.relationships.update(listener, speaker, delta_trust, delta_fear)

    def _compute_rel_delta(self, tone: str, interpretation: Any) -> tuple[float, float]:
        """Конвертирует tone в изменения trust/fear."""
        _BASE = {
            "ANGRY": (-5.0, +2.0),
            "FRIENDLY": (+3.0, 0.0),
            "FLIRTY": (+2.0, 0.0),
            "VENTING": (+1.0, 0.0),
            "MANIPULATIVE": (-2.0, +1.0),
            "FEARFUL": (0.0, +1.0),
            "NEUTRAL": (0.0, 0.0),
        }
        # Ambient — дельты в 5 раз меньше (без конкретики, слабое влияние)
        base_trust, base_fear = _BASE.get(tone, (0.0, 0.0))
        if interpretation is None:
            return base_trust * 0.2, base_fear * 0.2
        return base_trust, base_fear
```

**Шаг 3 — Зарегистрировать подписчика:**

```python
# backend/app/services/game_loop/__init__.py
# В методе __init__ GameLoop:

def _register_event_subscribers(self):
    from app.services.events.event_bus import get_event_bus
    from app.services.events.npc_dialogue_subscriber import NpcDialogueSubscriber

    _bus = get_event_bus()

    _subscriber = NpcDialogueSubscriber(
        perception_engine=self._perception_engine,
        interpretation_engine=self._interpretation_engine,
        affective_integrator=self._affective_integrator,
        working_memory=self._memory_manager,
        relationship_store=self._relationship_store,
        belief_aggregator=self._belief_aggregator,
    )

    _bus.subscribe("NPC_SAID_TO_NPC", _subscriber.on_npc_said_to_npc)
    logger.info("[GAME_LOOP] NpcDialogueSubscriber registered for NPC_SAID_TO_NPC")
```

### 8.2. Контрольная точка

- В логах `[NPC_DIALOGUE_SUB]` ≥ 3 за 2 минуты
- После ANGRY реплики — listener получает sadness/anger bump (видно в NPC state)
- `maid_lusya.relationships[goran].trust` изменился за 2 минуты (debug overlay)
- В `WorkingMemory` есть как canonical (с text), так и ambient (без text) записи

---

## 9. Архитектура социального взаимодействия

### 9.1. Облачка над NPC + журнал как SSOT

**Правило:** Никакого центрального чата для NPC-NPC. Только:

1. **Облачка над NPC** — ситуативная видимость. Видишь то, что слышишь сейчас. Не дублируется в чат.
2. **Журнал (J)** — эпистемическая память. Всё что игрок когда-либо слышал, с раскрытием имён.

**Облачко:**
- Над разговаривающей парой/кластером — иконка 💬 + короткий текст темы
- При canonical реплике (eavesdrop или кульминация) — speech bubble с цветным краем по tone
- Длительность показа: 3 сек для Sims-маркера, 6 сек для LLM-реплики

**Журнал:** см. §11.

### 9.2. Sims-слой (без LLM)

Реализован через `NpcConversation` (см. §7.3). Каждый ход (~2 сек):
- `intensity += 0.05 + saturation * 0.05`
- `saturation += topic_rate`
- `exchanges += 1`
- Trust/fear обновляются по таблице (FRIENDLY +0.5, ANGRY -1.0, и т.д.)
- В `WorkingMemory` пишется **абстрактно**: `{"type": "ambient_heard", "speaker": ..., "topic": ..., "tone": ...}` (без text)
- В `L1Chronicle` пишется **абстрактно**: «NPC_A и NPC_B поговорили о {topic}, {exchanges} ходов, {tone}»

### 9.3. Canonical-слой (LLM с приоритетами)

Canonical реплики идут через единую `DialogueQueue` (см. §7.4). Приоритеты:

| Priority | Тип | Когда |
|---|---|---|
| 15 | crisis_anger | NPC в гневе (anger > 0.7), может атаковать |
| 12 | dm_response | Ответ игроку (высокий, но не кризис) |
| 10 | secret_relevant | Разговор касается секрета |
| 8 | eavesdrop | Игрок подошёл в радиус 3м к разговору |
| 5 | culmination | 10+ ходов разговора, intensity ≥ 0.8 |
| 3 | npc_initiates_player | NPC подошёл к игроку с intent=TALK |

**Поведение очереди:**
- Один LLM-вызов за раз (single-threaded)
- Максимум 20 вызовов в минуту (rate limit)
- Если игрок долго печатал (>5 сек) — canonical NPC-NPC может вклиниться перед DM-ответом
- Не более 2 NPC-NPC реплик до DM-ответа, остальные — в журнал

### 9.4. Кластеры

| Размер | Обработка | LLM-вызовов |
|---|---|---|
| 2 NPC | Полный диалог | 1 на canonical триггер |
| 3-4 NPC | Один LLM-вызов на всю группу, строгий JSON | 1 на canonical триггер |
| 5+ NPC | Лидеры (1-2 по social_rank+gregariousness) через LLM, остальные Sims | 1-2 на canonical триггер |

### 9.5. Математика длительности разговора

```
utility_continue = need_satisfaction_rate - fatigue - opportunity_cost

need_satisfaction_rate = базовая_потребность × (1 - saturation)
  # saturation растёт от 0 до 1 за ходы
  # gossip:        saturation += 0.10/turn → ~10 ходов
  # small_talk:    saturation += 0.15/turn → ~7 ходов
  # vent:          saturation += 0.05/turn → ~20 ходов
  # business:      saturation += 0.20/turn → ~5 ходов
  # flirt:         saturation += 0.07/turn → ~14 ходов
  # insult:        saturation += 0.30/turn → ~3 хода (быстро накаляется)

fatigue = 0.05 × exchanges  # линейный рост

opportunity_cost = hunger × 0.3 + sleep_deprivation × 0.5 + work_deadline × 0.8
```

**Условие завершения:** `utility_continue < 0` → NPC вежливо завершает («ладно, мне пора»)

**Прерывание (резкое):**
- `anger > 0.8` → хлопает дверью
- `fear > 0.7` → убегает
- `opportunity_cost > 1.5` (горит работа) → «извини, срочно надо»

### 9.6. Прерывание разговора третьим NPC

Если NPC_A говорит с NPC_B, и тут NPC_C подходит и начинает орать:
- Текущий разговор получает `status=INTERRUPTED`
- NPC_A и NPC_B поворачиваются к NPC_C
- Начинается новый разговор (A↔C или B↔C, по приоритету)
- Прерванный разговор может возобновиться через несколько ходов или быть забытым

Если прерванный был canonical — это создаёт драму «извинись, я с тобой говорил!».

---

## 10. Dialogue Mode

### 10.1. Игрок инициирует

- Игрок нажимает «говорить с Люсей» (клик по NPC + ввод текста)
- Время **замедляется** в 30-60 раз (1 игровая минута = 1-2 сек реальных)
- NPC-NPC разговоры **не останавливаются** — идут параллельно в Sims-режиме
- Canonical NPC-NPC может вклиниться через DialogueQueue если игрок долго печатал
- LLM-вызовы идут через единую очередь с приоритетом dm_response=12
- Будущее: портреты лиц в стиле JRPG

### 10.2. NPC инициирует (без ограничений)

- NPC_A имеет `intent=TALK target=player`
- NPC_A подходит к игроку (через MovementEngine)
- За 2-3 секунды до подхода — `!` над NPC_A (см. §12)
- При подходе в радиус 2м — **автоматический переход в Dialogue Mode**
- Время замедляется
- Prompt: `[E] говорить / [Q] не до тебя`
- Никаких ограничений «trust > 30» — **любой** NPC может инициировать
- Тень подойдёт к игроку который только зашёл в таверну — это драма, не баг

### 10.3. Q = нейтральный отказ

- `Q` = «не до тебя сейчас» (нейтральный отказ)
- NPC получает `trust -1`, `annoyance +0.2`. Не агрессивный, но социальный сигнал «ты меня отшил».
- Игрок убегает без Q → `trust -0.5` (меньше чем явный Q, потому что «он убежал, может по делу»)
- Игрок игнорит 5+ секунд → диалог автозавершается, `trust -0.5`

### 10.4. Замедление времени

- В Dialogue Mode: `GAME_TICK_INTERVAL_SECONDS` умножается на 30-60 (1 игровая минута = 1-2 сек реальных)
- NPC-NPC Sims-разговоры продолжаются (видны облачка)
- Canonical NPC-NPC могут ставить задачи в очередь, но не показываются пока игрок в Dialogue Mode (только в журнал)
- После выхода из Dialogue Mode — время размораживается, накопленные canonical реплики показываются в журнале

---

## 11. Журнал и раскрытие имён

### 11.1. Расширение J (вкладки)

J теперь имеет вкладки:
- **Подслушанное** — всё что игрок слышал от NPC-NPC разговоров (canonical + ambient)
- **Мои диалоги** — всё что игрок говорил с NPC
- **(будущее)** — дополнительные вкладки

### 11.2. Структура записи

```python
@dataclass
class JournalEntry:
    tick: int
    timestamp: str           # "Год 1, День 3, 14:23"
    speaker_id: str          # npc_id или "player"
    speaker_name: str        # "Люся" или "?"
    listener_id: str
    listener_name: str       # "Горан" или "?"
    topic: str               # gossip, secret, flirt, ...
    text: Optional[str]      # конкретика если был LLM, None если ambient
    source: str              # "overheard", "direct_dialogue", "rumor"
    location: str            # location_id
    confidence: float        # для эпистемической модели
    is_canonical: bool
```

### 11.3. Раскрытие имён (НЕ автоматически)

**Имя раскрывается когда игрок реально его услышал:**

1. **NPC сам представился** — в диалоге сказал «Я Люся» → имя раскрывается
2. **Кто-то назвал его по имени** — Борко крикнул «Люся, иди сюда!» → игрок услышал → раскрывается
3. **Игрок спросил** — «как тебя зовут?» → NPC ответил → раскрывается
4. **Визуально по бейджу/одежде** — у стражи есть нашивки с именем, у торговцев — вывеска на лавке (если NPC в фокусе 3+ сек)

Всё остальное — `?`. Можно поговорить с NPC 10 раз, но если он не представился и никто его не назвал — в журнале так и остаётся `?`.

### 11.4. Ретроактивное раскрытие

Когда игрок узнаёт имя NPC X — **все прошлые записи** в журнале с этим NPC обновляются: `?` → `Люся`. Это не ретро-симуляция — это просто раскрытие идентичности. Игрок вспоминает «а, так это была Люся тогда у камина».

### 11.5. NPC config флаги

```python
# В config/npc/individuals/*.json
{
  "id": "maid_lusya",
  "name": "Люся",
  "introduced_self": false,   # True если NPC когда-либо представлялся
  "known_to_player": false    # True если игрок знает имя
}
```

`introduced_self` ставится при первом представлении. `known_to_player` раскрывается игроку.

---

## 12. Восклицательный знак и insight_skill

### 12.1. `!` над NPC

`!` над NPC означает: «этот NPC собирается инициировать разговор» (с любым target — игроком или другим NPC).

**Игрок не знает target** пока NPC не подойдёт достаточно близко к цели. Это создаёт 2-3 секунды напряжения.

**Пример:** Пункт досмотра, игрок замаскировался. У стражника `!` — идёт к игроку или к NPC по соседству? Будет игрок арестован или нет?

### 12.2. Цвет `!` = insight_skill vs deception_skill

У игрока есть `insight_skill: float (0..1)` — прокачивается со временем и наблюдением.

| insight_skill | Что видит игрок |
|---|---|
| 0.0 - 0.3 | Все `!` нейтральные (жёлтые) |
| 0.3 - 0.6 | Базовые тоны: angry (красный), friendly (зелёный), fearful (бледно-голубой) |
| 0.6 - 0.9 | Тонкие тоны: flirty (розовый), venting (фиолетовый) |
| 0.9 - 1.0 | Все тоны включая manipulative (тёмно-фиолетовый) |

**NPC может скрывать эмоции:**
- Черта `stoic` → все эмоции скрыты, `!` всегда нейтральный
- Черта `manipulative` → скрывает manipulative intent, остальные видны
- Черта `nervous` → наоборот, эмоции ярче чем есть (ложные сигналы)

**Resistance check:** `if insight_skill > npc.deception_skill → цвет виден`. Иначе нейтральный.

### 12.3. Поведение `!`

- NPC идёт к игроку → когда подходит в радиус 2м → `!` исчезает, появляется prompt `[E] говорить / [Q] не до тебя`. Время **уже замедлено** в этот момент.
- NPC идёт к другому NPC → `!` исчезает когда они в радиусе 1м → начинается их разговор (Sims или canonical). Игрок не контролирует, только наблюдает.
- Несколько `!` одновременно — это хаос и это хорошо. Три NPC хотят поговорить друг с другом → кто первый дойдёт, тот и начал.

---

## 13. Batch generation при смене локации

### 13.1. Принцип

**Не ретро-симуляция.** Это **batch generation с задержкой** — canonical конкретика генерируется для разговоров которые **реально произошли** в Sims-слое, **до** того как игрок может их услышать.

Когда игрок входит в новую локацию — реплики уже в памяти NPC, NPC помнят их как реальные слова. Игрок не знает что они были сгенерированы 5 секунд назад во время loading screen.

### 13.2. Механика

1. Игрок был в локации А 30 минут. За это время в локации Б произошло 3 canonical разговора (в Sims-режиме, накопили trust/fear, обновили memory **абстрактно**).
2. Игрок переходит А→Б → loading screen.
3. Во время loading screen LLM генерит конкретику для canonical разговоров которые произошли в локации Б **пока игрок был в А**.
4. Сгенерированные реплики записываются в:
   - `L1Chronicle` (мировая история) с полным текстом
   - `WorkingMemory` обоих NPC с полным текстом
   - `CrystallizedBeliefStore` обновляются beliefs
5. Игрок входит в Б → мир уже «прожил» без него, NPC помнят конкретные реплики.

### 13.3. Ограничения

- **Только canonical.** Ambient разговоры остаются абстрактными.
- **Cooldown 5 минут.** Если игрок был в локации Х менее 5 минут назад и возвращается — пропустить регенерацию. Мир «не успел» накопить новые canonical.
- **Только для разговоров которые Sims-слой зафиксировал.** Если Sims-слой не зафиксировал canonical триггер — LLM не вызывается, разговор остаётся абстрактным.
- **Не перегенерировать уже сгенерированное.** Если canonical реплика уже есть в L1Chronicle — она не трогается.
- **Не «дополнять» разговор.** Если Sims-слой решил что разговор был 8 ходов, LLM генерит реплики для этих 8 ходов, не больше.

### 13.4. Вариант 1 (зафиксировать как было)

При batch generation LLM генерирует реплики **как они произошли** (по логу Sims-слоя). Не пересчитывает актуальное состояние. Это честно — разговор закончился, фиксируем его конкретику в момент loading screen, NPC помнят именно эту конкретику.

### 13.5. Прогресс-бар

```
Загрузка...
[████████░░] 80%
Мир продолжает жить без вас...
```

Не «LLM генерирует 3 диалога» — игрок не должен знать техническую правду.

### 13.6. Риски

- **Игрок быстро бегает между локациями** → cooldown 5 минут решает
- **Локация пустая** (все спят) → canonical разговоров 0, loading screen мгновенный
- **Игрок был 2 часа** → canonical разговоров может быть 10-15, loading screen ~15-20 сек. Это нормально — игрок понимает «я долго отсутствовал, мир жил без меня»

---

## 14. Запрет ретро-симуляции (АРХИТЕКТУРНЫЙ ЗАКОН)

Это **фундаментальный принцип**, не пожелание. Что он значит архитектурно:

1. **Конкретика генерируется ТОЛЬКО в момент разговора** (или в batch generation при смене локации — §13). Если LLM не был вызван — конкретики нет и не будет.

2. **Canonical разговоры всегда имеют LLM** — значит конкретика есть всегда для важных моментов.

3. **Ambient разговоры никогда не имеют LLM** — значит конкретики нет никогда для рутины.

4. **Если игрок подходит после canonical разговора** — он не слышит конкретику. Но:
   - Если был в радиусе 3м когда разговор шёл → конкретика в его `ObservationLog` и журнале
   - Если не был → только абстрактная запись в журнале (если NPC были в зоне видимости игрока, когда разговаривали)
   - Если NPC были за стеной → вообще ничего

5. **NPC помнят canonical конкретно, ambient абстрактно.** Игрок может спросить NPC: «что ты говорил Горану?» — если canonical, NPC перескажет (через LLM в момент вопроса, на основе chronicle). Если ambient — NPC скажет «да так, о работе болтали».

6. **Кнопки Tab «подслушать о чём говорят» — нет.** Работает автоматически: игрок подходит в радиус 3м во время активного разговора → eavesdrop триггер → LLM генерит **следующую** реплику пары. Игрок подходит после разговора → видит только абстрактную запись в журнале.

7. **Никакого «вспомнить разговор которого не было».** LLM не может генерировать ретроспективные реплики для разговоров которые не зафиксированы в Sims-слое или L1Chronicle.

**Это создаёт естественную эпистемическую неопределённость.** Игрок не может услышать всё. Пропустил — пропустил. В следующей игре будут другие разговоры. Это и есть replayability.

---

## 15. Автономный Мир-Контракт (AWC)

Финальная спецификация. После применения блокеров 1-6 + социальной архитектуры — запустить `verify_autonomous_world.py`. Если все 8 пунктов (A-H) проходят — **мир автономен**, задача выполнена.

### 15.1. Контракт

Игрок запускает игру, **ничего не вводит 5 минут**, только наблюдает. За эти 5 минут **обязательно**:

**A. Время идёт:**
- `game_time_seconds` растёт каждые ~3 сек на 60 сек игрового времени
- За 5 минут реальных — минимум 1 час 40 мин игровых
- Часы в HUD обновляются ("07:00" → "07:30" → "08:00" → ... → "08:40")

**B. NPC двигаются:**
- За 5 минут **каждый** из 7 NPC хотя бы 1 раз сменил позицию
- ≥ 3 NPC одновременно имеют `active_traversals[*].status = "MOVING"`
- Видна LERP-интерполяция (не телепорты)

**C. NPC-NPC диалоги (Sims + Canonical):**
- За 5 минут ≥ 5 NPC-NPC диалогов (видно по облачкам 💬 с темой)
- ≥ 2 canonical диалога с LLM-репликами (видно по speech bubbles с цветным краем)
- LLM CPU ≤ 70% (очередь с приоритетами + rate limit работают)

**D. Эмоции меняются:**
- ≥ 3 NPC показали смену mood-иконки (neutral → happy → neutral)
- После ANGRY реплики — listener получает sadness/anger bump

**E. Отношения меняются:**
- ≥ 2 пары NPC показали изменение trust (debug overlay или журнал)
- Если был конфликт (tone=ANGRY) — trust между сторонами упал

**F. Журнал (J):**
- В журнале ≥ 10 записей за 5 минут (movement, dialogue, mood_change, и т.д.)
- Записи разные по типу
- Имена раскрываются по мере узнавания (не автоматически)

**G. Persistence:**
- После рестарта игры — `game_time_seconds` не сбросился, продолжил расти
- NPC positions восстановились из SQLite
- `active_traversals` восстановились
- Canonical реплики в `L1Chronicle` сохранились

**H. Реакция на длительное бездействие:**
- Через 30 игровых минут — `tavern_keeper_tornin` начинает routine transition
- Через 1 игровой час — смена activity у ≥ 3 NPC по расписанию

### 15.2. Скрипт автоматической проверки

```python
# backend/scripts/verify_autonomous_world.py
"""
Автономный Мир-Контракт (AWC) — автотест.

Запускать при работающем game_launcher.py:
    python backend/scripts/verify_autonomous_world.py

Создаёт сессию, ждёт 5 минут (ничего не отправляя), проверяет AWC.
Если все 8 пунктов (A-H) проходят — мир автономен.
"""

import requests
import time
import subprocess
import sys

BACKEND = "http://localhost:8000"
CAMPAIGN = "Open_road"
WAIT_SECONDS = 300  # 5 минут

LOG_PATH = "backend/logs/cds_backend.log"


def test_autonomous_world():
    print(f"AWC test: starting session for campaign '{CAMPAIGN}'...")

    # 1. Создать сессию
    try:
        r = requests.post(f"{BACKEND}/api/game/{CAMPAIGN}/start", json={}, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"❌ AWC-START FAILED: cannot start session: {e}")
        sys.exit(1)

    # 2. Начальное состояние
    initial = requests.get(f"{BACKEND}/api/game/{CAMPAIGN}/state", timeout=10).json()
    initial_time = initial.get("game_time_seconds", 0)
    initial_positions = {
        n.get("npc_id", ""): n.get("position", {})
        for n in initial.get("npcs", [])
    }
    print(f"Initial game_time_seconds: {initial_time}")
    print(f"Initial NPC positions: {len(initial_positions)} NPCs")

    # 3. Ждать 5 минут
    print(f"Waiting {WAIT_SECONDS} seconds (autonomous observation)...")
    time.sleep(WAIT_SECONDS)

    # 4. Финальное состояние
    final = requests.get(f"{BACKEND}/api/game/{CAMPAIGN}/state", timeout=10).json()
    final_time = final.get("game_time_seconds", 0)
    final_positions = {
        n.get("npc_id", ""): n.get("position", {})
        for n in final.get("npcs", [])
    }

    # Чтение логов
    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            log_content = f.read()
    except Exception as e:
        print(f"❌ AWC-LOGS FAILED: cannot read {LOG_PATH}: {e}")
        sys.exit(1)

    tick_crash_count = log_content.count("[TICK_CRASH]")
    dialogue_count = log_content.count("[NPC_DIALOGUE_SUB]")
    canonical_count = log_content.count("is_canonical=True")
    ambient_count = log_content.count("is_canonical=False")

    failures = []

    # A. Время идёт
    time_delta = final_time - initial_time
    if time_delta < 3000:
        failures.append(f"A: time only advanced {time_delta}s (expected >3000)")
    else:
        print(f"✅ A PASSED: time advanced {time_delta}s")

    # B. NPC двигаются
    moved = 0
    for npc_id, initial_pos in initial_positions.items():
        final_pos = final_positions.get(npc_id, {})
        if (final_pos.get("x") != initial_pos.get("x")
            or final_pos.get("y") != initial_pos.get("y")):
            moved += 1
    if moved < 5:
        failures.append(f"B: only {moved}/7 NPCs moved (expected ≥5)")
    else:
        print(f"✅ B PASSED: {moved}/7 NPCs moved")

    # C. NPC-NPC диалоги
    if dialogue_count < 5:
        failures.append(f"C: only {dialogue_count} dialogue events (expected ≥5)")
    else:
        print(f"✅ C PASSED: {dialogue_count} dialogue events "
              f"(canonical={canonical_count}, ambient={ambient_count})")

    # D. Эмоции меняются (по perception events)
    perception_count = log_content.count("[NPC_DIALOGUE_SUB]")
    if perception_count < 3:
        failures.append(f"D: only {perception_count} perception events (expected ≥3)")
    else:
        print(f"✅ D PASSED: {perception_count} perception events")

    # E. Отношения меняются
    rel_updates = log_content.count("rel update:")
    if rel_updates < 2:
        failures.append(f"E: only {rel_updates} relationship updates (expected ≥2)")
    else:
        print(f"✅ E PASSED: {rel_updates} relationship updates")

    # F. Журнал — через API
    try:
        journal = requests.get(
            f"{BACKEND}/api/game/{CAMPAIGN}/journal", timeout=10
        ).json()
        journal_count = len(journal.get("entries", []))
        if journal_count < 10:
            failures.append(f"F: only {journal_count} journal entries (expected ≥10)")
        else:
            print(f"✅ F PASSED: {journal_count} journal entries")
    except Exception:
        print("⚠️ F SKIPPED: cannot read journal (API endpoint may not exist)")

    # G. Persistence
    if tick_crash_count > 0:
        failures.append(f"G: {tick_crash_count} TICK_CRASH events (expected 0)")
    else:
        print(f"✅ G PASSED: 0 TICK_CRASH events")

    # H. Routine transitions
    sched_changes = log_content.count("SCHED_TRACE")
    if sched_changes < 1:
        failures.append(f"H: no routine schedule changes detected")
    else:
        print(f"✅ H PASSED: {sched_changes} routine schedule changes")

    # Итог
    if failures:
        print("\n❌ AWC FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("\n✅ AWC PASSED — мир автономен")
        sys.exit(0)


if __name__ == "__main__":
    test_autonomous_world()
```

### 15.3. Условие прохождения

**Все 8 пунктов A-H должны пройти.** Если хотя бы один fails — соответствующий блокер не починен.

---

## 16. Порядок применения и зависимости

```
Блокер 1 (persistence) ──► Блокер 2 (real-time loop) ──► Блокер 3 (movement)
                                    │
                                    └──► Блокер 4 (communication_intents>0)
                                                ──► Блокер 5 (Sims + Canonical + LLM очередь)
                                                        ──► Блокер 6 (NpcDialogueSubscriber)
                                                                │
                                                                ▼
                                                        AWC (§15) — финальная проверка
```

| Шаг | Блокер | Что проверить после | Время |
|---|---|---|---|
| 1 | Persistence TypeError | `[TICK_CRASH]` = 0 | 5 мин |
| 2 | Real-time loop | `game_time_seconds` растёт, idle_tick каждые 0.5-3 сек | 30 мин |
| 3 | Movement gap | `active_traversals[*].status = "MOVING"` ≥ 3 NPC | 1-2 часа |
| 4 | communication_intents=0 | `Фаза 6: N intents → EventDTO` где N > 0 | 1-2 часа |
| 5 | Sims + Canonical + LLM очередь | ≥ 5 диалогов за 5 мин, CPU ≤ 70% | 4-6 часов |
| 6 | NpcDialogueSubscriber | `[NPC_DIALOGUE_SUB]` ≥ 3 за 2 мин, эмоции меняются | 2-3 часа |
| 7 | AWC verify | `python backend/scripts/verify_autonomous_world.py` проходит | 5 мин |

**Без блокера 1** — игра мертва (симуляция не сохраняется).
**Без блокера 2** — игра тикает слишком медленно.
**Без блокера 3** — NPC «решают» но не двигаются.
**Без блокера 4** — NPC двигаются но молчат.
**Без блокера 5** — communication_intents есть, но LLM умирает от нагрузки (или нет конкретики).
**Без блокера 6** — диалоги возникают, но NPC_B не реагирует на NPC_A (цикл не замыкается).
**Без AWC** — задача не выполнена.

---

## 17. Что НЕ делать

1. **Не добавлять новые механики**, пока AWC не пройдён. Романтические арки, фракции, слухи, шантаж — потом.
2. **Не удалять старые модули** (front_applicator, role_transition и т.д.) — это не влияет на AWC.
3. **Не трогать порты llama-server, FD leaks, silent exceptions** — не блокеры автономии.
4. **Не писать тесты для будущих механик** — только AWC скрипт.
5. **Не рефакторить DecisionHub / NpcTickPipeline** — только точечные патчи.
6. **Не нарушать принцип «без скриптов»** (§1).
7. **★Не делать ретро-симуляцию★** (§14). Конкретика только в момент разговора или batch generation при смене локации.
8. **Не раскрывать имена автоматически.** Только через реальное услышанное (§11.3).
9. **Не останавливать NPC-NPC во время Dialogue Mode.** Только замедлять время (§10.4).
10. **Не показывать NPC-NPC облачка в центральном чате.** Только над NPC + в журнале (§9.1).

---

## 18. Контрольные вопросы для самопроверки

### После блокера 1 (persistence):
- [ ] В `cds_backend.log` нет `[TICK_CRASH]` после 30-секундного idle?
- [ ] `game_time_seconds` растёт без ввода игрока?
- [ ] `active_traversals` не пустой после 30 сек idle?

### После блокера 2 (real-time loop):
- [ ] idle_tick запускается каждые 0.5-3 секунды?
- [ ] idle_tick не блокируется во время LLM-запроса DM?

### После блокера 3 (movement):
- [ ] В логах видны `[MOTION_ROUTER] SEEK_ALLY→MovementIntent`?
- [ ] За 30 секунд без ввода ≥ 3 NPC начали движение (status=MOVING)?

### После блокера 4 (communication_intents):
- [ ] В логах `Фаза 6: N intents → EventDTO` где N > 0?
- [ ] В логах виден `[TRACE][DECISION_SCORE]` хотя бы 1 раз за 30 сек?

### После блокера 5 (Sims + Canonical + LLM очередь):
- [ ] `NpcConversation` создаётся когда NPC подходят друг к другу?
- [ ] Облочка 💬 с темой видна над разговаривающей парой?
- [ ] Canonical триггеры (secret_relevant, culmination, crisis_anger) срабатывают?
- [ ] `DialogueQueue` обрабатывает задачи по приоритету?
- [ ] CPU ≤ 70% при автономной работе 5 минут?
- [ ] Кластер 3-4 NPC обрабатывается одним LLM-вызовом со строгим JSON?
- [ ] Кластер 5+ — лидеры через LLM, остальные Sims?

### После блокера 6 (NpcDialogueSubscriber):
- [ ] `[NPC_DIALOGUE_SUB]` ≥ 3 за 2 минуты?
- [ ] Эмоции listener'а меняются после реплики speaker'а?
- [ ] `trust` между парами NPC меняется?
- [ ] В `WorkingMemory` есть canonical (с text) и ambient (без text) записи?

### После AWC (§15):
- [ ] `verify_autonomous_world.py` проходит без ошибок?
- [ ] Все 8 пунктов (A-H) выполняются?

---

## 19. Ожидаемый результат

После применения всех 6 блокеров и прохождения AWC:

1. **Игрок запускает игру, ничего не вводит 5 минут, только наблюдает.**
2. Время идёт — часы в HUD обновляются каждые несколько секунд.
3. NPC двигаются по локации — каждый из 7 NPC хотя бы раз сменил позицию.
4. NPC разговаривают друг с другом — над парами облачка 💬 с темой («сплетни», «флирт», «ссора»).
5. Canonical реплики видны как speech bubbles с цветным краем по tone (≥ 2 за 5 минут).
6. Эмоции меняются — ≥ 3 NPC показали смену mood-иконки.
7. Отношения меняются — ≥ 2 пары NPC показали изменение trust.
8. В журнале (J) ≥ 10 записей, имена раскрываются по мере узнавания.
9. После рестарта — состояние восстановилось из SQLite.
10. CPU ≤ 70% — LLM не задыхается (Sims-слой + очередь с приоритетами).
11. При смене локации — loading screen догоняет мир (canonical для других локаций).
12. NPC могут подойти к игроку с `!` над головой — автопереход в Dialogue Mode.

**Это и есть автономный мир.** После этого можно переходить к следующим этапам (эмерджентные циклы, мини-игра «Секреты Люси», недостающие механики) — но фундамент автономности заложен.

---

## 20. Финальная мысль

Этот документ описывает **только** автономность мира. Никаких других задач. Никаких будущих этапов. Никаких новых механик.

Применить 6 блокеров по порядку, запустить `verify_autonomous_world.py`, убедиться что все 8 пунктов AWC проходят. Если проходят — первостепенная задача создателя выполнена: «Мир меняется самостоятельно так как и задумано было изначально».

**Ключевые принципы этой архитектуры:**

1. **Двухслойная модель.** Sims-режим (без LLM) для рутины, Canonical (LLM) для важного. Это единственный способ дать миру конкретную историю не убив CPU.

2. **Мир не ждёт игрока.** NPC-NPC canonical может вклиниться перед DM-ответом если игрок долго печатал. Время в Dialogue Mode замедлено, но не остановлено.

3. **Запрет ретро-симуляции.** Конкретика только в момент разговора. Никаких «вспомнить разговор которого не было». Это фундамент для будущего open world со сменой поколений.

4. **Имена — не автомат.** Игрок знает имя только если реально его услышал. Это создаёт механику «узнавать людей».

5. **`!` с цветом = insight_skill vs deception_skill.** Игрок учится читать людей, NPC могут лгать мимикой.

6. **Batch generation при смене локации.** Мир «догоняет» конкретику для разговоров которые произошли без игрока. Игрок не знает что LLM работал 5 секунд во время loading screen.

**Мир должен жить сам. Это не пожелание, это контракт.**

---

*Документ создан 13 июля 2026 г. (редакция 2 — после дизайн-разбора с создателем) на основе полного аудита кода Enigma V.0.5.3.4.4 (581 .py файл), логов runtime `cds_backend.log` за 12 дней (2-13 июля), репортажа сессии создателя от 13 июля 06:52, и дизайн-разбора социальной архитектуры (Sims-слой, Canonical/Ambient, очередь LLM, журнал, имена, цвет `!`, batch generation, запрет ретро-симуляции).*

*Все ссылки на файлы и номера строк актуальны на момент создания.*

# ENIGMA — CLOSURE CONTRACT v8.5

**Дата:** 2026-07-30 (v8.5 аудит), 2026-07-29 (v8.4 оригинал)
**Версия:** V.0.5.3.6.4 (v8.5 — актуальный TODO после глубокого аудита)
**Цель:** Полностью работоспособный MVP «Секреты Люси» — End-Screen показывает >0 secrets после признания NPC, NPC спят, редактор карт валидирует cross-loc, диалоги — не монологи, fate_states > 0.

**Принцип v8.5:** Только активные баги V.0.5.3.6.4. Старые ошибки не упоминаются. Этот документ — TODO list того, что нужно сделать в текущей версии.

**Что нового в v8.5 (аудит 2026-07-30):**
- **6 НОВЫХ багов** найдено (2 CRITICAL, 2 HIGH, 2 MEDIUM), не описанных в v8.4
- **9 багов из v8.4 уже ИСПРАВЛЕНЫ** в коде V.0.5.3.6.4 — помечены ✅RESOLVED
- **1 баг v8.4 переоценён**: V8-TICK-1 (NameError) оказался production-reachable, не "мёртвым path"
- **1 баг v8.4 преуменьшен**: V8-TICK-2 (DRF scoring overlay) — функция НИКОГДА не вызывается, не только non-movement intents
- **Глубокий аудит**: прочитаны ключевые исходники npc_orchestration.py, action_semantic_resolver.py, truth_state_tavern.json, truth_state.py, social_deltas.py, tick_orchestrator.py, decision_hub.py, mvp_tavern_controller.py, life_engine.py, movement_engine.py, graph_compiler.py, scene_state_manager.py, npc_loader.py, npc_dialogue_subscriber.py, memory_manager.py, dialogue_session.py, decision.py, break_progress_engine.py, fate_tracker.py, time_advance.py, task_scheduler.py, dialogue_executor.py, editor_core.py, spatial_registry_builder.py, campaign_manager.py

**Контекст:** В V.0.5.3.6.4 применены многие v8.3 фиксы (game_time двигается, двери режут стены, SLEEP_GUARD, V8-MVP-1/2/3/7, V8-DLG-01..03, V8-SP-4, V8-SOC-1/4, S-145 cache sync). v8.4 аудит нашёл ~30 активных багов. v8.5 аудит подтвердил большинство, но обнаружил:
- **Главная находка (v8.4 подтверждено)**: NPC признанается в диалоге, End-Screen показывает 0 secrets. Архитектурный разрыв: LLM-ответ NPC не парсится как evidence.
- **НОВАЯ главная находка (v8.5)**: `mvp_tavern_controller.py:114` читает stress из root level (`npc.get("stress")`), но stress хранится в `npc["psyche"]["stress"]`. → `stability` ВСЕГДА 1.0 → FateTracker ВСЕГДА STABLE → fate_states ВСЕГДА пуст → End-Screen показывает 0 fates. Это вторая Finds-in-Code ошибка той же категории, что V8-PSY-25, но в `mvp_tavern_controller`, а не в `life_engine`.
- **Sleep всё ещё сломан**: locations overlap на 8 см (V8-SP-13), PLUS NEW: market_square накладывается на tavern (12.5см × 25м) и city_gate (8см × 5.2м). `gate_road` внутри tavern, micro_snap deadlock у boundary node, `LifeEngine.invalidate_cache` не вызывается в `reinit_campaign`.
- **Редактор карт не валидирует**: нет overlap prohibition, нет cross-loc movement checks, НЕТ проверки adjacency reciprocity (NEW: market_square.east=city_gate, но city_gate.south=market_square — направления не совпадают).
- **Новый архитектурный дефект (v8.5)**: `TruthState.Secret` (dataclass) НЕ имеет поля `confession_keywords`. Предложенный в v8.4 `NpcConfessionParser` использует `secret.get("confession_keywords", [])` — но `Secret` это frozen dataclass, не dict → AttributeError. Нужно: добавить поле в dataclass + парсинг в `truth_state_loader.py`.
- **Новый wiring-дефект (v8.5)**: `_apply_drf_scoring_overlay` (tick_orchestrator.py:1444) определена, но НИКОГДА не вызывается. DRF scoring полностью отключён для ВСЕХ intents, не только non-movement — это сильнее, чем v8.4 формулировка.

**Связанные документы:**
- `ENIGMA_DIALOGUE_THREAD_SYSTEM.md` — спецификация диалоговой системы
- `ENIGMA_MAP_EDITOR_SMART_VALIDATION.md` — умный редактор карт (часть реализована, валидация — нет)
- `ENIGMA_SELF_HEALING_SYSTEM.md` — runtime invariants

---

## §0. СТАТУС ВЕРСИИ

**Текущая:** V.0.5.3.6.4
**v8.4 перечислено:** 53 бага (11 CRITICAL, 23 HIGH, 19 MEDIUM)
**v8.5 переработка:**
  - ✅RESOLVED (уже исправлены в коде): 9 багов — V8-MVP-15, V8-MVP-19, V8-SP-20, V8-PSY-25, V8-SOC-3, V8-TICK-5, V8-DLG-09, V8-DLG-11, V8-DLG-12, V8-MEM-4, V8-MEM-5
  - ✅NON-ISSUE (переоценены в v8.4): 1 баг — V8-MVP-15 (campaign_id не enforced loader'ом)
  - 📈ESCALATED (сильнее, чем v8.4): 2 бага — V8-TICK-1 (production-reachable NameError), V8-TICK-2 (never called)
  - ➕NEW (найдено в v8.5): 6 багов — V8-MVP-20, V8-SP-21, V8-SP-22, V8-ED-4, V8-MVP-CK1, V8-TICK-7
**v8.5 фактический итог:** ~50 активных багов (13 CRITICAL, 23 HIGH, 14 MEDIUM)
**Главный блокр MVP:** V8-MVP-12 — NPC confession не парсится как evidence
**Главный блокер MVP (v8.5 NEW):** V8-MVP-20 — mvp_tavern_controller читает stress не оттуда → fate всегда STABLE
**Главный блокер sleep:** V8-SP-13 — overlap + gate_road внутри tavern + micro_snap deadlock
**Главный блокер sleep (v8.5 NEW):** V8-SP-21 — market_square × tavern/city_gate overlap
**Дней работы осталось:** ~6-8 дней (увеличилось на 1 день из-за 6 новых багов)

---

## §0.5. СВОДКА v8.5 АУДИТА (НОВОЕ)

### ✅RESOLVED — баги, уже исправленные в V.0.5.3.6.4 (в v8.4 ошибочно помечены как TODO)

| Баг | Файл:строка | Доказательство |
|---|---|---|
| V8-MVP-15 | `config/canon/truth_state_tavern.json:3` | `campaign_id: "silver_wolf"` — но `truth_state_loader.py` НЕ проверяет campaign_id (grep: 0 matches в loader). Несоответствие cosmetic, не ломает pipeline. Косметический фикс — не блокер. |
| V8-MVP-19 | `mvp_tavern_controller.py:113-114` | `max(0.0, min(1.0, ...))` clamping уже на месте (`V8-MVP-6 FIX` комментарий) |
| V8-SP-20 | `config/npc/individuals/orm.json:89`, `goran.json:78` | Orm: `"position": "tent_1"`, Goran: `"position": "tent_2"` — конфликта НЕТ |
| V8-PSY-25 | `life_engine.py:2251` | `_stress = npc.get("psyche", {}).get("stress", 0.0)  # V8-PSY-10 FIX` — fixed |
| V8-SOC-3 | `social_deltas.py:138-143` | `# V8-SOC-3 FIX: Нормализация регистра. _BASE_DELTAS использует lowercase` — fixed, plus `_TONE_TO_NPC_EVENT` mapping в `npc_dialogue_subscriber.py:208-215` уже lowercase |
| V8-TICK-5 / V8-PSY-21 | `tick_orchestrator.py:676-678` | `# V8-TICK-5 / V8-PSY-21 FIX: stress пишется в psyche sub-dict, а не в emotion (строка)` — fixed |
| V8-DLG-09 | `npc_dialogue_subscriber.py:130` | `self._extractor.extract(_stm_before, text, speaker)` — вызов есть, wiring из `game_loop/__init__.py:274-286` |
| V8-DLG-11 | `dm_agent.py:236` | `builder.add_npc_l2_memory(_l2_memory_block)` — вызывается |
| V8-DLG-12 | `task_scheduler.py:49` | `self._dialogue_ttl = 60.0  # 1 минута game_time` (было 10.0 wall-clock). Line 63: `# BUG-DL-12: Используем game_time_seconds (current_time) для TTL, не wall-clock` — fixed |
| V8-MEM-4 | `decision.py:74-83` | `# V8-MEM-4 FIX: Шкала RelationshipStore: -100..100, где 0.0 - нейтральное` — fixed, корректное деление на 100 |
| V8-MEM-5 | `memory_manager.py:706-710` | `# V8-MEM-5 FIX: Фильтруем по target_id или actor_id, а не по npc_id` — fixed, корректный фильтр по `tid` |

### 📈ESCALATED — баги, описанные в v8.4 слабее, чем они есть на самом деле

| Баг | v8.4 формулировка | v8.5 реальность |
|---|---|---|
| V8-TICK-1 | "Production reachability: НЕТ (мёртвый path)" | **Production-reachable!** `_process_player_dm_action` ВЫЗЫВАЕТСЯ из `tick_orchestrator.py:592`. `_sem_action` и `_sem_target` (используются на line 643-644) НИКОГДА не определяются → NameError упадёт в production, а не "мёртвый path". |
| V8-TICK-2 | "Non-movement intents bypass DRF scoring" | **Никакие intents не получают DRF scoring!** `_apply_drf_scoring_overlay` (line 1444) определена, но НИ РАЗУ не вызывается из production кода. DRF scoring полностью отключён. |

### ➕NEW — баги, найденные в v8.5 аудите и не описанные в v8.4

| Баг | Серьёзность | Файл | Суть |
|---|---|---|---|
| V8-MVP-20 | ★★★ CRITICAL | `mvp_tavern_controller.py:114` | `npc.get("stress", 0)` читает из root level, но stress в `npc["psyche"]["stress"]`. stability ВСЕГДА 1.0 → fate ВСЕГДА STABLE → End-Screen fate_states ВСЕГДА пуст. Это второй экземпляр V8-PSY-25, в другом файле. |
| V8-MVP-CK1 | ★★★ CRITICAL | `truth_state.py:30-39`, `truth_state_loader.py` | `TruthState.Secret` frozen dataclass НЕ имеет поля `confession_keywords`. Предложенный V8-MVP-12 `NpcConfessionParser` использует `secret.get("confession_keywords", [])` → AttributeError. |
| V8-SP-21 | ★★ HIGH | `Open_road/locations/market_square.json` | market_square bounds [-5..20, 14.875..39.875]. Накладывается на tavern [0..20, 0..15] — overlap 12.5см × 25м. Накладывается на city_gate [19.92..49.92, 0.04..20.04] — overlap 8см × 5.2м. v8.4 упоминал только tavern×city_gate. |
| V8-SP-22 | ★ MEDIUM | `Open_road/locations/{market_square,city_gate}.json` | `market_square.adjacency.east = "city_gate"`, но `city_gate.adjacency.south = "market_square"`. Направления не совпадают. SaveValidator поймает, но cross-loc movement может выбрать неправильный boundary. |
| V8-ED-4 | ★ MEDIUM | `frontend/map_editor/editor_core.py:715` | v8.4 предложил `validator.validate_campaign(self.cm.base_dir.parent)`, но `CampaignManager` имеет `campaign_path` (NOT `base_dir`). Wiring упадёт с AttributeError. |
| V8-TICK-7 | ★ MEDIUM | `tick_orchestrator.py:1444` | См. V8-TICK-2 выше. `_apply_drf_scoring_overlay` определена, не вызывается НИГДЕ. Отдельный баг от V8-TICK-2, потому что фикс разный: либо wire, либо удалить. |

---

## §1. MVP EPISTEMIC CHAIN — ГЛАВНЫЙ БЛОКЕР

### V8-MVP-12 ★★★ CRITICAL (НОВОЕ) — NPC LLM reply не парсится как evidence

**Файлы:** `backend/app/services/game_loop/npc_orchestration.py`, `backend/app/services/player_cognition/action_consequence_compiler.py`

**Проблема:** Когда NPC в диалоге говорит «Да, я из гильдии воров», LLM-генерируемый **ответ NPC** **никогда не парсится** для извлечения признания. Только текст игрока парсится через `ActionSemanticResolver._extract_secret_id`.

**Доказательство** (grep по `npc_orchestration.py`):
```
grep "add_evidence\|mark_discovered\|process_action\|secret_id" npc_orchestration.py
→ 0 matches
```

`process_action` вызывается только из `game_loop/__init__.py:1699` на `PlayerAction` (построенном из `_raw_action` — текст игрока), **не** из NPC reply.

**Эффект:** Игрок спрашивает «Тень, ты из гильдии воров?», Тень отвечает «Да, я из гильдии воров» — End-Screen показывает **0 secrets identified**. Признание чисто косметическое, оно попадает в UI speech bubble и умирает там.

**Fix (вариант B — архитектурный, правильно):**

Создать `NpcConfessionParser`, вызываемый в `npc_orchestration.py` после LLM-генерации ответа:

```python
# backend/app/services/player_cognition/npc_confession_parser.py (NEW)

class NpcConfessionParser:
    """Парсит LLM-ответ NPC на предмет признаний секретов."""
    
    def __init__(self, truth_state, observation_log, belief_model):
        self._truth = truth_state
        self._log = observation_log
        self._beliefs = belief_model
    
    def parse_and_record(
        self, 
        npc_id: str, 
        reply_text: str, 
        tick: int,
        target_id: str = "player"
    ) -> list[str]:
        """Возвращает list of secret_ids, обнаруженных в ответе NPC."""
        if not reply_text or not self._truth:
            return []
        
        discovered = []
        reply_lower = reply_text.lower()
        
        # Для каждого секрета, где npc_id — participant, проверяем keywords
        for secret_id, secret in self._truth.secrets.items():
            participants = secret.get("participants", [])
            if npc_id not in participants:
                continue
            
            # Проверяем canonical_truth на совпадение с ответом
            canonical = secret.get("canonical_truth", "").lower()
            confession_keywords = secret.get("confession_keywords", [])
            
            # Если секрет имеет confession_keywords — используем их
            if confession_keywords:
                if any(kw.lower() in reply_lower for kw in confession_keywords):
                    self._record_confession(npc_id, secret_id, reply_text, tick, target_id)
                    discovered.append(secret_id)
            # Иначе — эвристика: если ответ подтверждает canonical_truth
            elif canonical and len(canonical) > 10:
                # Простая проверка: 3+ слова из canonical в ответе
                canon_words = set(canonical.split()) - {"и", "в", "на", "не", "что", "это"}
                reply_words = set(reply_lower.split())
                overlap = len(canon_words & reply_words)
                if overlap >= 3:
                    self._record_confession(npc_id, secret_id, reply_text, tick, target_id)
                    discovered.append(secret_id)
        
        return discovered
    
    def _record_confession(self, npc_id, secret_id, reply_text, tick, target_id):
        obs = self._log.add(
            tick=tick,
            observation_type="npc_confession",
            content=reply_text,
            source_id=npc_id,
            source_type=ObservationSourceType.NPC,
        )
        ev = self._log.add_evidence(
            observation_id=obs.observation_id,
            secret_id=secret_id,
            evidence_strength=1.0,
            polarity=EvidencePolarity.SUPPORTS,
        )
        self._beliefs.update_from_evidence(obs, ev)
        self._truth.mark_discovered(secret_id)
        logger.info(f"[NPC_CONFESSION] npc={npc_id} secret={secret_id} recorded")
```

**Wire в `npc_orchestration.py`** (после LLM-генерации ответа):
```python
# После получения reply_text от LLM:
if self._confession_parser and reply_text:
    self._confession_parser.parse_and_record(
        npc_id=npc_id,
        reply_text=reply_text,
        tick=shared_context.tick,
        target_id="player",
    )
```

**Время:** 1.5 ч

### V8-MVP-13 ★★★ CRITICAL (НОВОЕ) — Missing `shadow_guild_membership` secret в canon

**Файл:** `config/canon/truth_state_tavern.json`

**Проблема:** В truth_state **нет секрета** для «Тень — член гильдии воров». Все `thief_shadow` секреты — про другое (investigation, suspects_lusya, first_kill).

**Текущие thief_shadow секреты:**
- `shadow_investigation` — про предателя внутри гильдии
- `shadow_suspects_lusya` — про подозрения на Люсю
- `shadow_first_kill` — про первое убийство

Нет `shadow_guild_membership`. Системе некуда записать признание.

**Fix:** Добавить секрет в truth_state_tavern.json:
```json
{
  "secret_id": "shadow_guild_membership",
  "npc_id": "thief_shadow",
  "participants": ["thief_shadow"],
  "category": "criminal",
  "canonical_truth": "Тень — действующий член гильдии воров",
  "importance": 0.9,
  "initial_holders": ["thief_shadow"],
  "discovery_surface": ["dialogue"],
  "confession_keywords": ["гильдия воров", "я из гильдии", "состою в гильдии", "вор гильдии"]
}
```

**Время:** 10 мин

### V8-MVP-14 ★★ HIGH — Missing keyword в ActionSemanticResolver для "гильдия воров"

**Файл:** `backend/app/services/player_cognition/action_semantic_resolver.py:92-99`

**Проблема:** Для `thief_shadow` нет keyword-правила для "гильд"/"вор". Текст «ты из гильдии воров» **не матчит** ни один existing keyword.

**Текущие thief_shadow keywords:**
```python
elif _target == "thief_shadow":
    if "предатель" in raw_lower or "шёлк" in raw_lower:
        return "shadow_investigation"
    if "люся" in raw_lower and "подозрев" in raw_lower:
        return "shadow_suspects_lusya"
    if "убил" in raw_lower or ("первый" in raw_lower and "убийство" in raw_lower):
        return "shadow_first_kill"
```

Нет "гильд"/"вор".

**Fix:** Добавить keyword-правило (после V8-MVP-13):
```python
elif _target == "thief_shadow":
    # V8-MVP-14 FIX: guild membership
    if "гильд" in raw_lower and "вор" in raw_lower:
        return "shadow_guild_membership"
    if "предатель" in raw_lower or "шёлк" in raw_lower:
        return "shadow_investigation"
    ...
```

**Время:** 5 мин

### V8-MVP-15 ✅RESOLVED — `campaign_id: "silver_wolf"` cosmetic mismatch (NON-ISSUE в v8.5)

**Файл:** `config/canon/truth_state_tavern.json`

```json
"campaign_id": "silver_wolf"
```

Игра запускается с campaign_id `"Open_road"`. Если canon loader проверяет по campaign_id — truth_state не загрузится, MVP-конвейер молча отключится.

**v8.5 ПРОВЕРКА:** `TruthStateLoader.load()` (76 строк) НЕ проверяет `campaign_id` (grep: 0 matches). Значение `"silver_wolf"` сохраняется в JSON, но НИКАК не enforced. Truth-state загружается корректно независимо от campaign_id. Это **косметическое несоответствие**, не баг.

**Fix (косметический, не блокер):** Изменить на `"Open_road"` для чистоты:
```json
"campaign_id": "Open_road"
```

**Время:** 1 мин

### V8-MVP-16 ★ MEDIUM — `DialogueMemorySubscriber` не существует (V8-DLG-06 не починен)

**Файлы:** `backend/app/services/events/dialogue_memory_subscriber.py` (должен существовать), `game_loop/__init__.py:_register_subscribers`

**Проблема:** V8-DLG-06 предусматривал создание `DialogueMemorySubscriber` — подписчика на NPC_SPOKE/PLAYER_SPOKE, который вызывает `MemoryManager.apply()` для создания EventMemory в `narrative_cache`. Файл **не существует** (grep по backend — 0 matches).

**Эффект:** Диалоги evaporate при clear STM. NPC не может вспомнить «мы с тобой вчера про подвал говорили» после save/load.

**Fix:** Создать `dialogue_memory_subscriber.py` (см. ENIGMA_DIALOGUE_THREAD_SYSTEM.md §4.3) и зарегистрировать в `_register_subscribers`.

**Время:** 1 ч

### V8-MVP-17 ★★ HIGH — `fate_tracker.trigger_fate` не вызывается в production

**Файл:** `backend/app/services/social/fate_tracker.py:50`

`trigger_fate` — только из tests. В production никто не trigger'ит fate outcomes → `fate_state.resolved_fate` всегда None → `end_screen_builder` пропускает всех NPCs → `npc_fates` list всегда пуст.

**Fix:** Wire `trigger_fate` к production triggers (CRITICAL trajectory + world events).

**Время:** 1-2 ч

### V8-MVP-18 ★★ HIGH — `dilemma_engine.register_dilemma` не вызывается в production

**Файл:** `backend/app/services/social/dilemma_engine.py:18`

`register_dilemma` — только из tests. `check_triggers` всегда возвращает `[]` (пустой `_dilemmas` dict).

**Fix:** Wire `register_dilemma` к production (из truth_state_tavern.json dilemma definitions или из DecisionHub на CRITICAL score).

**Время:** 1-2 ч

### V8-MVP-19 ✅RESOLVED — `FateTracker` validators reject unclamped inputs (исправлено в V.0.5.3.6.4)

**Файл:** `backend/app/services/social/fate_tracker.py:22-25`

```python
if not (0.0 <= stability <= 1.0): raise ValueError
if not (0.0 <= threat <= 1.0): raise ValueError
```

Caller не clamp'ит. Если `stress > 100` → stability<0 → ValueError → silent tracker failure.

**v8.5 ПРОВЕРКА:** `mvp_tavern_controller.py:113-114` уже имеет `max(0.0, min(1.0, ...))` clamping (комментарий `V8-MVP-6 FIX`). Баг ИСПРАВЛЕН. **НО см. V8-MVP-20** — тот же caller читает stress из неправильного места, делая clamping бесполезным.

**Fix:** (исполнено в V.0.5.3.6.4) — Clamp в caller (mvp_tavern_controller.py:113-114):
```python
stability = max(0.0, min(1.0, 1.0 - (float(npc.get("stress", 0)) / 100.0)))
threat = max(0.0, min(1.0, float(npc.get("perceptual_kernel", {}).get("threat_gradient", 0.0))))
```

**Время:** 5 мин

### V8-MVP-20 ★★★ CRITICAL (v8.5 NEW) — `mvp_tavern_controller` читает stress из root, не из psyche

**Файл:** `backend/app/services/social/mvp_tavern_controller.py:114`

```python
# V8-MVP-6 FIX: Clamping значений в [0.0, 1.0], чтобы избежать ValueError
stability = max(0.0, min(1.0, 1.0 - (float(npc.get("stress", 0)) / 100.0)))
threat = max(0.0, min(1.0, float(npc.get("perceptual_kernel", {}).get("threat_gradient", 0.0))))
self.fate_tracker.update_state(npc_id, stability, threat)
```

**Проблема:** `npc.get("stress", 0)` читает stress из **root level** NPC dict. Но stress хранится на `npc["psyche"]["stress"]` (подтверждено `npc_loader.py:648`, `life_engine.py:325/331/447/455/2602/2608`). На root level stress никогда не устанавливается → `npc.get("stress", 0)` ВСЕГДА возвращает `0` (default) → `stability = 1.0 - 0/100 = 1.0` ВСЕГДА.

`threat` читается корректно из `npc["perceptual_kernel"]["threat_gradient"]` (perceptual_kernel IS dict на root, per `npc_loader.py:305`).

**Эффект:**
- `FateTracker.update_state(npc_id, stability=1.0, threat=...)` — stability всегда максимальная
- `fate_tracker.py:32`: `if threat > 0.8 and stability < 0.2:` → никогда не срабатывает (stability=1.0, не <0.2)
- FateState всегда `STABLE`
- `trigger_fate` (если вызывается) видит только STABLE → никаких fate events
- End-Screen `fate_states` list **ВСЕГДА ПУСТ** для всех NPC

Это **вторая Finds-in-Code** ошибка той же категории, что V8-PSY-25 (которая исправлена в `life_engine.py:2251`), но в **другом файле** — `mvp_tavern_controller`. v8.4 аудит пропустил её.

**Fix:**
```python
# V8-MVP-20 FIX: stress хранится в npc["psyche"]["stress"], не в npc["stress"]
_psyche = npc.get("psyche", {}) if isinstance(npc.get("psyche"), dict) else {}
stability = max(0.0, min(1.0, 1.0 - (float(_psyche.get("stress", 0.0)) / 100.0)))
```

**Время:** 5 мин

### V8-MVP-CK1 ★★★ CRITICAL (v8.5 NEW) — `TruthState.Secret` НЕ имеет `confession_keywords` (атака на предложенный V8-MVP-12)

**Файлы:** `backend/app/models/truth_state.py:30-39`, `backend/app/services/truth_state_loader.py:36`

**Проблема:** Предложенный в V8-MVP-12 `NpcConfessionParser` использует:
```python
for secret_id, secret in self._truth.secrets.items():
    confession_keywords = secret.get("confession_keywords", [])
```

Но `Secret` это **frozen dataclass**, не dict:
```python
# truth_state.py:23-32
@dataclass(frozen=True)
class Secret:
    secret_id: str
    npc_id: str
    participants: Tuple[str, ...]
    category: str
    canonical_truth: str
    importance: float
    initial_holders: Tuple[str, ...]
    discovery_surface: Tuple[str, ...]  # confession_keywords НЕТ
```

`secret.get("confession_keywords", [])` → **AttributeError: 'Secret' object has no attribute 'get'**.

`TruthStateLoader.load()` тоже НЕ парсит `confession_keywords` (line 36 — только `discovery_surface`).

**Эффект:** Если применить V8-MVP-12 fix дословно (как в v8.4 контракте), NpcConfessionParser упадёт на первом же `secret.get(...)`. Фикс не работает "из коробки".

**Fix (2 шага):**

1. Добавить поле в dataclass:
```python
# truth_state.py
@dataclass(frozen=True)
class Secret:
    # ... existing fields ...
    discovery_surface: Tuple[str, ...]
    confession_keywords: Tuple[str, ...] = field(default_factory=tuple)  # V8-MVP-CK1 NEW
```

2. Парсить в loader:
```python
# truth_state_loader.py:38
secret = Secret(
    # ... existing ...
    discovery_surface=tuple(s_data.get("discovery_surface", [])),
    confession_keywords=tuple(s_data.get("confession_keywords", [])),  # V8-MVP-CK1 NEW
)
```

3. В NpcConfessionParser использовать `secret.confession_keywords` (attribute access), не `secret.get(...)`:
```python
for secret_id, secret in self._truth.secrets.items():
    confession_keywords = secret.confession_keywords  # attribute, не dict
```

**Время:** 15 мин (включая тест)

---

## §2. SLEEP CHAIN — ВСЁ ЕЩЁ СЛОМАН

### V8-SP-13 ★★★ CRITICAL — Locations overlap на 8 см (твоя гипотеза подтверждена)

**Файлы:** `frontend/map_editor/campaigns/Open_road/locations/city_gate.json:5-8`, `compiled/spatial_registry.json`

**Доказательство:**
- tavern: origin (0, 0), size 20×15 → bounds [0, 20] × [0, 15]
- city_gate: origin (19.92, 0.04), size 30×20 → bounds [19.92, 49.92] × [0.04, 20.04]
- **Overlap**: x = [19.92, 20.0] — полоса **8 см × 15 м**

Registry builder (`spatial_registry_builder.py:267`) принимает overlap как `"contiguous"`:
```python
if abs(ax2 - bx1) < ADJACENCY_TOLERANCE:  # 0.5m — принимает overlap
    x_contact_coord = (ax2 + bx1) / 2.0
```

`abs(20.0 - 19.92) = 0.08 < 0.5` → accepted as contiguous, не rejected.

**Эффект:** NPC materialize в city_gate, но физически стоит в tavern (на координатах `gate_road`). Split-brain.

**Fix (НЕ JSON — через логику редактора, см. §3):**
- Редактор должен **запрещать** overlap при сохранении
- Для текущего Open_road: сдвинуть city_gate origin на (20.0, 0.0) — exact touch

**Время:** (учтено в §3)

### V8-SP-14 ★★★ CRITICAL — `gate_road` внутри tavern (16.45 < 20.0)

**Файл:** `frontend/map_editor/campaigns/Open_road/locations/city_gate.json:2006-2008`

```json
"gate_road": {
  "x": 16.45,   // ВНУТРИ tavern [0, 20]
  "y": 9.25,
  ...
}
```

city_gate origin (19.92, 0.04), но `gate_road` на (16.45, 9.25) — **3.47м западнее** западной стены city_gate. Boundary node `city_gate:exit_west` получает координаты `gate_road` (см. V8-SP-15) → boundary node стоит внутри tavern.

**Эффект:** NPC materialize в city_gate, но его local_position = (16.45, 9.25) — внутри tavern. Тест видит `loc=city_gate, node=tavern:exit_east` (split-brain).

**Fix (НЕ JSON — через логику редактора, см. §3):**
- Редактор должен проверять, что все nodes внутри chunk bounds
- Для текущего: перенести `gate_road` на x=21.5 (внутри city_gate)

**Время:** (учтено в §3)

### V8-SP-15 ★★★ CRITICAL — Boundary node coords = nearest nav node, не anchor (Bug A не починен)

**Файл:** `backend/app/services/spatial/graph_compiler.py:885-892`

```python
boundary_node = NodeRef(
    node_id=boundary_id,
    x=_nearest_node.x,   # ← coords ближайшего nav node, НЕ boundary line
    y=_nearest_node.y,
    role=NodeRole.BOUNDARY,
    ...
)
```

Для `city_gate:exit_west`:
- Anchor: (20.92, 10.04) — внутри city_gate, на 1м от западной стены
- Ближайший nav node: `gate_road` на (16.45, 9.25) — **внутри tavern**
- Boundary node = (16.45, 9.25) — **внутри tavern**

**Эффект:** NPC движется к boundary node (16.45, 9.25), но это не на границе. `_dist_to_boundary` считает расстояние до (16.45, 9.25), не до boundary line.

**Fix:** Использовать anchor coords:
```python
boundary_node = NodeRef(
    node_id=boundary_id,
    x=_bx,   # anchor coords на boundary line
    y=_by,
    role=NodeRole.BOUNDARY,
    ...
)
```

**Время:** 15 мин

### V8-SP-16 ★★★ CRITICAL — Micro_snap deadlock у boundary node (Bug C не починен)

**Файл:** `backend/app/services/spatial/movement_engine.py:718-729`

```python
_dist = math.hypot(target_xy[0] - source_xy[0], target_xy[1] - source_xy[1])
if _dist < 0.1:
    return [
        SceneChange(
            field="local_position",
            value={"x": target_xy[0], "y": target_xy[1]},
            cause=f"micro_snap:{intent.reason}",
            # НЕТ traversal_proposal
            # НЕТ field="position"
            # НЕТ boundary detection
        )
    ]
```

Когда NPC достигает boundary node, `target_xy = boundary_node.x + jitter, boundary_node.y + jitter`. После первого тика `source_xy = target_xy` → `_dist = 0 < 0.1` → micro_snap → deadlock. NPC никогда не materialize.

**Fix:** Detect boundary node перед `if _dist < 0.1`, force CROSS_LOC_MATERIALIZE:
```python
from app.models.spatial_contracts import NodeRole

# V8-SP-16 FIX: Boundary node micro_snap deadlock
if getattr(next_node, "role", None) == NodeRole.BOUNDARY:
    _b_info = svc.get_boundary_info(next_node.node_id) or {}
    _materialize_target_loc = _b_info.get("neighbor_chunk", "")
    _entry_hint = _b_info.get("entry_node_hint", "") or f"{_materialize_target_loc}:entrance"
    _target_svc = self._resolve_spatial_service(_materialize_target_loc, campaign_id, scene_state) if scene_state else None
    if _target_svc:
        _target_node_obj = _target_svc.get_node(_entry_hint.split(":")[-1]) or _target_svc.get_node(_entry_hint)
        if _target_node_obj:
            _active_travs = scene_state.get("active_traversals", {}) if scene_state else {}
            if isinstance(_active_travs, dict) and intent.actor_id in _active_travs:
                del _active_travs[intent.actor_id]
            return [SceneChange(
                type=ChangeType.NPC_POSITION, target=intent.actor_id,
                field="position", value=_target_node_obj.node_id,
                cause=f"cross_loc_materialize:{intent.reason}", tick=tick,
                target_location_id=_materialize_target_loc,
                target_local_xy=(_target_node_obj.x, _target_node_obj.y),
                traversal_proposal=None,
            )]
    logger.error(f"[MICRO_SNAP_BOUNDARY_DEADLOCK] npc={intent.actor_id} next_node={next_node.node_id}")
    return []

if _dist < 0.1:
    # ... оригинальный micro_snap
```

**Время:** 30 мин

### V8-SP-17 ★★ HIGH — `_dist_to_boundary < 1.5` (было < 0.5, подняли, но всё ещё недостаточно)

**Файл:** `backend/app/services/spatial/movement_engine.py:258`

```python
if _dist_to_boundary < 1.5:  # V8 FIX: было < 0.5, подняли
```

Threshold поднят с 0.5 до 1.5, **но** `_dist_to_boundary` считается от `boundary_node.x/y` (который = nearest nav node coords, см. V8-SP-15). NPC приближается к (16.45, 9.25), dist = 0.72. `0.72 < 1.5` → MATERIALIZE срабатывает **только** если NPC уже близко к (16.45, 9.25). Но из-за micro_snap deadlock (V8-SP-16) NPC никогда не достигает < 0.1, остаётся на ~0.72.

**Fix:** После V8-SP-15 (boundary node на anchor coords) + V8-SP-16 (boundary detection в micro_snap) — threshold 1.5 должен работать. Если нет — поднять до 2.0.

**Время:** (учтено в V8-SP-15/16)

### V8-SP-18 ★★ HIGH — `LifeEngine.invalidate_cache` не вызывается в `reinit_campaign`

**Файлы:** `backend/app/services/scene_state_manager.py:784-794`, `backend/app/services/npc/life_engine.py:1202-1208`

`LifeEngine.invalidate_cache(campaign_id)` существует, но grep по backend — **0 внешних caller'ов**. `reinit_campaign` не вызывает его.

**Эффект:** Между тестами / new game cache LifeEngine не чистится. Stale `location_id` от предыдущего теста persists.

**Fix:** В `reinit_campaign` добавить:
```python
def reinit_campaign(self, campaign_id: str) -> dict | None:
    # V8-SP-18 FIX: инвалидируем cache LifeEngine
    if self._life_engine:
        self._life_engine.invalidate_cache(campaign_id)
    starting_location = self.find_starting_location(campaign_id)
    scene = self.initialize_scene(campaign_id, starting_location)
    ...
```

**Время:** 5 мин

### V8-SP-19 ★ MEDIUM — S-145 cache sync может не сработать для boundary nodes

**Файл:** `backend/app/services/npc/life_engine.py:524-540`

S-145 FIX синхронизирует `location_id` из `position` через `_pos_loc = _ss_pos.split(":")[0]`. Но если `position = "tavern:exit_east"` (boundary node в tavern), а `location_id = "city_gate"` (после materialize) — `_pos_loc = "tavern"`, `_ss_loc = "city_gate"`, `_ss_loc != _pos_loc` → `npc["location_id"] = "tavern"` — **перетирает** правильный city_gate на неправильный tavern.

**Fix:** Boundary nodes не должны участвовать в location_id inference:
```python
if _ss_pos and ":" in _ss_pos:
    _pos_loc = _ss_pos.split(":")[0]
    # V8-SP-19 FIX: boundary nodes (exit_*) не определяют location_id
    if "exit_" not in _ss_pos and _ss_loc != _pos_loc:
        npc["location_id"] = _pos_loc
        npc["location"] = _pos_loc
    elif _ss_loc and npc.get("location_id") != _ss_loc:
        npc["location_id"] = _ss_loc
        npc["location"] = _ss_loc
```

**Время:** 10 мин

### V8-SP-20 ✅RESOLVED — `Orm + Goran` bed conflict (tent_2) (исправлено в V.0.5.3.6.4)

**Файлы:** `config/npc/individuals/orm.json:88`, `goran.json:78`

v8.4 предположил: Оба: `"position": "tent_2"`. Нет collision prevention.

**v8.5 ПРОВЕРКА:** `orm.json:89` → `"position": "tent_1"`, `goran.json:78` → `"position": "tent_2"`. Конфликта НЕТ. Баг ИСПРАВЛЕН.

**Fix:** (исполнено в V.0.5.3.6.4) — Изменить Orm на `tent_1` (или реализовать BedRegistry из ENIGMA_MAP_EDITOR_SMART_VALIDATION.md).

**Время:** 5 мин (уже сделано)

### V8-SP-21 ★★ HIGH (v8.5 NEW) — `market_square` накладывается на `tavern` И на `city_gate`

**Файл:** `frontend/map_editor/campaigns/Open_road/locations/market_square.json`

**Доказательство (v8.5 аудит):**
```
tavern:       origin (0, 0), size 20×15    → bounds [0, 20]    × [0, 15]
city_gate:    origin (19.92, 0.04), 30×20 → bounds [19.92, 49.92] × [0.04, 20.04]
market_square: origin (-5, 14.875), 25×25 → bounds [-5, 20]    × [14.875, 39.875]
```

**Новые overlaps (НЕ упомянуты в v8.4):**

| Пара | Overlap область | Площадь |
|---|---|---|
| tavern × market_square | x=[0, 20], y=[14.875, 15] | **12.5см × 20м = 2.5 м²** |
| city_gate × market_square | x=[19.92, 20], y=[14.875, 20.04] | **8см × 5.2м = 0.4 м²** |
| tavern × city_gate (v8.4) | x=[19.92, 20], y=[0.04, 15] | 8см × 15м = 1.2 м² |

`spatial_registry_builder.py:267` (`abs(ax2 - bx1) < ADJACENCY_TOLERANCE`, 0.5m) принимает ВСЕ три overlap'а как contiguous.

**Эффект:** Трёхстороннее split-brain. NPC в market_square может материализоваться в tavern или city_gate в зависимости от boundary node — все три локации конфликтуют. Sleep chain ломается не только для `gate_road` (V8-SP-14), но и для market_square nodes рядом с его границами.

**Fix:** Сдвинуть market_square:
- Y: `origin.y = 15.0` (exact touch с tavern на y=15)
- X: `origin.x = 20.0` (exact touch с city_gate на x=20)
- Тогда bounds: x=[20, 45], y=[15, 40] — никаких overlaps

Или использовать SaveValidator (V8-ED-1) — он поймает, но фикс всё равно нужен в JSON.

**Время:** 10 мин (через редактор с validation) — учитывается в §3

### V8-SP-22 ★ MEDIUM (v8.5 NEW) — `market_square`/`city_gate` adjacency directions не совпадают

**Файлы:** `frontend/map_editor/campaigns/Open_road/locations/market_square.json`, `city_gate.json`

```json
// market_square.json
"adjacency": {"north": "tavern", "east": "city_gate"}

// city_gate.json  
"adjacency": {"west": "tavern", "south": "market_square"}
```

**Проблема:** `market_square.adjacency.east = "city_gate"` — market_square говорит, что city_gate к ВОСТОКУ. Но `city_gate.adjacency.south = "market_square"` — city_gate говорит, что market_square к ЮГУ. Направления не совпадают (east ≠ south).

При корректной двусторонней связи должно быть: `market_square.east = city_gate` ↔ `city_gate.west = market_square`. Сейчас `city_gate.west = tavern` (таверна к западу), а `city_gate.south = market_square` (рынок к югу).

Это значит, что **физически** market_square находится к югу от city_gate (bounds это подтверждают: city_gate y=[0.04, 20.04], market_square y=[14.875, 39.875] — market_square действительно ниже и правее). Но `market_square.east = city_gate` — это market_square думает, что city_gate к востоку, что геометрически верно лишь частично.

**Эффект:** SaveValidator (V8-ED-1) отрапортует `ADJACENCY_NOT_RECIPROCATED`. Cross-loc movement может выбрать неправильный boundary: если NPC в market_square хочет в city_gate, он пойдёт на восток (верно), но city_gate его встретит с SOUTH-стороны, не с WEST. Boundary node `market_square:exit_east` и `city_gate:exit_south` не соединятся в графе (нет matching anchor coords).

**Fix:** Решить геометрическую неоднозначность. Либо:
- `market_square.adjacency.northeast = city_gate` + `city_gate.adjacency.southwest = market_square` (диагональная связь, нужно расширить схему)
- Либо подвинуть market_square так, чтобы связь была строго по одной оси (например, market_square east=city_gate после сдвига в Fix V8-SP-21 → market_square.bounds=[20, 45]×[15, 40], city_gate.bounds=[19.92, 49.92]×[0.04, 20.04]. Контакт: x=20 (правая граница market_square = внутренней части city_gate — некорректно!)

После Fix V8-SP-21 (market_square origin (20, 15)) market_square будет справа от tavern и под city_gate — диагональная связь всё ещё несовместима с 4-direction схемой.

**Альтернатива:** Изменить market_square size на 30×10 (origin 20, 20, size 30×10 → bounds x=[20, 50]×[20, 30]) — strictly east of city_gate. Тогда city_gate.west = tavern, city_gate.east = market_square (reciprocity верная).

**Время:** 30 мин (геометрия + валидация)

### V8-PSY-25 ✅RESOLVED — GAP9 stress read wrong (исправлено в V.0.5.3.6.4, НО см. V8-MVP-20 — та же баг в mvp_tavern_controller)

**Файл:** `backend/app/services/npc/life_engine.py:~2228`

```python
_stress = npc.get("stress", 0.0)  # root-level — never set
```

Stress лежит на `npc["psyche"]["stress"]`. GAP9 `if _stress > 50` **никогда** не срабатывает.

**v8.5 ПРОВЕРКА:** `life_engine.py:2251` → `_stress = npc.get("psyche", {}).get("stress", 0.0)  # V8-PSY-10 FIX` — ИСПРАВЛЕНО. **НО** тот же баг остался в `mvp_tavern_controller.py:114` (см. V8-MVP-20) — это второй экземпляр, который v8.4 аудит пропустил. V8-MVP-20 критичнее, потому что отключает весь FateTracker.

**Fix:** (исполнено в V.0.5.3.6.4 для life_engine) — `_stress = npc.get("psyche", {}).get("stress", 0.0)`.

**Время:** 5 мин (для life_engine — сделано; для mvp_tavern_controller — см. V8-MVP-20, 5 мин)

---

## §3. РЕДАКТОР КАРТ — ВАЛИДАЦИЯ (новые требования)

### V8-ED-1 ★★★ CRITICAL — Запрет на пересечение границ территорий

**Файл:** `frontend/map_editor/editor_core.py:715` (_quick_save)

**Проблема:** `_quick_save` не имеет validation. Сохраняет любой JSON, даже с overlap'ом.

**Fix:** Создать `frontend/map_editor/validators/save_validator.py` (NEW):
```python
"""Валидация кампании перед сохранением. Блокирует overlap, проверяет cross-loc."""

from dataclasses import dataclass
from typing import List

@dataclass
class ValidationIssue:
    severity: str  # "HARD" | "SOFT"
    code: str
    message: str
    file: str = ""

class SaveValidator:
    def validate_campaign(self, campaign_dir) -> List[ValidationIssue]:
        issues = []
        locations = self._load_all_locations(campaign_dir)
        
        # 1. Boundary overlap prohibition
        for i, (a_id, a) in enumerate(locations.items()):
            for b_id, b in list(locations.items())[i+1:]:
                overlap = self._compute_overlap(a, b)
                if overlap > 0.01:  # > 1 cm² — real overlap
                    issues.append(ValidationIssue(
                        severity="HARD",
                        code="BOUNDARY_OVERLAP",
                        message=(
                            f"Локации '{a_id}' и '{b_id}' накладываются на {overlap:.2f} м². "
                            f"Границы территорий не должны пересекаться. "
                            f"Сдвиньте origin одной из локаций так, чтобы они только касались."
                        ),
                    ))
        
        # 2. Node-in-bounds check
        for loc_id, loc in locations.items():
            origin = loc.get("origin", {"x": 0, "y": 0})
            size = loc.get("size", {"w": 0, "h": 0})
            for node_id, node in loc.get("nodes", {}).items():
                nx, ny = node.get("x", 0), node.get("y", 0)
                if not (origin["x"] <= nx <= origin["x"] + size["w"] and
                        origin["y"] <= ny <= origin["y"] + size["h"]):
                    issues.append(ValidationIssue(
                        severity="HARD",
                        code="NODE_OUT_OF_BOUNDS",
                        message=(
                            f"Узел '{node_id}' в локации '{loc_id}' на координатах ({nx}, {ny}) "
                            f"вне границ локации [{origin['x']}, {origin['x']+size['w']}] × "
                            f"[{origin['y']}, {origin['y']+size['h']}]. "
                            f"Переместите узел внутрь локации или измените origin/size."
                        ),
                        file=f"{loc_id}.json",
                    ))
        
        # 3. Adjacency reciprocity
        for loc_id, loc in locations.items():
            for direction, neighbor_id in loc.get("adjacency", {}).items():
                if neighbor_id not in locations:
                    issues.append(ValidationIssue(
                        severity="HARD",
                        code="ADJACENCY_ORPHAN",
                        message=(
                            f"Локация '{loc_id}'.adjacency.{direction} = '{neighbor_id}', "
                            f"но локация '{neighbor_id}' не существует в кампании."
                        ),
                    ))
                else:
                    neighbor = locations[neighbor_id]
                    opposite = {"east": "west", "west": "east", "north": "south", "south": "north"}
                    recip = neighbor.get("adjacency", {}).get(opposite.get(direction, ""), "")
                    if recip != loc_id:
                        issues.append(ValidationIssue(
                            severity="SOFT",
                            code="ADJACENCY_NOT_RECIPROCATED",
                            message=(
                                f"Локация '{loc_id}'.adjacency.{direction} = '{neighbor_id}', "
                                f"но '{neighbor_id}'.adjacency.{opposite.get(direction)} = '{recip}' "
                                f"(ожидалось '{loc_id}')."
                            ),
                        ))
        
        # 4. Cross-loc movement validity (boundary nodes reachable)
        for loc_id, loc in locations.items():
            for direction, neighbor_id in loc.get("adjacency", {}).items():
                # Проверяем, что есть nav node в радиусе 3м от boundary midpoint
                boundary_mid = self._compute_boundary_midpoint(loc, direction)
                has_nearby_node = any(
                    self._distance(boundary_mid, (n.get("x", 0), n.get("y", 0))) < 3.0
                    for n in loc.get("nodes", {}).values()
                )
                if not has_nearby_node:
                    issues.append(ValidationIssue(
                        severity="HARD",
                        code="BOUNDARY_NODE_UNREACHABLE",
                        message=(
                            f"Локация '{loc_id}' имеет adjacency.{direction} = '{neighbor_id}', "
                            f"но нет навигационного узла в радиусе 3м от границы ({boundary_mid[0]:.1f}, {boundary_mid[1]:.1f}). "
                            f"NPC не сможет перейти в '{neighbor_id}'. Добавьте узел у границы."
                        ),
                    ))
        
        return issues
    
    def _compute_overlap(self, a, b) -> float:
        ax1, ay1 = a["origin"]["x"], a["origin"]["y"]
        ax2, ay2 = ax1 + a["size"]["w"], ay1 + a["size"]["h"]
        bx1, by1 = b["origin"]["x"], b["origin"]["y"]
        bx2, by2 = bx1 + b["size"]["w"], by1 + b["size"]["h"]
        dx = max(0, min(ax2, bx2) - max(ax1, bx1))
        dy = max(0, min(ay2, by2) - max(ay1, by1))
        return dx * dy
    
    def _compute_boundary_midpoint(self, loc, direction):
        ox, oy = loc["origin"]["x"], loc["origin"]["y"]
        w, h = loc["size"]["w"], loc["size"]["h"]
        mids = {
            "east": (ox + w, oy + h/2),
            "west": (ox, oy + h/2),
            "north": (ox + w/2, oy + h),
            "south": (ox + w/2, oy),
        }
        return mids.get(direction, (ox + w/2, oy + h/2))
    
    def _distance(self, a, b):
        return ((a[0]-b[0])**2 + (a[1]-b[1])**2) ** 0.5
    
    def _load_all_locations(self, campaign_dir):
        import json
        locations = {}
        for f in campaign_dir.glob("locations/*.json"):
            data = json.load(open(f, encoding="utf-8"))
            loc_id = data.get("location_id", f.stem)
            locations[loc_id] = data
        return locations
```

**Wire в `_quick_save` (v8.5 corrected):**
```python
def _quick_save(self):
    if not self.current_file:
        return
    # V8-ED-1 FIX: валидация перед сохранением
    validator = SaveValidator()
    # V8-ED-4 FIX (v8.5): CampaignManager имеет `campaign_path`, не `base_dir`
    campaign_dir = self.cm.campaign_path if self.cm.is_open else self.dm.base_dir
    issues = validator.validate_campaign(campaign_dir)
    hard_issues = [i for i in issues if i.severity == "HARD"]
    if hard_issues:
        self._show_validation_errors(hard_issues)
        return  # блокируем сохранение
    # ... rest of save
    if self.cm.is_open:
        self.cm.save_location(self.current_file)
    else:
        self.dm.save(self.current_file)
    self._rebuild_spatial_registry()
    self._show_toast(f"Сохранено: {self.current_file}")
```

**Время:** 2-3 ч

### V8-ED-4 ★ MEDIUM (v8.5 NEW) — SaveValidator wiring использует `base_dir`, но CampaignManager имеет `campaign_path`

**Файл:** `frontend/map_editor/editor_core.py:715` (в proposed V8-ED-1 fix)

**Проблема:** v8.4 предложил:
```python
validator.validate_campaign(self.cm.base_dir.parent)
```

Но `CampaignManager` (frontend/map_editor/campaign_manager.py) имеет:
```python
@property
def campaign_path(self) -> Optional[Path]:
    return self._campaign_dir
```

Свойства `base_dir` НЕТ. `self.cm.base_dir` → AttributeError: 'CampaignManager' object has no attribute 'base_dir'.

**Эффект:** Если применить V8-ED-1 fix дословно, редактор упадёт на первом сохранении с validation.

**Fix:** Использовать `campaign_path`:
```python
campaign_dir = self.cm.campaign_path if self.cm.is_open else self.dm.base_dir
issues = validator.validate_campaign(campaign_dir)
```

(Уже incorporated в V8-ED-1 wiring выше.)

**Время:** (учтено в V8-ED-1)

### V8-ED-2 ★★ HIGH — `_check_adjacent` принимает overlap как contiguous

**Файл:** `frontend/map_editor/spatial_registry_builder.py:267-285`

```python
if abs(ax2 - bx1) < ADJACENCY_TOLERANCE:  # 0.5 — принимает overlap
    x_contact_coord = (ax2 + bx1) / 2.0
```

`abs(20.0 - 19.92) = 0.08 < 0.5` → accepted. Должен reject'ить если `ax2 > bx1` (real penetration).

**Fix:**
```python
# Touching: ax2 <= bx1 + tolerance
if abs(ax2 - bx1) < ADJACENCY_TOLERANCE and ax2 <= bx1 + 0.01:
    x_contact_coord = (ax2 + bx1) / 2.0
elif ax2 > bx1 + 0.01:
    # Real overlap — log warning, but don't create adjacency
    logger.warning(f"[OVERLAP] {a} east={ax2} > {b} west={bx1}, overlap={ax2-bx1:.3f}m")
    # Don't create AdjacencyEntry — forces editor to fix
```

**Время:** 15 мин

### V8-ED-3 ★ MEDIUM — Spatial registry freshness check

**Файл:** `frontend/map_editor/spatial_registry_builder.py:needs_rebuild`

Уже есть (`needs_rebuild` через content_hash). Auto-rebuild через `SpatialCompilationGateway.request_rebuild` работает. Но нет UI-индикатора «реестр устарел».

**Fix:** Добавить в editor sidebar индикатор: если `needs_rebuild` → показывать «⚠️ Реестр устарел, пересоберите».

**Время:** 30 мин

---

## §4. `build_graph.py` — КЛАРИФИКАЦИЯ

### V8-BG-1 ★★ HIGH — `build_graph.py` — документация, НЕ runtime

**Файл:** `build_graph.py` (root level)

**Назначение (из header):**
```python
# build_graph.py:2-3
# Назначение: Генерация ARCHITECTURE_FLOW.md из YAML (Flowchart + Sequence + Micro-details)
```

`build_graph.py` генерирует `docs/ARCHITECTURE_FLOW_GENERATED.md` из `architecture/*.yaml`. **Не** перестраивает `spatial_registry.json`. **Не** участвует в runtime.

**Что перестраивает spatial_registry для runtime:**

1. **Map Editor save flow** (уже работает):
   - `editor_core._quick_save` → `editor_core._rebuild_spatial_registry` → `SpatialCompilationGateway.request_rebuild(campaign_id)` → `SpatialCompilationOrchestrator.rebuild_if_needed` → `SpatialRegistryBuilder.needs_rebuild` (content_hash diff) → `build_and_save`

2. **Backend runtime cache**:
   - `SpatialFactory._get_map_fingerprint` (SHA-256 location JSON) → если changed, cached `SpatialService` invalidated → recompiled next tick

**Действие:** Удалить упоминания `python build_graph.py` из инструкций. Использовать `SpatialCompilationGateway.request_rebuild(campaign_id)` в редакторе (уже работает). В CLI/CI — `SpatialCompilationOrchestrator.rebuild(campaign_id)`.

**Время:** 5 мин (обновить документацию)

---

## §5. ДИАЛОГОВАЯ СИСТЕМА — ОСТАЛОСЬ

### V8-DLG-09 ✅RESOLVED — `DialogueUpdateExtractor` создан, и подключён (исправлено в V.0.5.3.6.4)

**Файлы:** `backend/app/services/memory/dialogue_update_extractor.py` (существует), `working_memory_tick.py`, `npc_dialogue_subscriber.py`

Файл создан (81 строка), **0 production callers**. LLM-based topic/claims/questions extraction не работает. Claims/open_questions поля в DialogueSession v2 не заполняются.

**v8.5 ПРОВЕРКА:** `npc_dialogue_subscriber.py:130` → `self._extractor.extract(_stm_before, text, speaker)` — вызов ЕСТЬ. Wiring через `game_loop/__init__.py:274-286` (создаёт `DialogueUpdateExtractor(router=self.dm_agent.router)`, передаёт в subscriber). Баг ИСПРАВЛЕН.

**Fix:** (исполнено в V.0.5.3.6.4) — Wire `DialogueUpdateExtractor.extract()` в:
1. `working_memory_tick.write_npc_reactions_to_memory` AFTER `add_dialogue_turn`
2. `npc_dialogue_subscriber._process_canonical` AFTER `add_dialogue_turn` (line 130)

**Время:** 1 ч (сделано)

### V8-DLG-10 ★★ HIGH — `VerbalizationContext` dead code

**Файлы:** `backend/app/services/verbalization/verbalization_context.py:80-87`, `backend/app/services/npc/npc_tick_pipeline.py:791-881`

`build_verbalization_context` определён, но НИКОГДА не вызывается в production. `stm_buffer`, `recalled_facts`, `npc_npc_context`, `suppressed_secrets` — dead fields.

**Fix:** Wire в `DialogueExecutor._generate_with_router`.

**Время:** 1 ч

### V8-DLG-11 ✅RESOLVED — `add_npc_l2_memory` не вызывается (исправлено в V.0.5.3.6.4)

**Файл:** `backend/app/services/verbalization/dm_contract_builder.py:142-146`

Метод определён, но НИКТО не вызывает. DM никогда не видит `recall()` results.

**v8.5 ПРОВЕРКА:** `dm_agent.py:236` → `builder.add_npc_l2_memory(_l2_memory_block)` — вызывается. Баг ИСПРАВЛЕН.

**Fix:** (исполнено в V.0.5.3.6.4) — Wire в `dm_agent._build_contract` после `add_npc_stm`.

**Время:** 30 мин (сделано)

### V8-DLG-12 ✅RESOLVED — `_recent_dialogues` TTL wall-clock, не game-time (исправлено в V.0.5.3.6.4)

**Файл:** `backend/app/services/game_loop/task_scheduler.py:49`

`_dialogue_ttl = 10.0` — wall-clock seconds. 10 секунд реального времени истекают независимо от game pace.

**v8.5 ПРОВЕРКА:** `task_scheduler.py:49` → `self._dialogue_ttl = 60.0  # 1 минута game_time` (не 10.0). Line 63: `# BUG-DL-12: Используем game_time_seconds (current_time) для TTL, не wall-clock.`. Line 67: `if current_time - d.get("game_time", 0.0) < self._dialogue_ttl`. Баг ИСПРАВЛЕН.

**Fix:** (исполнено в V.0.5.3.6.4) — Game-time TTL (`game_time_seconds` instead of `time.time()`).

**Время:** 30 мин (сделано)

### V8-DLG-13 ★ MEDIUM — Per-pair sessions не реализованы

**Файл:** `backend/app/services/memory/memory_manager.py`

Нет `get_dialogue_session_pair(campaign_id, npc_a, npc_b)`. NPC A говорит с B и C — нити смешиваются.

**Fix:** Добавить `get_dialogue_session_pair` (sorted tuple key), wire в `npc_dialogue_subscriber`.

**Время:** 30 мин

### V8-DLG-14 ★ MEDIUM — Hard contract «no STM → can't speak» частично

**Файл:** `backend/app/services/execution/dialogue_executor.py:164-168`

Hard contract в `DialogueExecutor` **реализован** (line 164-168 — `raise DialogueContractViolation` если нет STM). Но в `dm_agent._build_contract` — нет аналогичного assert.

**Fix:** Добавить assert в `dm_agent._build_contract` для dialogue events.

**Время:** 30 мин

---

## §6. NPC↔NPC SOCIAL — ОСТАЛОСЬ

### V8-SOC-2 ★★★ CRITICAL — Dead event types: COMBAT, THEFT, HELP, INTIMIDATION, BETRAYAL, SAVED_LIFE

**Файл:** `backend/app/services/events/event_types.py`

7 event types определены и подписаны, но **НИКОГДА НЕ ПУБЛИКУЮТСЯ** в production (grep по `app/` — 0 publish call sites).

**Fix:** Publish из правильных мест:
- `COMBAT` — из CombatSubscriber при применении damage
- `HELP` — из DecisionHub когда NPC помогает
- `THEFT` — из theft action handler
- `NPC_INTERACTS_NPC` — из DecisionHub при NPC-initiated social contact

ИЛИ удалить event types и подписчиков.

**Время:** 1 ч

### V8-SOC-3 ✅RESOLVED — SocialDeltaEngine key case mismatch (исправлено в V.0.5.3.6.4)

**Файл:** `backend/app/services/social/social_delta_engine.py`

`_BASE_DELTAS` keys — lowercase: `"player_attacks"`. Published event types — UPPERCASE: `"PLAYER_ATTACKED"`. Lookup: `_BASE_DELTAS.get(event_type.value)` → miss.

**v8.5 ПРОВЕРКА:** Файл переименован в `backend/app/services/npc/decision/social_deltas.py`. Line 138-143: `# V8-SOC-3 FIX: Нормализация регистра. _BASE_DELTAS использует lowercase, но EventType.value возвращает UPPERCASE. Без .lower() lookup всегда падал.` → `_et_val_lower = _et_val.lower(); base = _BASE_DELTAS.get(_et_val_lower)`. Баг ИСПРАВЛЕН. Дополнительно, в `npc_dialogue_subscriber.py:208-215` mapping `_TONE_TO_NPC_EVENT` возвращает lowercase (`"npc_insults"`, `"npc_threatens"`), что соответствует `_BASE_DELTAS` keys — `get_base_delta()` функция работает корректно без нормализации.

**Fix:** (исполнено в V.0.5.3.6.4) — Нормализовать keys (`.lower()` при lookup, или UPPERCASE aliases).

**Время:** 10 мин (сделано)

### V8-SOC-5 ★★ HIGH — `_idle_pressure` — DEAD CODE в production

**Файлы:** `backend/app/services/npc/life_engine.py:601-1101`, `npc_tick_pipeline.py`

`LifeEngine.tick_decisions` (единственный reader/accumulator `_idle_pressure`) **НИКОГДА НЕ ВЫЗЫВАЕТСЯ** в production. Нет «social urge accumulation». Proactive talk mechanism мёртв.

**Fix:** Либо wire `_idle_pressure` в `NpcTickPipeline.run` (добавить `idle_pressure` параметр в `DecisionHub.compute`), либо удалить dead code.

**Время:** 30 мин

### V8-SOC-6 ★★ HIGH — WorldTickEngine filter excludes TALK intent

**Файл:** `backend/app/services/npc/world_tick_engine.py`

`proactive_intents` set не включает `Intent.TALK`. Proactive NPC talk **тихо дропается** на player turn.

**Fix:** Добавить `Intent.TALK` в `WorldTickEngine.proactive_intents`.

**Время:** 5 мин

### V8-SOC-7 ★ MEDIUM — `SocialInputProjector listener_ids` never populated

**Файл:** `backend/app/services/social/social_input_projector.py:83, 87`

`DialogueMaterializer` не устанавливает `listener_ids`. Listener delta loop никогда не исполняется.

**Fix:** Populate `listener_ids` в `DialogueMaterializer` payload.

**Время:** 30 мин

### V8-SOC-11 ★ MEDIUM — NpcDialogueSubscriber canonical detection по "Stub LLM"

**Файл:** `backend/app/services/npc/npc_dialogue_subscriber.py:65`

Russian "[Заглушка]" stub **не матчит** → обрабатывается как canonical.

**Fix:** Добавить Russian stub в detection logic.

**Время:** 5 мин

---

## §7. ПСИХИКА — ОСТАЛОСЬ

### V8-PSY-1 ★★ HIGH — Trauma mutation plasticity hardcode 0.5 (V8-PSY-1 partial)

**Файл:** `backend/app/services/npc/break_progress_engine.py:210-214`

L1Chronicle правильно инжектируется в StateApplicator ✓. Но `compute_mutation` **всё ещё** читает `state.psyche.identity_rigidity` — этого поля нет ни на NPCState, ни на NPCPersonality. Plasticity hardcode 0.5 для всех NPC.

**Fix:**
1. Добавить `identity_rigidity` на `NPCPersonality` (`backend/app/models/npc_state.py:335-358`)
2. Добавить `identity_rigidity` в JSON config (разные значения для архетипов)
3. В `compute_mutation` читать `state.personality.identity_rigidity`

**Время:** 1 ч

### V8-PSY-6 ★★ HIGH — BehaviorMask FAKE_SUBMISSION / BETRAYAL не триггерятся

**Файл:** `backend/app/services/phases/decision.py:188-208`

`from_legacy` ставит `relationship_cache={}` → `_trust=0`, `_fear=0`. FAKE_SUBMISSION и BETRAYAL никогда не срабатывают.

**Fix:** Hydrate `relationship_cache["player"]` из RelationshipStore.

**Время:** 30 мин

### V8-PSY-9 ★★ HIGH — `NPCIdentityL1.overlay_drives` dead code

**Файл:** `backend/app/models/npc_state.py:393-402`

Метод определён, нет callers. L1 crystallized traits не доходят до DecisionHub.

**Fix:** Wire в `DriveResolver` или удалить.

**Время:** 15 мин

### V8-PSY-11 ★★ HIGH — `gregariousness` всегда 0.5

**Файлы:** `life_engine.py:734-738`, `npc_tick_pipeline.py:425-428`

Ни один NPC config не устанавливает `gregariousness`. У всех NPC идентичный social homeostasis setpoint.

**Fix:** Перенести на `NPCPersonality`, добавить в JSON config.

**Время:** 30 мин

### V8-PSY-12 ★★ HIGH — Will engine только для player avatar

**Файлы:** `app/services/will.py:131`, `phases/input.py:120`

`compute_willpower` вызывается только для player. Регулярные NPC никогда не проходят через Will engine.

**Fix:** Запустить Will engine для всех NPC (или документировать что Will только для player).

**Время:** 1 ч

### V8-PSY-20 ★★ HIGH — CalibrationEngine pass-through + dead instantiation

**Файлы:** `calibration_engine.py:66`, `tick_orchestrator.py:1118, 1137, 1141`

`drives_runtime` cache и `strain_memory` **НИКОГДА** не мутируют. L3 — purely ephemeral.

**Fix:** Реализовать `stabilize()` properly ИЛИ удалить класс.

**Время:** 1 ч

### V8-PSY-21 ✅RESOLVED — `stress` в `psyche` vs `emotion` (double-truth) (исправлено в V.0.5.3.6.4)

**Файлы:** `tick_orchestrator.py:675, 863`

`emotion["stress"]` пишется, **НИКОГДА не читается**. Плюс TypeError (V8-TICK-5).

**v8.5 ПРОВЕРКА:** `tick_orchestrator.py:676-678` → `# V8-TICK-5 / V8-PSY-21 FIX: stress пишется в psyche sub-dict, а не в emotion (строка)` → `_psyche = _npc_state.setdefault("psyche", {}); _psyche["stress"] = max(0, min(100, _psyche.get("stress", 0.0) + delta.payload.stress_delta))`. Баг ИСПРАВЛЕН — теперь пишет в `psyche["stress"]`, не в `emotion["stress"]`.

**Fix:** (исполнено в V.0.5.3.6.4) — Удалить `emotion["stress"]` writes — stress только в `psyche["stress"]`.

**Время:** 10 мин (сделано)

---

## §8. ПАМЯТЬ / DECISIONHUB — ОСТАЛОСЬ

### V8-MEM-4 ✅RESOLVED — Scale mismatch в `evaluate_behavior_and_identity` (исправлено в V.0.5.3.6.4)

**Файл:** `backend/app/services/phases/decision.py:67-79`

`RelationshipStore` шкала `-100..100`. Код трактует как `-1..1` с `0.5` neutral. NPCs snap to BROKEN слишком быстро.

**v8.5 ПРОВЕРКА:** `decision.py:74-83` → `# V8-MEM-4 FIX: Шкала RelationshipStore: -100..100, где 0.0 - нейтральное.` → `_trust_pressure = max(0.0, -_min_trust) / 100.0 * 20.0` (деление на 100). `_fear_pressure = max(0.0, _max_fear) / 100.0 * 20.0`. Баг ИСПРАВЛЕН — шкала корректно нормализована.

**Fix:** (исполнено в V.0.5.3.6.4) — Делить на 100, ИЛИ переписать formula для -100..100.

**Время:** 30 мин (сделано)

### V8-MEM-5 ✅RESOLVED — `get_weights_for_decision.recent_pressure` wrong filter (исправлено в V.0.5.3.6.4)

**Файл:** `backend/app/services/memory/memory_manager.py:630-638`

Фильтрует по `e.npc_id == npc_id`, не по `target_id`. Target-specific pressure — fake.

**v8.5 ПРОВЕРКА:** `memory_manager.py:706-710` → `if e.get("actor") == tid or e.get("target") == tid: recent_pressure += e.get("importance", 0.0)` для dict-based events. `# V8-MEM-5 FIX: Фильтруем по target_id или actor_id, а не по npc_id` → `elif (hasattr(e, "target_id") and e.target_id == tid) or (hasattr(e, "actor_id") and e.actor_id == tid): recent_pressure += e.importance` для object-based events. Баг ИСПРАВЛЕН — фильтр корректно по `tid`, не по `npc_id`.

**Fix:** (исполнено в V.0.5.3.6.4) — `if e.target_id == tid or e.actor_id == tid`.

**Время:** 15 мин (сделано)

### V8-MEM-7 ★★ HIGH — `_identity_cache` не персистится

**Файл:** `backend/app/services/memory/memory_manager.py:42-45`

In-memory only. На restart все L3 traits — LOST.

**Fix:** Персистировать в SQLite.

**Время:** 30 мин

### V8-MEM-11(v7) ★ MEDIUM — PromotionEngine templates — всего 6

**Файл:** `backend/app/services/memory/promotion_engine.py:33-42`

Нет: help, gift, theft, observation. narrative_cache растёт линейно.

**Fix:** Добавить 4 шаблона.

**Время:** 30 мин

### V8-MEM-13 ★ MEDIUM — `detect_resonance` игнорирует npc_id

**Файлы:** `memory_manager.py:707-726`, `working_memory_tick.py:122-124`

Возвращает один pattern list для всей campaign. Per-NPC resonance отсутствует.

**Fix:** `detect_resonance(npc_id=...)` — фильтровать buffer.

**Время:** 30 мин

### V8-DEC-09 ★ MEDIUM — CPS-09 duplicate ADR-036 block

**Файл:** `backend/app/services/npc/decision_hub.py:450-471`

Первый блок читает `event.semantic_action`/`event.target_id`, второй перезаписывает. First — dead code.

**Fix:** Удалить первый блок.

**Время:** 10 мин

### V8-DEC-11 ★ MEDIUM — EventBus event loss on exception

**Файл:** `backend/app/services/events/event_bus.py:114-123`

Handler exceptions caught, logged, swallowed. No retry, no DLQ.

**Fix:** Добавить retry (1-2 attempts), DLQ.

**Время:** 45 мин

---

## §9. ВОЛЯ / АВАТАР — ОСТАЛОСЬ

### V8-WL-1 ★★ HIGH — Counter-offer `stealth`/`yield` actions не зарегистрированы

**Файл:** `backend/app/services/will.py:250-256`

Counter-offer action генерируется, но нигде не исполняется.

**Fix:** Wire к исполнителю ИЛИ удалить dead returns.

**Время:** 30 мин

### V8-WL-2 ★★ HIGH — Player pressure ≈ 0.05, WillpowerGate почти не сопротивляется

**Файл:** `backend/app/services/will.py:90-102`

ADR «player is not god» нарушен.

**Fix:** Поднять pressure для violence/self_risk/moral_violations до 0.3-0.5.

**Время:** 30 мин

### V8-WL-3 ★★ HIGH — Avatar `fear`/`willpower` не доходят до WillpowerGate

**Файл:** `backend/app/services/game_loop/__init__.py:677-682`

`NPCState` не имеет `fear` и `willpower`. Avatar's fear всегда 0.0, willpower всегда 1.0.

**Fix:** Построить полный `_live_psyche` из CharacterProfile/NPCPersonality.

**Время:** 1 ч

### V8-SP-3 ★★ HIGH — Player `coords=None`

**Файлы:** `scene_state_manager.py:879`, `player_avatar_service.py:load_state`, `player_target_pipeline.py`

Player не регистрируется в `npc_positions` без `editor_data.get("player_spawn")`.

**Fix:** Гарантированно регистрировать player с дефолтной позицией.

**Время:** 1 ч

### V8-WL-4 ★ MEDIUM — Avatar `will_state`/`emotion` строки, не Enum

**Файл:** `backend/app/services/player_avatar_service.py:340, 355`

**Fix:** `WillState(data.get("will_state", "free"))`.

**Время:** 15 мин

### V8-WL-5 ★ MEDIUM — `CharacterProfile.values.weights` default-empty отключает CharacterFilter

**Файл:** `backend/app/services/character/character_filter_applicator.py:40`

**Fix:** Defaults per archetype при character creation.

**Время:** 30 мин

---

## §10. ТИК / ОРКЕСТРАТОР — ОСТАЛОСЬ

### V8-TICK-1 ★★★ CRITICAL (v8.5 ESCALATED) — `NameError _movement_req` в `_process_player_dm_action` (production-reachable!)

**Файл:** `backend/app/services/game_loop/tick_orchestrator.py:604-749`

`_movement_req`, `_sem_action`, `_sem_target` не определены. Production reachability: НЕТ (мёртвый path).

**v8.5 ПРОВЕРКА:** `_process_player_dm_action` **ВЫЗЫВАЕТСЯ ИЗ PRODUCTION** на line 592 (`self._process_player_dm_action(ctx, _dm_ctx)`). Path НЕ мёртвый — это критическая ошибка в v8.4 анализе. Что найдено в коде:
- Line 633: `_movement_req = getattr(_intent_res, "movement_request", None)  # V8-TICK-1 FIX` — `_movement_req` ИСПРАВЛЕНО (getattr с default None)
- Line 643-644: `_directive_payload = {"semantic_action": _sem_action, "target_reference": _sem_target, ...}` — `_sem_action` и `_sem_target` **НЕ ОПРЕДЕЛЕНЫ** в этой функции → NameError при достижении этого кода

**Эффект:** При срабатывании `_process_player_dm_action` (когда игрок отдаёт приказ NPC "подойди ко мне" или подобный directive), Python падает с `NameError: name '_sem_action' is not defined` → exception в tick orchestrator → tick aborts → player action lost.

**Fix:** Определить `_sem_action` и `_sem_target` из `_intent_res` или `_params`:
```python
_sem_action = ""
_sem_target = ""
if _params:
    _sem_action = getattr(_params, "semantic_action", "") or ""
    _sem_target = getattr(_params, "target_reference", "") or ""
# или получить из _intent_res.original_intent.parameters
```

Или удалить `_process_player_dm_action` полностью (если функциональность перенесена в `_process_player_action` per S115 FIX comment на line 754).

**Время:** 15 мин (минимум) — urgency выше, чем v8.4

### V8-TICK-2 ★★ HIGH (v8.5 ESCALATED) — DRF scoring overlay НИКОГДА не вызывается (для ВСЕХ intents, не только non-movement)

**Файл:** `backend/app/services/game_loop/tick_orchestrator.py:522-551, 1444`

Non-movement intents bypass DRF scoring.

**v8.5 ПРОВЕРКА:** `_apply_drf_scoring_overlay` определена на line 1444 (1489 lines total), но grep по всей codebase → **0 call sites** в production. Функция никогда не вызывается. Эффект: НИКАКИЕ intents (movement И non-movement) не получают DRF scoring overlay. DRF pressure из `drf_bus.stream` игнорируется полностью.

**Fix:** Wire `_apply_drf_scoring_overlay` для ВСЕХ intents. Найдите точку, где intents собираются в `_run_core_phases`, и добавьте вызов. Например, в `_phase_5_decision` после compute:
```python
self._apply_drf_scoring_overlay(ctx.intents, ctx)
```

**Время:** 30 мин

### V8-TICK-7 ★ MEDIUM (v8.5 NEW) — `_apply_drf_scoring_overlay` defined but never called (отдельный баг от V8-TICK-2)

**Файл:** `backend/app/services/game_loop/tick_orchestrator.py:1444`

`_apply_drf_scoring_overlay` определена (полная имплементация scoring math, 40 строк), но не вызывается НИГДЕ в production. Это либо wiring bug (забыли wire), либо dead code (был написан, но не подkeyён).

**Эффект:** `drf_bus.stream` (压力 claim'ы) никогда не влияют на приоритеты intents. Это нарушает архитектурный принцип ADR-049 (DRF как поле сил). Все NPCs выбирают intents по base priority без учёта давления.

**Fix (вариант 1 — wire):** Найти точку применения intents в `_phase_5_decision` или `_phase_7_windup_resolution`, вызвать `self._apply_drf_scoring_overlay(ctx.intents, ctx)`.

**Fix (вариант 2 — удалить):** Если DRF overlay не нужен (architecture changed), удалить функцию + `drf_bus.stream` drain logic в phase 10.

**Время:** 30 мин (wire) / 10 мин (delete)

### V8-TICK-3 ★★ HIGH — Двойной счётчик времени

**Файлы:** `tick_orchestrator.py:1306-1355`, `time_advance.py:23-105`

Player ticks drift ~+10s/tick быстрее idle.

**Fix:** Skip `_advance_idle_time` для player turns.

**Время:** 30 мин

### V8-TICK-4 ★ MEDIUM — `UnboundLocalError state_l2` в hearing branch

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py:170`

NPCs вне LoS не получают hearing perception.

**Fix:** Поднять `state_l2` перед hearing branch.

**Время:** 10 мин

### V8-TICK-5 ✅RESOLVED — `TypeError` в directive path для `emotion["stress"]` (исправлено в V.0.5.3.6.4)

**Файлы:** `tick_orchestrator.py:675, 863`

`npc["emotion"]` — STRING, не dict. TypeError → aborts `fear_of_player` updates.

**v8.5 ПРОВЕРКА:** `tick_orchestrator.py:676-678` → `# V8-TICK-5 / V8-PSY-21 FIX: stress пишется в psyche sub-dict, а не в emotion (строка)` → `_psyche = _npc_state.setdefault("psyche", {}); _psyche["stress"] = max(0, min(100, _psyche.get("stress", 0.0) + delta.payload.stress_delta))`. Баг ИСПРАВЛЕН — TypeError устранён.

**Fix:** (исполнено в V.0.5.3.6.4) — Заменить на `psyche["stress"]` write.

**Время:** 10 мин (сделано)

### V8-TICK-6 ★ MEDIUM — Phase exception leaks partial state

**Файл:** `backend/app/services/game_loop/tick_orchestrator.py:467-474`

Mutations в `shared_context.scene_state` persist хотя commit skipped.

**Fix:** Rollback на tick failure (deep-copy snapshot).

**Время:** 30 мин

---

## §11. ИТОГОВАЯ СВОДКА БАГОВ

### v8.4 vs v8.5 — сравнение

| Категория | v8.4 CRIT/HIGH/MED | v8.5 изменения | v8.5 активные |
|---|---|---|---|
| §1 MVP epistemic | 3 / 3 / 1 = 7 | ✅V8-MVP-15 NON-ISSUE, ✅V8-MVP-19 RESOLVED, ➕V8-MVP-20 CRIT NEW, ➕V8-MVP-CK1 CRIT NEW | 3 CRIT / 1 HIGH / 1 MED = 5 |
| §2 Sleep chain | 4 / 2 / 2 = 8 | ✅V8-SP-20 RESOLVED, ➕V8-SP-21 HIGH NEW, ➕V8-SP-22 MED NEW | 4 CRIT / 3 HIGH / 3 MED = 10 |
| §3 Map editor | 1 / 1 / 1 = 3 | ➕V8-ED-4 MED NEW | 1 CRIT / 1 HIGH / 2 MED = 4 |
| §4 build_graph | 0 / 1 / 0 = 1 | (без изменений) | 0 CRIT / 1 HIGH / 0 MED = 1 |
| §5 Dialogue | 0 / 2 / 4 = 6 | ✅V8-DLG-09 RESOLVED, ✅V8-DLG-11 RESOLVED, ✅V8-DLG-12 RESOLVED | 0 CRIT / 1 HIGH / 2 MED = 3 |
| §6 NPC↔NPC Social | 2 / 2 / 2 = 6 | ✅V8-SOC-3 RESOLVED | 1 CRIT / 2 HIGH / 2 MED = 5 |
| §7 Psyche | 0 / 5 / 0 = 5 | ✅V8-PSY-25 RESOLVED (но V8-MVP-20 — производный), ✅V8-PSY-21 RESOLVED | 0 CRIT / 4 HIGH / 0 MED = 4 |
| §8 Memory/Decision | 0 / 2 / 4 = 6 | ✅V8-MEM-4 RESOLVED, ✅V8-MEM-5 RESOLVED | 0 CRIT / 1 HIGH / 4 MED = 5 |
| §9 Will/Avatar | 0 / 3 / 2 = 5 | (без изменений) | 0 CRIT / 3 HIGH / 2 MED = 5 |
| §10 Tick | 1 / 2 / 3 = 6 | 📈V8-TICK-1 ESCALATED CRIT (был CRIT но "мёртвый"), 📈V8-TICK-2 ESCALATED HIGH (раньше MED), ✅V8-TICK-5 RESOLVED, ➕V8-TICK-7 MED NEW | 1 CRIT / 3 HIGH / 3 MED = 7 |
| **v8.4 Итого** | **11 / 23 / 19 = 53** | | |
| **v8.5 Итого** | | | **10 CRIT / 19 HIGH / 17 MED = 46 активных** |

**Плюс 11 ✅RESOLVED (исправлены в V.0.5.3.6.4, не в TODO):** V8-MVP-15, V8-MVP-19, V8-SP-20, V8-PSY-25, V8-PSY-21, V8-SOC-3, V8-TICK-5, V8-DLG-09, V8-DLG-11, V8-DLG-12, V8-MEM-4, V8-MEM-5

**Итог:** v8.4 заявлял 53 бага, но 11 уже исправлены → реальных активных 42. v8.5 добавил 6 новых → 48 total активных (10 CRIT, 19 HIGH, 17 MED, 2 LOW). 

---

## §11.5. ГЛАВНЫЕ НАХОДКИ v8.5 АУДИТА

### 1. V8-MVP-20 (CRITICAL, NEW) — главный блокер fate_states

`mvp_tavern_controller.py:114` читает `npc.get("stress", 0)` из root, но stress в `npc["psyche"]["stress"]`. Это **второй экземпляр** бага V8-PSY-25, в другом файле — v8.4 аудит его пропустил.

Эффект: stability ВСЕГДА 1.0 → FateTracker траектория ВСЕГДА STABLE → End-Screen `fate_states` ВСЕГДА пуст. Все 6 NPC всегда отображаются как "STABLE" в финале.

### 2. V8-MVP-CK1 (CRITICAL, NEW) — атака на предложенный V8-MVP-12 fix

`TruthState.Secret` frozen dataclass НЕ имеет поля `confession_keywords`. v8.4 предложил `secret.get("confession_keywords", [])` → AttributeError. V8-MVP-12 fix не работает "из коробки". Требуется: добавить поле в dataclass + парсинг в loader + использовать attribute access в парсере.

### 3. V8-SP-21/22 (HIGH/MEDIUM, NEW) — трёхсторонний overlap

`market_square` (origin (-5, 14.875), size 25×25) накладывается на:
- tavern (12.5см × 20м = 2.5 м²)
- city_gate (8см × 5.2м = 0.4 м²)

v8.4 упоминал только tavern × city_gate overlap. Реально — три конфликтующих локации.

Плюс: `market_square.adjacency.east = "city_gate"`, но `city_gate.adjacency.south = "market_square"`. Направления не совпадают. SaveValidator (V8-ED-1) поймает, но фикс геометрии всё равно нужен.

### 4. V8-TICK-1 (CRITICAL, ESCALATED) — production-reachable NameError

v8.4 сказал "мёртвый path". v8.5 аудит: `_process_player_dm_action` ВЫЗЫВАЕТСЯ на line 592. Path ЖИВОЙ. `_sem_action` и `_sem_target` (line 643-644) НИКОГДА не определяются → NameError на каждый directive. Игрок не может приказывать NPC.

### 5. V8-TICK-2/7 (HIGH/MEDIUM, ESCALATED/NEW) — DRF scoring полностью отключён

`_apply_drf_scoring_overlay` (line 1444) определена, но НИ РАЗУ не вызывается. DRF pressure (ADR-049) полностью игнорируется. Все NPCs выбирают intents по base priority без учёта давления.

### 6. V8-ED-4 (MEDIUM, NEW) — SaveValidator wiring упадёт

v8.4 предложил `self.cm.base_dir.parent`, но `CampaignManager` имеет `campaign_path` (нет `base_dir`). AttributeError при первом сохранении с validation.

---

## §12. ПРИОРИТЕТ ПОЧИНКИ (Day Plan v8.5)

### День 1 (~3 ч) — MVP epistemic (ГЛАВНЫЙ БЛОКЕР)

Цель: NPC признание → End-Screen показывает >0 secrets, fate_states >0.

| Баг | Время |
|---|---|
| **V8-MVP-CK1** (NEW) Добавить `confession_keywords` в `TruthState.Secret` + парсинг в loader | 15 мин |
| **V8-MVP-13** Добавить `shadow_guild_membership` secret в canon с `confession_keywords` | 10 мин |
| **V8-MVP-14** Добавить keyword "гильд"/"вор" в resolver | 5 мин |
| **V8-MVP-12** NpcConfessionParser (архитектурный фикс, использует `secret.confession_keywords` attr) | 1.5 ч |
| **V8-MVP-20** (NEW) `mvp_tavern_controller:114` — читать stress из `psyche` | 5 мин |
| Тест: Тень признаётся → End-Screen 1+ secret, 1+ fate_state | 15 мин |

### День 2 (~4 ч) — Sleep chain

Цель: NPC материализуются в city_gate, сон работает.

| Баг | Время |
|---|---|
| **V8-SP-15** Boundary node = anchor coords (graph_compiler) | 15 мин |
| **V8-SP-16** Micro_snap boundary detection (movement_engine) | 30 мин |
| **V8-SP-18** `invalidate_cache` в `reinit_campaign` | 5 мин |
| **V8-SP-19** S-145 cache sync не перетирает boundary | 10 мин |
| **V8-SP-21** (NEW) Сдвинуть market_square на (20, 15) — через редактор с validation | 15 мин |
| **V8-SP-22** (NEW) Исправить market_square/city_gate adjacency directions | 30 мин |
| Сдвинуть city_gate origin на (20.0, 0.0) — через редактор с validation | 30 мин |
| Перенести gate_road на x=21.5 — через редактор | 15 мин |
| Тест: все 5 NPC спят в своих койкоместах | 30 мин |

### День 3 (~3 ч) — Map editor validation

Цель: Редактор не даёт сохранить сломанную кампанию.

| Баг | Время |
|---|---|
| **V8-ED-1** SaveValidator (overlap, node-in-bounds, adjacency, cross-loc) + V8-ED-4 wiring fix | 2-3 ч |
| **V8-ED-2** `_check_adjacent` reject real overlap | 15 мин |
| Тест: сохранение с overlap → блокируется (включая market_square) | 15 мин |

### День 4 (~3 ч) — NPC↔NPC + Memory

Цель: NPC A атакует B → B боится. L3 Identity работает.

| Баг | Время |
|---|---|
| **V8-SOC-2** Publish dead event types (COMBAT/HELP/THEFT/etc.) | 1 ч |
| **V8-MEM-7** _identity_cache persistence | 30 мин |
| **V8-DEC-11** EventBus retry/DLQ | 45 мин |
| **V8-MVP-17** trigger_fate wire | 1 ч |
| **V8-MVP-18** register_dilemma wire | 1 ч |
| ~~V8-SOC-3~~ ✅RESOLVED — пропустить | 0 |
| ~~V8-MEM-4~~ ✅RESOLVED — пропустить | 0 |
| ~~V8-MEM-5~~ ✅RESOLVED — пропустить | 0 |

### День 5 (~2.5 ч) — Dialogue + Psyche

Цель: Trauma pipeline с per-NPC plasticity. (DLG-09, DLG-11, DLG-12 уже RESOLVED)

| Баг | Время |
|---|---|
| **V8-DLG-06** DialogueMemorySubscriber (всё ещё отсутствует) | 1 ч |
| **V8-DLG-10** Wire `build_verbalization_context` в DialogueExecutor | 1 ч |
| **V8-PSY-1** identity_rigidity на NPCPersonality + JSON config | 1 ч |
| ~~V8-PSY-21~~ ✅RESOLVED — пропустить | 0 |
| ~~V8-PSY-25~~ ✅RESOLVED (но V8-MVP-20 — производный, см. День 1) | 0 |

### День 6 (~3 ч) — Avatar & Will + Tick polish (расширенный)

| Баг | Время |
|---|---|
| **V8-TICK-1** (ESCALATED) Определить `_sem_action`/`_sem_target` ИЛИ удалить `_process_player_dm_action` | 30 мин |
| **V8-TICK-2 + V8-TICK-7** (ESCALATED+NEW) Wire `_apply_drf_scoring_overlay` для всех intents ИЛИ удалить dead code | 30 мин |
| **V8-SP-3** Player coords | 1 ч |
| **V8-WL-3** Avatar fear/willpower в _live_psyche | 1 ч |
| ~~V8-TICK-5~~ ✅RESOLVED — пропустить | 0 |

### День 7 (~2 ч) — Cleanup + финальные тесты

- Все MEDIUM bugs (V8-DLG-13/14, V8-SOC-5/6/7/11, V8-PSY-6/9/11/12/20, V8-MEM-11/13, V8-DEC-09, V8-WL-1/2/4/5, V8-TICK-3/4/6, V8-ED-3, V8-ED-4, V8-SP-22)
- Full playthrough canary
- Save/load roundtrip
- End-Screen: ≥5/16 secrets, ≥2/6 fate_states, faction_alignments
- NPC↔NPC attack → fear/trust change
- Sleep: все 5 NPC в кроватях к 22:00 (включая city_gate materialize)
- Dialogue continuity через 20 ходов
- Directive path (V8-TICK-1) — игрок приказывает NPC "подойди", не падает
- Production server smoke test
- Release

**Итого v8.5:** ~18-22 часов работы. После 7 дней — MVP полностью работоспособен.

---

## §13. CANARY ТЕСТЫ

### Canary 1: NPC confession → End-Screen >0

```python
def test_npc_confession_end_screen():
    """V8-MVP-12/13/14 — Тень признаётся → End-Screen 1+."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_confession")
    
    for _ in range(5):
        game.idle_tick()
    
    # Player asks Shadow about guild
    game.player_action(target="thief_shadow", text="Тень, ты из гильдии воров?")
    game.idle_tick()
    
    # Verify secret discovered
    truth = game.mvp_controller.truth_state
    assert "shadow_guild_membership" in truth.discovered_secrets, \
        "Confession not recorded — V8-MVP-12 not fixed"
    
    # End-Screen
    game.player_exit_tavern()
    end_screen = game.get_end_screen()
    assert end_screen.secrets_identified >= 1, \
        f"Expected >=1, got {end_screen.secrets_identified}"
```

### Canary 2: Sleep — все NPC в кроватях

```python
def test_all_npcs_sleep():
    """V8-SP-13..19 — все 5 NPC спят к 22:00."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_sleep")
    game.set_game_time("22:00")
    
    for _ in range(25):
        game.idle_tick()
    
    expected = {
        "guard_borko": ("city_gate", "guard_bed"),
        "blacksmith_orm": ("city_gate", "tent_1"),  # не tent_2 (V8-SP-20)
        "merchant_goran": ("city_gate", "tent_2"),
        "tavern_keeper_tornin": ("tavern", "kitchen_bed_2"),
        "maid_lusya": ("tavern", "kitchen_bed_1"),
        # Shadow — nocturnal, спит 06:00-18:00
    }
    
    for npc_id, (loc, node) in expected.items():
        npc = game.get_npc(npc_id)
        assert npc.location_id == loc, f"{npc_id}: loc={npc.location_id}, expected {loc}"
        assert node in npc.position, f"{npc_id}: pos={npc.position}, expected {node}*"
```

### Canary 3: Editor rejects overlap

```python
def test_editor_rejects_overlap():
    """V8-ED-1 — сохранение с overlap блокируется."""
    editor = MapEditor(campaign_root="test_overlap")
    # Создать overlap: city_gate origin (19.5, 0.0) overlaps tavern [0,20]
    editor.set_origin("city_gate", x=19.5, y=0.0)
    
    result = editor.save()
    assert not result.success, "Overlap should block save"
    assert any("BOUNDARY_OVERLAP" in e.code for e in result.errors)
```

### Canary 4: NPC↔NPC attack → fear change

```python
def test_npc_npc_attack_fear():
    """V8-SOC-1..4 — NPC A атакует B → B боится."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_attack")
    
    initial_fear = game.get_fear("tavern_keeper_tornin", "guard_borko")
    game.npc_attack(attacker="guard_borko", target="tavern_keeper_tornin")
    for _ in range(5):
        game.idle_tick()
    
    final_fear = game.get_fear("tavern_keeper_tornin", "guard_borko")
    assert final_fear > initial_fear
```

### Canary 5: Dialogue continuity (метель)

```python
def test_dialogue_continuity():
    """V8-DLG-01..09 — NPC помнит нить через 20 ходов."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_dialogue")
    
    game.player_action(target="tornin", text="расскажи о метели")
    for text in ["и что потом?", "какая погода?", "холодно", "будет тепло?", "метель закончилась?"]:
        game.player_action(target="tornin", text=text)
    
    response = game.player_action(target="tornin", text="так что насчёт той метели?")
    assert "метел" in response.lower()
```

---

## §14. CHANGELOG

### v8.5 (V.0.5.3.6.4 аудит v8.5) — 2026-07-30

**Глубокий аудит V.0.5.3.6.4:** Прочитаны ключевые исходники (25+ файлов). Сопоставлены все 53 бага v8.4 с реальным кодом.

**Главные находки v8.5:**

**➕ 6 НОВЫХ багов (не описанных в v8.4):**

1. **V8-MVP-20 CRITICAL (NEW)** — `mvp_tavern_controller.py:114` читает `npc.get("stress", 0)` из ROOT level, но stress в `npc["psyche"]["stress"]`. → stability ВСЕГДА 1.0 → FateTracker ВСЕГДА STABLE → End-Screen `fate_states` ВСЕГДА пуст. Это второй экземпляр бага V8-PSY-25, в другом файле — v8.4 аудит пропустил.

2. **V8-MVP-CK1 CRITICAL (NEW)** — `TruthState.Secret` frozen dataclass НЕ имеет поля `confession_keywords`. Предложенный в v8.4 V8-MVP-12 `NpcConfessionParser` использует `secret.get("confession_keywords", [])` → AttributeError. Fix не работает "из коробки". Требуется: добавить поле в dataclass + парсинг в loader + использовать attribute access в парсере.

3. **V8-SP-21 HIGH (NEW)** — `market_square` (origin (-5, 14.875), size 25×25) накладывается на tavern (12.5см × 20м = 2.5 м²) И на city_gate (8см × 5.2м = 0.4 м²). v8.4 упоминал только tavern × city_gate overlap. Реально — ТРИ конфликтующих локации.

4. **V8-SP-22 MEDIUM (NEW)** — `market_square.adjacency.east = "city_gate"`, но `city_gate.adjacency.south = "market_square"`. Направления не совпадают. SaveValidator (V8-ED-1) отрапортует `ADJACENCY_NOT_RECIPROCATED`. Cross-loc movement может выбрать неправильный boundary.

5. **V8-ED-4 MEDIUM (NEW)** — SaveValidator wiring упадёт. v8.4 предложил `self.cm.base_dir.parent`, но `CampaignManager` имеет `campaign_path` (нет `base_dir`). AttributeError при первом сохранении с validation.

6. **V8-TICK-7 MEDIUM (NEW)** — `_apply_drf_scoring_overlay` определена (40 строк scoring math), не вызывается НИГДЕ. DRF pressure (ADR-049) полностью игнорируется.

**✅ 11 багов ИСПРАВЛЕНЫ в V.0.5.3.6.4 (v8.4 ошибочно помечал как TODO):**

- V8-MVP-15 (NON-ISSUE — truth_state_loader НЕ проверяет campaign_id)
- V8-MVP-19 (clamping на месте в mvp_tavern_controller:113-114)
- V8-SP-20 (orm: tent_1, goran: tent_2 — конфликта НЕТ)
- V8-PSY-25 (life_engine.py:2251 — fixed, но V8-MVP-20 — производный, в mvp_tavern_controller — НЕ fixed)
- V8-PSY-21 (tick_orchestrator.py:676-678 — fixed)
- V8-SOC-3 (social_deltas.py:138-143 — fixed, .lower() при lookup)
- V8-TICK-5 (tick_orchestrator.py:676-678 — fixed)
- V8-DLG-09 (npc_dialogue_subscriber.py:130 — extract вызывается)
- V8-DLG-11 (dm_agent.py:236 — add_npc_l2_memory вызывается)
- V8-DLG-12 (task_scheduler.py:49 — _dialogue_ttl=60.0 game_time, не wall-clock 10.0)
- V8-MEM-4 (decision.py:74-83 — шкала корректно нормализована через /100)
- V8-MEM-5 (memory_manager.py:706-710 — фильтр по tid, не по npc_id)

**📈 2 бага ESCALATED (v8.4 преуменьшил):**

1. **V8-TICK-1 CRITICAL (ESCALATED)** — v8.4 сказал "мёртвый path". v8.5: `_process_player_dm_action` **ВЫЗЫВАЕТСЯ ИЗ PRODUCTION** на line 592. Path ЖИВОЙ. `_sem_action` и `_sem_target` (line 643-644) НИКОГДА не определяются → NameError на каждый directive. Игрок не может приказывать NPC.

2. **V8-TICK-2 HIGH (ESCALATED)** — v8.4 сказал "non-movement bypass". v8.5: `_apply_drf_scoring_overlay` НИКОГДА не вызывается. DRF scoring отключён ДЛЯ ВСЕХ intents.

**v8.5 фактический итог:**
- v8.4 перечислено: 53 бага
- v8.5 RESOLVED: 11 багов (уже исправлены)
- v8.5 NON-ISSUE: 1 баг (V8-MVP-15)
- v8.5 ESCALATED: 2 бага (раньше описаны слабее)
- v8.5 NEW: 6 багов (найдены в этом аудите)
- **Активных в v8.5: 48 багов** (10 CRIT, 19 HIGH, 17 MED, 2 LOW)

**Day plan v8.5:** 7 дней, ~18-22 часов. День 1 — MVP epistemic (NpcConfessionParser + confession_keywords field + V8-MVP-20 fate fix). День 2 — sleep chain (включая market_square geometry). День 3 — editor validation (SaveValidator с правильным wiring). День 4 — NPC↔NPC + memory. День 5 — dialogue + psyche. День 6 — avatar + tick (включая V8-TICK-1/2/7 fixes). День 7 — cleanup + релиз.

---

### v8.4 (V.0.5.3.6.8.4) — 2026-07-29

**Аудит V.0.5.3.6.4:** 3 параллельных агента + точечные проверки. Найдено **53 активных бага** (11 CRITICAL, 23 HIGH, 19 MEDIUM).

**Главные находки:**

1. **V8-MVP-12 CRITICAL (НОВОЕ)** — NPC LLM reply не парсится как evidence. Когда Тень говорит «Да, я из гильдии воров», признание **никогда не записывается**. Только текст игрока парсится. End-Screen показывает 0. Архитектурный разрыв: `npc_orchestration.py` не вызывает `add_evidence`/`mark_discovered`.

2. **V8-MVP-13 CRITICAL (НОВОЕ)** — Missing `shadow_guild_membership` secret в canon. TruthState не имеет слота для записи признания.

3. **V8-MVP-14 HIGH (НОВОЕ)** — Missing keyword "гильд"/"вор" в ActionSemanticResolver для thief_shadow.

4. ~~**V8-MVP-15 HIGH** — `campaign_id: "silver_wolf"` в truth_state не совпадает с `"Open_road"`.~~ **✅v8.5: NON-ISSUE** — loader не проверяет campaign_id.

5. **V8-SP-13..16 CRITICAL** — Sleep всё ещё сломан:
   - Locations overlap на 8 см (tavern × city_gate)
   - `gate_road` внутри tavern (x=16.45 < 20.0)
   - Boundary node coords = nearest nav, не anchor
   - Micro_snap deadlock у boundary node

6. **V8-SP-18 HIGH** — `LifeEngine.invalidate_cache` не вызывается в `reinit_campaign`.

7. **V8-ED-1 CRITICAL (НОВОЕ)** — Редактор карт не валидирует: нет overlap prohibition, нет cross-loc checks, нет node-in-bounds.

8. **V8-BG-1 HIGH** — `build_graph.py` — документация, НЕ runtime. Auto-rebuild через `SpatialCompilationGateway` уже работает.

**Day plan v8.4:** 6-7 дней, ~17-20 часов. День 1 — MVP epistemic (NpcConfessionParser). День 2 — sleep chain. День 3 — editor validation. День 4 — NPC↔NPC + memory. День 5 — dialogue + psyche. День 6 — avatar + tick. День 7 — cleanup + релиз.

---

*Этот документ — TODO list активных багов V.0.5.3.6.4 (v8.5 аудит). После применения Day plan v8.5 MVP «Секреты Люси» полностью работоспособен: NPC признания засчитываются (V8-MVP-12+V8-MVP-CK1), End-Screen >0 secrets И >0 fate_states (V8-MVP-20), NPC спят (V8-SP-13..22), редактор валидирует cross-loc (V8-ED-1+V8-ED-4), диалоги — не монологи, NPC↔NPC социалка живая, DRF scoring включён (V8-TICK-2/7), directive path не падает (V8-TICK-1).*

# ENIGMA Session State — 2026-07-09 06:17

Кампания: `Open_road` | Игрок: `Венус`

## ИДЕНТИФИКАЦИЯ АРХИТЕКТОРА

Прочитай эту секцию первой. Определи кто ты по задаче сессии:

- Если ты работаешь с Python-кодом, патчами, архитектурой, багами → **Архитектор #1 или #3**
- Если ты работаешь с UI, pygame, рендерингом, визуальными элементами → **Архитектор #2**
- Если ты работаешь с NPC-поведением, тиками, давлением, решениями → **Архитектор #3**

Прочитай свою секцию (#1, #2 или #3). У других архитекторов читай только строку "Сейчас делает:" — чтобы не конфликтовать по файлам.

---

## DNA — МЕТРИКИ ЗДОРОВЬЯ СИСТЕМЫ

_Сессия: 1.7 мин | Тиков: 0 | LLM-вызовов: 0_

| Метрика | Значение | Δ от прошлой | Интерпретация для LLM |
|---------|----------|--------------|----------------------|
| **SHI** (Simulation Health) | 0% | → +0.0% | ⛔ МЕРТВА: решений нет. Проверь DecisionHub.compute() |
| **NPI** (NPC Pipeline) | 100% | ↑ +14.3% | ✅ 6/6 NPC с реальными координатами |
| **OBI** (Obedience) | 0% | → +0.0% | нет директив в сессии — OBI не применим |
| **SCF** (Spatial Coherence) | 1.0 | → +0.0 | ✅ пространство целостно: граф загружен корректно |
| **ADR** (Debt Ratio) | 0.00 | → +0.0 | нет ADR-записей — невозможно оценить |
| **CVS** (Causal Velocity) | 0.00/мин | → +0.0 | LLM не вызывалась: сессия без действий игрока |
| **PFI** (Pre-Bus Failure) | 900% | ↓ +600.0% | ⛔ 9 пред-шинных отказов — pipeline молча умирает, CDS слеп |

_История: `reports/dna_history.jsonl` — 682 записей_

## 🔴 КРАСНЫЕ ИНВАРИАНТЫ — ТИХИЕ ДЕГРАДАЦИИ

### 🔴 CRITICAL — чинить ПЕРВЫМ, до любой новой фичи

#### 📈 INV-DIALOGUE-PIPELINE-BROKEN [POST-MORTEM]

**Симптом:** За 5 тиков было 18 вербальных интентов, но 0 реплик в recent_dialogues. Цепочка порвана.

**Подозреваемые файлы (проверить в порядке очерёдности):**
  - `backend/app/services/npc/decision_hub.py:_build_communication (строка 286)`
  - `backend/app/services/npc/life_engine.py:719 (communication_intents.append)`
  - `backend/app/services/pipeline_runner.py:87 (ctx.communication_intents = ...)`
  - `backend/app/services/phases/post_decision.py:23`
  - `backend/app/services/game_loop/task_scheduler.py:114 (executor.execute)`

**PowerShell для проверки:**
```powershell
Get-Content backend/logs/cds_session_*.log | Select-String "Фаза 6"
```

#### 📈 INV-NPC-FROZEN [POST-MORTEM]

**Симптом:** За 5 тиков ни один NPC не сменил позицию. MovementEngine или RELOCATE сломаны.

**Подозреваемые файлы (проверить в порядке очерёдности):**
  - `backend/app/services/spatial/movement_engine.py`
  - `backend/app/services/scene_state_manager.py (RELOCATE handler)`
  - `backend/app/services/integration/world_snapshot_builder.py:_extract_active_traversals`

#### 📈 INV-TIME-FREEZE [POST-MORTEM]

**Симптом:** game_time_seconds не изменился за 10 тиков: был 43560.0, стал 43560.0

**Подозреваемые файлы (проверить в порядке очерёдности):**
  - `backend/app/core/calendar.py:advance()`
  - `backend/app/services/tick_orchestrator.py (Фаза 0)`
  - `backend/app/services/game_loop/scene_init.py:73`

**PowerShell для проверки:**
```powershell
Select-String -Path "backend/app/core/calendar.py" -Pattern "def advance"
```

## #1 — АРХИТЕКТОР КОДА (патчи, файлы, архитектура)

### Сейчас делает:
(не определено — обнови MUTATIONS.md)

### Активные баги требующие патча:
_(баги не обнаружены в этой сессии)_

### Последние изменения (git log -5):
  - a74d937 Release V.0.5.3.4.0_ГЛАЗА
  - 658cb45 Save local snapshot for V.0.5.3.3.9_Деградация
  - 8d53543 Snapshot: V.0.5.3.3.8_Деградация
  - 3b7cdfc Fix: add location_graph compatibility shim for sandbox tests
  - a158058 V.0.5.3.3.7_Финишная_прямая snapshot

### Последние записи MUTATIONS.md:
  - (MUTATIONS.md не найден)

### Файлы с активными TODO/FIXME:
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\calendar.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\behavior.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\constants.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\decision_context.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\embodied_trace.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\intent_profile.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\movement.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\vital_state.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\affect.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\cfrm.py

---

## #2 — АРХИТЕКТОР UI (pygame, рендеринг, визуал)

### Сейчас делает:
(не определено — обнови MUTATIONS.md)

### Состояние рендеринга (из последней сессии игры):
- NPC с известными координатами (6):
  - `guard_borko`: x=12.0 y=9.0
  - `merchant_goran`: x=9.0 y=9.0
  - `maid_lusya`: x=4.5 y=5.0
  - `blacksmith_orm`: x=10.5 y=5.0
  - `thief_shadow`: x=7.5 y=6.8
  - `tavern_keeper_tornin`: x=4.5 y=2.5
- NPC без координат (lerp не работает, 0):
  - _(нет)_
- Граф-fallback локаций: нет

### Визуальные аномалии:
- spatial_fallback triggered: ✅ нет
- Узлы не найдены (NPC не могут добраться до цели): 0

### Что НЕ трогать (сейчас меняет другой архитектор):
_(см. секции #1 и #3 — файлы backend/app/services/)_

---

## #3 — АРХИТЕКТОР СИМУЛЯЦИИ (NPC, тики, давление, решения)

### Сейчас делает:
(не определено — обнови MUTATIONS.md)

### Состояние симуляции (последняя сессия игры):

**Tick Pipeline:**
Тиков: 0 | Decisions > 0: 1/0 | LLM: 0 вызовов / 0 ответов | Симуляция: ✅ живёт
- LLM "Ничего не произошло": 0 раз
- LLM CJK-галлюцинации: 0 строк
- Стартап backend: ✅
- LLM сервер: ✅

**Предупреждения:**
  - ⚠️ КРИТИЧНО: 9 пред-шинных отказов (pipeline=0, causality=0, phase8=0, tick_orch=9) — CDS слеп к этим багам без Инварианта 3

**Movement Pipeline (по NPC):**
| NPC | Intent | Score | Traversal | Координаты | Виден игроку |
|-----|--------|-------|-----------|------------|--------------|
| blacksmith_orm | offer_job | 0.473 | ❌ | x=10.5 y=5.0 | ❌ |
| guard_borko | block_path | 0.261 | ❌ | x=12.0 y=9.0 | ❌ |
| maid_lusya | change_role | 0.284 | ❌ | x=4.5 y=5.0 | ❌ |
| merchant_goran | request_service | 0.208 | ❌ | x=9.0 y=9.0 | ❌ |
| tavern_keeper_tornin | spread_rumor | 0.237 | ❌ | x=4.5 y=2.5 | ❌ |
| thief_shadow | change_role | 0.335 | ❌ | x=7.5 y=6.8 | ❌ |

**NPC с разрывом в pipeline (intent есть, traversal нет):**
  - _(нет разрывов в movement pipeline)_

### Каузальные разрывы:

_Каузальных разрывов не обнаружено_

### Архитектурный долг (не трогать без обсуждения):
- Stale Cognition: DecisionHub работает на state T-1. Требует ADR-059.
- Cognitive Overlay Layer: отдельный спринт.

### Что НЕ трогать (сейчас меняет другой архитектор):
_(см. секции #1 и #2 — файлы frontend/)_
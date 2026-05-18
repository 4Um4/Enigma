# ENIGMA Session State — 2026-05-18 21:14

Кампания: `?` | Игрок: `?`

## ИДЕНТИФИКАЦИЯ АРХИТЕКТОРА

Прочитай эту секцию первой. Определи кто ты по задаче сессии:

- Если ты работаешь с Python-кодом, патчами, архитектурой, багами → **Архитектор #1 или #3**
- Если ты работаешь с UI, pygame, рендерингом, визуальными элементами → **Архитектор #2**
- Если ты работаешь с NPC-поведением, тиками, давлением, решениями → **Архитектор #3**

Прочитай свою секцию (#1, #2 или #3). У других архитекторов читай только строку "Сейчас делает:" — чтобы не конфликтовать по файлам.

---

## #1 — АРХИТЕКТОР КОДА (патчи, файлы, архитектура)

### Сейчас делает:
- **Очистка корня:** `diagnose_spatial.py` перемещен в `backend/tests/sandbox/`. Артефакты `decision_hub_sandbox.py` перенаправлены в директорию песочницы. **[Инфраструктура]**

### Активные баги требующие патча:
_(баги не обнаружены в этой сессии)_

### Последние изменения (git log -5):
  - 49f7dc4 docs: update README future vector for V.0.5.3.0.8_ПЕСОЧНИЦЫ_5
  - 2f5db48 V.0.5.3.0.8_ПЕСОЧНИЦЫ_5
  - 59195d5 cleanup: remove root trash files moved to ignored directories
  - 9e96f52 cleanup: moved root trash to ignored directories and added sandbox diagnostic file
  - 1f8d826 Update README, evolution docs, and comparison report for V.0.5.3.0.7_ПЕСОЧНИЦЫ_8

### Последние записи MUTATIONS.md:
  - - **`backend/app/services/game_loop/npc_orchestration.py`:** Добавлен проброс `initiative_suppression` из буфера в `NPCPositionDTO` для фронтендного рендера. **[Пайплайн]**`scene_state["npc_positions"]`. **[Пайплайн]**
  - - **`backend/app/services/integration/world_snapshot_builder.py`:** Добавлена сборка `initiative_suppression` в `NPCPositionDTO`. **[Пайплайн]**
  - - **Очистка корня:** `diagnose_spatial.py` перемещен в `backend/tests/sandbox/`. Артефакты `decision_hub_sandbox.py` перенаправлены в директорию песочницы. **[Инфраструктура]**

### Файлы с активными TODO/FIXME:
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\calendar.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\constants.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\decision_context.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\intent_profile.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\affect.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\cfrm.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\delta_payloads.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\front.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\idle_tick.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\impact.py

---

## #2 — АРХИТЕКТОР UI (pygame, рендеринг, визуал)

### Сейчас делает:
- **Очистка корня:** `diagnose_spatial.py` перемещен в `backend/tests/sandbox/`. Артефакты `decision_hub_sandbox.py` перенаправлены в директорию песочницы. **[Инфраструктура]**

### Состояние рендеринга (из последней сессии игры):
- NPC с известными координатами (0):
  - _(нет данных о координатах — SNAPSHOT-паттерн не сработал)_
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
- **Очистка корня:** `diagnose_spatial.py` перемещен в `backend/tests/sandbox/`. Артефакты `decision_hub_sandbox.py` перенаправлены в директорию песочницы. **[Инфраструктура]**

### Состояние симуляции (последняя сессия игры):

**Tick Pipeline:**
Тиков: 0 | Decisions > 0: 0/0 | LLM: 0 вызовов / 0 ответов | Симуляция: ❌ МЕРТВА
- LLM "Ничего не произошло": 0 раз
- LLM CJK-галлюцинации: 0 строк
- Стартап backend: ❌
- LLM сервер: ❌ (не доступен при старте)

**Предупреждения:**
  - ⚠️ КРИТИЧНО: все тики вернули 0 decisions — симуляция заморожена

**Movement Pipeline (по NPC):**
_Нет данных по NPC_

**NPC с разрывом в pipeline (intent есть, traversal нет):**
  - _(нет разрывов в movement pipeline)_

### Каузальные разрывы:

#### [BREAK-1] Симуляция заморожена
**Симптом:** все тики вернули 0 decisions
**Файл для проверки:** `backend/app/services/npc/decision_hub.py`
**PowerShell:** `Select-String -Path "backend/app/services/npc/decision_hub.py" -Pattern "def compute"`

### Архитектурный долг (не трогать без обсуждения):
- Stale Cognition: DecisionHub работает на state T-1. Требует ADR-059.
- Cognitive Overlay Layer: отдельный спринт.

### Что НЕ трогать (сейчас меняет другой архитектор):
_(см. секции #1 и #2 — файлы frontend/)_
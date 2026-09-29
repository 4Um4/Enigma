# ENIGMA Session State — 2026-09-30 02:42

Кампания: `?` | Игрок: `?`

## ИДЕНТИФИКАЦИЯ АРХИТЕКТОРА

Прочитай эту секцию первой. Определи кто ты по задаче сессии:

- Если ты работаешь с Python-кодом, патчами, архитектурой, багами → **Архитектор #1 или #3**
- Если ты работаешь с UI, pygame, рендерингом, визуальными элементами → **Архитектор #2**
- Если ты работаешь с NPC-поведением, тиками, давлением, решениями → **Архитектор #3**

Прочитай свою секцию (#1, #2 или #3). У других архитекторов читай только строку "Сейчас делает:" — чтобы не конфликтовать по файлам.

---

## DNA — МЕТРИКИ ЗДОРОВЬЯ СИСТЕМЫ

_Сессия: 0.4 мин | Тиков: 2 | LLM-вызовов: 2_

| Метрика | Значение | Δ от прошлой | Интерпретация для LLM |
|---------|----------|--------------|----------------------|
| **SHI** (Simulation Health) | 100% | → +0.0% | ✅ норма: NPC активно принимают решения |
| **NPI** (NPC Pipeline) | 100% | → +0.0% | ✅ 6/6 NPC с реальными координатами |
| **OBI** (Obedience) | 0% | → +0.0% | нет директив в сессии — OBI не применим |
| **SCF** (Spatial Coherence) | 1.0 | → +0.0 | ✅ пространство целостно: граф загружен корректно |
| **ADR** (Debt Ratio) | 0.00 | → +0.0 | нет ADR-записей — невозможно оценить |
| **CVS** (Causal Velocity) | 5.51/мин | ↓ -2.3 | ✅ 5.51/мин: активная сессия |
| **PFI** (Pre-Bus Failure) | 0% | → +0.0% | ✅ норма: пред-шинных отказов нет — CDS видит всё |
| **Tracebacks** | 0 (AttrErr=0, TypeErr=0) | → | ✅ норма |
| **BCI** (Belief Crystallization) | 22 (idx=11.00) | → | ✅ Убеждения формируются |
| **BPI** (Break Progress) | 13 (broken=0) | → | ✅ Давление доходит |
| **NEI** (Need Urgency) | 0 (critical=0) | → | ⚠️ NPC слишком комфортны (NEI=0) |
| **DRI** (Response Integrity) | 100% | → +0.0% | ✅ LLM отвечает на все запросы |
| **DPI** (Dialogue Pipeline) | 100% | → +0.0% | ✅ Конвейер диалогов стабилен |

_История: `reports/dna_history.jsonl` — 1279 записей_

## 🟢 КРАСНЫЕ ИНВАРИАНТЫ — ТИХИЕ ДЕГРАДАЦИИ

_Не обнаружено — игра жива._

**Источники проверки:**
- Runtime: `SimulationIntegrityError` в pipeline (не сработал)
- Post-mortem: `InvariantHealthChecker` в CausalObserver (не нашёл)
- Слой ДО: `python backend/tests/IPT.py` (запускается LLM до коммита)

## #1 — АРХИТЕКТОР КОДА (патчи, файлы, архитектура)

### Сейчас делает:
(не определено — обнови MUTATIONS.md)

### Активные баги требующие патча:
_(баги не обнаружены в этой сессии)_

### Последние изменения (git log -5):
  - 0aa6611c chore: untrack replay.db (60MB рантайм-БД реплея) + combat_log
  - 045a4b65 chore: untrack dna_history.jsonl (runtime CDS-история; LAST_SESSION.md — канон истории сессий)
  - af8aa4b6 chore: хвост гигиены — ignore session_memory, диск-очистка одноразовых дампов
  - b9b4af6a chore: gitignore — dna_history.jsonl (пропущенная строка из a5fab11e)
  - 33c51773 chore: cds-ротатор (дополнение a5fab11e, упомянутый в его message)

### Последние записи MUTATIONS.md:
  - (MUTATIONS.md не найден)

### Файлы с активными TODO/FIXME:
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\constants.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\constants.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\decision_context.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\intent_profile.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\vital_state.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\affect.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\cfrm.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\locomotion.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\npc_state.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\phase8.py

---

## #2 — АРХИТЕКТОР UI (pygame, рендеринг, визуал)

### Сейчас делает:
(не определено — обнови MUTATIONS.md)

### Состояние рендеринга (из последней сессии игры):
- NPC с известными координатами (6):
  - `guard_borko`: x=16.7 y=3.8
  - `merchant_goran`: x=8.3 y=5.8
  - `maid_lusya`: x=9.8 y=2.2
  - `blacksmith_orm`: x=9.2 y=4.5
  - `thief_shadow`: x=11.5 y=11.0
  - `tavern_keeper_tornin`: x=6.0 y=2.6
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
Тиков: 2 | Decisions > 0: 1/2 | LLM: 2 вызовов / 2 ответов | Симуляция: ✅ живёт
- LLM "Ничего не произошло": 0 раз
- LLM CJK-галлюцинации: 0 строк
- Стартап backend: ✅
- LLM сервер: ✅

**Предупреждения:**
  - _(нет)_

**Movement Pipeline (по NPC):**
| NPC | Intent | Score | Traversal | Координаты | Виден игроку |
|-----|--------|-------|-----------|------------|--------------|
| blacksmith_orm | request_service | 0.747 | ✅ | x=9.2 y=4.5 | ❌ |
| guard_borko | block_path | 0.330 | ✅ | x=16.7 y=3.8 | ❌ |
| maid_lusya | flee | 0.511 | ✅ | x=9.8 y=2.2 | ❌ |
| merchant_goran | offer_job | 0.558 | ✅ | x=8.3 y=5.8 | ❌ |
| tavern_keeper_tornin | call_for_help | 0.333 | ✅ | x=6.0 y=2.6 | ❌ |
| thief_shadow | observe | 0.185 | ✅ | x=11.5 y=11.0 | ❌ |

**NPC с разрывом в pipeline (intent есть, traversal нет):**
  - _(нет разрывов в movement pipeline)_

### Каузальные разрывы:

_Каузальных разрывов не обнаружено_

### Архитектурный долг (не трогать без обсуждения):
- Stale Cognition: DecisionHub работает на state T-1. Требует ADR-059.
- Cognitive Overlay Layer: отдельный спринт.

### Что НЕ трогать (сейчас меняет другой архитектор):
_(см. секции #1 и #2 — файлы frontend/)_
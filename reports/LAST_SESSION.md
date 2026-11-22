# ENIGMA Session State — 2026-11-22 15:46

Кампания: `Open_road` | Игрок: `Dav12`

## ИДЕНТИФИКАЦИЯ АРХИТЕКТОРА

Прочитай эту секцию первой. Определи кто ты по задаче сессии:

- Если ты работаешь с Python-кодом, патчами, архитектурой, багами → **Архитектор #1 или #3**
- Если ты работаешь с UI, pygame, рендерингом, визуальными элементами → **Архитектор #2**
- Если ты работаешь с NPC-поведением, тиками, давлением, решениями → **Архитектор #3**

Прочитай свою секцию (#1, #2 или #3). У других архитекторов читай только строку "Сейчас делает:" — чтобы не конфликтовать по файлам.

---

## DNA — МЕТРИКИ ЗДОРОВЬЯ СИСТЕМЫ

_Сессия: 2.3 мин | Тиков: 116 | LLM-вызовов: 12_

| Метрика | Значение | Δ от прошлой | Интерпретация для LLM |
|---------|----------|--------------|----------------------|
| **SHI** (Simulation Health) | 100% | → +0.0% | ✅ норма: NPC активно принимают решения |
| **NPI** (NPC Pipeline) | 86% | → +0.0% | ⚠️ 6/7 NPC с координатами: есть потери в traversal |
| **OBI** (Obedience) | 0% | → +0.0% | нет директив в сессии — OBI не применим |
| **SCF** (Spatial Coherence) | 1.0 | → +0.0 | ✅ пространство целостно: граф загружен корректно |
| **ADR** (Debt Ratio) | 0.00 | → +0.0 | нет ADR-записей — невозможно оценить |
| **CVS** (Causal Velocity) | 5.25/мин | ↑ +1.9 | ✅ 5.25/мин: активная сессия |
| **PFI** (Pre-Bus Failure) | 0% | → +0.0% | ✅ норма: пред-шинных отказов нет — CDS видит всё |
| **Tracebacks** | 1 (AttrErr=0, TypeErr=0) | → | ⚠️ КРИТИЧНО: невидимые регрессии (Tracebacks) |
| **BCI** (Belief Crystallization) | 837 (idx=7.22) | → | ✅ Убеждения формируются |
| **BPI** (Break Progress) | 809 (broken=0) | → | ✅ Давление доходит |
| **NEI** (Need Urgency) | 0 (critical=0) | → | ⚠️ NPC слишком комфортны (NEI=0) |
| **DRI** (Response Integrity) | 100% | → +0.0% | ✅ LLM отвечает на все запросы |
| **DPI** (Dialogue Pipeline) | 100% | → +0.0% | ✅ Конвейер диалогов стабилен |

_История: `reports/dna_history.jsonl` — 1404 записей_

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
  - b41560b7 chore: релиз V.0.5.4.7.1 Говори!
  - 2a16529a fix(re-cache): синхронизация allowlist и пина с фактическим состоянием кода
  - 3ccf1509 test(s365): verify parser safely ignores bare numbers without age markers
  - 78a77eae test(s365): fix cot_leak_blocked indentation and update to new ambiguous age warning format
  - 14e991f0 test(cch8): fix seed report control test to validate actual payload vs registry

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
  - `merchant_goran`: x=74.6 y=9.4
  - `maid_lusya`: x=35.1 y=9.2
  - `blacksmith_orm`: x=74.6 y=9.4
  - `thief_shadow`: x=78.8 y=9.5
  - `tavern_keeper_tornin`: x=42.4 y=9.5
  - `guard_borko`: x=78.8 y=9.5
- NPC без координат (lerp не работает, 1):
  - `player` (intent=?)
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
Тиков: 116 | Decisions > 0: 5/116 | LLM: 12 вызовов / 16 ответов | Симуляция: ✅ живёт
- LLM "Ничего не произошло": 0 раз
- LLM CJK-галлюцинации: 0 строк
- Стартап backend: ✅
- LLM сервер: ❌ (не доступен при старте)

**Предупреждения:**
  - _(нет)_

**Movement Pipeline (по NPC):**
| NPC | Intent | Score | Traversal | Координаты | Виден игроку |
|-----|--------|-------|-----------|------------|--------------|
| blacksmith_orm | talk | 1.210 | ✅ | x=74.6 y=9.4 | ❌ |
| guard_borko | talk | 1.351 | ✅ | x=78.8 y=9.5 | ❌ |
| maid_lusya | flee | 0.790 | ✅ | x=35.1 y=9.2 | ❌ |
| merchant_goran | talk | 1.123 | ✅ | x=74.6 y=9.4 | ❌ |
| player | ? | 0.000 | ✅ | None | ❌ |
| tavern_keeper_tornin | flee | 0.432 | ✅ | x=42.4 y=9.5 | ❌ |
| thief_shadow | trade | 0.523 | ✅ | x=78.8 y=9.5 | ❌ |

**NPC с разрывом в pipeline (intent есть, traversal нет):**
  - _(нет разрывов в movement pipeline)_

### Каузальные разрывы:

_Каузальных разрывов не обнаружено_

### Архитектурный долг (не трогать без обсуждения):
- Stale Cognition: DecisionHub работает на state T-1. Требует ADR-059.
- Cognitive Overlay Layer: отдельный спринт.

### Что НЕ трогать (сейчас меняет другой архитектор):
_(см. секции #1 и #2 — файлы frontend/)_
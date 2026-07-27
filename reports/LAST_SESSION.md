# ENIGMA Session State — 2026-07-27 22:42

Кампания: `Open_road` | Игрок: `фыап`

## ИДЕНТИФИКАЦИЯ АРХИТЕКТОРА

Прочитай эту секцию первой. Определи кто ты по задаче сессии:

- Если ты работаешь с Python-кодом, патчами, архитектурой, багами → **Архитектор #1 или #3**
- Если ты работаешь с UI, pygame, рендерингом, визуальными элементами → **Архитектор #2**
- Если ты работаешь с NPC-поведением, тиками, давлением, решениями → **Архитектор #3**

Прочитай свою секцию (#1, #2 или #3). У других архитекторов читай только строку "Сейчас делает:" — чтобы не конфликтовать по файлам.

---

## DNA — МЕТРИКИ ЗДОРОВЬЯ СИСТЕМЫ

_Сессия: 1.1 мин | Тиков: 0 | LLM-вызовов: 12_

| Метрика | Значение | Δ от прошлой | Интерпретация для LLM |
|---------|----------|--------------|----------------------|
| **SHI** (Simulation Health) | 0% | → +0.0% | ⛔ МЕРТВА: решений нет. Проверь DecisionHub.compute() |
| **NPI** (NPC Pipeline) | 100% | ↑ +100.0% | ✅ 6/6 NPC с реальными координатами |
| **OBI** (Obedience) | 0% | → +0.0% | нет директив в сессии — OBI не применим |
| **SCF** (Spatial Coherence) | 1.0 | → +0.0 | ✅ пространство целостно: граф загружен корректно |
| **ADR** (Debt Ratio) | 0.00 | → +0.0 | нет ADR-записей — невозможно оценить |
| **CVS** (Causal Velocity) | 10.73/мин | ↑ +10.7 | ✅ 10.73/мин: активная сессия |
| **PFI** (Pre-Bus Failure) | 0% | → +0.0% | ✅ норма: пред-шинных отказов нет — CDS видит всё |

**Системные сигналы (требуют внимания):**
- SHI=0% при активных LLM-вызовах: игрок взаимодействует но NPC не решают — разрыв между R3_DIRECT и DecisionHub

_История: `reports/dna_history.jsonl` — 863 записей_

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
  - c66a8b8 V.0.5.3.6.0 — подготовка к созданию ветки V.0.5.3.6.1
  - 8657b35 V.0.5.3.6.0 — полный снапшот проекта Enigma
  - e0566a8 Save point before creating branch V.0.5.3.5.9
  - 45f2052 V.0.5.3.5.8 — финальные логи и доработки
  - d4612f6 V.0.5.3.5.8_Ви́ам_супэрва́дэт_ва́дэнс — полный снапшот проекта Enigma

### Последние записи MUTATIONS.md:
  - (MUTATIONS.md не найден)

### Файлы с активными TODO/FIXME:
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\calendar.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\constants.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\constants.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\decision_context.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\intent_profile.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\vital_state.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\affect.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\cfrm.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\locomotion.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\phase8.py

---

## #2 — АРХИТЕКТОР UI (pygame, рендеринг, визуал)

### Сейчас делает:
(не определено — обнови MUTATIONS.md)

### Состояние рендеринга (из последней сессии игры):
- NPC с известными координатами (6):
  - `guard_borko`: x=10.9 y=7.0
  - `merchant_goran`: x=3.9 y=6.0
  - `maid_lusya`: x=10.5 y=4.9
  - `blacksmith_orm`: x=6.3 y=5.3
  - `thief_shadow`: x=6.0 y=5.3
  - `tavern_keeper_tornin`: x=8.4 y=4.2
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
Тиков: 0 | Decisions > 0: 1/0 | LLM: 12 вызовов / 12 ответов | Симуляция: ✅ живёт
- LLM "Ничего не произошло": 0 раз
- LLM CJK-галлюцинации: 0 строк
- Стартап backend: ✅
- LLM сервер: ✅

**Предупреждения:**
  - _(нет)_

**Movement Pipeline (по NPC):**
| NPC | Intent | Score | Traversal | Координаты | Виден игроку |
|-----|--------|-------|-----------|------------|--------------|
| blacksmith_orm | request_service | 0.780 | ❌ | x=6.3 y=5.3 | ❌ |
| guard_borko | observe | 0.216 | ❌ | x=10.9 y=7.0 | ❌ |
| maid_lusya | observe | 0.266 | ❌ | x=10.5 y=4.9 | ❌ |
| merchant_goran | observe | 0.239 | ❌ | x=3.9 y=6.0 | ❌ |
| tavern_keeper_tornin | observe | 0.256 | ❌ | x=8.4 y=4.2 | ❌ |
| thief_shadow | request_service | 0.161 | ❌ | x=6.0 y=5.3 | ❌ |

**NPC с разрывом в pipeline (intent есть, traversal нет):**
  - _(нет разрывов в movement pipeline)_

### Каузальные разрывы:

_Каузальных разрывов не обнаружено_

### Архитектурный долг (не трогать без обсуждения):
- Stale Cognition: DecisionHub работает на state T-1. Требует ADR-059.
- Cognitive Overlay Layer: отдельный спринт.

### Что НЕ трогать (сейчас меняет другой архитектор):
_(см. секции #1 и #2 — файлы frontend/)_
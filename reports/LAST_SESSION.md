# ENIGMA Session State — 2026-08-30 23:24

Кампания: `?` | Игрок: `?`

## ИДЕНТИФИКАЦИЯ АРХИТЕКТОРА

Прочитай эту секцию первой. Определи кто ты по задаче сессии:

- Если ты работаешь с Python-кодом, патчами, архитектурой, багами → **Архитектор #1 или #3**
- Если ты работаешь с UI, pygame, рендерингом, визуальными элементами → **Архитектор #2**
- Если ты работаешь с NPC-поведением, тиками, давлением, решениями → **Архитектор #3**

Прочитай свою секцию (#1, #2 или #3). У других архитекторов читай только строку "Сейчас делает:" — чтобы не конфликтовать по файлам.

---

## DNA — МЕТРИКИ ЗДОРОВЬЯ СИСТЕМЫ

_Сессия: 3.1 мин | Тиков: 13 | LLM-вызовов: 36_

| Метрика | Значение | Δ от прошлой | Интерпретация для LLM |
|---------|----------|--------------|----------------------|
| **SHI** (Simulation Health) | 100% | → +0.0% | ✅ норма: NPC активно принимают решения |
| **NPI** (NPC Pipeline) | 86% | → +0.0% | ⚠️ 6/7 NPC с координатами: есть потери в traversal |
| **OBI** (Obedience) | 0% | → +0.0% | нет директив в сессии — OBI не применим |
| **SCF** (Spatial Coherence) | 1.0 | → +0.0 | ✅ пространство целостно: граф загружен корректно |
| **ADR** (Debt Ratio) | 0.00 | → +0.0 | нет ADR-записей — невозможно оценить |
| **CVS** (Causal Velocity) | 11.58/мин | ↓ -15.3 | ✅ 11.58/мин: активная сессия |
| **PFI** (Pre-Bus Failure) | 0% | → +0.0% | ✅ норма: пред-шинных отказов нет — CDS видит всё |
| **Tracebacks** | 1 (AttrErr=1, TypeErr=0) | → | ⚠️ КРИТИЧНО: невидимые регрессии (Tracebacks) |
| **BCI** (Belief Crystallization) | 22 (idx=1.69) | → | ✅ Убеждения формируются |
| **BPI** (Break Progress) | 94 (broken=0) | → | ✅ Давление доходит |
| **NEI** (Need Urgency) | 0 (critical=0) | → | ⚠️ NPC слишком комфортны (NEI=0) |
| **DRI** (Response Integrity) | 100% | ↑ +97.6% | ✅ LLM отвечает на все запросы |
| **DPI** (Dialogue Pipeline) | 100% | → +0.0% | ✅ Конвейер диалогов стабилен |

_История: `reports/dna_history.jsonl` — 1113 записей_

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
  - 600d89e0 M1b.4.1 ADR-O-371: V2RelationshipBackend — тупой адаптер над scene_state.directed (legacy-интерфейс; headroom+clamp+Vacuum+round(4) дословно; без _cache/файлов/новых семантик; provider-лямбда сцены) + контрактная сетка D3 legacy==v2 (8x8x5) 186 тестов; ленивая навигация create=True; L4-чист; попутно mypy-дефект M1a: дубль _KEY_SUBSTITUTABILITY → _KEY_HC_SUBSTITUTABILITY
  - 2afdb89d S232 W2 Affordances ADR-O-372: pure resolver (WorldObject, BodyStateView, npc_position) -> Tuple[SemanticAction, ...]; substrate-only, 0 runtime-потребителей; IPT 45/45, W2 24/24, W1 30/30
  - 5d879987 M1b.2.7 ADR-O-371: ARCHITECTURAL PROOF — вечные греп-инварианты: (1) ноль прямых writer'ов 5 скаляров вне RelationshipWriteGate (D2-инвариант, разовый аудит увековечен тестом); (2) attraction-хирургия кэша запрещена (§8.6). Лестница M1b.2 замкнута: 2.0 гейт+D3-сетка 8x8x5 → 2.1-2.5 пять механических миграций (соц-подписчик/компилятор/фасад/Applicator/decay-доказательство) → 2.6 semantic gate §8.6 → 2.7 proof
  - 5c2db815 M1b.2.6 ADR-O-371 (semantic gate, вердикт Мастера): комплимент — ОДНА направленная запись player→target через гейт (§8.6 'зеркальный комплимент заменяется направленной семантикой'); зеркальная target→player и кэш-хирургия attraction/trust УДАЛЕНЫ (обход SSOT закрыт); тест-контракт ожидаемого изменения (не паритет): player→target растут / target→player Vacuum / кэш не тронут подписчиком
  - 5ae7792f M1b.2.5 ADR-O-371: decay-маршрут ЗАМКНУТ доказательством (археология: SocialDecayHandler=produce Δ → delta_buffer → apply_batch → update_relationships → Gate M1b.2.4; ноль изменений поведения) + интеграционный тест цепочки с канонической headroom-формулой (урок: ассерты по формуле стора, не линейный хардкод)

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
  - `guard_borko`: x=11.0 y=10.0
  - `merchant_goran`: x=5.5 y=6.0
  - `maid_lusya`: x=10.5 y=3.0
  - `blacksmith_orm`: x=5.5 y=6.0
  - `thief_shadow`: x=8.1 y=13.0
  - `tavern_keeper_tornin`: x=10.5 y=6.5
- NPC без координат (lerp не работает, 1):
  - `player` (intent=seek_ally)
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
Тиков: 13 | Decisions > 0: 4/13 | LLM: 36 вызовов / 34 ответов | Симуляция: ✅ живёт
- LLM "Ничего не произошло": 0 раз
- LLM CJK-галлюцинации: 0 строк
- Стартап backend: ✅
- LLM сервер: ✅

**Предупреждения:**
  - _(нет)_

**Movement Pipeline (по NPC):**
| NPC | Intent | Score | Traversal | Координаты | Виден игроку |
|-----|--------|-------|-----------|------------|--------------|
| blacksmith_orm | idle | 0.000 | ✅ | x=5.5 y=6.0 | ❌ |
| guard_borko | block_path | 0.485 | ✅ | x=11.0 y=10.0 | ❌ |
| maid_lusya | flee | 0.575 | ✅ | x=10.5 y=3.0 | ❌ |
| merchant_goran | offer_job | 0.746 | ✅ | x=5.5 y=6.0 | ❌ |
| player | seek_ally | 0.312 | ✅ | None | ❌ |
| tavern_keeper_tornin | call_for_help | 0.352 | ✅ | x=10.5 y=6.5 | ❌ |
| thief_shadow | warn | 0.360 | ✅ | x=8.1 y=13.0 | ❌ |

**NPC с разрывом в pipeline (intent есть, traversal нет):**
  - _(нет разрывов в movement pipeline)_

### Каузальные разрывы:

_Каузальных разрывов не обнаружено_

### Архитектурный долг (не трогать без обсуждения):
- Stale Cognition: DecisionHub работает на state T-1. Требует ADR-059.
- Cognitive Overlay Layer: отдельный спринт.

### Что НЕ трогать (сейчас меняет другой архитектор):
_(см. секции #1 и #2 — файлы frontend/)_
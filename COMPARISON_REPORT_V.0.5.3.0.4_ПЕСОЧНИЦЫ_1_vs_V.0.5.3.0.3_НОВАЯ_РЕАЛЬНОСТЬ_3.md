# Сравнение отчёта: V.0.5.3.0.2_НОВАЯ_РЕАЛЬНОСТЬ_2 vs V.0.5.3.0.3_НОВАЯ_РЕАЛЬНОСТЬ_3

Дата среза: 12 мая 2026

## 0. Git-статистика (сколько реально сделано)

> Метод: diff по дереву Git между теговыми/веточными точками.

- **Файлов изменено:** 135
- **Вставок:** ~ (полные numstat/line-diff лучше снять отдельно)
- **Удалений:** ~
- **Новые файлы:** 41
- **Переименования/перемещения:** 4

Ключ: отчёт ниже оценивает не «строки», а **объём внедрённых игровых систем** и **ценность изменений**, опираясь на:
- структуру MUTATIONS.md (как дневник/лог усилий),
- перечень новых/включённых subsystems, которые появились в diff.

## 1. Сводка: что важного и ценного появилось в V.0.5.3.0.3

### 1.1. Новый слой WillpowerGate / Cumulative Strain (ADR-031 + pipeline)
**Ценность:** появился механизм, который связывает действие игрока/воли с сопротивлением психики, а не только с «решением/намерением».

Что именно:
- `backend/app/models/will.py` (контракты воли: IntentPressureProfile, WillState, WillResponseDTO)
- `backend/app/services/will.py` (compute/resolution логика)
- адаптация в рантайм-слоях: boundary adapter в Phase 1
- API-цепочка и сохранение данных через PipelineContext/доменные DTO.

**Итог для геймплея:** у DM/игрового симулятора появляется *предсказуемая* ось «намерение → давление → сопротивление → состояние воли», что делает историю устойчивее к импульсивным вводам игрока.

### 1.2. Intent Compression Layer (LLM-friendly sematic input) + тесты
**Ценность:** игроковый ввод перестал быть «сырым текстом» и превратился в структурированное доменное намерение (с зоной, силой/эмоциями/социальным давлением), что резко улучшает стабильность и воспроизводимость.

Что именно:
- `backend/app/domain/intent_profile.py`
- `backend/app/services/input/intent_compressor.py`
- `backend/app/services/input/llm_compressor_client.py` (JSON mode + DI под llama.cpp)
- `backend/tests/test_intent_compressor.py`.

**Итог:** меньше «понимания на глаз»; повышенная детерминированность входного пути для дальнейших фаз.

### 1.3. Affective Resonance System Integration (ADR-036)
**Ценность:** добавлен ещё один «психофизиологический» слой интерпретации реакции: FEAR/AGGRESSION/FREEZE/... bias → resonance profile.

Что именно:
- `backend/app/models/affect.py`
- `backend/app/services/affect.py` (двухслойный процесс)
- интеграция в `NPCState` (affective_imprints) и в фазовые обработки.

### 1.4. Local Causal Solver (CFRM Layer 1 closure): Projection → Attenuation → Local Reduction
**Ценность:** causal pipeline закрывается *локальной* редукцией, а не только глобальной буферизацией событий.

Что именно:
- `backend/app/services/cfrm/local_causal_solver.py`
- расширение `backend/app/models/cfrm.py` (classification/bridge)
- `backend/app/services/tick_orchestrator.py`: use classification result и rebuild occupancy.

**Итог:** система получает реальную «каузальную опору» на события, а не приближение.

### 1.5. Encapsulated/разруленные Presentation + AvatarStateDTO (ADR-035)
**Ценность:** добавлена полноценная связка физио/ментальной картины игрока в WorldSnapshot для визуализации.

Что именно:
- `backend/app/domain/snapshot.py`: AvatarStateDTO + когнитивно-перцептивные параметры
- `backend/app/services/presentation/avatar_presentation_assembler.py`
- `backend/app/services/integration/world_snapshot_builder.py`
- `frontend/scene_renderer.py`, `frontend/game_screen.py`.

### 1.6. Frontend/transport: Will conflict data + manifestation/perception overlays
**Ценность:** конфликт воли не теряется между слоями — дошёл до UI и визуальных эффектов (mental_state).

Что именно:
- `frontend/presentation_firewall.py`
- `frontend/perceptual_momentum.py`
- `frontend/text_input.py` сопротивление вводу.

### 1.7. Sandbox/infra для доказательства новых систем
**Ценность:** появились runtime/sandbox артефакты, чтобы эти подсистемы можно было запускать и проверять.

Что именно:
- `backend/tests/sandbox/...` (новая инфраструктура)
- new probes/utility probes.

## 2. «Сколько новых функций за день» — не строки кода, а сколько *действий/механик* было сделано

По MUTATIONS.md (как дневник) между ветками произошло внедрение сразу нескольких независимых механик:

1) WillpowerGate / Cumulative Strain (ADR-031/034 + pipeline)
2) Intent Compression Layer (ADR-035)
3) Affective Resonance (ADR-036)
4) Local Causal Solver closure (CFRM layer 1 completion)
5) Avatar perception/materialization pipeline (ADR-035)
6) Conflict data plumbing + UI manifestation (frontend)
7) Sandbox verticals + causal probes

**Итого «значимых функций/механик»: 7 крупных внедрений**.

Почему это число «за день»: потому что diff по дереву показывает **кластерную** (подсистемную) работу: новые файлы/контракты/связывание в фазах/тесты. Это не «растекание по мелочам», а пакетный выпуск подсистем.

## 3. Список новых/переиспользованных ключевых модулей (с ориентирами из diff)

### Backend
- `backend/app/domain/*`: intent / intent_profile / snapshot (AvatarStateDTO)
- `backend/app/models/*`: will / locomotion / traversal / affect + расширения cfrm
- `backend/app/services/input/*`: intent_compressor + llama.cpp client
- `backend/app/services/will.py`, `backend/app/services/affect.py`
- `backend/app/services/cfrm/local_causal_solver.py`
- `backend/app/services/presentation/*`: avatar_presentation_assembler
- `backend/app/services/integration/world_snapshot_builder.py`

### Frontend
- `frontend/text_input.py`: сопротивление вводу + infect/exorcise
- `frontend/scene_renderer.py`: mental_state overlay
- `frontend/perceptual_momentum.py`: плавная интерференция/инерция
- `frontend/presentation_firewall.py`: sanitization boundary

### Tests/Sandbox
- `backend/tests/test_intent_compressor.py`
- `backend/tests/test_will.py`
- `backend/tests/sandbox/...` (vertical causal probes).

## 4. Что именно было «важно» — в терминах игры

1) **Стабилизация входа**: ввод игрока становится контролируемым доменным намерением.
2) **Стабилизация внутренней психофизиологии**: воля/давление/сопротивление + аффект.
3) **Стабилизация causal-логики**: local causal reduction делает результат управляемым.
4) **Стабилизация визуального следа**: UI показывает последствия воли/ментального состояния.

## 5. Сравнение с форматом старого отчёта (V.0.5.1.9)

Старый отчёт строился по схеме:
- «Сводка» → «что было добавлено» по архитектурным узлам → «почему важно».

Этот новый отчёт следует той же логике, но для версии `0.5.3.0.x` делает акцент на **Will/Intent/Fuzzy cognition**, потому что именно они выделяются как пакетная поставка подсистем.

---

## 6. Приложение: подтверждение источников ценности

- Основной источник «что было сделано как система за дни» — `docs/Tasks/MUTATIONS.md`.
- Точки diff/внедрённые файлы — git diff между ветками.

*/ конец отчёта */


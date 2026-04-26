# ENIGMA: The Final File Tree (Production-Grade Architecture)

Это итоговая структура проекта, исправленная с учетом критических уязвимостей. Главное правило: **LLM — это рендерер, а не симуляционный движок. LLM не имеет права добавлять новую информацию или генерировать события.**

## 📂 `backend/app/`

### 📁 `core/` (Ядро и Оркестрация)
*Здесь бьется сердце игры. Управляет мутациями состояния и временем.*
- `tick_orchestrator.py` — Жесткий 10-фазный цикл.
- `event_bus.py` — Центральная шина событий.
- `world_state.py` — Глобальное состояние мира (SceneState).
- `temporal_engine.py` — **[NEW]** Временной контекст (recency_weight, decay, persistence). События устаревают.
- `state_delta.py` — **[UPDATED]** Структурированные дельты (`SpatialDelta`, `HealthDelta`, `SocialDelta`, `EconomyDelta`), чтобы избежать скрытых мутаций.
- `state_applicator.py` — Единственный модуль, имеющий право изменять `WorldState` на основе `StateDelta`.

### 📁 `domain/` (Игровая логика и Правила)
*Чистый Python. Возвращают ТОЛЬКО `StateDelta`, ничего не меняют сами.*
- **`combat/`**
  - `dice_engine.py` — Градиентная боевка (ResultScore).
  - `trauma_engine.py` — Нелинейный расчет шока, боли и кровотечения.
  - `damage_model.py` — 6 зон тела, параметр `CONTROL` и `Function Loss`.
- **`social/`**
  - `reputation_store.py` — Хранение отношений и фракций.
  - `permission_matrix.py` — Матрица дозволенного (action_allowed).
- **`economy/`**
  - `production_engine.py` — Производство ресурсов NPC.
  - `distribution.py` — Локальные пулы ресурсов и расчет Local Scarcity.
  - `shadow_market.py` — Теневая экономика.
  - `trade_scene.py` — Разрешение торговли как сцены.
- **`needs/`**
  - `gradient_pressure.py` — Градиентное давление потребностей.
  - `economic_trauma.py` — Влияние долгого дефицита на психику.
- **`spatial/`**
  - `movement_engine.py` — Исполнение перемещений (Action Execution).
  - `location_graph.py` — Топология мира.

### 📁 `npc/` (Мозг персонажей)
*Принятие решений. Работает только с нормализованными сигналами.*
- `perception_filter.py` — Что NPC видит (искажается памятью).
- `interpretation_engine.py` — **[NEW]** Слой интерпретации. Переводит факт ("игрок подошел") в смысл ("угроза" или "флирт").
- `psyche_engine.py` — Взвешенный срыв (`break_score`).
- `decision_hub.py` — Чистый Scorer. Получает `Soft Bias` из памяти (страх/доверие) и смыслы из интерпретатора.

### 📁 `infrastructure/` (Внешние системы)
*Генерация текста, мета-нарратив, сеть, базы данных.*
- **`llm/`**
  - `narrative_compressor.py` — Перевод `State + StateDelta` в художественные инструкции.
  - `llm_shield.py` — Трехступенчатая валидация.
  - `verbalizer.py` — Генерация реплик. **Возвращает текст в API/DTO, а не в EventBus!**
- **`narrative/`**
  - `emergent_generator.py` — **[MOVED]** Генерация "Тайн" и квестов на основе `Pressure`. Перенесено из Домена, так как это мета-интерпретация значимости событий.
- **`memory/`**
  - `memory_shaper.py` — Расчет `importance` (учитывает `temporal_engine`).
  - `vector_store.py` — RAG и эмбеддинги.
- **`api/`**
  - `router.py` — FastAPI эндпоинты.
  - `dto.py` — `WorldSnapshotDTO` для фронтенда.

---

## 📂 `frontend/`
*Глупый рендерер. Только отображает то, что прислал бэкенд.*
- `ui/` — Компоненты интерфейса.
- `map/` — Отрисовка графа локаций.
- `chat/` — Окно диалогов (Tab-mode).

---

## 📂 `data/`
*Статика и сохранения.*
- `campaigns/` — Сохранения игроков.
- `prompts/` — Шаблоны для LLM.
- `world_def/` — JSON/YAML файлы с описанием локаций, предметов и базовых NPC.
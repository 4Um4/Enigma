
## Стоп. Архитектурный аудит предложений.

  ---

  ### Что реально происходит сейчас

  Прежде чем трогать что-либо — нужно честно оценить состояние.

  **Что только что заработало (этот сеанс):**
  - R1 Working Memory — подключена, пишется, попадает в промпт
  - R2.1 NarrativeExtractor — работает, поднос зарегистрирован
  - scene_events — пишутся в SceneState

  **Что ещё не подтверждено тестом:**
  - Торнин помнит конкретные цифры? Не проверено после фиксов
  - scene_events_block попадает в DM промпт? Не проверено
  - Люся роняет поднос дважды — исчезло? Не проверено

  **Вывод:** Мы не завершили R1-Connect и R2. Предлагается начать R3.5 (Goal/Intent architecture) + социальные роли. Это прыжок через две фазы.

  ---

  ### Разбор каждого предложения

  **1. "Перенести S.0 наверх в python_engines.py — фатальная архитектурная ошибка"**

  За: логически верно — зачем строить промпты для NPC которые не активны.

  Против:
  - Это оптимизация производительности, не исправление бага
  - Система **уже работает** — NPC молчат через `_resolve_active_npcs` в `npc_agent.py`
  - "Гигантская бесполезная работа" — `build_npc_prompt` это Python dict, не LLM вызов. Реальная стоимость: микросекунды
  - Изменение затрагивает `python_engines.py` — один из самых сложных файлов проекта

  Вердикт: **не сейчас**. Это рефакторинг ради чистоты, не функциональность.

  ---

  **2. "Active Speaker Selection — ленивая генерация"**

  За: правильная идея в теории.

  Против:
  - `npc_agent.py` уже делает это через `_resolve_active_npcs()` — возвращает только активных NPC, остальные не получают LLM вызов
  - Флаг `is_active` в `python_engines.py` — дублирование логики которая уже есть в агенте
  - Создаёт скрытую зависимость между двумя файлами

  Вердикт: **не нужно** — проблема уже решена другим путём.

  ---

  **3. "Social Reaction Rules — Защитник/Перехватчик"**

  За: это действительно нужная система для живого мира.

  Против:
  - Это **фаза R3** по roadmap (Goal Engine + Intent architecture)
  - Требует стабильных Relationships (R1.C2 — ещё не подключено полностью)
  - Без Working Memory работающей в промпте — бессмысленно: Защитник вмешается, но NPC не будут помнить почему
  - Порядок: сначала NPC должны помнить → потом реагировать на основе памяти

  Вердикт: **правильно, но преждевременно**. Вернёмся в R3.

  ---

  **4. "Data-Driven NPC JSON с social_role и social_links"**

  За: архитектурно правильно, расширяемо.

  Против:
  - Требует изменения схемы `major_npcs.json` для всех NPC
  - Требует нового движка чтения этих полей
  - Без Goal Engine эти поля мертвы — некому их читать

  Вердикт: **спроектировать поля сейчас, реализовать в R3**. Добавить `social_role` и `social_links` в JSON как пустые заглушки — ничего не сломает, подготовит почву.

  ---

  ### Текущее реальное положение на roadmap

  ```
  R1-Connect  ████████░░  80%  (Working Memory подключена, Relationships — нет)
  R2          ██████░░░░  60%  (Extractor работает, scene_events в промпт — не подтверждено)
  R3          ░░░░░░░░░░   0%  (Goal Engine, Intent, Social Rules — не начато)
  ```

  ---

  ### Что делать прямо сейчас (в правильном порядке)

  **Шаг 1 — подтвердить что R1 работает** (5 минут игры):
  Сыграй 3 хода с Торнином о цене. Спроси на 4-м ходу. Помнит цифры — R1 закрыт. Не помнит — сначала чиним это.

  **Шаг 2 — подтвердить R2** (1 ход):
  Люся уронила поднос → следующий ход. В панели объектов `поднос: dropped`? DM не повторяет падение? Если да — R2 закрыт.

  **Шаг 3 — единственное полезное из предложенного сейчас:**

  Добавить `social_role` и `social_links` в JSON NPC как пустые поля — это 2 минуты, ничего не ломает, готовит R3:

  ```json
  "social_role": "owner",
  "social_links": [
    {"target": "maid_lusya", "type": "authority", "strength": 0.8}
  ]
  ```

  **Шаг 4 — после подтверждения R1+R2:** идём в R3 по roadmap — Goal Engine.

  ---

  ### Итог

  Из всего предложенного **сейчас делаем только одно**: добавляем `social_role` и `social_links` как пустые поля в `major_npcs.json`. Всё остальное — R3, после подтверждения что R1 и R2 реально работают.

  Покажи результат теста с Торнином и подносом — тогда поймём точно, где мы находимся.


## Анализ перед планом.

  Сначала — честная карта: что из этой архитектуры **уже есть** в Enigma, что **есть частично**, что **отсутствует**.

  ---

  ```
  [1] WORLD STATE          ✅ world_state.py, scene_state_manager.py
  [2] EVENT LAYER          ✅ event_bus.py, event_types.py (только что починен)
  [3] DECISION HUB         ⚠️  фрагменты: npc_cognition, psyche_engine,
                              reaction_priority — но НЕТ единой формулы score()
  [4] STATE UPDATE         ⚠️  life_engine.py — частично, без intent-фиксации
  [5] LLM VERBALIZATION    ✅ dm_agent.py, npc_agent.py — но получают слишком
                              много контекста, а не только intent+emotion
  [6] MEMORY AS WEIGHT     ⚠️  файлы есть (importance_engine, relationship_store,
                              working_memory) — но НЕ подключены к score()
  ```

  **Вывод:** скелет стоит. Нет главной связки: `Event → score() → intent → LLM`.

  ---

  ## ПЛАН ПЕРЕХОДА

  ### ФАЗА R1 — Memory Core v1 *(текущий запланированный milestone)*
  *Цель: подключить память к весам, не к тексту.*

  **R1.1** — `MemoryManager` фасад  
  Единая точка входа для всех агентов. Не хранит текст — возвращает числа.  
  Файл: `services/memory/memory_manager.py`

  **R1.2** — `WorkingMemory` deque  
  Скользящее окно последних N событий сессии.  
  Файл: `services/memory/working_memory.py`

  **R1.3** — `ImportanceEngine` + decay  
  `importance_score(event) → float`. Затухание по времени.  
  Файл: `services/memory/importance_engine.py`

  **R1.4** — `RelationshipStore` как весовая матрица  
  `trust[player][npc_id]`, `fear[npc_id]`, `debt[npc_id]`.  
  JSON-персистентность. Без текста.  
  Файл: `services/memory/relationship_store.py`

  **R1.5** — `ContradictionResolver`  
  Если два события дают противоположные сигналы — резолюция по весу важности.  
  Файл: `services/memory/contradiction_resolver.py`

  ---

  ### ФАЗА R2 — Decision Hub v1 *(ядро интеллекта)*
  *Цель: реализовать единую формулу score() для каждого NPC.*

  **R2.1** — `NPCState` dataclass  
  Единый объект состояния NPC: `emotion`, `stress`, `intent`, `drives`.  
  Поля — только числа и enum.

  **R2.2** — `DecisionHub.score(action, npc_state, context) → float`  
  Реализация формулы:
  ```
  score = (drive_weight × context_relevance)
        + emotion_weight
        + relationship_modifier
        - (fear × risk)
  ```
  Все коэффициенты — константы в одном файле.

  **R2.3** — `IntentResolver`  
  `max(score(action) for action in possible_actions) → Intent`  
  Возможные действия — фиксированный enum (не генерирует LLM).

  **R2.4** — Подключение к EventBus  
  `Event → DecisionHub.process(npc_id, event) → NPCState (updated)`  
  Каждый NPC подписан на события в своём радиусе.

  **R2.5** — StateUpdate  
  После `IntentResolver` — запись в `NPCState`:  
  `emotion`, `stress ± delta`, `trust ± delta`, `intent`.

  ---

  ### ФАЗА R3 — LLM Verbalization Layer *(очистка)*
  *Цель: LLM получает только intent+emotion, не весь контекст.*

  **R3.1** — `VerbalizationContext` dataclass  
  ```python
  @dataclass
  class VerbalizationContext:
      npc_id:    str
      npc_name:  str
      emotion:   str      # enum → строка
      intent:    str      # enum → строка
      target:    str
      scene_hint: str     # ≤ 50 токенов
  ```

  **R3.2** — Переписать `npc_agent.py`  
  Агент принимает `VerbalizationContext`, не `shared_context`.  
  Промпт ≤ 300 токенов. Ответ — только реплика/действие NPC.

  **R3.3** — Переписать `dm_agent.py`  
  DM получает: список `intent`-ов всех NPC + результат хода.  
  Синтезирует нарратив. Не принимает решений за NPC.

  ---

  ### ФАЗА R4 — Integration & Calibration
  *Цель: сквозной прогон, калибровка коэффициентов.*

  **R4.1** — Smoke test: `Event → score() → intent → verbalization`  
  Один NPC, одно действие игрока, сквозной путь без LLM.

  **R4.2** — Калибровка весов  
  Ручной прогон 10 сценариев. Запись ожидаемого `intent`.  
  Подбор коэффициентов до совпадения с ожиданием.

  **R4.3** — Координаты в `SceneState`  
  `life_engine.py` начинает писать `position: {x, y}` для каждого NPC.  
  `PlayerTargetExtractor._get_distance()` переключится на реальные данные автоматически (уже готово).

  **R4.4** — Финальный smoke test  
  Полный цикл с LLM: стражник видит провальную попытку игрока, Decision Hub выдаёт `INVESTIGATE`, LLM вербализует реплику.

  ---

  ## Порядок старта

  ```
  Сейчас → R1.1 (MemoryManager фасад)
  ```

  Для старта нужен файл:
  ```
  backend/app/services/memory/memory_manager.py
  ```

  Покажи его — начнём R1.1.  



Итоговая таблица архитектурных решений (финальная):
  #Решение1NPCState — источник истины2Intent хранится в NPCState3Event-trigger + редкий idle тик4Enum + фильтр доступности5RelationshipStore + кэш в NPCState6emotion_base + Σ(delta × decay)7Risk из контекста (свидетели, дистанция, сила)8Радиус → Perception (два фильтра)9DecisionHub = read-only. StateApplicator = write-only10LifeEngine = фоновый тик11intent + emotion + fact-hint ≤ 100 токенов12±10% randomness, seed per-session13Цель: 10–30 NPC, запас до 5014Старт: только R1.1

И вот я начал следовать плану:
R1.1 закрыт.
R1.2 закрыт.
R1.3 закрыт.
R1.4 закрыт.
R1.5 закрыт.
Все пять задач R1 выполнены.

R2.1 закрыт.
 pending_decay — отклоняю. Преждевременная оптимизация. Разные скорости decay решаются параметром в apply_decay(), не структурой данных.
Проблема: _score_npc читает npc dict напрямую, а не NPCState. После R2 это создаст дублирование источников данных.

R2.2 готов.
R2.3 готов.
R1 полностью закрыт. R2.1–R2.4 закрыты.

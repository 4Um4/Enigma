# SESSION S62: DM Vision Fix — Снятие слепоты DM-агента

## Исправленные разрывы

### 1. NameError в DecisionHub (КРИТИЧЕСКИЙ КРАШ)
- **Файл:** `backend/app/services/npc/decision_hub.py:882`
- **Баг:** `getattr(state, 'npc_id', '?')` — переменная `state` не существует в scope `_context_relevance`
- **Фикс:** Убрана ссылка на несуществующий `state`, заменена на `intent`
- **Результат:** DecisionHub больше не крашится при атаке игрока. `[DIAG_AGGRESSION] intent=attack event=player_attacks ATTACK_base=1.30`

### 2. Combat Outcome в DM-контракте
- **Файлы:** `pipeline_context.py`, `tick_orchestrator.py`, `dm_agent.py`
- **Баг:** DM видел "Результаты проверок: успех" но не знал урон, шок, кровопотерю
- **Фикс:** Извлечение PhysiologyPayload из combat_result → combat_data в shared_context → блок "Последствия атаки" в DM
- **Результат:** DM видит `tavern_keeper_tornin: боль +22, шок 0.36, кровопотеря +0.09`

### 3. Контекст NPC (роли, описания) в DM-контракте
- **Файлы:** `pipeline_context.py`, `dm_agent.py`
- **Баг:** DM не знал кто такой guard_borko — стражник или вор
- **Фикс:** Проброс all_npcs_raw_snapshot из tick_orchestrator → shared_context → DM. Поддержка dict и dataclass (getattr + get fallback)
- **Результат:** DM видит `Стражник Борко: Стражник городских ворот: Дородный стражник в городской броне...`

### 4. Range Gate в CombatSubscriber
- **Файлы:** `combat_subscriber.py`, `tick_orchestrator.py`, `dm_agent.py`
- **Баг:** Игрок "достаёт" NPC через всю комнату без проверки расстояния
- **Фикс:** Проверка player_distances перед физическим воздействием. Промахи попадают в combat_data для DM
- **Результат:** NPC вне радиуса не получают урон, DM видит "НЕ ДОСТИГНУТ — слишком далеко"

### 5. Очистка диагностического мусора
- Убраны print-диагностики из dm_agent.py (DIAG_NPC_CTX, DIAG_NPC_TYPE, DIAG_NPC_KEYS)

## Подтверждённые работающие системы

### Embodied Traces (The Fool v2) — РАБОТАЕТ
Вопреки изначальному анализу, embodied_traces УЖЕ доходили до DM. Блок "Наблюдаемые симптомы NPC" работает корректно: `guard_borko: дрожит, покачивается, напряжённая поза`

## Нерешённые проблемы (следующая сессия)

### 6. NPC position = "bed" вместо актуального узла (stale schedule)
- **Симптом:** `[PIPELINE][TRAVERSAL] npc=maid_lusya status=MOVING from=bed to=tavern_silver_wolf:room_1`
- **Корень:** NPC position берётся из schedule ("bed" = спит), но NPC уже стоит в комнате с local_position
- **Следствие:** TraversalState строит путь от кровати, визуальная телепортация

### 7. "NPC не предпринимают значимых действий" — ЛОЖЬ
- maid_lusya бежит (intent=flee), но DM видит "NPC не предпринимают значимых действий"
- Корень: SceneOutcomeBuilder.to_dm_prompt_block() не получает данные о движении NPC
- Требует интеграции movement_intents в DMFrame или отдельный блок

### 8. all_npcs_raw_snapshot пропадает на некоторых ходах
- Первый ход: _anr=YES len=6
- Иногда: _anr=NONE
- Корень: предположительно reset shared_context между ходами или условие в tick_orchestrator

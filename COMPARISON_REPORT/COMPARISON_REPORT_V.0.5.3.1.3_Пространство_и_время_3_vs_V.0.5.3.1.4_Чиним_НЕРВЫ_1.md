# Сравнение за день: V.0.5.3.1.3_Пространство_и_время_3 -> V.0.5.3.1.4_Чиним_НЕРВЫ_1

## CRITICAL_PARAMETER

Сравнение сделано не по строкам, а по функциональным узлам pipeline.

- База: `origin/V.0.5.3.1.3_Пространство_и_время_3`
- Новая ветка: `V.0.5.3.1.4_Чиним_НЕРВЫ_1`
- Дата фиксации: 2026-05-24
- Diff до документирования: 26 измененных tracked-файлов, `1153` добавления, `2820` удалений.
- Новые untracked-артефакты до сохранения: 19 файлов.
- Главная метрика дня: не объем кода, а закрытие разрыва `will/directive -> exact player position -> MovementIntent -> SceneChange -> frontend projection`.

## PIPELINE_OBJECT

Главный объект дня:

```text
Reactive embodied response to player will
```

Рабочая цепь:

```text
player action / directive
-> NpcTickInput / hub event
-> npc_tick_pipeline reactive movement resolution
-> MacroMovementGoal(target_node_id, target_local_xy)
-> MovementEngine.process_intents()
-> SceneChange(target_local_xy)
-> SceneStateManager.apply_changes()
-> world_snapshot / npc_positions / avatar_state
-> frontend projection / Resistance Medium
```

Это не отдельная фича движения. Это попытка сделать так, чтобы The Fool реагировал телом, сопротивлением и пространством через один причинный канал.

## FAIL_STAGE

FAIL_STAGE предыдущего состояния:

```text
READ -> TRANSFORM -> APPLY
```

Причина:

`APPROACH` мог быть сформирован как смысловое решение, но цель игрока часто читалась как macro node `entrance`, а не как текущая точная координата. Дальше `MovementEngine` применял корректный intent к некорректному target, и NPC "слушался" не игрока, а устаревшего пространственного указателя.

Второй отказ:

```text
APPLY ownership conflict
```

`npc_orchestration` мог исполнять `MovementIntent` напрямую, хотя execution должен принадлежать `TickOrchestrator`/movement pipeline. Это создавало риск двойного будущего: один intent мог быть обработан двумя владельцами.

## HYPOTHESES

| Гипотеза | Вероятность | Проверка |
|---|---:|---|
| H1: главный корень был в протухшей позиции игрока и macro-node `entrance` | 55% | `npc_tick_pipeline.py`, `scene_state_manager.py`, `npc_orchestration.py` меняют чтение/синхронизацию позиции игрока |
| H2: часть симптомов была вызвана двойным исполнением movement intent | 25% | `npc_orchestration.py` удаляет прямой `process_intents/apply_changes`, `movement.py` добавляет processed/processor guard |
| H3: frontend не получал/не применял феноменологическую часть конфликта воли | 20% | `routes.py` и `game_screen.py` пробрасывают `will_conflict_data` и `avatar_state` |

Confidence: 84/100.

## FIX_SCOPE

Минимальный функциональный scope дня:

1. `llama-server` lifecycle guard.
2. `will_conflict_data` в API response.
3. Frontend Resistance Medium infection.
4. Обновление `avatar_state` после action-response.
5. `target_local_xy` в `MacroMovementGoal`.
6. `target_local_xy` в `SceneChange`.
7. Exact target handoff из `MovementEngine`.
8. Player local-position priority в `APPROACH`.
9. Восстановление `from_xy` из текущего узла при невалидных координатах.
10. Guard от двойной обработки `MovementIntent`.
11. Удаление execution ownership из `npc_orchestration`.
12. Документальная компрессия ADR/DTO/MUTATIONS/flow под доменную читаемость.

Итого: **примерно 9-12 смысловых функций/стабилизаций**, из них **6-7 напрямую влияют на gameplay/runtime The Fool**.

## RISKS

| Риск | Уровень | Причина |
|---|---|---|
| `MacroMovementGoal` перестал быть frozen | высокий | guard `processed` добавляет mutability в DTO; это защищает от double-process, но ослабляет immutable-contract |
| `player_spatial` снова участвует в чтении | средний | комментарии говорят о запрете, но часть кода использует fallback/синхронизацию; нужен финальный owner-contract |
| `target_local_xy` расширяет DTO без полного ADR-номера | средний | TODO/ADR-XXXX указывает незавершенную протоколизацию |
| Диагностические `print()` в runtime | низкий-средний | полезно для дня фикса, но шумит pipeline |
| Документация была сильно сжата | средний | меньше шума, но есть риск потери исторических деталей, если не сохранены старые источники |

## ALTERNATIVES

1. Не добавлять `target_local_xy`, а всегда резолвить игрока в macro node.
   - Отвергнуто: симптом оставался бы, NPC продолжали бы идти в "узел игрока", а не к телу игрока.

2. Исполнять movement в `npc_orchestration`.
   - Отвергнуто: это перенос ownership execution в слой сборки контекста.

3. Сделать отдельный DTO для player-target movement.
   - Не требуется сейчас: существующий `MacroMovementGoal` расширен минимально, без нового слоя.

4. Переписать spatial authority целиком.
   - Избыточно: текущий день показывает локальный отказ target resolution и ownership execution, не доказан полный отказ pipeline.

## CONCLUSION

За день сделано не "много строк", а важный локальный ремонт нервной системы The Fool.

Самая ценная работа:

- социальная/волевая реакция начала доходить до frontend как феноменологическое сопротивление;
- spatial target для `APPROACH` стал ближе к реальному телу игрока;
- movement execution вернули к единому владельцу;
- intent получил защиту от повторной обработки;
- `llama-server` lifecycle перестал разрушать соседний backend runtime;
- архитектурная память проекта стала компактнее и читабельнее для следующих проходов.

Системная оценка:

```text
feature growth: medium
runtime stabilization: high
ownership risk: still high
gameplay value: high for embodied NPC response
documentation compression value: medium-high
```

Главный остаток:

Нужно окончательно закрепить contract:

```text
player position owner -> npc_positions.player
player_spatial -> projection/legacy/dead source status
MovementIntent -> immutable request or mutable processing-token
```

Пока это не закрыто, The Fool уже двигается в правильную сторону, но spatial authority остается горячей зоной.

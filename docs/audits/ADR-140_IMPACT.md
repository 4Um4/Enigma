# ADR-140 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-140` [STANDARD] **IMPACT**
# ADR-140 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Суть
DM получает life_status из player_state через avatar_to_prompt и генерирует death scene narration.
DM НЕ вычисляет смерть — только читает уже замороженный факт из S74-S75.
Death Guard вызывает DM вместо возврата хардкод-строки (с fallback при Exception).

## Changed Domains
- Narrative (DM layer)
- Player State projection (avatar_to_prompt)

## Downstream Consumers
- dm_agent._build_contract() — читает pdata["life_status"]
- DMContractBuilder.add_custom_block() — получает death scene block
- game_loop Death Guard — вызывает DM для death narration

## Изменённые файлы (4)

### 1. backend/app/services/game_loop/phase_6_avatar.py
- avatar_to_prompt() добавлено поле life_status из body_state
- Fallback: body_state=None → ALIVE

### 2. backend/app/agents/dm_agent.py
- Блок 4: pdata["life_status"]=="DEAD" → маркер "МЁРТВ"
- Блок 4.2: Death Scene custom block при _is_player_dead

### 3. backend/app/services/game_loop/__init__.py
- Death Guard: shared_context.player_state заполняется ПЕРЕД return
- Death Guard: вызов DM через run_agent_safe вместо хардкод-строки
- Fallback при Exception: старая хардкод-строка

### 4. backend/tests/sandbox/persistence/test_dm_death_scene_includes_life_status.py
- 6 тестов: avatar_to_prompt (3), dm_contract (2), dm-no-compute (1)

## Runtime Impact
- +1 LLM call при смерти игрока (death narration вместо хардкода)
- 0 при ALIVE (death block не генерируется)

## Sandbox Tests
- test_dm_death_scene_includes_life_status.py (6 тестов, все PASS)

## Rollback
1. Удалить life_status из avatar_to_prompt()
2. Удалить death block из dm_agent._build_contract()
3. Вернуть хардкод-строку в Death Guard
4. Удалить тест-файл

## Новые архитектурные запреты
- Rule 62: DM narration без проверки player life_status = каузальный обман
- Rule 65: avatar_to_prompt без life_status = слепой DM
- Rule 66: Death Guard без вызова DM = подмена нарратива хардкодом


Files: N/A

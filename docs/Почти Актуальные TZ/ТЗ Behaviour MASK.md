# ТЗ преемнику

## Контекст: где мы

Сессия работала над закрытием B′ (Behavior Mask closure, эпизод E-BM1). Пятая итерация повтора (`B′-005`) воспроизвела историческую пару с byte-exact точностью (`attack contrast = +1.607665`). Корневая причина найдена, документация зафиксирована, патч подготовлен, но **не применён** — Master взял паузу на решение по радиусу.

Ветка: `V.0.5.4.3.8_Замыкание_1`. HEAD на момент фиксации аудита: `8c5c3bbba` (worktree для B′-005 — `2d2fea08`).

## Что уже сделано (читай перед стартом)

1. **`docs/MUTATIONS.md` строка S357** — запись про B′-005: повтор, причинная цепочка, корень, решения Master (2-A interim + новая задача), статус `⏳ IN PROGRESS`.
2. **`docs/ENIGMA_ROADMAP_v4_7_EPI-updated.md` §20** — новый трек SUBJ-AVOID «Субъективная оценка угрозы и социальное избегание» (v4.9-draft, roadmap-only). 4 фазы, 6 сценариев S1–S6 с поправкой S4, гейты SUBJ-GC-01..04, архитектурный бриф с 5 развилками.
3. **`reports/bprime_artifacts_repeat_005/`** — 6 JSON артефактов B′-005 (из worktree).
4. **`reports/bprime_artifacts/CLOSURE.md` §11** — обновлён полной причинной цепочкой + B5 warning.

## Что НЕ сделано (твоя зона)

### Этап C — патч и повтор B′-006 (блокер)

**Перед стартом — получить от Master вердикт по радиусу патча:**

| Вариант | Строки | Ожидаемый recent_pressure (WORLD_TICK) |
|---|---|---|
| **1 (рекомендован)** | 1226 + 208 + 323 (skip 267) | 0.0 |
| **2 (минимум)** | только 1226 | ~0.4–0.8 (perception пути 208/323 остаются) |
| **3 (отложить)** | ничего | 0.8 (как сейчас) |

**Если Вариант 1 или 2 — выполнить:**

1. Патч в `backend/app/services/npc/npc_tick_pipeline.py`:
   - 1226: `player_target_id=state.player_target_id or "player",` → `player_target_id=state.player_target_id or "",`
   - 208 (только Вариант 1): `_p_target = state.player_target_id or "player"` → `_p_target = state.player_target_id or ""`
   - 323 (только Вариант 1): `state.player_target_id or "player",` → `state.player_target_id or "",`
   - 267: **НЕ ТРОГАТЬ** (guard check в `resolve_physical_attack`, нет записи в память)

2. Запустить B′-006 (framework: `backend/tests/sandbox/SUPERBOX/scenarios/bm_bprime_framework.py`) на том же HEAD, что B′-005. Артефакты → `reports/bprime_artifacts_repeat_006/`.

3. Проверить двойной критерий C.3:
   - `recent_pressure` (player) = 0.0 (или близко) — **исчезновение ложного давления**
   - `attack contrast` (mask ON − OFF) = +1.607665 ± 0.01 — **сохранение независимых mask-эффектов**

4. Если УСПЕХ по обоим — закрыть S357 в MUTATIONS (`⏳ IN PROGRESS` → `✅`), добавить S358 (B′-closure). Если ЧАСТИЧНО или ПРОВАЛ — трассировка, что именно изменилось, и эскалация Master.

**Стоп-правило:** production-код меняется только после вердикта Master по радиусу.

### Этап D — аудит SUBJ-AVOID (параллельно, без кода)

После (или параллельно с) Этапом C — начать Фазу 0 трека §20:

1. Аудит шести доменов (физическая угроза, страх, память о вреде, соц. отношения, репутация/статус, выбор стратегии).
2. Спецификация сценариев S1–S6 (с поправкой S4: `threat_intent ≠ threat_credibility ≠ expected_harm`).
3. Deliverables: `reports/threat_audit/DOMAIN_MAP.md`, `reports/threat_audit/SCENARIOS.md`.
4. Гейт SUBJ-GC-01.

Фаза 1 (черновик контракта) — только после SUBJ-GC-01. Фаза 3 (реализация) — только после SUBJ-GC-04 (вердикт Master).

## Ключевые контракты (не пересомневай)

- `EventContext.target_id: Optional[str] = None` — поле существует (`decision_hub.py`, GAP10 FIX)
- `EventMemory.target_id: str` — обязательное, принимает `""` без побочных эффектов (`npc_state.py:222`)
- `MemoryManager.apply`: `target_id=payload.get("target_id", event.source)` — fallback на `event.source` срабатывает только при отсутствии ключа; при `target_id=""` в payload возвращается `""`, не `event.source`
- `get_weights_for_decision` фильтр: `e.target_id == tid` — при `e.target_id=""` и `tid="player"` не срабатывает → `recent_pressure` не накапливается
- В `decision_hub.py` уже есть `if event.target_id and event.event_type != EventType.WORLD_TICK: return event.target_id` — наш патч соответствует существующему контракту системы, не вводит новое правило
- `apply_perception_memory` (1305) и `create_memory_event` (1362) — две разные функции, но обе пишут в `EventDTO.payload["target_id"]` → обе загрязняют `recent_pressure`. Патчить нужно обе точки входа.

## Инструментарий (готовый, нейтральность подтверждена)

| Инструмент | Файл | Назначение |
|---|---|---|
| D-5 | `rel_goran_per_tick` | V2 directed relations per tick |
| H1a | `components_per_tick` | `_score_all` interceptor, 6/6 neutral |
| H1b-mini | `base_before/after_mask`, `mask_application_enabled` | Mask gate |
| H1b-mini2 | `fear/drives/risk inputs` (строки, не числа!) | Risk inputs |
| H1b-mini3 | `_h1b3_pressure_events` (list) | Pressure events |

**Критический урок (B5 warning):** H1b-mini2 изначально добавил числовые диагностические поля в `components` dict, которые `base = sum(...)` ошибочно суммировал. Это сломало B′-003/004. **Диагностические поля должны быть строками или списками, не числами** — иначе они попадут в sum и сломают baseline. Проверяй нейтральность каждого нового поля.

##Anti-Race §4 (Устав)

- S-номер = max(диска)+1 **перед записью**. Текущий max: S357 (внесён этой сессией). Следующий: S358.
- `git commit --amend` при живых параллельных сессиях **ЗАПРЕЩЁН** (инцидент S318). Только `git commit -- <pathspec>`.
- При параллельных ветках — проверяй `git log --all` и реестр перед присвоением номера.

## Живая эскалация на Master (не моя компетенция)

1. **Радиус патча** (Вариант 1/2/3) — блокер для Этапа C.
2. **5 развилок §20.6** — архитектурный бриф SUBJ-AVOID (тип `expected_harm`, место `memory_of_harm`, природа `threat_credibility`, статус avoidance, владение §R.7).
3. **Семантика `recent_pressure`** — interim 2-A не закрывает вопрос «какие события имеют право влиять на давление». Это вне компетенции преемника — решение Master.
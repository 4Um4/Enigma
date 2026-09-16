# ADR-O-395 Impact Audit
> Детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- причинный слой (DesiredChange + вторая фабрика), экономика (только ЧТЕНИЕ has_good/gold)

## Downstream Consumers
- Срез 2b (буд.): npc_tick_pipeline (проводка causal_modifiers), DecisionHub.compute(causal_addressee), _resolve_target
- SOCIAL-сессия S262+: addressee hunger-среза — готовый причинный вход их target-stage
- eco_modifiers: сосуществуют (CS12: безликая деформация vs адресованное распределение)

## Runtime Impact
- Нулевой в 2a: продюсер не подключён к пайплайну. Прогноз 2b: O(candidates) скан на голодного NPC, ~микросекунды; RAM — ноль (профили уже препружены в TickState)

## Sandbox Tests
- backend/tests/gameplay/test_r6_causal_slice_hunger.py: T1-T4 (пины) / W1-W5+W4b (контрфакт CS13) / A1-A3 (факторная чувствительность) / A-A (no-op проекция)
- Регрессия: tests/gameplay/ 96 passed + gc09b (pre-existing, §6 хенда); IPT 45/0 = baseline V.0.5.4.0.5_Говорим_4

## Rollback
- Удалить causal_slice_hunger.py + тест; вырезать фабрику acquire_resource из desired_change.py (аддитивный блок в конце файла). Ядро/пайплайн не задеты — откат тривиален и бесследен.

## Уроки (для §8-реестра будущих хендоффов)
- D-R6-HASSTOCK-SEMANTICS: семантика метода не выводится из имени — только из тела (has_stock ≠ has_good). Собственное нарушение §13.1 поймано зондом за 1 итерацию: прогноз-таблица + рантайм-декомпозиция.
- D-R6-PARTIAL-PATCH: патч-блоки применяются частично (A3 остался старым) — прогон после каждого применения пакета, не после «всех сразу».
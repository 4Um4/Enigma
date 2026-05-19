### ADR-PRE-FLIGHT CHECKLIST (Perception → Emotion Converter)

1. **Тип АДР:** ONTOLOGY (ADR-O) — Восстановление каузальной цепи Восприятие → Эмоция.
2. **Затронутые домены:** `perception`, `emotion`, `decision`.
3. **Связанные потребители (Downstream):**
   - `DecisionHub` (должен получать сгенерированный `EmotionPayload` для корректировки решений)
   - `StateApplicator` (применяет `EmotionPayload` к `NPCState`)
   - `AffectEngine` / `ResonanceEngine` (могут использовать эмоции для усиления давления)
4. **Бюджет ресурсов:** 
   - RAM Delta: ~0
   - VRAM Delta: 0
   - Tick Latency Delta: +0.1ms (вычисление порога и генерация DTO)
5. **Откат (Rollback):** Удалить конвертер и вызов из `tick_orchestrator` / `state_applicator`.
6. **Регрессия:** `python -m pytest backend/tests/sandbox/ -v --tb=short`

### ADR-PRE-FLIGHT CHECKLIST (ADR-049 Phase 3: Legacy Hardcode Deprecation)

1. **Тип АДР:** STANDARD (Удаление мертвого легаси-кода)
2. **Затронутые домены:** `emotion`, `decision`
3. **Связанные потребители (Downstream):**
   - `StateApplicator` (перестанет получать искаженные реактивные `EmotionPayload` от `DecisionHub`)
   - `DecisionHub` (очищение от ответственности за генерацию эмоций)
4. **Бюджет ресурсов:** 
   - RAM Delta: 0
   - VRAM Delta: 0
   - Tick Latency Delta: -0.05ms (удаление цикла маппинга эмоций)
5. **Откат (Rollback):** Раскомментировать блок `emotion_map` в `_extract_deltas_from_decision`.
6. **Регрессия:** `python -m pytest backend/tests/sandbox/ -v --tb=short`

Я вижу проблему своими глазами. `MovementIntent` объединяет две несовместимые физики:
1. **LOD1 (Макро):** `target_node_id` — навигация по графу (двери, комнаты).
2. **LOD0 (Микро):** `local_target_xy` — локальный stepping (уклонение, расхождение).

Это и есть **Критический разрыв №2**. Как предупреждал Стратег: *"Pipeline не понимает: это pathfinding или steering?"*

В соответствии с Уставом, я заполняю **ADR-PRE-FLIGHT CHECKLIST** для разделения онтологий:

### ADR-PRE-FLIGHT CHECKLIST (ADR-060: LOD0/LOD1 Movement Ontology Split)

1. **Тип АДР:** ONTOLOGY (ADR-O) — Разделение макро-навигации и микро-рулежки.
2. **Затронутые домены:** `spatial`, `locomotion`, `decision`.
3. **Связанные потребители (Downstream):**
   - `MovementEngine` (должен обрабатывать два разных типа интентов)
   - `LifeEngine` (генерирует LOD1)
   - `npc_tick_pipeline` (генерирует LOD0 для MOVE рефлекса)
4. **Бюджет ресурсов:** 
   - RAM Delta: 0
   - VRAM Delta: 0
   - Tick Latency Delta: 0
5. **Откат (Rollback):** Вернуть `local_target_xy` в `MovementIntent`.
6. **Регрессия:** `python -m pytest backend/tests/sandbox/ -v --tb=short`



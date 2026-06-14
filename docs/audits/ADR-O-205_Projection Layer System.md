### ADR-PRE-FLIGHT CHECKLIST: ADR-O-205 (Projection Layer System)

**1. Тип АДР:** ONTOLOGY (ADR-O). Мы меняем онтологию аффективного вывода: переход от `EmotionTag` как универсального состояния к трём несовместимым проекциям.

**2. Затронутые домены:**
*   `emotion/affective` (Убийство `EmotionTag` как источника истины)
*   `perception/interpretation` (Моторная проекция)
*   `verbalization/narrative` (Нарративная проекция)
*   `memory/identity` (Мнемоническая проекция)
*   `causality/pipeline` (Изменение структуры `EmotionPayload`)

**3. Связанные потребители (Downstream):**
*   `BehaviorManifestationService` — Переводится на сырые сигналы (`threat_gradient`, `affective_velocity`, `somatic_urgency`).
*   `VerbalizationContext` / `VerbalStance` — Переводится на чтение вектора `redirect` (победивший драйв) вместо `state.emotion`.
*   `ImportanceEngine` / `MemoryManager` — Переводится на чтение `error_vector` (величина расхождения) и `dominant_drive` вместо `emotion_tag`.
*   `StateApplicator` — Изменяет правила сериализации (запись трёх проекций вместо одного тега).
*   `TickOrchestrator` — Точка генерации проекций на основе данных Котла и DecisionHub.

**4. Бюджет ресурсов:**
*   **RAM:** Увеличение на ~20-30 байт на NPC (хранение 3 лёгких проекций вместо 1 строки + 1 float). Пренебрежимо.
*   **Tick Latency:** Увеличение на микросекунды (вычисление 3 простых проекций вместо 1 свитча). Пренебрежимо.
*   **Determinism:** Система остаётся детерминированной. Проекции являются чистыми функциями от уже вычисленных полей.

**5. Откат (Rollback):**
1. Восстановить `EmotionTag` как первичный ключ в `EmotionPayload`.
2. Вернуть свитчи `if emotion == "fearful"` в `BehaviorManifestationService`.
3. Вернуть чтение `state.emotion` в `VerbalizationContext`.
4. Вернуть `emotion_tag` в `ImportanceEngine`.

**6. Регрессия (Sandbox Tests):**
*   `test_motor_projection_no_tag.py` — Моторика генерирует `rigidity` при высоком `threat_gradient`, даже если `redirect` выбрал ATTACK. (Доказательство: тело не знает о разуме).
*   `test_narrative_projection_from_redirect.py` — Нарратив генерирует текст о контроле/агрессии, если `redirect ATTACK > 0`, даже при высоком `affective_load`. (Доказательство: разум рационализирует победу драйва).
*   `test_memory_projection_from_error.py` — Память фиксирует высокую важность при большом `delta` (Surprise) в Котле, независимо от того, какой драйв победил.
*   `test_no_cross_projection_leakage.py` — Верификация инварианта: Motor layer не имеет доступа к `redirect`; Narrative layer не имеет доступа к `somatic_urgency`.
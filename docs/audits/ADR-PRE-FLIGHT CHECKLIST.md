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
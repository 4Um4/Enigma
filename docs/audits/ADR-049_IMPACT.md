# ADR-049 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-049` [STANDARD] **IMPACT**
# ADR-049 Impact Audit: Causal Pressure Pipeline & Affective Accumulation

## Измененный АДР
ADR-049 (Замыкание контуров Восприятие-Эмоция-Решение)

## Тип изменения
ONTOLOGY (ADR-O)

## Этап 1: DecisionContext Geometry (ЗАВЕРШЁН)
- Врезка PerceptualKernel в скоринг DecisionHub.
- Cognitive Override Guard в LifeEngine.

## Этап 2: Affective Accumulation Pipeline (ЗАВЕРШЁН)
- Внедрение субъективного аффективного коллапса (Интеграл угрозы по времени).

## Этап 3: Legacy Hardcode Deprecation (ЗАВЕРШЁН)
- Ампутация реактивного маппинга событий в эмоции из DecisionHub.
- Очищена зона ответственности: DecisionHub больше не генерирует EmotionPayload.

## Изменённые файлы (Этап 3)
- `backend/app/services/npc/decision_hub.py` — удалены `e_stress`, `e_emotion`, `e_tag`. Удален блок `emotion_map`. Удалена генерация `EmotionPayload` в сборке дельт. Социальные дельты (`s_trust`, `s_fear`) сохранены, так как отношения — это рефлекс, а не аффективный коллапс.

## Влияние на производительность (Runtime Impact)
- RAM Delta: 0
- VRAM Delta: 0
- Tick Latency Delta: -0.05ms (удаление цикла маппинга эмоций)

## Песочные тесты (Sandbox Tests)
- 37 passed, 0 failed

## Откат (Rollback)
1. Вернуть блоки вычисления `e_stress`, `e_emotion`, `e_tag` и `emotion_map` в метод `_compute_deltas`.
2. Вернуть генерацию `EmotionPayload` в сборку `result_deltas`.
```

---

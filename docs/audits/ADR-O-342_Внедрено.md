## ADR-O-342: Real-Time Causal Probes & PBT [ONTO]
> **Статус:** ACTIVE
> **Домен:** DOM-01 (Foundation), DOM-08 (Observability)
> **Сессия:** S149

**Контекст:**
Инварианты проверялись только post-mortem (CausalObserver) или вручную (IPT). Баги сериализации и пространства ускользали в production.

**Решение:**
1. **PBT (Подсистема 1):** `hypothesis` генерирует 100+ edge-cases для `NPCState` round-trip (§12.2) при каждом запуске `IPT.py`.
2. **Causal Probes (Подсистема 3):** `ProbeRunner` запускается после Фазы 10 в `TickOrchestrator` в production. `SpatialCoherenceProbe` проверяет SC-1 (запрет `0.0, 0.0`) в реальном времени.

**Taboo:**
- ❌ Запуск `IPT.py` без прохождения `INV-PBT-ROUNDTRIP`.
- ❌ Игнорирование `[PROBE_FAIL]` в production логах.
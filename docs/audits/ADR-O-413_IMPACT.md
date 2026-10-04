# Impact Audit — ADR-O-413 [ONTO] Causal Slice 4 — Affection: забота о состоянии другого (R8)
`ADR-O-413` [ONTO] **Causal Slice 4 — Affection: забота о состоянии другого**
Files: backend/app/domain/desired_change.py, backend/app/services/npc/causal_slice_affection.py, backend/app/services/npc/npc_tick_pipeline.py, backend/tests/gameplay/test_r8_causal_slice_affection.py
> Примечание: изначально анонсирован как ADR-O-400 (конфликт с Watermark S274) — ренумбер по Уставу 11.1.1. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- desired_change/affection: проекция тёплых осей (trust≥40 ∧ attraction≥40) + world-снапшот distress + capacity → DesiredChange(nurture, who≠target_of_change)

## Downstream Consumers
- backend/app/domain/desired_change.py (nurture), backend/app/services/npc/causal_slice_affection.py, backend/app/services/npc/npc_loader.py (attraction-патч enrichment), backend/app/services/npc/npc_tick_pipeline.py (проводка R8)

## Runtime Impact
- тёплые связи порождают заботу (talk/trade/call_for_help, сумма ≤1.0); каскад threat > hunger > grievance > affection

## Sandbox Tests
- backend/tests/gameplay/test_r8_causal_slice_affection.py (10); production-probe orm→lusya←care (trade 0.512)

## Rollback
- revert attraction-патча npc_loader + проводка R8 в npc_tick_pipeline
```

## 4. Наблюдение по git status (не трогаем)

50+ modified и untracked (`cognition_context.py`, `act_consumer.py`, SemanticProbe-корпус) — **чужая параллельная серия живёт в дереве** (Understanding/кognиция-трек). Наши pathspec-коммиты её не задели — дисциплина S242 работает. Ни один чужой файл не добавляем.

## Очередь

1. Создай 4 stub'а + примени Н-55-фикс (выше).
2. Прогони №85 — по выводу выдаю патч `get_impact` + тест.
3. **Коммит 3**: Н-55-строка + 4 stub + path-match fix — «ADR-Net tail: полная честность инструмента».
4. Затем — **DTO Registry** (команды №84 у тебя уже были? если нет — повторю с первым куском).
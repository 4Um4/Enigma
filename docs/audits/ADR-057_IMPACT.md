# ADR-057 Impact Audit: Legitimacy Gate & Elastic Time Foundation

## Changed Domains
- SOCIAL (DirectiveInterpretationSubscriber: Legitimacy Gate)
- IDENTITY (IdentityPayload: is_obedience flag, irritation vectors)
- TEMPORAL (GAME_TICK_INTERVAL_SECONDS: 900s → 60s)
- COGNITIVE (TopicExtractor: directive_response injection)

## Downstream Consumers
- `LifeEngine`: Читает `recent_directive.interrupts_routine` (теперь всегда True при директиве).
- `DecisionHub`: Получает тему `directive_obedience` или `directive_confrontation`. Должен учитывать `is_obedience` для выбора действия.
- `TopicExtractor`: Переопределен темой директивы, если `recent_directive` существует.

## Runtime Impact
- RAM: 0
- CPU: Снижение нагрузки за счет уменьшения временных скачков (меньше догоняющих тиков).
- UX: Фундаментальное изменение поведения NPC: подчинение только при страхе/доверии, иначе раздражение.

## Sandbox Tests
- Требуется создание `backend/tests/sandbox/test_legitimacy_gate.py` для верификации векторов Подчинения и Раздражения.

## Rollback
1. Вернуть `GAME_TICK_INTERVAL_SECONDS = 900`.
2. Удалить проверку `legitimacy` в `DirectiveInterpretationSubscriber`.
3. Удалить инжект темы в `npc_tick_pipeline.py`.
```

Файл: docs/ADR (Architecture Decision Records).md

```markdown
### ADR-057: Legitimacy Gate & Elastic Time Foundation

**Контекст:**
Любое обращение игрока к NPC механически обрабатывалось как Приказ (ObediencePressure), подавляющий волю. Вор подчинялся незнакомцу. Время продвигалось на 15 минут за тик, разрушая физическую непрерывность.

**Решение:**
1. **Legitimacy Gate:** Давление подчинения генерируется только при наличии страха (принуждение) или доверия (авторитет). При их отсутствии директива порождает Раздражение (Irritation), снимающее блоки с агрессии, но не подавляющее волю.
2. **Attention Capture Revision:** Внимание NPC прерывается всегда (бытовуха замораживается), но вектор реакции зависит от флага `is_obedience`.
3. **Topic Injection:** Если есть `recent_directive`, TopicExtractor переопределяется темой `directive_obedience` или `directive_confrontation`.
4. **Elastic Time Foundation:** Базовый интервал `GAME_TICK_INTERVAL_SECONDS` снижен с 900 (15 мин) до 60 (1 мин) секунд для обеспечения плавности хода.

**Последствия:**
- NPC реагирует на игрока контекстуально: подчиняется, если боится/уважает, или возмущается, если тот никто для него.
- Тик больше не прыгает на 15 минут, делая движение и диалог физически ощутимыми.
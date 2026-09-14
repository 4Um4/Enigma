# ADR-O-390 Impact Audit — Epistemic Self-Relevance Channel (GC-RELEVANCE-01)
> Детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`
> Сессия: S258 | Гейт: GC-RELEVANCE-01 | Лестница AGENCY: self-relevance

## Changed Domains
- Epistemic (EpistemicContext: +claims_about_self, +max_self_confidence; resolver: маршрутизация)
- Decision (to_modifiers: разговорный self-буст; DecisionHub не изменён — получает те же Dict[str, float])

## Доказанная дыра (фальсификация, живой проб на живом коде ДО фикса)
Сцена: Люсья слышит от Горана два клейма — «Люсья украла золото» и «Тень украла золото».
- perceived_threats = ('maid_lusya', 'thief_shadow') — агент в собственных угрозах
- perceived_violations = 2 — обвинение в свой адрес засчитано как нарушение
- confidence обоих убеждений идентичен (0.8) — канала различения нет
- trigger_proposition мог выбрать self-клейм → warn-наведение на себя (guard DecisionHub:1929
  прикрывал, но канал триггера оставался загрязнён)

## Downstream Consumers
- DecisionHub.apply_modifiers — аддитивно, без изменений контракта (Modifier Contract v1 цел)
- Epistemic Targeting (DecisionHub:1922) — развязан от self-клеймов на уровне источника
- S211-диспозиции — не тронуты (self-буст аддитивен к disposition-весам)
- Легаси-ветка S198 (to_modifiers без archetype) — байт-в-байт нетронута: пустой
  claims_about_self = прежнее поведение

## Runtime Impact
- resolve(): тот же O(records)-цикл, +2 локальные переменные
- EpistemicContext: +2 поля runtime-only (сериализации нет — grep: конструируется
  единственный раз в resolver:72)
- RAM/latency: пренебрежимо

## Sandbox Tests
- tests/micro/test_self_relevance_gate.py — 9/9 (маршрутизация, развязка threats/violations/
  trigger, модификаторная развязка talk vs warn/attack, нейтральность пустого контекста,
  выживание ключа в apply_modifiers, чистота входа)
- Полная батарея micro: 61/61 (52 прежних + 9 новых, ноль регрессий)
- IPT: 45/45 (0 CRITICAL)
- Пробы до/после: см. «Доказанная дыра» / [PROBE-R1] [PROBE-R2A/B/C] в отчёте сессии

## Rollback
Revert трёх файлов: epistemology.py (2 поля), epistemic_context_resolver.py (маршрутизация +
модификатор), test_self_relevance_gate.py (удаление). Поля с пустыми дефолтами = поведение
прежнее. Частичный откат (поле без маршрутизации или маршрутизация без потребления)
бессмыслен — откатывать целиком. Прецедент ADR-O-389: проекция без применения = ложь.

## Досье среза (долги и границы)
1. DEBT-S28-KEYCASE (НАХОДКА, чужая зона, эскалация Мастеру): S28 Utility Deformation
   (decision_hub.py:577–599) мертва — UPPERCASE-литералы ("ATTACK", "FLEE", "APPROACH",
   "TALK", "INTIMIDATE") проверяются против lowercase-словаря scores (Intent(str, Enum),
   .value строчные, рождение scores: decision_hub:990/1002–1004). Агрессия не подавляется
   соматикой, escape_salience не усиливает FLEE. Не фиксировалось в S258 (Two-Domain Rule:
   чужая фича, фикс = отдельная сессия с собственными замками).
2. object_id == me (я — жертва атаки) — намеренно вне v1: субъект-агрессор корректно
   попадает в threats как есть; изменений семантики требует attack-таблица (долг A12).
3. RESIST/MODIFY (противостояние клейму, конфликт клейма с собственным опытом, виновность)
   — следующая ступень лестницы; v1 даёт только салиентность.
4. End-to-end SUPERBOX-сценарий self-relevance при живой llama — кандидат живой-сессии
   чеклиста (механизм доказан микро-замком на живом коде, прецедент S255: механизм замком,
   end-to-end — живая сессия).
5. Шрам №12 (реестр преемнику): числовые константы в ожиданиях тестов — только прочитанные
   с диска. Инцидент S258: вписал _CLAIM_WEIGHT×0.8 по памяти, пойман собственным замком
   (1 failed), на диске _CLAIM_WEIGHT = 1.0 (belief_revision_engine:15). Поймал замок, не
   прогон — дешёвая цена.
# ADR-O-415 Impact Audit (S319, RE-01 M1b.3.7)
> Греп-страж freeze-поверхности relationship_cache. Единый атлас: docs/ADR (Architecture Decision Records).md. Вход: читатель-карта S318 (коммит 9c282746); сжатая версия — docs/audits/ADR-RE-M1B3_6_IMPACT.md.

## Changed Domains
- RE-01 enforcement: новая статическая поверхность заморозки чтений relationship_cache. Ноль рантайм-изменений (behavior-neutral по построению: скрипт рантаймом не импортируется).
- Развилка гипотез решена археологией: «nested-кэш» карты S318 — не отдельная структура, а вложенность {target: {trust, fear}} того же поля NPCState.relationship_cache / ключа npc-dict → гипотеза A (только рендер-проекции) фальсифицирована, allowlist = заморозка всей текущей легальной поверхности.

## Freeze-семантика (точные счётчики)
- Сайт = строка, содержащая токен (токен дважды в строке = один сайт). Комментарии считаются: термин заморожен, док-дрейф = дрейф.
- GROWTH — новый сайт в разрешённом файле (вне ценза); NEW-FILE — файл с токеном вне allowlist; SHRINK/MISSING — сжатие/исчезновение (ценз-тач allowlist + запись в ADR обязательны: сжатие = документированная миграция DECISION-READER → V2 после M2/D + GC-11; стратегический смысл «кэш-чтения только рендер-проекциям» = конечное состояние поверхности, не стартовое условие стража).
- UNREADABLE = violation (молчаливый пропуск файла = дыра в заморозке, L4).
- Уроки вшиты: utf-8-sig (S317, BOM ×11 read-sites); root от __file__ (S314, CWD-относительные пути); fail-loud PARSE-политика.

## Allowlist (19 файлов / 52 сайта; baseline независимо пересчитан суд-прогоном скрипта на живом дереве)

| Файл (от backend/app) | Сайтов | Роль |
|---|---|---|
| models/npc_state.py | 7 | OWNER-MODEL + PROJECTION-SERIALIZE + ephemeral-фабрика |
| models/idle_tick.py | 1 | DECL-MODEL (idle TypedDict, READ-ONLY проекция Фазы 0.5) |
| models/causality_manifest.py | 1 | DECL-MANIFEST (S317, authority ADR-O-370) |
| services/tick_utils.py | 10 | SANITIZER (единственная точка обогащения кэша) |
| services/npc/state_applicator.py | 2 | WRITER-SYNC (update_relationships) |
| services/npc/npc_tick_pipeline.py | 2 | WRITER-TICK-HYDRATE (TZ-10 preloaded weights) |
| services/npc/npc_loader.py | 8 | LOADER-BOOTSTRAP (legacy-обогащение; GAP-4-контекст) |
| services/social/v2_relationship_backend.py | 2 | BOOTSTRAP-SOURCE (lift legacy → V2, M1b.1) |
| services/npc/interpretation_engine.py | 2 | DECISION-READER (карта S318) |
| services/npc/decision/risk.py | 1 | DECISION-READER |
| services/npc/decision/social_deltas.py | 1 | DECISION-READER |
| services/npc/social_target_resolver.py | 1 | DECISION-READER |
| services/phases/decision.py | 1 | DECISION-READER |
| services/social/directive_interpretation_subscriber.py | 5 | DECISION-READER |
| services/social/social_decay_handler.py | 2 | DECAY-READER (GAP-4-контекст) |
| services/combat/combat_subscriber.py | 2 | SNAPSHOT-COPY-THROUGH + INIT-EMPTY |
| services/npc/decision_hub.py | 2 | DOC-NEGATIVE (запретительные комменты ENIGMA-REL-001) |
| services/player_cognition/cognitive_distortion.py | 1 | DOC-NEGATIVE |
| services/player_avatar_service.py | 1 | DOC-EPHEMERAL |

## Downstream Consumers
- IPT: инвариант INV-RE-CACHE-ALLOWLIST (CRITICAL; линтер-инвариант, лимит 15 симуляционных не расходует). IPT 50 → 51.
- Будущее: M2/D + GC-11 мигрируют DECISION-READER на V2-Store → сжатие allowlist через ценз-тач (обновление карты = запись в ADR).

## Runtime Impact
- Нулевой: рантайм не тронут; IPT-добавка O(файлов) grep, единицы мс.

## Sandbox Tests
- backend/tests/micro/test_re_cache_allowlist.py — 7/7: clean / growth / new-file / shrink / missing / baseline-pin (19/52) / real-tree-green (боевой прогон).
- Суд-прогон скрипта на живом дереве: независимое подтверждение baseline до интеграции (таблица архитектора стала фактом заморозки).

## Rollback
- Удалить scripts/lint_relationship_cache_allowlist.py + micro-тест; убрать inv_re_cache_allowlist из IPT (функция + строка INVARIANTS). Одиночная точка подключения, revert не ломает смежные инварианты.

## Граница решения
- GAP-1C (activation), α-design-question (модели A–D), GAP-4 (idle-store wiring), RE-D9 (BehaviorMask/fear-scale) — НЕ решались, владельцы по roadmap.
- Роли сайтов — документация заморозки, не enforcement.
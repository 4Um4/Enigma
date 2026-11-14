# ADR-O-443 Impact Audit

> Детальный аудит ОДНОГО ADR. Атлас: `docs/ADR (Architecture Decision Records).md`.
> Связанные: MEM-D10 (перспектива записи), MEM-D20 (5 belief-носителей), MEM-D17 (evidence), §16.10 (Memory Lifecycle, 3 запрета + GC-инвариант), ADR-O-307 (травма), ADR-O-413 (affection).
> Источник онтологии: `reports/MEM-0_ADR_DRAFT.md` (PROPOSED → APPROVED 2026-11-14, ветвь А).
> Коммит: **pending** — на момент публикации IMPACT ADR-O-443 не закоммичен.

## Статус — три независимых состояния

MEM-0 в трёх состояниях, не сливаются:

| Состояние | Вердикт | Что это значит |
|---|---|---|
| **ADR APPROVED** | **ДА** (2026-11-14, ветвь А) | Master утвердил онтологию. Документационный акт. |
| **IPT CONTRACT ENFORCED** | **НЕТ** | Отдельная инженерная фаза: ungated-инварианты §3.8 ещё не реализованы в `IPT.py`. |
| **MEM-0 CLOSED** | **НЕТ** | Требует APPROVED + ungated ENFORCED + **фактическое** прохождение MEM-GC-01. |

APPROVED — архитектурное одобрение онтологии и causal ownership. **Не означает реализации.** APPROVED не открывает код; CLOSED из APPROVED автоматически не следует.

## Контекст

Основание — §16.0 ROADMAP, §7.9 (MEM-D1…D43), §16.4 MEM-0 (6 подпунктов), §16.6 `MEM-ONT-1`, §16.10 (дополнение аудита 2026-10-23).

P0-дефекты (без их устранения верхние слои памяти строятся на песке; закрытие — MEM-1/MEM-2, не этот ADR):

- MEM-D1 — `day=0` у всех runtime-записей; в схеме нет tick/game_day; `created_at` — wall-clock, в модель не грузится.
- MEM-D3 — `apply_decay` только в RAM; LTM вечен; «забытое в сессии воскресает» при load.
- MEM-D5 — seq_0-коллизия: `sequence_id` никогда не присваивается → компрессия выметает весь кэш при первом сжатии — латентная деструкция.
- MEM-D20 — 5 belief-носителей без арбитра (BeliefState, CrystallizedBelief, ConclusionStore, EpistemicStore, MemoryCrystal).

## Changed Domains — архитектурная онтология (ничего не реализовано)

MEM-0 — контракт, не реализация. Вводимые онтологические принципы:

1. **MEM-INV-TRIPLE:** `WORLD TRUTH ≠ NPC MEMORY ≠ NPC BELIEF` — три уровня никогда не сливаются. Реконструкция/reconsolidation памяти не меняет WORLD TRUTH. Causal ownership каждого звена — в черновике §3.1.
2. **MEM-INV-FOUR-STATES:** `operational deletion` / `historical retention` / `irreversible destruction` — три уровня разведены. Tombstone — свидетельство, не исходная запись.
3. **Event Source ≠ Event Transport:** EventBus — транспорт, не SSOT. Authoritative Event Source — TBD/UNVERIFIED (кандидаты: TruthState / L1Chronicle / world-event-producer).
4. **Five belief-носителей:** pre-flight ownership-таблица (7 полей: Trait / Authoritative owner / Writer / Readers / Projection / Migration / Conflict policy). Принцип: один trait — один авторитетный владелец, не обязательно один физический Store.
5. **§16.10 три запрета + I4:** silent deletion prohibition; operational ≠ historical; consolidation ≠ fact; GC не создаёт фактов задним числом.
6. **15 IPT-инвариантов объявлены** (§3.8 черновика). Ungated — для следующих фаз; gated (2b, 6, 8-частично, 15) — MEM-3 / MEM-10.

**Ничего не реализовано.** Список выше — контрактные утверждения. Реализация — пакеты MEM-1…MEM-10.

## Согласованность с §16.10

| §16.10 | §16.1 | Отношение |
|---|---|---|
| P1 silent deletion | §16.1.3 / §16.1.11 | усиление |
| P2 operational ≠ historical | (новый контракт в §16.10) | не противоречит §16.1 |
| P3 consolidation ≠ fact | §16.1.1 TRIPLE | усиление |
| I4 GC no retrospective facts | §16.1.5 + CAUSAL_CONTRACT §10.4 | совпадение |

## Девять UNVERIFIED (технический долг следующих фаз)

| # | Вопрос | Где закрывается |
|---|---|---|
| U1 | Authoritative Event Source (TruthState / L1Chronicle / world-producer) | MEM-1 археология |
| U2 | Точный EventMemory schema delta (2 или N колонок) | MEM-1 археология SQLite |
| U3 | MigrationRunner API + идемпотентность | MEM-1 pre-flight |
| U4 | `contradiction_resolver` — grep `update_beliefs` / `resolve_all` | read-only шаг до MEM-3 |
| U5 | Ownership-таблица D20 — реальные traits × owners | MEM-3 pre-flight |
| U6 | MEM-3 ExperienceTrace — точка в BeliefCrystallization evidence-цепи | MEM-3 |
| U7 | MEM-GC-01 — фактическое прохождение гейта | MEM-1 → MEM-GC-01 |
| U8 | Калибровка (`decay_rate`, `×6`, `τ=100`, `importance≥0.9`) | MEM-10 / MATH-3 |
| U9 | Gated IPT-инварианты (2b, 6, 8-частично, 15) | Master + IPT |

**U7 — условие закрытия**, не доказательство существования: MEM-GC-01 предстоит подтвердить фактическим прохождением.

## Downstream — что будет зависеть после реализации

DecisionHub (npc_memory_modifiers) · BC-2…BC-7 · NL-1/NL-2/NL-3/NL-10 · CCH-02 RP-1 · RE-01 M2/D · LC-IMPL-4/5 · Body/EM · MATH-3/4 · HUM-09 · P14/P15/SCALE-03…07 · EPI-VER.

## Бюджет

- **MEM-0 ADR:** 0 (docs-only).
- **MEM-1** (следующий пакет, не в MEM-0): точная schema delta — UNVERIFIED. RAM/latency оценки — после MEM-1 археологии.
- **VRAM:** 0.

## Rollback

Docs-only. `git revert` коммита ADR-O-443 + IMPACT откатывает обе записи целиком. Схема, код, флаги не затронуты — откат ничего не восстанавливает, потому что нечего восстанавливать.

## Проверки — фактическое состояние на 2026-11-14

**MEM-0 не реализован, тестов нет, IPT для MEM-0 не гонялся.** Пять честных NOT:

- Реализация MEM-0 — **NOT IMPLEMENTED**.
- MEM-GC-01 (гейт закрытия) — **NOT VERIFIED** (гейт декларирован, фактическое прохождение pending).
- ungated IPT-инварианты — **NOT ENFORCED** (в `IPT.py` не реализованы).
- MEM-0 CLOSED — **NOT CLOSED** (требует ungated ENFORCED + MEM-GC-01).
- 15 IPT-инвариантов в §3.8 — **NOT DONE** (декларация для следующей фазы; в `IPT.py` их нет).

## Что запрещено приписывать этому ADR

- «MEM-0 реализован» — **нет**.
- «MEM-GC-01 пройден» — **нет**.
- «IPT 55/0/0 подтверждает MEM-0» — **нет** (baseline не менялся этим ADR; production-код не затронут).
- «ExperienceTrace активирован» — **нет** (отложено MEM-3, вариант C).
- «Ownership-таблица D20 заполнена» — **нет** (pre-flight для MEM-3).

## Источники

ROADMAP §16.0–16.10, §7.9 MEM-D1…D43, §9.3e MEM-GC-01…09, §16.4 MEM-0 (6 подпунктов), §16.6 ADR-кандидаты, CAUSAL_CONTRACT §10.4, ADR-O-307 (травма), ADR-O-413 (affection), ADR-O-441 (persistence). Черновик онтологии: `reports/MEM-0_ADR_DRAFT.md` (PROPOSED → APPROVED 2026-11-14).

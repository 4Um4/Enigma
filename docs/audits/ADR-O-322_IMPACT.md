# ADR-O-322 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-322` [STANDARD] **IMPACT**
# ADR-O-322 Impact Audit: Epistemology Machine Architecture
> Этот файл — детальный аудит онтологического сдвига. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- PERCEPTION & PHENOMENOLOGY
- FRONTEND, PRESENTATION & INPUT
- FOUNDATION

## Ontological Shift
Система официально переименована из "Игрового движка NPC" в "Машину Эпистемологии".
Введён универсальный паттерн для систем с неполной информацией:
`State → Manifestation → ObservationRelation → Signal → Fact → Hypothesis → Belief → Consumers`

## The 5 Invariants (НЕНАРУШИМЫ)
1. **Закон невозрастания истины:** Ни один слой не может увеличивать объём истины. Он может только терять информацию или преобразовывать её.
2. **Запрет каузального возврата:** `Inference` никогда не изменяет `Reality`. Он создаёт только гипотезы.
3. **Изоляция потребителей:** Любой потребитель (DM, Renderer, CDS, Replay) получает только эпистемическое представление, а не мир напрямую.
4. **Реляционная сущность:** `ObservationRelation` моделируется отдельным объектом, а не встраивается в объекты мира. Хранит только параметры среды, без ID, фракций и эмоций.
5. **Единственный мост:** `Manifestation` является единственным мостом между внутренним состоянием мира и внешне наблюдаемой физикой. Полностью immutable.

## Architecture (DAG)
- **Ось 1 (Каузальность):** Reality → Manifestation
- **Ось 2 (Эпистемология):** ObservationRelation → PerceivedSignal → ObservedFact → Inference → Memory
- **Потребители (Downstream):** PresentationAssembler, DMContractBuilder, CausalObserver.

## Rollback
Откат невозможен. Предыдущая линейная модель (Pipeline) признана хрупкой и убита.



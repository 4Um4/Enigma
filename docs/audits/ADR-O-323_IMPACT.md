# ADR-O-323 Impact Audit: Atomic Fact Extraction
> Этот файл — детальный аудит онтологического сдвига.

## Changed Domains
- PERCEPTION & PHENOMENOLOGY

## Ontological Shift
`ObservedFact` теперь строго атомарен. 
Составные выводы (например, `hand_on_weapon`) запрещены на уровне FactExtractor.
FactExtractor извлекает только атомарные сущности: `hand_position`, `weapon_visible`, `distance_to_observer`.
Сложные выводы и гипотезы выносятся в слой `Inference`.

## Rationale
Чем атомарнее FactExtractor, тем мощнее Inference. Составные факты ломают гибкость системы и заставляют FactExtractor делать предположения, что нарушает инвариант невозрастания истины.


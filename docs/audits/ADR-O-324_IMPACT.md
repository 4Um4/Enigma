# ADR-O-324 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-324` [STANDARD] **IMPACT**
# ADR-O-324 Impact Audit: ObservationRelation Contract
> Этот файл — детальный аудит онтологического сдвига.

## Changed Domains
- PERCEPTION & PHENOMENOLOGY

## Ontological Shift
`ObservationContext` переименован в `ObservationRelation` для жёсткого закрепления его природы.
Это объект *отношения* (observer × target + environment), а не сущность мира.

## Constraints
В `ObservationRelation` категорически запрещено класть:
- NPC id, Faction, Mood, Emotion, Quest, Memory.

Разрешено только:
- Параметры среды (lighting, weather, noise, occluders, motion blur).
- Геометрия (distance, angle).
- Оптика и тип наблюдателя.

Это предотвращает утечку истины мира в эпистемологию.


Files: N/A

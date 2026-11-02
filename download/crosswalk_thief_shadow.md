# Crosswalk: старый канон vs новый draft

- Старый канон: 39 записей
- Новый draft: 38 записей
- Строк crosswalk: 39

## Сводка по статусам

| Статус | Кол-во |
|--------|--------|
| PRESERVED | 1 |
| RECLASSIFIED | 7 |
| MERGED | 4 |
| DUPLICATED | 2 |
| LOST | 21 |
| AMBIGUOUS | 4 |

## Сводка по kind (только критичные: EFFECT, LOCATION, BELIEF_SEED)

### EFFECT

| Статус | Кол-во |
|--------|--------|
| AMBIGUOUS | 4 |
| LOST | 5 |
| MERGED | 1 |
| RECLASSIFIED | 3 |

### BELIEF_SEED

| Статус | Кол-во |
|--------|--------|
| LOST | 2 |
| MERGED | 1 |
| PRESERVED | 1 |
| RECLASSIFIED | 1 |

## LOST (полная потеря)

| ordinal | kind | summary |
|---------|------|---------|
| 400 | EVENT | гильдия послала его не убивать сразу — ни кого-то одного, ни всех: ему велено вы |
| 500 | EVENT | начало процесса проверки виновности |
| 501 | EFFECT | проверка Люси | Люси | task |
| 502 | EVENT | обнаружение информации о Гросбухе и его значении |
| 600 | RELATIONSHIP | Борко является начальником на городских воротах. | стражник Борко | dependence | |
| 601 | RELATIONSHIP | Тень может устранить стража Борко. | Тень | power | positive |
| 602 | EFFECT | Ей нужно доложить Тени о стражнике Борко. | guardianship |
| 702 | EFFECT | Тень прислали устранить гнома | Торнин Тень | gain |
| 703 | TRAIT_SEED | подозрительность | верить гному до конца не стоит |
| 704 | BELIEF_SEED |  |
| 705 | TRAIT_SEED | интерес | очень даже интересно |
| 900 | RELATIONSHIP | Борко Тень маленький человек. | Борко | dependence | negative |
| 902 | EVENT | Тень надеется, что Борко попадётся с поличным. |
| 1100 | EVENT | Орма Тень попросил лишь об одном: не вмешиваться. |
| 1200 | EVENT | Борко в последнее время слишком счастлив; так улыбаются, только если ждёт золото |
| 1201 | RELATIONSHIP | постоянных девушек у стражника гильдия проверяла — нет | стражник | dependence | |
| 1202 | EFFECT | значит, это он подговорил пьяного трактирщика напасть на гильдию и сдать всех ст |
| 1203 | RELATIONSHIP | постоянных девушек у стражника гильдия проверяла — нет | стражник | dependence | |
| 1204 | BELIEF_SEED | предатель — стражник |
| 1404 | EFFECT | его неуязвимость в этой сцене: его нельзя напоить, подкупить или купить | custom |
| 1405 | TRAIT_SEED | слабость | его единственная слабость в том, что он ошибается |

## AMBIGUOUS (неоднозначно)

| ordinal | kind | summary | candidates |
|---------|------|---------|-----------|
| 503 | EFFECT | задача Люси | постоянные клиенты таверны и владелец | task | 3 |
| 701 | EFFECT | гном сдал их властям и уже точит меч против них | Торнин Тень | loss | 3 |
| 1002 | EFFECT | Тень зафиксировал это в столбце «наблюдения»: купец либо должен и боится, либо ч | 2 |
| 1500 | EFFECT | Красный «Гросбух» сейчас в руках у Тени, ему поручили не только убийство, но и п | 3 |

## RECLASSIFIED (kind изменился)

| ordinal | old_kind | new_kind | old_summary | new_text |
|---------|----------|----------|-------------|----------|
| 2 | TRAIT_SEED | RELATIONSHIP | человек | Убийца гильdии воров, соглядатай: человек | Убийца гильдии воров, соглядатай | враждебный | negative |
| 700 | EVENT | RELATIONSHIP | Торнин Тень пришёл из гильдии | Тень рассказывает Люсе о плане гильдии | Тень |
| 901 | EFFECT | RELATIONSHIP | Тень предупредил Борко о грязи и зрелище ночью. | Борко | wa | Борко Тень предупредил Орма не приближаться к таверне ночью, |
| 1000 | BELIEF_SEED | RELATIONSHIP | долги гильдии — не его ремесло, он отвечает за убийства, а н | Тень отвечает за убийства в гильдии, а не за долги и вытряхи |
| 1400 | EVENT | PORTRET | сидит в тёмном углу, лицом к двери подвала | Сидит в тёмном углу, лицом к двери подвала — не потому, что  |
| 1402 | EFFECT | TRAIT_SEED | платит не глядя, отсчитывая больше, чем нужно | custom | платит не глядя | Платит не глядя, отсчитывая больше, чем ну |
| 1403 | EFFECT | RELATIONSHIP | единственный человек в этой таверне, которому от её посетите | Он единственный человек в этой таверне, которому от её посет |

## Полная таблица

| ordinal | kind | status | rationale |
|---------|------|--------|-----------|
| 0 | TRAIT_SEED | MERGED | meaning distributed across 2 new entries (top=0.57, 2nd=0.25) |
| 1 | TRAIT_SEED | MERGED | meaning distributed across 2 new entries (top=0.57, 2nd=0.25) |
| 2 | TRAIT_SEED | RECLASSIFIED | 1 match, kind changed: TRAIT_SEED → RELATIONSHIP |
| 100 | PORTRET | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.23) |
| 400 | EVENT | LOST | no semantic match (score < 0.2) |
| 500 | EVENT | LOST | no semantic match (score < 0.2) |
| 501 | EFFECT | LOST | no semantic match (score < 0.2) |
| 502 | EVENT | LOST | no semantic match (score < 0.2) |
| 503 | EFFECT | AMBIGUOUS | multiple candidates with close scores (top=0.23, 2nd=0.22) |
| 600 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 601 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 602 | EFFECT | LOST | no semantic match (score < 0.2) |
| 700 | EVENT | RECLASSIFIED | 1 match, kind changed: EVENT → RELATIONSHIP |
| 701 | EFFECT | AMBIGUOUS | multiple candidates with close scores (top=0.30, 2nd=0.26) |
| 702 | EFFECT | LOST | no semantic match (score < 0.2) |
| 703 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 704 | BELIEF_SEED | LOST | no semantic match (score < 0.2) |
| 705 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 800 | BELIEF_SEED | MERGED | meaning distributed across 3 new entries (top=1.00, 2nd=0.23) |
| 900 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 901 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → RELATIONSHIP |
| 902 | EVENT | LOST | no semantic match (score < 0.2) |
| 1000 | BELIEF_SEED | RECLASSIFIED | 1 match, kind changed: BELIEF_SEED → RELATIONSHIP |
| 1001 | OBSERVATION | DUPLICATED | >1 matches with same kind (top=0.60, 2nd=0.22) |
| 1002 | EFFECT | AMBIGUOUS | multiple candidates with close scores (top=0.37, 2nd=0.36) |
| 1100 | EVENT | LOST | no semantic match (score < 0.2) |
| 1200 | EVENT | LOST | no semantic match (score < 0.2) |
| 1201 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 1202 | EFFECT | LOST | no semantic match (score < 0.2) |
| 1203 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 1204 | BELIEF_SEED | LOST | no semantic match (score < 0.2) |
| 1300 | BELIEF_SEED | PRESERVED | 1 match, same kind (BELIEF_SEED) |
| 1400 | EVENT | RECLASSIFIED | 1 match, kind changed: EVENT → PORTRET |
| 1401 | EFFECT | MERGED | meaning distributed across 2 new entries (top=1.00, 2nd=0.68) |
| 1402 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → TRAIT_SEED |
| 1403 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → RELATIONSHIP |
| 1404 | EFFECT | LOST | no semantic match (score < 0.2) |
| 1405 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 1500 | EFFECT | AMBIGUOUS | multiple candidates with close scores (top=0.45, 2nd=0.36) |
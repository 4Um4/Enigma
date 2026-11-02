# Crosswalk: старый канон vs новый draft

- Старый канон: 63 записей
- Новый draft: 63 записей
- Строк crosswalk: 63

## Сводка по статусам

| Статус | Кол-во |
|--------|--------|
| PRESERVED | 38 |
| RECLASSIFIED | 0 |
| MERGED | 0 |
| DUPLICATED | 20 |
| LOST | 0 |
| AMBIGUOUS | 5 |

## Сводка по kind (только критичные: EFFECT, LOCATION, BELIEF_SEED)

### EFFECT

| Статус | Кол-во |
|--------|--------|
| DUPLICATED | 2 |
| PRESERVED | 13 |

### LOCATION

| Статус | Кол-во |
|--------|--------|
| DUPLICATED | 1 |
| PRESERVED | 2 |

### BELIEF_SEED

| Статус | Кол-во |
|--------|--------|
| DUPLICATED | 1 |
| PRESERVED | 6 |

## LOST (полная потеря)

| ordinal | kind | summary |
|---------|------|---------|

## AMBIGUOUS (неоднозначно)

| ordinal | kind | summary | candidates |
|---------|------|---------|-----------|
| 1503 | TRAIT_SEED | старая мебель | Орм — мебель этого города. Старая, полезная, которую никто не тр | 3 |
| 1504 | TRAIT_SEED | полезный | Орм — мебель этого города. Старая, полезная, которую никто не трогает | 3 |
| 1505 | TRAIT_SEED | не трогаемый | Орм — мебель этого города. Старая, полезная, которую никто не тро | 3 |
| 1507 | TRAIT_SEED | не герой | Орм не герой и не предатель. | 3 |
| 1508 | TRAIT_SEED | не предатель | Орм не герой и не предатель. | 3 |

## RECLASSIFIED (kind изменился)

| ordinal | old_kind | new_kind | old_summary | new_text |
|---------|----------|----------|-------------|----------|

## Полная таблица

| ordinal | kind | status | rationale |
|---------|------|--------|-----------|
| 0 | LOCATION | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.20) |
| 100 | EFFECT | PRESERVED | 1 match, same kind (EFFECT) |
| 200 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 201 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 300 | RELATIONSHIP | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.22) |
| 301 | EVENT | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.20) |
| 500 | EVENT | PRESERVED | 1 match, same kind (EVENT) |
| 501 | EFFECT | PRESERVED | 1 match, same kind (EFFECT) |
| 502 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 600 | EFFECT | PRESERVED | 1 match, same kind (EFFECT) |
| 700 | EVENT | PRESERVED | 1 match, same kind (EVENT) |
| 800 | TRAIT_SEED | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.78) |
| 801 | TRAIT_SEED | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.78) |
| 802 | TRAIT_SEED | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.78) |
| 803 | RELATIONSHIP | PRESERVED | 1 match, same kind (RELATIONSHIP) |
| 804 | BELIEF_SEED | PRESERVED | 1 match, same kind (BELIEF_SEED) |
| 1000 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 1100 | BELIEF_SEED | PRESERVED | 1 match, same kind (BELIEF_SEED) |
| 1200 | EVENT | PRESERVED | 1 match, same kind (EVENT) |
| 1300 | EVENT | PRESERVED | 1 match, same kind (EVENT) |
| 1400 | BELIEF_SEED | PRESERVED | 1 match, same kind (BELIEF_SEED) |
| 1500 | EVENT | PRESERVED | 1 match, same kind (EVENT) |
| 1501 | RELATIONSHIP | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.71) |
| 1502 | RELATIONSHIP | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.71) |
| 1503 | TRAIT_SEED | AMBIGUOUS | multiple candidates with close scores (top=1.00, 2nd=1.00) |
| 1504 | TRAIT_SEED | AMBIGUOUS | multiple candidates with close scores (top=1.00, 2nd=1.00) |
| 1505 | TRAIT_SEED | AMBIGUOUS | multiple candidates with close scores (top=1.00, 2nd=1.00) |
| 1506 | TRAIT_SEED | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.32) |
| 1507 | TRAIT_SEED | AMBIGUOUS | multiple candidates with close scores (top=1.00, 2nd=1.00) |
| 1508 | TRAIT_SEED | AMBIGUOUS | multiple candidates with close scores (top=1.00, 2nd=1.00) |
| 1509 | PORTRET | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.74) |
| 1600 | BELIEF_SEED | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.21) |
| 1601 | RELATIONSHIP | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.43) |
| 1602 | RELATIONSHIP | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.43) |
| 1603 | EFFECT | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.75) |
| 1604 | EFFECT | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.75) |
| 1605 | EFFECT | PRESERVED | 1 match, same kind (EFFECT) |
| 1606 | BELIEF_SEED | PRESERVED | 1 match, same kind (BELIEF_SEED) |
| 1607 | EFFECT | PRESERVED | 1 match, same kind (EFFECT) |
| 1700 | RELATIONSHIP | PRESERVED | 1 match, same kind (RELATIONSHIP) |
| 1701 | EFFECT | PRESERVED | 1 match, same kind (EFFECT) |
| 1702 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 1703 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 1704 | EFFECT | PRESERVED | 1 match, same kind (EFFECT) |
| 1705 | BELIEF_SEED | PRESERVED | 1 match, same kind (BELIEF_SEED) |
| 1800 | LOCATION | PRESERVED | 1 match, same kind (LOCATION) |
| 1801 | EFFECT | PRESERVED | 1 match, same kind (EFFECT) |
| 1802 | EFFECT | PRESERVED | 1 match, same kind (EFFECT) |
| 1803 | TRAIT_SEED | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.32) |
| 1804 | BELIEF_SEED | PRESERVED | 1 match, same kind (BELIEF_SEED) |
| 1900 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 1901 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 1902 | RELATIONSHIP | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.22) |
| 1903 | RELATIONSHIP | PRESERVED | 1 match, same kind (RELATIONSHIP) |
| 1904 | RELATIONSHIP | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.20) |
| 2000 | PORTRET | PRESERVED | 1 match, same kind (PORTRET) |
| 2100 | EFFECT | PRESERVED | 1 match, same kind (EFFECT) |
| 2101 | EFFECT | PRESERVED | 1 match, same kind (EFFECT) |
| 2102 | EFFECT | PRESERVED | 1 match, same kind (EFFECT) |
| 2103 | TRAIT_SEED | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.50) |
| 2104 | LOCATION | PRESERVED | 1 match, same kind (LOCATION) |
| 2105 | EFFECT | PRESERVED | 1 match, same kind (EFFECT) |
| 2106 | TRAIT_SEED | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.50) |
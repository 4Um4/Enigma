# Crosswalk: старый канон vs новый draft

- Старый канон: 63 записей
- Новый draft: 62 записей
- Строк crosswalk: 63

## Сводка по статусам

| Статус | Кол-во |
|--------|--------|
| PRESERVED | 9 |
| RECLASSIFIED | 26 |
| MERGED | 3 |
| DUPLICATED | 3 |
| LOST | 17 |
| AMBIGUOUS | 5 |

## Сводка по kind (только критичные: EFFECT, LOCATION, BELIEF_SEED)

### EFFECT

| Статус | Кол-во |
|--------|--------|
| AMBIGUOUS | 1 |
| LOST | 4 |
| PRESERVED | 1 |
| RECLASSIFIED | 9 |

### LOCATION

| Статус | Кол-во |
|--------|--------|
| LOST | 2 |
| RECLASSIFIED | 1 |

### BELIEF_SEED

| Статус | Кол-во |
|--------|--------|
| AMBIGUOUS | 1 |
| LOST | 1 |
| MERGED | 1 |
| RECLASSIFIED | 4 |

## LOST (полная потеря)

| ordinal | kind | summary |
|---------|------|---------|
| 201 | TRAIT_SEED | пьянство | и выпивкой |
| 300 | RELATIONSHIP | напоминает старого друга | Торнин | идеализация | positive |
| 301 | EVENT | умершего 70 лет назад |
| 803 | RELATIONSHIP | перенос | его жена | dependence | negative |
| 1100 | BELIEF_SEED | Только перед Торниным его грызла совесть: тот хоть и бил девочку, но по-своему х |
| 1501 | RELATIONSHIP | Гильдия терпит Орма. | Орм | dependence | positive |
| 1602 | RELATIONSHIP | дальний родственник | Торнин | привязанность | positive |
| 1607 | EFFECT | спрятал сожаление о Торнине | сожаление о Торнине | secret |
| 1700 | RELATIONSHIP | Борко не имеет власти над Ормом. | Орм | dependence | negative |
| 1800 | LOCATION | Крыша. |
| 1801 | EFFECT | принадлежащая Торнину и оплаченная молчанием и починкой утвари. | residence |
| 1904 | RELATIONSHIP | лучший слушатель из всех возможных | собутыльник | superiority | positive |
| 2100 | EFFECT | руки и речь | trauma |
| 2103 | TRAIT_SEED | старый | 57 лет привычки |
| 2104 | LOCATION | кузнице |
| 2105 | EFFECT | спит на лежанке у остывающего горна | residence |
| 2106 | TRAIT_SEED | привычный | 57 лет привычки |

## AMBIGUOUS (неоднозначно)

| ordinal | kind | summary | candidates |
|---------|------|---------|-----------|
| 100 | EFFECT | из которых он кузнец в городе уже 57 лет. | occupation | 3 |
| 1502 | RELATIONSHIP | Правительство терпит Орма. | Орм | dependence | positive | 2 |
| 1506 | TRAIT_SEED | не молчит | Орм это знает. Поэтому он говорит и тем и другим. Не из хитрости. Из | 2 |
| 1509 | PORTRET | Орм — мебель этого города. | 3 |
| 1606 | BELIEF_SEED | гном привык хранить многое | 2 |

## RECLASSIFIED (kind изменился)

| ordinal | old_kind | new_kind | old_summary | new_text |
|---------|----------|----------|-------------|----------|
| 0 | LOCATION | TRAIT_SEED | кузнец Орм: гном | Орм | гном | кузнец Орм: гном |
| 500 | EVENT | RELATIONSHIP | Писарь сидит на содержании гильдии второй десяток лет. | Писарь на содержании гильдии | мелкий чиновник |
| 501 | EFFECT | EVENT | Мастер гильдии знал о предупреждении слово в слово и от кого | Мастер гильдии узнал о предупреждении |
| 600 | EFFECT | EVENT | учился кузнечному делу | skill | учился кузнечному делу у мастера Грунта | game_start_age - y |
| 800 | TRAIT_SEED | PORTRET | тихая | Орм давно заприметил Люсю — тихую, серьёзную и испол | Орм давно заприметил Люсю — тихую, серьёзную и исполнительну |
| 801 | TRAIT_SEED | PORTRET | серьёзная | Орм давно заприметил Люсю — тихую, серьёзную и и | Орм давно заприметил Люсю — тихую, серьёзную и исполнительну |
| 802 | TRAIT_SEED | PORTRET | исполнительная | Орм давно заприметил Люсю — тихую, серьёзну | Орм давно заприметил Люсю — тихую, серьёзную и исполнительну |
| 804 | BELIEF_SEED | PORTRET | Орм в себе так и не разглядел перенос, потому что разглядыва | Орм привык хранить в себе многое. И это тоже спрятал. |
| 1200 | EVENT | TRAIT_SEED | Горан понял, что заказ Торнина можно продать купцу. | продавец информации | гном понял: заказ Торнина можно продат |
| 1300 | EVENT | PORTRET | он не насилует Люсю, а видит её в таверне | Когда он не насилует Люсю, а видит её в таверне, испытывает  |
| 1400 | BELIEF_SEED | TRAIT_SEED | Орм думает, когда всё закончится, получить оплату за информа | думает получить оплату | думает получить оплату за информаци |
| 1500 | EVENT | PORTRET | Орм пережил трёх старейшин Гильдии, двух капитанов стражи и  | Баланс Орма между Гильдией воров и городским правительством  |
| 1503 | TRAIT_SEED | EVENT | старая мебель | Орм — мебель этого города. Старая, полезная, | Орм предупредит городское правительство о Торнине |
| 1504 | TRAIT_SEED | EVENT | полезный | Орм — мебель этого города. Старая, полезная, кото | Орм предупредит городское правительство о Торнине |
| 1505 | TRAIT_SEED | EVENT | не трогаемый | Орм — мебель этого города. Старая, полезная,  | Орм предупредит городское правительство о Торнине |
| 1603 | EFFECT | EVENT | предупредил Гильдию, чтобы не винить кузнеца | Торнин | guar | Орм предупредил Гильдию о Торнине |
| 1604 | EFFECT | EVENT | предупредил правительство, чтобы не винить кузнеца | Торнин  | Орм предупредил правительство о Торнине |
| 1701 | EFFECT | RELATIONSHIP | Орм не испугался шантажа стражника. | gain | Орм не испугался шантажа стражника Борко, понял что это разр |
| 1704 | EFFECT | RELATIONSHIP | Орм просто пользуется Борко как инструментом для собственног | Орм пользуется стражником Борко как инструментом для собстве |
| 1705 | BELIEF_SEED | TRAIT_SEED | Борко думает, что он хозяин. | думает получить оплату | думает получить оплату за информаци |
| 1802 | EFFECT | RELATIONSHIP | угроза Борко «посажу и сдам Торнину» бьёт не по самолюбию, а | угроза Борко "посаду и сдам Торнину" | Борко | враждебное пр |
| 1804 | BELIEF_SEED | DESIRE_SEED | его мечта о собственной кузне (п.14) — не про статус, а про  | его мечта о собственной кузне (п.14) — не про статус, а про  |
| 1902 | RELATIONSHIP | TRAIT_SEED | поддерживает застолье | собутыльник | dependence | positive | поддерживает застолье | один поддерживает застолье, другой в |
| 1903 | RELATIONSHIP | TRAIT_SEED | выключается из него | собутыльник | disengagement | neutral | поддерживает застолье | один поддерживает застолье, другой в |
| 2101 | EFFECT | TRAIT_SEED | говорит односложно: «Да». «Нет». «Жди». | loss | говорит односложно | Говорит односложно: «Да». "Нет". "Жди". |
| 2102 | EFFECT | TRAIT_SEED | матерится только по-гномьи | trauma | матерится по-гномьи | Матерится только по-гномьи — зал не по |

## Полная таблица

| ordinal | kind | status | rationale |
|---------|------|--------|-----------|
| 0 | LOCATION | RECLASSIFIED | 1 match, kind changed: LOCATION → TRAIT_SEED |
| 100 | EFFECT | AMBIGUOUS | multiple candidates with close scores (top=0.25, 2nd=0.21) |
| 200 | TRAIT_SEED | DUPLICATED | >1 matches with same kind (top=0.83, 2nd=0.62) |
| 201 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 300 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 301 | EVENT | LOST | no semantic match (score < 0.2) |
| 500 | EVENT | RECLASSIFIED | 1 match, kind changed: EVENT → RELATIONSHIP |
| 501 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → EVENT |
| 502 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 600 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → EVENT |
| 700 | EVENT | PRESERVED | 1 match, same kind (EVENT) |
| 800 | TRAIT_SEED | RECLASSIFIED | 1 match, kind changed: TRAIT_SEED → PORTRET |
| 801 | TRAIT_SEED | RECLASSIFIED | 1 match, kind changed: TRAIT_SEED → PORTRET |
| 802 | TRAIT_SEED | RECLASSIFIED | 1 match, kind changed: TRAIT_SEED → PORTRET |
| 803 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 804 | BELIEF_SEED | RECLASSIFIED | 1 match, kind changed: BELIEF_SEED → PORTRET |
| 1000 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 1100 | BELIEF_SEED | LOST | no semantic match (score < 0.2) |
| 1200 | EVENT | RECLASSIFIED | 1 match, kind changed: EVENT → TRAIT_SEED |
| 1300 | EVENT | RECLASSIFIED | 1 match, kind changed: EVENT → PORTRET |
| 1400 | BELIEF_SEED | RECLASSIFIED | 1 match, kind changed: BELIEF_SEED → TRAIT_SEED |
| 1500 | EVENT | RECLASSIFIED | 1 match, kind changed: EVENT → PORTRET |
| 1501 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 1502 | RELATIONSHIP | AMBIGUOUS | multiple candidates with close scores (top=0.25, 2nd=0.22) |
| 1503 | TRAIT_SEED | RECLASSIFIED | 1 match, kind changed: TRAIT_SEED → EVENT |
| 1504 | TRAIT_SEED | RECLASSIFIED | 1 match, kind changed: TRAIT_SEED → EVENT |
| 1505 | TRAIT_SEED | RECLASSIFIED | 1 match, kind changed: TRAIT_SEED → EVENT |
| 1506 | TRAIT_SEED | AMBIGUOUS | multiple candidates with close scores (top=0.28, 2nd=0.26) |
| 1507 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 1508 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 1509 | PORTRET | AMBIGUOUS | multiple candidates with close scores (top=0.28, 2nd=0.22) |
| 1600 | BELIEF_SEED | MERGED | meaning distributed across 2 new entries (top=0.88, 2nd=0.24) |
| 1601 | RELATIONSHIP | PRESERVED | 1 match, same kind (RELATIONSHIP) |
| 1602 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 1603 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → EVENT |
| 1604 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → EVENT |
| 1605 | EFFECT | PRESERVED | 1 match, same kind (EFFECT) |
| 1606 | BELIEF_SEED | AMBIGUOUS | multiple candidates with close scores (top=0.43, 2nd=0.33) |
| 1607 | EFFECT | LOST | no semantic match (score < 0.2) |
| 1700 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 1701 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → RELATIONSHIP |
| 1702 | TRAIT_SEED | MERGED | meaning distributed across 4 new entries (top=1.00, 2nd=0.45) |
| 1703 | TRAIT_SEED | DUPLICATED | >1 matches with same kind (top=0.62, 2nd=0.32) |
| 1704 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → RELATIONSHIP |
| 1705 | BELIEF_SEED | RECLASSIFIED | 1 match, kind changed: BELIEF_SEED → TRAIT_SEED |
| 1800 | LOCATION | LOST | no semantic match (score < 0.2) |
| 1801 | EFFECT | LOST | no semantic match (score < 0.2) |
| 1802 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → RELATIONSHIP |
| 1803 | TRAIT_SEED | MERGED | meaning distributed across 3 new entries (top=1.00, 2nd=0.26) |
| 1804 | BELIEF_SEED | RECLASSIFIED | 1 match, kind changed: BELIEF_SEED → DESIRE_SEED |
| 1900 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 1901 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 1902 | RELATIONSHIP | RECLASSIFIED | 1 match, kind changed: RELATIONSHIP → TRAIT_SEED |
| 1903 | RELATIONSHIP | RECLASSIFIED | 1 match, kind changed: RELATIONSHIP → TRAIT_SEED |
| 1904 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 2000 | PORTRET | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.26) |
| 2100 | EFFECT | LOST | no semantic match (score < 0.2) |
| 2101 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → TRAIT_SEED |
| 2102 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → TRAIT_SEED |
| 2103 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 2104 | LOCATION | LOST | no semantic match (score < 0.2) |
| 2105 | EFFECT | LOST | no semantic match (score < 0.2) |
| 2106 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
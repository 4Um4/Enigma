# Crosswalk: старый канон vs новый draft

- Старый канон: 78 записей
- Новый draft: 55 записей
- Строк crosswalk: 78

## Сводка по статусам

| Статус | Кол-во |
|--------|--------|
| PRESERVED | 11 |
| RECLASSIFIED | 28 |
| MERGED | 7 |
| DUPLICATED | 2 |
| LOST | 29 |
| AMBIGUOUS | 1 |

## Сводка по kind (только критичные: EFFECT, LOCATION, BELIEF_SEED)

### EFFECT

| Статус | Кол-во |
|--------|--------|
| LOST | 9 |
| MERGED | 2 |
| RECLASSIFIED | 13 |

### BELIEF_SEED

| Статус | Кол-во |
|--------|--------|
| LOST | 2 |
| MERGED | 1 |
| RECLASSIFIED | 1 |

## LOST (полная потеря)

| ordinal | kind | summary |
|---------|------|---------|
| 0 | PORTRET | человек |
| 1000 | EFFECT | привело к алкоголизму | trauma |
| 1200 | EVENT | ударила по его финансам |
| 1201 | EFFECT | его отношение к ней стало крайне недоброжелательным | loss |
| 1202 | RELATIONSHIP | отношение было недоброжелательным | девочка | inimical | negative |
| 1203 | RELATIONSHIP | ее прислали следить за ним | гильдия | dependence | negative |
| 1301 | EFFECT | дело закрыли тихо, через Борко, которому приказали «драки не было». | loss |
| 1302 | EFFECT | долг и вырос так резко, без объяснений. | должник | gain |
| 1401 | EFFECT | посчитал это недобрым знаком («стража идёт, жизнь кончена») | belief_seed |
| 1403 | EFFECT | бросил на её кровать, как мешок с картофелем | Люся | state |
| 1404 | EVENT | вырубился на своей кровати |
| 1903 | EFFECT | не может уйти | residence |
| 1904 | BELIEF_SEED | узнай Гильдия, что заказ от Торнина, от него незамедлительно избавятся |
| 2001 | RELATIONSHIP | не доверяет | Орму | 不信任 | negative |
| 2003 | RELATIONSHIP | продаст Торнина за бутылку | Орму | 交易 | negative |
| 2101 | TRAIT_SEED | бывший солдат | одна его часть — бывший солдат |
| 2103 | TRAIT_SEED | ненавидит себя | эта часть ненавидит себя за то, что он бьёт девочку |
| 2105 | TRAIT_SEED | ненавидит себя | эта часть ненавидит себя за то, что продал себя Гильдии за лаз  |
| 2106 | TRAIT_SEED | пьёт | другая часть — та, что пьёт |
| 2107 | TRAIT_SEED | бьёт | другая часть — та, что бьёт |
| 2108 | TRAIT_SEED | смотрит на Люсю и видит в ней причину всех бед | другая часть — та, что смотрит  |
| 2110 | EFFECT | эти две части не разговаривают друг с другом. | conflict |
| 2401 | TRAIT_SEED | подумает | Я подумаю |
| 2402 | BELIEF_SEED | Орм — собутыльник, а хоронить товарища по стойке — это уже не клетка, это могила |
| 2404 | TRAIT_SEED | спорят каждую смену | спорят каждую смену |
| 2500 | EVENT | Орму нужно ещё две-три недели. |
| 2503 | EVENT | через его подвал пройдёт Гросбух |
| 2504 | EFFECT | будет готова сталь, в которой он видит своё спасение. | сталь | gain |
| 2602 | TRAIT_SEED | привычка встречать рассвет на ногах | Солдат в нём не умер — даже запойный, он п |

## AMBIGUOUS (неоднозначно)

| ordinal | kind | summary | candidates |
|---------|------|---------|-----------|
| 2104 | TRAIT_SEED | ненавидит себя | эта часть ненавидит себя за то, что убил двоих и не сдался стра | 3 |

## RECLASSIFIED (kind изменился)

| ordinal | old_kind | new_kind | old_summary | new_text |
|---------|----------|----------|-------------|----------|
| 200 | EFFECT | TRAIT_SEED | отстранена от службы из-за травмы ноги | trauma | прихрамывает | отстранён от службы из-за травмы ноги |
| 300 | PORTRET | TRAIT_SEED | На момент игры ему 45 лет. | возраст | На момент игры ему 45 лет |
| 500 | EVENT | DESIRE_SEED | решено купить таверну | купить таверну | собственная таверна |
| 700 | EFFECT | EVENT | гильдия выделила ему неприличную сумму | gain | Гильдия выделила ему неприличную сумму за договоренность пос |
| 801 | EFFECT | TRAIT_SEED | он не завёл новых близких связей | loss | отсутствие новых близких связей | не завёл новых близких свя |
| 1400 | EVENT | DESIRE_SEED | вернулся в таверну после драки | купить таверну | собственная таверна |
| 1600 | EFFECT | EVENT | долг возрос ещё больше | loss | Гильдия сказала, что долг возрос ещё больше и что, если дево |
| 1601 | EFFECT | EVENT | если девочка умрёт, это будет считаться нападением на саму г | Гильдия сказала, что долг возрос ещё больше и что, если дево |
| 1602 | EFFECT | RELATIONSHIP | Торнин неделю сам кормил и выхаживал её | девочка | care | Торнин неделю сам кормил и выхаживал её — и понял, что Гильд |
| 1603 | EFFECT | RELATIONSHIP | понял, что Гильдия надавила и на стражу | стражу | realizati | Торнин неделю сам кормил и выхаживал её — и понял, что Гильд |
| 1604 | EFFECT | RELATIONSHIP | его жизнь ещё меньше принадлежит ему | loss_of_control | Торнин неделю сам кормил и выхаживал её — и понял, что Гильд |
| 1800 | EVENT | RELATIONSHIP | Торнин собирается убить Люсю и других членов гильдии. | Торнин собирается убить Люсю и других членов гильдии, потому |
| 1901 | EFFECT | PORTRET | остается работать, пить и выплачивать долги | loss | Он понимает, что это самообман: даже когда меч будет выкован |
| 1902 | TRAIT_SEED | PORTRET | побоится | даже когда меч будет выкован, он побоится им восп | Он понимает, что это самообман: даже когда меч будет выкован |
| 1905 | TRAIT_SEED | EFFECT | надо от него избавиться | если им не воспользоваться, надо о | меч стал новой петлёй: если им не воспользоваться, надо от н |
| 2005 | RELATIONSHIP | TRAIT_SEED | более подозрительный, чем Люся | Борко | 怀疑 | negative | подозрительный | Борко — продажный стражник, ещё более подоз |
| 2007 | RELATIONSHIP | TRAIT_SEED | обращается к Борко при драках или спорных случаях | Торнин | | обращается к Борко при драках или спорных случаях | Торнин с |
| 2008 | RELATIONSHIP | TRAIT_SEED | связаны с гильдией | Борко и Торнин | 联系 | neutral | обращается к Борко при драках или спорных случаях | Торнин с |
| 2109 | TRAIT_SEED | PORTRET | проще, чем видеть причину в себе | другая часть — та, что см | Психика Торнина за годы алкоголизма приобрела двойственную с |
| 2111 | EFFECT | PORTRET | они существуют параллельно, сменяясь в зависимости от того,  | Психика Торнина за годы алкоголизма приобрела двойственную с |
| 2300 | EVENT | PORTRET | Заказ меча | Заказ меча не был планом. Не был расчётом. Не был решением. |
| 2400 | EVENT | RELATIONSHIP | Торнин не ответил на предложение Тени о прощении долгов за п | Торнин не говорит однозначно на предложение Тени, но соглаша |
| 2403 | EFFECT | PORTRET | Внутри Торнина спорят две части его сознания. | conflict | внутри него спорят две части: пьяная и трезвая; исход спора  |
| 2405 | EFFECT | PORTRET | Исход спора зависит от количества выпитого Торниным перед те | внутри него спорят две части: пьяная и трезвая; исход спора  |
| 2505 | EFFECT | BELIEF_SEED | часы сцены тикают быстрее его плана | loss | часы сцены тикают быстрее его плана | danger |
| 2600 | TRAIT_SEED | PORTRET | строгость | Трезвый Торнин протирает стойку строевыми ровным | Трезвый Торнин протирает стойку строевыми ровными движениями |
| 2601 | TRAIT_SEED | PORTRET | хромота | Пьяный гоняет полотенце по одному и тому же месту  | Трезвый Торнин протирает стойку строевыми ровными движениями |
| 2603 | BELIEF_SEED | RELATIONSHIP | армия подготовила его к осаде, а не к жизни в кредит. | Торнин Серебряная Луна — солдат, подготовленный к осаде, но  |

## Полная таблица

| ordinal | kind | status | rationale |
|---------|------|--------|-----------|
| 0 | PORTRET | LOST | no semantic match (score < 0.2) |
| 100 | EFFECT | MERGED | meaning distributed across 2 new entries (top=0.82, 2nd=0.26) |
| 200 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → TRAIT_SEED |
| 300 | PORTRET | RECLASSIFIED | 1 match, kind changed: PORTRET → TRAIT_SEED |
| 400 | EVENT | PRESERVED | 1 match, same kind (EVENT) |
| 500 | EVENT | RECLASSIFIED | 1 match, kind changed: EVENT → DESIRE_SEED |
| 600 | EVENT | DUPLICATED | >1 matches with same kind (top=0.65, 2nd=0.26) |
| 700 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → EVENT |
| 800 | EVENT | PRESERVED | 1 match, same kind (EVENT) |
| 801 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → TRAIT_SEED |
| 900 | EVENT | PRESERVED | 1 match, same kind (EVENT) |
| 1000 | EFFECT | LOST | no semantic match (score < 0.2) |
| 1100 | EVENT | PRESERVED | 1 match, same kind (EVENT) |
| 1200 | EVENT | LOST | no semantic match (score < 0.2) |
| 1201 | EFFECT | LOST | no semantic match (score < 0.2) |
| 1202 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 1203 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 1300 | EVENT | MERGED | meaning distributed across 5 new entries (top=1.00, 2nd=0.65) |
| 1301 | EFFECT | LOST | no semantic match (score < 0.2) |
| 1302 | EFFECT | LOST | no semantic match (score < 0.2) |
| 1400 | EVENT | RECLASSIFIED | 1 match, kind changed: EVENT → DESIRE_SEED |
| 1401 | EFFECT | LOST | no semantic match (score < 0.2) |
| 1402 | EVENT | PRESERVED | 1 match, same kind (EVENT) |
| 1403 | EFFECT | LOST | no semantic match (score < 0.2) |
| 1404 | EVENT | LOST | no semantic match (score < 0.2) |
| 1500 | EFFECT | MERGED | meaning distributed across 2 new entries (top=1.00, 2nd=0.23) |
| 1600 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → EVENT |
| 1601 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → EVENT |
| 1602 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → RELATIONSHIP |
| 1603 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → RELATIONSHIP |
| 1604 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → RELATIONSHIP |
| 1700 | EVENT | PRESERVED | 1 match, same kind (EVENT) |
| 1800 | EVENT | RECLASSIFIED | 1 match, kind changed: EVENT → RELATIONSHIP |
| 1900 | BELIEF_SEED | MERGED | meaning distributed across 2 new entries (top=1.00, 2nd=0.27) |
| 1901 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → PORTRET |
| 1902 | TRAIT_SEED | RECLASSIFIED | 1 match, kind changed: TRAIT_SEED → PORTRET |
| 1903 | EFFECT | LOST | no semantic match (score < 0.2) |
| 1904 | BELIEF_SEED | LOST | no semantic match (score < 0.2) |
| 1905 | TRAIT_SEED | RECLASSIFIED | 1 match, kind changed: TRAIT_SEED → EFFECT |
| 2000 | RELATIONSHIP | PRESERVED | 1 match, same kind (RELATIONSHIP) |
| 2001 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 2002 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 2003 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 2004 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 2005 | RELATIONSHIP | RECLASSIFIED | 1 match, kind changed: RELATIONSHIP → TRAIT_SEED |
| 2006 | TRAIT_SEED | MERGED | meaning distributed across 2 new entries (top=0.47, 2nd=0.33) |
| 2007 | RELATIONSHIP | RECLASSIFIED | 1 match, kind changed: RELATIONSHIP → TRAIT_SEED |
| 2008 | RELATIONSHIP | RECLASSIFIED | 1 match, kind changed: RELATIONSHIP → TRAIT_SEED |
| 2100 | PORTRET | MERGED | meaning distributed across 2 new entries (top=1.00, 2nd=0.40) |
| 2101 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 2102 | TRAIT_SEED | MERGED | meaning distributed across 2 new entries (top=0.61, 2nd=0.28) |
| 2103 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 2104 | TRAIT_SEED | AMBIGUOUS | multiple candidates with close scores (top=0.30, 2nd=0.29) |
| 2105 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 2106 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 2107 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 2108 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 2109 | TRAIT_SEED | RECLASSIFIED | 1 match, kind changed: TRAIT_SEED → PORTRET |
| 2110 | EFFECT | LOST | no semantic match (score < 0.2) |
| 2111 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → PORTRET |
| 2300 | EVENT | RECLASSIFIED | 1 match, kind changed: EVENT → PORTRET |
| 2400 | EVENT | RECLASSIFIED | 1 match, kind changed: EVENT → RELATIONSHIP |
| 2401 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 2402 | BELIEF_SEED | LOST | no semantic match (score < 0.2) |
| 2403 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → PORTRET |
| 2404 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 2405 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → PORTRET |
| 2500 | EVENT | LOST | no semantic match (score < 0.2) |
| 2501 | EVENT | PRESERVED | 1 match, same kind (EVENT) |
| 2502 | RELATIONSHIP | PRESERVED | 1 match, same kind (RELATIONSHIP) |
| 2503 | EVENT | LOST | no semantic match (score < 0.2) |
| 2504 | EFFECT | LOST | no semantic match (score < 0.2) |
| 2505 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → BELIEF_SEED |
| 2600 | TRAIT_SEED | RECLASSIFIED | 1 match, kind changed: TRAIT_SEED → PORTRET |
| 2601 | TRAIT_SEED | RECLASSIFIED | 1 match, kind changed: TRAIT_SEED → PORTRET |
| 2602 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 2603 | BELIEF_SEED | RECLASSIFIED | 1 match, kind changed: BELIEF_SEED → RELATIONSHIP |
| 2700 | PORTRET | DUPLICATED | >1 matches with same kind (top=0.73, 2nd=0.23) |
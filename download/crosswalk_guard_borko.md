# Crosswalk: старый канон vs новый draft

- Старый канон: 66 записей
- Новый draft: 67 записей
- Строк crosswalk: 66

## Сводка по статусам

| Статус | Кол-во |
|--------|--------|
| PRESERVED | 8 |
| RECLASSIFIED | 20 |
| MERGED | 4 |
| DUPLICATED | 4 |
| LOST | 26 |
| AMBIGUOUS | 4 |

## Сводка по kind (только критичные: EFFECT, LOCATION, BELIEF_SEED)

### EFFECT

| Статус | Кол-во |
|--------|--------|
| LOST | 6 |
| MERGED | 3 |
| RECLASSIFIED | 8 |

### LOCATION

| Статус | Кол-во |
|--------|--------|
| AMBIGUOUS | 1 |
| PRESERVED | 1 |

### BELIEF_SEED

| Статус | Кол-во |
|--------|--------|
| AMBIGUOUS | 1 |
| LOST | 1 |
| PRESERVED | 1 |
| RECLASSIFIED | 4 |

## LOST (полная потеря)

| ordinal | kind | summary |
|---------|------|---------|
| 1100 | EVENT | познакомился с Гораном |
| 1200 | EVENT | Возрастные якоря фрагмента: [24]. В 24 застал изнасилование Люси Ормом |
| 1300 | EVENT | застал насилие |
| 1303 | EVENT | решился подсесть за стол к Орму и заявил, что посадит его и сдаст Торнину |
| 1304 | RELATIONSHIP | не будет сообщать ему заранее, когда снова будет насиловать Люсю | Орм | conditi |
| 1305 | EVENT | предложил прекратить насильство |
| 1306 | EFFECT | его жизнь тут же будет закончена | жизнь Борко | loss |
| 1900 | EVENT | По долгу службы орудует копьем на начальном уровне. |
| 2001 | RELATIONSHIP | не зарился на ЕГО Люсю! | Тень | protection | positive |
| 2101 | RELATIONSHIP | Борко боится потерять работу. | Гильдия воров | fear | negative |
| 2103 | EFFECT | Борко подписывает документы и говорит, что драка закончилась ничем. | action |
| 2202 | TRAIT_SEED | заблуждение | Это заблуждение стражника, который в жизни не имел настоящей власт |
| 2203 | TRAIT_SEED | безвластный | стражника, который в жизни не имел настоящей власти |
| 2204 | TRAIT_SEED | надменный | что он теперь хозяин ситуации, что Орм у него на крючке |
| 2205 | TRAIT_SEED | властолюбивый | что он теперь хозяин ситуации, что Орм у него на крючке |
| 2301 | BELIEF_SEED | Борко вообразил себя акулой, потому что однажды увидел, как акула ест, и решил,  |
| 2302 | RELATIONSHIP | Борко не контролирует Орма. | Орм | dependence | negative |
| 2303 | RELATIONSHIP | Борко не контролирует Гильдию. | Гильдия | dependence | negative |
| 2304 | RELATIONSHIP | Борко не контролирует Горана. | Горан | dependence | negative |
| 2307 | TRAIT_SEED | хозяин Люси | хозяин Люси |
| 2310 | EFFECT | И это всё, что у него есть. | gain |
| 2400 | EFFECT | система грязи сформировалась в его понимании | custom |
| 2403 | EFFECT | грязь делает его равнодушным к деньгам до определенного момента | custom |
| 2600 | PORTRET | Так удобнее зал видеть |
| 2602 | RELATIONSHIP | Люся | Люся | внимание | positive |
| 2701 | EFFECT | она хуже всего остального | emotion |

## AMBIGUOUS (неоднозначно)

| ordinal | kind | summary | candidates |
|---------|------|---------|-----------|
| 500 | LOCATION | тахта пристрастилась заходить в таверну «Серебряный волк» есть днём и выпивать в | 2 |
| 700 | PORTRET | из-за внешности он производит хорошее впечатление на начальство, ему доверяют бо | 3 |
| 1800 | BELIEF_SEED | Новая мечта, к которой он, впрочем, и не стремится, — стать хозяином «Серебряног | 2 |
| 2402 | TRAIT_SEED | спокойный | У каждого вида грязи своя касса, и пока кассы не смешиваются, совест | 2 |

## RECLASSIFIED (kind изменился)

| ordinal | old_kind | new_kind | old_summary | new_text |
|---------|----------|----------|-------------|----------|
| 100 | EFFECT | EVENT | работал грузчиком на рынке | occupation | работал грузчиком на рынке с детства |
| 600 | EFFECT | BELIEF_SEED | понял, что те, кто вмешивается в чужие дела, долго не живут  | те, кто вмешивается в чужие дела, долго не живут | danger |
| 800 | EFFECT | EVENT | благодаря тяжёлой работе в молодости добился хорошего телосл | добился хорошего телосложения от тяжелой работы в молодости |
| 900 | EFFECT | RELATIONSHIP | гильдия воров поняла, что он ничего собой не представляет |  | Гильдия воров прекрасно понимает, что Орм ничего собой не пр |
| 1102 | EFFECT | RELATIONSHIP | часто пил и ел в «Серебряном волке» за счёт Горана | custom | помогал Горану скрывать контрабанду от стражи и властей, час |
| 1103 | EFFECT | TRAIT_SEED | деньгами от купца не брал никогда | gain | не берет деньги от друзей | никому не брал никогда, но деньг |
| 1301 | EFFECT | TRAIT_SEED | хочет снова наблюдать и мастурбировать за этим зрелищем | de | хочет наблюдать за насилием | решился подсесть, чтобы снова  |
| 1302 | RELATIONSHIP | TRAIT_SEED | хочет снова наблюдать и мастурбировать за этим зрелищем | Ор | хочет наблюдать за насилием | решился подсесть, чтобы снова  |
| 1400 | BELIEF_SEED | DESIRE_SEED | Не женился только потому, что сначала искал «ту самую», а се | хочет наблюдать за насилием, не участвуя напрямую | наблюден |
| 1501 | TRAIT_SEED | PORTRET | чувство стыда | отпало всякое чувство стыда | со временем у стражника отпало всякое чувство стыда, осталос |
| 2000 | RELATIONSHIP | BELIEF_SEED | Тень — просто мутный тип, скорее всего связанный с криминало | Тень — скорее всего связанный с криминалом мутный тип | dang |
| 2002 | EFFECT | LOCATION | появился в таверне | Тень | residence | Орм садится за угловой стол в таверне, лицом к коридору на к |
| 2100 | RELATIONSHIP | EVENT | Гильдия воров платит Борко зарплату. | Гильдия воров | depen | начинает получать зарплату от гильдии воров |
| 2102 | EVENT | RELATIONSHIP | Гильдия воров заявила стражнику, что двойное убийство Торнин | Борко прикрывает Торнина по приказу Гильдии воров, закрывая  |
| 2200 | BELIEF_SEED | RELATIONSHIP | Борко думает, что он кукловод. | Борко думает, что имеет власть над Ормом | вражда | negative |
| 2201 | BELIEF_SEED | RELATIONSHIP | Борко думает, что без его разрешения Орм не посмеет. | Борко думает, что имеет власть над Ормом | вражда | negative |
| 2300 | TRAIT_SEED | RELATIONSHIP | серый кардинал | Борко не серый кардинал. | Борко — стражник, человек | Стражник Борко | человек |
| 2306 | TRAIT_SEED | BELIEF_SEED | хозяин таверны | он хозяин таверны | Борко рисует себе картину, где он хозяин таверны, хозяин Люс |
| 2308 | TRAIT_SEED | BELIEF_SEED | хозяин всего маленького мира «Серебряного волка» | хозяин вс | Борко рисует себе картину, где он хозяин таверны, хозяин Люс |
| 2309 | BELIEF_SEED | PORTRET | Эта картина его греет по ночам. | Борко воображает себя акулой, контролирующим Орма, Гильдию и |

## Полная таблица

| ordinal | kind | status | rationale |
|---------|------|--------|-----------|
| 0 | RELATIONSHIP | PRESERVED | 1 match, same kind (RELATIONSHIP) |
| 100 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → EVENT |
| 200 | EVENT | DUPLICATED | >1 matches with same kind (top=0.58, 2nd=0.26) |
| 300 | EVENT | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.48) |
| 400 | EFFECT | MERGED | meaning distributed across 4 new entries (top=0.72, 2nd=0.26) |
| 500 | LOCATION | AMBIGUOUS | multiple candidates with close scores (top=0.44, 2nd=0.40) |
| 600 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → BELIEF_SEED |
| 700 | PORTRET | AMBIGUOUS | multiple candidates with close scores (top=0.59, 2nd=0.59) |
| 800 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → EVENT |
| 900 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → RELATIONSHIP |
| 1000 | EVENT | PRESERVED | 1 match, same kind (EVENT) |
| 1100 | EVENT | LOST | no semantic match (score < 0.2) |
| 1101 | RELATIONSHIP | PRESERVED | 1 match, same kind (RELATIONSHIP) |
| 1102 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → RELATIONSHIP |
| 1103 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → TRAIT_SEED |
| 1104 | BELIEF_SEED | PRESERVED | 1 match, same kind (BELIEF_SEED) |
| 1105 | EFFECT | MERGED | meaning distributed across 3 new entries (top=1.00, 2nd=0.44) |
| 1200 | EVENT | LOST | no semantic match (score < 0.2) |
| 1300 | EVENT | LOST | no semantic match (score < 0.2) |
| 1301 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → TRAIT_SEED |
| 1302 | RELATIONSHIP | RECLASSIFIED | 1 match, kind changed: RELATIONSHIP → TRAIT_SEED |
| 1303 | EVENT | LOST | no semantic match (score < 0.2) |
| 1304 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 1305 | EVENT | LOST | no semantic match (score < 0.2) |
| 1306 | EFFECT | LOST | no semantic match (score < 0.2) |
| 1400 | BELIEF_SEED | RECLASSIFIED | 1 match, kind changed: BELIEF_SEED → DESIRE_SEED |
| 1500 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 1501 | TRAIT_SEED | RECLASSIFIED | 1 match, kind changed: TRAIT_SEED → PORTRET |
| 1700 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 1701 | EFFECT | MERGED | meaning distributed across 2 new entries (top=0.44, 2nd=0.33) |
| 1800 | BELIEF_SEED | AMBIGUOUS | multiple candidates with close scores (top=0.32, 2nd=0.24) |
| 1900 | EVENT | LOST | no semantic match (score < 0.2) |
| 2000 | RELATIONSHIP | RECLASSIFIED | 1 match, kind changed: RELATIONSHIP → BELIEF_SEED |
| 2001 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 2002 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → LOCATION |
| 2100 | RELATIONSHIP | RECLASSIFIED | 1 match, kind changed: RELATIONSHIP → EVENT |
| 2101 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 2102 | EVENT | RECLASSIFIED | 1 match, kind changed: EVENT → RELATIONSHIP |
| 2103 | EFFECT | LOST | no semantic match (score < 0.2) |
| 2200 | BELIEF_SEED | RECLASSIFIED | 1 match, kind changed: BELIEF_SEED → RELATIONSHIP |
| 2201 | BELIEF_SEED | RECLASSIFIED | 1 match, kind changed: BELIEF_SEED → RELATIONSHIP |
| 2202 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 2203 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 2204 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 2205 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 2300 | TRAIT_SEED | RECLASSIFIED | 1 match, kind changed: TRAIT_SEED → RELATIONSHIP |
| 2301 | BELIEF_SEED | LOST | no semantic match (score < 0.2) |
| 2302 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 2303 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 2304 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 2305 | PORTRET | DUPLICATED | >1 matches with same kind (top=0.62, 2nd=0.50) |
| 2306 | TRAIT_SEED | RECLASSIFIED | 1 match, kind changed: TRAIT_SEED → BELIEF_SEED |
| 2307 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 2308 | TRAIT_SEED | RECLASSIFIED | 1 match, kind changed: TRAIT_SEED → BELIEF_SEED |
| 2309 | BELIEF_SEED | RECLASSIFIED | 1 match, kind changed: BELIEF_SEED → PORTRET |
| 2310 | EFFECT | LOST | no semantic match (score < 0.2) |
| 2400 | EFFECT | LOST | no semantic match (score < 0.2) |
| 2401 | TRAIT_SEED | DUPLICATED | >1 matches with same kind (top=0.54, 2nd=0.38) |
| 2402 | TRAIT_SEED | AMBIGUOUS | multiple candidates with close scores (top=0.38, 2nd=0.36) |
| 2403 | EFFECT | LOST | no semantic match (score < 0.2) |
| 2600 | PORTRET | LOST | no semantic match (score < 0.2) |
| 2601 | LOCATION | PRESERVED | 1 match, same kind (LOCATION) |
| 2602 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 2700 | PORTRET | PRESERVED | 1 match, same kind (PORTRET) |
| 2701 | EFFECT | LOST | no semantic match (score < 0.2) |
| 2800 | PORTRET | MERGED | meaning distributed across 3 new entries (top=0.46, 2nd=0.25) |
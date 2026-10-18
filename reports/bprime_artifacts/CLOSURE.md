# B′ CLOSURE — фиксация закрытой пары (E-BM1)

> **Статус:** ЗАКРЫТА (2026-10-17T17:50+07:00, HEAD 0633ed0c, ветка V.0.5.4.3.7_тесты_1)
> **Вердикт Мастера (2026-10-17):** B′ локализовал вмешательство, но не доказал механизм.
> **Принцип:** оригиналы неизменны; повторы — в отдельный каталог с новым experiment_id.

## 1. Эпистемологическая рамка

B′ изолирует причинный эффект ПОТРЕБЛЕНИЯ МНОЖИТЕЛЯ маски в точке вмешательства (decision_hub.py:1116, base *= mask_mod). Это НЕ доказательство полного механизма маски. B3 = отклонение от предсказания, не механизм.

## 2. Контрольные суммы оригиналов (заморозка)

7 файлов, 226 КБ суммарно, mtimes 2026-10-17T12:09..12:25+07:00:

| Файл | Bytes | SHA-256 |
|---|---|---|
| compare_report.json | 4320 | 2E43E9D79302F1E7F24390CF5D672FC317DB8AFD869FFFAA01317738B73014D7 |
| passport_off.json | 1516 | 281A3BB2FB4F45AA683621A5DB88C26CF2D82783A07213BC1D61081F426337D0 |
| passport_on.json | 1515 | D080EAC6BC0C95A295F8ED582EB4C4B00455E3043E228FDE5D18F33A18D77107 |
| result_off.json | 4511 | 4D82E20C03D1E89ED025B439A4208BD7F4CF794F08FFE1603847892BAA35CC39 |
| result_on.json | 3802 | 97AFA202B5DFFA0FFB7B9F934312D330BE6C3B89BF95C8EAAF20DBC7151D82AB |
| result_raw_off.json | 107994 | 03DE36B0C17F1446C790741933DCB1B03F23ABE16CFB7D96CFB614639FD440B7 |
| result_raw_on.json | 104559 | 4FE19777A203CF6E68352751ADD555434A50F3A5F01AB913A0F0C6C9B2C640DC |

Запрет: не перезаписывать оригиналы. Повторы B′ — в reports/bprime_artifacts_repeat_<id>/ с новым experiment_id.

## 3. Паспорта пары — COMPATIBLE

Обе ноги: head=351c74dbe2654d4fdbdd4c12ecbfe8161150e879, diff_hash=c4b2b999..., status_porcelain = 5 файлов только docs/, untracked_significant_roots=[], input_sha256 совпадает по 5 файлам. mask_ticks: {on: 29, off: 29} — симметрично.

## 4. Вердикт по замороженным критериям

Окно 2..15 (14 тиков), tol=0.1. Ветвь: B3 + coverage-drift.

- attack: ON -0.341114, OFF -1.948779, contrast +1.607665, PRED 1.361308, dev +0.246357, within_tol=false
- intimidate: ON -0.237543, OFF -1.845229, contrast +1.607686, PRED 1.361329, dev +0.246357, within_tol=false
- observe: dev +0.158843, within_tol=false (аннотация)
- warn/talk/idle: within_tol=true

ON == B1(B) побайтово: 6 per-intent средних воспроизводят A+F+PRED до 6-го знака.

## 5. Per-tick анатомия (описательная, пост-хок)

- rec0 (t1): IDENTICAL в обеих ногах. Инъекция не течёт назад.
- rec1 (t2, точка вмешательства): OFF flee=0.6221 (argmax) → ON flee=0.184 (suppressed). Контрасты в пределах 0.0155 от PRED. Локальное каузальное закрытие N4.
- rec2 (t3): attack/intim контраст 1.6196 (ступня +0.274 за один тик).
- rec3 (t4): attack/intim 1.6283 (плато). observe разгон +0.039/тик.

## 6. Гипотезы — статус реестра

H-a (замкнутый контур поведения) — SUPPORTED, NOT CONFIRMED. Наблюдаемая временная структура совместима с обратной связью, но конкретный канал и его вклад не установлены (rel_goran_per_tick = 30×null, D-5).

H-b (влияние незамороженного WIP) — RETRACTED (forensics). Парные паспорта подтверждают совместимость входов и дерева. Постфактум наблюдавшийся porcelain породил ложное подозрение. H-b остаётся в реестре как RETRACTED.

## 7. Реестр дефектов после B′

- D-1: ЗАКРЫТ (351c74db) — walk-имя ≠ имя цепочки
- D-2: ЗАКРЫТ — ключ сырья scores_per_tick vs scores_raw
- D-3: ЗАКРЫТ — porcelain-фильтр своих артефактов
- D-5: ОТКРЫТ — rel_goran_per_tick = 30×null. Capture-слепота двух слоёв: (1) B′ framework делегирует capture rec донору; (2) result.rel_captures либо пуст, либо snap.get(_NPC) = None. Чинить через прямой capture V2RelationshipBackend.get_pair в mode_leg B′ framework
- O-2: зафиксировано — ON-нога: пустые скоры тиков 16-30; вне окна
- Д-4: сужен — willpower 60.0 / stress 0.0 / will free. Воля исключена как драйвер ступни t3. Оговорка: psyche_willpower=60 в артефакте ≠ DecisionHub потребляет 60 (DecisionHub читает will_state enum и effective_drives["control"], без psyche.willpower напрямую)

## 8. Инструмент и пререгистрация (заморожены)

Фреймворк: backend/tests/sandbox/SUPERBOX/scenarios/bm_bprime_framework.py @ 351c74db. Режимы: --check | --leg on|off (требует --window-confirmed "2..15") | --compare. Инъекция OFF-ноги: in-memory, decision_hub.py:1116 base *= mask_mod → base *= 1.0. Геометрия: CELL-B_f70_tm60, golden_fear_f70.yaml, merchant_goran, Open_road, 30 тиков, окно 2..15.

## 9. Ограничения доказательной базы

- E1: возможное загрязнение результатов межноговым состоянием runner
- E2: исторические multi-leg-отчёты условны до подтверждения изоляции
- E3: score-записи пропадали после ~15-го тика в некоторых конфигурациях
- E4: смена пространственной базовой линии после PATH-D1 — статус клетки A ОТКРЫТ
- H1: неполный захват компонентов score
- INVALID-ON: артефакт B5-инцидента, независимым подтверждением НЕ является

## 10. Передача преемнику

Дуга B′ закрыта. Порядок работ (вердикт Мастера): bm_window_check.py v2 → D-5 → H1a → вопрос A → C′ design → доклад. Ключевой запрет: не превращать установленный эффект потребления множителя в утверждение, что уже найден полный механизм поведения маски.

## 11. Обновление: повтор 005 — полная причинная цепочка (CONFIRMED)

> **Вердикт Мастера (2026-10-18):** Дуга B′ закрыта как экспериментально подтверждённая причинная цепочка.
> Канал обратной связи подтверждён в сценарии B′: маска → действие → событие мира → память → риск → следующее решение.

### 11.1 Полная причинная цепочка (доказана в повторе 005, изолированный worktree)

t2: mask-off (инъекция base *= 1.0)
  -> attack score не подавлен
  -> flee выигрывает
  -> Goran выбирает flee
  -> MovementEngine двигает Goran
  -> Публикуется событие world_tick (actor=merchant_goran, target=player, importance=0.8)
  -> MemoryManager.apply() добавляет в Working Memory

t2 (Фаза 5): decision.py -> get_weights_for_decision
  -> recent_pressure = sum(importance) = 0.8 (от world_tick)
  -> npc_tick_pipeline обновляет state.relationship_cache

t3: DecisionHub._score_components
  -> compute_objective_risk: recent_pressure=0.8 -> base_risk += 0.3
  -> risk_penalty = -fear * risk * 1.25 - 0.6 = -1.3981 (было -1.1227)
  -> base_before_mask = -1.8681 (было -1.5927)
  -> Контраст base_before_mask (ON-OFF) = +0.2651
  -> Итоговый score расхождение: attack ON -0.35 vs OFF -1.9696

### 11.2 Что доказано

1. B3 воспроизводим: CONFIRMED (повтор 005: контрасты побайтово идентичны)
2. Локальный эффект маски на t2: CONFIRMED (base_after_mask +1.3458)
3. Closed-loop обратная связь на t3: CONFIRMED (base_before_mask +0.2651)
4. Канал = risk_penalty: CONFIRMED (+0.2651 = risk_penalty delta)
5. recent_pressure — источник: CONFIRMED (0.0 -> 0.8 в OFF, 0.0 -> 0.0 в ON)
6. Событие world_tick (actor=Goran, target=player, importance=0.8): CONFIRMED
7. Отношения Goran->player (trust/fear) — канал: REFUTED (статичны)

### 11.3 Оговорка B5

Историческая пара воспроизведена по ручному сравнению артефактов; формальная проверка --compare заблокирована несовпадением diff_hash, связанным с untracked тестовыми файлами в worktree.

### 11.4 Оговорка о границах причинного вывода

Цепочка подтверждена в сценарии B′. Формулировка: «канал обратной связи подтверждён в сценарии B′», а не «вся система BehaviorMask полностью доказана».

### 11.5 Статус гипотез (финальный)

- H-a (замкнутый контур): CONFIRMED
- H-b (влияние WIP): RETRACTED

### 11.6 Инструментирование (нейтральное)

- D-5: rel_goran_per_tick
- H1a: components_per_tick
- H1b-mini: base_before/after_mask
- H1b-mini2: fear, drives, risk inputs (strings, neutral)
- H1b-mini3: pressure events (list, neutral)

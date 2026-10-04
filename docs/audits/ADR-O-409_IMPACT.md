`ADR-O-409` [STANDARD] **IMPACT**
Files: backend/app/services/player_avatar_service.py, backend/app/services/events/npc_dialogue_subscriber.py, frontend/ui_workbench/workbench_screen.py
# ADR-O-409 Impact Audit — Name-Gate Closure (FACE/NAME/LINK)

> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR:
> `docs/ADR (Architecture Decision Records).md` (DOM-07, запись ADR-O-409).
> Статус: APPROVED (эскиз утверждён Мастера дословно, сессия S302-окно;
> реализация — следующий заход). Presentation-часть (фото-джойн доски)
> уже в коде: S302, К1.

## Суть решения

Разделены три несводимых знания:

| Ось | Значение | Владелец | Состояние |
|---|---|---|---|
| FACE | «узнаю этого человека» | RecognitionMemory (scene_state["npc_recognition"], M17) | существует, живой |
| NAME | «знаю, как его зовут» | NameKnowledge (per-campaign) | НОВЫЙ, план |
| LINK | «считаю, что имя = это лицо» | player_link на доске | НОВЫЙ, план |

**Канонический инвариант:** `npc_id` в backend ≠ знание игрока.
Наличие machine-identity у движка не даёт игроку имени NPC.

**Формула отображения:** `show_name = recognition_confirmed AND name_confirmed`.

**Прогрессия UI:** Незнакомец → «человек с фартуком» (generic из
visible_markers) → «Имя (?)» → Имя.

## Changed Domains

- **Player cognition (journal-запись):** writer-gate в
  `npc_dialogue_subscriber` — speaker резолвится через NAME-ось, не
  напрямую из npc_positions[name] (дыра 3.А: имя попадало в журнал до
  того, как заработано).
- **Avatar персистенция:** NameKnowledge живёт в
  `saves/<campaign>/player_avatar.json` (владелец — avatar_service,
  по образцу dialog_journal; НОВЫЙ сервис ЗАПРЕЩЁН).
- **Journal-схема записи:** + скрытый провенанс-поле `npc_id`
  (машина знает ≠ игрок знает; кормит фото-джойн доски, не UI).
- **M17-семантика:** direct-разговор сужен до FACE-confirmed;
  NAME — только через отдельные каналы.

## Каналы NAME (закрытый список)

1. **SELF_INTRO** — SPEAKER_MENTION в собственной реплике спикера
   (говорит о себе / представился) → confirmed. Спан-механизм
   ground_speaker_mention уже существует.
2. **NPC_MENTION** — услышанное игроком чужое имя → **tentative
   ТОЛЬКО**. ⚠️ STOP-вердикт Мастера: identity-link с фото ЗАПРЕЩЁН
   на уровне механизма — «Торнин сказал, что видел Горана» не
   связывает имя Горана с лицом Горана. Имя ≠ идентичность.
3. **PLAYER_LINK** — доска: фото-карточка + выбранное имя → confirmed.
   Решение игрока, не системы (BOARD = внешний интерфейс мышления
   игрока; авто-inference запрещён).

## Downstream Consumers

- `npc_dialogue_subscriber` (writer-gate + провенанс) — менять.
- `world_snapshot_builder` (display_name над головой) — сужение гейта:
  confirmed-имя требует обе оси.
- `workbench_screen._draw_board` (фото-джойн по npc_id) — частично
  готов (S302/К1: джойн по спикеру; переключится на npc_id-провенанс).
- `recognition_layer._generic_description` — реюз как чистая
  presentation-функция (словарь маркеров → «женщина с фартуком»).
- **НЕ трогаем:** EncounterHistory (третий SSOT cognition запрещён —
  вердикт Мастера), RecognitionMemory-механику M17 (только сужение
  семантики имени, не лица).

## Runtime Impact

- NameKnowledge: RAM-кэш per-campaign + round-trip в
  player_avatar.json (по образцу dialog_journal; ~десятки записей —
  пренебрежимо).
- Writer-gate: O(1) lookup на реплику — ноль влияния на тик.
- Эскалация (LLM-слой, semantic-сессия): DM-промпт «NPC не произносит
  своё имя без представления» — без него гейт честен, но уклончивость
  LLM остаётся вкусовой; наш слой делает её видимой, их — мотивированной.

## Sandbox Tests (план, обязательные при реализации)

1. **Гейт-инвариант:** direct-разговор без произнесённого имени →
   журнал «Незнакомец», npc_id в провенансе; над головой «Незнакомец».
2. **STOP-кейс:** услышанное имя «Горан» от Торнина → NameKnowledge
   tentative, identity-link не создаётся, фото не привязывается.
3. **SELF_INTRO:** реплика с собственным именем → confirmed.
4. **PLAYER_LINK:** доска-ассоциация → confirmed + show_name.
5. **Round-trip:** NameKnowledge переживает перезапуск (save/load).
6. **Регрессия M12/M17:** recognition-лицо не сломан (confirm по
   факту разговора жив, «(?)»-маркеры на месте).

## Rollback

Presentation (S302/К1) независим — откат не требуется. Backend-часть:
writer-gate за флагом `NAME_GATE_ENABLED` (env, default OFF — прецедент
ARBITER_ENFORCEMENT/COGNITION_V0); OFF = байтово прежнее поведение
журнала. NameKnowledge-персистенция аддитивна (неизвестные поля
игнорируются старым кодом) — откат = удаление гейта, файл не мешает.

## Связанное

- Эскиз согласован в диалоге S302-окна (формулировки Мастера
  дословно: инвариант npc_id ≠ знание; STOP identity-link; сужение
  M17-direct; EncounterHistory не подключать).
- Против смежного ADR-408 (GATE-TRIGGER, [FIX]) — ортогонален:
  там эпистемические триггеры, здесь презентационное знание имён.
- Отклонено в окне согласования: мини-окно «Расследование», любые
  счётчики during-game (принцип Мастера), клик-пузырь→журнал.

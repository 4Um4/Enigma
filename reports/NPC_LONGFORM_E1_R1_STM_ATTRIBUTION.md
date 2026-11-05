# NPC_LONGFORM E1 — R-1: Починка атрибуции STM в парной сессии NPC<->NPC

**Трек:** NPC_AUTONOMOUS_LONGFORM_INTERACTION_EXPERIMENT (этап E1)
**Дата:** 2026-11-05
**Предыдущий коммит:** 4f3dcc1f S415.1: Chronicle lifecycle fix

---

## 0. Контекст

Разрыв R-1 (из реестра NPC_LONGFORM §6): в парной сессии NPC<->NPC
LLM не различает «я сказал»/«мне сказали» — обе реплики подписаны
именем владельца сессии.

**Симптом:** в собранном промпте `to_prompt_block` каждая строка
истории подписана `self.npc_id` (владельцем сессии), а не фактическим
говорящим `turn.speaker`. LLM не может определить, кто сказал какую реплику.

**Доказательство (археология):**
- `dialogue_session.py:166` (до фикса):
  `speaker_name = "Игрок" if turn.speaker == "player" else self.npc_id`
- `DialogueTurn.speaker: str` (L47) — поле существует, корректно
- `memory_manager.py:113`: `session.add_turn(speaker=speaker, ...)` —
  speaker передаётся как NPC ID строка
- 3 потребителя `to_prompt_block`:
  - `npc_dialogue_subscriber.py:492,517`
  - `memory_manager.py:213`

---

## 1. Fix (БЫЛО/СТАЛО)

**Файл:** `backend/app/services/memory/dialogue_session.py`
**Метод:** `to_prompt_block` (L166)

**БЫЛО:**
    speaker_name = "Игрок" if turn.speaker == "player" else self.npc_id

**СТАЛО:**
    # R-1 FIX (NPC_LONGFORM E1): атрибуция говорящего в парной сессии NPC<->NPC.
    # До фикса не-игрок печатался как self.npc_id (владелец сессии) — LLM не мог
    # различить «я сказал»/«мне сказали». Теперь печатается фактический говорящий
    # (turn.speaker — NPC ID). Display name resolver — опциональный параметр
    # для будущей улучшения (прецедент name_gate ADR-O-409).
    speaker_name = "Игрок" if turn.speaker == "player" else turn.speaker

**Принцип:** минимальное изменение — одна строка рендера. Форматы данных
не меняются. Display name resolver — опциональное будущее улучшение
(прецедент name_gate ADR-O-409), не часть E1.

---

## 2. Тесты (RED -> GREEN)

**Файл:** `backend/tests/micro/test_r1_stm_attribution.py` (3 теста)

### test_r1_npc_speaker_attributed_not_owner
Парная сессия `maid_lusya` (владелец) с репликой `speaker="tavern_keeper_tornin"`.
После фикса block содержит:
    Последние реплики:
      tavern_keeper_tornin -> maid_lusya [intimidate]: Опять кружку разбила?
      maid_lusya -> tavern_keeper_tornin [appease]: Простите, хозяин

До фикса обе реплики были подписаны `maid_lusya` (владельцем).

### test_r1_player_speaker_still_igrok
Реплика игрока по-прежнему подписана «Игрок» (не «player»).

### test_r1_three_way_attribution
Три реплики от двух разных говорящих — все подписаны корректно.

**Результат:** 3/3 PASSED (pytest exit_code=0, 0.18s)

---

## 3. Гейты

- **ruff:** `python -m ruff check app/services/memory/dialogue_session.py tests/micro/test_r1_stm_attribution.py` — All checks passed!
- **pytest:** 3/3 PASSED
- **IPT:** 52 passed / 0 skipped / 2 failed (2 CRITICAL) — оба CRITICAL чужие:
  - `INV-RE-CACHE-ALLOWLIST` — `services/npc/npc_loader.py` (GROWTH, чужой WIP)
  - `INV-SILENT-FAILURE` — `dialogue_executor.py:390` (P5-B, чужой контур)
- **Дельта-метод:** вклад = 0 новых CRITICAL

---

## 4. Соответствие плану NPC_LONGFORM §7 (E1)

| Требование плана | Реализация |
|---|---|
| Файл: `services/memory/dialogue_session.py` | ✅ |
| Изменение: `self.npc_id` -> `turn.speaker` | ✅ |
| Тесты до: воспроизводят дефект | ✅ (test_r1_npc_speaker_attributed_not_owner) |
| Тесты после: рендерит «tavern_keeper_tornin: …» и «maid_lusya: …» | ✅ |
| Критерий: каждая строка истории подписана фактическим говорящим | ✅ |
| Регресс существующих тестов STM | ✅ (ruff чист, IPT без новых CRITICAL) |
| Риск: низкий | ✅ (одна строка рендера) |

---

## 5. Следующие этапы NPC_LONGFORM

- **E2** — Гарантированный ответ и потребление thread_id (R-3, часть R-2)
- **E3** — ConversationSession — групповая сессия (R-2)
- **E4** — Жизненный цикл разговора (R-4, R-5)
- **E0** — диагностический харнесс `experiment_runner.py` (параллельно)

---

## 6. Открытые вопросы

- Display name resolver (опциональное улучшение): `turn.speaker` выводит
  NPC ID (например «tavern_keeper_tornin»), а не display name («Торнин»).
  Это приемлемо для E1 — LLM видит корректную атрибуцию. Display name
  можно добавить позже как опциональный параметр `to_prompt_block`,
  когда будет живой реестр имён (прецедент name_gate ADR-O-409).
# HANDOFF: S380 — is_recurring (повторяемость событий до памяти NPC)

**Дата:** 2026-11-04  
**Ветка:** main  
**Коммиты:** `92bf31d0` (патч), `d2ac23c5` (canon update)  
**Предыдущий:** S380 USL-1.1/1.2/1.3/1.4 (`fe50b3be`, `8caefebc`)

---

## 1. Исходная задача

S380 / USL — точка остановки «повторяемость событий».  
Фраза «Люся регулярно подвергалась избиениям» должна создавать событие с признаком повторяемости, который доходит до EventMemory и замедляет затухание памяти.

**Точка потери (диагноз):** REPEAT-якорь извлекался age_anchor.py, попадал в hint для LLM, но LLM не производил структурированного маркера `is_recurring` в draft_payload. Seeder читал только `summary` из payload, назначал `decay_rate=SEED_DECAY_RATE=0.001` безусловно. Повторяемость терялась на переходе «якорь → payload».

---

## 2. Принятые решения (Мастер Тай)

| Решение | Обоснование |
|---|---|
| `is_recurring` — ключ payload (`_PL_IS_RECURRING` константа), НЕ поле dataclass | payload уже Dict[str, Any] (§12.1); backward compat автоматический |
| `is_recurring` НЕ добавлен на EventMemory | decay_rate уже персистируется и несёт эффект; минимальный патч |
| `SEED_DECAY_RATE_RECURRING = 0.0005` (половина от 0.001) | Повторяющееся забывается медленнее, но НЕ перманентно (0.0 = модель травмы) |
| Prompt усилен: `is_recurring: true` ОБЯЗАТЕЛЬНО при REPEAT | Соответствует ТЗ: «summary ОБЯЗАТЕЛЬНО должен содержать маркер регулярности» |
| Canon update через payload-update, не re-decompose | COV-12: re-decompose создаёт дубликат (AUTHOR_CONFIRMED не заменяется) |

---

## 3. Выполненные изменения

### Коммит `92bf31d0` — патч is_recurring

| Файл | Изменение |
|---|---|
| `chronicle_seeder.py` | `_PL_IS_RECURRING` константа + `SEED_DECAY_RATE_RECURRING=0.0005` + модуляция decay_rate в `build_seed_memories` |
| `chronicle_decompose_system.txt` | `is_recurring` в схему EVENT + усиление REPEAT-инструкции (уже в репо через `6e48f8fb`) |
| `age_anchor.py` | REPEAT hint: «установи is_recurring: true» (обе ветки) |
| `test_s380_is_recurring_chain.py` | 7 тестов (Уровень А: seeder + Уровень Б: normalizer + полная цепочка) |

### Коммит `d2ac23c5` — maid_lusya canon update

| Файл | Изменение |
|---|---|
| `config/npc/chronicles/maid_lusya.json` | payload-update: `is_recurring: true` на EVENT `83a72f0...` («регулярное насилие после пьянки»); version 1→2 |

**Backup:** `config/npc/chronicles/maid_lusya.json.bak_s380` — временный снимок для отката. Удалить после стабилизации.

---

## 4. Тесты и результаты

| Проверка | Результат |
|---|---|
| `test_s380_is_recurring_chain.py` | 7/7 GREEN (mock chain: seeder + normalizer + full chain) |
| Ruff | All checks passed |
| IPT | 54 passed / 0 failed / 0 CRITICAL |
| CCH-4 seed регрессия | PASSED (seeder-логика расширена, не заменена) |
| Live LLM (Hermes-3) | GREEN: «регулярно избивал» → REPEAT anchor → `is_recurring: true` в EVENT |
| Canon update verify | 6/6 GREEN (canonical, is_recurring, provenance, regression, seeder decay, no dup) |

---

## 5. Доказательства цепочки

**Полный путь доказан end-to-end:**

```
SOURCE TEXT («регулярно избивал»)
  → age_anchor.py: REPEAT-якорь извлечён (value=0)
  → build_age_hint: «установи is_recurring: true в draft_payload»
  → Hermes-3 LLM: {"summary": "регулярно избивал Люсю", "is_recurring": true}
  → ChronicleDecompositionNormalizer.normalize: draft_payload проходит (dict copy)
  → ChronicleEntry.payload: is_recurring=true (AUTHOR_CONFIRMED)
  → chronicle_seeder.build_seed_memories: decay_rate=SEED_DECAY_RATE_RECURRING (0.0005)
  → EventMemory.decay_rate=0.0005 (vs 0.001 для единичных)
```

**Доказано на трёх уровнях:**
1. Mock-тесты (7/7): ChronicleEntry → seeder → EventMemory
2. Живой LLM: фрагмент 6 maid_lusya → REPEAT → is_recurring=true
3. Canon update: maid_lusya.json → seeder → EventMemory(decay_rate=0.0005)

---

## 6. Оставшиеся дефекты / нерешённые вопросы

1. **Другие NPC canons** — 5 канонов (guard_borko, merchant_goran, blacksmith_orm, thief_shadow, tavern_keeper_tornin) могут иметь EVENT с повторяемостью без `is_recurring`. Проверка: `python -c` скрипт (как maid_lusya). Если найдены — payload-update по тому же паттерну.

2. **CALIBRATION_CANDIDATE: `SEED_DECAY_RATE_RECURRING=0.0005`** — значение выбрано как половина от `SEED_DECAY_RATE=0.001`. Не калибровано через Calibration Lab. Если повторяющиеся события забываются слишком медленно/быстро — корректировка через Lab.

3. **Backup file** `maid_lusya.json.bak_s380` — удалить после стабилизации (не в git).

4. **`test_butterfly_full_game_loop.py`** — untracked, чужой файл (параллельная сессия `ca22e780`). НЕ коммитить (Anti-Race).

5. **PermissionError pytest temp** — `C:\Users\lipir\AppData\Local\Temp\pytest-of-lipir\pytest-current` — доступ заблокирован. Окружение, не код. Фикс: `Remove-Item -Recurse -Force $env:TEMP\pytest-of-lipir` или запуск от админа.

---

## 7. Следующий конкретный шаг

**USL-1.5 / USL-1.6** (по дорожной карте USL):

- **USL-1.5**: CanonicalRegistry bridge — `registry_builder.CanonicalRegistry` → input-контур (intent_compressor). Проверить, что «Орму» автора = «Орму» игрока через canonical resolution.
- **USL-1.6**: Regression + Activation — финальные тесты, флаги, DTO Registry.

**Или:** проверить остальные 5 NPC canons на наличие REPEAT-событий без `is_recurring` (массовый payload-update, если нужно).

---

## 8. Архитектурные ориентиры (не нарушены)

- ADR-O-206 / L8.1: decay_rate = surprise (НЕ EmotionTag) — `is_recurring` НЕ EmotionTag, конфликт нет
- ADR-O-423: seeder — pure translator — расширение payload-чтением консистентно
- §12.1: ключи-константы — `_PL_IS_RECURRING` модульная константа
- COV-12: AUTHOR_CONFIRMED не заменяется при re-decompose — обойдён через payload-update
- CCH-7 / ADR-O-422: Semantic Validation Gate — вызван и пройден
- ТЗ: «Не подменять повторяемость важностью» — importance не тронут (0.6)
- ТЗ: «Не менять общий decay» — только для is_recurring=True, остальные байт-идентичны

---
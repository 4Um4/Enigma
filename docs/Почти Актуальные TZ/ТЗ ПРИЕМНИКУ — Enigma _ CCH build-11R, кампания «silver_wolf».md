# ТЗ ПРИЕМНИКУ — Enigma / CCH build-11R, кампания «silver_wolf»

Дата: 2026-10-18. Предыдущая сессия закрыта сразу после разбора вывода BLOCK 9. Твоя точка входа — **BLOCK 10**.

## 0. Быстрый старт (первые 60 секунд новой сессии)

1. Прочитай ЦЕЛИКОМ `/home/z/my-project/worklog.md` (общий журнал: intake-материалы, BLOCK 5–9) и этот ТЗ.
2. Суть: конвейер «Все.md → черновик → подтверждение автора → канон → сеялка → отчёт понимания» ПРОРВАН на 1 из 6 NPC. blacksmith_orm канонизирован (71 запись; понимание 11✓/8~/2✗ из 21 пункта; всего по канону 38.8%). Остальные 5 упёрлись в серверный баг: POST canonize даёт **500** вместо ожидаемого 422 «Save=Contract» на неразрешённых открытых вопросах.
3. Первый шаг: **BLOCK 10** — безопасный репро 500 (sandbox-копия, свежий процесс, traceback), патч сервера (422 с русским fix_hint; валидация ДО записи), рестарт бэкенда, проверка через живые эндпоинты. Детальный план — §6.

## 1. Миссия Мастера (не меняется)

«Все.md = канон → сеялка грузит его в игру → по каждому пункту игра показывает "поняла / не поняла". Главное сделай мне код!»

Цепочка: Все.md (пункты по каждому NPC) → pygame-редактор хроники: Ctrl+G раскладывает пункты на записи (черновик, provenance=LLM_DRAFT) → акт автора: подтверждение (LLM_DRAFT→AUTHOR_CONFIRMED, confidence СНЯТЬ) → F9 канонизация (канон `config/npc/chronicles/`) → сеялка `build_full_seed(npc_id)` грузит хронику в игру (консьюмер — npc_loader, гейт «новой игры»; mtime-кэш сеялки инвалидируется записью канона — по преп-записи BLOCK 9, проверить grep при необходимости) → отчёт понимания (Ctrl+U): по каждому пункту ✓ поняла (≥35% значимых слов) / ~ частично (18–35%) / ✗ не поняла.

## 2. Железные правила поставки (нарушать нельзя)

1. **Поставка = нумерованные PowerShell BLOCK'и** (следующий — BLOCK 10). Мастер вставляет в `(x64) PS C:\DDD\Codex\VSC_Enigma\Enigma`, .venv активирован. Блок самодостаточен.
2. **Вопросов Мастеру НЕ задавать.** Нужен выбор — печатай варианты + рекомендацию в выводе блока.
3. Файлы — только через блок: каждый патч с `.bak-blockN` рядом; py_compile после патча; FAIL — автооткат из .bak.
4. Идемпотентность: повторный прогон безопасен (guard'ы «уже пропатчен», Test-Path бэкапов).
5. После возвращения вывода блока: append-запись в `/home/z/my-project/worklog.md` (формат — в начале журнала), архив блока в `/home/z/my-project/scripts/`.
6. Статусы/хинты — по-русски. HTTP из PS/питона — urllib c UTF-8 (НЕ Invoke-RestMethod — портит кодировку). Печать в консоль — ASCII-безопасная.
7. Бэкенд может быть не поднят → alive-check (`GET /api/chronicle/roster/silver_wolf`) в §0 блока; где можно — работать in-process. Патч бэкенда ⇒ нужен рестарт uvicorn (BLOCK 9 не перезапускал: его патчи фронтовые).

## 3. Архитектура (проверено блоками 1–9; НЕ перепроверять)

| Компонент | Факт |
|---|---|
| Бэкенд | FastAPI, `uvicorn app.main:app`, 127.0.0.1:8000, роуты под `/api` |
| Редактор | pygame, `frontend/chronicle_editor/chronicle_app.py` + `api.py` (HTTP-клиент) |
| Клавиши | F7 редактор; Ctrl+G разложить; Ctrl+O загрузить; Ctrl+U отчёт понимания; K_c (C) навигатор вопросов, C+1..4 выбор; F9 = «подтвердить и канонизовать» (с BLOCK 9) |
| Канон | `config/npc/chronicles/<npc>.json` (canonical=True, canonical_version) |
| Черновики | `saves/silver_wolf/chronicle_drafts/<npc>.json` |
| BASE_DIR | корень проекта (`backend/app/core/config.py`) |
| Store | `chronicle_store`: валидация «Save = Contract» (ADR-O-420): LLM_DRAFT в канон нельзя (422); AUTHOR_* не хранит confidence (domain:231 «канон не гипотеза»); доступ — `routes_chronicle._get_store()` (fallback `ChronicleStore(CANON, saves)` — сигнатуру сверить inspect'ом) |
| Сеялка | `chronicle_seeder`: `canonical_chronicle(npc_id)` → `build_full_seed(npc_id)` — чистый транслятор, сигнатуры подтверждены (обе принимают npc_id); берёт ТОЛЬКО AUTHOR_CONFIRMED/AUTHOR_AUTHORED (chronicle_seeder:116); варнинги `[CCH_SEED]` |
| Отчёт | `understanding_report`: docs_from_dir / build_report / render_markdown; читает КАНОН; пороги ✓≥35% / ~18–35% / ✗ |
| Эндпоинты | `/api/chronicle/{campaign}/{npc}/draft` GET/PUT; `.../canonize` POST (body `{"campaign_id": ...}`); `/api/chronicle/roster/{campaign}`; `/api/chronicle/{campaign}/understanding` |
| Фронт-клиент api.py | get_draft (GET, `data["document"]`), save_draft (PUT всем документом), canonize (POST), resolve_question — ГОТОВЫЙ прецедент read-modify-write |

## 4. Состояние после BLOCK 9 (вывод прогона у Мастера)

### 4.1 Патчи (оба py_compile OK, бэкапы `.bak-block9` рядом с файлами)

- `frontend/chronicle_editor/api.py` — новый метод `confirm_author_entries(campaign, npc_id)` (сейчас строки 104–123, вставлен перед `def canonize`): GET draft → все LLM_DRAFT→AUTHOR_CONFIRMED + `pop("confidence")` → PUT; возврат числа переведённых, −1 если черновик/сервер недоступен.
- `frontend/chronicle_editor/chronicle_app.py` — `_canonize()` (строки 559–574): сперва `confirm_author_entries`, при −1 статус и выход, иначе `canonize`; статусы «КАНОНИЗИРОВАНО (v…; подтверждено: N)» / «БЛОК (Save=Contract): …».
- ⚠️ В рантайме UI (запуск редактора) НЕ смоук-тестировано — только py_compile. Смоук in-process: confirm_author_entries по уже подтверждённому NPC (ждём 0) и по несуществующему (ждём −1).
- Бэкенд НЕ перезапускался — поднятый uvicorn несёт ДОпатчевый серверный код (именно его canonize дал 500-е).

### 4.2 Данные

Все 6 черновиков УЖЕ переведены: 100% AUTHOR_CONFIRMED, confidence снят (PUT 200 ×6). Повторный флип — no-op.

| NPC | записей | неразреш. вопросов | PUT | POST canonize | Канон сейчас |
|---|---|---|---|---|---|
| blacksmith_orm | 71 | 0 | 200 | **200** | 71 AUTHOR_CONFIRMED, v1 ✓ |
| guard_borko | 76 | 1 | 200 | **500** | **entries=0 (!), canonical=True, v1** |
| tavern_keeper_tornin | 77 | 2 | 200 | **500** | отсутствует |
| maid_lusya | 53 | 1 | 200 | **500** | отсутствует |
| merchant_goran | 46 | 1 | 200 | **500** | отсутствует |
| thief_shadow | 35 | 1 | 200 | **500** | отсутствует |

Корреляция 500 ↔ неразрешённые вопросы идеальная (0→200; ≥1→500). Ожидался 422 с fix_hint — сервер вместо этого падает. Это НЕ фронт: флип и PUT прошли у всех; падает серверный canonize.

**Аномалия:** `config/npc/chronicles/guard_borko.json` с 0 записями (canonical=True, v1). Происхождение неясно: (а) докатился с BLOCK 6 (block6_canon_e2e.ps1 — канон-e2e того периода; «канон 0 записей» в диагностике BLOCK 7 ему не противоречит) или (б) его написал падающий canonize в BLOCK 9. Развязка: `Get-Item ...\guard_borko.json | fl CreationTime, LastWriteTime` — если время ≈ прогон BLOCK 9, значит путь 500 пишет частичные файлы ⇒ обязательно чинить «валидация ДО записи». По вердикту S336 пустой канон тихо вытеснится успешной re-канонизацией (76 записей), но до того он портит отчёт (Борко 0/28) и сеялку.

### 4.3 Отчёт понимания (по канону, LIVE = Ctrl+U)

49 пунктов (2 канонизированных NPC): **✓11 ~8 ✗30 = 38.8%**.
- blacksmith_orm: 21 пункт → 11✓ 8~ 2✗. Прорыв с нуля. Провалы п.12 и п.16 (0 записей) — пробелы разложения Ctrl+G (контент, не код; опционально добрать — P6).
- guard_borko: 28 пунктов → 0/0/28 — из-за пустого канона (аномалия выше).

### 4.4 Сеялка (block8_probe, секция C)

blacksmith_orm (71 канон-запись) → в сид уходит только **memories=9**:
- 13 RELATIONSHIP отброшено: «связь на неразрешённую сущность — не сеется» (гипотеза: таргеты записаны именами «Торнин»/«Люся», а не entity-id `tavern_keeper_tornin` и т.п. — проверить содержимое canon-записей);
- 5 BELIEF_SEED отброшено: «belief_type='None' вне реестра — в каноне» (belief_type не заполнен при разложении);
- beliefs=0, relationships=0, knowledge=0, imprints=0.

Итого: половина миссии «сеялка грузит в игру» по сути не сделана — без beliefs/relationships игра не получит главного. Замечание: из 71 записи сид-релевантны не все типы (PORTRET/TRAIT_SEED/EVENT/EFFECT сеялку не интересуют?) — в BLOCK 12 снять гистограмму типов записей против маппинга сеялки.

## 5. Проблемы-задачи (по приоритету)

- **P1 (BLOCK 10, критично).** Сервер: POST canonize по черновику с неразрешёнными вопросами → 500 вместо 422. Нужен traceback (безопасный репро — §6), патч: чистый 422 с русским fix_hint (npc, запись, вопрос, опции) и главное — никакого частичного write (валидация ДО save_canonical). После патча — рестарт uvicorn.
- **P2 (BLOCK 10).** guard_borko.json (0 записей): происхождение по таймстампам; решение — удалить (бэкап .bak-block10) или оставить до re-канонизации (S336: вытеснится). Выбрать и обосновать в выводе блока. Проверить, что других canon-файлов с entries=0 нет.
- **P3 (BLOCK 12).** Сеялка: relationship-таргеты (маппинг имена → entity-id в трансляторе, либо корректный emit при Ctrl+G) и belief_type (дефолт/вывод типа; где реестр — grep). Цель: build_full_seed с beliefs>0, relationships>0, memories>0; гистограмма типов; энд-ту-энд: «новая игра» (гейт npc_loader) реально засеивает NPC.
- **P4 (BLOCK 11).** 6 неразрешённых вопросов (borko 1, lusya 1, goran 1, tornin 2, shadow 1). По Save=Contract выбор — за автором: блок печатает вопросы с опциями → Мастер выбирает (в чате или в редакторе C/C+1..4) → применить по прецеденту resolve_question (GET → set selected_option → PUT) → F9/canonize ×5. После: канон 6/6, отчёт по всем NPC.
- **P5 (мелочь).** block8_probe секция A печатает `per_npc: null` для LIVE (in-process B — норма): скорее всего неверная форма (list vs dict) в пробнике — починить печать.
- **P6 (опция).** Пробелы п.12/п.16 у Орма — рекомендация Мастеру: догнать разложение (повтор Ctrl+G по недостающим пунктам или ручные записи).

## 6. План BLOCK 10 (диагностика + серверный фикс; код пишешь ты)

- **§0** alive-check бэкенда.
- **§1 Безопасный репро 500** (не трогая живые данные): зеркало структуры во временный каталог (`tmp/config/npc/chronicles` + `tmp/saves/silver_wolf/chronicle_drafts`), store на копиях; вызвать ровно то, что зовёт POST-эндпоинт (grep routes_chronicle), try/except → traceback.print_exc(). Репро — в СВЕЖЕМ питон-процессе на КАЖДОГО падающего NPC (подозрение на отравление состояния после первого краша: borko — первый упавший и единственный с файлом; остальные 4 падают без файлов — возможно, крашатся раньше по испорченному состоянию). Если store игнорирует аргументы конструктора и ходит по BASE_DIR — план Б: полный .bak обеих директорий → репро in-place → восстановление.
- **§2** Печать кодовых зон с номерами строк: canonize-эндпоинт (routes_chronicle) + метод валидации store (где живёт проверка открытых вопросов; где LLM_DRAFT→422 — воспроизвести тот raise-стиль для вопросов).
- **§3 Патч** (.bak-block10, py_compile, автооткат): неразрешённые вопросы → HTTPException 422 + русский fix_hint; валидация ДО save_canonical (никаких частичных файлов). Семантику Save=Contract НЕ ослаблять.
- **§4 Рестарт бэкенда.** Патч серверный — поднятый uvicorn несёт старый код. Рекомендуемый сценарий: блок печатает Мастеру «перезапусти uvicorn (Ctrl+C в его консоли, затем запусти снова) и прогони этот блок ещё раз — продолжит с §5» (идемпотентность). Альтернатива — убить процесс по порту 8000 и поднять фоном (Get-NetTCPConnection → Stop-Process → Start-Process), на твой выбор; консоль Мастера молча не рубить.
- **§5 Разбор с guard_borko.json**: таймстампы (происхождение), решение (удалить с .bak-block10 / оставить до re-канонизации), проверка «нет canon-файлов с entries=0».
- **§6 Валидация через LIVE**: re-run `scripts/fix_confirm_canonize_http.py` (на стороне Мастера; он всегда POST-ит canonize всем — orm перескочит на v2, это безвредно; можно добавить skip «канон уже есть») → ожидание: orm 200 (v2), остальные 5 → **чистый 422 со списком вопросов** (до P4). Затем `scripts/block8_probe.py`: отчёт (Борко выпадет из канона, если файл удалили — items упадёт с 49 до 21, это норма), сеялка без изменений.

Дальше: **BLOCK 11** = P4 (вопросы → canonize ×5 → полный отчёт 6/6 NPC); **BLOCK 12** = P3 (сеялка: beliefs/relationships + энд-ту-энд «новая игра»); **BLOCK 13 (опция)** = P6. Хвосты архитекторов (accept-UI per-entry, рантайм-половина canon-sync `tests/gameplay/test_p2_canon_sync.py`) — отдельные задачи, не смешивать.

Референс-сниппет для §1 (адаптируй по результатам grep):

```python
import inspect, shutil, sys, tempfile, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core.config import BASE_DIR

tmp = Path(tempfile.mkdtemp(prefix="cch_repro_"))
canon_t = tmp / "config" / "npc" / "chronicles"; canon_t.mkdir(parents=True)
saves_t = tmp / "saves" / "silver_wolf" / "chronicle_drafts"; saves_t.mkdir(parents=True)
for p in (BASE_DIR / "config" / "npc" / "chronicles").glob("*.json"):
    shutil.copy(p, canon_t / p.name)
for p in (BASE_DIR / "saves" / "silver_wolf" / "chronicle_drafts").glob("*.json"):
    shutil.copy(p, saves_t / p.name)

# импорт store — точный из grep routes_chronicle; ПЕРЕД вызовом:
# print("sig ChronicleStore:", inspect.signature(ChronicleStore))
store = ChronicleStore(canon_t, saves_t)  # сверить с распечатанной сигнатурой!
try:
    store.canonize("silver_wolf", "thief_shadow")  # метод — как в эндпоинте; thief_shadow — минимальный (35 записей, 1 вопрос)
    print("no crash?!")
except Exception:
    traceback.print_exc()
```

## 7. Известные НЕ-баги (не тратить сессию)

- URL'ы во frontend/api.py все верные (подозрение снято).
- `routes_chronicle.py:172` — алиас, не дубль.
- roster/understanding отвечают 200 OK.
- Статический тест canon-sync GREEN.
- Отсутствует рантайм `tests/gameplay/test_p2_canon_sync.py` — хвост, вне цепочки.
- `[SCHEMA] No subscribers for TICK_COMPLETED` — вне цепочки, не блокирует.
- «Сеялка не работает» BLOCK 7 была багом пробника (забыт аргумент npc_id) — пробник уже исправлен (block8_probe.py, секция C).
- 500 при canonize — НЕ фронт: PUT 200 прошёл у всех; это серверный путь.

## 8. Исторические уроки (цена ошибок уже уплачена)

1. Бэкенд может быть не поднят → alive-check либо in-process.
2. Фильтры каталогов: безаякорный `^\.?venv` (`.venv311` пропускался анкером).
3. `python -c`: снаружи двойные кавычки, внутри одинарные.
4. UTF-8 JSON через urllib; Invoke-RestMethod портит кодировку.
5. Write-Host — ASCII; питон-печать — с явным UTF-8.
6. Here-string `@'...'@` с вложенным питоном — без интерполяции; хвостовые пустые строки срезать.
7. После каждого патча py_compile + автооткат из .bak; идемпотентные guard'ы.
8. `inspect.signature` перед вызовом незнакомых API.
9. Патч бэкенда ⇒ рестарт uvicorn; патч фронта ⇒ перезапуск редактора (старый процесс держит старый код).
10. Флип LLM_DRAFT→AUTHOR_* обязан снимать confidence (domain:231) — уже учтено в confirm_author_entries.

## 9. Песочница и артефакты

- `/home/z/my-project/worklog.md` — общий журнал: читать ПЕРВЫМ. Записи: intake-материалы Мастера (протокольные доки на диске: РЕЖИМ РАБОТЫ, Правила Фикса БАГОВ, АРХИТЕКТУРНЫЙ УСТАВ, ENIGMA_ROADMAP_v4_7_EPI, DTO Registry, 00_CAUSAL_CONTRACT_v3.0), BLOCK 5–9, разбор результатов BLOCK 9.
- `/home/z/my-project/scripts/` — архив блоков: block5, block6_canon_e2e, block7_diag, block8_confirm_canonize, block9_f9_confirm_canonize (+ служебные validate_*/smoke_*).
- `/home/z/my-project/download/TZ_preemniku_CCH_block10.md` — этот документ.
- На стороне Мастера (Windows): `scripts/fix_confirm_canonize_http.py` (данные через LIVE), `scripts/block8_probe.py` (проверка A/B/C), бэкапы `*.bak-block8` (данные), `*.bak-block9` (api.py, chronicle_app.py).

## 10. Критерии готовности (когда всё сделано)

1. POST canonize с неразрешёнными вопросами → 422 + русский fix_hint; никаких 500 и никаких частичных canon-файлов.
2. В каноне нет мусора (entries=0 при canonical=True); запись только после успешной валидации.
3. 6/6 NPC в каноне: entries>0, provenance=AUTHOR_CONFIRMED, без confidence, version≥1.
4. Отчёт понимания покрывает всех 6 NPC, каждый пункт Все.md имеет вердикт ✓/~/✗; доля ✓ растёт (у Орма уже 11/21).
5. build_full_seed по каждому NPC: memories>0, beliefs>0, relationships>0; варнинги [CCH_SEED] — только обоснованные; «новая игра» реально несёт сид в игру (гейт npc_loader).
6. UI-цикл: Ctrl+G → C (вопросы) → F9 = «подтвердить и канонизовать» → канон обновился, Ctrl+U показывает отчёт.
7. Дисциплина: после каждого блока — worklog + архив; .bak-и на месте; вопросов Мастеру — ноль, кроме распечатанных развилок с рекомендацией.
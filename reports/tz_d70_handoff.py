# -*- coding: utf-8 -*-
# ============================================================================
# S356 — ПЕРЕДАЧА ПРЕЕМНИКУ (закрытие сессии, ветвь Б):
#   1) файл ТЗ  docs/Почти Актуальные TZ/ТЗ_COV-1_ПЕРЕДАЧА_преемнику_D70.md
#   2) строка в реестре §1.3 roadmap (после последней строки таблицы)
# Протокол: fail-before-write — оба гейта до первой записи; несовпадение = [ABORT].
# Запуск из корня репозитория:  python reports/tz_d70_handoff.py
# ============================================================================
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ROOT = Path.cwd()
TZ_DIR = ROOT / 'docs' / 'Почти Актуальные TZ'
TZ_FILE = TZ_DIR / 'ТЗ_COV-1_ПЕРЕДАЧА_преемнику_D70.md'
ROADMAP = ROOT / 'docs' / 'ENIGMA_ROADMAP_v4_7_EPI-updated.md'

ANCHOR = ('| `«Замыкание игровой петли» (Loop Closure).md` (LC-1 addendum, '
          'решения владельца) | §0.2 Ступень LC; §15 | LC-IMPL-1 — немедленно; '
          'LC-IMPL-2/3 — после GC-01→02→27; гейты LC-GC — §9.3c |')
ROW = ('| `ТЗ_COV-1_ПЕРЕДАЧА_преемнику_D70.md` | §0.2 Ступень COV; §17.5/§17.8; '
       'ADR-O-426 | Активен — Шаг 4 D70 (fail-loud старт-гейт); после D70 — '
       'Шаг 5 D72 (replay-бюджет) |')

TZ_TEXT = '''# ТЗ COV-1: Передаточный акт преемнику — Шаг 4 (D70, fail-loud старт-гейт)

> **Предшественник:** S356, ветвь Б («Честный сброс»); серия D60 закрыта 2026-10-17 (доки — коммит 821fb59d). Письмо №6 в ЗАВЕЩАНИИ уже написано — не дублируй; твоё будет №7 после твоей серии.
> **Приёмник:** следующая сессия ветви Б. Букву ветви сообщает Мастер (§R.1) — самостоятельно выбирать/менять ветвь запрещено.
> **Статус этого ТЗ:** активен; якорь — §0.2 Ступень COV; исполнен и верифицирован → удалить по §1.3 п.2 (git rm + снять строку §1.3; MUTATIONS-строка ступени фиксирует удаление).

## 1. Что уже сделано до тебя (канон, не переоткрывай — читай)

Трек ADR-O-426 «COV-1: персистентность, миграции и надёжность старта» — поэтапно, Шаги 1–3 закрыты:

- **Шаг 1 D58 ✅** — MigrationRunner (PRAGMA user_version) + реестр миграций + bootstrap + бэкап + стампинг живых БД + `lint_sqlite_registry`/INV-SQLITE-REGISTRY; COV-GC-01 GREEN. Коммиты 813407e9/450931cd/d1a7a5de/83e316b5. Живой инвентарь: 3 файла-семейства (enigma_memory 8 таблиц, enigma_runtime state_kv, replay 6 таблиц).
- **Шаг 2 D59 ✅ (S354)** — save-версионирование «детект-и-мигрировать»: детектор CURRENT/MIGRABLE/UNMIGRABLE (8 причин отказа), миграции v0→v1, `.bak` + побайтовая верификация. Код f51cc6ae, тесты 5d0748ab, pytest 42/42. IMPACT §9.
- **Шаг 3 D60 ✅ (S356)** — reset_campaign fail-loud: класс `CampaignResetError` (campaign_id/step/detail; машиночитаемое сообщение — В7), 15 сайтов immediate-interrupt (log остаётся → raise from e), фикс биндинга `_mem_reset`, П1-18 passthrough, маршрут new_game → HTTPException 500 dict-detail. Код d67e9eda, тесты 0633ed0c (14), доки 821fb59d; pytest 44/44 совместно с D59. IMPACT §10; Письмо №6.
- **COV-GC-02 закрыт полностью** (три критерия: конверсия/честный отказ + поле-версии — S354; fail-loud reset — S356).

Канон шагов: roadmap §17.5 (порядок/зависимости), §17.8 (чеклист шагов), §7.10 (реестр находок), §9.3f (гейты); IMPACT-аудит `docs/audits/ADR-O-426_IMPACT.md` §8–§10 — читай целиком перед дизайном; MUTATIONS S354/S356; атлас O-426 Status.

## 2. Твоя задача: Шаг 4 — D70, fail-loud старт-гейт

Находка COV-D70 (roadmap §7.10, дословно): стартап fail-silent по умолчанию —

- `schema_validator.validate_all_schemas` не блокирует («в будущем RuntimeError», schema_validator.py:56-61);
- readiness.py — устаревший хардкод-отчёт (:20-23);
- pydantic extra=ignore глотает опечатки env (config.py:182);
- единого конфиг-гейта старта нет.

Цель — та же грань честности, что D59 (сейв) и D60 (сброс): **старт обязан либо доехать до живого мира, либо громко отказать с машиночитаемой причиной — старт не притворяется.** Формулировка гейта и объём — §9.3f/§17.5 живыми строками; ТЗ здесь — «как», roadmap — «что/почему».

Шаг 5 после тебя: D72 replay-бюджет (вход живой: replay.db ~436 МБ по замеру Шага 1 — сверь свежесть).

## 3. Протокол входа (по РЕЖИМ РАБОТЫ.md; порядок не сокращай)

1. Буква ветви — от Мастера. Ветвь Б: шапка roadmap (слои 0–12, сквозной закон) → §0.3 (истины/принципы) → §R целиком → §R.2 (зоны) + §R.4 (лестница Б) → это ТЗ + все §1.3-строки с якорем Ступени COV → ТЗ открываются ЦЕЛИКОМ.
2. IPT-базлайн: `python backend/tests/IPT.py 2>&1 | Select-Object -Last 10` — сейчас **53 passed / 0 skipped / 0 failed**; нет строки ИТОГО = INVALID RUN (§3.12). При CRITICAL работа над фичей запрещена.
3. Археология §3.6: schema_validator.py, readiness.py, config.py + Owner Discovery — кто зовёт валидацию при старте (build_game_loop / init_campaign), читатели/писатели каждого узла.
4. ADR-PRE-FLIGHT §13: перед правкой файла проверь его в Files-списках ADR (атлас `docs/ADR (Architecture Decision Records).md`); стартовые/конфиг-файлы могли попасть в чужие списки — гейт обязателен.
5. Дизайн-прецеденты: машиночитаемый отказ — S322 (ContractValidationError), S354 (load_refusal_reason), S356 (CampaignResetError; В7); fail-loud без молчаливой подмены — табу O-426.
6. Патчи §4 (Файл / БЫЛО / СТАЛО / IPT / КРАСНЫЕ ИНВАРИАНТЫ) → smoke §3.9 → микро-тесты → IPT после каждого патча.
7. Закрытие серии (паттерн S354/S356): MUTATIONS (следующий номер = max живого реестра + 1; сейчас реестр 237 записей, максимум S356 → твой S357, если параллельная сессия не вписалась раньше — гейт в момент записи) + roadmap (§7.10 статус D70, §17.8 Шаг 4, §10 журнал, трек COV в таблице §0.2-обзора) + IMPACT §11 + атлас Status O-426 + письмо №7 в ЗАВЕЩАНИЕ (append-only, после подписи S356) + удаление этого ТЗ (§1.3 п.2). Прецедент док-закрытия скриптом: `reports/d60_close.py`.

## 4. Красные инварианты (кратко; полные тексты — в первоисточниках)

- Один фикс → один коммит → один тест; IPT до закрытия шага.
- Терминальный коммит только `git commit -- <pathspec>`; amend запрещён (инцидент S318).
- O-403: порядок 13 операций reset 1→12; board_state.json в reset-списке — НЕ удалять; фасады GameLoop не трогать.
- O-426: молчаливая подмена запрещена; машиночитаемость В7; новое ADR не создавать — IMPACT-аддендум (паттерн S354/S356).
- Устав §4.2: SQLite runtime truth; all-or-nothing; JSON-fallback читает только своё.
- Observability never mutates; MockProvider запрещён; KernelRNG; LOG-GATE.
- Anti-Race: S-номер = max(диска)+1 перед записью; правки только в зонах своей ветви (§R.2); общие файлы — построчно, чужие строки не трогать.

## 5. Хвосты и вердикты Мастера (НЕ твои решения — не трогай без вердикта)

- Косметика вне скоупа D60 (7 позиций; зафиксирована в IMPACT §10 «Вне скоупа»): мислейбл «Atomic commit:» в логе шага 2 reset; дубль нумерации шагов 7/12; `_current_campaign_id` выставляется до reset; YAML-узел CampaignLifecycle отсутствует в топологии; дубли constraints в ARCHITECTURE_FLOW_GENERATED; комментарий пути сессий (saves/<cid>.json vs «saves/<cid>/session.json»); `_load_sessions_from_disk` читает все .json в saves/.
- LLM_RESILIENCE_V1 default OFF → ON — вердикт Мастера (очередь D62).
- Параллельная сессия **S355-EPI-0** (ветвь А, doc-only, EPI-0): в живом реестре отсутствует; git-ветка S355-EPI-0 в этом клоне НЕ найдена (проверено 2026-10-17); разводка при слиянии — на Мастере.
- Артефакты серии D60: `reports/d60_close.py` (скрипт док-закрытия — живой прецедент) и `_d60_backup/` (бэкапы 5 доков; после приёмки Мастера можно удалить).

## 6. Живые метрики на момент передачи (2026-10-17)

- IPT: 53/0/0 (четыре прогона за серию — стабилен).
- Микро-тесты: D59 30 + D60 14 = 44 passed (1.55s).
- Реестр MUTATIONS: 237 записей, максимум S356.
- Ветка git: V.0.5.4.3.7_тесты_1; HEAD = 821fb59d (доки D60).

## 7. Как убедиться, что D60 вообще был (проверка преемника на живом диске)

Урони мир на втором шаге сброса (monkeypatch владельца sqlite_persistence) — до D60 был warning и полусброшенный мир; после — `CampaignResetError` с полями campaign_id/step/detail и HTTP 500 dict-detail от new_game. Тест-прецедент: `backend/tests/micro/test_d60_reset_fail_loud.py` (14 тестов; TestHappyPath/TestImmediateInterrupt/TestMachineReadable/TestRouteTranslation).

Сброс не обязан доходить до конца. Но если игра сказала «мир сброшен» — мир обязан быть пустым. Твоя грань той же честности: если игра сказала «мир запущен» — мир обязан быть живым, а не вежливо мёртвым.
'''


def die(msg):
    print('[ABORT] ' + msg)
    sys.exit(1)


print('=== S356 → S357: передача ТЗ D70 (гейты fail-before-write) ===')
if not TZ_DIR.is_dir():
    die('корпус ТЗ не найден: %s (запуск из корня репозитория?)' % TZ_DIR)
if TZ_FILE.exists():
    die('ТЗ уже существует: %s' % TZ_FILE)
if not ROADMAP.is_file():
    die('roadmap не найден: %s' % ROADMAP)

rt = ROADMAP.read_bytes().decode('utf-8')
n_anchor = rt.count(ANCHOR)
if n_anchor != 1:
    die('гейт G1 якорь §1.3 (последняя строка таблицы): вхождений %d, '
        'ожидалось 1' % n_anchor)
print('  [GATE OK] G1 якорь §1.3 уникален')
if 'ТЗ_COV-1_ПЕРЕДАЧА_преемнику_D70' in rt:
    die('гейт G2: строка ТЗ D70 уже есть в §1.3 — повторная регистрация')
print('  [GATE OK] G2 имя ТЗ в roadmap отсутствует (слот свободен)')

nl = '\r\n' if '\r\n' in rt else '\n'
TZ_FILE.write_bytes(TZ_TEXT.replace('\n', nl).encode('utf-8'))
print('  [WRITE] %s (%d байт)' % (TZ_FILE, TZ_FILE.stat().st_size))

i = rt.index(ANCHOR) + len(ANCHOR)
rt = rt[:i] + nl + ROW + rt[i:]
ROADMAP.write_bytes(rt.encode('utf-8'))
print('  [EDIT] roadmap §1.3: строка ТЗ D70 (после строки LC)')

print('=== Пост-сверка ===')
rt2 = ROADMAP.read_bytes().decode('utf-8')
checks = [
    ('строк-вхождений имени ТЗ в roadmap', rt2.count('ТЗ_COV-1_ПЕРЕДАЧА_преемнику_D70'), 1),
    ('якорь §1.3 на месте (1)', rt2.count(ANCHOR), 1),
    ('ТЗ-файл существует', 1 if TZ_FILE.is_file() else 0, 1),
    ('ТЗ-файл > 5000 байт', 1 if TZ_FILE.stat().st_size > 5000 else 0, 1),
    ('ТЗ: маркер D70 в тексте', 1 if 'D70' in TZ_FILE.read_bytes().decode('utf-8') else 0, 1),
]
ok = True
for name, got, exp in checks:
    mark = 'OK' if got == exp else 'FAIL'
    if got != exp:
        ok = False
    print('  [%s] %s: %s (ожидалось %s)' % (mark, name, got, exp))
if not ok:
    die('пост-сверка не сошлась — roadmap откатить: убрать строку ТЗ из §1.3, '
        'удалить %s' % TZ_FILE)

print('=== ПЕРЕДАЧА ОФОРМЛЕНА: ТЗ D70 зарегистрирован (файл + §1.3) ===')
print('Опционально (вердикт Мастера) — git-след передачи:')
print('  git add -- "docs/Почти Актуальные TZ/ТЗ_COV-1_ПЕРЕДАЧА_преемнику_D70.md" '
      '"docs/ENIGMA_ROADMAP_v4_7_EPI-updated.md"')
print('  git commit -m "S356: передаточный ТЗ преемнику D70 (COV-1 Шаг 4) + '
      'регистрация §1.3" -- <те же два pathspec>')

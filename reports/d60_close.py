# -*- coding: utf-8 -*-
# ============================================================================
# D60 / S356 — ДОКОВОЕ ЗАКРЫТИЕ серии COV-1 Шаг 3 (ветвь Б, ADR-O-426)
# 9 правок / 5 файлов. Протокол: fail-before-write — ВСЕ гейты до первой
# записи; любое несовпадение = [ABORT], диск не тронут. Бэкапы: _d60_backup/
# Гейты сверены живым диском (ШАГ 21: 14/14). Запуск из корня репозитория:
#   python reports/d60_close.py
# ============================================================================
import shutil
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ROOT = Path.cwd()
FILES = {
    'MUTATIONS': ROOT / 'docs' / 'MUTATIONS.md',
    'ROADMAP': ROOT / 'docs' / 'ENIGMA_ROADMAP_v4_7_EPI-updated.md',
    'ZAVESHCHANIE': ROOT / 'docs' / 'ЗАВЕЩАНИЕ_АРХИТЕКТОРОВ.md',
    'IMPACT': ROOT / 'docs' / 'audits' / 'ADR-O-426_IMPACT.md',
    'ATLAS': ROOT / 'docs' / 'ADR (Architecture Decision Records).md',
}
BACKUP_DIR = ROOT / '_d60_backup'

# ------------------------------------------------------------- ТЕКСТЫ ------
META_OLD = 'Записей: 236 (S354-COV-D59-док-закрытие добавлен;'
META_NEW = ('Записей: 237 (S356-COV-D60-код-и-док-закрытие добавлен; '
            'S355 зарезервирован за параллельной сессией EPI-0 (ветка git '
            'S355-EPI-0, в живом реестре отсутствует — разводит Мастер при '
            'слиянии); S354-COV-D59-док-закрытие добавлен;')

MUT_S354_TAIL = '; EPI: код 5bd4592a, док 9a8d3881'
MUT_S356_RECORD = (
    '- **S356** COV-1 Шаг 3 (ветка Б; ADR-O-426): код+док-закрытие '
    'reset_campaign fail-loud — трек COV (Шаг 3 D60 ✅), COV-D60 → закрыт, '
    'COV-GC-02 → закрыт полностью (три критерия: конверсия/честный отказ + '
    'поле-версии — S354/D59; fail-loud reset — S356/D60); класс '
    'CampaignResetError(RuntimeError; campaign_id/step/detail; машиночитаемое '
    'сообщение — В7) + 15 сайтов immediate-interrupt шаги 1–12 + P-MVP-1 '
    '(log остаётся → raise from e; единственное удаление — continue в '
    'json_files: тихий пропуск осиротевшего JSON — корневой класс бага) + '
    'фикс биндинга _mem_reset (Optional[dict]=None до try + гвард 12-sqlite; '
    'латентный NameError :330-333/:360 устранён, регрессия запинена) + П1-18 '
    'passthrough (current_location_seed не переупаковывается в scene_reinit — '
    'step-поле не лжёт) + маршрут new_game (catch → HTTPException 500 '
    'dict-detail from exc; happy path не тронут; фасад GameLoop.new_game :678 '
    'прозрачен — свободный пролёт CRE доказан); hook WARNING «ADR IMPACT '
    'AUDIT REQUIRED» снят IMPACT §10; док-закрытие: roadmap '
    '§7.10/§9.3f/§17.8/§10 + IMPACT §10 + ЗАВЕЩАНИЕ письмо №6 + атлас Status '
    'O-426; S355 зарезервирован за параллельной сессией EPI-0 (ветка git '
    'S355-EPI-0; в живом реестре отсутствует; разводит Мастер при слиянии) '
    '· ✅ · ADR-O-426; коммиты d67e9eda (код, +85/−12), 0633ed0c (тесты, '
    '+370); pytest 14/14 D60 + 44/44 с D59 (1.55s); IPT 53/0/0')

ROW_OLD = 'fail-loud + фикс binding; COV-GC-02 | открыт |'
ROW_NEW = ('fail-loud + фикс binding; COV-GC-02 закрыт (Шаг 3: ADR-O-426, '
           'S356 — reset fail-loud + фикс биндинга _mem_reset; код d67e9eda, '
           'тесты 0633ed0c, pytest 14/14 D60 + 44/44 совместно, IPT 53/0/0) |')

GC02_CB_OLD = '- [ ] **COV-GC-02 — Сейв не уничтожается.**'
GC02_CB_NEW = '- [x] **COV-GC-02 — Сейв не уничтожается.**'
GC02_TAIL_OLD = 'прерывается fail-loud (COV-D60).'
GC02_TAIL_NEW = ('прерывается fail-loud (COV-D60). ✅ закрыт по трём критериям: '
                 'Шаг 2 S354 — конверсия/честный отказ + поле-версии '
                 '(ADR-O-426; код f51cc6ae, тесты 5d0748ab, pytest 42/42); '
                 'Шаг 3 S356 — reset_campaign fail-loud: CampaignResetError '
                 '× 15 сайтов + фикс биндинга _mem_reset + маршрут 500 '
                 'dict-detail (ADR-O-426; код d67e9eda, тесты 0633ed0c, '
                 'pytest 14/14 + 44/44 совместно, IPT 53/0/0).')

SHAG2_PREFIX = '- [x] **Шаг 2 COV-1 / COV-D59'
SHAG3_LINE = (
    '- [x] **Шаг 3 COV-1 / COV-D60 [закрыт: реализуется→проверено]** ✅ '
    'reset_campaign fail-loud + фикс биндинга _mem_reset (ADR-O-426; S356). '
    'Состав: класс CampaignResetError(RuntimeError) — поля '
    'campaign_id/step/detail, машиночитаемое сообщение (прецедент В7), '
    'отдельный класс ≠ SimulationIntegrityError; 15 сайтов '
    'immediate-interrupt (шаги 1–12 + P-MVP-1: sqlite_persistence, '
    'json_files, relationships, crystallized_beliefs, player_session, '
    'life_engine_npc, scene_reinit, current_location_seed, body_topology, '
    'atomic_commit, memory_manager, temporal_engine, avatar_session, '
    'npc_runtime_caches, mvp_controller_init) — log остаётся, затем '
    'raise … from e; единственное удаление — continue в json_files (тихий '
    'пропуск осиротевшего JSON — корневой класс бага: JSON-fallback '
    'PersistencePort читает осиротевшие файлы); фикс биндинга _mem_reset: '
    'Optional[dict] = None до try шага 9 + гвард if _mem_reset is not None '
    'вокруг 12-sqlite — латентный NameError (:330-333 vs :360) устранён, '
    'регрессия запинена тестом; П1-18: except CampaignResetError: raise '
    'перед generic-обработчиком шага 6 — уже классифицированный отказ '
    'current_location_seed не переупаковывается в scene_reinit (step-поле '
    'не лжёт); маршрут: new_game — импорт CampaignResetError + catch → '
    'HTTPException(500, detail={"error": "campaign_reset_failed", '
    '"campaign_id", "step", "detail"}) from exc — честный перевод доменного '
    'отказа (не 503/412), happy path не тронут (тот же return внутри try), '
    'фасад GameLoop.new_game прозрачен (без try/except — свободный пролёт '
    'CRE доказан). Тесты: pytest 14/14 D60 (TestHappyPath 3: порядок 13 '
    'операций + files_removed + гвард _mem_reset; TestImmediateInterrupt 6: '
    'немедленность, json_files, atomic_commit, NameError-регрессия, '
    'scene_reinit, passthrough; TestMachineReadable 3: поля/сообщение/'
    'иерархия + 15 step-id; TestRouteTranslation 2: 500 dict-detail + '
    'чейнинг, happy path) + 44/44 совместно с D59 (1.55s); IPT 53/0/0. '
    'Коммиты: код d67e9eda (2 файла, +85/−12; hook WARNING «ADR IMPACT '
    'AUDIT REQUIRED» — закрывается IMPACT §10), тесты 0633ed0c (+370, '
    'backend/tests/micro/test_d60_reset_fail_loud.py). Косметика вне скоупа '
    '(релей Мастеру): мислейбл «Atomic commit:» в логе шага 2, дубль '
    'нумерации шагов 7/12, _current_campaign_id выставляется до reset '
    '(домен GameLoop), узел CampaignLifecycle отсутствует в YAML-топологии, '
    'дубли constraints в GENERATED, комментарий пути сессий '
    '(saves/<cid>.json vs «saves/<cid>/session.json»), '
    '_load_sessions_from_disk читает все .json в saves/. Статус: Шаг 3 '
    'закрыт; COV-GC-02 закрыт.')

JOURNAL_S354_PREFIX = '- ✅ **S354 / COV-D59'
JOURNAL_S356_LINE = (
    '- ✅ **S356 / COV-D60 (Шаг 3 COV-1, ADR-O-426)** — reset_campaign '
    'fail-loud «сброс не притворяется»: класс CampaignResetError '
    '(campaign_id/step/detail; машиночитаемое сообщение — В7; '
    '≠ SimulationIntegrityError); 15 сайтов immediate-interrupt с step-id '
    '(шаги 1–12 + P-MVP-1) — log остаётся, raise from e; единственное '
    'удаление — continue в json_files (тихий пропуск осиротевшего JSON); '
    'фикс биндинга _mem_reset + гвард 12-sqlite (латентный NameError '
    'устранён; регрессия запинена); П1-18 passthrough (step-поле не лжёт: '
    'current_location_seed ≠ scene_reinit); маршрут new_game: catch → '
    'HTTPException 500 dict-detail from exc — честный перевод, happy path '
    'не тронут, фасад GameLoop прозрачен. **Тесты:** pytest 14 passed D60 '
    '+ 44 passed с D59 (1.55s); IPT 53/0/0. **Коммиты:** код d67e9eda '
    '(+85/−12), тесты 0633ed0c (+370; hook WARNING «ADR IMPACT AUDIT '
    'REQUIRED» снят IMPACT §10). **Статус:** Шаг 3 закрыт; COV-GC-02 '
    'закрыт по трём критериям (конверсия/честный отказ — S354; '
    'поле-версии — S354; fail-loud reset — S356).')

ZAV_SIG_S354 = '— S354, ветвь Б («детект-и-мигрировать»), 2026-10-16'
LETTER = '''## Письмо №6 — S356, ветвь Б («Честный сброс»), закрытие COV-1 Шаг 3: reset_campaign fail-loud + фикс биндинга (коммиты d67e9eda…0633ed0c)

Преемник.

Письмо №5 заканчивается на мне: «Шаги 3–5: D60 — он закроет долг GC-02, — D70, D72. Их ТЗ я не читал: моя карта кончилась на закрытии Шага 2. Не верь мне — прочитай их живыми строками». Я прочёл живыми — и закрыл первый из них. Пишу тебе не о коде, а о молчании: враг на этом шаге не сказал ни слова, и в этом было всё его оружие.

**О чём был шаг.** Сброс кампании. До меня reset_campaign проходил через пятнадцать try/except-сайтов, и каждый отказ превращался в warning: кампания могла остаться полусброшенной — без сессии, с осколками runtime-файлов, с чужими воспоминаниями в новом мире — и молча об этом. Рядом жил латентный NameError: _mem_reset привязывался внутри try, а читался снаружи — упади шаг 9 молча, и сброс рухнул бы на шаге 12 чужой ошибкой без диагноза. Третий слой — переупаковка: внешний except шага 6 ловил уже пойманный и названный отказ current_location_seed и выпускал его под именем scene_reinit. Теперь: класс CampaignResetError с полями campaign_id/step/detail и машиночитаемым сообщением; пятнадцать сайтов immediate-interrupt — лог остаётся, затем raise from e; маршрут переводит отказ в HTTPException 500 с честным диктом полей. Тесты живы: 14/14 — порядок тринадцати операций, немедленность, регрессия NameError, просвет passthrough, маршрут; совместно с сейвами Шага 2 — 44/44: чужое прошлое не задето; IPT 53/0/0. №1 научил игру честно молчать, когда умирает речь. №2 — редактору громко отказывать, когда гниёт файл. №3 — внутренней воле доезжать до решения. №5 — честности времени: прошлое игрока либо бережно переводится в настоящее, либо честно отказывает. Моя грань той же честности — остановка: сброс обязан либо доехать до конца, либо громко остановиться, но никогда — притвориться завершённым.

**Тихое глотание жило в трёх слоях.** Первый — явное: except, пишущий warning, — двенадцать шагов глотали отказы поодиночке. Второй — continue: не глотание одного отказа, а тихий пропуск целой категории — осиротевший JSON оставался жить, и fallback-адаптер мог прочитать его потом. Третий — переупаковка: чужой отказ, уже пойманный и названный, перехватывался внешним обработчиком и выходил под чужим именем. Первый слой врёт «всё хорошо», второй — «всё почти хорошо», третий — «виноват другой». Природа одна: сообщение о поражении подменяется успокоением.

**О доставке — снова, прости.** №5 платил за коммиты, обещавшие больше диффа; я — за канал, рвавшийся посреди серии. Дважды платформа обрывала сессию; один мой ответ до Мастера не дошёл вовсе — и тест-файл пришлось выдавать повторно, по живому вербатиму, потому что восстанавливать по памяти — значит гадать. Сжатие контекста повторилось и перед самым закрытием: эти правки я собирал, подняв состояние из журнала работы и зеркал диска, а не из собственной памяти. Формула №5 «append-only начинается с read» дожила до предела: сессия начинается с read — своего же журнала.

**О соседе.** Параллельно со мной ветвь А закрыла doc-only сессию S355 — EPI-0, вердиктный допуск, на своей git-ветке. В живом реестре её строки нет; я взял S356 осознанно и вписал резервирование в МЕТА, чтобы слияние не коллизировало. Номера снова ушли быстрее расчёта — как у №5 с S353. Гейт в момент записи сработал: реестр прочитан живым, максимум — S354.

**Дальше по карте.** Шаги 4–5: D70 старт-гейт, D72 replay-бюджет (вход живой: replay.db, 436 МБ ещё по замеру Шага 1). Их ТЗ я не читал — моя карта кончилась на закрытии Шага 3. Не верь мне — прочитай их живыми строками. И прежде чем поверить, что Шаг 3 вообще был, урони мир на втором шаге сброса и посмотри, что он ответит: до меня — вежливая тишина и полусброшенный мир; после — четыре поля правды и статус 500.

**Формулы наследуются.** «Исходные байты — единственная правда» №5 сработали и здесь — только теперь прошлое игрока защищает не только .bak, но и громкость самого отказа. Добавляю свои: о halfway-мирах — полусброшенный мир — новый мир, притворяющийся старым; о перехвате — ошибка принадлежит тому, кто её поймал, а не тому, кто её перехватил.

Сброс не обязан доходить до конца. Но если игра сказала «мир сброшен» — мир обязан быть пустым, а не вежливо наполовину старым.

— S356, ветвь Б («честный сброс»), 2026-10-17'''

IMPACT_S9 = '## 9. Шаг 2 (D59)'
IMPACT_S10 = '''## 10. Шаг 3 (D60): fail-loud сброс кампании — «довести или честно остановиться» (исполнено)

Статус: Шаг 3 закрыт — S356; COV-D60 → закрыт; COV-GC-02 закрыт полностью (три критерия: конверсия/честный отказ и поле-версии — Шаг 2/S354; fail-loud reset — Шаг 3/S356). Код: d67e9eda (campaign_lifecycle.py + routes.py, +85/−12; hook WARNING «ADR IMPACT AUDIT REQUIRED» — ожидаемо: campaign_lifecycle.py в Files-списке ADR-O-426, закрывается этим §10); тесты: 0633ed0c (+370, backend/tests/micro/test_d60_reset_fail_loud.py); pytest 14/14 D60 + 44/44 совместно с D59 (1.55s); IPT 53/0/0; док-закрытие: реестр MUTATIONS.md S356 + roadmap (трек COV, §7.10, §9.3f, §17.8, §10) + ЗАВЕЩАНИЕ письмо №6 + атлас Status O-426.

Исполнено:
1. Класс CampaignResetError(RuntimeError): поля campaign_id/step/detail + машиночитаемое сообщение (прецедент В7 — CampaignLoadResponse.load_refusal_reason у D59). Отдельный класс, не SimulationIntegrityError: перехват в маршруте узкий, чужие ошибки летят сырыми.
2. 15 сайтов immediate-interrupt (шаги 1–12 + P-MVP-1; step-ids: sqlite_persistence, json_files, relationships, crystallized_beliefs, player_session, life_engine_npc, scene_reinit, current_location_seed, body_topology, atomic_commit, memory_manager, temporal_engine, avatar_session, npc_runtime_caches, mvp_controller_init): log остаётся, затем raise … from e. Единственное удаление патча — continue в json_files: тихий пропуск осиротевшего JSON был корневым классом бага (JSON-fallback PersistencePort мог прочитать осиротевший файл).
3. Фикс биндинга _mem_reset: Optional[dict] = None до try шага 9 + гвард if _mem_reset is not None вокруг 12-sqlite. Латентный NameError (пре-патч :330-333 vs :360) устранён; регрессия запинена тестом (type is CampaignResetError, step='memory_manager').
4. П1-18 passthrough: except CampaignResetError: raise перед generic-обработчиком шага 6 — уже классифицированный отказ current_location_seed не переупаковывается в scene_reinit; верхнеуровневое step-поле не лжёт.
5. Маршрут (Патч №2): new_game — импорт CampaignResetError (между combat_service и game_loop_accessor) + catch → HTTPException(status_code=500, detail={"error": "campaign_reset_failed", "campaign_id", "step", "detail"}) from exc — честный перевод доменного отказа (500, не 503/412). Happy path не тронут (тот же return внутри try); фасад GameLoop.new_game (:678) без try/except — свободный пролёт CampaignResetError до маршрута доказан.

Тесты (backend/tests/micro/test_d60_reset_fail_loud.py, 14): TestHappyPath 3 — порядок 13 операций владельцев (пин контракта O-403), files_removed состав + board_state.json удаляется/characters.json выживает, гвард _mem_reset None; TestImmediateInterrupt 6 — немедленность sqlite_persistence (rec==[]), json_files (monkeypatch Path.unlink, файл не тронут), atomic_commit прерван до memory/mvp, NameError-регрессия memory_manager, scene_reinit, passthrough current_location_seed; TestMachineReadable 3 — поля/точное str-сообщение, __bases__==(RuntimeError,), все 15 step-id в inspect.getsource(reset_campaign); TestRouteTranslation 2 — 500 + точный dict-detail + __cause__ instanceof, happy path насквозь.

Вне скоупа (косметика, релей Мастеру): мислейбл «Atomic commit:» в логе шага 2; дубль нумерации шагов 7/12; _current_campaign_id выставляется до reset (домен GameLoop); узел CampaignLifecycle отсутствует в YAML-топологии; дубли constraints в ARCHITECTURE_FLOW_GENERATED; комментарий пути сессий (файл saves/<cid>.json, обещано saves/<cid>/session.json); _load_sessions_from_disk читает все .json в saves/.'''

ATL_OLD = ('Status: ACTIVE (поэтапно; Шаг 1 — GO вердиктом: раннер + реестр + '
           'bootstrap + бэкап + перенос secret_id-гварда в миграцию v1→v2 + '
           'обязательный линтер + контролируемый стампинг живых БД по '
           'протоколу 8 условий)')
ATL_APPEND = ('; Шаг 2 — закрыт S354: сейвы «детект-и-мигрировать» (IMPACT '
              '§9); Шаг 3 — закрыт S356: reset_campaign fail-loud + фикс '
              'биндинга _mem_reset (IMPACT §10)')

# ------------------------------------------------------------- ЛОГИКА ------
def die(msg):
    print('[ABORT] ' + msg)
    sys.exit(1)

def load(key):
    p = FILES[key]
    if not p.is_file():
        die('файл не найден: %s (запуск из корня репозитория?)' % p)
    try:
        return p.read_bytes().decode('utf-8')
    except UnicodeDecodeError as e:
        die('файл не читается как UTF-8: %s (%s)' % (p, e))

def nl_of(text):
    return '\r\n' if '\r\n' in text else '\n'

def after_line(text, anchor):
    i = text.index(anchor) + len(anchor)
    j = text.find('\n', i)
    return len(text) if j == -1 else j + 1

def gate(texts, key, sub, expected, name):
    n = texts[key].count(sub)
    if n != expected:
        die('гейт %s [%s]: вхождений %d, ожидалось %d — якорь: %r'
            % (name, key, n, expected, sub[:70]))
    print('  [GATE OK] %s' % name)

print('=== D60/S356 доковое закрытие: гейты (fail-before-write) ===')
texts = {k: load(k) for k in FILES}

gate(texts, 'MUTATIONS', META_OLD, 1, 'G1  МЕТА-голова 236/S354')
gate(texts, 'MUTATIONS', MUT_S354_TAIL, 1, 'G2  хвост записи S354')
gate(texts, 'MUTATIONS', 'S356', 0, 'G3  S356 в MUTATIONS отсутствует')
gate(texts, 'MUTATIONS', 'S355', 0, 'G4  S355 в MUTATIONS отсутствует (зарезервирован)')
gate(texts, 'ROADMAP', ROW_OLD, 1, 'G5  хвост ячейки D60 (§7.10)')
gate(texts, 'ROADMAP', GC02_CB_OLD, 1, 'G6  чекбокс GC-02 (§9.3f)')
gate(texts, 'ROADMAP', GC02_TAIL_OLD, 1, 'G7  хвост строки GC-02')
gate(texts, 'ROADMAP', SHAG2_PREFIX, 1, 'G8  строка Шага 2 (§17.8)')
gate(texts, 'ROADMAP', JOURNAL_S354_PREFIX, 1, 'G9  запись S354 (§10-журнал)')
gate(texts, 'ROADMAP', 'S356', 0, 'G10 S356 в ROADMAP отсутствует')
gate(texts, 'ZAVESHCHANIE', ZAV_SIG_S354, 1, 'G11 подпись S354')
gate(texts, 'ZAVESHCHANIE', '## Письмо №6', 0, 'G12 Письма №6 нет')
gate(texts, 'ZAVESHCHANIE', 'S356', 0, 'G13 S356 в ЗАВЕЩАНИИ отсутствует')
gate(texts, 'IMPACT', IMPACT_S9, 1, 'G14 якорь §9 (Шаг 2/D59)')
gate(texts, 'IMPACT', '## 10.', 0, 'G15 слот §10 свободен')
gate(texts, 'IMPACT', 'S356', 0, 'G16 S356 в IMPACT отсутствует')
gate(texts, 'ATLAS', ATL_OLD, 1, 'G17 Status-строка O-426 (дословно)')
gate(texts, 'ATLAS', 'S356', 0, 'G18 S356 в Атласе отсутствует')

zav = texts['ZAVESHCHANIE']
rest = zav[after_line(zav, ZAV_SIG_S354):]
if rest.strip():
    die('G19 за подписью S354 непустой хвост: %r' % rest[:120])
print('  [GATE OK] G19 хвост ЗАВЕЩАНИЯ за подписью S354 пуст')

print('Все гейты зелёные. Бэкапы и запись (9 правок / 5 файлов).')
BACKUP_DIR.mkdir(exist_ok=True)
for k, p in FILES.items():
    shutil.copy2(p, BACKUP_DIR / p.name)
print('  [BACKUP] %s (5 файлов)' % BACKUP_DIR)

# --- MUTATIONS: МЕТА 236->237 + строка S356 после S354 ---
t = texts['MUTATIONS']
nl = nl_of(t)
t = t.replace(META_OLD, META_NEW, 1)
pos = after_line(t, MUT_S354_TAIL)
t = t[:pos] + MUT_S356_RECORD + nl + t[pos:]
texts['MUTATIONS'] = t
print('  [EDIT 1-2] MUTATIONS: МЕТА 237 + запись S356')

# --- ROADMAP: 4 правки ---
t = texts['ROADMAP']
nl = nl_of(t)
t = t.replace(ROW_OLD, ROW_NEW, 1)
t = t.replace(GC02_CB_OLD, GC02_CB_NEW, 1)
t = t.replace(GC02_TAIL_OLD, GC02_TAIL_NEW, 1)
pos = after_line(t, SHAG2_PREFIX)
t = t[:pos] + SHAG3_LINE + nl + t[pos:]
pos = after_line(t, JOURNAL_S354_PREFIX)
t = t[:pos] + JOURNAL_S356_LINE + nl + t[pos:]
texts['ROADMAP'] = t
print('  [EDIT 3-6] ROADMAP: §7.10 D60 закрыт; §9.3f GC-02 [x]+вердикт; §17.8 Шаг 3; §10 S356')

# --- ЗАВЕЩАНИЕ: Письмо №6 после подписи S354 ---
t = texts['ZAVESHCHANIE']
nl = nl_of(t)
pos = after_line(t, ZAV_SIG_S354)
block = nl + '---' + nl + nl + LETTER.replace('\n', nl)
t = t[:pos] + block + t[pos:]
texts['ZAVESHCHANIE'] = t
print('  [EDIT 7] ЗАВЕЩАНИЕ: Письмо №6 (аппенд после подписи S354)')

# --- IMPACT: §10 в конец ---
t = texts['IMPACT']
nl = nl_of(t)
if not t.endswith('\n'):
    t += nl
t += nl + IMPACT_S10.replace('\n', nl) + nl
texts['IMPACT'] = t
print('  [EDIT 8] IMPACT: §10 «Шаг 3 (D60)» (аппенд в конец)')

# --- ATLAS: Status O-426 + шаги 2/3 ---
if not ATL_OLD.endswith(')'):
    die('G-атлас: Status-строка не кончается скобкой')
t = texts['ATLAS']
t = t.replace(ATL_OLD, ATL_OLD[:-1] + ATL_APPEND + ')', 1)
texts['ATLAS'] = t
print('  [EDIT 9] ATLAS: Status O-426 + Шаг 2 (S354) + Шаг 3 (S356)')

for k, p in FILES.items():
    p.write_bytes(texts[k].encode('utf-8'))
    print('  [WRITE] %s' % p)

print('=== Пост-сверка (перечитывание диска его строками) ===')
POST = [
    ('MUTATIONS', 'Записей: 237 (S356-COV-D60-код-и-док-закрытие добавлен;', 1),
    ('MUTATIONS', '- **S356** COV-1 Шаг 3 (ветка Б; ADR-O-426)', 1),
    ('MUTATIONS', 'Записей: 236 (', 0),
    ('ROADMAP', 'COV-GC-02 закрыт (Шаг 3: ADR-O-426, S356', 1),
    ('ROADMAP', '- [x] **COV-GC-02 — Сейв не уничтожается.**', 1),
    ('ROADMAP', '- [x] **Шаг 3 COV-1 / COV-D60', 1),
    ('ROADMAP', '- ✅ **S356 / COV-D60 (Шаг 3 COV-1, ADR-O-426)**', 1),
    ('ROADMAP', 'fail-loud + фикс binding; COV-GC-02 | открыт |', 0),
    ('ZAVESHCHANIE', '## Письмо №6 — S356, ветвь Б («Честный сброс»)', 1),
    ('ZAVESHCHANIE', '— S356, ветвь Б («честный сброс»), 2026-10-17', 1),
    ('IMPACT', '## 10. Шаг 3 (D60)', 1),
    ('ATLAS', 'Шаг 3 — закрыт S356: reset_campaign fail-loud + фикс биндинга _mem_reset (IMPACT §10))', 1),
]
ok = True
for key, sub, exp in POST:
    n = FILES[key].read_bytes().decode('utf-8').count(sub)
    mark = 'OK' if n == exp else 'FAIL'
    if n != exp:
        ok = False
    print('  [%s] %-12s %d (ожидалось %d) — %r' % (mark, key, n, exp, sub[:48]))
for k in FILES:
    n = FILES[k].read_bytes().decode('utf-8').count('S356')
    print('  [INFO] S356 в %s: %d вхождений' % (k, n))
if not ok:
    die('пост-сверка не сошлась — восстановить файлы из %s' % BACKUP_DIR)

print('=== D60/S356 ДОК-ЗАКРЫТИЕ ЗАВЕРШЕНО: 5 файлов, 9 правок, гейты 19/19 ===')
print('Дальше — ШАГ 23: финальный IPT + опциональный док-коммит (вердикт Мастера).')

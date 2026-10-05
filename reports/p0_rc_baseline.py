"""path: /project/reports/p0_rc_baseline.py

Назначение: P0-2 (SR-1, GO Мастера): R-c lexical baseline — ИЗМЕРИТЕЛЬНЫЙ
    КОНТРОЛЬ, не router-архитектура (вердикт: NEVER production candidate;
    результат ЗАПРЕЩЁНО использовать для наполнения R-a/R-b — иначе
    вырастет скрытый второй parser). Лексикон выведен ТОЛЬКО из контента
    semantic-модулей (leak-free: якорные фразы модулей чужды корпусу —
    «корабль»/«караванщик»). Boundary (10) прогоняются и логируются, но
    не входят в pass/fail знаменатели (Q-1 GO: boundary = диагностический
    материал, не ground truth). Основная количественная метрика SR-1 —
    PROV routing; identity — isolation/diagnostic arm (Q-2 GO, вар. а).
    Отвечает на вопрос нижней планки (печать Мастера): baseline — нижняя
    планка, oracle — верхняя, R-a/R-b — есть ли полезный зазор.
Зависимости: stdlib (ast, pathlib, typing). Импорт semantic_probe_corpus
    ЗАПРЕЩЁН (module-level start_llama_server — side-effect): корпус
    извлекается ast-парсингом. app/ не импортируется; production-эффект
    нулевой; детерминизм тривиален (чистая функция, без рандома).
Основные сущности: _PROV_LEXEMES/_ID_LEXEMES (заморожены, verbatim из
    модулей), _FAMILY_DEFAULTS + _OVERRIDES (ground truth аудита P0-1,
    заморожен вердиктами Q-1/Q-2), _PROV_CONTROL_TEXTS/_ID_CONTROL_TEXTS
    (FP-контроли корпуса), classify(), _load_corpus(),
    _assert_invariants(), main().
Запуск: python reports/p0_rc_baseline.py (из корня репозитория).
"""

import ast
from pathlib import Path
from typing import Dict, List, Tuple

_ROOT = Path(__file__).resolve().parents[1]
_CORPUS_PATH = (
    _ROOT / "backend" / "tests" / "sandbox" / "SUPERBOX"
    / "scenarios" / "semantic_probe_corpus.py"
)
_PROV_MODULE = (
    _ROOT / "backend" / "app" / "services" / "input"
    / "semantic_library" / "dialogue_provenance.md"
)
_ID_MODULE = (
    _ROOT / "backend" / "app" / "services" / "input"
    / "semantic_library" / "dialogue_identity.md"
)

# ── Лексикон (ЗАМОРОЖЕН до прогона; verbatim-токены контента модулей) ──
# provenance: перечисление определений enum-tail («кто сказал, откуда
# известно, кто сообщил, источник сведения») + глагол якорной пары
# («доложил»). identity: «зовут» (обе ноги пары), «имени» («вопрос об
# ИМЕНИ ТРЕТЬЕГО ЛИЦА»). Расширение лексикона по итогам прогона = подгон
# под ответ = инвалидация измерения (R-c = control only).
_PROV_LEXEMES: Tuple[str, ...] = (
    "сказал", "сообщил", "доложил", "откуда", "известно", "источник", "сведения",
)
_ID_LEXEMES: Tuple[str, ...] = ("зовут", "имени")

# ── Ground truth (аудит P0-1; заморожен вердиктами Q-1/Q-2) ──
# Правило по классу; отклонения — дословные тексты корпуса.
_FAMILY_DEFAULTS: Dict[str, str] = {
    "PROVENANCE": "PROV", "GEN-PROV": "PROV", "AB-PROV": "PROV",
    "IND-PROV": "PROV", "H-PROV": "PROV",
    "H-GREET": "EMPTY", "H-INTRO": "EMPTY", "H-AGGRO": "EMPTY",
    "H-ACTION": "EMPTY", "H-CHAT": "EMPTY", "SELF_INTRO": "EMPTY",
    "CORRECTION": "EMPTY", "CHALLENGE": "EMPTY", "META": "EMPTY",
    "MULTI": "EMPTY", "CONTRAST": "EMPTY", "AB-META": "EMPTY",
    "AB-3RD": "EMPTY", "AB-EDGE": "EMPTY", "IND-3RD": "EMPTY",
    "GEN-3RD": "EMPTY",
}

# Отклонения (13 записей: 10 boundary + 3 ID+).
_OVERRIDES: Dict[str, str] = {
    # boundary — диагностика, не ground truth (Q-1 GO):
    "Ты сам это узнал или тебе кто-то сказал?": "BOUNDARY",   # GEN-PROV
    "Кто ей об этом рассказал?": "BOUNDARY",                 # GEN-3RD («не назначать заранее»)
    "Ты узнал моё имя сам?": "BOUNDARY",                     # IND-PROV
    "Тебе говорили, кто ходил к Люсе?": "BOUNDARY",          # IND-3RD
    "Кто рассказал Люсе про меня?": "BOUNDARY",              # AB-EDGE (context-dependent)
    "Это я говорил?": "BOUNDARY",                            # H-PROV (META/QUESTION)
    "Ты уверен, или просто краем уха услышал?": "BOUNDARY",  # H-PROV (PROVENANCE/CHALLENGE)
    "Выдумываешь? может тебе показалось?": "BOUNDARY",       # H-PROV (CHALLENGE)
    "Я не Мю": "BOUNDARY",                                   # CONTRAST (отрицание — вне модуля, вердикт)
    "Это ты сказал? Или твоя мама?": "BOUNDARY",             # H-AGGRO (QUESTION-провокация)
    # ID+ (1 чистый + 2 multi-act компонента; Q-2 diagnostic arm):
    "Кто ты?": "ID",                    # AB-META, ASK_IDENTITY
    "Мю ВАн - а вы?": "ID",             # H-INTRO, SELF_INTRO+ASK_IDENTITY
    "Привет, я Мю. А кто ты?": "ID",    # MULTI, GREETING+SELF_INTRO+ASK_IDENTITY
}

# PROV-негативы (gold EMPTY; 12 уникальных текстов = 13 записей —
# «Ты знаешь…» встречается в META и AB-META). Встроенный FP-контроль корпуса.
_PROV_CONTROL_TEXTS: Tuple[str, ...] = (
    "Ты знаешь, что меня зовут Мю?",
    "Ты помнишь моё имя?",
    "Ты уверен, что меня зовут Мю?",
    "Кто уже разговаривал с Люсей?",
    "Кто уже трахался с Люсей?",
    "Кто с Люсей разговаривал вчера вечером?",
    "Кто-нибудь говорил с служанкой?",
    "Кто ходил к Торнину с новостями?",
    "Кто вчера был с Люсей?",
    "Кто с ней вообще разговаривал?",
    "Кто что-то делал с Люсей?",
    "Ну рассказывайте - кто уже трахался с Люсей?",
)
# ID-негативы (gold EMPTY; identity-формулировка, ожидающая QUESTION):
_ID_CONTROL_TEXTS: Tuple[str, ...] = ("Ты Мю?", "Ты ведь Мю?")

# Замороженные счётчики аудита P0-1 (сверка fail-loud):
_EXPECTED_COUNTS: Dict[str, int] = {"PROV": 22, "ID": 3, "EMPTY": 55, "BOUNDARY": 10}
_ROUTES = ("PROV", "ID", "EMPTY")


def _load_corpus() -> List[Tuple[str, str, str]]:
    """Корпус БЕЗ импорта модуля (import = запуск llama-server,
    side-effect уровня модуля). Извлечение узла CORPUS через
    ast.literal_eval — ноль побочных эффектов, fail-loud при дрейфе."""
    source = _CORPUS_PATH.read_text(encoding="utf-8-sig")
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "CORPUS" for t in node.targets
        ):
            raw = ast.literal_eval(node.value)
            return [(str(c), str(t), str(e)) for c, t, e in raw]
    raise RuntimeError(f"CORPUS не найден в {_CORPUS_PATH}")


def _gold(cls: str, text: str) -> str:
    """Gold-семья записи: default по классу, override по дословному тексту."""
    family = _OVERRIDES.get(text, _FAMILY_DEFAULTS.get(cls))
    if family is None:
        raise RuntimeError(f"нет family-правила для класса {cls!r} (текст {text!r})")
    return family


def classify(text: str) -> str:
    """R-c: покрытие лексемой (substring, lower). PROV приоритетен —
    provenance-модуль владеет регионом, identity add-only. Без порогов,
    без контекста — тупой контроль по построению (это и есть baseline)."""
    t = text.lower()
    if any(lex in t for lex in _PROV_LEXEMES):
        return "PROV"
    if any(lex in t for lex in _ID_LEXEMES):
        return "ID"
    return "EMPTY"


def _assert_invariants(entries: List[Tuple[str, str, str]]) -> None:
    """Fail-loud сверки перед измерением: счётчики gold == аудит P0-1;
    один текст — одна gold-семья; override-тексты существуют в корпусе;
    лексемы — verbatim из модулей. Дрейф корпуса/модулей останавливает
    измерение, а не тихо меняет его (L4)."""
    corpus_texts = {t for _, t, _ in entries}
    for text in _OVERRIDES:
        if text not in corpus_texts:
            raise RuntimeError(f"override-текст отсутствует в корпусе: {text!r}")
    by_text: Dict[str, str] = {}
    counts: Dict[str, int] = {}
    for cls, text, _ in entries:
        family = _gold(cls, text)
        if text in by_text and by_text[text] != family:
            raise RuntimeError(f"текст {text!r} имеет две gold-семьи")
        by_text[text] = family
        counts[family] = counts.get(family, 0) + 1
    if len(entries) != 90 or counts != _EXPECTED_COUNTS:
        raise RuntimeError(
            f"счётчики дрейфнули: {counts} "
            f"(ожидалось {_EXPECTED_COUNTS}, всего {len(entries)})"
        )
    prov_md = _PROV_MODULE.read_text(encoding="utf-8-sig").lower()
    id_md = _ID_MODULE.read_text(encoding="utf-8-sig").lower()
    for lex in _PROV_LEXEMES:
        if lex not in prov_md:
            raise RuntimeError(f"prov-лексема не из модуля: {lex!r}")
    for lex in _ID_LEXEMES:
        if lex not in id_md:
            raise RuntimeError(f"id-лексема не из модуля: {lex!r}")


def main() -> None:
    entries = _load_corpus()
    _assert_invariants(entries)

    confusion: Dict[Tuple[str, str], int] = {}
    prov_misses: List[str] = []
    id_misses: List[str] = []
    id_fps: List[str] = []
    boundary_routes: List[Tuple[str, str]] = []
    prov_fp_controls = 0
    prov_fp_other = 0
    cross_family = 0  # PROV→ID — главная ошибка (вердикт Q-2)

    for cls, text, _expected in entries:
        gold = _gold(cls, text)
        route = classify(text)
        if gold == "BOUNDARY":
            boundary_routes.append((text, route))  # логируем, не считаем (Q-1)
            continue
        confusion[(gold, route)] = confusion.get((gold, route), 0) + 1
        if gold == "PROV" and route != "PROV":
            prov_misses.append(text)
            if route == "ID":
                cross_family += 1
        if gold == "EMPTY" and route == "PROV":
            if text in _PROV_CONTROL_TEXTS:
                prov_fp_controls += 1
            else:
                prov_fp_other += 1
        if gold == "ID" and route != "ID":
            id_misses.append(text)
        if gold == "EMPTY" and route == "ID":
            id_fps.append(text)

    prov_total = sum(v for (g, _), v in confusion.items() if g == "PROV")
    id_total = sum(v for (g, _), v in confusion.items() if g == "ID")
    empty_total = sum(v for (g, _), v in confusion.items() if g == "EMPTY")
    scored = prov_total + id_total + empty_total

    print("=== P0-2: R-c LEXICAL BASELINE (measurement control, NOT architecture) ===")
    print(f"corpus: {len(entries)} | scored: {scored} | boundary: {len(boundary_routes)} (вне знаменателей)")
    print(f"gold: PROV={prov_total} ID={id_total} EMPTY={empty_total}")
    print()
    print("--- Конфьюжн (gold -> route) ---")
    for gold in ("PROV", "ID", "EMPTY"):
        cells = "  ".join(f"{r}:{confusion.get((gold, r), 0):3}" for r in _ROUTES)
        print(f"{gold:6} {cells}")
    print()
    print("--- PROV routing (основная количественная метрика SR-1) ---")
    print(f"PROV recall: {prov_total - len(prov_misses)}/{prov_total}")
    for m in prov_misses:
        print(f"  MISS: {m!r}")
    print(f"PROV FP: контрольные PROV-негативы: {prov_fp_controls} | прочие EMPTY: {prov_fp_other}")
    print(f"cross-family PROV->ID: {cross_family}")
    print()
    print("--- Identity (diagnostic arm, n=3) ---")
    print(f"ID recall: {id_total - len(id_misses)}/{id_total}")
    for m in id_misses:
        print(f"  MISS: {m!r}")
    print(f"ID FP (EMPTY->ID): {len(id_fps)}")
    for m in id_fps:
        print(f"  FP: {m!r}")
    for text in _ID_CONTROL_TEXTS:
        print(f"  ID-контроль: {text!r} -> {classify(text)} (ожидание EMPTY)")
    print()
    print("--- Boundary (диагностика, НЕ ground truth; Q-1) ---")
    for text, route in boundary_routes:
        print(f"  {text!r} -> {route}")
    print()
    print(
        f"ИТОГО P0-2: PROV recall {prov_total - len(prov_misses)}/{prov_total}, "
        f"PROV-FP {prov_fp_controls + prov_fp_other}, "
        f"ID recall {id_total - len(id_misses)}/{id_total}, ID-FP {len(id_fps)}, "
        f"cross-family {cross_family}, boundary {len(boundary_routes)} логировано"
    )


if __name__ == "__main__":
    main()
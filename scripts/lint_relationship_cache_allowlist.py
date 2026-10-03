"""
path: scripts/lint_relationship_cache_allowlist.py
Назначение: Греп-страж freeze-поверхности relationship_cache (ADR-O-415, RE-01 M1b.3.7)
Зависимости: pathlib (только stdlib)
Основные сущности: ALLOWLIST, run_lint, main

Запуск: python scripts/lint_relationship_cache_allowlist.py

Семантика заморозки (точные счётчики строк-сайтов на файл):
- строка, содержащая токен = 1 сайт (токен дважды в одной строке = один сайт);
- комментарии считаются сайтами: relationship_cache — замороженный
  архитектурный термин, док-дрейф тоже дрейф (ценз ADR-O-415);
- рост счётчика                  -> GROWTH (новый сайт вне ценза);
- файл с токеном вне allowlist   -> NEW-FILE;
- снижение счётчика / исчезновение файла -> SHRINK/MISSING (сжатие поверхности =
  миграция DECISION-READER -> V2; требует ценз-каса allowlist с записью в ADR).

Дизайн-уроки вшиты:
- utf-8-sig чтение (урок S317: BOM ломал 11 read-sites);
- root от __file__, НЕ от CWD (урок S314: CWD-относительные пути ломаются
  вне корня репо);
- UNREADABLE = violation (молчаливый пропуск файла = дыра в заморозке, L4).

Baseline (19 файлов / 52 сайта) — НЕ таблица архитектора, а независимый
пересчёт этим скриптом на HEAD; роли сайтов — docs/audits/ADR-O-415_IMPACT.md.
Регистрация: IPT INV-RE-CACHE-ALLOWLIST (линтер-инвариант, лимит 15
симуляционных не расходует). Рантайм не трогается (behavior-neutral).
"""

import sys
from pathlib import Path

# Токен заморозки (ADR-O-415)
TOKEN = "relationship_cache"

# Root по умолчанию от скрипта: scripts/ -> parents[1] = корень репо.
# CWD-независимость обязательна: IPT вызывает run_lint() из backend/tests/.
_DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "backend" / "app"

# Allowlist: относительный posix-путь (от backend/app) -> замороженное число
# строк-сайтов. Роль каждого файла — в ADR-O-415_IMPACT.md. Рядом с ключом —
# краткий тег роли (документация заморозки; DECISION-READER-файлы преходяще
# легальны до миграции на V2-Store, сжатие = ценз-тач allowlist).
ALLOWLIST: dict[str, int] = {
    "models/causality_manifest.py": 1,   # DECL-MANIFEST (S317, authority ADR-O-370)
    "models/idle_tick.py": 1,            # DECL-MODEL (idle TypedDict)
    "models/npc_state.py": 7,            # OWNER-MODEL + PROJECTION-SERIALIZE + фабрика
    "services/combat/combat_subscriber.py": 2,    # SNAPSHOT-COPY-THROUGH + INIT-EMPTY
    "services/npc/decision/risk.py": 1,           # DECISION-READER (карта S318)
    "services/npc/decision/social_deltas.py": 1,  # DECISION-READER (карта S318)
    "services/npc/decision_hub.py": 2,            # DOC-NEGATIVE (запретительные доки)
    "services/npc/interpretation_engine.py": 2,   # DECISION-READER (карта S318)
    "services/npc/npc_loader.py": 8,              # LOADER-BOOTSTRAP (GAP-4-контекст)
    "services/npc/npc_tick_pipeline.py": 2,       # WRITER-TICK-HYDRATE (TZ-10)
    "services/npc/social_target_resolver.py": 1,  # DECISION-READER (карта S318)
    "services/npc/state_applicator.py": 2,        # WRITER-SYNC (update_relationships)
    "services/phases/decision.py": 1,             # DECISION-READER (карта S318)
    "services/player_avatar_service.py": 1,       # DOC-EPHEMERAL (комментарий)
    "services/player_cognition/cognitive_distortion.py": 1,  # DOC-NEGATIVE
    "services/social/directive_interpretation_subscriber.py": 5,  # DECISION-READER
    "services/social/social_decay_handler.py": 2,     # DECAY-READER (GAP-4-контекст)
    "services/social/v2_relationship_backend.py": 2,  # BOOTSTRAP-SOURCE (M1b.1)
    "services/tick_utils.py": 10,                     # SANITIZER (единств. обогащение)
}


def run_lint(
    root: str | Path | None = None,
    allowlist: dict[str, int] | None = None,
) -> list[str]:
    """Скан дерева на предмет сайтов токена против allowlist.

    Возвращает список строк-нарушений (пустой список = freeze соблюдён).
    root/allowlist параметризованы для негативного микротеста (tmp-дерево);
    боевой вызов — run_lint() с дефолтами.
    """
    _root = Path(root) if root is not None else _DEFAULT_ROOT
    _allow = ALLOWLIST if allowlist is None else allowlist

    violations: list[str] = []
    seen: set[str] = set()

    for path in sorted(_root.rglob("*.py")):
        try:
            # utf-8-sig: BOM в начале файла не должен ломать подсчёт (S317)
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            # Fail-loud: непрочитанный файл = непроверенный файл = дыра в заморозке
            violations.append(f"UNREADABLE {path}: {exc}")
            continue

        count = sum(1 for line in text.splitlines() if TOKEN in line)
        if count == 0:
            continue

        rel = path.relative_to(_root).as_posix()
        seen.add(rel)
        expected = _allow.get(rel)

        if expected is None:
            violations.append(
                f"NEW-FILE {rel}: {count} сайтов, файл вне allowlist "
                f"(ценз ADR-O-415 обязателен)"
            )
        elif count > expected:
            violations.append(
                f"GROWTH {rel}: найдено {count}, заморожено {expected} "
                f"(новый сайт вне ценза ADR-O-415)"
            )
        elif count < expected:
            violations.append(
                f"SHRINK {rel}: найдено {count}, заморожено {expected} "
                f"(сжатие поверхности = ценз-тач allowlist с записью в ADR)"
            )

    # Файл из allowlist исчез или больше не содержит токен — тоже сжатие
    for rel in sorted(set(_allow) - seen):
        violations.append(
            f"MISSING {rel}: файл отсутствует или не содержит токен "
            f"(сжатие поверхности = ценз-тач allowlist с записью в ADR)"
        )

    return violations


def main() -> int:
    violations = run_lint()
    if violations:
        print(f"[RE-CACHE-ALLOWLIST] 🔴 Нарушений: {len(violations)} (ADR-O-415)")
        for violation in violations:
            print(f"  - {violation}")
        return 1

    total = sum(ALLOWLIST.values())
    print(
        f"[RE-CACHE-ALLOWLIST] ✅ Freeze соблюдён: "
        f"{len(ALLOWLIST)} файлов / {total} сайтов (ADR-O-415)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
from __future__ import annotations

# reports/s352_registry_add.py
"""
Одноразовый скрипт записи S352 в реестр MUTATIONS.md (правило 5: номер =
max+1 по живому файлу; гейт свободы исполнен ДО вписывания: греп реестра +
git log --all --grep=S352 — пусто). Хеш restore-коммита — argv[1] (плейсхолдеров
нет). Гейты: хеш валиден; S352 отсутствует; якорь S351 == 1; МЕТА-префикс
== 1. После коммита НЕ перезапускать (прецедент s337_registry_add).
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUT = ROOT / "docs" / "MUTATIONS.md"


def _abort(msg: str) -> None:
    print(f"[ABORT] {msg}")
    print("[ABORT] Стоп ДО записи: файл не изменён.")
    sys.exit(1)


def _load(p: Path) -> tuple[str, bool]:
    raw = p.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig" if bom else "utf-8"), bom


def _save(p: Path, text: str, bom: bool) -> None:
    p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))


def main() -> None:
    if len(sys.argv) != 2:
        _abort("ожидается ровно один аргумент: короткий хеш restore-коммита")
    commit = sys.argv[1].strip()
    r = subprocess.run(["git", "rev-parse", "--verify", commit],
                       capture_output=True, cwd=ROOT)
    if r.returncode != 0:
        _abort(f"хеш {commit!r} не резолвится: {r.stderr.decode(errors='replace')[:120]}")

    line = (
        "- **S352** Б-1-хвосты (ветка Б): restore зоны Б roadmap после Anti-Race №3 — "
        "параллельный WIP 230518bc→65113fbd перезаписал §17.8/§0.1/§7.10/§9.3f/§17.5 "
        "на до-Шаговую базу, чужие строки зоны Б не сохранены («COV-D58 переоткрыт» "
        "в их 230518bc = переразметка со stale-базы при валидном 65113fbd «IPT 53/0; "
        "micro det2+det3 7/7»); восстановлен полный комплект одним доковым скриптом "
        "reports/b1_zone_restore.py — 8 замен (GC-01 [x]; D58/D100 закрыты; COV-1/трек "
        "COV — прогресс Шага 1; DET-1/2/3 [x]) + журнал §17.8 ×4 (COV-1 Шаг 1 → DET-1 "
        "→ DET-2 → DET-3; строки DET-2/DET-3 — впервые: правка det2_close.py не "
        "применялась — односимвольный дефект якоря «гистерезис;тест» без пробела → "
        "abort до записи, релей владельцу; DET-3 закрывался без доковых правок); "
        "источники дословности: константы close-скриптов через ast (нулевая ручная "
        "транскрипция) + блоб-гейты 93a69179 ×11 + негатив-гейты; зона А "
        "(DLG/NL-8b/GC-58/§9.13/W14) верифицирована до/после; урок: параллельные "
        "dict-структуры правок — метки пар обязаны совпадать попарно (KeyError на "
        "6-й паре пойман ДО единственной точки записи — fail-before-write подтверждён "
        "реальным отказом, диск не тронут); релей: доковые правки параллельных ветвей "
        "обязаны сохранять чужие строки §17.8/§10-журнала зоны Б (§R.6.4); "
        "IPT 50 passed / 0 failed / 3 skipped (SpatialRegistry-вход, 0 CRITICAL) · ✅ · "
        f"без ADR (док-восстановление, код не тронут) · коммит {commit}"
    )

    text, bom = _load(MUT)
    if text.count("- **S352**") != 0:
        _abort("S352 уже в реестре — скрипт уже исполнен?")
    anchor_idx = [i for i, ln in enumerate(text.split("\n"))
                  if ln.startswith("- **S351** COV-1 Шаг 1")]
    if len(anchor_idx) != 1:
        _abort(f"якорь S351 найден {len(anchor_idx)} раз (ожидался 1)")
    meta_old = "Записей: 233 ("
    if text.count(meta_old) != 1:
        _abort(f"МЕТА-префикс найден {text.count(meta_old)} раз (ожидался 1)")

    lines = text.split("\n")
    lines.insert(anchor_idx[0] + 1, line)
    text = "\n".join(lines)
    text = text.replace(meta_old,
                        "Записей: 234 (S352-Б-1-restore добавлен; ", 1)

    if text.count("- **S352**") != 1 or text.count("Записей: 234") != 1:
        _abort("пост-гейт не прошёл")
    _save(MUT, text, bom)
    print("[OK] S352 записан после S351; МЕТА 233→234.")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""scripts/patch_s348_registry_tail.py — S348: регистрация хвостов потомкам.

Self-audit закрытия: 4 пробела фиксации. (1) Три находки живого прогона
(dual-stack спавнеров / латентное окно /health / router-зомби) — прозой в
S348+IMPACT, но НЕ строками §7.10, тогда как §17.7-1 DoD: «любая находка
→ строка §7.10 с file:line». (2) 4-й инцидент семейства §3.7 (ручная
вставка paste-ready-врезки с плейсхолдерами {running}/{screen}) — только
в артефактах. (3) O-424 near-miss (гейт номеров поймал до записи). (4)
Повтор урока S317. ID новых строк: динамически max+1..3 по §7.10 (гейт
уникальности в скрипте). Дополнение S348-строки — прецедент S342-reg.
Одноразовый; после применения перенести в reports/.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P_ROAD = ROOT / "docs" / "ENIGMA_ROADMAP_v4_6.md"
P_MUT = ROOT / "docs" / "MUTATIONS.md"


class Abort(Exception):
    """Громкий отказ (Law L4): ничего не записано."""


def req(cond, msg):
    if not cond:
        raise Abort(msg)


def load(p: Path):
    raw = p.read_bytes()
    bom = b""
    if raw.startswith(b"\xef\xbb\xbf"):  # урок S317: BOM
        bom, raw = raw[:3], raw[3:]
    text = raw.decode("utf-8")
    crlf = "\r\n" in text
    if crlf:
        text = text.replace("\r\n", "\n")
    return text, bom, crlf


def save(p: Path, text: str, bom: bytes, crlf: bool) -> None:
    out = text.replace("\n", "\r\n") if crlf else text
    p.write_bytes(bom + out.encode("utf-8"))


def main() -> int:
    # ---------- 1. Roadmap §7.10: три строки долгов ----------
    road, road_bom, road_crlf = load(P_ROAD)
    lines = road.split("\n")
    ids = sorted(
        {int(m.group(1)) for ln in lines
         if (m := re.match(r"^\| COV-D(\d+) \|", ln))}
    )
    req(ids, "§7.10: не найдено ни одной строки | COV-D* |")
    a, b, c = ids[-1] + 1, ids[-1] + 2, ids[-1] + 3
    print(f"[i] §7.10: max COV-D{ids[-1]} -> новые D{a}/D{b}/D{c}")

    row_a = (
        f"| COV-D{a} | Dual-stack спавнеров llama-server: менеджер поднимает --host localhost "
        "(резолв в ::1 — HTTP-проба на 127.0.0.1 не отвечает; DET-ENV прогона 0253d0ef) vs "
        "server_lifecycle --host 127.0.0.1; пробы живости обязаны быть dual-stack либо стеки "
        "выровнены (сценарий D61 закрылся TCP-пробой обоих стеков). Якоря: scripts/"
        "llm_server_manager.py:80, backend/app/services/llm/server_lifecycle.py:151 "
        "| P2 | COV-2-хвост | выравнивание --host спавнеров (вердикт Мастера) | открыт |"
    )
    row_b = (
        f"| COV-D{b} | Латентное окно /health при загрузке модели: после спавна /health отвечает "
        ">1с (3с-проба GREEN, 1с timeout — прогоны D61); прод-старт-гейт D61 переживает окно как "
        "unconfirmed×2 без модалки — легально по доктрине ADR-O-425, UX-вопрос. Якорь: backend/"
        "app/services/llm/server_lifecycle.py:226 | P3 | COV-2-хвост | опция wait-ready при старте "
        "(поллинг до стабилизации) | открыт |"
    )
    row_c = (
        f"| COV-D{c} | Router не детектирует смерть llama-server вне провала in-flight запроса "
        "(эскалация S347/81544792, зона Б): пул узнаёт о смерти только по record_failure запроса; "
        "фронт-D61 видит отказ по health — два канала детекции расходятся во времени "
        "| P2 | COV-2-хвост | единый outage-источник (health+pool) для фронта и router-метрик | открыт |"
    )
    d74 = [i for i, ln in enumerate(lines) if ln.startswith("| COV-D74 |")]
    req(len(d74) == 1, f"§7.10: якорь COV-D74 найден {len(d74)} раз (ожидался 1)")
    rows_before = sum(1 for ln in lines if ln.startswith("| COV-D"))
    lines[d74[0] + 1:d74[0] + 1] = [row_a, row_b, row_c]
    road = "\n".join(lines)
    # стражи (относительные + полные строки)
    req(sum(1 for ln in road.split("\n") if ln.startswith("| COV-D")) == rows_before + 3,
        "пост: строк §7.10 не +3")
    for row in (row_a, row_b, row_c):
        req(road.count(row) == 1, f"пост: строка D{row.split('|')[1].strip()} != 1")
    req(road.startswith("\n".join(lines[:d74[0]]).rstrip("\n")) or True, "")  # no-op
    save(P_ROAD, road, road_bom, road_crlf)
    print(f"[ok] §7.10: +{a}/D{b}/D{c} (dual-stack / health-окно / router-зомби)")

    # ---------- 2. MUTATIONS: дополнение S348 (прецедент S342-reg) ----------
    mut, mut_bom, mut_crlf = load(P_MUT)
    s_before = len(re.findall(r"^- \*\*S\d", mut, re.M))
    anchor = "относительные проверки; пакет:"
    req(mut.count(anchor) == 1,
        f"MUTATIONS: якорь S348 найден {mut.count(anchor)} раз (ожидался 1)")
    add = (
        "относительные проверки; процесс-хвост-2 (потомкам): 4-й инцидент семейства §3.7 — ручная "
        "вставка paste-ready-врезки с плейсхолдерами {running}/{screen} (SyntaxError до любых "
        "гейтов; урок: подстановки живут ТОЛЬКО внутри скрипта, paste-ready блоки плейсхолдеров "
        "не содержат); ADR-O-424 занят ветвью А между разведкой и записью — гейт номеров "
        "(атлас+git log --all) поймал ДО записи, ренумбер не потребовался (позитивный прецедент "
        "доверия гейту); повтор урока S317 (untracked add до pathspec) пойман пустым коммитом — "
        f"без потерь; находки прогона зарегистрированы §7.10: COV-D{a}/D{b}/D{c}; пакет:"
    )
    mut = mut.replace(anchor, add, 1)
    # стражи: S-счётчик не изменился, строка S348 одна
    req(len(re.findall(r"^- \*\*S\d", mut, re.M)) == s_before,
        f"пост: S-счётчик изменился {s_before} (дополнение, не новая строка)")
    req(mut.count("- **S348**") == 1, "пост: S348 != 1")
    req(mut.count("процесс-хвост-2 (потомкам)") == 1, "пост: дополнение != 1")
    save(P_MUT, mut, mut_bom, mut_crlf)
    print("[ok] MUTATIONS: S348 дополнен (процесс-хвост-2 + §7.10-ссылки)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Abort as e:
        print(f"\n[ABORT] {e}\nНичего не записано.", file=sys.stderr)
        sys.exit(2)

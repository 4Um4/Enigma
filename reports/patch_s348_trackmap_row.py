# -*- coding: utf-8 -*-
"""scripts/patch_s348_trackmap_row.py — S348: забытая статусная строка.

Self-audit (запрос Мастера по живому документу): чеклисты §17.4 закрыты,
§10-строка лежит, а строка трека COV в §0.1 «Карта треков» осталась «—» —
потомок сверху видит COV-2 открытым. Строка ветви Б (§17 COV). Попутно
зафиксированы эскалации: CCH-строка §0.1 просрочена (зона А), шапка
«Базлайн: IPT 49/49» (общий контур, Мастер). Одноразовый; в reports/.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P_ROAD = ROOT / "docs" / "ENIGMA_ROADMAP_v4_6.md"


class Abort(Exception):
    """Громкий отказ (Law L4): ничего не записано."""


def req(cond, msg):
    if not cond:
        raise Abort(msg)


OLD = "| **COV — Карта полноты (v4.5)** | — (новый гарантирующий слой; рой-аудит полноты 2026-10-08 read-only: 4 агента, находки §7.10 — 96 позиций, карта фактов §17.2, Gap Matrix §17.3) | COV-0 реестр флагов/вердиктов → COV-1 персистентность/миграции → COV-2 LLM-контур/телеметрия → COV-3…6 вердикты механик (экономика/сцена/комбат/движение) → COV-7 игрок/MVP-вертикаль → COV-8…11 фронтенд/релиз/контент/документация; протокол поддержания полноты — §17.7. Раздел §17 | — |"
NEW = "| **COV — Карта полноты (v4.5)** | COV-0 ✅ (S343/S344: flags.yaml + lint_flags C1–C7 + INV-FLAG-REGISTRY + pre-commit) → **COV-2 ✅ (S348, ADR-O-425: доктрина обязательной LLM — D61-фронт + транспорт-фикс + живой smoke d61_llm_outage_doctrine 32/0 EXIT=0; очередь D62 за LLM_RESILIENCE_V1 default OFF — ON вердикт Мастера; S2-стыковка разблокирована)** | COV-1 персистентность/миграции (публикует S1) → COV-3…6 вердикты механик (экономика/сцена/комбат/движение) → COV-7 игрок/MVP-вертикаль → COV-8…11 фронтенд/релиз/контент/документация; протокол поддержания полноты — §17.7 (карта фактов §17.2, Gap Matrix §17.3). Раздел §17 | O-425 |"


def main() -> int:
    raw = P_ROAD.read_bytes()
    bom = b""
    if raw.startswith(b"\xef\xbb\xbf"):  # урок S317: BOM
        bom, raw = raw[:3], raw[3:]
    text = raw.decode("utf-8")
    crlf = "\r\n" in text
    if crlf:
        text = text.replace("\r\n", "\n")

    req(text.count(OLD) == 1,
        f"якорь COV-строки §0.1 найден {text.count(OLD)} раз (ожидался 1) — "
        "строка дрейфнула, пришли дословно")
    text = text.replace(OLD, NEW, 1)

    # стражи: полные строки
    req(text.count(NEW) == 1, "пост: новая строка != 1")
    req(text.count("| **COV — Карта полноты (v4.5)** |") == 1,
        "пост: заголовок строки COV затронут")
    req(text.count("COV-2 ✅ (S348") == 1, "пост: статус COV-2 != 1")
    out = text.replace("\n", "\r\n") if crlf else text
    P_ROAD.write_bytes(bom + out.encode("utf-8"))
    print("[ok] §0.1: строка трека COV обновлена (COV-0/COV-2 закрыты, ADR O-425)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Abort as e:
        print(f"\n[ABORT] {e}\nНичего не записано.", file=sys.stderr)
        sys.exit(2)

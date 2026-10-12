# -*- coding: utf-8 -*-
"""scripts/patch_cov2_close_docs.py — COV-2/S348: доковый пакет закрытия.

Правки (doc-only):
  1) MUTATIONS.md — строка S348 (якорь: заголовок §4) + МЕТА 230->231
     (+Базлайн IPT 52/52 мягко);
  2) ADR-атлас — STANDALONE ADR-O-425 (конвенция S311: без бэктиков),
     аппенд в конец;
  3) docs/audits/ADR-O-425_IMPACT.md — новый (формат O-424_IMPACT);
  4) flags.yaml — LLM_RESILIENCE_V1.adr: COV-2 -> ADR-O-425 (verdict
     ROLLOUT-PENDING НЕ трогаем: ON = отдельный вердикт Мастера);
  5) roadmap — чекбоксы COV-2 x2 (префиксные замены строк), COV-GC-03 [x]
     (критерий-1 ревизирован доктриной D61), §7.10: 11 строк COV-D*
     (закрыт/вне COV-2 по вердиктам Мастера; статус только через хвост
     '| открыт |'); READ-ONLY дамп §10 — строка журнала следующим
     доковым коммитом (прецедент backfill S334).
Стражи: якоря count==1; МЕТА-греп до/после (230->231); ADR-O-425
отсутствует до записи. Одноразовый; после применения перенести в reports/.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P_MUT = ROOT / "docs" / "MUTATIONS.md"
P_ATLAS = ROOT / "docs" / "ADR (Architecture Decision Records).md"
P_IMPACT = ROOT / "docs" / "audits" / "ADR-O-425_IMPACT.md"
P_FLAGS = ROOT / "architecture" / "flags.yaml"
P_ROAD = ROOT / "docs" / "ENIGMA_ROADMAP_v4_6.md"


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


S348_LINE = (
    "- **S348** COV-2 закрыт (ветка Б; ТЗ-приёмник S343-S345): D61-фронт + живой smoke доктрины обязательной LLM — "
    "LlmOutageController (frontend/llm_outage_ui.py: единственный watcher 5с, generation-счётчик, дебаунс unconfirmed×2, "
    "рестарт-флоу без авто-возобновления) + модалка двух выборов ×4 состояния (rising-edge клик, локальный шрифт) + гейты "
    "кадра game_screen (idle, skip×4, submit через self — ТЗ §3.4-4, хозяин _handle_text_input, call-site run:921) + "
    "старт-гейт + api_client.get_llm_outage/restart_llm + T-пауза×3 (micro 27/27); прод-фикс: per-call таймаут рестарта "
    "HttpClient 30с->180с (_LLM_RESTART_TIMEOUT_SEC; ложный FAILED при штатно долгой загрузке — находка живого прогона); "
    "SUPERBOX d61_llm_outage_doctrine GREEN 32/0 EXIT=0 против настоящего llama-server (kill×3/restart×3: in-flight "
    "честный отказ -> pool backoff -> outage немедленно минуя дебаунс -> мир стоит; рестарт SUCCESS -> пауза держится -> "
    "resume -> реплика end-to-end; FAILED exe_missing + retry + recovery; дебаунс живым watcher; модалка headless) + "
    "артефакты reports/d61_llm_outage_doctrine.{json,md}; находки прогона: dual-stack спавнеров (менеджер --host "
    "localhost=::1 vs lifecycle 127.0.0.1 — выравнивание Мастеру), латентное окно /health при загрузке (старт-гейт "
    "переживает как unconfirmed×2 — легально по доктрине), резолв localhost ~7с вне socket-таймаута; UX-FB Тай "
    "(44a65f77) переиспользует D61-модалку — совместно в main, CI зелёный; процесс-урок: 5 ABORTов одного класса "
    "«страж-счётчик» в патч-скриптах — стражи только полные строки кода/относительные проверки; пакет: D61/D62/D64-ядро/"
    "D65/D66-мин/D67/D74 закрыты, D63/D68/D69/D71 вне COV-2 (вердикт Мастера); COV-GC-03 закрыт с ревизией критерия-1 "
    "доктриной D61 (отказ->пауза, не degraded-тикание); LLM_RESILIENCE_V1 ROLLOUT-PENDING (ON — отдельный вердикт "
    "Мастера); S2-стыковка (§R.5) разблокирована (COV-GC-03 GREEN) — публикация за Мастером; хвосты: §10-строка "
    "журнала — следующим доковым коммитом; router-зомби (эскалация S347, зона Б) · ✅ · ADR-O-425; коммиты ea5a05d1, "
    "6849a9f3, 0253d0ef + бэкенд-серия передатчика ccd13e38…31387976 (D74/D67/D65/D66/D64-ядро/D62/D61-бэкенд) · "
    "IPT 52/52, micro 27/27"
)

ATLAS_ENTRY = """ADR-O-425 [STANDARD] **LLM Mandatory Delivery Doctrine — D61 Front Contour** (S348)
Суть: отказа без паузы не существует (вердикты Мастера, ТЗ D61 §3.1, дословно): (1) LLM обязательна — доказанный отказ (pool backoff; /api/llm/outage status=outage) => остановка игрового времени + модалка двух выборов (Перезапустить | Выйти) НЕМЕДЛЕННО; (2) неподтверждённый (health offline при чистом пуле, unconfirmed) => дебаунс 2 проб подряд; (3) успех рестарта НЕ возобновляет игру (SUCCESS -> «Возобновить» только по клику; авто-возобновление запрещено во всех ветках); (4) провал рестарта — пауза сохраняется, причина показана (Повторить/Выйти); (5) никаких заглушек NPC (ADR-113): in-flight ход завершается честным отказом; (6) один watcher-поток (5с) + generation-счётчик: рестарт/резюм инкрементируют поколение, устаревшие результаты отбрасываются. Реализация: frontend/llm_outage_ui.py (LlmOutageController + draw_outdate_modal-контракт: rising-edge клик — не event-очередь; рестарт-флоу владеет модалкой) + гейты кадра game_screen (idle/skip×4; submit через self — хозяин _handle_text_input, call-site run:921) + старт-гейт run() + api_client.get_llm_outage/restart_llm (транспорт рестарта per-call 180с, _LLM_RESTART_TIMEOUT_SEC). Доказательство: SUPERBOX d61_llm_outage_doctrine GREEN 32/0 EXIT=0 против настоящего llama-server. Очередь D62 — за LLM_RESILIENCE_V1 (default OFF, ROLLOUT-PENDING; ON — вердикт Мастера).
❌ Taboo: продолжение симуляции при доказанном отказе; авто-возобновление после SUCCESS; пауза на транспортный сбой без доказательства; фейковый нарратив при отказе (ADR-113); второй watcher-поток; применение устаревшего (generation) результата; новые env-флаги вне flags.yaml (COV-0).
Status: ACTIVE
Files: frontend/llm_outage_ui.py, frontend/game_screen.py, frontend/api_client.py, backend/app/services/llm/server_lifecycle.py, backend/tests/sandbox/SUPERBOX/scenarios/d61_llm_outage_doctrine_test.py, backend/tests/micro/test_llm_resilience_v1.py"""

IMPACT_CONTENT = """# ADR-O-425 Impact Audit

ADR-O-425 [STANDARD] **IMPACT**

> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: docs/ADR (Architecture Decision Records).md

## Changed Domains
- Фронтенд-контур доставки LLM: статус-наблюдение, пауза мира, рестарт-флоу (D61)
- Транспорт api_client: per-call таймаут рестарта (30с -> 180с, _LLM_RESTART_TIMEOUT_SEC)
- Бэкенд-пакет COV-2 — серия передатчика (S343-S345): /llm/outage, /api/llm/restart, server_lifecycle, pool backoff (31387976 и др.)

## Downstream Consumers
- game_screen.run() — гейты idle/skip/submit + модалка поглощает кадр (дренаж событий, QUIT пробрасывается)
- _handle_text_input — гвард submit через self._llm_ctrl (ТЗ §3.4-4; единственный call-site run:921, после инициализации)
- UX-FB Тай (44a65f77) — переиспользует D61-модалку для честной деградации LLM-хода (совместимо с доктриной, в main вместе)
- TaskScheduler/worker-путь — не тронуты (очередь D62 за LLM_RESILIENCE_V1)

## Runtime Impact
- +1 daemon-поток (5с poll; generation-счётчик гасит при выходе; повторный run() гасит прошлый watcher)
- Рестарт-воркер — разовый поток на попытку; транспорт держит сокет до 180с (вместо ложного FAILED на 30с)

## Sandbox Tests
- backend/tests/sandbox/SUPERBOX/scenarios/d61_llm_outage_doctrine_test.py — GREEN 32/0, PROCESS EXIT=0 (живой llama-server, kill×3/restart×3; артефакты reports/d61_llm_outage_doctrine.{json,md})
- backend/tests/micro/test_llm_resilience_v1.py — 27/27 (24 бэкенд + T-пауза×3)

## Rollback
- git revert ea5a05d1 6849a9f3 0253d0ef (фронт+smoke; бэкенд-серия COV-2 откатывается отдельно)

## Остатки
- LLM_RESILIENCE_V1 ROLLOUT-PENDING: ON = отдельный вердикт Мастера + повторная приёмка (full pytest + IPT + живой smoke)
- Ручной чеклист Мастера (вне headless): модалка на экране / утечка кликов-ESC через event-loop game_screen / крестик при модалке
- Router-зомби (эскалация S347): детекция смерти llama-server вне in-flight запросов — COV-2-смежный хвост зоны Б
- Dual-stack спавнеров: менеджер --host localhost (стек ::1) vs lifecycle 127.0.0.1 — выравнивание на Мастере
- UX старт-гейта: латентное окно /health при загрузке модели переживается как unconfirmed×2 без модалки (легально по доктрине; вопрос удобства)
"""

CHECKBOX_A = (
    "- [x] **COV-2** — LLM-контур и телеметрия (D61–D69, D71, D74): ✅ S348/ADR-O-425 — замкнут доктриной обязательной "
    "LLM: D61 бэкенд 31387976 + фронт ea5a05d1 + транспорт-фикс 6849a9f3 + живой smoke 0253d0ef "
    "(d61_llm_outage_doctrine GREEN 32/0 EXIT=0); D62 очередь за LLM_RESILIENCE_V1 default OFF (7a9294fd+92ab49dc; "
    "ON — вердикт Мастера); D65 streaming→replay d0171f09; D66-мин 6b85b7c9; D67 miss громко 6562f86e; D74 ccd13e38; "
    "D64-ядро latency 6b85b7c9; D63/D68/D69/D71 — вне COV-2 (вердикт Мастера); COV-GC-03 закрыт (критерий-1 "
    "ревизирован доктриной: отказ→пауза, не degraded-тикание); S2-стыковка (§R.5) разблокирована — публикация за Мастером."
)
CHECKBOX_B = (
    "- [x] **COV-2 — LLM-контур и телеметрия** (D61–D69, D71, D74): ✅ S348 — доктрина обязательной LLM (ADR-O-425): "
    "D61/D62-за-флагом/D64-ядро/D65/D66-мин/D67/D74 закрыты с якорями (ea5a05d1, 6849a9f3, 0253d0ef, 31387976, "
    "7a9294fd, d0171f09, 6b85b7c9, 6562f86e, ccd13e38); D63/D68/D69/D71 — вне COV-2 (вердикт Мастера); "
    "LLM_RESILIENCE_V1 ROLLOUT-PENDING (ON — отдельное решение Мастера)."
)
GC03_LINE = (
    "- [x] **COV-GC-03 — Деградация живая.** ✅ S348 — критерий-1 РЕВИЗИРОВАН доктриной D61 (вердикты Мастера): "
    "доказанный отказ LLM → остановка времени + модалка двух выборов (продолжение без LLM запрещено; degraded-тикание "
    "отвергнуто) — доказано живым прогоном d61_llm_outage_doctrine 32/0 (outage немедленно минуя дебаунс; мир стоит; "
    "рестарт SUCCESS → пауза держится; resume → реплика end-to-end); streaming-сессия воспроизводится в replay (D65, "
    "d0171f09, micro T3×5); параллельный запрос не убивает первый (D62, очередь 7a9294fd+92ab49dc, за LLM_RESILIENCE_V1 "
    "default OFF — ON отдельный вердикт); playback miss громко (D67, 6562f86e, micro T1/T2)."
)
ROWS = [
    ("COV-D61", "закрыт (S348/ADR-O-425: доктрина обязательной LLM — пауза+модалка вместо degraded, вердикты Мастера; 31387976+ea5a05d1+0253d0ef)"),
    ("COV-D62", "закрыт (S348: очередь за LLM_RESILIENCE_V1 default OFF, 7a9294fd+92ab49dc; ON — вердикт Мастера)"),
    ("COV-D63", "вне COV-2 (вердикт Мастера: token-budget — отдельный фронт)"),
    ("COV-D64", "частично закрыт (ядро: latency worker-пути 6b85b7c9; VRAM-заглушка/токены — вне COV-2, вердикт Мастера)"),
    ("COV-D65", "закрыт (d0171f09, micro T3×5)"),
    ("COV-D66", "закрыт минимально (to_thread SSE-fallback 6b85b7c9; полный неблокирующий router — вне COV-2, вердикт Мастера)"),
    ("COV-D67", "закрыт (6562f86e+2d6148cd, micro T1/T2)"),
    ("COV-D68", "вне COV-2 (вердикт Мастера: унификация compressor→router — отдельный шаг)"),
    ("COV-D69", "вне COV-2 (вердикт Мастера: санация мёртвой инфраструктуры)"),
    ("COV-D71", "вне COV-2 (вердикт Мастера: observability-экспорт)"),
    ("COV-D74", "закрыт (ccd13e38)"),
]


def replace_line_by_prefix(text: str, prefix: str, new_line: str, tag: str) -> str:
    lines = text.split("\n")
    hits = [i for i, ln in enumerate(lines) if ln.startswith(prefix)]
    req(len(hits) == 1, f"{tag}: префикс найден {len(hits)} раз (ожидался 1): {prefix!r}")
    lines[hits[0]] = new_line
    return "\n".join(lines)


def close_row(text: str, row_id: str, status: str) -> str:
    lines = text.split("\n")
    hits = [i for i, ln in enumerate(lines) if ln.startswith(f"| {row_id} |")]
    req(len(hits) == 1, f"{row_id}: строка §7.10 найдена {len(hits)} раз (ожидался 1)")
    ln = lines[hits[0]].rstrip()
    req(ln.endswith("| открыт |"),
        f"{row_id}: строка не кончается '| открыт |' — хвост: {ln[-90:]!r}")
    lines[hits[0]] = ln[: -len("| открыт |")] + f"| {status} |"
    return "\n".join(lines)


def main() -> int:
    # ---------- 1. MUTATIONS ----------
    mut, mut_bom, mut_crlf = load(P_MUT)
    s_before = len(re.findall(r"^- \*\*S\d", mut, re.M))
    req(s_before == 230,
        f"MUTATIONS: греп-счётчик S-строк = {s_before}, МЕТА ждёт 230 — "
        "дрейф; пришли фактическое число")
    req(mut.count("## 4. Правила ведения (вперёд)") == 1,
        "MUTATIONS: якорь §4 не уникален")
    req(mut.count("Записей: 230 (S347-CCH-4-финал добавлен;") == 1,
        "MUTATIONS: якорь МЕТА не найден/не уникален")
    req("**S348**" not in mut, "MUTATIONS: S348 уже есть — двойная запись?")
    mut = mut.replace("## 4. Правила ведения (вперёд)",
                      S348_LINE + "\n\n## 4. Правила ведения (вперёд)", 1)
    mut = mut.replace("Записей: 230 (S347-CCH-4-финал добавлен;",
                      "Записей: 231 (S348-COV-2 добавлен; S347-CCH-4-финал добавлен;", 1)
    if mut.count("Базлайн: IPT 51/51") == 1:
        mut = mut.replace("Базлайн: IPT 51/51", "Базлайн: IPT 52/52", 1)
        print("[i] МЕТА: Базлайн IPT 51/51 -> 52/52")
    else:
        print("[i] МЕТА: Базлайн не 51/51 — не тронут")
    s_after = len(re.findall(r"^- \*\*S\d", mut, re.M))
    req(s_after == 231, f"MUTATIONS: пост-греп = {s_after}, ожидался 231")
    save(P_MUT, mut, mut_bom, mut_crlf)
    print("[ok] MUTATIONS: строка S348 + МЕТА 231 (греп-эквивалентность)")

    # ---------- 2. Атлас ----------
    atl, atl_bom, atl_crlf = load(P_ATLAS)
    req(atl.count("ADR-O-425") == 0, "атлас: ADR-O-425 уже существует — номер занят")
    atl = atl.rstrip("\n") + "\n\n" + ATLAS_ENTRY.rstrip("\n") + "\n"
    req(atl.count("ADR-O-425 [STANDARD]") == 1, "атлас: пост-запись != 1")
    save(P_ATLAS, atl, atl_bom, atl_crlf)
    print("[ok] атлас: ADR-O-425 (STANDALONE, заголовок без бэктиков — S311)")

    # ---------- 3. IMPACT ----------
    req(not P_IMPACT.exists(), "IMPACT уже существует")
    P_IMPACT.parent.mkdir(parents=True, exist_ok=True)
    P_IMPACT.write_text(IMPACT_CONTENT, encoding="utf-8")
    print("[ok] IMPACT: docs/audits/ADR-O-425_IMPACT.md")

    # ---------- 4. flags.yaml ----------
    flg, flg_bom, flg_crlf = load(P_FLAGS)
    FLAG_OLD = ('  LLM_RESILIENCE_V1:\n    type: env\n    read_mode: call\n'
                '    default: ""\n    verdict: ROLLOUT-PENDING\n    adr: COV-2')
    req(flg.count(FLAG_OLD) == 1,
        "flags.yaml: якорь блока LLM_RESILIENCE_V1 не найден/не уникален")
    flg = flg.replace(FLAG_OLD, FLAG_OLD.replace("adr: COV-2", "adr: ADR-O-425"), 1)
    req(flg.count("adr: ADR-O-425") == 1, "flags.yaml: adr не заменён")
    save(P_FLAGS, flg, flg_bom, flg_crlf)
    print("[ok] flags.yaml: adr COV-2 -> ADR-O-425 (verdict ROLLOUT-PENDING сохранён)")

    # ---------- 5. Roadmap ----------
    road, road_bom, road_crlf = load(P_ROAD)
    road = replace_line_by_prefix(road, "- [ ] **COV-2** — LLM-контур", CHECKBOX_A, "чекбокс-COV-2(A)")
    road = replace_line_by_prefix(road, "- [ ] **COV-2 — LLM-контур", CHECKBOX_B, "чекбокс-COV-2(B)")
    road = replace_line_by_prefix(road, "- [ ] **COV-GC-03", GC03_LINE, "COV-GC-03")
    for row_id, status in ROWS:
        road = close_row(road, row_id, status)
    for row_id, _ in ROWS:
        for ln in road.split("\n"):
            if ln.startswith(f"| {row_id} |"):
                req("| открыт |" not in ln, f"{row_id}: статус не заменился")
    save(P_ROAD, road, road_bom, road_crlf)
    print(f"[ok] roadmap: 2 чекбокса COV-2 [x] + COV-GC-03 [x] + {len(ROWS)} строк §7.10")

    # ---------- 6. READ-ONLY дамп §10 (строка журнала — следующим коммитом) ----
    m = re.search(r"^#{2,3} 10\b.*$", road, re.M)
    if m:
        seg = road[m.start():].split("\n")[:16]
        print("--- DUMP §10 (read-only; строка журнала — следующим доковым коммитом) ---")
        print("\n".join(seg))
        print("--- конец DUMP ---")
    else:
        print("[i] §10 не найден — строка журнала следующим коммитом")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Abort as e:
        print(f"\n[ABORT] {e}\nНичего не записано (правки атомарны по файлам: "
              "MUTATIONS/атлас/IMPACT/flags уже могли лечь — смотри [ok]-строки выше).",
              file=sys.stderr)
        sys.exit(2)

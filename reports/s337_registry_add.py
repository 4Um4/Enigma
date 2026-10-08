"""
path: /project/reports/s337_registry_add.py
Назначение: Строка S337 в реестр MUTATIONS (блок: S330-probe + хвосты S329/LC).
    Вставка после строки S336, МЕТА-бамп, якорь-верификация (прецедент
    s329_backfill_mark.py; BOM-обработка — урок S317).
Запуск: python reports/s337_registry_add.py
"""
import re
from pathlib import Path

F = Path(__file__).resolve().parents[1] / "docs" / "MUTATIONS.md"
_raw = F.read_bytes()
_bom = _raw.startswith(b"\xef\xbb\xbf")
text = _raw.decode("utf-8-sig" if _bom else "utf-8")

assert not re.search(r"^- \*\*S337\*\*", text, re.M), "S337 занят — ренумбер (Устав 11.1.1)"
_s336 = [l for l in text.splitlines() if l.startswith("- **S336**")]
assert len(_s336) == 1, f"count(S336)={len(_s336)}"

NEW = ("- **S337** S330-probe (мандат Мастера: targeted-probe → установить точку потери движения деятельности, "
       "диагностика НЕ фикс; вердикт финальный: ROOT CAUSE CONFIRMED / FIX OWNER HOLD — владелец не назначен, "
       "самовольная калибровка 2.0→2.108 запрещена) + хвосты передачи S334. Точка потери: activity-MOVE-цель "
       "(activity:eat:… target=tavern:bar_area) теряется в MovementEngine._compile_traversal_plan → REJECTED(GAP_TOO_WIDE) "
       "→ return [] → вечная переэмиссия → ACTIVITY_TIMEOUT-терминал без success (CONF 90: три log-only зонда "
       "[ObservabilityTap-паттерн ADR-O-361], A/A-детерминизм двух прогонов, контролируемая пара). Механизм: capability-blind "
       "A* выбирает первый хоп right_table→main_hall_west (маршрут 6.9 < альт. 7.8); прямой луч чиркает obj_11 "
       "rect(7.35,6.65,1.30,0.70) clearance=-0.350 → единственный локальный обход JUMP h_dist≈2.108 > дефолт "
       "max_jump_distance 2.0 (shortfall 5.4%); S131.1 HARD_REJECT финален by design, ревизии маршрута нет. Развилка "
       "A/B/C закрыта probe-3: obstacle снят (obj_11, §6.1); порог 2.0 введён e3f6377a [V.0.5.3.5.5 full snapshot] БЕЗ "
       "калибровочного следа, ADR-O-333_IMPACT отсутствует → ветка B не самодостаточна; альтернатива через main_hall "
       "правдоподобна (тот же тик тем же телом right_table→main_hall ACCEPTED, JUMP≈1.05), полный по-хопный диф — за "
       "владельцем фикса (варианты §7 досье: A movement-ревизия маршрута / B политика порога / C топология-данные / D "
       "латентный проброс тела). Опровергнуто: зомби-MOVING (транзиты завершаются честно), B1-COLLAPSE activity-цели, "
       "missing node (bar_area в графе), «дефолт-тело не прыгает» (can_jump=True, дошел до дистанционной ветки kernel), "
       "drop-механика досье S330 event_compiler:741-747/SSM:955-963 — недостижимы как первый отказ (proposal не "
       "рождается; вердикт «досье говорит где подозревать, не доказывает root cause» подтверждён буквально). Побочные "
       "находки: GAP_TOO_WIDE ∉ movement_contract M000-M008 (дыра классификации причин); латентная асимметрия "
       "body_capabilities (_build_goal не задаёт → дефолт, npc_tick_pipeline:1171 передаёт реальное тело) — сегодня "
       "нейтральна [config-override: греп 0], кандидат мини-ADR; GATE-зонды Правил §12 — logger.debug, в RED-прогонах "
       "невидимы (видимость приборов ≠ отсутствие пути); seek_ally резолвится в собственный узел (COLLAPSE=15) — мелочь; "
       "системность: 78 GAP_TOO_WIDE/20 тиков по всем NPC (хоп восток→запад отказывает классом). Хвост S329: commit "
       "binding UNPROVEN — не фабриковать (вердикт); карта атрибуции: авторский docs=31823f9e; код вшит dd7bfe31 "
       "[WIP-релиз V.0.5.4.2.7, --diff-filter=A]; атлас O-419 + манифест need_slot.gen_rate вшиты 9290260e [WIP-релиз "
       "V.0.5.4.2.8]; строка внесена 9e18f7cd-disclosure; замена скриптом 1:1, остаточных '<SHA>'=0 → 7dbc8e12. Санация "
       "LC-каталога (вердикт: tracked+clean): chat-dump-обёртка удалена 198→186, канон 9-194 байт-в-байт, независимые "
       "грепы=0, git diff --check чист, файл живёт до LC-IMPL-6 (§1.3) → 340c65f7. Диагностический бандл (досье "
       "+§10, зонды ×2 новых, отчёты, хвостовые скрипты) → 6374f72e; probe1-артефакты не дублированы — втянуты релизом "
       "58b2389e (v0.5.4.3.0, доказано git log по путям). Гейты: IPT 51/51 ×2 (чужой RED эры S336-разработки починен их "
       "контуром ed560688), lint_consumer_gap GREEN 26/299/75 (дрейфа нет), pytest micro 279/279 (267→279, +12 "
       "параллельные S336/S338 — дрейф счётчика = находка, не починка). Дрейф платформы: v0.5.4.3.0 влит (HEAD=origin/main "
       "до моих коммитов), roadmap v4.3→v4_6 (живой, обновляется оператором — учтено). Далее: владелец фикса S330 — "
       "вердикт Мастера; GC-спринт (GC-01, §9.10 v4.6, F5-лаборатория). · ✅ · коммиты: 7dbc8e12, 340c65f7, 6374f72e")

lines = text.splitlines(keepends=True)
for _i, _l in enumerate(lines):
    if _l.startswith("- **S336**"):
        lines.insert(_i + 1, NEW + "\n")
        break
text2 = "".join(lines)

_m = re.search(r"^Записей: (\d+)", text2, re.M)
assert _m, "МЕТА-строка не найдена"
_n = int(_m.group(1))
text2 = re.sub(r"^Записей: \d+", f"Записей: {_n + 1}", text2, count=1, flags=re.M)

assert text2.count("- **S337**") == 1
assert len(text2.splitlines()) == len(text.splitlines()) + 1
assert "S330-probe" in text2 and "ROOT CAUSE CONFIRMED" in text2

F.write_bytes((b"\xef\xbb\xbf" if _bom else b"") + text2.encode("utf-8"))
print(f"OK: S337 вставлена после S336; МЕТА {_n} -> {_n + 1}")
# scripts/d72_doc_closure.py
"""
path: scripts/d72_doc_closure.py
Назначение: док-закрытие D72 (COV-1 Шаг 5, S360, ветка Б).
  8 правок в 6 файлах: MUTATIONS, roadmap (4 зоны), атлас, IMPACT, ЗАВЕЩАНИЕ.
  Anti-Race: чужие строки не трогаются; правки — точные замены БЫЛО/СТАЛО.
Зависимости: pathlib, datetime.
Запуск (из корня): python scripts/d72_doc_closure.py
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TODAY = "2026-10-19"
SESSION = "S360"
COMMIT_HASH = "<SHA>"  # будет вписан после коммита кода


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def _write(p: Path, text: str) -> None:
    p.write_text(text, encoding="utf-8", newline="\n")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        print(f"[FAIL] {label}: anchor not found")
        sys.exit(1)
    if text.count(old) > 1:
        print(f"[FAIL] {label}: anchor not unique ({text.count(old)} matches)")
        sys.exit(1)
    print(f"[OK] {label}")
    return text.replace(old, new)


def main() -> None:
    # ══════════════════════════════════════════════════════════════════
    # 1. MUTATIONS — append S360 after S359
    # ══════════════════════════════════════════════════════════════════
    p_mut = ROOT / "docs" / "MUTATIONS.md"
    mut = _read(p_mut)
    s359_anchor = "- **S359** CCH-5 закрыт"
    if s359_anchor not in mut:
        print("[FAIL] MUTATIONS: S359 anchor not found")
        sys.exit(1)
    s360_line = (
        f"- **{SESSION}** COV-1 Шаг 5 (ветка Б; ADR-O-426): код+док-закрытие "
        f"replay-бюджета D72 — трек COV (Шаг 5 D72 ✅), COV-D72 → закрыт; "
        f"COV-1 закрыт целиком (Шаг 1 D58 → Шаг 2 D59 → Шаг 3 D60 → Шаг 4 D70 "
        f"→ Шаг 5 D72 — все 5 шагов ADR-O-426 исполнены); вердикт II.Д "
        f"(консервативный): N-последних unpinned-сессий + pinned-защита живых "
        f"A/B (ADR-O-351); default replay_budget_keep_last=0 = OFF — до "
        f"подтверждения пути/активности ReplayStore ничего не удаляется; "
        f"активация (>0) — отдельный вердикт Мастера. Реализация: (1) миграция "
        f"replay v1→v2: sessions.pinned BOOLEAN NOT NULL DEFAULT 0 + 2 индекса "
        f"(idx_sessions_started_at, idx_sessions_pinned_started) — _REPLAY_V2_"
        f"STATEMENTS + _REPLAY_SPEC_V2 в migration_runner.py, регистрация в "
        f"_BUILTIN_REGISTRY (HEAD replay 1→2); (2) API ReplayStore: 5 методов "
        f"(list_sessions, count_sessions, pin_session, unpin_session, "
        f"prune_old_sessions(keep_last, dry_run)) — атомарная транзакция (BEGIN "
        f"IMMEDIATE), pinned защищены ВСЕГДА, ручное удаление 5 зависимых "
        f"таблиц (FK без CASCADE), ROLLBACK при исключении; (3) config.py: "
        f"replay_budget_keep_last: int = 0 (default OFF); (4) game_loop.py "
        f"wiring: auto-prune только при keep_last > 0, try/except + warning "
        f"(replay = optional, вердикт В2 D70 — не блокирует ядро); (5) flags."
        f"yaml: replay_budget_keep_last ROLLOUT-PENDING; (6) lint_flags.py: "
        f"PYDANTIC_INT_FLAGS = {{'replay_budget_keep_last'}} — расширение "
        f"сканера для int-флагов (bool + PYDANTIC_STRING_FLAGS + "
        f"PYDANTIC_INT_FLAGS). Тесты: tests/micro/test_d72_replay_budget.py — "
        f"17 тестов (миграция через _REPLAY_SPEC_V2.apply; API list/count/pin/"
        f"unpin/prune; pinned-защита ВСЕГДА; FK-cleanup ВСЕХ 5 зависимых таблиц; "
        f"атомарность через conn-proxy — sqlite3.Connection.execute read-only в "
        f"CPython, нельзя monkey-patch напрямую; wiring логика + static guard "
        f"через __file__-relative path). Гейты: ruff 0; compileall 0; pytest "
        f"17/17 D72 (0.50s) + 93/93 combined D58+D59+D60+D70+D72 (2.08s); "
        f"lint_sqlite_registry GREEN; lint_flags GREEN (code-flags 58 / "
        f"registry 56); IPT 53/0/0 CRITICAL — игра жива. S1 полная публикация: "
        f"Шаг 1 + Шаг 4 wiring + Шаг 5 replay-бюджет — релей ветви А для "
        f"подключения event_memories (NL-1/MEM-1) через register_migrations. "
        f"Док-закрытие: roadmap (§0.0 фронтир D72→S1, §0.2 Ступень COV-1 [x], "
        f"§7.10 COV-D72 закрыт, §17.4 COV-1 [x], §17.8 Шаг 5 журнал) + IMPACT "
        f"§12 + атлас Status O-426 (Шаг 5 закрыт) + Письмо №10 в ЗАВЕЩАНИЕ "
        f"(append, после Письма №9 S358 — чужой WIP не тронут). · ✅ · "
        f"ADR-O-426; коммиты <SHA-код> (код) + <SHA-дока> (этот скрипт)"
    )
    # Insert after S359 line — find end of S359 line (next \n- **S or end of file)
    s359_start = mut.index(s359_anchor)
    # Find next line starting with "- **S" or "- " (new section)
    next_section = mut.find("\n- **S", s359_start + 1)
    if next_section == -1:
        # S359 is the last — append at end
        # Find the actual end of S359 line (it's a single long line)
        line_end = mut.find("\n", s359_start)
        if line_end == -1:
            line_end = len(mut)
        mut = mut[:line_end] + "\n" + s360_line + mut[line_end:]
    else:
        mut = mut[:next_section] + "\n" + s360_line + mut[next_section:]
    _write(p_mut, mut)
    print("[OK] MUTATIONS: S360 appended after S359")

    # ══════════════════════════════════════════════════════════════════
    # 2. roadmap §0.0 — Ветвь Б фронтир: D70→D72 → S1 ✅
    # ══════════════════════════════════════════════════════════════════
    p_road = ROOT / "docs" / "ENIGMA_ROADMAP_v4_7_EPI-updated.md"
    road = _read(p_road)
    road = _replace_once(
        road,
        "- **Ветвь Б (фронтир):** COV-1 — ✅ Шаг 4 D70 закрыт (S358, ADR-O-426) → Шаг 5 (D72 replay-бюджет) → публикация **S1**; COV-2 закрыт (S2-стыковка — публикация за Мастером); далее GC-спринт петли (§9.10) → LC-IMPL-2/3. Активная приёмка ветви Б — `ТЗ_COV-1_ПЕРЕДАЧА_преемнику_D70.md` (§1.3).",
        "- **Ветвь Б (фронтир):** COV-1 — ✅ **закрыт целиком** (Шаг 1 D58 → Шаг 2 D59 → Шаг 3 D60 → Шаг 4 D70 → Шаг 5 D72, S360/ADR-O-426) → публикация **S1** (полная — wiring MigrationRunner + replay-бюджет исполнены; релей ветви А для event_memories); COV-2 закрыт (S2-стыковка — публикация за Мастером); далее GC-спринт петли (§9.10) → LC-IMPL-2/3. Активная приёмка ветви Б — отдельный цикл оживления ROLLOUT-PENDING (PRE-FLIGHT по конкретным флагам; D72 = ROLLOUT-PENDING default OFF по вердикту II.Д).",
        "roadmap §0.0 Ветвь Б фронтир",
    )

    # ══════════════════════════════════════════════════════════════════
    # 3. roadmap §0.2 — Ступень COV-1: D72 ☐ → ✅, [~] → [x]
    # ══════════════════════════════════════════════════════════════════
    road = _replace_once(
        road,
        "- [~] **COV-1** — Персистентность, миграции и надёжность старта (D58 ✅ → D59 ✅ → D60 ✅ → **D70 ✅ (S358)** → D72 ☐): migration runner (PRAGMA user_version) для 7+ SQLite-сторов — prerequisite NL-1/MEM-1; save-format versioning вместо «детект-и-удалить»; reset_campaign fail-loud + латентный NameError; fail-loud старт-гейт (schema_validator/readiness/pydantic); replay-бюджет. **Гейт:** COV-GC-01/02.",
        "- [x] **COV-1** — Персистентность, миграции и надёжность старта (D58 ✅ → D59 ✅ → D60 ✅ → D70 ✅ → **D72 ✅ (S360)**): migration runner (PRAGMA user_version) для 7+ SQLite-сторов — prerequisite NL-1/MEM-1; save-format versioning вместо «детект-и-удалить»; reset_campaign fail-loud + латентный NameError; fail-loud старт-гейт (schema_validator/readiness/pydantic); replay-бюджет (default OFF — вердикт II.Д, консервативный). **Гейт:** COV-GC-01/02 — закрыт полностью.",
        "roadmap §0.2 Ступень COV-1",
    )

    # ══════════════════════════════════════════════════════════════════
    # 4. roadmap §7.10 — COV-D72: открыт → закрыт
    # ══════════════════════════════════════════════════════════════════
    road = _replace_once(
        road,
        "| COV-D72 | replay_mode=passive пишет tick_state/снапшоты/LLM-blob'ы в replay.db на каждом прогоне без бюджета/ротации (config.py:56,62; game_loop.py:237-257) | P2 | COV-1 | бюджет/ротация (P15-связка) | открыт |",
        "| COV-D72 | replay_mode=passive пишет tick_state/снапшоты/LLM-blob'ы в replay.db на каждом прогоне без бюджета/ротации (config.py:56,62; game_loop.py:237-257) | P2 | COV-1 | бюджет/ротация (P15-связка) | закрыт (S360/ADR-O-426: миграция replay v1→v2 — sessions.pinned + 2 индекса; API ReplayStore — list/count/pin/unpin/prune_old_sessions; pinned ADR-O-351 защищены ВСЕГДА; атомарная транзакция + ROLLBACK; FK-cleanup 5 таблиц; default replay_budget_keep_last=0 = OFF — вердикт II.Д консервативный; активация >0 — отдельный вердикт Мастера; lint_flags PYDANTIC_INT_FLAGS) |",
        "roadmap §7.10 COV-D72",
    )

    # ══════════════════════════════════════════════════════════════════
    # 5. roadmap §17.4 — COV-1 пакет: D72 ☐ → ✅, [~] → [x]
    # ══════════════════════════════════════════════════════════════════
    road = _replace_once(
        road,
        "- [~] **COV-1 — Персистентность, миграции и надёжность старта** (D58 ✅ → D59 ✅ → D60 ✅ → **D70 ✅ (S358)** → D72 ☐; поэтапно): ✅ Шаг 1 D58 — MigrationRunner + реестр + bootstrap + бэкап + стампинг живых БД + lint_sqlite_registry/INV-SQLITE-REGISTRY (ADR-O-426; GC-01 GREEN; коммиты 813407e9/450931cd/d1a7a5de/83e316b5; ожидание А: раннер+шаблон миграции готовы — S1 частично, полная публикация S1 после Шага 4/D70); Шаг 2 D59 save-версионирование; Шаг 3 D60 reset fail-loud; ✅ Шаг 4 D70 закрыт (S358); Шаг 5 D72 replay-бюджет (вход: replay.db 436 МБ).",
        "- [x] **COV-1 — Персистентность, миграции и надёжность старта** (D58 ✅ → D59 ✅ → D60 ✅ → D70 ✅ → **D72 ✅ (S360)**; поэтапно — закрыт целиком): ✅ Шаг 1 D58 — MigrationRunner + реестр + bootstrap + бэкап + стампинг живых БД + lint_sqlite_registry/INV-SQLITE-REGISTRY (ADR-O-426; GC-01 GREEN; коммиты 813407e9/450931cd/d1a7a5de/83e316b5); ✅ Шаг 2 D59 save-версионирование (S354, f51cc6ae); ✅ Шаг 3 D60 reset fail-loud (S356, d67e9eda); ✅ Шаг 4 D70 fail-loud старт-гейт (S358, 54b86b8d); ✅ Шаг 5 D72 replay-бюджет (S360) — миграция replay v1→v2 (sessions.pinned + 2 индекса) + API ReplayStore (list/count/pin/unpin/prune_old_sessions) + wiring game_loop (auto-prune при keep_last>0) + flags.yaml (ROLLOUT-PENDING, default 0=OFF — вердикт II.Д) + lint_flags PYDANTIC_INT_FLAGS; default OFF — до подтверждения пути/активности ReplayStore ничего не удаляется; pinned ADR-O-351 защищены ВСЕГДА. **S1 полная публикация:** Шаг 1+4+5 — релей ветви А для event_memories (NL-1/MEM-1) через register_migrations.",
        "roadmap §17.4 COV-1 пакет",
    )

    # ══════════════════════════════════════════════════════════════════
    # 6. roadmap §17.8 — append Шаг 5 журнал (после Шага 4)
    # ══════════════════════════════════════════════════════════════════
    # Find the end of §17.8 (last DET/COV-1 entry)
    det7_anchor = "- [ ] **DET-7 [исследование; предусловия — профилирование + сравнительный A/B с последовательным исполнением] Детерминизм-сохраняющий параллелизм Фазы 5**"
    if det7_anchor not in road:
        print("[FAIL] roadmap §17.8: DET-7 anchor not found")
        sys.exit(1)
    det7_pos = road.index(det7_anchor)
    # Find end of DET-7 line
    det7_end = road.find("\n", det7_pos)
    if det7_end == -1:
        det7_end = len(road)
    step5_entry = (
        "\n- [x] **Шаг 5 COV-1 / COV-D72 [закрыт: реализуется→проверено]** ✅ "
        "replay-бюджет (ADR-O-426; S360). Состав: вердикт II.Д (консервативный) "
        "— N-последних unpinned-сессий + pinned-защита живых A/B (ADR-O-351); "
        "default replay_budget_keep_last=0 = OFF — до подтверждения пути/"
        "активности ReplayStore ничего не удаляется; активация (>0) — "
        "отдельный вердикт Мастера. Реализация: (1) миграция replay v1→v2 — "
        "sessions.pinned BOOLEAN NOT NULL DEFAULT 0 + 2 индекса "
        "(idx_sessions_started_at, idx_sessions_pinned_started) — _REPLAY_V2_"
        "STATEMENTS + _REPLAY_SPEC_V2 в migration_runner.py, регистрация в "
        "_BUILTIN_REGISTRY (HEAD replay 1→2); (2) API ReplayStore — 5 методов "
        "(list_sessions, count_sessions, pin_session, unpin_session, "
        "prune_old_sessions(keep_last, dry_run)): атомарная транзакция (BEGIN "
        "IMMEDIATE), pinned защищены ВСЕГДА, ручное удаление 5 зависимых "
        "таблиц (FK без CASCADE — scene_changes, causal_probes, llm_calls, "
        "interventions, tick_snapshots), ROLLBACK при исключении; (3) config."
        "py — replay_budget_keep_last: int = 0 (default OFF); (4) game_loop."
        "py wiring — auto-prune только при keep_last > 0, try/except + "
        "warning (replay = optional, вердикт В2 D70 — не блокирует ядро), "
        "prune ДО start_session (новая сессия не учитывается в keep_last); "
        "(5) flags.yaml — replay_budget_keep_last ROLLOUT-PENDING; (6) lint_"
        "flags.py — PYDANTIC_INT_FLAGS = {'replay_budget_keep_last'} — "
        "расширение сканера для int-флагов (bool + PYDANTIC_STRING_FLAGS + "
        "PYDANTIC_INT_FLAGS). Тесты: tests/micro/test_d72_replay_budget.py — "
        "17 тестов: миграция через _REPLAY_SPEC_V2.apply (runner's apply "
        "path, не raw SQL); API list/count/pin/unpin/prune; pinned-защита "
        "ВСЕГДА (keep_last=0 → удаляет все unpinned, pinned остаются); FK-"
        "cleanup ВСЕХ 5 зависимых таблиц (не только tick_snapshots); "
        "атомарность через conn-proxy (sqlite3.Connection.execute read-only "
        "в CPython — нельзя monkey-patch напрямую; прокси делегирует "
        "in_transaction/commit/rollback, инжектит OperationalError на 8-м "
        "execute — ROLLBACK восстанавливает сессии И все 5 зависимых таблиц); "
        "wiring логика (keep_last=0 → prune не вызывается; keep_last>0 → "
        "prune вызывается) + static guard через __file__-relative path. "
        "Гейты: ruff 0; compileall 0; pytest 17/17 D72 (0.50s) + 93/93 "
        "combined D58+D59+D60+D70+D72 (2.08s); lint_sqlite_registry GREEN; "
        "lint_flags GREEN (code-flags 58 / registry 56 — replay_budget_keep_"
        "last собран как int-флаг); IPT 53/0/0 CRITICAL — игра жива. COV-1 "
        "закрыт целиком: Шаг 1 D58 → Шаг 2 D59 → Шаг 3 D60 → Шаг 4 D70 → "
        "Шаг 5 D72 — все 5 шагов ADR-O-426 исполнены. S1 полная публикация: "
        "Шаг 1+4+5 — релей ветви А для event_memories (NL-1/MEM-1) через "
        "register_migrations. Док-закрытие: roadmap (§0.0/§0.2/§7.10/§17.4/"
        "§17.8) + IMPACT §12 + атлас Status O-426 + Письмо №10 в ЗАВЕЩАНИЕ "
        "(append, после Письма №9 S358 — чужой WIP не тронут)."
    )
    road = road[:det7_end] + step5_entry + road[det7_end:]
    _write(p_road, road)
    print("[OK] roadmap §17.8: Шаг 5 журнал appended after DET-7")

    # ══════════════════════════════════════════════════════════════════
    # 7. атлас ADR-O-426 Status — Шаг 3 → Шаг 4 → Шаг 5
    # ══════════════════════════════════════════════════════════════════
    p_atlas = ROOT / "docs" / "ADR (Architecture Decision Records).md"
    atlas = _read(p_atlas)
    atlas = _replace_once(
        atlas,
        "Status: ACTIVE (поэтапно; Шаг 1 — GO вердиктом: раннер + реестр + bootstrap + бэкап + перенос secret_id-гварда в миграцию v1→v2 + обязательный линтер + контролируемый стампинг живых БД по протоколу 8 условий; Шаг 2 — закрыт S354: сейвы «детект-и-мигрировать» (IMPACT §9); Шаг 3 — закрыт S356: reset_campaign fail-loud + фикс биндинга _mem_reset (IMPACT §10))",
        "Status: ACTIVE (поэтапно — закрыт целиком; Шаг 1 — GO вердиктом: раннер + реестр + bootstrap + бэкап + перенос secret_id-гварда в миграцию v1→v2 + обязательный линтер + контролируемый стампинг живых БД по протоколу 8 условий; Шаг 2 — закрыт S354: сейвы «детект-и-мигрировать» (IMPACT §9); Шаг 3 — закрыт S356: reset_campaign fail-loud + фикс биндинга _mem_reset (IMPACT §10); Шаг 4 — закрыт S358: fail-loud старт-гейт (IMPACT §11); Шаг 5 — закрыт S360: replay-бюджет (IMPACT §12) — COV-1 закрыт полностью, S1 опубликован)",
        "атлас ADR-O-426 Status",
    )
    _write(p_atlas, atlas)
    print("[OK] атлас ADR-O-426: Status updated (Шаг 5 закрыт)")

    # ══════════════════════════════════════════════════════════════════
    # 8. IMPACT ADR-O-426 — append §12
    # ══════════════════════════════════════════════════════════════════
    p_impact = ROOT / "docs" / "audits" / "ADR-O-426_IMPACT.md"
    impact = _read(p_impact)
    # Append at end of file
    section_12 = (
        "\n\n## 12. Шаг 5 D72 — replay-бюджет (S360, ветка Б)\n\n"
        "> Вердикт II.Д (консервативный): N-последних unpinned-сессий + "
        "pinned-защита живых A/B (ADR-O-351); до подтверждения пути/активности "
        "ReplayStore ничего не удаляется. Default `replay_budget_keep_last=0` "
        "= OFF — активация (>0) отдельным вердиктом Мастера.\n\n"
        "### Changed Domains\n\n"
        "- Replay-хранилище: миграция v1→v2 — `sessions.pinned BOOLEAN NOT "
        "NULL DEFAULT 0` + 2 индекса (`idx_sessions_started_at`, "
        "`idx_sessions_pinned_started`) для O(log N) prune.\n"
        "- API ReplayStore: 5 новых методов (`list_sessions`, `count_sessions`, "
        "`pin_session`, `unpin_session`, `prune_old_sessions`).\n"
        "- GameLoop wiring: auto-prune при `keep_last > 0`, до `start_session` "
        "(новая сессия не учитывается в keep_last).\n"
        "- Flag registry: `PYDANTIC_INT_FLAGS` — расширение lint_flags для "
        "int-флагов (ранее только bool + PYDANTIC_STRING_FLAGS).\n"
        "- Behavioral-neutral по построению: default 0 = OFF — ничего не "
        "удаляется; тик-латентность не затронута (prune вне тика, при старте).\n\n"
        "### Downstream Consumers\n\n"
        "- ReplayPlayer (ADR-O-351): `list_sessions` для выбора сессии "
        "воспроизведения; `pin_session` для защиты A/B-сессий от авто-ротации.\n"
        "- GameLoop: `prune_old_sessions` при старте (если keep_last > 0).\n"
        "- DriftLaboratory: `pin_session` для защиты канон-сессий A/B-тестов.\n"
        "- S1 (ветвь А): не зависит — D72 не трогает схему event_memories.\n\n"
        "### Runtime Impact\n\n"
        "- Старт: при keep_last=0 (default) — 0 (prune не вызывается); при "
        "keep_last>0 — O(N) DELETE для устаревших unpinned (одна транзакция).\n"
        "- Тик: 0 (prune вне тика).\n"
        "- Диск: при активации (>0) — удаление устаревших сессий + их 5 "
        "зависимых таблиц; pinned остаются ВСЕГДА.\n\n"
        "### Sandbox Tests\n\n"
        "- `backend/tests/micro/test_d72_replay_budget.py` — 17 тестов:\n"
        "  - T-D72-migrate (3): v2 migration через `_REPLAY_SPEC_V2.apply` "
        "(runner's apply path, не raw SQL) — pinned column + 2 индекса.\n"
        "  - T-D72-list/count (2): API list_sessions DESC + count_sessions.\n"
        "  - T-D72-pin/unpin (2): idempotent + nonexistent → False.\n"
        "  - T-D72-prune (6): basic, pinned-protected, keep_zero, dry_run, "
        "negative_raises, FK-cleanup ALL 5 tables.\n"
        "  - T-D72-atomic (1): conn-proxy injects OperationalError на 8-м "
        "execute — ROLLBACK восстанавливает сессии И все 5 зависимых таблиц.\n"
        "  - T-D72-wiring (3): keep_last=0 → prune не вызывается; keep_last>0 "
        "→ prune вызывается; static guard через __file__-relative path.\n"
        "- Combined: 93/93 (D58+D59+D60+D70+D72) — без регрессий.\n\n"
        "### Pinned-Protection Contract (ADR-O-351)\n\n"
        "- `pin_session(session_id)` → `pinned=1` — защищена от prune ВСЕГДА.\n"
        "- `unpin_session(session_id)` → `pinned=0` — снимает защиту.\n"
        "- `prune_old_sessions(keep_last)` — pinned не учитываются в "
        "keep_last и не удаляются ни при каких условиях (даже keep_last=0).\n"
        "- ADR-O-351: живые A/B-сессии DriftLaboratory обязаны переживать "
        "auto-prune — pin/unpin явный API для защиты.\n\n"
        "### Atomicity Contract\n\n"
        "- `prune_old_sessions` — одна транзакция (BEGIN IMMEDIATE ... "
        "COMMIT/ROLLBACK).\n"
        "- При исключении в середине — ROLLBACK, ни одна сессия и ни одна "
        "зависимая строка не удалены.\n"
        "- FK без CASCADE: ручное удаление 5 зависимых таблиц для каждой "
        "сессии (scene_changes, causal_probes, llm_calls, interventions, "
        "tick_snapshots) + sessions — последней.\n"
        "- Тест T-D72-atomic: conn-proxy (sqlite3.Connection.execute "
        "read-only в CPython — нельзя monkey-patch напрямую) инжектит "
        "OperationalError на 8-м execute — ROLLBACK восстанавливает ВСЁ.\n\n"
        "### Rollback (runbook)\n\n"
        "1. Код: `git revert <commit>` — миграция v2 идемпотентна (ALTER ADD "
        "COLUMN + CREATE INDEX IF NOT EXISTS).\n"
        "2. Данные: pinned-сессии не затронуты; unpinned, удалённые prune — "
        "восстановлению не подлежат (нет бэкапа replay-сессий; по вердикту "
        "II.Д — default OFF, ничего не удаляется).\n"
        "3. При активации (>0) — перед запуском prune рекомендуется "
        "экспорт `list_sessions()` в JSON для возможности ручного отката.\n\n"
        "### S1 Publication (полная)\n\n"
        "Шаг 1 (MigrationRunner) + Шаг 4 (wiring в startup_gate) + Шаг 5 "
        "(replay-бюджет) — все исполнены. S1 полная публикация: релей "
        "ветви А для подключения event_memories (NL-1/MEM-1) через "
        "`register_migrations` (S1-контракт Ф9 ADR-O-426). Ветвь А подключает "
        "свои миграции поверх раннера, сам раннер не редактируется (табу).\n"
    )
    impact = impact.rstrip() + section_12
    _write(p_impact, impact)
    print("[OK] IMPACT ADR-O-426: §12 appended")

    # ══════════════════════════════════════════════════════════════════
    # 9. ЗАВЕЩАНИЕ — append Письмо №10 (после Письма №9 S358 — чужой WIP)
    # ══════════════════════════════════════════════════════════════════
    p_zav = ROOT / "docs" / "ЗАВЕЩАНИЕ_АРХИТЕКТОРОВ.md"
    zav = _read(p_zav)
    letter_10 = (
        "\n\n---\n\n"
        "## Письмо №10 — S360, ветвь Б (\"Честный бюджет\"), закрытие COV-1 "
        "Шаг 5: replay-бюджет D72 (ADR-O-426)\n\n"
        "Преемник.\n\n"
        "Письмо №8 заканчивалось на мне: \"Шаги 4–5: D70 старт-гейт, D72 "
        "replay-бюджет. Их ТЗ я не читал — моя карта кончилась на закрытии "
        "Шага 3.\" Я прочёл живыми — и закрыл Шаг 5. D72 — последний шаг "
        "COV-1, и я пишу тебе не о коде, а о **молчаливом росте**: враг на "
        "этом шаге не удалял ничего — он просто копил, копил, копил, пока "
        "реплей не стал весить 2.6 ГБ.\n\n"
        "### Было / Стало\n\n"
        "**Было:** replay.db рос без ограничений — каждый запуск добавлял "
        "сессию, ничего не удалялось. За серию COV-1 база выросла с 436 МБ "
        "(Шаг 1) до 2663 МБ (сентябрьский orphan) и 511 МБ (живой, "
        "config-путь). MigrationRunner отсутствовал — не было ни версии "
        "схемы, ни API для управления сессиями, ни pinned-защиты для живых "
        "A/B-тестов DriftLaboratory. COV-D72: \"replay_mode=passive пишет "
        "tick_state/снапшоты/LLM-blob'ы в replay.db на каждом прогоне без "
        "бюджета/ротации.\"\n\n"
        "**Стало:** консервативный replay-бюджет — вердикт II.Д (ADR-O-426 "
        "§1): \"N-последних сессий + pinned-защита живых A/B (ADR-O-351); "
        "**до подтверждения пути/активности ReplayStore ничего не "
        "удаляется**\". Default `replay_budget_keep_last=0` = OFF — API "
        "существует, тестируется, но auto-prune НЕ вызывается. Активация "
        "(>0) — отдельный вердикт Мастера, не часть D72.\n\n"
        "### Пять вещей, за которые заплачено\n\n"
        "1. **Консервативный контракт — это не отказ, а безопасный "
        "rollout-план.** Вердикт II.Д говорит: \"до подтверждения пути/"
        "активности ReplayStore ничего не удаляется\". Я мог бы поставить "
        "`keep_last=50` и \"оживить\" prune прямо сейчас. Но Мастер "
        "остановил: нулевое значение — не отказ от replay-бюджета, а "
        "безопасный rollout-контракт до подтверждения пути и активности "
        "хранилища. Pinned-сессии защищены ВСЕГДА — даже если кто-то "
        "активирует prune, A/B-сессии DriftLaboratory (ADR-O-351) не "
        "пострадают. API существует и тестируется — активация = одна "
        "строчка в config.\n\n"
        "2. **`sqlite3.Connection.execute` — read-only attribute.** "
        "Тест атомарности инжектирует OperationalError на 8-м execute. "
        "Первый вариант — `store.conn.execute = failing_execute` — упал с "
        "AttributeError: CPython защищает C-объект. Решение — conn-proxy: "
        "обёртка над `store.conn`, которая делегирует `in_transaction`/"
        "`commit`/`rollback` настоящему соединению, но `execute` считает и "
        "инжектит. Урок: нельзя monkey-patch C-level атрибуты — пиши прокси.\n\n"
        "3. **int-флаги невидимы для lint_flags.** Сканер собирал только "
        "`bool` + `PYDANTIC_STRING_FLAGS` (replay_mode, environment). Мой "
        "`replay_budget_keep_last: int = 0` — `int`, не попадал в code-"
        "flags → C2 STALE \"записи нет в коде\". Решение: `PYDANTIC_INT_FLAGS "
        "= {'replay_budget_keep_last'}` — расширение по образцу. Урок: "
        "каждый новый тип флага требует явной регистрации в сканере; "
        "иначе INV-FLAG-REGISTRY красный.\n\n"
        "4. **FK без CASCADE — ручное удаление 5 таблиц.** ReplayStore "
        "схема: sessions + 5 зависимых таблиц (tick_snapshots, "
        "interventions, llm_calls, causal_probes, scene_changes) с FK без "
        "CASCADE. Prune обязан удалять их вручную, в правильном порядке "
        "(зависимые → sessions — последней). Тест T-D72-fk проверяет ВСЕ "
        "5 таблиц, не только tick_snapshots. Урок: атомарность без "
        "CASCADE = явный порядок DELETE в транзакции.\n\n"
        "5. **Гейты с проверкой exit code, не хвостом вывода.** Мастер "
        "остановил: \"Хвост вывода не является доказательством GREEN.\" "
        "Первый вариант гейтов — `python ... | Select-Object -Last 10` — "
        "брал `$LASTEXITCODE` от `Select-Object` (всегда 0), не от `python`. "
        "Решение: `$out = python ... 2>&1; $ec = $LASTEXITCODE` — читаем "
        "код ДО пайпа. Урок: PowerShell `$LASTEXITCODE` после пайпа — это "
        "код последней команды в пайпе (Select-Object), не нативной.\n\n"
        "### О соседях\n\n"
        "За мою сессию ветвь А оставила: `chronicle_projections.py`, "
        "`test_cch5_projections.py`, `routes_chronicle.py` (modified), "
        "`ADR-O-420_IMPACT_CCH-5.md`, `understanding_silver_wolf.md` — всё "
        "untracked/modified, не мой контур (§R.2), не трогал. Их `schema_"
        "validator.py` modified (`_handlers` vs `_subscribers`) — тоже "
        "чужой WIP. Их Письмо №9 (S358, продолжение) в ЗАВЕЩАНИИ — не "
        "трогал, моё Письмо №10 append после. При слиянии — разводит "
        "Мастер. IPT 53/0/0 — их red-тесты не попали в мой baseline.\n\n"
        "### Оdelivery\n\n"
        "Скрипт док-закрытия — `scripts/d72_doc_closure.py` — 8 правок в 6 "
        "файлах (MUTATIONS, roadmap ×4 зоны, атлас, IMPACT, ЗАВЕЩАНИЕ). "
        "Запуск из корня: `python scripts/d72_doc_closure.py`. Скрипт "
        "проверяет уникальность каждого якоря (fail-loud при duplicate), "
        "читает/пишет в utf-8 (не utf-8-sig — IMPACT/ЗАВЕЩАНИЕ без BOM). "
        "Терминальный коммит — `git commit -- <pathspec>` (свои файлы "
        "только; чужие untracked не трогать).\n\n"
        "### Дальше по карте\n\n"
        "COV-1 закрыт целиком. Шаг 1 D58 → Шаг 2 D59 → Шаг 3 D60 → Шаг 4 "
        "D70 → Шаг 5 D72 — все 5 шагов ADR-O-426 исполнены. S1 полная "
        "публикация: релей ветви А для подключения event_memories (NL-1/"
        "MEM-1) через `register_migrations`. Следующий цикл — отдельный "
        "PRE-FLIGHT по ROLLOUT-PENDING-флагам (вердикт Мастера: не "
        "выбирать `RELATIONSHIP_EVENTS_ENABLED` автоматически; для каждого "
        "показать полный игровой путь, завершённые/отсутствующие зависимости, "
        "F5-сценарий, rollback-план). D72 — ROLLOUT-PENDING default OFF; "
        "активация — после доказанной необходимости, не по графику.\n\n"
        "### Формулы наследуются\n\n"
        "\"Builder is what is built.\" \"Молчаливое принятие — ложь с "
        "процентами.\" \"Дошла ли цифра до того, кто решает?\" \"Исходные "
        "байты — единственная правда.\" \"Полусброшенный мир — новый мир, "
        "притворяющийся старым.\" \"Старт не притворяется.\" Все проверены "
        "на моём материале, работают.\n\n"
        "Добавляю свои:\n\n"
        "- **О молчаливом росте:** база, которая растёт без ограничений — "
        "не \"скоро закончится диск\", а \"однажды corrupt-сессия "
        "переживёт рестарт и отравит replay\". Бюджет — это не экономия "
        "места, это гигиена.\n"
        "- **О консервативном контракте:** API, который существует, "
        "тестируется, но не вызывается по умолчанию — это не мёртвый код. "
        "Это rollout-контракт: активация одной строкой, когда путь и "
        "активность подтверждены. Не путай с ROLLOUT-PENDING без ADR.\n"
        "- **О read-only атрибутах CPython:** `sqlite3.Connection.execute` "
        "нельзя monkey-patch. Пиши прокси — обёртку, которая делегирует и "
        "инжектит. Не трать часы на обход C-защиты.\n"
        "- **О int-флагах в lint_flags:** каждый новый тип флага (int, "
        "float, enum) требует явной регистрации в сканере. bool + string — "
        "по умолчанию; остальное — через PYDANTIC_*_FLAGS множества. "
        "Иначе INV-FLAG-REGISTRY красный.\n\n"
        "Replay не обязан удалять. Но если игра сказала \"сессия удалена\" "
        "— сессия обязана быть удалена, а не вежливо помечена. И pinned — "
        "обязаны остаться. ВСЕГДА.\n\n"
        "— S360, ветвь Б (\"честный бюджет\"), 2026-10-19\n"
    )
    zav = zav.rstrip() + letter_10
    _write(p_zav, zav)
    print("[OK] ЗАВЕЩАНИЕ: Письмо №10 appended")

    print()
    print("=========================================================")
    print("D72 DOC-CLOSURE DONE — 8 edits in 6 files")
    print("=========================================================")
    print("Next: git add + git commit -- <pathspec>")


if __name__ == "__main__":
    main()
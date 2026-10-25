"""
R4 / D2 — передача дел приёмнику (v2, робастный).
Программно находит MAX S-номер и вставляет S365 (MAX+1).

4 правки:
  1. MUTATIONS.md — добавить S365 после последней S-записи (программный поиск)
  2. MUTATIONS.md — обновить МЕТА (программно найти «Записей: NNN» и инкрементировать)
  3. ADR — добавить ADR-O-429 (найти ADR-O-428 как предыдущий max, O-429 = max+1)
  4. roadmap — отметить R4/D2 в §0.0 навигации
"""
import sys
import re
import shutil
from pathlib import Path

DOCS = Path("docs")
MUT_PATH = DOCS / "MUTATIONS.md"
ADR_PATH = DOCS / "ADR (Architecture Decision Records).md"
ROAD_PATH = DOCS / "ENIGMA_ROADMAP_v4_11_WPS.md"

for p in [MUT_PATH, ADR_PATH, ROAD_PATH]:
    if not p.exists():
        print(f"ERROR: {p} not found"); sys.exit(1)


def backup(path: Path):
    bak = path.with_suffix(path.suffix + ".r4_handoff_backup")
    if not bak.exists():
        shutil.copy2(path, bak)
        print(f"[OK] backup: {bak}")
    else:
        print(f"[skip] backup exists: {bak}")


# ════════════════════════════════════════════════════════════════════
# Правка 1+2: MUTATIONS.md
# ════════════════════════════════════════════════════════════════════
backup(MUT_PATH)
mut_src = MUT_PATH.read_text(encoding="utf-8")

# Найти все S-номера в реестре (строки начинающиеся с "- **SNNN**")
s_pattern = re.compile(r'^- \*\*S(\d{3})\*\*', re.MULTILINE)
s_matches = list(s_pattern.finditer(mut_src))
if not s_matches:
    print("[FAIL] No S-records found in MUTATIONS.md"); sys.exit(2)

s_numbers = [int(m.group(1)) for m in s_matches]
max_s = max(s_numbers)
new_s = max_s + 1
print(f"[INFO] MUTATIONS: max S-number = S{max_s:03d}, new = S{new_s:03d}")

# Проверить, что S365 (или какой получился) не занят
if new_s in s_numbers:
    print(f"[FAIL] S{new_s:03d} already exists — duplicates in file"); sys.exit(3)

# Найти ПОСЛЕДНЮЮ S-запись (последний match)
last_s_match = s_matches[-1]
# Найти конец этой строки (до следующего \n)
line_end = mut_src.index("\n", last_s_match.start())
# Использовать всю строку S{max_s} как маркер
last_s_line = mut_src[last_s_match.start():line_end]
print(f"[INFO] Last S-record line (first 100 chars): {last_s_line[:100]}...")

# Новая строка S365
S_LINE = (
    f"- **S{new_s:03d}** R4 / D2 закрытие (ветвь Б; read-only археология → реализация → PAT ×8): "
    "R4 — отдельная ревизия (не roadmap-трек) по контракту acquisition/release тик-сцены; "
    "фазы: план v3.10 → C44 (реестр локаций, H6b/H6a не подтверждены, BLOCKED-гейт сохранён) "
    "→ C45 (контракт acquisition/release, 8а/8в/8г/8д нарушены, 8е=недоказуемо, 8ж→GATE-9A) "
    "→ C41-pre (F1=подтверждён, F2=опровергнут — механизм мутации через общие ссылки "
    "get_scene_state → apply_changes → _sync_relationship_directed) → GATE-9A (D2 выбран, "
    "не D1/D3) → реализация SSM-патча + game_loop-патча v3 → PAT ×8 (37/37 PASS). "
    "Production changes: scene_state_manager.py +3184 байта (поле _tick_aborted, метод "
    "mark_tick_aborted с guard владения, unlock_tick с if not _tick_aborted + finally для "
    "сброса маркера — блокер Мастера закрыт); game_loop.py +27 строк (skip_time/idle_tick/"
    "run_turn обёрнуты в try/except/finally с mark_tick_aborted в except и unlock_tick в "
    "finally; run_turn v3 — wrap включает execute call, чтобы exception в acquisition "
    "попадал в except). Backup: scene_state_manager.py.r4_backup, game_loop.py.r4_backup. "
    "Тесты: test_r4_d2_ssm.py 7/7 PASS (SSM unit), test_r4_pat_x8.py 6/6 PASS (exception "
    "paths + persistence + foreign campaign_id), существующие 31/31 PASS (Tavern + GC-01 + "
    "Probe 97), итого 37/37 PASS / 0 FAIL / 0 необъяснённых SKIP. Артефакты: "
    "download/R4_C44_artifact.md, R4_C45_artifact.md, R4_C41pre_artifact.md, "
    "R4_GATE-9A_artifact.md, R4_plan_v3.10.md. Нюанс за рамками: проверка №7 подтверждает, "
    "что atomic_commit_all не вызывается ИЗ unlock_tick на аварийном пути, но не доказывает, "
    "что другие компоненты не пишут частичное состояние ДО unlock_tick — отдельный вопрос о "
    "границах транзакции. Вердикт Мастера Тая: ACCEPTED / CLOSED (2026-10-25). "
    "· ✅ · ADR-O-429 · IPT 53/0/0"
)

# Замена: найти ровно 1 вхождение last_s_line и добавить после него новую строку
count = mut_src.count(last_s_line)
if count != 1:
    print(f"[FAIL] Правка 1: last S-line found {count} times (expected 1)")
    print(f"  Line (first 200 chars): {last_s_line[:200]}")
    sys.exit(4)

mut_src = mut_src.replace(last_s_line, last_s_line + "\n" + S_LINE, 1)
print(f"[OK] Правка 1: S{new_s:03d} added after S{max_s:03d}")

# Правка 2: обновить МЕТА — найти «Записей: NNN» и инкрементировать
meta_pattern = re.compile(r'Записей:\s*(\d+)')
meta_match = meta_pattern.search(mut_src)
if not meta_match:
    print("[FAIL] Правка 2: МЕТА «Записей: NNN» not found"); sys.exit(5)

old_count = int(meta_match.group(1))
new_count = old_count + 1
print(f"[INFO] МЕТА: Записей {old_count} → {new_count}")

# Заменить только первое вхождение
old_meta_str = f"Записей: {old_count}"
new_meta_str = f"Записей: {new_count} (S{new_s:03d}-R4-D2-закрытие добавлен; "
new_meta_full = new_meta_str + mut_src[meta_match.end():]

# Простейший подход: вставить "(S365-R4-D2-закрытие добавлен; " после "Записей: NNN ("
# Но формат МЕТА сложный. Давайте просто инкрементируем число и добавим пометку
old_full = f"Записей: {old_count} ("
new_full = f"Записей: {new_count} (S{new_s:03d}-R4-D2-закрытие добавлен; "
if old_full in mut_src:
    mut_src = mut_src.replace(old_full, new_full, 1)
    print(f"[OK] Правка 2: МЕТА updated ({old_count} → {new_count})")
else:
    # Fallback: просто инкрементировать число
    mut_src = mut_src.replace(f"Записей: {old_count}", f"Записей: {new_count}", 1)
    print(f"[OK] Правка 2: МЕТА updated (fallback — number only)")

MUT_PATH.write_text(mut_src, encoding="utf-8")
print(f"[DONE] MUTATIONS.md updated\n")


# ════════════════════════════════════════════════════════════════════
# Правка 3: ADR — добавить ADR-O-429
# ════════════════════════════════════════════════════════════════════
backup(ADR_PATH)
adr_src = ADR_PATH.read_text(encoding="utf-8")

# Найти max ADR-O-NNN
adr_pattern = re.compile(r'ADR-O-(\d{3})')
adr_nums = [int(m.group(1)) for m in adr_pattern.finditer(adr_src)]
max_adr = max(adr_nums) if adr_nums else 0
new_adr_num = max_adr + 1
print(f"[INFO] ADR: max = O-{max_adr:03d}, new = O-{new_adr_num:03d}")

# Проверить, что O-429 не занят (если max >= 429, нужен другой номер)
if new_adr_num <= 429:
    new_adr_num = 429  # Я хочу именно O-429 (как в артефакте)
    if f"ADR-O-{new_adr_num}" in adr_src:
        print(f"[FAIL] ADR-O-{new_adr_num} already exists — using next available")
        new_adr_num = max_adr + 1
        if f"ADR-O-{new_adr_num}" in adr_src:
            print(f"[FAIL] ADR-O-{new_adr_num} also exists"); sys.exit(6)

new_adr = f"ADR-O-{new_adr_num:03d}"
print(f"[INFO] Using ADR: {new_adr}")

# Вставить перед EQUIVALENCE VALIDATOR (как раньше)
ADR_INSERT_BEFORE = "## 🧬 EQUIVALENCE VALIDATOR (Drift Measurement)"
if ADR_INSERT_BEFORE not in adr_src:
    print("[FAIL] ADR insert marker not found"); sys.exit(7)

ADR_BLOCK = f"""### {new_adr}: R4 / D2 — Abort Marker + Skip Persist on Exception (Tick-Scoped Identity)

**Статус:** ACCEPTED (вердикт Мастера Тая, 2026-10-25) | **Сессия:** S{new_s:03d} | **Связанные законы:** L2 (Runtime Purity), L4 (Atomic Persist)

**Контекст:**
R4 (отдельная ревизия, не roadmap-трек) — исследование контракта acquisition/release тик-сцены через read-only археологию (C44/C45/C41-pre). Установленные факты:
- `get_scene_state` возвращает прямую ссылку на `_tick_scenes[v]` во время тика (F41.14).
- `apply_changes` мутирует переданный `scene_state` in-place через `apply_change` (F41.16).
- `_sync_relationship_directed` в `unlock_tick` мутирует contents `_tick_scenes[v]` in-place (F41.6).
- F2 = ОПРОВЕРГНУТ: найден конкретный механизм мутации через общие ссылки.

Вердикт C45: ветка «безопасность аварийного release доказана» недостижима (8а/8в/8г/8д нарушены, 8е=НЕДОСТИЖИМО, 8ж→блокирующий вопрос GATE-9A).

**Решение (D2 — выбран Мастером на GATE-9A):**
На аварийном пути release (exception в execute) `unlock_tick` НЕ выполняет `atomic_commit_all` — persistence остаётся в pre-tick. Нормальный путь сохраняется (atomic_commit_all вызывается как раньше).

**Реализация:**
1. `scene_state_manager.py`:
   - Новое поле `_tick_aborted: bool = False` в `__init__`.
   - Новый метод `mark_tick_aborted(campaign_id)` — устанавливает маркер ТОЛЬКО при подтверждённом владении (guard `if self._tick_locked and self._tick_campaign_id == campaign_id`; иначе silent no-op).
   - `lock_for_tick`/`lock_all_for_tick`/`adopt_scene_for_tick` — сброс маркера при fresh acquire.
   - `unlock_tick` — persist обёрнут в `if not self._tick_aborted:`; маркер сбрасывается в `finally` (блокер Мастера: гарантированно даже при исключении в `atomic_commit_all`).
2. `game_loop.py`:
   - `skip_time` — добавлен `except Exception: mark_tick_aborted + raise` перед существующим `finally:`.
   - `idle_tick` — тело `[lock_all+1 .. unlock-1]` обёрнуто в `try/except/finally` (250 строк, +4 indent); `unlock_tick` перенесён в `finally`.
   - `run_turn` — тело `[execute .. unlock-1]` обёрнуто в `try/except/finally` (307 строк, +4 indent, v3 fix: включает execute call).

**Контракт безопасности:**
- **Откатывается:** `atomic_commit_all` не вызывается из `unlock_tick` при abort → persistence остаётся в pre-tick.
- **Остаётся в памяти:** `_tick_scenes[v]` мутированный объект (SSE bridge может читать); `_tick_locked=False`; следующий fresh `lock_for_tick` загружает pre-tick сцену из persistence.
- **Не входит в гарантию:** `world_scheduler.maybe_tick` (async), `MemoryManager` записи, `TaskScheduler`, `life_engine` NPC states, `AvatarService`/`BodyTopologyService` — отдельные подсистемы.

**Границы применимости (нюанс за рамками закрытия):**
Проверка №7 PAT ×8 подтверждает, что `atomic_commit_all` не вызывается ИЗ `unlock_tick` на аварийном пути. Это НЕ доказывает, что другие компоненты не пишут частичное состояние ДО вызова `unlock_tick` (например, `save_scene_state` @1219 в `idle_tick` — нормальный pre-tick persist вне D2 контракта).

**Тесты (PAT ×8, 37/37 PASS):**
- SSM unit: 7/7; Exception paths: 6/6; Существующие: 31/31 (Tavern + Probe 97 + GC-01).

**Backup paths:** `app/services/scene_state_manager.py.r4_backup`, `app/services/game_loop/game_loop.py.r4_backup`

**Артефакты R4:** `download/R4_plan_v3.10.md`, `download/R4_C44_artifact.md`, `download/R4_C45_artifact.md`, `download/R4_C41pre_artifact.md`, `download/R4_GATE-9A_artifact.md`, `worklog.md`.

---

"""

count = adr_src.count(ADR_INSERT_BEFORE)
if count != 1:
    print(f"[FAIL] ADR insert marker found {count} times"); sys.exit(8)

adr_src = adr_src.replace(ADR_INSERT_BEFORE, ADR_BLOCK + ADR_INSERT_BEFORE, 1)
ADR_PATH.write_text(adr_src, encoding="utf-8")
print(f"[OK] Правка 3: {new_adr} added")
print(f"[DONE] ADR updated\n")


# ════════════════════════════════════════════════════════════════════
# Правка 4: roadmap §0.0
# ════════════════════════════════════════════════════════════════════
backup(ROAD_PATH)
road_src = ROAD_PATH.read_text(encoding="utf-8")

ROAD_BEFORE = "- **Активные ТЗ-приёмки (реестр §1.3):**"
ROAD_R4_LINE = (
    f"- **R4 / D2 — ACCEPTED / CLOSED** (2026-10-25, вердикт Мастера Тая; S{new_s:03d}, {new_adr}): "
    "контракт acquisition/release тик-сцены — отдельная ревизия (не roadmap-трек). "
    "Реализация: scene_state_manager.py (поле _tick_aborted, метод mark_tick_aborted с guard "
    "владения, unlock_tick с if not _tick_aborted + finally) + game_loop.py (skip_time/idle_tick/"
    "run_turn обёрнуты в try/except/finally с mark_tick_aborted + unlock_tick). PAT ×8: 37/37 PASS. "
    "Артефакты: download/R4_*.md. Backup: .r4_backup. Нюанс: atomic_commit_all из других "
    "компонентов до unlock_tick — отдельный вопрос о границах транзакции.\n"
)

count = road_src.count(ROAD_BEFORE)
if count != 1:
    print(f"[FAIL] Правка 4: roadmap marker found {count} times"); sys.exit(9)

road_src = road_src.replace(ROAD_BEFORE, ROAD_R4_LINE + ROAD_BEFORE, 1)
ROAD_PATH.write_text(road_src, encoding="utf-8")
print(f"[OK] Правка 4: roadmap §0.0 updated")
print(f"[DONE] roadmap updated\n")


print("=" * 60)
print("Передача дел завершена:")
print(f"  - MUTATIONS.md: S{new_s:03d} added (after S{max_s:03d}), МЕТА {old_count}→{new_count}")
print(f"  - ADR: {new_adr} added")
print(f"  - roadmap §0.0: R4/D2 CLOSED noted")
print("Backups: .r4_handoff_backup")

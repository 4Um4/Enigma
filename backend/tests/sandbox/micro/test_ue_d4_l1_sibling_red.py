"""UX-UE-01 / D4 sibling-audit: L1-фиксация директив игрока (SHI-FIX CAUSAL). v4 GREEN.

Имя файла сохранено (pathspec-дисциплина коммита); стадия — здесь.

Применено (scripts/patch_ue_l1_sibling.py --write): readiness-гейт на commit
L1-фиксации в backend/app/services/game_loop/npc_orchestration.py.

История стадий:
    v3 RED : 4 контракта XFAIL(strict) — доказательство отсутствия гейта.
    Прогон оператора: 4 XPASS(strict) — контракты прошли => патч влит.
    (дефект v3: предпосылка-якорь искала ДО-патчевый `if _l1_events:` —
    после патча его нет; отсюда FAILED якоря при XPASS контрактов.)
    v4 GREEN (этот файл): xfail-маркеры сняты, якорь переведён в гейтованную
    форму, добавлены инварианты целостности try-тела и дефолта RESOLVED.

Регрессионные инварианты (зелёные всегда):
    1. Файл синтаксически цел.
    2. Commit-блок открыт ТОЛЬКО при RESOLVED — для ВСЕХ sem_action.
    3. Чтение readiness предшествует commit.
    4. [UE-GATE-L1] >= 2 (attack-гейт + гейт фиксации).
    5. Подавление наблюдаемо в консоли (warning-текст).
    6. try-тело commit не задето: bind_campaign + commit_tick_buffer +
       [L1_FIXATION]-лог + except-ветка.
    7. Дефолт "RESOLVED" при отсутствии intent_resolution.

Живая приемка (вне pytest): run_terminal_mvp, 'Не угрожать Торнину' /
'Держаться подальше от Торнина' → [UE-GATE-L1]-подавление фиксации, НЕТ
[L1_FIXATION] sem_action=THREATEN/MOVE. Контроль: 'Бью Люсю по носу'
(RESOLVED ATTACK) → [L1_FIXATION] остаётся. Консоль вернуть → D4-финал.

Запуск ИЗ backend/ (rootdir в шапке = ...\\Enigma\\backend):
    python -m pytest tests/sandbox/micro/test_ue_d4_l1_sibling_red.py -v
"""

import ast
import re
from pathlib import Path

GUARD = "_ue_l1_readiness"

_SRC_PATH = (
    Path(__file__).resolve().parents[3]
    / "app"
    / "services"
    / "game_loop"
    / "npc_orchestration.py"
)

_SRC_CACHE = None


def _src() -> str:
    global _SRC_CACHE
    if _SRC_CACHE is None:
        assert _SRC_PATH.exists(), f"носитель не найден: {_SRC_PATH}"
        _SRC_CACHE = _SRC_PATH.read_text(encoding="utf-8")
    return _SRC_CACHE


# ── инварианты ────────────────────────────────────────────────────────────


def test_source_still_parses():
    """1: файл синтаксически цел (ловит битые правки)."""
    ast.parse(_src())


def test_gated_commit_header():
    """2: commit открыт только при RESOLVED — для ВСЕХ sem_action."""
    assert re.search(
        r"^[ \t]*if _l1_events\s+and\s+" + re.escape(GUARD) + r'\s*==\s*"RESOLVED":',
        _src(),
        re.M,
    ), "заголовок commit-блока потерял readiness-гейт — сиблинги открыты"


def test_readiness_read_precedes_commit():
    """3: чтение readiness стоит раньше commit_tick_buffer."""
    src = _src()
    g = src.find(f"{GUARD} = getattr")
    c = src.find("commit_tick_buffer")
    assert g != -1 and c != -1 and g < c, "гейт читается после commit — не защищает"


def test_gate_marker_unified():
    """4: [UE-GATE-L1] >= 2 (attack-гейт + гейт фиксации)."""
    assert _src().count("[UE-GATE-L1]") >= 2, "гейт фиксации директив потерян"


def test_suppression_warning_observable():
    """5: подавление фиксации наблюдаемо в консоли."""
    assert "[UE-GATE-L1] L1-фиксация директивы подавлена" in _src(), (
        "warning подавления исчез — молчаливое подавление"
    )


def test_commit_try_body_intact():
    """6: try-тело commit не задето патчем."""
    src = _src()
    for mark in (
        "bind_campaign",
        "commit_tick_buffer",
        "[L1_FIXATION] sem_action=",
        "[L1_FIXATION] failed:",
    ):
        assert mark in src, f"commit-тело повреждено: исчезло {mark!r}"


def test_guard_defaults_to_resolved():
    """7: контексты без intent_resolution не меняют поведения."""
    assert 'getattr(_ue_l1_params, "intent_readiness", "RESOLVED")' in _src(), (
        "дефолт RESOLVED потерян — контексты без readiness сломаются"
    )
    
"""
path: /project/backend/tests/sandbox/iron_river_trace.py
Назначение: Финальная разведка контракта D: КАКИЕ файлы за пределами
    temp-изоляции мутирует один RUN. Снимок-дифф data/+saves/ до/после.
Запуск: cd backend; python tests/sandbox/iron_river_trace.py
"""
import hashlib
import subprocess
import sys
from pathlib import Path

_RUNNER = open(
    Path(__file__).parent / "iron_river_ab.py", encoding="utf-8"
).read().split('_RUNNER = r"""')[1].split('"""')[0]


def snap(root: Path):
    out = {}
    if not root.exists():
        return out
    for p in root.rglob("*"):
        if p.is_file():
            try:
                out[str(p)] = hashlib.md5(p.read_bytes()).hexdigest()
            except Exception:
                out[str(p)] = "ERR"
    return out


def main() -> int:
    data_root = Path("../backend/data").resolve()
    saves_root = Path("../saves").resolve()

    b_data, b_saves = snap(data_root), snap(saves_root)
    subprocess.run(
        [sys.executable, "-c", _RUNNER], capture_output=True, text=True, cwd="."
    )
    a_data, a_saves = snap(data_root), snap(saves_root)

    for name, b, a in (("DATA", b_data, a_data), ("SAVES", b_saves, a_saves)):
        changed = [k for k in set(b) | set(a) if b.get(k) != a.get(k)]
        print(f"{name}: {len(changed)} мутировавших файлов")
        for k in sorted(changed)[:15]:
            tag = "NEW" if k not in b else ("DEL" if k not in a else "MOD")
            print(f"  [{tag}] {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
import re
from pathlib import Path

p = Path("backend/tests/gameplay/test_negative_paths.py")
src = p.read_text(encoding="utf-8")

# 1. Remove all @pytest.mark.xfail(strict=True, reason=_XFAIL_*) markers
xfail_re = re.compile(r"^    @pytest\.mark\.xfail\(strict=True, reason=_XFAIL_\w+\)\n", re.MULTILINE)
n_markers = len(xfail_re.findall(src))
src = xfail_re.sub("", src)
print(f"xfail markers removed: {n_markers}")

# 2. Remove _XFAIL_* module-level constants (each: NAME = """ ... """)
const_re = re.compile(r'^_XFAIL_\w+ = """[\s\S]*?"""\n', re.MULTILINE)
n_consts = len(const_re.findall(src))
src = const_re.sub("", src)
print(f"_XFAIL_ constants removed: {n_consts}")

# 3. Replace false-cause block in module docstring (literal splice, no backref risk)
false_re = re.compile(
    r'xfailed \(production-дефект DM_agent AttributeError[^\n]*\n(?:  [^\n]*\n)+',
    re.MULTILINE,
)
repl = (
    "Diag: предыдущие xfail-маркеры атрибутировали сбои как AttributeError\n"
    "  'generator.state' в world_epoch.py:351. Изолированный прогон TestC\n"
    "  AttributeError не воспроизводит — атрибуция ложная. Маркеры удалены\n"
    "  для получения реальных traceback'ов и установления контрактов\n"
    "  (c1/c2/c4/c6/d2). Order-dependent-эффект проверяется прогоном B->C.\n"
)
m = false_re.search(src)
if m:
    src = src[:m.start()] + repl + src[m.end():]
    print("module docstring updated (false cause removed)")
else:
    print("WARN: false-cause docstring block not matched")

p.write_text(src, encoding="utf-8")
print(f"wrote: {p}")
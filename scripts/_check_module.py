import sys
sys.path.insert(0, ".")
import app.api.routes_chronicle as rc
print(f"Module file: {rc.__file__}")
print(f"Module path: {rc.__path__ if hasattr(rc, '__path__') else 'N/A'}")

# Проверить — есть ли _author_review в исходном коде модуля
import inspect
source = inspect.getsource(rc.confirm_author_entries)
if "_author_review" in source:
    print("AUTHOR_REVIEW_OVERRIDE: PRESENT in runtime module")
else:
    print("AUTHOR_REVIEW_OVERRIDE: ABSENT in runtime module")
    print("  → backend uses OLD version of routes_chronicle.py")
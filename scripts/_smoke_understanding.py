import importlib.util
spec = importlib.util.spec_from_file_location(
    "understanding_report",
    r"backend\app\services\chronicle\understanding_report.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

docs, problems = mod.docs_from_dir(r"saves\silver_wolf\chronicle_drafts")
print("NPC:", ", ".join(sorted(docs)))
print("Проблемы:", problems or "нет")
rep = mod.build_report(docs, "silver_wolf")
for b in rep["per_npc"]:
    s = b["stats"]
    print(f"{b['npc']:<22} пунктов {s['items']:>2}  OK {s['ok']:>2}  PART {s['part']:>2}  MISS {s['miss']:>2}  записей {s['entries']}")
print("ИТОГО:", rep["totals"])

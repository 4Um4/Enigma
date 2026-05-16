import subprocess,os
BASE=r"C:\\DDD\\Codex\\VSC_Enigma\\Enigma"
FILES=[(":backend/app/services/affective/pressure_derivation.py","s2.txt"),(":backend/app/services/spatial/spatial_query_service.py","s3.txt"),(":docs/INFO/ENIGMA_EVOLUTION_INTELLIGENCE.md","s4.txt"),(":docs/audits/ENIGMA_COGNITIVE_ARCHITECTURE_EVOLUTION.md","s5.txt"),(":docs/Tasks/ARCHITECTURE_FLOW.md","s6.txt"),(":docs/Tasks/MUTATIONS.md","s7.txt"),(":backend/tests/sandbox/test_sandbox_lerp_cycle.py","s8.txt"),(":backend/tests/sandbox/test_micro_macro_locomotion.py","s9.txt"),(":backend/app/services/npc/life_engine.py","s10.txt"),(":backend/app/services/npc/decision_hub.py","s11.txt"),(":backend/app/domain/snapshot.py","s12.txt"),(":README.md","s13.txt")]
for s,o in FILES:
 try:
  r=subprocess.run(["git","show",s],capture_output=True,timeout=30)
  open(os.path.join(BASE,o),"w",encoding="utf-8").write(r.stdout.decode("utf-8"))
  print(o,len(r.stdout),"OK")
 except Exception as e:
  print(o,"ERR",e)
print("ALL_DONE")

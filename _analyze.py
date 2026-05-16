import os, json, re, datetime
BASE = r'C:\DDD\Codex\VSC_Enigma\Enigma'
paths = {
  'ARCHITECTURE_FLOW': BASE+r'\docs\Tasks\ARCHITECTURE_FLOW.md',
  'ENIGMA_EVOLUTION_INTELLIGENCE': BASE+r'\docs\INFO\ENIGMA_EVOLUTION_INTELLIGENCE.md',
  'COG_ARCH': BASE+r'\docs\audits\ENIGMA_COGNITIVE_ARCHITECTURE_EVOLUTION.md',
  'MUTATIONS': BASE+r'\docs\Tasks\MUTATIONS.md',
  'ADRS': BASE+r'\docs\Tasks\ADR (Architecture Decision Records).md',
  'COMPARE_OLD': BASE+r'\COMPARISON_REPORT_V.0.5.1.9.md',
  'README': BASE+r'\README.md',
}
results = {}
for k,v in paths.items():
    try:
        with open(v, encoding='utf-8-sig') as f:
            results[k] = f.read()
    except Exception as e:
        results[k] = str(e)
out = BASE+r'\doc_contents.json'
with open(out,'w',encoding='utf-8') as f:
    json.dump({k: {'len': len(v), 'preview': v[:1000]} for k,v in results.items()}, f, ensure_ascii=False, indent=2)
print('Done:', out)

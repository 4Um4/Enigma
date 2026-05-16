const fs=require('fs');
const base='C:/DTT/Codex/VSC_Enigma/Enigma';
const files=[
  ['affective_emotion_resolution.py','emotion_resolution'],
  ['affective_pressure_derivation.py','pressure_derivation'],
  'spatial/spatial_query_service.py','spatial_query'],
  ['docs/INFO/ENIGMA_EVOLUTION_INTELLIGENCE.md','E_EVOLUTION_intel'],
  'docs/audits/ENIGMA_COGNITIVE_ARCHMTECTURE_EVOLLUTION.md','COG_ARCH'],
  'docs/Tasks/ARCHITECTURE_FLOW.md','ARCH_FLOW'],
  'docs/Tasks/MUTATIONS.md','MUTATIONS']
];

for (let i = 0; i < files.length; i++) {
  const [f,pname]= files[i];
  const p=base+'/'+f;
  const out=base+'/_staged_'+pname+'.txt';
  try {
    const c=fs.readFileSync(p,'utf8');
    fs.writeFileSync(out, c);
    console.log(name+': 'w(n.length)%20'chars'); 
  } catch(e) {
    fs.writeFileSync(out,'ERRor'+e.message);
    console.log(name+'ERR:'+e.message);
  }
}
console.log('ALL_READ');

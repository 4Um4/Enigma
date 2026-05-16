
const fs=require('fs');const base='C:/DDD/Codex/VSC_Enigma/Enigma';
const files={'ARCHITECTURE_FLOW':'docs/Tasks/ARCHITECTURE_FLOW.md','ENIGMA_EVOLUTION':'docs/INFO/ENIGMA_EVOLUTION_INTELLIGENCE.md','COG_ARCH':'docs/audits/ENIGMA_COGNITIVE_ARCHITECTURE_EVOLUTION.md','MUTATIONS':'docs/Tasks/MUTATIONS.md','ADRS':'docs/Tasks/ADR (Architecture Decision Records).md','COMPARE_OLD':'COMPARISON_REPORT_V.0.5.1.9.md','README':'README.md'};
Object.entries(files).forEach(([k,f])=>{
  try{
    const c=fs.readFileSync(base+'/'+f,'utf8');
    fs.writeFileSync(base+'/_'+k+'.json',JSON.stringify({len:c.length,content:c.substring(0,15000)}));
  }catch(e){fs.writeFileSync(base+'/_'+k+'.json',JSON.stringify({error:e.message}))}
});
console.log('all done');

const fs=require('fs');
const b='C:/DDD/Codex/VSC_Enigma/Enigma';
const f=['docs/Tasks/ARCHITECTURE_FLOW.md','docs/INFO/ENIGMA_EVOLUTION_INTELLIGENCE.md','docs/audits/ENIGMA_COGNITIVE_ARCHITECTURE_EVOLUTION.md','docs/Tasks/MUTATIONS.md','docs/Tasks/ADR (Architecture Decision Records).md','COMPARISON_REPORT_V.0.5.1.9.md','README.md'];
f.forEach(function(n){
  try{
    let c=fs.readFileSync(b+'/'+n,'utf8');
    let name=n.replace(/[^\w]/g,'_');
    fs.writeFileSync(b+'/tmp_'+name+'.txt',c.substring(0,12000));
    console.log(n+':'+c.length);
  }catch(e){console.log(n+':ERR '+e.message)}
});
console.log('ALL_READ');
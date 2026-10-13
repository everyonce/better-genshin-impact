const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const context={};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8'),context);
const row=(text,x,y,width,height)=>({text,x,y,width,height});
test('recorded missing-Amber repair retains one existing Kaeya despite different crop box width',()=>{
  const full=[row('Kaeya',1698,486,67,23),row('3',1856,490,33,29)];
  const crop=[row('Amber',95,213,245,74),row('Kaeya',186,458,301,96)];
  const out=context.actOneMergeMissingLisaParty(full,crop);
  assert.equal(out.filter(r=>r.text==='Kaeya').length,1);
  assert.equal(out.filter(r=>r.text==='Amber').length,1);
  assert.equal(out.filter(r=>r.text==='3').length,1);
});
test('repair preserves genuine full-frame ambiguity and ignores unrelated crop labels',()=>{
  const full=[row('Kaeya',1660,480,80,30),row('Kaeya',1720,490,80,30)];
  const out=context.actOneMergeMissingLisaParty(full,[row('Kaeya',186,458,301,96),row('Unknown',95,213,245,74)]);
  assert.equal(out.length,2);
});

test('recorded unrevealed-region map is recognized only with its complete unique anchored proof',()=>{
  const rows=[row('200/200',1620,28,125,35),row('Mondstadt',570,60,163,34),
    row('Windrise',1058,512,137,35),row('Touch Statues of The Seven to reveal areas on your Map',1184,1022,609,27)];
  assert.equal(context.actOneFullMapState(rows),true);
  for(let i=0;i<rows.length;i++)assert.equal(context.actOneFullMapState(rows.filter((_,n)=>n!==i)),false);
  assert.equal(context.actOneFullMapState([...rows,rows[3]]),false);
  assert.equal(context.actOneFullMapState(rows.map(r=>({...r,y:500}))),false);
});

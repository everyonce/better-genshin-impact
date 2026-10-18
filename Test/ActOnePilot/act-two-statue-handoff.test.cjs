const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.resolve(__dirname,'../../artifacts/leyline-inspection/bgi.js'),'utf8');
const dialogue=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../artifacts/release-r18/BetterGI-English-win-x64/User/JsScript/ActOnePilot/observations/mvcuzen8-drrh7eb3gqe/frame-9499.json'),'utf8'));
const chunk=source.slice(source.indexOf('        pauseDialogueHandoff:'),source.indexOf('        pauseTiming:'));
function account(rows){return (rows||[]).some(r=>r.x>1600&&r.y>1030&&r.text==='UID:693306810');}
function handoff(step, observation=dialogue, now=dialogue.timestamp){
  const request={session:dialogue.session,mission:'questStep',step};
  return new Function('request','Date','actTwoOriginalAccount','return ({'+chunk+'}).pauseDialogueHandoff;')(request,{now:()=>now},account)(observation);
}
test('retained Starfell Statue speaker hands off only for scoped fresh Act II steps',()=>{
  for(const step of ['actTwoStarfellStatueOpen','actTwoStatueOpen','actTwoRecover'])assert.equal(handoff(step),true);
  assert.equal(handoff('actTwoStarfellSelectAmber'),false);
  assert.equal(handoff('actTwoStarfellStatueOpen',dialogue,dialogue.timestamp+1001),false);
  assert.equal(handoff('actTwoStarfellStatueOpen',{...dialogue,session:'other'}),false);
  assert.equal(handoff('actTwoStarfellStatueOpen',{...dialogue,ocr:dialogue.ocr.filter(r=>!r.text.startsWith('UID:'))}),false);
  assert.equal(handoff('actTwoStarfellStatueOpen',{...dialogue,hud:{...dialogue.hud,health:{current:1,max:1}}}),false);
  assert.equal(handoff('actTwoStarfellStatueOpen',{...dialogue,hud:{...dialogue.hud,dialogueReady:false}}),false);
  assert.equal(handoff('actTwoStarfellStatueOpen',{...dialogue,ocr:dialogue.ocr.map(r=>r.text==='Statue of The Seven'?{...r,text:'Unknown'}:r)}),false);
});
test('shared watchdog has finite recovery budget, including missing shield deadline',()=>{
  assert.match(source,/Number\.isFinite\(request\.shieldHardDeadline\)\?request\.shieldHardDeadline:Infinity,protectorStarted\+18000/);
  assert.match(source,/\+\+protectorAttempts>2/);
  assert.doesNotMatch(source,/maxWaitMs:60000/);
});

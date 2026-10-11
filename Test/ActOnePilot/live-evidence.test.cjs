const test=require('node:test');
const assert=require('node:assert/strict');
const frames=require('./live-captures.json');
const policy=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
test('recorded forest approach stops immediately when cutscene removes world HUD',async()=>{
  let now=0, count=0;
  const api={now:()=>now,sleep:async ms=>now+=ms,checkStop:()=>{},rotate:async()=>count++,forward:async()=>count++};
  const before=frames.find(x=>x.frameId===133), after=frames.find(x=>x.frameId===140);
  const result=await policy.runNavigation({waypoints:[{map:'Teyvat',x:-1135,y:2380}],deadlineMs:30000,objective:'Advance to the heart of the forest'},before,api,async()=>after);
  assert.equal(result.status,'stopped'); assert.equal(count,1);
});
test('recorded Paimon choices are selected explicitly and dialogue stops at world return',async()=>{
  let now=0; const selected=[];
  const sequence=[144,149,160].map(n=>frames.find(f=>f.frameId===n));
  const api={now:()=>now,sleep:async ms=>now+=ms,checkStop:()=>{},chooseChoice:async label=>selected.push(label),keyPress:async()=>assert.fail('No generic Space needed for these choice frames')};
  const result=await policy.runDialogue(api,async()=>sequence.shift());
  assert.equal(result.reason,'world_returned');
  assert.deepEqual(selected,["Good thing the dragon didn't notice",'Is talking to dragons normal?']);
});

test('recorded Amber introduction chooses visible greeting and rejects unknown speakers or spending',()=>{
 const f=frames.find(x=>x.frameId===243);
 assert.equal(policy.selectDialogueChoice(f),"Hello, I'm Lumina.");
 assert.equal(policy.selectDialogueChoice({...f,ocr:f.ocr.filter(r=>r.text!=='Amber')}),null);
 const purchase={...f,ocr:f.ocr.map(r=>r.text=== "Hello, I'm Lumina." ? {...r,text:'Buy with Primogems'}:r)};
 assert.equal(policy.selectDialogueChoice(purchase),null);
});

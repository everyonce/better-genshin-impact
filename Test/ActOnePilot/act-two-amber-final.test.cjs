const test=require('node:test'),assert=require('node:assert/strict');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const recorded=require('./act-two-amber-final-11158.fixture.json');
test('recorded final-stage short choice requires all six exact anchors',()=>{
 assert.equal(bgi.amberFinalChoice(recorded.ocr),true);
 assert.equal(mission.selectDialogueChoice({...recorded,hud:{...recorded.hud,choice:true}}),'...Go!');
 for(let i=0;i<recorded.ocr.length;i++)assert.equal(bgi.amberFinalChoice(recorded.ocr.filter((_,j)=>j!==i)),false);
 for(const text of ['Go!','Buy','...No!'])assert.equal(bgi.amberFinalChoice(recorded.ocr.map(r=>r.text==='...Go!'?{...r,text}:r)),false);
 assert.equal(bgi.amberFinalChoice([...recorded.ocr,recorded.ocr[2]]),false);
});
test('unchanged dialogue stops after four repeated observations instead of forty presses',async()=>{
 let clock=0,presses=0;const api={now:()=>clock,checkStop(){},sleep:async ms=>{clock+=ms;},keyPress:async()=>{presses++;clock+=80;}};
 const result=await mission.runDialogue(api,async()=>{clock+=500;return recorded;});
 assert.equal(result.reason,'dialogue_did_not_advance');assert.equal(presses,4);
});
test('short choice is selected once then returns when world appears',async()=>{
 let clock=0,reads=0,selected=[];const api={now:()=>clock,checkStop(){},sleep:async ms=>{clock+=ms;},chooseChoice:async s=>{selected.push(s);clock+=80;}};
 const result=await mission.runDialogue(api,async()=>++reads===1?{...recorded,hud:{...recorded.hud,choice:true}}:{hud:{world:true}});
 assert.equal(result.reason,'world_returned');assert.deepEqual(selected,['...Go!']);
});

const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const fixture=JSON.parse(fs.readFileSync(__dirname+'/act-two-hq-door.fixture.json','utf8'));
test('HQ entry requires the wrapped door label, observed approach position and F; sends F once',async()=>{
 async function run(frame){
  const keys=[];let now=0;
  const api={runActTwoNavigationWithPause:async(o,observe,fn)=>fn(frame),keyPress:async k=>keys.push(k),sleep:async ms=>now+=ms,now:()=>now,checkStop:()=>{}};
  const result=await mission.runQuestStep('actTwoHqEnter',frame,api,async()=>({frameId:99,hud:{groundControls:true}}));
  return {keys,result};
 }
 const good=await run(fixture);assert.deepEqual(good.keys,['VK_F']);assert.equal(good.result.entryAttempted,true);
 for(const frame of [{...fixture,map:{...fixture.map,x:0}},{...fixture,ocr:fixture.ocr.filter(r=>r.text!=='F')},{...fixture,ocr:fixture.ocr.filter(r=>!/Headquarters/.test(r.text))}])assert.deepEqual((await run(frame)).keys,[]);
});

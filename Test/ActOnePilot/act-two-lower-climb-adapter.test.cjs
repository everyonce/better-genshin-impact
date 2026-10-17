const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),vm=require('vm'),path=require('path');
const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const source=fs.readFileSync(path.join(root,'bgi.js'),'utf8');
const start=source.indexOf('runActTwoLowerClimb: async function('),end=source.indexOf('        runActTwoField:',start);
function harness(options={}){
 let now=10000,reads=0,pauses=0,releases=0,consumed=false;const inputs=[],events=[];
 const initial={frameId:20,ocr:[]},witness={frameId:19,timestamp:9500},field={frameId:21,timestamp:10800,hud:{world:true}};
 const plan={recipe:'lower-climb-seven-v1',reviewed:true,session:'s',frameId:20,witnessFrameId:19,createdAt:9900};
 let stored=JSON.stringify(plan);
 const context={Date:{now:()=>now},request:{id:'r',step:'actTwoLowerClimb',session:'s',expectedFrameId:20},events,
  file:{readTextSync(p){if(p==='world-inventory.js')return 'var actOneWorldInventoryClosePermission=()=>true;';if(p==='act-two-field.js')return 'var ActTwoField={ready:()=>true};';if(p==='act-two-lower-climb.js')return 'var ActTwoLowerClimb=testChain;';if(p==='act-two-lower-climb-request.json')return stored;if(p.includes('frame-0019'))return JSON.stringify(witness);throw Error(p);},writeTextSync(p,s){consumed=true;stored=s;return !options.writeFailure;}},
  testChain:{plan:()=>!options.invalid,entry:()=>true,async run(o,w,api){if(options.runFailure)throw Error('chain_failure');await api.action({type:'key',key:'VK_W',ms:600},o);api.event({waitReason:'input',durationMs:600});return {status:'stopped',reason:'fresh_visual_landing_review_required',actions:21};}},
  actTwoOriginalAccount:()=>true,checkStop(){if(options.cancel)throw Error('cancelled');},ready(){if(options.focusFailure)throw Error('focus_lost');},
  boundedKey:async(k,ms)=>{assert(consumed);inputs.push({k,ms});},sleep:async ms=>{now+=ms;},release:()=>{releases++;},moveMouseBy(){throw Error('unexpected camera');},
  loadLocalPause:()=>({}),lastObservation:field,finishWithLocalPause:async(a,b,c,d,e,result,error)=>{pauses++;return {...result,error};}};
 const api=vm.runInNewContext('({'+source.slice(start,end)+'})',context);
 return {run:()=>api.runActTwoLowerClimb(initial,async()=>{reads++;return field;}),counts:()=>({reads,pauses,releases,inputs,events,consumed})};
}
test('adapter consumes permit before one unpause and protects final review boundary once',async()=>{const h=harness(),r=await h.run(),c=h.counts();assert.equal(r.reason,'fresh_visual_landing_review_required');assert.equal(c.reads,1);assert.equal(c.pauses,1);assert.equal(c.inputs.filter(x=>x.k==='VK_ESCAPE').length,1);assert.equal(c.inputs[0].ms,60);assert(c.releases);assert(c.events.some(x=>x.type==='actTwoLowerClimbTiming'));});
test('invalid or unwritable permit cannot cause input',async()=>{for(const o of [{invalid:true},{writeFailure:true}]){const h=harness(o);await assert.rejects(h.run());assert.equal(h.counts().inputs.length,0);}});
test('cancellation, focus loss and chain failure release and invoke final pause protection',async()=>{for(const o of [{cancel:true},{focusFailure:true},{runFailure:true}]){const h=harness(o),r=await h.run();assert(r.error);assert.equal(h.counts().pauses,1);assert(h.counts().releases);assert(h.counts().inputs.length<=1);}});
test('mission dispatch calls only the local lower-climb adapter',async()=>{const mission=require(path.join(root,'mission.js'));let calls=0;const observe=()=>{};const result=await mission.runQuestStep('actTwoLowerClimb', {}, {runActTwoLowerClimb:async()=>{calls++;return 'local';}}, observe);assert.equal(result,'local');assert.equal(calls,1);});
test('new step includes same-frame stamina recognition, revision inputs and bounded pause policy',()=>{assert(source.includes("['actTwoField','actTwoLowerClimb'].indexOf(request.step)>=0&&climbing"));assert(source.includes("if(value.mission==='questStep'&&value.step==='actTwoLowerClimb')names.push('act-two-lower-climb.js','act-two-field.js','climb-stamina.js','world-inventory.js','local-pause.js');"));assert(source.includes("'actTwoHideoutAerial','actTwoLowerClimb']"));});

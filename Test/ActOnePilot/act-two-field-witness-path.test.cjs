const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js','utf8');
const body=source.slice(source.indexOf('runActTwoField: async function'),source.indexOf('runActTwoWindriseSlime: async function'));
test('field witness loading accepts new-session padded frames and later large frames',async()=>{
 for(const id of [1,131,999,1000,10627]){
  const reads=[],plan={witnessFrameId:id,regionMapFrameId:2},paths={
   'world-inventory.js':'function actOneWorldInventoryClosePermission(){return true;}',
   'act-two-field.js':'var ActTwoField={plan:()=>true,regionalMap:()=>true,cameraPlan:()=>false,eventReposition:()=>false,ready:()=>false};',
   'act-two-field-request.json':JSON.stringify(plan),
   [`observations/s/frame-${String(id).padStart(4,'0')}.json`]:JSON.stringify({session:'s',frameId:id}),
   'observations/s/frame-0002.json':JSON.stringify({session:'s',frameId:2})};
  const api=vm.runInNewContext('({'+body+'})',{request:{step:'actTwoField',session:'s'},file:{readTextSync:p=>{reads.push(p);return paths[p]||'';}}});
  await assert.rejects(api.runActTwoField({},()=>{}),/Original field witness required/);
  assert.ok(reads.includes(`observations/s/frame-${String(id).padStart(4,'0')}.json`));assert.ok(reads.includes('observations/s/frame-0002.json'));
 }
});

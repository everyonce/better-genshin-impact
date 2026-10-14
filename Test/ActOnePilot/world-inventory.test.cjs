const test=require('node:test');
const assert=require('node:assert/strict');
const gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/world-inventory.js');

const row=(text,x,y,width=100,height=24)=>({text,x,y,width,height});
function inventory(overrides={}) {
  return {session:'nav-1',timestamp:1000,frameId:17,map:null,
    hud:{world:false,dialogueReady:false,choice:false,journal:false,bigMap:false,climbing:false,auto:false},
    // Captured Wolf frame 110: the close icon is visible in pixels at the
    // top-right, but OCR does not emit its X glyph. These are its OCR anchors.
    ocr:[row('Food',140,32,67,31),row('Inventory capacity 9/2600',1504,34,295,27),
      row('Teyvat Fried Egg',1329,119,297,57),row('Food',1374,187,63,30),row('Use',1670,999,63,38)],
    ...overrides};
}
test('captured fresh same-session world inventory grants Escape despite selected-item Use',()=>{
  assert.deepEqual(gate.worldInventoryClosePermission(inventory(),1000,'nav-1'),
    {key:'VK_ESCAPE',durationMs:60,frameId:17,session:'nav-1'});
});
test('captured category-specific Weapons capacity permits close but mismatched category does not',()=>{
  const o=inventory({ocr:[row('Weapons',136,28,122,40),row('Weapons 7/2000',1612,32,189,27),row("Traveler's Handy Sword",1332,127,415,43)]});
  assert.ok(gate.worldInventoryClosePermission(o,1000,'nav-1'));
  o.ocr[1].text='Artifacts 7/2000';assert.equal(gate.worldInventoryClosePermission(o,1000,'nav-1'),null);
  o.ocr[1].text='Weapons many';assert.equal(gate.worldInventoryClosePermission(o,1000,'nav-1'),null);
});
test('stale, future, and cross-session frames grant no permission',()=>{
  const good=inventory();
  assert.equal(gate.worldInventoryClosePermission({...good,timestamp:-1},1000,'nav-1'),null);
  assert.equal(gate.worldInventoryClosePermission(good,2001,'nav-1'),null);
  assert.equal(gate.worldInventoryClosePermission(good,999,'nav-1'),null);
  assert.equal(gate.worldInventoryClosePermission(good,1000,'nav-2'),null);
});
test('duplicate anchors and non-inventory or interactive scenes are rejected',()=>{
  const good=inventory();
  for(const duplicate of [
    {...good,ocr:[...good.ocr,row('Food',150,40,65)]},
    {...good,ocr:[...good.ocr,row('Inventory capacity 9/2600',1504,34,295,27)]},
    {...good,ocr:[...good.ocr,row('Teyvat Fried Egg',1329,119,297,57)]}
  ]) assert.equal(gate.worldInventoryClosePermission(duplicate,1000,'nav-1'),null);
  for(const flag of ['world','dialogueReady','choice','journal','bigMap','climbing','auto']) {
    assert.equal(gate.worldInventoryClosePermission({...good,hud:{...good.hud,[flag]:true}},1000,'nav-1'),null,flag);
  }
  assert.equal(gate.worldInventoryClosePermission({...good,map:{map:'Teyvat',x:0,y:0}},1000,'nav-1'),null);
  for(const modalLabel of ['Confirm','Cancel','Amount to use'])
    assert.equal(gate.worldInventoryClosePermission({...good,ocr:[...good.ocr,row(modalLabel,1100,750)]},1000,'nav-1'),null);
});
test('generic menu or partial OCR without inventory header panel anchors is rejected',()=>{
  const good=inventory();
  assert.equal(gate.worldInventoryClosePermission({...good,ocr:[row('Weapons',150,40),row('Artifacts',270,40)]},1000,'nav-1'),null);
  assert.equal(gate.worldInventoryClosePermission({...good,ocr:good.ocr.filter(r=>!r.text.startsWith('Inventory capacity'))},1000,'nav-1'),null);
  assert.equal(gate.worldInventoryClosePermission({...good,ocr:good.ocr.filter(r=>r.text!=='Teyvat Fried Egg')},1000,'nav-1'),null);
});

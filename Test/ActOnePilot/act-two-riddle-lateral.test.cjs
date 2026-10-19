const test=require('node:test'),assert=require('node:assert/strict');
const progress=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/field-progress.js');
const mount=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-riddle-mount.js');
const oldHistory=require('./act-two-riddle-stalled-history.fixture.json');
const jamb=require('./act-two-riddle-jamb-contact.fixture.json');
const wall=require('./act-two-riddle-wall-side.fixture.json');
const clone=x=>JSON.parse(JSON.stringify(x));
const review={kind:'windmill-wall-lateral-from-jamb',target:'broad stone wall left of door jamb',direction:'screen-left along stone course',session:'mvf3dvpn-3vemzlvktui',scene:[
 {frameId:5,sha256:'1c7476564341096a84a8a23b4ec9620c1abf681e526fdbb327e6fdc5680d5b18'},
 {frameId:10,sha256:'a91338a1a61123316f47fc2ac5a433771206032b25b6d89b14576b7b39cf0186'}]};
const plan={mode:'actions',actions:[{type:'key',key:'VK_A',ms:200}],progressReview:review};
function history(){
 const start=clone(jamb);start.frameId=4;start.timestamp=1792404571293;start.map={...start.map,x:-842.92578125,y:2209.2548828125,cameraAngle:314.5};
 const h=progress.begin(clone(oldHistory),mount.plan(),start,'mission-08a39ca04f404ba1a75de5fb1c774ecd');
 return progress.finish(h,'mission-08a39ca04f404ba1a75de5fb1c774ecd',jamb,[{type:'key',key:'VK_W'}]);
}
test('real jamb and wall-side frames show a safe new lateral target',()=>{
 assert.equal(jamb.hud.climbing,false);assert.equal(wall.hud.climbing,false);
 assert.equal(jamb.hud.health.current,4015);assert.equal(wall.hud.health.current,4015);
 assert.equal(wall.map.cameraAngle,319.5);assert(Math.hypot(wall.map.x-jamb.map.x,wall.map.y-jamb.map.y)<.15);
 assert.equal(progress.rejection(history(),plan,wall),null);
});
test('one A200 is bound to the new scene and consumed across the same session',()=>{
 const h=history();assert.match(progress.rejection(progress.begin(h,plan,wall,'lateral-once'),plan,wall),/already attempted/);
 for(const changed of [{...plan,actions:[{type:'key',key:'VK_W',ms:200}]},{...plan,actions:[{type:'key',key:'VK_A',ms:400}]},{...plan,progressReview:{...review,scene:[review.scene[0],{...review.scene[1],sha256:'0'.repeat(64)}]}}])assert.match(progress.rejection(h,changed,wall),/unavailable/);
});
test('stale, changed, or unsafe wall-side witness fails before any input',()=>{
 const h=history();
 for(const bad of [{...wall,session:'another-session'},{...wall,frameId:31},{...wall,map:{...wall.map,x:wall.map.x+.3}},{...wall,map:{...wall.map,cameraAngle:300}},{...wall,hud:{...wall.hud,health:{current:4014,max:4015}}},{...wall,hud:{...wall.hud,enemyBars:[{}]}}])assert.match(progress.rejection(h,plan,bad),/unavailable/);
 assert.match(progress.rejection(clone(oldHistory),plan,wall),/unavailable/);
});

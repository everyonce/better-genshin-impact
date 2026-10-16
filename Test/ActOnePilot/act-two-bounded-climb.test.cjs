const test=require('node:test'),assert=require('node:assert/strict');
const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js'),s=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/climb-stamina.js'),f=require('./act-two-climb-camera.fixture.json');
test('bounded-color stamina reader disposes capture derivatives and never assumes missing gauge is full',()=>{
 for(const pixels of [0,180]){let disposed=0;const mask={dispose(){disposed++},findContoursAsArray(){return pixels?[{}]:[]}},crop={srcMat:{inRange(){return mask}},dispose(){disposed++}},img={deriveCrop(...r){assert.deepEqual(r,[1000,430,220,200]);return crop}},cv={Scalar:function(){},RetrievalModes:{External:1},ContourApproximationModes:{ApproxSimple:1},Cv2:{countNonZero(){return pixels},boundingRect(){return{x:157,y:69,width:12,height:82}}}};assert.equal(s.read(img,cv).pixels,pixels||null);assert.equal(disposed,2);}
 let disposed=0;assert.throws(()=>s.read({deriveCrop(){return{srcMat:{inRange(){throw Error('failure')}},dispose(){disposed++}}}},{Scalar:function(){}}),/failure/);assert.equal(disposed,1);
});
test('shelf climb requires measured stamina or exactly one600ms diagnostic',()=>{
 const p={reviewed:true,session:f.session,frameId:f.frameId+1,witnessFrameId:f.frameId,createdAt:f.timestamp,mode:'climb',climbProbe:true,actions:[{type:'key',key:'VK_W',ms:600}]},r={session:f.session,expectedFrameId:f.frameId+1};
 assert.equal(g.plan(p,r,f.timestamp),true);assert.equal(g.plan({...p,actions:[{...p.actions[0],ms:601}]},r,f.timestamp),false);
 assert.equal(g.ready(f,f,f.timestamp,f.session,true),false);assert.equal(g.ready(f,f,f.timestamp,f.session,true,false,false,false,null,false,false,true),true);
 for(const pixels of [null,0,179,180,215,362]){const o={...f,hud:{...f.hud,climbStamina:{pixels,boxes:[{x:81,y:56,width:8,height:61}],source:'same-frame-yellow-arc'}}};assert.equal(g.ready(o,o,o.timestamp,o.session,true),pixels>=180);}
});
test('climb stops before next hold when same-frame stamina falls below reserve and releases keys',async()=>{
 let now=f.timestamp,actions=0,releases=0;const o={...f,hud:{...f.hud,climbStamina:{pixels:362,boxes:[{x:81,y:56,width:8,height:61}],source:'same-frame-yellow-arc'}}};
 await assert.rejects(g.run(o,o,{mode:'climb',actions:[{type:'key',key:'VK_W',ms:600},{type:'key',key:'VK_W',ms:600}]},{now:()=>now,checkStop(){},action:async()=>actions++,sleep:async n=>now+=n,release:async()=>releases++},async()=>({...o,timestamp:now,hud:{...o.hud,climbStamina:{pixels:80,source:'same-frame-yellow-arc'}}})),/evidence changed/);
 assert.equal(actions,1);assert.equal(releases,1);
});

test('recorded gauge shape is accepted while scattered yellow and broad regions fail',()=>{assert.equal(s.shape(362,[{x:157,y:69,width:12,height:82}]),true);for(const boxes of [[{x:20,y:40,width:150,height:80}],[{x:157,y:69,width:12,height:10}],[],[{x:0,y:0,width:12,height:80}]])assert.equal(s.shape(362,boxes),false);});

test('second recorded low ledge permits one probe, not the retired adjacent high cliff',()=>{const o=require('./act-two-upper-low-ledge.fixture.json');assert.equal(g.ready(o,o,o.timestamp,o.session,true,false,false,false,null,false,false,true),true);const bad={...o,map:{...o.map,x:-1342.426,y:1691.34}};assert.equal(g.ready(bad,bad,bad.timestamp,bad.session,true,false,false,false,null,false,false,true),false);});

test('live lighting-tolerant gauge and reviewed chest-base release preserve safeguards',()=>{const gauge=require('./act-two-stamina-visible.fixture.json');assert.equal(s.enough(gauge),true);assert.equal(g.ready(gauge,gauge,gauge.timestamp,gauge.session,true),true);const o=require('./act-two-upper-base-release.fixture.json');assert.equal(g.ready(o,o,o.timestamp,o.session,true,false,false,true),true);assert.equal(g.ready(o,o,o.timestamp,o.session,true),false);const low={...o,hud:{...o.hud,health:{current:3000,max:4015}}};assert.equal(g.ready(low,low,low.timestamp,low.session,true,false,false,true),false);});

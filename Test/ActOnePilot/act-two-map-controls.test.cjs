const test=require('node:test'),assert=require('node:assert/strict');
const gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-map.js');
const row=(text,x,y,width=100,height=25)=>({text,x,y,width,height});
const request={session:'synthetic',expectedFrameId:3};
const plan=action=>({session:'synthetic',frameId:3,reviewed:true,createdAt:1000,action});
test('zoom controls require their exact observed city-map layout',()=>{
 const o={timestamp:1000,hud:{bigMap:true},ocr:[row('Mondstadt',854,405),row('Cider Lake',872,238),row('+',34,431)]};
 assert.deepEqual(gate.target(o,1000,plan('zoomCity'),request),{x:48,y:444});
 assert.equal(gate.target(o,2001,plan('zoomCity'),request),null);
 const zoomed={timestamp:1000,hud:{bigMap:true},ocr:[row('Mondstadt',826,351),row('Cider Lake',850,122),row('Windrise',1251,743)]};
 assert.deepEqual(gate.target(zoomed,1000,plan('restoreCityZoom'),request),{x:48,y:635});
 assert.equal(gate.target(o,1000,plan('restoreCityZoom'),request),null);
});
test('an unconfirmed pin panel permits close only, never confirm or waypoint actions',()=>{
 const o={timestamp:1000,hud:{bigMap:false},ocr:[row('Custom Pin (Click to edit',1492,6),row('Total Pins 0/350',1443,915),row('X',1849,7)]};
 assert.deepEqual(gate.target(o,1000,plan('closeUnconfirmedPin'),request),{x:1876,y:34});
 for(const action of ['teleport','translatedCityWaypoint','confirm','zoomCity'])assert.equal(gate.target(o,1000,plan(action),request),null);
});

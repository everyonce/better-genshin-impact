const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-exam.js'),o=require('./act-two-flight-journal.fixture.json');
test('recorded flight pause permits journal close only with exact selected quest',()=>{
 assert(g.journalReady(o,1000,o.session));assert(!g.journalReady(o,2001,o.session));assert(!g.journalReady(o,1000,'wrong'));
 for(const text of ['In Progress','Mondstadt Glider','Follow the markers to arrive at the finish line in time'])assert(!g.journalReady({...o,ocr:o.ocr.filter(q=>q.text.trim()!==text)},1000,o.session));
 assert(!g.journalReady({...o,hud:{...o.hud,choice:true}},1000,o.session));assert(!g.journalReady({...o,ocr:[...o.ocr,{text:'Confirm'}]},1000,o.session));
});

test('authoritative final-trial completion permits bounded stationary landing only near the recorded roof',()=>{
 const f=require('./act-two-final-completed-flight.fixture.json');assert(g.afterTrial(f,1000,f.session,false));assert(g.fastState({space:true,health:f.hud.health},f.ocr,true));
 assert(!g.afterTrial(f,1000,f.session,true));assert(!g.afterTrial({...f,map:{...f.map,x:-1000}},1000,f.session,false));assert(!g.afterTrial({...f,ocr:f.ocr.filter(q=>q.text.trim()!=='Guild')},1000,f.session,false));assert(!g.afterTrial({...f,ocr:[...f.ocr,{text:'00:15',x:900,y:45}]},1000,f.session,false));
});

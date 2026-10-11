const test = require('node:test');
const assert = require('node:assert/strict');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');

function row(text,x,y,width=100,height=30){return {text,x,y,width,height};}
function partyScreen(patch={}) {
  return {timestamp:1000,map:null,ocr:[
    row('Party Setup',75,30),row('Lumina',410,320),row('Amber',760,350),
    row('Team Standing By',80,1010,280,35),row('Start',1688,999,85,36),
  ],hud:{world:false,journal:false,bigMap:false,dialogueReady:false,choice:false},...patch};
}

test('falcon party target accepts only the fresh expected two-character party screen',()=>{
  assert.deepEqual(bgi.falconPartyTarget(partyScreen(),1500),{x:1731,y:1017});
  const base=partyScreen();
  for(const bad of [
    {...base,timestamp:499},{...base,timestamp:1501},
    {...base,ocr:base.ocr.map(r=>r.text==='Party Setup'?{...r,text:'Domain Entrance'}:r)},
    {...base,ocr:base.ocr.filter(r=>r.text!=='Amber')},
    {...base,ocr:[...base.ocr,row('Start',1700,1000)]},
  ]) assert.equal(bgi.falconPartyTarget(bad,1500),null);
});

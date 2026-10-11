const test = require('node:test');
const assert = require('node:assert/strict');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');

function row(text,x,y,width=80,height=25){return {text,x,y,width,height};}

// Privacy-filtered OCR rows copied from frames 186, 192, and 198. UID rows are omitted.
const capture186=[
  row('Lumina',1674,342,92,36),row('Amber',1662,447,89,23),
  row('Amber has the ability to aim and shoot. While aiming, her arrows will',464,784,991,35),
  row('accumulate charge. Once fully charged, the arrow will be imbued with Pyro',412,822,1089,29),
];
const capture192=[
  row('Lumina',1677,342,89,36),row('Amber',1662,447,89,23),
  row('Use Pyro Skills to ignite combustible objects.',627,780,657,44),
];
const capture198=[
  row('Amber',1662,447,85,23),row('Trial',1799.333,418.333,45,21.333),
  row('R',1708,1026,29,25),
];

test('Pyro tutorial recognizes both captured English tutorial pages',()=>{
  assert.equal(bgi.falconPyroInfo(capture186),true);
  assert.equal(bgi.falconPyroInfo(capture192),true);
});

test('Pyro tutorial rejects unrelated text and matching text outside its recognized region',()=>{
  assert.equal(bgi.falconPyroInfo([row('Use Pyro Skills to ignite combustible objects.',900,780)]),false);
  assert.equal(bgi.falconPyroInfo([row('Amber has the ability to aim and shoot. While aiming, her arrows will',100,784),
    row('accumulate charge. Once fully charged, the arrow will be imbued with Pyro',100,822)]),false);
  assert.equal(bgi.falconPyroInfo([row('A different tutorial page.',620,780)]),false);
});

function aimFrame(patch={}) {
  const {hud:hudPatch,...rest}=patch;
  return {timestamp:1000,map:null,ocr:capture198,hud:{world:false,groundControls:false,climbing:false,journal:false,bigMap:false,
    dialogueReady:false,choice:false,tutorialStep:null,objectiveChanged:false,health:{current:1184,max:1184},...hudPatch},...rest};
}

test('aim tutorial requires captured R cue, fresh mapless domain state, safe HP and clear UI',()=>{
  assert.equal(bgi.falconAimHud(aimFrame(),1500),true);
  for(const bad of [
    aimFrame({hud:{groundControls:true}}),aimFrame({timestamp:0}),aimFrame({map:{map:'Teyvat'}}),
    aimFrame({hud:{health:{current:599,max:1184}}}),aimFrame({hud:{journal:true}}),
    aimFrame({hud:{bigMap:true}}),aimFrame({hud:{dialogueReady:true}}),aimFrame({hud:{choice:true}}),
    aimFrame({hud:{climbing:true}}),aimFrame({ocr:capture198.filter(r=>r.text!=='R')}),
  ]) assert.equal(bgi.falconAimHud(bad,1500),false);
});

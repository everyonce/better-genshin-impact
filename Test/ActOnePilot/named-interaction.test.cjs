const test = require('node:test');
const assert = require('node:assert/strict');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const wrappedTemple = [
  { text: 'Temple of the', x: 1228, y: 506, width: 181, height: 35 },
  { text: 'Falcon', x: 1217, y: 532, width: 98, height: 42 },
];
function safeScreen(overrides = {}) {
  return { objective: 'Enter the temple', world: true, position: true, health: { current: 1213, max: 1213 }, auto: false,
    journal: false, bigMap: false, dialogueReady: false, choice: false, objectiveChanged: false, tutorialStep: null, ...overrides };
}

test('named interaction recognizes Amber and adjacent aligned wrapped temple OCR rows', () => {
  assert.equal(bgi.namedInteractionVisible([{ text: 'Amber', x: 1300, y: 470 }], 'Talk to Amber'), true);
  assert.equal(bgi.namedInteractionVisible(wrappedTemple, 'Enter the temple'), true);
  assert.equal(bgi.namedInteractionVisible([{ text: 'Temple of the Falcon', x: 1300, y: 460 }], 'Enter the temple'), true);
  assert.equal(bgi.namedInteractionVisible([{ text: 'Amber', x: 1300, y: 470 }], 'Enter the temple'), false);
  assert.equal(bgi.namedInteractionVisible([
    wrappedTemple[0], { text: 'Falcon', x: 1300, y: 570, width: 98, height: 42 },
  ], 'Enter the temple'), false, 'nonadjacent rows are not concatenated');
  assert.equal(bgi.namedInteractionVisible([
    wrappedTemple[0], { text: 'Falcon', x: 1280, y: 532, width: 98, height: 42 },
  ], 'Enter the temple'), false, 'misaligned rows are rejected');
});

test('same-capture F crop is enabled only with named target and safe navigation HUD', () => {
  assert.equal(bgi.shouldReadInteractionCrop(wrappedTemple, 'Enter the temple', safeScreen()), true);
  assert.equal(bgi.shouldReadInteractionCrop([{ text: 'Amber', x: 1300, y: 470 }], 'Enter the temple', safeScreen()), false);
  assert.equal(bgi.shouldReadInteractionCrop(wrappedTemple, 'Enter the temple', safeScreen({ position: false })), false);
  assert.equal(bgi.shouldReadInteractionCrop(wrappedTemple, 'Enter the temple', safeScreen({ health: { current: 590, max: 1213 } })), false);
  assert.equal(bgi.shouldReadInteractionCrop(wrappedTemple, 'Enter the temple', safeScreen({ dialogueReady: true })), false);
  assert.equal(bgi.shouldReadInteractionCrop(wrappedTemple, 'Enter the temple', safeScreen({ journal: true })), false);
  assert.equal(bgi.shouldReadInteractionCrop(wrappedTemple, 'Enter the temple', safeScreen({ choice: true })), false);
  assert.equal(bgi.shouldReadInteractionCrop([...wrappedTemple, { text: 'F', x: 1098, y: 522 }], 'Enter the temple', safeScreen()), false,
    'same-capture crop is skipped when full-frame OCR already found the F prompt');
});

test('keyPress without a request objective uses only an observed exact supported objective', () => {
  const objective = bgi.resolveInteractionObjective(undefined, [{ text: 'Enter the temple', x: 100, y: 250 }]);
  assert.equal(objective, 'Enter the temple');
  assert.equal(bgi.shouldReadInteractionCrop(wrappedTemple, objective, safeScreen()), true,
    'the named screen and observed objective are enough without a fabricated request objective');
  assert.equal(bgi.resolveInteractionObjective(undefined, [{ text: 'Go to Mondstadt', x: 100, y: 250 }]), null);
  assert.equal(bgi.shouldReadInteractionCrop(wrappedTemple, null, safeScreen({ objective: null })), false);
});

test('3x-scaled same-image crop accepts one exact F prompt inside the bounded target region', () => {
  const f = bgi.interactionCropF([{ text: 'F', x: 54, y: 96, width: 135, height: 105 }], 1080, 490);
  assert.deepEqual({ text: f.text, x: Math.round(f.x), y: Math.round(f.y) }, { text: 'F', x: 1098, y: 522 });
  assert.equal(bgi.interactionCropF([{ text: 'F', x: 285, y: 20 }], 1080, 490), null, 'outside prompt region');
  assert.equal(bgi.interactionCropF([{ text: 'F', x: 54, y: 96 }, { text: 'F', x: 55, y: 97 }], 1080, 490), null,
    'ambiguous crop OCR is rejected');
});

test('Kaeya and Lisa interaction labels must match the exact requested speaker in the prompt zone', () => {
  const kaeya=[{text:'Kaeya',x:1320,y:470,width:75,height:28}];
  const lisa=[{text:'Lisa',x:1320,y:470,width:50,height:28}];
  assert.equal(bgi.namedInteractionVisible(kaeya,'Talk to Kaeya'),true);
  assert.equal(bgi.namedInteractionVisible(lisa,'Talk to Lisa'),true);
  assert.equal(bgi.namedInteractionVisible(lisa,'Talk to Kaeya'),false);
  assert.equal(bgi.namedInteractionVisible(kaeya,'Talk to Lisa'),false);
  assert.equal(bgi.namedInteractionVisible([{text:'Kaeya',x:500,y:470,width:75,height:28}],'Talk to Kaeya'),false,
    'party/member labels outside the center interaction prompt zone cannot establish the target');
  assert.equal(bgi.namedInteractionVisible([{text:'Lisa',x:1320,y:250,width:50,height:28}],'Talk to Lisa'),false,
    'a name outside the vertical prompt zone is not an interaction target');
});

test('interaction-crop guard preserves exact objective, speaker, health, and safe-scene requirements', () => {
  const kaeya=[{text:'Kaeya',x:1320,y:470,width:75,height:28}];
  const lisa=[{text:'Lisa',x:1320,y:470,width:50,height:28}];
  assert.equal(bgi.shouldReadInteractionCrop(kaeya,'Talk to Kaeya',safeScreen({objective:'Talk to Kaeya'})),true);
  assert.equal(bgi.shouldReadInteractionCrop(lisa,'Talk to Lisa',safeScreen({objective:'Talk to Lisa'})),true);
  assert.equal(bgi.shouldReadInteractionCrop(lisa,'Talk to Kaeya',safeScreen({objective:'Talk to Kaeya'})),false);
  assert.equal(bgi.shouldReadInteractionCrop(kaeya,'Talk to Lisa',safeScreen({objective:'Talk to Lisa'})),false);
  assert.equal(bgi.shouldReadInteractionCrop(kaeya,'Talk to Kaeya',safeScreen({objective:'Talk to Lisa'})),false,
    'crop reads require the requested and observed objective to agree exactly');
  for(const patch of [
    {world:false},{position:false},{health:{current:590,max:1213}},{health:null},{auto:true},{journal:true},
    {bigMap:true},{dialogueReady:true},{choice:true},{climbing:true},{objectiveChanged:true},{tutorialStep:'glideOpen'},
  ]) assert.equal(bgi.shouldReadInteractionCrop(kaeya,'Talk to Kaeya',safeScreen({objective:'Talk to Kaeya',...patch})),false);
});

test('objective resolution accepts only one exact named Talk objective',()=>{
  assert.equal(bgi.resolveInteractionObjective(undefined,[{text:'Talk to Kaeya',x:70,y:250}]),'Talk to Kaeya');
  assert.equal(bgi.resolveInteractionObjective(undefined,[{text:'Talk to Lisa',x:70,y:250}]),'Talk to Lisa');
  assert.equal(bgi.resolveInteractionObjective('Talk to Kaeya',[{text:'Talk to Lisa',x:70,y:250}]),'Talk to Kaeya');
  assert.equal(bgi.resolveInteractionObjective(undefined,[{text:'Talk to Kaeya',x:70,y:250},{text:'Talk to Lisa',x:70,y:280}]),null,
    'ambiguous simultaneous objectives are not resolved by choosing one');
});

test('navigation stops for only the exact requested NPC and does not accept party labels',async()=>{
  async function run(objective,speaker,x=1320) {
    let now=1000;const moves=[];
    const frame={frameId:4,map:{map:'Teyvat',x:0,y:0,cameraAngle:180},ocr:[
      {text:speaker,x,y:470,width:80,height:28},{text:'F',x:1098,y:522,width:45,height:35},
    ],hud:{world:true,objectives:[objective],health:{current:900,max:1000},interact:true,dialogueReady:false,choice:false,
      objectiveChanged:false,lowHealth:false,climbing:false,journal:false,bigMap:false}};
    const api={now:()=>now,sleep:async ms=>{now+=ms;},checkStop:()=>{},rotate:async()=>{},forward:async ms=>moves.push(ms)};
    const result=await mission.runNavigation({objective,deadlineMs:5000,waypoints:[{map:'Teyvat',x:10,y:0}]},frame,api,async()=>frame);
    return {result,moves};
  }
  for(const who of ['Kaeya','Lisa']) {
    const match=await run('Talk to '+who,who);
    assert.equal(match.result.reason,'Interaction available');assert.deepEqual(match.moves,[]);
    const wrong=await run('Talk to '+who,who==='Kaeya'?'Lisa':'Kaeya');
    assert.notEqual(wrong.result.reason,'Interaction available');assert.ok(wrong.moves.length>0);
  }
  const partyLabel=await run('Talk to Kaeya','Kaeya',500);
  assert.notEqual(partyLabel.result.reason,'Interaction available');assert.ok(partyLabel.moves.length>0);
});


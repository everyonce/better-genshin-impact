const test = require('node:test');
const assert = require('node:assert/strict');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');

const targetBar = { x: 1370, y: 631, width: 52, height: 6 };
const matchingLv1 = { text: 'Lv.1', x: 1357, y: 580, width: 97, height: 48 };

test('recorded nearby Lv10 labels anchor both partly depleted and full threat bars',()=>{
  const fixture=require('./act-two-lv10-anchors.fixture.json');
  for(const item of fixture.localReads){
    assert.equal(bgi.enemyBarAnchored(item.bar,item.rows,10),true);
    for(const level of [1,5,11,13])assert.equal(bgi.enemyBarAnchored(item.bar,item.rows,level),false);
    assert.equal(bgi.enemyBarAnchored(item.bar,item.rows.map(r=>({...r,y:r.y+100})),10),false);
  }
});

test('anchors an enemy bar to a nearby level-one OCR row', () => {
  assert.equal(bgi.enemyBarSize(targetBar.width, targetBar.height), true);
  assert.equal(bgi.enemyBarAnchored(targetBar, [matchingLv1]), true);
});

test('normal camp camera has a twelve-pixel level-to-bar gap', () => {
  // Screen geometry from live frame 534, before combat-camera zoom.
  assert.equal(bgi.enemyBarAnchored({x:612,y:555,width:84,height:8},
    [{text:'Lv. 1',x:589,y:536,width:43,height:14}]), true);
  assert.equal(bgi.enemyBarAnchored({x:966,y:278,width:65,height:6},
    [{text:'Lv. 1',x:949,y:259,width:34,height:14}]), true);
});

test('accepts common OCR variants of level one but not the player or other levels', () => {
  for (const text of ['Lv. 1', 'LV1', 'Lv.I', 'Lv. l']) {
    assert.equal(bgi.enemyBarAnchored(targetBar, [{ ...matchingLv1, text }]), true, text);
  }
  for (const text of ['Lv.3', 'Lv.2', 'Level 1', 'Teleport-Waypoint']) {
    assert.equal(bgi.enemyBarAnchored(targetBar, [{ ...matchingLv1, text }]), false, text);
  }
});

test('rejects waypoint-like red slivers when no enemy level label is present', () => {
  const waypointBars = [
    { x: 1546, y: 630.5, width: 2, height: 3 },
    { x: 1550, y: 507.5, width: 2, height: 3 },
    { x: 1568.5, y: 502.5, width: 3, height: 3 },
  ];
  const waypointOcr = [{ text: 'Teleport-Waypoint', x: 1216, y: 520, width: 275, height: 35 }];
  for (const bar of waypointBars) {
    assert.equal(bgi.enemyBarSize(bar.width, bar.height), true);
    assert.equal(bgi.enemyBarAnchored(bar, waypointOcr), false);
  }
});

test('requires the level label to be above and horizontally associated with the bar', () => {
  assert.equal(bgi.enemyBarAnchored(targetBar, [{ ...matchingLv1, x: 1000 }]), false, 'too far sideways');
  assert.equal(bgi.enemyBarAnchored(targetBar, [{ ...matchingLv1, y: 650 }]), false, 'below the bar');
  assert.equal(bgi.enemyBarAnchored(targetBar, [{ ...matchingLv1, y: 500 }]), false, 'too far above');
});

test('level-13 depleted bars require an exact nearby level label',()=>{
 const bar={x:1216,y:317,width:12,height:7},r={text:'Lv.13',x:1217,y:290,width:67,height:20};
 assert.equal(bgi.enemyBarAnchored(bar,[r],13),true);
 for(const text of ['Lv.3','Lv.1','Lv.14','13','Level 13'])assert.equal(bgi.enemyBarAnchored(bar,[{...r,text}],13),false);
 assert.equal(bgi.enemyBarAnchored(bar,[{...r,x:1600}],13),false);
 assert.equal(bgi.enemyBarAnchored(bar,[r],4),false);
});
test('Crossroads level 11 and 14 bars require the exact nearby level label',()=>{
 for(const level of [11,14]){
  const row={text:'Lv. '+level,x:800,y:460,width:100,height:30},bar={x:850,y:500,width:12,height:7};
  assert.equal(bgi.enemyBarAnchored(bar,[row],level),true);
  for(const text of ['Lv. 16','Level '+level,'Lv. 1','Lv. 13'])assert.equal(bgi.enemyBarAnchored(bar,[{...row,text}],level),false);
  assert.equal(bgi.enemyBarAnchored(bar,[{...row,x:1400}],level),false);
 }
});

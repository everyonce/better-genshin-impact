const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');

const packageDir = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const source = fs.readFileSync(path.join(packageDir, 'bgi.js'), 'utf8');
const row = (text, x, y, width = 50, height = 20) => ({ text, x, y, width, height });

async function observe({ level = 5, greenRows = [], tightRows = [], extraContours = [], wrongRed = false, barContour = { x: 762, y: 709, width: 164, height: 13 } } = {}) {
  const contours = [barContour, ...extraContours];
  const full = [row('Kaeya', 1664, 484), row('Trial', 1796, 463), row('1427/1427', 912, 1003, 195, 14), row('E', 1700, 1015, 30, 20)];
  if (level === 1) full.push(row('Defeat the nearby hilichurls', 100, 250, 300, 24));
  const cropCalls = [], counters = { normalOcr: 0, greenOcr: 0, inRange: [], regionsCreated: 0, regionsDisposed: 0,
    barLocalOcr: 0, cropsCreated: 0, cropsDisposed: 0, masksCreated: 0, masksDisposed: 0, convertedCreated: 0, convertedDisposed: 0 };
  const context = {
    Date: class extends Date { static now() { return 2000000; } },
    genshin: { isRemoteDesktopSession: true, windowsSessionId: 7, isGameForeground: true, getPositionFromMap: () => null, getCameraOrientation: () => 0 },
    file: { isExists: () => false, readTextSync: p => fs.readFileSync(path.join(packageDir, p), 'utf8'), writeTextSync: () => true, writeImageSync: () => true },
    RecognitionObject: { Ocr: () => ({}) },
    ImageRegion: class {
      constructor(mat) { this.mat = mat; this.width = 1920; this.height = 1080; counters.regionsCreated++; }
      findMulti() {
        const selected = this.mat && this.mat.green ? greenRows : this.mat && this.mat.tight ? tightRows : [];
        const result = selected.map(r => ({ ...r, x: (r.x - this.mat.x) * 3, y: (r.y - this.mat.y) * 3, width: r.width * 3, height: r.height * 3 }));
        if (this.mat && this.mat.green) counters.greenOcr++; else counters.normalOcr++;
        if (this.mat && this.mat.barLocal) counters.barLocalOcr++;
        result.count = result.length; return result;
      }
      dispose() { counters.regionsDisposed++; if (this.mat && this.mat.dispose) this.mat.dispose(); }
    },
    OpenCvSharp: { OpenCvSharp: {
      Size: class { constructor(w, h) { this.width = w; this.height = h; } },
      Scalar: class { constructor(a, b, c) { this.values = [a, b, c]; } },
      ColorConversionCodes: { GRAY2BGR: 1 },
      RetrievalModes: { External: 0 }, ContourApproximationModes: { ApproxSimple: 0 }, Cv2: { boundingRect: c => c, contourArea: () => 0 },
    } },
    captureGameRegion: () => ({ width: 1920, height: 1080, srcMat: {}, findMulti: () => { const result = full.map(r => ({ ...r })); result.count = result.length; return result; },
      deriveCrop: (x, y, w, h) => {
        counters.cropsCreated++; cropCalls.push({ x, y, w, h });
        if (x === 350 && y === 100) return { srcMat: { inRange: (low, high) => {
          counters.inRange.push({ low: low.values, high: high.values }); counters.masksCreated++;
          return { findContoursAsArray: () => wrongRed ? [] : contours, dispose() { counters.masksDisposed++; } };
        } }, dispose() { counters.cropsDisposed++; } };
        if (w === 240 && (h === 70 || h === 90)) return { srcMat: { inRange: (low, high) => {
          counters.inRange.push({ low: low.values, high: high.values }); counters.masksCreated++;
          return { cvtColor: () => { counters.convertedCreated++; return { green: true, x, y, resize: () => ({ green: true, x, y, dispose() {} }), dispose() { counters.convertedDisposed++; } }; }, dispose() { counters.masksDisposed++; } };
        } }, dispose() { counters.cropsDisposed++; } };
        return { srcMat: { resize: () => ({ local: true, x, y, tight: w === 64 && h === 28, barLocal: w === 300 && h === 90, dispose() {} }) }, dispose() { counters.cropsDisposed++; } };
      }, dispose() {} }),
    sleep: async () => {}, click: () => {}, log: { info() {} },
  };
  vm.runInNewContext(source, context);
  const adapter = context.createActOneAdapter(7);
  const step = level === 5 ? 'wolfLookLeft' : level === 4 ? 'falconCombat' : 'combat';
  const objective = level === 1 ? 'Defeat the nearby hilichurls' : undefined;
  adapter.beginMission({ mission: 'questStep', step, objective, session: 'test', createdAt: 2000000 });
  const result = await adapter.observe('test', 1);
  return { bars: JSON.parse(JSON.stringify(result.hud.enemyBars)), diagnostic: JSON.parse(JSON.stringify(result.hud.enemyBarDiagnostic)), cropCalls, counters };
}

test('one green-mask OCR recovers only a spatially anchored Lv.5 above a bar-shaped red candidate', async () => {
  const result = await observe({ greenRows: [row('Lv.5', 1149, 772, 70, 28)] });
  assert.deepEqual(result.bars, [{ x: 1194, y: 815.5, width: 164, height: 13 }]);
  assert.equal(result.counters.greenOcr, 1);
  assert.deepEqual(result.diagnostic.greenMask.rows.map(r => r.text), ['Lv.5']);
  assert.deepEqual(result.diagnostic.greenMask.rows[0], { text: 'Lv.5', x: 1149, y: 772, width: 70, height: 28 });
  assert.deepEqual(result.cropCalls.filter(c => c.w === 240), [{ x: 1074, y: 738, w: 240, h: 70 }]);
  assert.deepEqual(result.counters.inRange.find(v => v.low[0] === 20), { low: [20, 110, 40], high: [130, 230, 190] });
});

test('wrong, absent, or ambiguous level labels never anchor a red bar', async () => {
  for (const greenRows of [[], [row('Lv.4', 1149, 772, 70, 28)],
    [row('Lv.5', 1149, 772, 70, 28), row('Lv.5', 1150, 772, 70, 28)]]) {
    const result = await observe({ greenRows });
    assert.deepEqual(result.bars, []);
  }
  const offAnchor = await observe({ greenRows: [row('Lv.5', 1149, 750, 70, 28)] });
  assert.deepEqual(offAnchor.bars, [], 'vertical distance outside the existing label-to-bar anchor is rejected');
});

test('Lv, 5 OCR punctuation is accepted only as a unique exact level-5 token at the bar anchor', async () => {
  const accepted = await observe({ greenRows: [row('Lv, 5', 1149, 772, 70, 28)] });
  assert.equal(accepted.bars.length, 1);
  for (const greenRows of [
    [row('Lv,4', 1149, 772, 70, 28)],
    [row('LV,55', 1149, 772, 70, 28)],
    [row('Lv, 5 enemy', 1149, 772, 70, 28)],
    [row('Lv, 5', 1149, 772, 70, 28), row('Lv, 5', 1150, 738, 70, 25)],
  ]) assert.deepEqual((await observe({ greenRows })).bars, []);
  const bar = { x: 1194, y: 815.5, width: 164, height: 13 };
  assert.equal(bgi.enemyBarAnchored(bar, [row('Lv, 5', 1149, 772, 70, 28)], 5), true);
  assert.equal(bgi.enemyBarAnchored(bar, [row('Lv,4', 1149, 772, 70, 28)], 5), false);
  assert.equal(bgi.enemyBarAnchored(bar, [row('Lv, 4', 1149, 772, 70, 28)], 4), false,
    'comma normalization does not change level-4 semantics');
  assert.equal(bgi.enemyBarAnchored(bar, [row('Lv.4', 1149, 772, 70, 28)], 4), true);
});

test('green fallback supports exact levels 4 and 5 and keeps the four existing local reads unchanged', async () => {
  const extraContours = Array.from({ length: 7 }, (_, i) => ({ x: 80 + i * 150, y: 200, width: 20, height: 6 }));
  const level5 = await observe({ greenRows: [row('Lv.5', 1149, 772, 70, 28)], extraContours });
  assert.equal(level5.counters.barLocalOcr, 4);
  assert.equal(level5.counters.greenOcr, 1);
  for (const level of [1]) {
    const other = await observe({ level, greenRows: [row('Lv.5', 1149, 772, 70, 28)], extraContours });
    assert.equal(other.counters.greenOcr, 0);
    assert.equal(other.counters.barLocalOcr, 4);
  }
  const level4 = await observe({ level:4, greenRows:[row('Lv.4',1149,772,70,28)], extraContours });
  assert.equal(level4.bars.length,1);
  assert.equal(level4.counters.greenOcr,1);
  assert.ok(level4.counters.inRange.some(v=>v.low.join(',')==='150,150,150'&&v.high.join(',')==='255,255,255'));
  assert.equal(level4.counters.barLocalOcr,4);
  for(const greenRows of [[row('Lv.5',1149,772,70,28)],[row('Lv.4',1149,750,70,28)],[row('Lv.4',1149,772,70,28),row('Lv.4',1150,772,70,28)]])
    assert.deepEqual((await observe({level:4,greenRows})).bars,[]);
});

test('masked diagnostics exclude the bottom-right UID and all crop/mask/region resources are disposed', async () => {
  const result = await observe({ greenRows: [row('Lv.5', 1149, 772, 70, 28), row('UID: 693300001', 1680, 1040, 200, 20)] });
  assert.doesNotMatch(JSON.stringify(result.diagnostic.greenMask), /UID|693300001/);
  assert.equal(result.counters.cropsCreated, result.counters.cropsDisposed);
  assert.equal(result.counters.masksCreated, result.counters.masksDisposed);
  assert.equal(result.counters.convertedCreated, result.counters.convertedDisposed);
  assert.equal(result.counters.regionsCreated, result.counters.regionsDisposed);
});

test('level-4 pale label recovery includes nearly depleted short red bars',async()=>{
  const result=await observe({level:4,barContour:{x:329,y:397,width:15,height:7},greenRows:[row('Lv.4',690,480,40,15)]});
  assert.deepEqual(result.bars,[{x:686.5,y:500.5,width:15,height:7}]);
  assert.equal(result.counters.greenOcr,1);
});

test('frame305 distant Lv4 fallback contains the complete label baseline at threefold scale',async()=>{
  // Recorded red contour and visually measured label bounds; OCR is stubbed here.
  // This tests crop geometry and anchoring, not real OCR recognition accuracy.
  const barContour={x:679,y:257,width:63,height:5};
  const label=row('Lv. 4',1038,340,41,15);
  const result=await observe({level:4,barContour,greenRows:[label]});
  const crop=result.cropCalls.find(c=>c.w===240);
  assert.deepEqual(crop,{x:941,y:282,w:240,h:90});
  assert.ok(label.y+label.height<=crop.y+crop.h,'whole label survives the crop');
  assert.ok(label.y+label.height>crop.y+70,'old crop clipped the label baseline');
  assert.deepEqual(result.diagnostic.greenMask.rows,[label]);
  assert.deepEqual(result.bars,[{x:1060.5,y:359.5,width:63,height:5}]);
  assert.equal(result.counters.regionsCreated,result.counters.regionsDisposed);
});

test('frame306 and non-enemy or wrong-level evidence still cannot authorize a Lv4 target',async()=>{
  const barContour={x:679,y:257,width:63,height:5};
  for(const greenRows of [[],[row('Lv.5',1038,340,41,15)],
    [row('4',1038,340,41,15)],[row('Food',1038,340,41,15)],
    [row('Lv.4',1038,365,41,15)],[row('Lv.4',1350,340,41,15)]]) {
    assert.deepEqual((await observe({level:4,barContour,greenRows})).bars,[]);
  }
  // Frame306 retains a visible label but has no in-crop red component.
  const noBar=await observe({level:4,barContour,wrongRed:true,greenRows:[row('Lv.4',1015,340,41,15)]});
  assert.deepEqual(noBar.bars,[]);
  assert.equal(noBar.counters.greenOcr,0);
});
const samples=[
 {frame:334,bar:{x:662,y:270,width:63,height:6},crop:{x:1012,y:343},raw:{text:'Lv.4',x:0,y:5,width:192,height:79}},
 {frame:335,bar:{x:663,y:268,width:64,height:5},crop:{x:1013,y:341},raw:{text:'Lv.4',x:0,y:17,width:192,height:67}},
 {frame:336,bar:{x:664,y:265,width:63,height:5},crop:{x:1014,y:338},raw:{text:'Lv.4',x:0,y:24,width:192,height:57}},
];
test('recorded334-336 actual in-process tight OCR rows retain exact-level spatial anchoring',async()=>{
 for(const s of samples){
  const r=s.raw,rows=[row(r.text,s.crop.x+r.x/3,s.crop.y+r.y/3,r.width/3,r.height/3)];
  const result=await observe({level:4,barContour:s.bar,tightRows:rows});
  assert.equal(result.bars.length,1,`frame${s.frame}`);
  assert.equal(result.diagnostic.tightLabel.anchored,true);
  assert.deepEqual(result.diagnostic.tightLabel.crop,{...s.crop,width:64,height:28,scale:3});
  assert.equal(result.counters.greenOcr,0);
  assert.equal(result.counters.regionsCreated,result.counters.regionsDisposed);
 }
});
test('tight fallback rejects recorded negatives, wrong levels, misreads and unanchored labels',async()=>{
 const barContour=samples[0].bar;
 for(const text of ['', 'ly. 16','Al.4','Ev. 4','Iv.4','V.4','Food','Lv.5']){
  assert.deepEqual((await observe({level:4,barContour,tightRows:text?[row(text,1012,345,64,26)]:[]})).bars,[]);
 }
 assert.deepEqual((await observe({level:4,barContour,wrongRed:true,tightRows:[row('Lv.4',1012,345,64,26)]})).bars,[]);
 assert.deepEqual((await observe({level:4,barContour,tightRows:[row('Lv.4',1012,380,64,26)]})).bars,[]);
 const outside=await observe({level:4,barContour:{...barContour,width:130,height:12},tightRows:[row('Lv.4',1012,345,64,26)]});
 assert.equal(outside.diagnostic.tightLabel,undefined,'larger known-positive134 uses existing recognition');
});

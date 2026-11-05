const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const fixture = require('./passive-regional-map-uid.fixture.json');
const bg = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'), 'utf8'), bg);

const observed = fixture.passiveFrame;
const request = {mission:'observe'};
const uidRows = rows => rows.filter(r => r.x > 1600 && r.y > 1020 && /^(?:UID)?[: ]*\d{9,10}$/.test(r.text.trim()));
const noRead = () => {throw Error('Unexpected targeted OCR');};
// Convert the retained full-image row back to the enlarged crop's local coordinates.
function cropCoordinates(r) {
    return {text:r.text, x:Math.round((r.x-1680)*3), y:Math.round((r.y-1040)*3),
        width:Math.round(r.width*3), height:Math.round(r.height*3)};
}
test('passive frame 36 uses the same exact UID crop as the successful native map request',()=>{
    const old = fixture.mapFrames[1];
    assert.equal(old.frameId,35);
    assert.equal(observed.frameId,36);
    assert.equal(observed.cropSha256,old.cropSha256);
    assert.equal(uidRows(observed.rows).length,0);
    assert(observed.rows.some(r=>r.x===1515 && r.text.includes('UID:')));
    for(const mapFrame of fixture.mapFrames){
        let reads=0;
        const result=bg.actOneObserveRegionalMapRows(request,observed.rows,observed.bigMap,observed.position,(...box)=>{
            reads++;assert.deepEqual(box,[1680,1040,190,40]);return mapFrame.targetedRows.map(cropCoordinates);
        });
        assert.equal(reads,1);
        assert.deepEqual(JSON.parse(JSON.stringify(result.slice(0,observed.rows.length))),observed.rows);
        assert.deepEqual(JSON.parse(JSON.stringify(uidRows(result))),mapFrame.targetedRows);
        assert.equal(bg.actTwoOriginalAccount(result),true);
    }
});

test('recognized UID evidence survives intact, including foreign and conflicting values',()=>{
    const old=fixture.mapFrames[1].targetedRows[0];
    for(const values of [[old.text],['UID: 123456789'],['1234567890'],[old.text,'UID: 123456789']]){
        const rows=[...observed.rows,...values.map(text=>({...old,text}))];
        assert.equal(bg.actOneObserveRegionalMapRows(request,rows,true,null,noRead),rows);
    }
    const missing=bg.actOneObserveRegionalMapRows(request,observed.rows,true,null,()=>[]);
    assert.equal(uidRows(missing).length,0);
    const other=bg.actOneObserveRegionalMapRows(request,observed.rows,true,null,()=>[{...cropCoordinates(old),text:'UID: 123456789'}]);
    assert.equal(bg.actTwoOriginalAccount(other),false);
});
test('world, menu, non-passive request and unrelated map text never trigger the UID crop',()=>{
    for(const [req,rows,bigMap,pos] of [
        [request,observed.rows,false,null], [request,observed.rows,true,{map:'Teyvat',x:12,y:6}],
        [{mission:'questStep',step:'actTwoWorldMap'},observed.rows,true,null],
        [request,[{text:'Starfell Valley',x:100,y:250},{text:'Exploration Progress: 16%',x:450,y:430}],true,null]
    ]) assert.equal(bg.actOneObserveRegionalMapRows(req,rows,bigMap,pos,noRead),rows);
});

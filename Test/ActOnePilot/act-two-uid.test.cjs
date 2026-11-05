const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
test('matching full and cropped UID reads remain valid; conflicting or absent identities fail',()=>{
 const o=JSON.parse(fs.readFileSync(__dirname+'/act-two-duplicate-uid.fixture.json','utf8'));
 assert.equal(bgi.originalAccount(o.ocr),true);
 assert.equal(bgi.originalAccount(o.ocr.concat({text:'UID: 665976391',x:1680,y:1052})),false);
 assert.equal(bgi.originalAccount([{text:'693306810',x:1500,y:1052}]),false);
 assert.equal(bgi.originalAccount([]),false);
});

test('guild frame 6 full-screen digits and scaled UID form one native OCR row',()=>{
 const vm=require('node:vm'),ctx=vm.createContext({});
 vm.runInContext(fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8'),ctx);
 const {rows}=require('./guild-uid-frame-6.fixture.json'),[bare,named]=rows;
 const raw={...named,x:(named.x-1680)*3,y:(named.y-1040)*3,width:named.width*3,height:named.height*3};
 const merged=ctx.actOneMergeControlCropRows([bare],[raw],1680,1040);
 assert.equal(merged.length,1);assert.equal(merged[0].text,named.text);assert.equal(merged[0].x,named.x);
 const historical=require('./act-two-duplicate-uid.fixture.json').ocr.find(r=>/^[0-9]{9}$/.test(r.text)).text;
 const original=pair=>pair.map(r=>({...r,text:r.text.replace('123456789',historical)}));
 assert.equal(bgi.originalAccount(original(merged)),true);
 assert.deepEqual(Array.from(ctx.actOneCanonicalUidRows([named,bare])),[named]);
 const alt=rows.map(r=>({...r,text:r.text.replace('123456789','1234567890')}));
 assert.deepEqual(Array.from(ctx.actOneCanonicalUidRows(alt)),[alt[1]]);
 for(const pair of [[bare,{...named,text:'UID:123456780'}],[bare,{...named,x:named.x+12}],
         [bare,{...named,y:1066}],[bare,{...named,width:undefined}],[bare,{...named,x:1679}],
         [bare,{...named,text:bare.text}],[named,{...named}],[bare,named,{...bare,x:1610}]]){
     assert.deepEqual(Array.from(ctx.actOneCanonicalUidRows(pair)),pair);
     assert.equal(bgi.originalAccount(original(pair)),false);
 }
 assert.equal(bgi.originalAccount(original([bare,{text:'UID:1123456789',x:1680,y:1024}])),false);
});

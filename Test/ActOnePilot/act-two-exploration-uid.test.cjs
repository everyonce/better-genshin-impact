const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const source=fs.readFileSync(path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8');
const body=source.slice(source.indexOf("                if(request&&(request.mission==='navigation'&&['Explore for Adventure Rank'"),source.indexOf('                var fullOcrMs'));
const run=new Function('request','rows','actTwoOriginalAccount','actOneMergeControlCropRows','scaledRows','img',body+'return rows;');
test('Exploration retries malformed UID prefix from the same frame through the right image edge',()=>{
 const rows=[{text:'JID: 693306810',x:1691,y:1046,width:219,height:33}],calls=[];
 const result=run({mission:'navigation',objective:'Explore for Adventure Rank'},rows,bgi.originalAccount,bgi.mergeControlCropRows,(img,x,y,w,h)=>{calls.push({img,x,y,w,h});return [{text:'693306810',x:40,y:12,width:180,height:24}];},'same-image');
 assert.deepEqual(calls,[{img:'same-image',x:1680,y:1040,w:240,h:40}]);assert.equal(bgi.originalAccount(result),true);
});
test('UID crop keeps conflicts rejected and avoids unrelated navigation',()=>{
 const rows=[{text:'UID: 111111111',x:1700,y:1052,width:200,height:24}];
 const result=run({mission:'navigation',objective:'Explore for Adventure Rank'},rows,bgi.originalAccount,bgi.mergeControlCropRows,()=>[{text:'693306810',x:40,y:12,width:180,height:24}],{});
 assert.equal(bgi.originalAccount(result),false);
 let crops=0;run({mission:'navigation',objective:'Other'},[],bgi.originalAccount,bgi.mergeControlCropRows,()=>{crops++;return [];},{});assert.equal(crops,0);
});

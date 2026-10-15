const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const context={};vm.runInNewContext(fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8'),context);
test('known map-label suffix preserves exact account identity and conflict rejection',()=>{
 const row={text:'UID: 693306810Cape',x:1675,y:1038,width:245,height:42};
 assert.equal(context.actTwoOriginalAccount([row]),true);
 assert.equal(context.actTwoOriginalAccount([{...row,text:'UID: 693306810ape'}]),true);
 assert.equal(context.actTwoOriginalAccount([{...row,text:'UID: 693306811ape'}]),false);
 assert.equal(context.actTwoOriginalAccount([row,{...row,text:'UID: 111111111ape'}]),false);
 for(const text of ['UID: 693306811Cape','UID: 6933068100Cape','UID: 693306810Other','UID: 693306810Cape123'])assert.equal(context.actTwoOriginalAccount([{...row,text}]),false);
 assert.equal(context.actTwoOriginalAccount([row,{...row,text:'UID: 111111111'}]),false);
 assert.equal(context.actTwoOriginalAccount([{...row,y:1020}]),false);
});

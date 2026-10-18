const test=require('node:test'),assert=require('node:assert/strict');
const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/field-progress.js');
const a={session:'recorded',frameId:1572,timestamp:1,map:null,hud:{world:true,climbing:true,groundControls:false,objectives:["Enter Raptor's Hideout",'Higher 33m']}};
const b={...a,frameId:1578,timestamp:2,map:{map:'Teyvat',x:8007.255859375,y:7974.60986328125,cameraAngle:122}};
const p={mode:'climb',actions:[{type:'key',key:'VK_W',ms:600}]};
const h=g.finish(g.begin({version:1,entries:[]},p,a,'probe'),'probe',b);
const cameraEvidence={method:'native-GIA-saved-image',session:'recorded',frames:[{frame:1572,angle:121,sha256:'EEC895B00367D48000A8913789D9509CBE8299D042F2D82C1F85469078D0F1BC'},{frame:1578,angle:121,sha256:'DA072EF2E202B7F01BEEB3C6A11FDEA4F849AF3AF2876727C169FD93CF83A274'}]};
const review={fromFrame:1572,toFrame:1578,kind:'vertical-landmark',landmark:'Grass-to-rock base at left wall seam',beforeY:650,afterY:700,cameraUnchanged:true,cameraEvidence};
test('saved-image headings can substantiate vertical review when start map is absent',()=>{
 assert.match(g.rejection(h,p,b),/unverified/);
 assert.equal(g.rejection(h,{...p,progressReview:review},b),null);
});
test('missing angle still fails without exact image provenance and unchanged view',()=>{
 for(const patch of [{cameraEvidence:null},{toFrame:1583},{cameraUnchanged:false},{afterY:655},{cameraEvidence:{...cameraEvidence,session:'other'}},{cameraEvidence:{...cameraEvidence,frames:[cameraEvidence.frames[0],{...cameraEvidence.frames[1],angle:145}]}},{cameraEvidence:{...cameraEvidence,frames:[cameraEvidence.frames[0],{...cameraEvidence.frames[1],sha256:'bad'}]}}])assert.match(g.rejection(h,{...p,progressReview:{...review,...patch}},b),/unverified/);
});
test('release landing cannot reuse earlier ascent proof',()=>{
 const landed={...b,frameId:1583,hud:{...b.hud,climbing:false,groundControls:true}};
 assert.match(g.rejection(h,{...p,progressReview:review},landed),/unverified/);
});

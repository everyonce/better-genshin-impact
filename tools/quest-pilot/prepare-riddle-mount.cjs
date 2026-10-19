const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'../..');
const pilot=path.join(root,'artifacts/release-r18/BetterGI-English-win-x64/User/JsScript/ActOnePilot');
const mount=require(path.join(root,'BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-riddle-mount.js'));
const inventoryGate=require(path.join(root,'BetterGenshinImpact/User/JsScript/ActOnePilot/world-inventory.js')).worldInventoryClosePermission;
const [session,frameText]=process.argv.slice(2),frame=Number(frameText),now=Date.now();
if(!session||!Number.isInteger(frame)||frame<1)throw Error('Fresh pinned session and inventory frame required');
const read=f=>JSON.parse(fs.readFileSync(f,'utf8'));
const inv=read(path.join(pilot,'observations',session,`frame-${String(frame).padStart(4,'0')}.json`));
if(!inventoryGate(inv,inv.timestamp,session)||now-inv.timestamp>15000)throw Error('Recent verified Inventory pause required');
const review=mount.plan().mountReview;
for(const scene of review.scene){
 const stem=path.join(pilot,'observations',review.surveySession,`frame-${String(scene.frameId).padStart(4,'0')}`);
 const witness=read(stem+'.json'),digest=crypto.createHash('sha256').update(fs.readFileSync(stem+'.png')).digest('hex');
 if(witness.session!==review.surveySession||witness.frameId!==scene.frameId||digest!==scene.sha256||!witness.map||witness.map.map!=='Teyvat'||Math.hypot(witness.map.x+842.92578125,witness.map.y-2209.25390625)>.02||!witness.hud.groundControls||witness.hud.climbing)throw Error('Saved stone-face scene changed');
}
const witness=read(path.join(pilot,'observations',review.surveySession,'frame-0520.json'));
const request={step:'actTwoRiddleMount',session,expectedFrameId:frame};
const plan={session,frameId:frame,witnessFrameId:520,witnessSession:review.surveySession,createdAt:now,mountReview:review};
if(!mount.permit(plan,request,inv,witness,now))throw Error('One-use permit preflight failed');
const out=path.join(pilot,'act-two-riddle-mount-request.json');
if(fs.existsSync(out))throw Error('Existing mount permit must be inspected before replacement');
fs.writeFileSync(out,JSON.stringify(plan));
console.log(JSON.stringify({session,frame,createdAt:now,surveySession:review.surveySession,sceneFrames:review.scene.map(x=>x.frameId),oneUse:true}));

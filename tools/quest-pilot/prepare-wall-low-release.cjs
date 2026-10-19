const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'../..'),pilot=path.join(root,'artifacts/release-r18/BetterGI-English-win-x64/User/JsScript/ActOnePilot');
const guard=require(path.join(root,'BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-wall-low-release.js'));
const stamina=require(path.join(root,'BetterGenshinImpact/User/JsScript/ActOnePilot/climb-stamina.js'));
const gate=require(path.join(pilot,'world-inventory.js')).worldInventoryClosePermission;
const [session,frameText]=process.argv.slice(2),frame=Number(frameText),now=Date.now(),read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
if(!session||!Number.isInteger(frame)||frame<1||session===guard.sourceSession)throw Error('Fresh Inventory session/frame required');
const initial=read(path.join(pilot,'observations',session,`frame-${String(frame).padStart(4,'0')}.json`));
if(!gate(initial,initial.timestamp,session)||now-initial.timestamp>120000)throw Error('Recent verified Inventory pause required');
const witnesses=[];
for(const id of [10,11]){
 const stem=path.join(pilot,'observations',guard.sourceSession,`frame-${String(id).padStart(4,'0')}`),o=read(stem+'.json');
 if(!guard.attached(o,guard.sourceSession,o.timestamp)||stamina.classify(o.hud.climbStamina).kind!=='absent')throw Error('Recorded low attachment or absent-signal witness changed');
 witnesses.push({frameId:id,sha256:crypto.createHash('sha256').update(fs.readFileSync(stem+'.png')).digest('hex')});
}
const plan={session,frameId:frame,sourceSession:guard.sourceSession,sourceFrames:[10,11],witnesses,createdAt:now};
if(!guard.permit(plan,{step:'actTwoWallLowRelease',session,expectedFrameId:frame},{...initial,timestamp:now},gate,now))throw Error('Low-release permit refused');
const target=path.join(pilot,'act-two-wall-low-release-request.json');if(fs.existsSync(target))throw Error('Existing low-release permit must be inspected');
fs.writeFileSync(target,JSON.stringify(plan));console.log(JSON.stringify(plan));

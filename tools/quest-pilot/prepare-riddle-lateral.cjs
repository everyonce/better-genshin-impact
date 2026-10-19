const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'../..');
const pilot=path.join(root,'artifacts/release-r18/BetterGI-English-win-x64/User/JsScript/ActOnePilot');
const field=require(path.join(pilot,'act-two-field.js'));
const progress=require(path.join(root,'BetterGenshinImpact/User/JsScript/ActOnePilot/field-progress.js'));
const gate=require(path.join(pilot,'world-inventory.js')).worldInventoryClosePermission;
const [session,frameText]=process.argv.slice(2),frame=Number(frameText),now=Date.now();
const read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const observation=n=>read(path.join(pilot,'observations',session,`frame-${String(n).padStart(4,'0')}.json`));
if(session!=='mvf3dvpn-3vemzlvktui'||!Number.isInteger(frame)||frame<=10)throw Error('Exact live lateral session/frame required');
const inventory=observation(frame),witness=observation(10),history=read(path.join(pilot,'field-progress-history.json'));
if(!gate(inventory,inventory.timestamp,session)||now-inventory.timestamp>600000)throw Error('Verified Inventory pause unavailable');
const review={kind:'windmill-wall-lateral-from-jamb',target:'broad stone wall left of door jamb',direction:'screen-left along stone course',session,scene:[
 {frameId:5,sha256:'1c7476564341096a84a8a23b4ec9620c1abf681e526fdbb327e6fdc5680d5b18'},
 {frameId:10,sha256:'a91338a1a61123316f47fc2ac5a433771206032b25b6d89b14576b7b39cf0186'}]};
for(const scene of review.scene){const png=path.join(pilot,'observations',session,`frame-${String(scene.frameId).padStart(4,'0')}.png`);if(crypto.createHash('sha256').update(fs.readFileSync(png)).digest('hex')!==scene.sha256)throw Error('Lateral scene hash changed');}
const plan={reviewed:true,session,frameId:frame,witnessFrameId:10,createdAt:now,mode:'actions',actions:[{type:'key',key:'VK_A',ms:200}],progressReview:review};
const request={session,expectedFrameId:frame,mission:'questStep',step:'actTwoField'};
if(!field.plan(plan,request,now)||field.originalWitnessFailure(witness,plan,request,now)||progress.rejection(history,plan,witness))throw Error('Field or ground-progress preflight rejected lateral plan');
const target=path.join(pilot,'act-two-field-request.json'),backup=path.join(root,'artifacts/release-r18/rollback-riddle-mount/previous-act-two-field-request.json');
if(fs.existsSync(backup))throw Error('Previous field-plan archive exists; inspect before replacement');
fs.copyFileSync(target,backup);
fs.writeFileSync(target,JSON.stringify(plan));
console.log(JSON.stringify({session,frame,witnessFrameId:10,action:'VK_A 200ms',oldPlanSha256:crypto.createHash('sha256').update(fs.readFileSync(backup)).digest('hex'),oneUse:true}));

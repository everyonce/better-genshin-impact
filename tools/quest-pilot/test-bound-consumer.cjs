const fs=require('node:fs'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'run-game-bound.js'),'utf8');
const wrapped=JSON.parse(fs.readFileSync(path.join(__dirname,'conpty-wrapped-result-fixture.json'),'utf8')).output;
const owner={session:'sample-one-r3',process_id:1234,windows_session_id:2,owner_lifetime_binding:'a'.repeat(64)};
async function scenario({change,held=false,transport='normal',durable='valid'}={}){
 const memory=new Map([['archonRelaySession',1],['archonBoundRuntime',{owner,python:'python',driver:'driver.py',config:'config.json',requestsDirectory:'D:\\fixture'}],['currentClan',{frameId:10}]]);
 if(held)memory.set('archonRelayHeld',{id:'prior'});
 let request,writes=0,dispatches=0,consumes=0,polls=0,ticks=0;
 const fakeDate={now:()=>{ticks+=30000;return 1000000+ticks;}};
 const tools={
  exec_command:async({cmd})=>{
   if(cmd.includes('[IO.FileMode]::CreateNew')){writes++;return {exit_code:0,output:''};}
   consumes++;
   if(durable==='missing'||durable==='delayed'&&consumes===1)return {exit_code:1,output:'exact result not yet available'};
   if(durable==='malformed')return {exit_code:0,output:'{not-json'};
   const value={id:request.id,boundResult:true,historicalRead:true,replayed:true,binding:'b'.repeat(64),boundRequest:request,owner,result:{session:owner.session,status:'completed',frameId:11,terminalId:'mission-'+'1'.repeat(32)}};
   if(change)change(value);
   return {exit_code:0,output:JSON.stringify(value)};
  },
  write_stdin:async({chars})=>{
   if(chars){dispatches++;request=JSON.parse(chars);}else polls++;
   if(transport==='throw')throw Error('transport connection lost');
   let output=JSON.stringify({relayDone:request.id,code:0,state:'settled',binding:'b'.repeat(64)})+'\n';
   if(transport==='wrapped')output=wrapped.replaceAll('r-transport-fixture-0001',request.id);
   if(transport==='split')output=chars?output.slice(0,24):output.slice(24);
   if(transport==='missing'||transport==='exited')output='';
   if(transport==='malformed')output='{"relayDone": ??? damaged';
   if(transport==='interleaved')output='unrelated\n{"relayDone":"stale-id","state":"settled"}\n'+output;
   return transport==='exited'?{exit_code:0,output}:{output};
  }
 };
 const run=new Function('tools','load','store','text','image','Date','return ('+source+');')(tools,k=>memory.get(k),(k,v)=>memory.set(k,v),()=>{},()=>{},fakeDate);
 let error;try{await run('observe --frame 10','fixture',{image:false});}catch(e){error=e;}
 return {memory,writes,dispatches,consumes,polls,error};
}
(async()=>{
 let count=0;
 for(const transport of ['normal','wrapped','split','missing','malformed','interleaved','exited','throw']){
  const ok=await scenario({transport});assert.equal(ok.error,undefined);assert.equal(ok.memory.get('currentClan').frameId,11);assert.equal(ok.memory.get('archonRelayHeld'),null);assert.equal(ok.dispatches,1);assert.equal(ok.consumes,1);count++;
 }
 const delayed=await scenario({transport:'missing',durable:'delayed'});assert.equal(delayed.error,undefined);assert.equal(delayed.consumes,2);assert.equal(delayed.dispatches,1);count++;
 for(const change of [v=>v.owner={...owner,owner_lifetime_binding:'c'.repeat(64)},v=>v.boundRequest={...v.boundRequest,frame:12},v=>v.binding='invalid',v=>v.historicalRead=false,v=>v.boundResult=false,v=>v.id='different-id',v=>v.result.session='different-session']){
  const bad=await scenario({change,transport:'missing'});assert.ok(bad.error);assert.equal(bad.memory.get('currentClan').frameId,10);assert.ok(bad.memory.get('archonRelayHeld'));assert.ok(bad.memory.get('archonRelayPending'));assert.equal(bad.dispatches,1);count++;
 }
 for(const options of [{transport:'missing',durable:'missing'},{transport:'exited',durable:'missing'},{transport:'normal',durable:'malformed'}]){
  const bad=await scenario(options);assert.ok(bad.error);assert.equal(bad.memory.get('currentClan').frameId,10);assert.ok(bad.memory.get('archonRelayHeld'));assert.ok(bad.memory.get('archonRelayPending'));assert.equal(bad.dispatches,1);assert.ok(bad.consumes<=24);count++;
 }
 const held=await scenario({held:true});assert.ok(held.error);assert.equal(held.writes,0);assert.equal(held.dispatches,0);count++;
 console.log(count+' injected caller scenarios passed: durable exact results survive absent/damaged/closed transport; unavailable or mismatched evidence stays held without replay.');
})().catch(e=>{console.error(e);process.exitCode=1;});

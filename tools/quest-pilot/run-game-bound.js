async (arg, why, opt = {}) => {
  if (load('archonRelayPending') || load('archonRelayHeld')) throw Error('A prior controller outcome is held; reconcile its original request before writing another action.');
  const qm = arg.match(/^questStep --step ([a-z][A-Za-z0-9]{0,39}) --frame (\d+)$/);
  const om = arg.match(/^observe --frame (\d+)$/);
  if (!qm && !om) throw Error('Only reviewed quest steps and observations use this bound relay.');
  const cfg = load('archonBoundRuntime'), sid = load('archonRelaySession');
  if (!cfg || !Number.isInteger(sid)) throw Error('The reviewed bound relay is not configured.');
  const id = 'r-' + Date.now() + '-' + Math.floor(Math.random() * 1000000);
  const request = qm ? {id, kind:'questStep', step:qm[1], frame:Number(qm[2])} : {id, kind:'observe', frame:Number(om[1])};
  const requestPath = cfg.requestsDirectory + '\\' + id + '.json';
  const quote = s => "'" + String(s).replaceAll("'", "''") + "'";
  const sameFlat = (a,b) => a && b && Object.keys(a).length === Object.keys(b).length && Object.keys(b).every(k => a[k] === b[k]);
  store('archonRelayPending', {request, requestPath, owner:cfg.owner});
  let settled = false;
  try {
    const script = '$archonCallerBytes=[Text.Encoding]::UTF8.GetBytes(' + quote(JSON.stringify(request)) + '); ' +
      '$archonCallerStream=[IO.File]::Open(' + quote(requestPath) + ',[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read); ' +
      'try {$archonCallerStream.Write($archonCallerBytes,0,$archonCallerBytes.Length); $archonCallerStream.Flush($true)} finally {$archonCallerStream.Dispose()}';
    const written = await tools.exec_command({cmd:script,max_output_tokens:120});
    if (written.exit_code !== 0) throw Error('The exact caller request was not saved; no relay dispatch was attempted.');
    let chunk;
    try {chunk=await tools.write_stdin({session_id:sid,chars:JSON.stringify(request)+'\n',yield_time_ms:1000,max_output_tokens:1800});}
    catch(error) {chunk={exit_code:1,output:String(error.message || error)};}
    // Durable exact binding is authoritative even if the PTY notice is missing or damaged.
    const deadline=Date.now()+120000;
    let consumed,saved;
    for(let reads=0;reads<24;reads++) {
      consumed=await tools.exec_command({cmd:'& '+quote(cfg.python)+' -B '+quote(cfg.driver)+' consume --config '+quote(cfg.config)+' --request-file '+quote(requestPath),max_output_tokens:10000});
      try {saved=JSON.parse(consumed.output.trim());} catch {saved=null;}
      if(consumed.exit_code===0) {
        if(!saved) throw Error('The durable result was malformed; retain the original request.');
        break;
      }
      if(chunk.exit_code!=null || Date.now()>=deadline || reads===23) throw Error('The exact durable result is unavailable; retain the original request without replay.');
      try {chunk=await tools.write_stdin({session_id:sid,chars:'',yield_time_ms:1000,max_output_tokens:1800});}
      catch(error) {chunk={exit_code:1,output:String(error.message || error)};}
    }
    if (consumed.exit_code !== 0 || saved.boundResult !== true || saved.historicalRead !== true || saved.replayed !== true ||
        saved.id !== id || !sameFlat(saved.boundRequest,request) || !sameFlat(saved.owner,cfg.owner) ||
        !/^[0-9a-f]{64}$/.test(saved.binding) || !saved.result || saved.result.session !== cfg.owner.session) {
      throw Error('The persisted result did not match the exact request and pinned controller owner.');
    }
    const result=saved.result;
    store('archonLastBoundProof',{id,binding:saved.binding,request,requestPath,owner:saved.owner,historicalRead:true,terminalId:result.terminalId,frame:result.frameId});
    store('currentClan',result);
    store('archonRelayPending',null);
    store('archonRelayHeld',null);
    settled=true;
    text({status:result.status,detail:result.result?.reason,frame:result.frameId,objective:result.hud?.objectives,hp:result.hud?.health});
    if(result.screenshot && opt.image!==false) image((await tools.view_image({path:result.screenshot})).image_url);
    return result;
  } catch(error) {
    if(!settled) store('archonRelayHeld',{id,requestPath,reason:String(error.message || error)});
    throw error;
  }
}

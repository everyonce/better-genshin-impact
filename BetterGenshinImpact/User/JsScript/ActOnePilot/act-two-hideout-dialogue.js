(function(root){
 'use strict';
 async function run(initial,api,observe){
  let current=initial,inputs=0;const labels=[];
  for(let page=0;page<2;page++){
   api.check();const target=api.target(current);
   if(!target||labels.includes(target.label))return {status:'stopped',reason:'Aerial tutorial unchanged or unknown; no replay',inputs,labels,pauseVerified:false};
   labels.push(target.label);
   const result=await api.advance(current,observe);inputs+=result.inputs||0;
   if(result.pauseVerified)return Object.assign({},result,{inputs,labels,handoff:'hideout_aerial_tutorials'});
   if(result.reason!=='Next aerial tutorial page; inspect before continuing')return Object.assign({},result,{inputs,labels});
   current=await observe();
  }
  return {status:'stopped',reason:'Aerial tutorial page bound reached',inputs,labels,pauseVerified:false};
 }
 root.ActTwoHideoutDialogue={run};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoHideoutDialogue;
})(typeof globalThis!=='undefined'?globalThis:this);

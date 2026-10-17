(function(root){
'use strict';
function labels(rows,level){const found=[];for(const r of rows||[]){if(!r||!new RegExp('^Lv[.,]?\\s*'+level+'$').test(String(r.text).trim())||![r.x,r.y,r.width,r.height].every(Number.isFinite)||r.x<350||r.x>1600||r.y<100||r.y>850||r.width<20||r.width>130||r.height<10||r.height>45)continue;if(!found.some(v=>Math.abs(v.x-r.x)<10&&Math.abs(v.y-r.y)<10))found.push(r);}return found;}
function classify(label,red,gold){
 const bars=(red||[]).filter(b=>b.width>=20&&b.width<=250&&b.height>=3&&b.height<=12&&b.rectangularity>=.75&&Math.abs(b.x-label.x-label.width/2)<=35&&b.y-label.y-label.height>=-5&&b.y-label.y-label.height<=25);
 if(bars.length!==1)return {phase:'unknown',reason:'target_bar_missing_or_ambiguous',target:null,shield:null};
 const target=bars[0],shields=(gold||[]).filter(b=>b.width>=20&&b.width<=target.width*1.35&&b.height>=2&&b.height<=9&&b.rectangularity>=.75&&Math.abs(b.x-target.x)<=35&&b.y-target.y>=5&&b.y-target.y<=20);
 return {phase:shields.length===1?'charging-shield':'unknown',reason:shields.length===1?'same_capture_orange_bar_below_anchored_health':'absence_of_shield_does_not_prove_stun',target:target,shield:shields.length===1?shields[0]:null};
}
function read(img,cv,rows,level){
 const candidates=labels(rows,level);if(candidates.length!==1)return {phase:'unknown',reason:'exact_level_label_missing_or_ambiguous',target:null,shield:null,level:level};
 const label=candidates[0],x=Math.max(0,Math.round(label.x+label.width/2-150)),y=Math.max(0,Math.round(label.y+label.height-5));let crop=null,red=null,gold=null;
 function boxes(mask){const cs=mask.findContoursAsArray(cv.RetrievalModes.External,cv.ContourApproximationModes.ApproxSimple),out=[];for(let i=0;i<cs.length;i++){const b=cv.Cv2.boundingRect(cs[i]),w=Number(b.width),h=Number(b.height);out.push({x:x+Number(b.x)+w/2,y:y+Number(b.y)+h/2,width:w,height:h,rectangularity:Number(cv.Cv2.contourArea(cs[i],false))/Math.max(1,(w-1)*(h-1))});}return out;}
 try{crop=img.deriveCrop(x,y,300,45);red=crop.srcMat.inRange(new cv.Scalar(75,75,230),new cv.Scalar(110,110,255));gold=crop.srcMat.inRange(new cv.Scalar(95,145,240),new cv.Scalar(140,220,255));return Object.assign(classify(label,boxes(red),boxes(gold)),{level:level,label:label,crop:[x,y,300,45]});}
 finally{if(gold)gold.dispose();if(red)red.dispose();if(crop)crop.dispose();}
}
const api={labels,classify,read};root.CombatTargetState=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);

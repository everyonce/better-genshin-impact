(function(root){
 'use strict';
 function shape(pixels,boxes){
  if(!Number.isFinite(pixels)||pixels<=0||pixels>800||!boxes.length||boxes.length>3)return false;
  const left=Math.min(...boxes.map(b=>b.x)),top=Math.min(...boxes.map(b=>b.y)),right=Math.max(...boxes.map(b=>b.x+b.width)),bottom=Math.max(...boxes.map(b=>b.y+b.height));
  return left>=20&&right<=210&&top>=0&&bottom<=190&&right-left<=30&&bottom-top>=30&&bottom-top<=130;
 }
 function substantialBoxes(boxes){return Array.isArray(boxes)?boxes.filter(b=>b&&Number.isFinite(b.x)&&Number.isFinite(b.y)&&Number.isFinite(b.width)&&Number.isFinite(b.height)&&b.width>0&&b.height>0&&b.width*b.height>=21):[];}
 function read(img,cv){
  let crop=null,hsv=null,mask=null;
  try{
   crop=img.deriveCrop(1000,430,220,200);
   hsv=crop.srcMat.cvtColor(cv.ColorConversionCodes.BGR2HSV,0);
   mask=hsv.inRange(new cv.Scalar(18,190,150),new cv.Scalar(28,255,255));
   const pixels=Number(cv.Cv2.countNonZero(mask));
   const contours=mask.findContoursAsArray(cv.RetrievalModes.External,cv.ContourApproximationModes.ApproxSimple),boxes=[];
   for(let i=0;i<contours.length;i++){const b=cv.Cv2.boundingRect(contours[i]);boxes.push({x:Number(b.x),y:Number(b.y),width:Number(b.width),height:Number(b.height)});}
   const dominant=substantialBoxes(boxes);
   return {pixels:shape(pixels,dominant)?pixels:null,rawPixels:pixels,boxes:dominant,source:'same-frame-yellow-arc',rect:[1000,430,220,200]};
  }finally{if(mask)mask.dispose();if(hsv)hsv.dispose();if(crop)crop.dispose();}
 }
 function wall(o){const m=o&&o.map,h=o&&o.hud,hp=h&&h.health;return !!(m&&m.map==='Teyvat'&&(Math.hypot(m.x+1368.7461,m.y-1671.1387)<=6||Math.hypot(m.x+1341.7891,m.y-1680.3379)<=3||Math.hypot(m.x+1313.8145,m.y-1667.4736)<=6)&&h&&hp&&hp.max===4015&&hp.current>=hp.max*.9&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='Gototheexampoint'));}
 function enough(o){const s=o&&o.hud&&o.hud.climbStamina;return !!(s&&s.source==='same-frame-yellow-arc'&&Number.isFinite(s.pixels)&&s.pixels>=180&&s.boxes&&Math.max(...s.boxes.map(b=>b.y+b.height))-Math.min(...s.boxes.map(b=>b.y))>=45);}
 function classify(s){
  if(!s||s.source!=='same-frame-yellow-arc'||!Array.isArray(s.boxes)||!Number.isFinite(s.rawPixels))return {kind:'unknown',pixels:null,height:null};
  if(s.rawPixels===0&&s.boxes.length===0)return {kind:'absent',pixels:null,height:null};
  const boxes=substantialBoxes(s.boxes),pixels=s.rawPixels;
  if(!shape(pixels,boxes))return {kind:'occluded-or-ambiguous',pixels:null,height:null};
  const height=Math.max(...boxes.map(b=>b.y+b.height))-Math.min(...boxes.map(b=>b.y));
  if(height<45||pixels<180)return {kind:'low',pixels,height};
  return {kind:'usable',pixels,height};
 }
 const api={read,wall,enough,shape,classify};root.ActTwoClimbStamina=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);

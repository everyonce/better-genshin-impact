(function(root){
 'use strict';
 function shape(pixels,boxes){
  if(!Number.isFinite(pixels)||pixels<=0||pixels>800||!boxes.length||boxes.length>3)return false;
  const left=Math.min(...boxes.map(b=>b.x)),top=Math.min(...boxes.map(b=>b.y)),right=Math.max(...boxes.map(b=>b.x+b.width)),bottom=Math.max(...boxes.map(b=>b.y+b.height));
  return left>=20&&right<=210&&top>=0&&bottom<=190&&right-left<=30&&bottom-top>=30&&bottom-top<=130;
 }
 function read(img,cv){
  let crop=null,mask=null;
  try{
   crop=img.deriveCrop(1000,430,220,200);
   mask=crop.srcMat.inRange(new cv.Scalar(0,180,250),new cv.Scalar(25,205,255));
   const pixels=Number(cv.Cv2.countNonZero(mask));
   const contours=mask.findContoursAsArray(cv.RetrievalModes.External,cv.ContourApproximationModes.ApproxSimple),boxes=[];
   for(let i=0;i<contours.length;i++){const b=cv.Cv2.boundingRect(contours[i]);boxes.push({x:Number(b.x),y:Number(b.y),width:Number(b.width),height:Number(b.height)});}
   return {pixels:shape(pixels,boxes)?pixels:null,rawPixels:pixels,boxes,source:'same-frame-yellow-arc',rect:[1000,430,220,200]};
  }finally{if(mask)mask.dispose();if(crop)crop.dispose();}
 }
 function wall(o){const m=o&&o.map,h=o&&o.hud,hp=h&&h.health;return !!(m&&m.map==='Teyvat'&&(Math.hypot(m.x+1368.7461,m.y-1671.1387)<=6||Math.hypot(m.x+1341.7891,m.y-1680.3379)<=3)&&h&&hp&&hp.max===4015&&hp.current>=hp.max*.9&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='Gototheexampoint'));}
 function enough(o){const s=o&&o.hud&&o.hud.climbStamina;return !!(s&&s.source==='same-frame-yellow-arc'&&Number.isFinite(s.pixels)&&s.pixels>=180&&s.boxes&&Math.max(...s.boxes.map(b=>b.y+b.height))-Math.min(...s.boxes.map(b=>b.y))>=45);}
 const api={read,wall,enough,shape};root.ActTwoClimbStamina=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);

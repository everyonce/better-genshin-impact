(function(root){
 'use strict';
 function classify(boxes,coreBoxes){
  const near=(boxes||[]).filter(b=>[b.x,b.y,b.width,b.height,b.area].every(Number.isFinite)&&b.x>=600&&b.x+b.width<=1500&&b.y>=250&&b.y+b.height<=800&&b.width>=140&&b.width<=350&&b.height>=140&&b.height<=350&&b.area>=2000&&b.area/(b.width*b.height)>=.18);
  const cores=(coreBoxes||[]).filter(b=>[b.x,b.y,b.width,b.height,b.area].every(Number.isFinite)&&b.x>=600&&b.x+b.width<=1500&&b.y>=180&&b.y+b.height<=750&&b.width>=150&&b.width<=400&&b.height>=150&&b.height<=400&&b.area>=5000&&b.area/(b.width*b.height)>=.25);
  return {nearBodyWarning:near.length===1||cores.length===1,ambiguous:near.length>1||cores.length>1,candidates:near,coreCandidates:cores,phase:'unclassified',limitation:'Teal body proximity, not proof of a specific attack or a safe absence.'};
 }
 function read(img,cv){
  let crop=null,hsv=null,mask=null,coreMask=null;const boxes=[],coreBoxes=[];
  try{
   crop=img.deriveCrop(350,100,1250,750);hsv=crop.srcMat.cvtColor(cv.ColorConversionCodes.BGR2HSV,0);mask=hsv.inRange(new cv.Scalar(80,90,40),new cv.Scalar(115,255,210));
   const contours=mask.findContoursAsArray(cv.RetrievalModes.External,cv.ContourApproximationModes.ApproxSimple);
   for(let i=0;i<contours.length;i++){const b=cv.Cv2.boundingRect(contours[i]),area=Number(cv.Cv2.contourArea(contours[i],false));if(Number(b.width)>=70&&Number(b.height)>=70&&area>=1500)boxes.push({x:350+Number(b.x),y:100+Number(b.y),width:Number(b.width),height:Number(b.height),area});}
   coreMask=hsv.inRange(new cv.Scalar(45,30,230),new cv.Scalar(100,255,255));const coreContours=coreMask.findContoursAsArray(cv.RetrievalModes.External,cv.ContourApproximationModes.ApproxSimple);
   for(let i=0;i<coreContours.length;i++){const b=cv.Cv2.boundingRect(coreContours[i]),area=Number(cv.Cv2.contourArea(coreContours[i],false));if(Number(b.width)>=70&&Number(b.height)>=70&&area>=1500)coreBoxes.push({x:350+Number(b.x),y:100+Number(b.y),width:Number(b.width),height:Number(b.height),area});}
   return Object.assign(classify(boxes,coreBoxes),{source:'same-frame-eye-teal-and-bright-core-contours',boxes,coreBoxes});
  }finally{if(coreMask)coreMask.dispose();if(mask)mask.dispose();if(hsv)hsv.dispose();if(crop)crop.dispose();}
 }
 root.ActTwoEyeThreat={classify,read};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoEyeThreat;
})(typeof globalThis!=='undefined'?globalThis:this);

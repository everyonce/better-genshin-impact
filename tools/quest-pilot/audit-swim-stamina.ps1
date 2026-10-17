param([string]$RuntimeDirectory='artifacts/release-r18/BetterGI-English-win-x64',[string]$Session='mvcuzen8-drrh7eb3gqe',[int[]]$Frames=@(615,644,722,729))
$ErrorActionPreference='Stop'
$runtime=(Resolve-Path -LiteralPath $RuntimeDirectory).Path
$env:PATH="$runtime;$env:PATH"
Add-Type -Path (Join-Path $runtime 'OpenCvSharp.dll')
Add-Type -CompilerOptions '/nowarn:1701' -ReferencedAssemblies (Join-Path $runtime 'OpenCvSharp.dll') -TypeDefinition @"
using OpenCvSharp;
using System.Collections.Generic;
public static class SwimStaminaImageAudit {
 public static int[][] Scan(string path,int x,int y,int width,int height,bool broad) {
  using(var src=Cv2.ImRead(path)) using(var crop=new Mat(src,new Rect(x,y,width,height))) using(var hsv=new Mat()) using(var mask=new Mat()) {
   Cv2.CvtColor(crop,hsv,ColorConversionCodes.BGR2HSV);
   Cv2.InRange(hsv,broad?new Scalar(12,100,100):new Scalar(18,190,150),broad?new Scalar(36,255,255):new Scalar(28,255,255),mask);
   var pixels=Cv2.CountNonZero(mask);
   Point[][] contours;HierarchyIndex[] hierarchy;Cv2.FindContours(mask,out contours,out hierarchy,RetrievalModes.External,ContourApproximationModes.ApproxSimple);
   var result=new int[contours.Length+1][];result[0]=new int[]{pixels};for(int i=0;i<contours.Length;i++){var b=Cv2.BoundingRect(contours[i]);result[i+1]=new int[]{b.X+x,b.Y+y,b.Width,b.Height};}
   return result;
  }
 }
}
"@
$rows=foreach($frame in $Frames){
 $image=Join-Path $runtime ("User/JsScript/ActOnePilot/observations/{0}/frame-{1:d4}.png" -f $Session,$frame)
 $regions=foreach($r in @(@('swimCrop',1060,560,80,180),@('centralSearch',800,350,500,630))){
  $strict=[SwimStaminaImageAudit]::Scan($image,$r[1],$r[2],$r[3],$r[4],$false)
  $broad=[SwimStaminaImageAudit]::Scan($image,$r[1],$r[2],$r[3],$r[4],$true)
  [pscustomobject]@{region=$r[0];strictPixels=$strict[0][0];strictBoxes=@($strict|Select-Object -Skip 1);broadPixels=$broad[0][0];broadBoxes=@($broad|Select-Object -Skip 1)}
 }
 [pscustomobject]@{frame=$frame;sha256=(Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash;regions=$regions}
}
[pscustomobject]@{session=$Session;method='Read-only native OpenCvSharp replay using the live runtime assembly. No source images modified.';frames=$rows}|ConvertTo-Json -Depth 8

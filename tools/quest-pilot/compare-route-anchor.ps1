param(
 [Parameter(Mandatory)][string]$RuntimeDirectory,
 [Parameter(Mandatory)][string]$ReferenceImage,
 [Parameter(Mandatory)][string]$CandidateImage,
 [Parameter(Mandatory)][double]$ReferenceHeading,
 [Parameter(Mandatory)][double]$CandidateHeading
)
# Offline evidence review only. This script never captures or sends game input.
$ErrorActionPreference='Stop'
$runtime=(Resolve-Path -LiteralPath $RuntimeDirectory).Path
$reference=(Resolve-Path -LiteralPath $ReferenceImage).Path
$candidate=(Resolve-Path -LiteralPath $CandidateImage).Path
$env:PATH="$runtime;$env:PATH"
Add-Type -Path (Join-Path $runtime 'OpenCvSharp.dll')
[OpenCvSharp.Cv2]::SetNumThreads(1)
Add-Type -CompilerOptions '/nowarn:1701' -ReferencedAssemblies @((Join-Path $runtime 'OpenCvSharp.dll'),'System.Linq','System.Collections') -TypeDefinition @'
using System;
using System.Linq;
using OpenCvSharp;
public static class RouteAnchorComparison {
 public static double[] Compare(string first,string second) {
  using(var a0=Cv2.ImRead(first,ImreadModes.Grayscale))
  using(var b0=Cv2.ImRead(second,ImreadModes.Grayscale))
  using(var a=new Mat()) using(var b=new Mat())
  using(var mask=new Mat(540,960,MatType.CV_8UC1,Scalar.All(0)))
  using(var da=new Mat()) using(var db=new Mat())
  using(var orb=ORB.Create(2500))
  using(var matcher=new BFMatcher(NormTypes.Hamming)) {
   if(a0.Empty()||b0.Empty()||Math.Abs(a0.Width/(double)a0.Height-16.0/9)>0.01||Math.Abs(b0.Width/(double)b0.Height-16.0/9)>0.01)
    throw new ArgumentException("Two complete 16:9 recorded frames required; crops cannot establish a full-scene anchor");
   Cv2.Resize(a0,a,new Size(960,540)); Cv2.Resize(b0,b,new Size(960,540));
   // Exclude HUD, quest text, party portraits, and the player body.
   Cv2.Rectangle(mask,new Rect(200,65,580,405),Scalar.All(255),-1);
   Cv2.Rectangle(mask,new Rect(375,175,200,295),Scalar.All(0),-1);
   KeyPoint[] ka,kb; orb.DetectAndCompute(a,mask,out ka,da);orb.DetectAndCompute(b,mask,out kb,db);
   if(da.Empty()||db.Empty()) return new double[]{ka.Length,kb.Length,0,0,0,999,999};
   var good=matcher.KnnMatch(da,db,2).Where(x=>x.Length==2&&x[0].Distance<0.7*x[1].Distance).Select(x=>x[0]).ToArray();
   if(good.Length<8) return new double[]{ka.Length,kb.Length,good.Length,0,0,999,999};
   var pa=good.Select(x=>new Point2d(ka[x.QueryIdx].Pt.X,ka[x.QueryIdx].Pt.Y)).ToArray();
   var pb=good.Select(x=>new Point2d(kb[x.TrainIdx].Pt.X,kb[x.TrainIdx].Pt.Y)).ToArray();
   using(var inliers=new Mat()) using(var h=Cv2.FindHomography(pa,pb,HomographyMethods.Ransac,3,inliers,2000,0.995)) {
    int count=inliers.Empty()?0:Cv2.CountNonZero(inliers);
    if(h.Empty())return new double[]{ka.Length,kb.Length,good.Length,count,0,999,999};
    double maxShift=0,minX=960,maxX=0,minY=540,maxY=0;
    for(int i=0;i<pa.Length;i++)if(inliers.At<byte>(i,0)!=0){minX=Math.Min(minX,pa[i].X);maxX=Math.Max(maxX,pa[i].X);minY=Math.Min(minY,pa[i].Y);maxY=Math.Max(maxY,pa[i].Y);}
    foreach(var p in new[]{new Point2d(250,100),new Point2d(700,100),new Point2d(250,430),new Point2d(700,430)}) {
     double w=h.At<double>(2,0)*p.X+h.At<double>(2,1)*p.Y+h.At<double>(2,2);
     if(Math.Abs(w)<1e-8){maxShift=999;break;}
     double x=(h.At<double>(0,0)*p.X+h.At<double>(0,1)*p.Y+h.At<double>(0,2))/w;
     double y=(h.At<double>(1,0)*p.X+h.At<double>(1,1)*p.Y+h.At<double>(1,2))/w;
     maxShift=Math.Max(maxShift,Math.Sqrt(Math.Pow((x-p.X)/960,2)+Math.Pow((y-p.Y)/540,2)));
    }
    return new double[]{ka.Length,kb.Length,good.Length,count,count/(double)good.Length,maxShift,Math.Min((maxX-minX)/960,(maxY-minY)/540)};
   }
  }
 }
}
'@
$metrics=[RouteAnchorComparison]::Compare($reference,$candidate)
$delta=[Math]::Abs(($CandidateHeading-$ReferenceHeading+540)%360-180)
$aligned=$delta -le 8 -and $metrics[3] -ge 20 -and $metrics[4] -ge 0.6 -and $metrics[5] -le 0.08 -and $metrics[6] -ge 0.2
[pscustomobject]@{
 method='offline-ORB-terrain-homography';reference=$ReferenceImage;candidate=$CandidateImage
 referenceSha256=(Get-FileHash -LiteralPath $reference -Algorithm SHA256).Hash
 candidateSha256=(Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash
 headingDelta=$delta;referenceFeatures=$metrics[0];candidateFeatures=$metrics[1]
 matches=$metrics[2];inliers=$metrics[3];inlierRatio=$metrics[4]
 maximumNormalizedCornerShift=$metrics[5];minimumInlierSpan=$metrics[6]
 anchorAligned=$aligned;gameplayAuthorized=$false
 limitation='A matching saved frame is review evidence only. Missing upper-landing images cannot be reconstructed from distance or headings. No live route validation.'
}|ConvertTo-Json -Depth 3 -Compress
# This is a standalone CLI, not a dot-sourced library. Native OpenCV worker
# teardown can keep pwsh alive after all Mats have been disposed and output
# emitted; finish this read-only helper explicitly, without touching BetterGI.
[Console]::Out.Flush()
[Environment]::Exit(0)

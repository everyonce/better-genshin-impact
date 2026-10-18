param([string]$RuntimeDirectory='artifacts/release-r18/BetterGI-English-win-x64',[string]$Session='mvcuzen8-drrh7eb3gqe',[switch]$BigMap,[int[]]$FrameIds)
$ErrorActionPreference='Stop'
$runtime=(Resolve-Path -LiteralPath $RuntimeDirectory).Path
$env:PATH="$runtime;$env:PATH"
Add-Type -Path (Join-Path $runtime 'OpenCvSharp.dll')
Add-Type -CompilerOptions '/nowarn:1701' -ReferencedAssemblies @((Join-Path $runtime 'OpenCvSharp.dll'),'System.Linq','System.Collections') -TypeDefinition @'
using OpenCvSharp.Features2D; using System; using System.IO; using System.Linq; using System.Collections.Generic; using OpenCvSharp;
public sealed class SpringvaleSiftAudit : IDisposable {
 readonly Mat descriptors; readonly KeyPoint[] keys; readonly bool big;
 public int TrainingPoints {get {return keys.Length;}}
 public SpringvaleSiftAudit(string directory,bool bigMap) {
  big=bigMap;string stem=big?"Teyvat_0_256_SIFT":"Teyvat_0_2048_SIFT";
  var selected=new List<KeyPoint>();var indices=new List<int>();
  // Exact 3x3 cells surrounding tp5 in the repository's2048-map coordinate system.
  using(var reader=new BinaryReader(File.OpenRead(Path.Combine(directory,stem+".kp.bin")))) {
   int i=0;while(reader.BaseStream.Position<reader.BaseStream.Length){float x=reader.ReadSingle(),y=reader.ReadSingle(),size=reader.ReadSingle(),angle=reader.ReadSingle(),response=reader.ReadSingle();int octave=reader.ReadInt32(),id=reader.ReadInt32();
    if(big||(x>=32768&&x<35840&&y>=19456&&y<22528)){selected.Add(new KeyPoint(x,y,size,angle,response,octave,id));indices.Add(i);}i++;
   }
  }
  keys=selected.ToArray();descriptors=new Mat(keys.Length,128,MatType.CV_32FC1);
  using(var source=Cv2.ImRead(Path.Combine(directory,stem+".mat.png"),ImreadModes.Grayscale)) {
   if(source.Cols!=128)throw new Exception("Unexpected training descriptor width");
   for(int i=0;i<indices.Count;i++)using(var row=source.Row(indices[i]))using(var dest=descriptors.Row(i)){row.ConvertTo(dest,MatType.CV_32FC1);}
  }
 }
 public object Run(string path,string variant,double scale) {
  if(!new[]{.25,.75,1.0,1.25}.Contains(scale))throw new ArgumentException("Diagnostic scale outside fixed bounds");
  using(var full=Cv2.ImRead(path))using(var crop=new Mat(full,big?new Rect(0,0,full.Width,full.Height):new Rect(62,19,212,212)))using(var query=new Mat())using(var mask=new Mat())using(var sift=SIFT.Create())using(var qDesc=new Mat())using(var matcher=new BFMatcher(NormTypes.L2)) {
   Cv2.Resize(crop,query,new Size(),scale,scale);
   if(variant=="terrain") {mask.Create(query.Rows,query.Cols,MatType.CV_8UC1);mask.SetTo(Scalar.Black);double center=query.Width/2.0;
    for(int y=0;y<query.Rows;y++)for(int x=0;x<query.Cols;x++){var b=query.At<Vec3b>(y,x);int hi=Math.Max(b.Item0,Math.Max(b.Item1,b.Item2)),lo=Math.Min(b.Item0,Math.Min(b.Item1,b.Item2));double d=Math.Sqrt((x-center)*(x-center)+(y-center)*(y-center));if(d<96*scale&&d>23*scale&&hi>55&&hi-lo>20)mask.Set(y,x,(byte)255);}
   }
   KeyPoint[] qKeys;sift.DetectAndCompute(query,mask.Empty()?null:mask,out qKeys,qDesc);
   if(qDesc.Empty())return new {variant,scale,queryPoints=qKeys.Length,good=0,inliers=0,position=(object)null};
   var good=matcher.KnnMatch(qDesc,descriptors,2).Where(m=>m.Length==2&&m[0].Distance<.75*m[1].Distance).Select(m=>m[0]).ToList();
   if(good.Count<7)return new {variant,scale,queryPoints=qKeys.Length,good=good.Count,inliers=0,position=(object)null};
   var a=good.Select(m=>new Point2d(qKeys[m.QueryIdx].Pt.X,qKeys[m.QueryIdx].Pt.Y)).ToList();var b2=good.Select(m=>new Point2d(keys[m.TrainIdx].Pt.X,keys[m.TrainIdx].Pt.Y)).ToList();
   using(var inlier=new Mat())using(var homography=Cv2.FindHomography(a,b2,HomographyMethods.Ransac,3,inlier)) {
    if(homography.Empty())return new {variant,scale,queryPoints=qKeys.Length,good=good.Count,inliers=0,position=(object)null};
    var inlierPoints=good.Select((m,i)=>new {m,i}).Where(v=>inlier.At<byte>(v.i,0)>0).Select(v=>qKeys[v.m.QueryIdx].Pt).ToArray();
    var spreadX=inlierPoints.Length>0?(inlierPoints.Max(v=>v.X)-inlierPoints.Min(v=>v.X))/query.Cols:0;var spreadY=inlierPoints.Length>0?(inlierPoints.Max(v=>v.Y)-inlierPoints.Min(v=>v.Y))/query.Rows:0;
    var c=Cv2.PerspectiveTransform(new[]{new Point2f(query.Cols/2f,query.Rows/2f)},homography)[0];
    return new {variant,scale,queryPoints=qKeys.Length,good=good.Count,inliers=Cv2.CountNonZero(inlier),spreadX,spreadY,position=new {x=big?(4096-c.X)*4:(32768-c.X)/2,y=big?(3072-c.Y)*4:(24576-c.Y)/2},scaleX=homography.At<double>(0,0),scaleY=homography.At<double>(1,1)};
   }
  }
 }
 public void Dispose(){descriptors.Dispose();}
}
'@
$loadTimer=[Diagnostics.Stopwatch]::StartNew()
$audit=[SpringvaleSiftAudit]::new((Join-Path $runtime 'Assets/Map/Teyvat'),$BigMap.IsPresent)
$loadMs=$loadTimer.ElapsedMilliseconds
try {
 $ids=if($FrameIds){if($FrameIds.Count -gt 4){throw "At most four recorded frames"};$FrameIds}elseif($BigMap){@(7263,7292,7323,7198)}else{@(7277,7333,7357)}
 $rows=foreach($id in $ids) {
  $path=Join-Path $runtime ('User/JsScript/ActOnePilot/observations/{0}/frame-{1:d4}.png' -f $Session,$id)
  if(!(Test-Path -LiteralPath $path)){[pscustomobject]@{frame=$id;missing=$true};continue}
  $trials=if($BigMap){@([pscustomobject]@{variant='raw';scale=0.25})}else{@([pscustomobject]@{variant='raw';scale=1.0},[pscustomobject]@{variant='raw';scale=0.75},[pscustomobject]@{variant='raw';scale=1.25},[pscustomobject]@{variant='terrain';scale=1.0})}
  foreach($trial in $trials) {
   $timer=[Diagnostics.Stopwatch]::StartNew();$matched=$audit.Run($path,$trial.variant,$trial.scale)
   [pscustomobject]@{frame=$id;sha256=(Get-FileHash -LiteralPath $path).Hash;elapsedMs=$timer.ElapsedMilliseconds;result=$matched}
  }
 }
 [pscustomobject]@{method='Read-only native OpenCvSharp SIFT/BF KNN2, ratio0.75 and7matches; minimap62,19,212,212 or full-map quarter scale; diagnostic only';bigMap=$BigMap.IsPresent;loadMs=$loadMs;trainingRegion=$(if($BigMap){@(0,0,5632,4864)}else{@(32768,19456,3072,3072)});trainingPoints=$audit.TrainingPoints;rows=@($rows)}|ConvertTo-Json -Depth 7
} finally {$audit.Dispose()}

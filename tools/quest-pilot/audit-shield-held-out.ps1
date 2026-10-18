param([string]$RuntimeDirectory='artifacts/release-r18/BetterGI-English-win-x64',[string]$Session='mvcuzen8-drrh7eb3gqe')
$ErrorActionPreference='Stop'
$runtime=(Resolve-Path -LiteralPath $RuntimeDirectory).Path
$env:PATH="$runtime;$env:PATH"
Add-Type -Path (Join-Path $runtime 'OpenCvSharp.dll')
Add-Type -CompilerOptions '/nowarn:1701' -ReferencedAssemblies (Join-Path $runtime 'OpenCvSharp.dll') -TypeDefinition @"
using OpenCvSharp;
public static class ShieldHeldOutAudit {
 public static double[] Best(string path,string template,double scale) {
  using(var src=Cv2.ImRead(path)) using(var crop=new Mat(src,new Rect(200,280,1350,550))) using(var original=Cv2.ImRead(template)) using(var resized=new Mat()) using(var scores=new Mat()) {
   Cv2.Resize(original,resized,new Size((int)System.Math.Round(original.Width*scale),(int)System.Math.Round(original.Height*scale)));
   Cv2.MatchTemplate(crop,resized,scores,TemplateMatchModes.CCoeffNormed);
   double low,high;Point min,max;Cv2.MinMaxLoc(scores,out low,out high,out min,out max);
   return new double[]{high,max.X+200,max.Y+280,resized.Width,resized.Height};
  }
 }
}
"@
$ids=@(260065732,260065782,260065851,260065852,260066991,260066992,260067042,260067043,260067092,260067093,260067142,260067143,260067272)
$rows=foreach($id in $ids){
 $path=Join-Path $runtime ("User/JsScript/ActOnePilot/observations/{0}/frame-{1}.png" -f $Session,$id)
 if(!(Test-Path -LiteralPath $path)){[pscustomobject]@{frame=$id;missing=$true};continue}
 $trials=foreach($name in @('wood-shield-ranged','wood-shield-frontal-face')){
  $scales=if($name -eq 'wood-shield-ranged'){@(.75,1,1.25)}else{@(.8,.9,1,1.1,1.2,1.3,1.4)}
  foreach($scale in $scales){$m=[ShieldHeldOutAudit]::Best($path,(Join-Path $runtime "User/JsScript/ActOnePilot/assets/$name.png"),$scale);[pscustomobject]@{template=$name;scale=$scale;score=$m[0];rect=@($m[1],$m[2],$m[3],$m[4])}}
 }
 [pscustomobject]@{frame=$id;sha256=(Get-FileHash -LiteralPath $path).Hash;best=($trials|Sort-Object score -Descending|Select-Object -First 1);thresholdPasses=@($trials|Where-Object {$_.score -ge .9})}
}
[pscustomobject]@{session=$Session;method='Read-only native OpenCvSharp CCoeffNormed, color, active aim templates/scales/ROI, threshold0.90 unchanged. Peak scores only; this is not full controller/live-input validation.';frames=@($rows)}|ConvertTo-Json -Depth 8

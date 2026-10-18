param([Parameter(Mandatory)][string]$RuntimeDirectory,[Parameter(Mandatory)][string]$Session,[Parameter(Mandatory)][int]$FromFrame,[Parameter(Mandatory)][int]$ToFrame)
$ErrorActionPreference='Stop'
$runtime=(Resolve-Path -LiteralPath $RuntimeDirectory).Path
$env:PATH="$runtime;$env:PATH"
Add-Type -Path (Join-Path $runtime 'OpenCvSharp.dll')
# Replay the repository's existing GIA camera algorithm on retained images.
$source=Get-Content (Join-Path $PSScriptRoot '../../BetterGenshinImpact/GameTask/Common/Map/Camera/CameraOrientationFromGia.cs') -Raw
$source=$source.Replace('using BetterGenshinImpact.GameTask.Model.Area;','').Replace('using System.Drawing;','')
$start=$source.IndexOf('    public static void DrawDirection(')
$end=$source.IndexOf('    static List<int> FindPeaks', $start)
if($start -lt 0 -or $end -le $start){throw 'Camera source layout changed'}
$source=$source.Remove($start,$end-$start)
Add-Type -CompilerOptions '/nowarn:1701' -ReferencedAssemblies @((Join-Path $runtime 'OpenCvSharp.dll'),'System.Linq','System.Collections') -TypeDefinition $source
$frames=foreach($frame in @($FromFrame,$ToFrame)){
 $path=Join-Path $runtime ('User/JsScript/ActOnePilot/observations/{0}/frame-{1:d4}.png' -f $Session,$frame)
 $mat=[OpenCvSharp.Cv2]::ImRead($path)
 try {
  if($mat.Width -ne 1920 -or $mat.Height -ne 1080){throw 'Camera replay requires the validated capture size'}
  $crop=[OpenCvSharp.Mat]::new($mat,[OpenCvSharp.Rect]::new(62,19,212,212))
  try { [pscustomobject]@{frame=$frame;angle=[BetterGenshinImpact.GameTask.Common.Map.Camera.CameraOrientationFromGia]::ComputeMiniMap($crop);sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash} } finally {$crop.Dispose()}
 } finally {$mat.Dispose()}
}
[pscustomobject]@{method='native-GIA-saved-image';session=$Session;frames=@($frames)}|ConvertTo-Json -Depth 4 -Compress

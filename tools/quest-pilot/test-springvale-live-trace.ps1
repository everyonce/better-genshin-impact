param(
    [Parameter(Mandatory)][string]$Runtime,
    [Parameter(Mandatory)][string]$AssemblyPath,
    [Parameter(Mandatory)][string]$Receipt,
    [ValidateSet('trace','beforeTrace','afterTrace')][string]$Part='trace'
)
$ErrorActionPreference='Stop'
$runtime=(Resolve-Path -LiteralPath $Runtime).Path
$assembly=(Resolve-Path -LiteralPath $AssemblyPath).Path
$record=Get-Content -LiteralPath (Resolve-Path -LiteralPath $Receipt).Path -Raw | ConvertFrom-Json
$live=$record.details.result.$Part
if(!$live -or $live.layer -ne 'MapBack_2' -or @($live.crop).Count -ne 4){throw 'Missing exact live trace or unexpected map layer'}
$root=[IO.Path]::GetFullPath((Join-Path $runtime 'User/JsScript/ActOnePilot/diagnostics')).TrimEnd('\')+'\'
$path=[IO.Path]::GetFullPath($live.cropPath)
if(!$path.StartsWith($root,[StringComparison]::OrdinalIgnoreCase)){throw 'Trace PNG is outside this runtime'}
$item=Get-Item -LiteralPath $path
if($item.Length -le 0 -or $item.Length -gt 1MB){throw 'Trace PNG size invalid'}
$env:PATH="$runtime;$env:PATH"
Add-Type -Path (Join-Path $runtime 'OpenCvSharp.dll')
Add-Type -Path $assembly
$layer=[BetterGenshinImpact.GameTask.Common.Map.Maps.Base.BaseMapLayerByTemplateMatch]::new()
$layer.LayerId='MapBack_2';$layer.Left=2318;$layer.Top=5120;$layer.Scale=1
$layer.LoadLayer((Join-Path $runtime 'Assets/Map/Teyvat'))
$map=[BetterGenshinImpact.GameTask.Common.Map.Maps.TeyvatMapTest]::new()
$property=$map.GetType().GetProperties()|Where-Object {$_.Name -eq 'Layers' -and $_.DeclaringType.Name -eq 'SceneBaseMapByTemplateMatch'}
$layers=[System.Collections.Generic.List[BetterGenshinImpact.GameTask.Common.Map.Maps.Base.BaseMapLayerByTemplateMatch]]::new()
$layers.Add($layer);$property.SetValue($map,$layers)
$mini=[OpenCvSharp.Cv2]::ImRead($path)
try{
    if($mini.Width -ne [int]$live.crop[2] -or $mini.Height -ne [int]$live.crop[3]){throw 'Saved crop dimensions differ from live receipt'}
    $anchor=[OpenCvSharp.Point2f]::new([single]$live.anchor[0],[single]$live.anchor[1])
    $image=$map.ConvertGenshinMapCoordinatesToImageCoordinates($anchor)
    $offline=$map.GetFogAwareLocalPositionDiagnostic($mini,$image,'MapBack_2')
    $checks=@(
        ($offline.Accepted -eq [bool]$live.accepted),
        ($offline.Failure -eq [string]$live.reason),
        ([Math]::Abs($offline.Rotation-[double]$live.rotation) -le 0.001),
        ([Math]::Abs($offline.RotationConfidence-[double]$live.rotationConfidence) -le 0.001),
        ($offline.OriginalPixels -eq [int]$live.originalPixels),
        ($offline.VisiblePixels -eq [int]$live.visiblePixels),
        ([Math]::Abs($offline.RoughConfidence-[double]$live.roughConfidence) -le 0.001),
        ([Math]::Abs($offline.ExactConfidence-[double]$live.exactConfidence) -le 0.001),
        ([Math]::Abs($offline.WorldX-[double]$live.world[0]) -le 0.01),
        ([Math]::Abs($offline.WorldY-[double]$live.world[1]) -le 0.01)
    )
    [pscustomobject]@{receipt=$Receipt;part=$Part;png=$path;sha256=(Get-FileHash -LiteralPath $path).Hash;
        live=$live;offline=$offline;checks=$checks;passed=($checks -notcontains $false)}|ConvertTo-Json -Depth 8
    if($checks -contains $false){exit 1}
}finally{$mini.Dispose()}

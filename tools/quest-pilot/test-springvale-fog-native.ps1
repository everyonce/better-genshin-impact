param(
    [Parameter(Mandatory)][string]$Runtime,
    [Parameter(Mandatory)][string]$AssemblyPath
)
$ErrorActionPreference='Stop'
$runtime=(Resolve-Path -LiteralPath $Runtime).Path
$assembly=(Resolve-Path -LiteralPath $AssemblyPath).Path
$env:PATH="$runtime;$env:PATH"
Add-Type -Path (Join-Path $runtime 'OpenCvSharp.dll')
Add-Type -Path $assembly
$layer=[BetterGenshinImpact.GameTask.Common.Map.Maps.Base.BaseMapLayerByTemplateMatch]::new()
$layer.LayerId='MapBack_2';$layer.Left=2318;$layer.Top=5120;$layer.Scale=1
$layer.LoadLayer((Join-Path $runtime 'Assets/Map/Teyvat'))
$city=[BetterGenshinImpact.GameTask.Common.Map.Maps.Base.BaseMapLayerByTemplateMatch]::new()
$city.LayerId='City_102';$city.Left=-532;$city.Top=2474;$city.Scale=3
$city.LoadLayer((Join-Path $runtime 'Assets/Map/Teyvat'))
$decoy=[BetterGenshinImpact.GameTask.Common.Map.Maps.Base.BaseMapLayerByTemplateMatch]::new()
$decoy.LayerId='SyntheticWrongLayer';$decoy.Left=2328;$decoy.Top=5130;$decoy.Scale=1
$decoy.CoarseColorMatcher=$layer.CoarseColorMatcher;$decoy.FineGrayMap=$layer.FineGrayMap
$map=[BetterGenshinImpact.GameTask.Common.Map.Maps.TeyvatMapTest]::new()
$property=$map.GetType().GetProperties()|Where-Object {$_.Name -eq 'Layers' -and $_.DeclaringType.Name -eq 'SceneBaseMapByTemplateMatch'}
$layers=[System.Collections.Generic.List[BetterGenshinImpact.GameTask.Common.Map.Maps.Base.BaseMapLayerByTemplateMatch]]::new()
$layers.Add($city);$layers.Add($decoy);$layers.Add($layer);$property.SetValue($map,$layers)
$fixture=Join-Path $PSScriptRoot 'fixtures/springvale-fog'
$cases=@(
    @{file='2182.png';x=-867.23413;y=1992.874;accepted=$true},
    @{file='2198.png';x=-867.23413;y=1992.874;accepted=$true},
    @{file='2205.png';x=-867.23413;y=1992.874;accepted=$true},
    @{file='2212.png';x=-867.23413;y=1992.874;accepted=$true},
    @{file='low-confidence.png';x=-867.23413;y=1992.874;accepted=$true},
    @{file='live-step-3.png';x=-867.23413;y=1992.874;accepted=$true},
    @{file='live-step-4.png';x=-867.23413;y=1992.874;accepted=$true;maxError=3.0},
    @{file='live-r21-8.png';x=-867.23413;y=1992.874;accepted=$true;maxError=4.0},
    @{file='low-confidence.png';x=-1200;y=2200;accepted=$false},
    @{file='low-confidence.png';x=-650;y=1800;accepted=$false},
    @{file='low-confidence.png';x=-900;y=1800;accepted=$false}
)
$results=@()
foreach($case in $cases){
    $mini=[OpenCvSharp.Cv2]::ImRead((Join-Path $fixture $case.file))
    try{
        if($mini.Width -ne 212 -or $mini.Height -ne 212){throw 'Unexpected minimap fixture dimensions'}
        $anchor=[OpenCvSharp.Point2f]::new([single]$case.x,[single]$case.y)
        $image=$map.ConvertGenshinMapCoordinatesToImageCoordinates($anchor)
        $result=$map.GetFogAwareLocalPosition($mini,$image,'MapBack_2')
        $accepted=$result.X -ne 0 -or $result.Y -ne 0
        $world=if($accepted){$map.ConvertImageCoordinatesToGenshinMapCoordinates($result)}else{$null}
        $error=if($world){[Math]::Sqrt([Math]::Pow($world.X+867.23413,2)+[Math]::Pow($world.Y-1992.874,2))}else{$null}
        $limit=if($case.maxError){$case.maxError}else{1.2}
        $passed=$accepted -eq $case.accepted -and (!$accepted -or $error -le $limit)
        $results += [pscustomobject]@{fixture=$case.file;anchor=@($case.x,$case.y);accepted=$accepted;world=$world;errorMapUnits=$error;passed=$passed}
    }finally{$mini.Dispose()}
}
$results|ConvertTo-Json -Depth 4
if($results.Where({!$_.passed}).Count){exit 1}

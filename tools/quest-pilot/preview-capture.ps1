param([Parameter(Mandatory=$true)][string]$Path)
$ErrorActionPreference='Stop'
# Re-encode an existing BetterGI evidence image for chat viewing. No capture or
# game input occurs here; the original retained PNG is left untouched.
$source=(Resolve-Path -LiteralPath $Path).Path
$root=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../artifacts')).Path
if(-not $source.StartsWith($root+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetExtension($source) -ne '.png') {throw 'Existing artifact PNG required'}
Add-Type -AssemblyName System.Drawing
$destination=Join-Path $root 'act-one-preview.jpg'
$bitmap=[Drawing.Image]::FromFile($source)
$parameters=[Drawing.Imaging.EncoderParameters]::new(1)
try {
    $parameters.Param[0]=[Drawing.Imaging.EncoderParameter]::new([Drawing.Imaging.Encoder]::Quality,[long]75)
    $encoder=[Drawing.Imaging.ImageCodecInfo]::GetImageEncoders()|Where-Object MimeType -eq 'image/jpeg'
    $bitmap.Save($destination,$encoder,$parameters)
} finally {$parameters.Dispose();$bitmap.Dispose()}
Get-Item -LiteralPath $destination | Select-Object FullName,Length

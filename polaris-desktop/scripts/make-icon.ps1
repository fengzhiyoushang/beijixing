$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
$size = 256
$bmp = New-Object System.Drawing.Bitmap($size, $size)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

$bg = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 18, 18, 26))
$g.FillRectangle($bg, 0, 0, $size, $size)

$glow = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(90, 74, 222, 128))
$g.FillEllipse($glow, 40, 40, 176, 176)

$cx = 128; $cy = 128; $L = 92; $W = 22
$pts1 = @(
  (New-Object System.Drawing.Point($cx, ($cy - $L))),
  (New-Object System.Drawing.Point(($cx + $W), $cy)),
  (New-Object System.Drawing.Point($cx, ($cy + $L))),
  (New-Object System.Drawing.Point(($cx - $W), $cy))
)
$pts2 = @(
  (New-Object System.Drawing.Point(($cx - $L), $cy)),
  (New-Object System.Drawing.Point($cx, ($cy - $W))),
  (New-Object System.Drawing.Point(($cx + $L), $cy)),
  (New-Object System.Drawing.Point($cx, ($cy + $W)))
)
$star = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 250, 204, 21))
$g.FillPolygon($star, $pts1)
$g.FillPolygon($star, $pts2)

$core = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
$g.FillEllipse($core, ($cx - 12), ($cy - 12), 24, 24)

$g.Dispose()
New-Item -ItemType Directory -Force -Path "build" | Out-Null
$out = Join-Path (Get-Location).Path "build\icon.png"
$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output "saved: $out"

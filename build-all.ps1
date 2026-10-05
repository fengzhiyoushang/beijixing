# 北极星个人战略终端 —— 一键构建 / 打包脚本
#
# 作用：把「前端 dist + 后端 PyInstaller 产物 + Electron 安装包」全部重新构建，
#       并把产物同步到 polaris-desktop/resources（桌面版运行所需）。
#
# 用法（在仓库根目录或任意位置）：
#   pwsh -File build-all.ps1                 # 完整构建（前端 + 后端 + 安装包）
#   pwsh -File build-all.ps1 -SkipInstaller  # 只构建前端与后端，跳过 Electron 打包
#   pwsh -File build-all.ps1 -SkipBackend    # 跳过后端重建（仅前端 + 安装包）
#
# 产物：
#   polaris-terminal/dist/                         前端静态产物
#   polaris-desktop/resources/dist/                桌面前端（Electron extraResources）
#   polaris-backend/dist/polaris-backend/          后端 onedir 产物
#   polaris-desktop/resources/backend/             桌面后端（Electron extraResources）
#   polaris-desktop/release/北极星个人战略终端 Setup 1.0.0.exe   安装包
#   polaris-desktop/release/win-unpacked/          免安装版（可直接覆盖运行）

[CmdletBinding()]
param(
  [switch]$SkipFrontend,
  [switch]$SkipBackend,
  [switch]$SkipInstaller,
  [string]$Root = (Split-Path -Parent $MyInvocation.MyCommand.Path)
)

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'

$Node = 'C:\Users\lenovo\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe'
if (-not (Test-Path $Node)) { $Node = (Get-Command node).Source }

$Py = Join-Path $Root 'polaris-backend\.venv\Scripts\python.exe'
$Terminal = Join-Path $Root 'polaris-terminal'
$Backend = Join-Path $Root 'polaris-backend'
$Desktop = Join-Path $Root 'polaris-desktop'

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  [!]  $msg" -ForegroundColor Yellow }

function Sync-Dir($from, $to) {
  if (-not (Test-Path $from)) { throw "源目录不存在：$from" }
  if (Test-Path $to) { Remove-Item $to -Recurse -Force }
  New-Item -ItemType Directory -Path $to -Force | Out-Null
  Copy-Item (Join-Path $from '*') $to -Recurse -Force
  $n = (Get-ChildItem $to -Recurse -File | Measure-Object).Count
  Ok "同步 $from -> $to（$n 个文件）"
}

# 运行原生命令：PowerShell 5.1 会把子进程 stderr 也当成错误记录，
# 在 ErrorActionPreference='Stop' 下会直接中断，故此处临时放宽并用 exit code 判定。
function Invoke-Native([string]$Exe, [string[]]$CmdArgs, [string[]]$Filter, [int]$Tail = 8) {
  $prev = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    $out = @(& $Exe @CmdArgs 2>&1 | ForEach-Object { "$_" })
    $code = $LASTEXITCODE
  } finally { $ErrorActionPreference = $prev }
  $lines = if ($Filter) {
    $out | Where-Object { $ln = $_; ($Filter | Where-Object { $ln -match $_ }).Count -gt 0 }
  } else { $out }
  ($lines | Select-Object -Last $Tail) | ForEach-Object { Write-Host "    $_" }
  return $code
}

# ─────────── 1. 前端 ───────────
if (-not $SkipFrontend) {
  Step '构建前端（Vite）'
  Push-Location $Terminal
  try {
    $code = Invoke-Native $Node @('node_modules\vite\bin\vite.js', 'build') @('error', 'Error', 'built in')
    if ($code -ne 0) { throw "vite build 失败（exit $code）" }
    if (-not (Test-Path (Join-Path $Terminal 'dist\index.html'))) { throw 'dist/index.html 未生成' }
    Ok '前端构建完成'
  } finally { Pop-Location }

  Step '同步前端到 polaris-desktop/resources/dist'
  Sync-Dir (Join-Path $Terminal 'dist') (Join-Path $Desktop 'resources\dist')
}

# ─────────── 2. 后端 ───────────
if (-not $SkipBackend) {
  Step '构建后端（PyInstaller onedir）'

  # 关键：dist/build 若被运行中的 exe 占用，PyInstaller 会报 WinError 5/32 并留下残缺产物，
  # 但进程仍可能返回 0，导致「看起来成功、实际产物不全」。故先强制清理占用与旧产物。
  $locking = Get-Process -Name 'polaris-backend' -ErrorAction SilentlyContinue
  if ($locking) {
    Warn "检测到正在运行的 polaris-backend（PID $($locking.Id -join ',')），先结束以免占用构建目录"
    $locking | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
  }
  foreach ($dir in @('dist', 'build')) {
    $p = Join-Path $Backend $dir
    if (Test-Path $p) {
      try { Remove-Item $p -Recurse -Force -ErrorAction Stop }
      catch { throw "无法清理 $p（可能仍被占用）：$($_.Exception.Message)" }
    }
  }

  if (-not (Test-Path $Py)) { throw "未找到后端虚拟环境：$Py" }
  Push-Location $Backend
  try {
    $code = Invoke-Native $Py @('-m', 'PyInstaller', 'polaris-backend.spec', '--noconfirm', '--clean') `
      @('ERROR', 'completed successfully', 'Building COLLECT')
    $exe = Join-Path $Backend 'dist\polaris-backend\polaris-backend.exe'
    if (-not (Test-Path $exe)) { throw "后端 exe 未生成：$exe（pyinstaller exit $code）" }

    # 完整性校验：文件数明显偏少说明构建被中断/占用，必须报错而不是继续
    $n = (Get-ChildItem (Join-Path $Backend 'dist\polaris-backend') -Recurse -File | Measure-Object).Count
    if ($n -lt 400) { throw "后端产物不完整：仅 $n 个文件（正常约 940）。请确认无进程占用 dist 目录后重试" }
    Ok "后端构建完成：$exe（$n 个文件）"
  } finally { Pop-Location }

  Step '同步后端到 polaris-desktop/resources/backend'
  Sync-Dir (Join-Path $Backend 'dist\polaris-backend') (Join-Path $Desktop 'resources\backend')
}

# ─────────── 3. Electron 安装包 ───────────
if (-not $SkipInstaller) {
  Step '打包 Electron（electron-builder --win）'
  Push-Location $Desktop
  try {
    $code = Invoke-Native $Node @('node_modules\electron-builder\out\cli\cli.js', '--win') `
      @('building', 'error', 'Error', 'target=', 'packaging', 'signing') 12
    if ($code -ne 0) { Warn "electron-builder exit=$code（请检查上方输出）" }
    else { Ok 'Electron 打包完成' }
  } finally { Pop-Location }
}

# ─────────── 汇总 ───────────
Step '构建产物'
$items = @(
  @{ Name = '前端 dist';            Path = (Join-Path $Terminal 'dist\index.html') },
  @{ Name = '桌面 resources/dist';  Path = (Join-Path $Desktop 'resources\dist\index.html') },
  @{ Name = '后端 exe';             Path = (Join-Path $Desktop 'resources\backend\polaris-backend.exe') },
  @{ Name = '安装包';                Path = (Join-Path $Desktop 'release\北极星个人战略终端 Setup 1.0.0.exe') },
  @{ Name = '免安装版目录';          Path = (Join-Path $Desktop 'release\win-unpacked') }
)
foreach ($i in $items) {
  if (Test-Path $i.Path) {
    $sz = if ((Get-Item $i.Path).PSIsContainer) {
      '{0:N1} MB' -f ((Get-ChildItem $i.Path -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)
    } else { '{0:N1} MB' -f ((Get-Item $i.Path).Length / 1MB) }
    Write-Host ("  {0,-22} {1,12}  {2}" -f $i.Name, $sz, (Get-Item $i.Path).LastWriteTime) -ForegroundColor Green
  } else {
    Write-Host ("  {0,-22} 缺失" -f $i.Name) -ForegroundColor Red
  }
}
Write-Host "`n完成。" -ForegroundColor Cyan

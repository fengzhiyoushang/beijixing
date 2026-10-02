# Launch the DSH Web profile (web profile has the dsh-deep-whale skins installed)
# and record the tokenized URL into dsh-web-19388.url.txt.
$ErrorActionPreference = 'Stop'

$exe = 'E:\deepseek harnse\DeepSeek Harness.exe'
$cli = 'E:\deepseek harnse\resources\app.asar\dsh\node_modules\@deepseek-ai\dsh\lib\bin.js'
$port = 19388
$outLog = Join-Path $PSScriptRoot 'dsh-web-19388.out.log'
$errLog = Join-Path $PSScriptRoot 'dsh-web-19388.err.log'
$urlFile = Join-Path $PSScriptRoot 'dsh-web-19388.url.txt'

Remove-Item $outLog, $errLog, $urlFile -Force -ErrorAction SilentlyContinue

$env:ELECTRON_RUN_AS_NODE = '1'
$env:PATH = "C:\Users\lenovo\.dsh\bin;$env:PATH"

$proc = Start-Process -FilePath $exe `
  -ArgumentList @("`"$cli`"", '--profile', 'web', '--port', "$port", '--no-open') `
  -WorkingDirectory $env:USERPROFILE `
  -RedirectStandardOutput $outLog `
  -RedirectStandardError $errLog `
  -PassThru

for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500
    if (Test-Path $outLog) {
        $line = Select-String -Path $outLog -Pattern 'dsh web: (http\S+)' -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($line) {
            $url = $line.Matches[0].Groups[1].Value
            Set-Content -Path $urlFile -Value $url -Encoding ASCII
            Write-Host "pid=$($proc.Id)"
            Write-Host "url=$url"
            exit 0
        }
    }
    if ($proc.HasExited) { Write-Host "server exited early with code $($proc.ExitCode)"; exit 1 }
}

Write-Host 'timed out waiting for the dsh web URL banner'
exit 1

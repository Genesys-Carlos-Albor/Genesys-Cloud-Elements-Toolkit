# Builds dist\Genesys Cloud Elements Toolkit.exe (single file, no console window).
# Usage (from the gc-toolkit folder): .\packaging\build_exe.ps1 [-Python <path to python.exe>]
param(
    [string]$Python = "$env:LOCALAPPDATA\gc-toolkit\.venv\Scripts\python.exe"
)
# PyInstaller logs progress to stderr, which Windows PowerShell 5.1 turns into terminating errors
# under "Stop"; success is judged by exit codes instead.
$ErrorActionPreference = "Continue"
$project = Split-Path -Parent $PSScriptRoot
# PyInstaller's temporary build files stay out of OneDrive.
$work = Join-Path $env:LOCALAPPDATA "gc-toolkit\build"

& $Python -m pip install --quiet -e "$project" pyinstaller 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { Write-Error "pip install failed with exit code $LASTEXITCODE"; exit 1 }

& $Python -m PyInstaller `
    --noconfirm --clean --onefile --windowed `
    --log-level WARN `
    --name "Genesys Cloud Elements Toolkit" `
    --collect-submodules gctoolkit `
    --copy-metadata keyring `
    --workpath $work `
    --specpath $work `
    --distpath (Join-Path $project "dist") `
    (Join-Path $PSScriptRoot "launcher.py") 2>&1 | ForEach-Object { "$_" } | Out-Host
if ($LASTEXITCODE -ne 0) { Write-Error "PyInstaller failed with exit code $LASTEXITCODE"; exit 1 }

$exe = Join-Path $project "dist\Genesys Cloud Elements Toolkit.exe"
Write-Host ("Built {0} ({1:N1} MB)" -f $exe, ((Get-Item -LiteralPath $exe).Length / 1MB)) -ForegroundColor Green

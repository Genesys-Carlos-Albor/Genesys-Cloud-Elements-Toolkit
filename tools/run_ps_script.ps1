# Runs an original Elements PowerShell script against an org through tools\gc_shim.py instead of gc.exe,
# writing its reports under -Root so they can be compared with the Python port (tools\compare_workbooks.py).
param(
    [Parameter(Mandatory)][string]$Script,
    [Parameter(Mandatory)][string]$Root,
    [Parameter(Mandatory)][string]$GcProfile,
    [string]$OrgLabel = "DevDellTech",
    [string]$RegionLabel = "use1"
)
$ErrorActionPreference = "Stop"
$tools = $PSScriptRoot
$python = Join-Path $env:LOCALAPPDATA "gc-toolkit\.venv\Scripts\python.exe"
$elements = Join-Path $Root "Documents\Powershell\Elements"
New-Item -ItemType Directory -Force -Path $elements | Out-Null
Copy-Item (Join-Path (Split-Path $Script) "Source file and destination file versioning v1.0.ps1") $elements -Force

$gc = Join-Path $Root "gc.ps1"
Set-Content -Path $gc -Encoding UTF8 -Value "& '$python' '$(Join-Path $tools "gc_shim.py")' @args"

$lines = Get-Content -LiteralPath $Script | ForEach-Object {
    if ($_ -match '^\s*Set-Location\b') { "Set-Location -LiteralPath '$Root'" }
    elseif ($_ -match '^\s*\$GCpath\s*=') { "`$GCpath = '$gc'" }
    elseif ($_ -match "^\s*& '\.\\Documents\\Powershell\\Elements\\(?!Source file and destination file versioning)") { "" }
    elseif ($_ -match '^\s*Start \$|explorer /select') { "" }
    else { $_ }
}
$harness = Join-Path $Root "harness.ps1"
Set-Content -LiteralPath $harness -Encoding UTF8 -Value $lines
$escapes = Select-String -LiteralPath $harness -Pattern 'Set-Location(?! -LiteralPath)|\bcd\b|Push-Location'
if ($escapes) { throw "The script changes folder in a way the harness doesn't redirect: $($escapes.Line -join '; ')" }

$env:GC_SHIM_PROFILE = $GcProfile
$env:PYTHONPATH = Join-Path (Split-Path $tools) "src"
$Env = $OrgLabel
$Regionname = $RegionLabel
$ErrorActionPreference = "Continue"
. $harness

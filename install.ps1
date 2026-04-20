$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Installer = Join-Path $ScriptDir "scripts\install_skill_pack.py"
$LockFile = Join-Path $ScriptDir "skills.lock.json"

if (-not (Test-Path $Installer)) {
    Write-Error "Installer not found: $Installer"
    exit 1
}

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    $Python = Get-Command py -ErrorAction SilentlyContinue
}

if (-not $Python) {
    Write-Error "python/py not found"
    exit 1
}

$ArgsList = @(
    $Installer,
    "install",
    "--source", $ScriptDir,
    "--lock-file", $LockFile
) + $args

& $Python.Source @ArgsList
exit $LASTEXITCODE

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Src = Join-Path $ScriptDir "skills"
$Dest = Join-Path $HOME ".claude\skills"

if (-not (Test-Path $Src)) {
    Write-Error "Source not found: $Src"
    exit 1
}

if (-not (Test-Path $Dest)) {
    New-Item -ItemType Directory -Path $Dest -Force | Out-Null
}

$count = 0
Get-ChildItem -Path $Src -Directory | ForEach-Object {
    $target = Join-Path $Dest $_.Name
    if (Test-Path $target) {
        Remove-Item -Recurse -Force $target
    }
    Copy-Item -Recurse -Path $_.FullName -Destination $target
    $count++
}

Write-Host "Installed $count skills to $Dest"

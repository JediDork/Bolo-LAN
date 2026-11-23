# Bolo-LAN: update from GitHub then auto-join or host a LAN game.
# Usage: powershell -ExecutionPolicy Bypass -File .\Start-BoloLAN.ps1
param(
    [string]$HostIP = "",
    [string]$PlayerName = "",
    [string]$InstallPath = ""
)

$ErrorActionPreference = 'Stop'
$repoURL = 'https://github.com/JediDork/Bolo-LAN.git'

function Assert-LastCommand($description) {
    if ($LASTEXITCODE -ne 0) { throw "$description failed (exit code $LASTEXITCODE)." }
}

try {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw 'Git was not found. Install it with: winget install --id Git.Git -e'
    }

    if ($InstallPath) {
        $repoDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($InstallPath)
    }
    elseif (Test-Path (Join-Path $PSScriptRoot '.git')) {
        $repoDir = $PSScriptRoot
    }
    else {
        $repoDir = Join-Path $PSScriptRoot 'Bolo-LAN'
    }

    if (-not (Test-Path (Join-Path $repoDir '.git'))) {
        if (Test-Path $repoDir) { throw "Directory exists but isn't a Git repository: $repoDir" }
        Write-Host '[Bolo-LAN] Cloning repository...' -ForegroundColor Cyan
        & git clone $repoURL $repoDir
        Assert-LastCommand 'Git clone'
    }
    else {
        Write-Host '[Bolo-LAN] Pulling latest version...' -ForegroundColor Cyan
        & git -C $repoDir pull --ff-only
        Assert-LastCommand 'Git pull'
    }

    $venvDir = Join-Path $repoDir '.venv'
    $venvPython = Join-Path $venvDir 'Scripts\python.exe'
    if (-not (Test-Path $venvPython)) {
        Write-Host '[Bolo-LAN] Creating Python environment...' -ForegroundColor Cyan
        if (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3 -m venv $venvDir
        }
        elseif (Get-Command python -ErrorAction SilentlyContinue) {
            & python -m venv $venvDir
        }
        else {
            throw 'Python 3 was not found. Install Python 3.11+.'
        }
        Assert-LastCommand 'Creating Python environment'
    }

    Write-Host '[Bolo-LAN] Checking dependencies...' -ForegroundColor Cyan
    & $venvPython -m pip install --disable-pip-version-check -q -r (Join-Path $repoDir 'requirements.txt')
    Assert-LastCommand 'Dependency installation'

    $gameArgs = @((Join-Path $repoDir 'launcher.py'))
    if ($HostIP) { $gameArgs += @('--host', $HostIP) }
    if ($PlayerName) { $gameArgs += @('--name', $PlayerName) }
    Write-Host '[Bolo-LAN] Starting game (auto-join or host)...' -ForegroundColor Green
    & $venvPython @gameArgs
    Assert-LastCommand 'Bolo-LAN'
}
catch {
    Write-Host "[Bolo-LAN] ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}

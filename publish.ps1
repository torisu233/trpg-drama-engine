# One-click: expose the local app via a Cloudflare quick tunnel (temporary share).
#
# Usage (run in PowerShell, NOT cmd):
#   .\publish.ps1                 # prompts for an access password
#   .\publish.ps1 -Password xxxx
#   .\publish.ps1 -SkipBuild      # reuse existing dist (only if frontend unchanged)
#
# It sets the password gate, REBUILDS the frontend (the served dist must match the
# current source, else you ship a stale UI), starts the backend (serves frontend +
# /api on :8100), and opens a Cloudflare tunnel that prints a public https URL.
# Share that URL + the password. Press Ctrl+C to stop.
param([string]$Password, [switch]$SkipBuild)

$root = $PSScriptRoot

if (-not $Password) { $Password = Read-Host "Set an access password (share this with players)" }
if (-not $Password) { Write-Host "Password cannot be empty (public without a password = anyone can burn your API key)." -ForegroundColor Red; exit 1 }
$env:APP_PASSWORD = $Password

# locate cloudflared
$cf = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cf) {
    foreach ($p in @("$env:LOCALAPPDATA\Microsoft\WinGet\Links\cloudflared.exe",
                     "C:\Program Files (x86)\cloudflared\cloudflared.exe",
                     "C:\Program Files\cloudflared\cloudflared.exe")) {
        if (Test-Path $p) { $cf = $p; break }
    }
}
if (-not $cf) { Write-Host "cloudflared not found. Install: winget install Cloudflare.cloudflared" -ForegroundColor Red; exit 1 }

# build frontend (the served dist must match current source; rebuild every run)
if ($SkipBuild -and (Test-Path "$root\frontend\dist\index.html")) {
    Write-Host "Skipping frontend build (-SkipBuild); serving existing dist." -ForegroundColor DarkGray
} else {
    Write-Host "Building frontend so dist matches current source..." -ForegroundColor Cyan
    Push-Location "$root\frontend"
    npm run build
    Pop-Location
    if (-not (Test-Path "$root\frontend\dist\index.html")) {
        Write-Host "Frontend build failed (no dist\index.html). Run 'cd frontend; npm install' then retry." -ForegroundColor Red
        exit 1
    }
}

# start backend (child process inherits APP_PASSWORD)
$python = "$root\.venv\Scripts\python.exe"
$beArgs = @("-m", "uvicorn", "backend.main:app", "--port", "8100")
$be = Start-Process -FilePath $python -ArgumentList $beArgs -WorkingDirectory $root -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 4
Write-Host ("Backend up on :8100   |   access password: " + $Password) -ForegroundColor Green
Write-Host "Opening tunnel... a https://XXXX.trycloudflare.com URL appears below. Share that URL + the password." -ForegroundColor Cyan
Write-Host "(Press Ctrl+C to stop sharing)" -ForegroundColor DarkGray
Write-Host ""

try {
    & $cf tunnel --url http://localhost:8100
}
finally {
    Stop-Process -Id $be.Id -Force -ErrorAction SilentlyContinue
    Write-Host ""
    Write-Host "Backend stopped. Sharing ended." -ForegroundColor Yellow
}

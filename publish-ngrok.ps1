# One-click publish with a FIXED public URL via ngrok (same address every run).
#
# One-time setup (do these once):
#   1. Sign up free at https://ngrok.com  ->  copy your authtoken
#   2. Install ngrok:   winget install ngrok.ngrok
#   3. Save your token: ngrok config add-authtoken <YOUR_TOKEN>
#   4. Reserve a free domain at https://dashboard.ngrok.com/domains
#      (it looks like  your-name.ngrok-free.app  -- free plan gives you one)
#
# Usage (run in PowerShell, NOT cmd):
#   .\publish-ngrok.ps1                                   # uses saved domain, prompts password
#   .\publish-ngrok.ps1 -Domain your-name.ngrok-free.app -Password pw
#   .\publish-ngrok.ps1 -SkipBuild                        # reuse dist (frontend unchanged)
#
# The reserved domain is remembered in .ngrok-domain.txt so you only type it once.
# Share that fixed URL + the password. Press Ctrl+C to stop.
param([string]$Password, [string]$Domain, [switch]$SkipBuild)

$root = $PSScriptRoot
$domainFile = Join-Path $root ".ngrok-domain.txt"

# access password (backend gate; required so a public URL cannot burn your API key)
if (-not $Password) { $Password = Read-Host "Set an access password (share this with players)" }
if (-not $Password) { Write-Host "Password cannot be empty (public without a password = anyone can burn your API key)." -ForegroundColor Red; exit 1 }
$env:APP_PASSWORD = $Password

# fixed domain: priority = -Domain param > saved file > prompt (then remembered)
if (-not $Domain -and (Test-Path $domainFile)) { $Domain = (Get-Content $domainFile -Raw).Trim() }
if (-not $Domain) { $Domain = Read-Host "Your reserved ngrok domain (e.g. your-name.ngrok-free.app)" }
if (-not $Domain) { Write-Host "A reserved domain is required for a fixed URL. Get one free: https://dashboard.ngrok.com/domains" -ForegroundColor Red; exit 1 }
$Domain = ($Domain -replace '^https?://','').TrimEnd('/')   # tolerate pasted scheme/slash
Set-Content -Path $domainFile -Value $Domain -Encoding ascii  # remember for next time

# locate ngrok
$ng = (Get-Command ngrok -ErrorAction SilentlyContinue).Source
if (-not $ng) {
    foreach ($p in @("$env:LOCALAPPDATA\Microsoft\WinGet\Links\ngrok.exe",
                     "C:\Program Files\ngrok\ngrok.exe")) {
        if (Test-Path $p) { $ng = $p; break }
    }
}
if (-not $ng) { Write-Host "ngrok not found. Install: winget install ngrok.ngrok   then   ngrok config add-authtoken <TOKEN>" -ForegroundColor Red; exit 1 }

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
Write-Host ("Fixed public URL: https://" + $Domain + "   (share this + the password)") -ForegroundColor Green
Write-Host "Note: ngrok free shows a one-time 'Visit Site' warning page on first open; click through it." -ForegroundColor DarkGray
Write-Host "(Press Ctrl+C to stop sharing)" -ForegroundColor DarkGray
Write-Host ""

try {
    # --domain pins the reserved subdomain. (Newer ngrok also accepts --url=https://<domain>.)
    & $ng http ("--domain=" + $Domain) 8100
}
finally {
    Stop-Process -Id $be.Id -Force -ErrorAction SilentlyContinue
    Write-Host ""
    Write-Host "Backend stopped. Sharing ended." -ForegroundColor Yellow
}

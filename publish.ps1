# 一鍵把本機 app 透過 Cloudflare 隧道公開（臨時分享用）
# 用法：  .\publish.ps1            （會問你要設的存取密碼）
#         .\publish.ps1 -Password 你的密碼
#
# 會：設密碼閘 → (必要時)建置前端 → 起後端(供前端+API) → 開 Cloudflare 隧道印出公網網址。
# 把印出的 https://xxxx.trycloudflare.com 網址 ＋ 密碼 分享出去即可。Ctrl+C 結束。
param([string]$Password)

$root = $PSScriptRoot
if (-not $Password) { $Password = Read-Host "設定存取密碼（分享給對方用）" }
if (-not $Password) { Write-Error "密碼不可空（公開沒密碼會被人盜用金鑰）"; exit 1 }
$env:APP_PASSWORD = $Password

# 找 cloudflared
$cf = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
foreach ($p in @("$env:LOCALAPPDATA\Microsoft\WinGet\Links\cloudflared.exe",
                 "C:\Program Files (x86)\cloudflared\cloudflared.exe",
                 "C:\Program Files\cloudflared\cloudflared.exe")) {
  if (-not $cf -and (Test-Path $p)) { $cf = $p }
}
if (-not $cf) { Write-Error "找不到 cloudflared，請先 winget install Cloudflare.cloudflared"; exit 1 }

# 前端 dist（沒有就建置一次）
if (-not (Test-Path "$root\frontend\dist\index.html")) {
  Write-Host "建置前端…" -ForegroundColor Cyan
  Push-Location "$root\frontend"; npm run build; Pop-Location
}

# 起後端（子行程繼承 APP_PASSWORD）
$be = Start-Process -FilePath "$root\.venv\Scripts\python.exe" `
  -ArgumentList "-m", "uvicorn", "backend.main:app", "--port", "8100" `
  -WorkingDirectory $root -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 4
Write-Host "後端已啟動（埠 8100）。存取密碼：$Password" -ForegroundColor Green
Write-Host "開啟隧道中——下面會出現 https://xxxx.trycloudflare.com，把它和密碼分享出去：" -ForegroundColor Cyan
Write-Host "（Ctrl+C 結束分享）`n" -ForegroundColor DarkGray

try {
  & $cf tunnel --url http://localhost:8100
}
finally {
  Stop-Process -Id $be.Id -Force -ErrorAction SilentlyContinue
  Write-Host "`n已關閉後端，分享結束。" -ForegroundColor Yellow
}

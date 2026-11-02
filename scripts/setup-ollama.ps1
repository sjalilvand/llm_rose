#Requires -RunAsAdministrator
<#
.SYNOPSIS
    نصب و پیکربندی خودکار Ollama + مدل فارسی‌زبان Qwen3-8B روی Windows Server
.DESCRIPTION
    مراحل: نصب Ollama، تنظیم متغیرهای محیطی بهینه برای CPU، باز کردن پورت فایروال،
    دانلود مدل و تست نهایی API.
    اجرا:  PowerShell (Administrator)  ->  .\setup-ollama.ps1
#>

$ErrorActionPreference = "Stop"
$Model = "qwen3:8b"

Write-Host "=== ۱) بررسی و نصب Ollama ===" -ForegroundColor Cyan

# پیدا کردن مسیر ollama (با احتساب PATH سشن جاری)
$ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if (-not $ollama) { $ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" }

if (-not (Test-Path $ollama)) {
    Write-Host "Ollama یافت نشد؛ در حال نصب..."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
    }
    else {
        Write-Host "winget موجود نیست؛ دانلود مستقیم نصاب..."
        $installer = "$env:TEMP\OllamaSetup.exe"
        Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile $installer
        Start-Process $installer -ArgumentList "/silent" -Wait
    }
    # مسیر نصب تازه را دوباره پیدا کن
    $ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
    if (-not $ollama) { $ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" }
    if (-not (Test-Path $ollama)) { throw "نصب Ollama ناموفق بود؛ لطفاً دستی از ollama.com/download نصب کنید." }
}
else {
    Write-Host "Ollama از قبل نصب است: $ollama"
}

Write-Host "`n=== ۲) تنظیم متغیرهای محیطی (بهینه CPU / RAM) ===" -ForegroundColor Cyan
[Environment]::SetEnvironmentVariable("OLLAMA_HOST",              "0.0.0.0", "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE",        "-1",      "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_PARALLEL",      "1",       "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_MAX_LOADED_MODELS", "1",       "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_FLASH_ATTENTION",   "1",       "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_KV_CACHE_TYPE",     "q8_0",    "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_CONTEXT_LENGTH",    "8192",    "Machine")
Write-Host "متغیرهای OLLAMA_* در سطح سیستم ثبت شدند."

Write-Host "`n=== ۳) باز کردن پورت 11434 در فایروال ===" -ForegroundColor Cyan
if (-not (Get-NetFirewallRule -DisplayName "Ollama API 11434" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName "Ollama API 11434" -Direction Inbound -Protocol TCP -LocalPort 11434 -Action Allow | Out-Null
    Write-Host "قانون فایروال اضافه شد."
}
else { Write-Host "قانون فایروال از قبل وجود دارد." }

Write-Host "`n=== ۴) ری‌استارت Ollama برای اعمال متغیرها ===" -ForegroundColor Cyan
Get-Process -Name "ollama*", "Ollama*" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
$app = "$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe"
if (Test-Path $app) { Start-Process $app }
else { Start-Process $ollama -ArgumentList "serve" -WindowStyle Hidden }
Start-Sleep -Seconds 5

Write-Host "`n=== ۵) دانلود مدل $Model (~5.2GB) ===" -ForegroundColor Cyan
& $ollama pull $Model

Write-Host "`n=== ۶) تست نهایی API ===" -ForegroundColor Cyan
$testBody = @{
    model   = $Model
    think   = $false
    messages = @(@{ role = "user"; content = "سلام! در یک جمله خودت را معرفی کن." })
    stream  = $false
} | ConvertTo-Json -Depth 5

# ارسال بدنه به‌صورت UTF-8 تا متن فارسی درست برسد
$bytes = [System.Text.Encoding]::UTF8.GetBytes($testBody)
$resp = Invoke-RestMethod -Uri "http://localhost:11434/api/chat" -Method Post -Body $bytes -ContentType "application/json"

Write-Host "`n--- پاسخ مدل ---" -ForegroundColor Green
Write-Host $resp.message.content
Write-Host "`nنصب و پیکربندی کامل شد. برای چت تعاملی اجرا کنید:" -ForegroundColor Yellow
Write-Host "    $ollama run $Model   و سپس   /set nothink" -ForegroundColor Yellow

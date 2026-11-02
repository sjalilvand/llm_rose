#Requires -RunAsAdministrator
<#
.SYNOPSIS
    مدیریت سرویس چت وب LLM Rose روی Windows Server
.DESCRIPTION
    Action=run      اجرای مستقیم سرور در همین پنجره (برای تست)
    Action=install  باز کردن فایروال + ثبت سرویس به‌صورت Scheduled Task (بالاآمدن خودکار با ویندوز) + اجرا
    Action=remove   حذف سرویس
    Action=status   وضعیت سرویس
    -SetOllamaEnv   تنظیم OLLAMA_KEEP_ALIVE=-1 و بهینه‌سازی RAM (باعث می‌شود مدل همیشه در RAM بماند)
.EXAMPLES
    powershell -ExecutionPolicy Bypass -File install_service.ps1 -Action install -Port 8093 -SetOllamaEnv
    powershell -ExecutionPolicy Bypass -File install_service.ps1 -Action run
    powershell -ExecutionPolicy Bypass -File install_service.ps1 -Action status
#>

param(
    [ValidateSet("run", "install", "remove", "status")][string]$Action = "run",
    [int]$Port = 8093,
    [string]$Model = "qwen3:8b",
    [switch]$SetOllamaEnv
)

$ErrorActionPreference = "Stop"
$dir = $PSScriptRoot
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command py -ErrorAction Stop).Source }
$taskName = "LLMRoseChat"

if ($SetOllamaEnv) {
    Write-Host "تنظیم متغیرهای بهینه Ollama (KEEP_ALIVE / FLASH_ATTENTION / KV_CACHE)..." -ForegroundColor Cyan
    [Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "-1", "Machine")
    [Environment]::SetEnvironmentVariable("OLLAMA_FLASH_ATTENTION", "1", "Machine")
    [Environment]::SetEnvironmentVariable("OLLAMA_KV_CACHE_TYPE", "q8_0", "Machine")
    [Environment]::SetEnvironmentVariable("OLLAMA_CONTEXT_LENGTH", "8192", "Machine")
    Write-Host "انجام شد. برای اعمال، Ollama (یا سیستم) را یک‌بار ری‌استارت کنید." -ForegroundColor Yellow
}

switch ($Action) {

    "run" {
        Write-Host "اجرای سرور چت روی پورت $Port (توقف با Ctrl+C)..." -ForegroundColor Cyan
        & $python "$dir\chat_server.py" --port $Port --model $Model
    }

    "install" {
        Write-Host "=== ۱) فایروال ===" -ForegroundColor Cyan
        if (-not (Get-NetFirewallRule -DisplayName "LLM Rose Chat $Port" -ErrorAction SilentlyContinue)) {
            New-NetFirewallRule -DisplayName "LLM Rose Chat $Port" -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow | Out-Null
            Write-Host "پورت $Port در فایروال ویندوز باز شد."
        }
        else { Write-Host "قانون فایروال از قبل موجود است." }

        Write-Host "=== ۲) ثبت سرویس (Scheduled Task) ===" -ForegroundColor Cyan
        $act = New-ScheduledTaskAction -Execute $python `
            -Argument "`"$dir\chat_server.py`" --port $Port --model $Model" `
            -WorkingDirectory $dir
        $trg = New-ScheduledTaskTrigger -AtStartup
        Register-ScheduledTask -TaskName $taskName -Action $act -Trigger $trg `
            -RunLevel Highest -Force `
            -Description "LLM Rose - Persian chat server + OpenAI-compatible API" | Out-Null
        Write-Host "سرویس با نام $taskName ثبت شد (اجرای خودکار بعد از ری‌استارت ویندوز)."

        Write-Host "=== ۳) اجرای اولیه ===" -ForegroundColor Cyan
        Start-ScheduledTask -TaskName $taskName
        Start-Sleep -Seconds 4
        try {
            $h = Invoke-RestMethod "http://localhost:$Port/health" -TimeoutSec 10
            Write-Host "سرویس فعال است: $($h | ConvertTo-Json -Compress)" -ForegroundColor Green
        }
        catch {
            Write-Host "سرویس هنوز بالا نیامده؛ چند ثانیه بعد با Action=status بررسی کنید." -ForegroundColor Yellow
        }

        Write-Host "`n=== ساخت اولین توکن API ===" -ForegroundColor Cyan
        & $python "$dir\chat_server.py" add-token --name "first-token"
        Write-Host "`nآدرس چت:  http://<IP-سرور>:$Port" -ForegroundColor Green
        Write-Host "نکته: اگر فایروال بیرونی (شرکت میزبانی/کلود) دارید، پورت $Port را آنجا هم باز کنید." -ForegroundColor Yellow
    }

    "remove" {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
        Write-Host "سرویس $taskName حذف شد. (قانون فایروال حفظ شد)"
    }

    "status" {
        $t = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($t) { Write-Host "وضعیت تسک: $($t.State)" }
        else { Write-Host "تسکی ثبت نشده است." }
        try {
            $h = Invoke-RestMethod "http://localhost:$Port/health" -TimeoutSec 5
            Write-Host "سرویس پاسخ می‌دهد: $($h | ConvertTo-Json -Compress)" -ForegroundColor Green
        }
        catch { Write-Host "سرویس روی پورت $Port پاسخ نمی‌دهد." -ForegroundColor Red }
    }
}

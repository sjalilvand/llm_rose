#Requires -RunAsAdministrator
<#
.SYNOPSIS
    مدیریت سرویس چت وب LLM Rose روی Windows Server
.DESCRIPTION
    Action=run       اجرای مستقیم سرور در همین پنجره (برای دیدن خطاها هنگام تست)
    Action=install   باز کردن فایروال + ثبت سرویس با حساب SYSTEM (بالاآمدن خودکار با ویندوز، مستقل از لاگین) + اجرا
    Action=restart   توقف و اجرای مجدد سرویس (مثلاً بعد از git pull برای اعمال کد جدید)
    Action=diagnose  عیب‌یابی گام‌به‌گام وقتی سایت/API بالا نمی‌آید
    Action=remove    حذف سرویس
    Action=status    وضعیت سرویس
    -SetOllamaEnv    تنظیم OLLAMA_KEEP_ALIVE=20m و بهینه‌سازی RAM (مدل بعد از ۲۰ دقیقه بی‌کاری از RAM خارج می‌شود)
.EXAMPLES
    powershell -ExecutionPolicy Bypass -File install_service.ps1 -Action install -Port 8093 -SetOllamaEnv
    powershell -ExecutionPolicy Bypass -File install_service.ps1 -Action restart -Port 8093
    powershell -ExecutionPolicy Bypass -File install_service.ps1 -Action diagnose -Port 8093
    powershell -ExecutionPolicy Bypass -File install_service.ps1 -Action run
#>

param(
    [ValidateSet("run", "install", "restart", "diagnose", "remove", "status")][string]$Action = "run",
    [int]$Port = 8093,
    [string]$Model = "qwen3:4b",   # مدل سبک و سریع برای CPU (برای کیفیت بالاتر: -Model qwen3:8b)
    [string]$VisionModel = "",
    [switch]$SetOllamaEnv
)

$ErrorActionPreference = "Stop"
$dir = $PSScriptRoot
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command py -ErrorAction Stop).Source }
$taskName = "LLMRoseChat"

# اگر مدل روی Ollama موجود نباشد، یک‌بار دانلود می‌شود (اگر Ollama در دسترس باشد)
function Ensure-Model([string]$m) {
    if (-not $m) { return }
    $names = @()
    try {
        $tags = Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
        if ($tags.models) { $names = @($tags.models | ForEach-Object { $_.name }) }
    } catch {
        Write-Host "Ollama در دسترس نیست؛ بررسی وجود مدل '$m' رد شد (اگر مدل را ندارید: ollama pull $m)" -ForegroundColor Yellow
        return
    }
    if ($names -notcontains $m -and $names -notcontains "${m}:latest") {
        Write-Host "مدل '$m' روی Ollama نیست؛ دانلود می‌شود (فقط بار اول، ممکن است چند دقیقه طول بکشد)..." -ForegroundColor Yellow
        & ollama pull $m
    } else {
        Write-Host "مدل '$m' از قبل موجود است ✓"
    }
}

if ($SetOllamaEnv) {
    Write-Host "تنظیم متغیرهای بهینه Ollama (KEEP_ALIVE=20m / FLASH_ATTENTION / KV_CACHE)..." -ForegroundColor Cyan
    [Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "20m", "Machine")
    [Environment]::SetEnvironmentVariable("OLLAMA_FLASH_ATTENTION", "1", "Machine")
    [Environment]::SetEnvironmentVariable("OLLAMA_KV_CACHE_TYPE", "q8_0", "Machine")
    [Environment]::SetEnvironmentVariable("OLLAMA_CONTEXT_LENGTH", "8192", "Machine")
    Write-Host "انجام شد. برای اعمال، Ollama (یا سیستم) را یک‌بار ری‌استارت کنید." -ForegroundColor Yellow
}

switch ($Action) {

    "run" {
        Write-Host "اجرای سرور چت روی پورت $Port (توقف با Ctrl+C)..." -ForegroundColor Cyan
        $extra = @(); if ($VisionModel) { $extra += @("--vision-model", $VisionModel) }
        & $python "$dir\chat_server.py" --port $Port --model $Model @extra
    }

    "install" {
        Write-Host "=== ۱) فایروال ===" -ForegroundColor Cyan
        if (-not (Get-NetFirewallRule -DisplayName "LLM Rose Chat $Port" -ErrorAction SilentlyContinue)) {
            New-NetFirewallRule -DisplayName "LLM Rose Chat $Port" -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow | Out-Null
            Write-Host "پورت $Port در فایروال ویندوز باز شد."
        }
        else { Write-Host "قانون فایروال از قبل موجود است." }

        Write-Host "=== ۲) بررسی/دانلود مدل‌ها (چت + بینایی) ===" -ForegroundColor Cyan
        Ensure-Model $Model
        if ($VisionModel) { Ensure-Model $VisionModel }

        Write-Host "=== ۳) ثبت سرویس (Scheduled Task با حساب SYSTEM) ===" -ForegroundColor Cyan
        $argLine = "`"$dir\chat_server.py`" --port $Port --model $Model"
        if ($VisionModel) { $argLine += " --vision-model $VisionModel" }
        $act = New-ScheduledTaskAction -Execute $python `
            -Argument $argLine `
            -WorkingDirectory $dir
        $trg = New-ScheduledTaskTrigger -AtStartup
        Register-ScheduledTask -TaskName $taskName -Action $act -Trigger $trg `
            -User "SYSTEM" -RunLevel Highest -Force `
            -Description "LLM Rose - Persian chat server + OpenAI-compatible API" | Out-Null
        Write-Host "سرویس با نام $taskName و حساب SYSTEM ثبت شد (مستقل از لاگین شما؛ بعد از ری‌استارت ویندوز هم خودش بالا می‌آید)."

        Write-Host "=== ۴) توقف نسخه قبلی و اجرای کد جدید ===" -ForegroundColor Cyan
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        Start-ScheduledTask -TaskName $taskName
        Start-Sleep -Seconds 4
        try {
            $h = Invoke-RestMethod "http://localhost:$Port/health" -TimeoutSec 10
            Write-Host "سرویس با کد جدید فعال است: $($h | ConvertTo-Json -Compress)" -ForegroundColor Green
            Write-Host "(اگر 'model' بالا qwen3:4b و uptime چند ثانیه است، همه‌چیز درست است)"
        }
        catch {
            Write-Host "سرویس هنوز بالا نیامده؛ چند ثانیه بعد با Action=status یا Action=diagnose بررسی کنید." -ForegroundColor Yellow
        }

        Write-Host "`n=== ۵) توکن API (فقط بار اول) ===" -ForegroundColor Cyan
        if (Test-Path "$dir\data\tokens.json") {
            Write-Host "توکن‌ها از قبل موجودند (data\tokens.json) — توکن تکراری ساخته نشد ✓"
            Write-Host "توکن‌های موجود:  python `"$dir\chat_server.py`" list-tokens"
            Write-Host "توکن جدید:       python `"$dir\chat_server.py`" add-token --name `"نام-توکن`""
        } else {
            & $python "$dir\chat_server.py" add-token --name "first-token"
        }
        Write-Host "`nآدرس چت:  http://<IP-سرور>:$Port" -ForegroundColor Green
        Write-Host "نکته: اگر فایروال بیرونی (شرکت میزبانی/کلود) دارید، پورت $Port را آنجا هم باز کنید." -ForegroundColor Yellow
    }

    "restart" {
        $t = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if (-not $t) {
            Write-Host "تسک $taskName ثبت نشده است؛ اول Action=install را اجرا کنید." -ForegroundColor Red
            return
        }
        Write-Host "توقف و اجرای مجدد سرویس (اعمال کد جدید)..." -ForegroundColor Cyan
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        Start-ScheduledTask -TaskName $taskName
        Start-Sleep -Seconds 4
        try {
            $h = Invoke-RestMethod "http://localhost:$Port/health" -TimeoutSec 10
            Write-Host "✓ سرویس با کد جدید فعال شد: $($h | ConvertTo-Json -Compress)" -ForegroundColor Green
        }
        catch {
            Write-Host "هنوز بالا نیامده؛ با Action=status یا Action=diagnose بررسی کنید." -ForegroundColor Yellow
        }
    }

    "diagnose" {
        Write-Host "=== عیب‌یابی سرویس چت (پورت $Port) ===" -ForegroundColor Cyan
        $ok = $true

        # ۱) تسک زمان‌بندی‌شده
        $t = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($t) {
            Write-Host "۱) تسک سرویس   : موجود — وضعیت: $($t.State)"
            if ($t.State -ne "Running") {
                Write-Host "   → سرویس اجرا نمی‌شود. راه‌حل:" -ForegroundColor Yellow
                Write-Host "     Start-ScheduledTask -TaskName $taskName"
                Write-Host "     یا:  powershell -ExecutionPolicy Bypass -File `"$dir\install_service.ps1`" -Action restart"
                $ok = $false
            }
        } else {
            Write-Host "۱) تسک سرویس   : ثبت نشده است!" -ForegroundColor Red
            Write-Host "   → راه‌حل:" -ForegroundColor Yellow
            Write-Host "     powershell -ExecutionPolicy Bypass -File `"$dir\install_service.ps1`" -Action install -Port $Port"
            $ok = $false
        }

        # ۲) پورت گوش می‌دهد؟
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($conn) {
            Write-Host "۲) پورت $Port   : در حال گوش‌دادن (PID $($conn.OwningProcess))"
        } else {
            Write-Host "۲) پورت $Port   : هیچ برنامه‌ای روی این پورت گوش نمی‌دهد!" -ForegroundColor Red
            $ok = $false
            if ($t -and $t.State -eq "Running") {
                Write-Host "   → تسک Running است ولی پورت بسته است؛ یعنی سرور موقع اجرا خطا داده و بسته شده." -ForegroundColor Yellow
                Write-Host "     برای دیدن متن خطا، اجرای مستقیم:" -ForegroundColor Yellow
                Write-Host "     powershell -ExecutionPolicy Bypass -File `"$dir\install_service.ps1`" -Action run"
            }
        }

        # ۳) سلامت محلی
        if ($conn) {
            try {
                $h = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 5
                Write-Host "۳) سلامت محلی  : پاسخ می‌دهد — status=$($h.status)"
            } catch {
                Write-Host "۳) سلامت محلی  : پورت باز است ولی /health پاسخ نمی‌دهد! $_" -ForegroundColor Red
                $ok = $false
            }
        }

        # ۴) فایروال ویندوز
        $fw = Get-NetFirewallRule -DisplayName "LLM Rose Chat $Port" -ErrorAction SilentlyContinue
        if ($fw -and "$($fw.Enabled)" -eq "True" -and "$($fw.Action)" -eq "Allow") {
            Write-Host "۴) فایروال ویندوز: قانون باز برای پورت $Port موجود است"
        } else {
            Write-Host "۴) فایروال ویندوز: قانون باز وجود ندارد یا غیرفعال است!" -ForegroundColor Red
            Write-Host "   → راه‌حل:" -ForegroundColor Yellow
            Write-Host "     New-NetFirewallRule -DisplayName `"LLM Rose Chat $Port`" -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow"
            $ok = $false
        }

        # ۵) Ollama (فقط هشدار — روی /health اثر ندارد)
        try {
            $null = Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
            Write-Host "۵) Ollama       : فعال است"
        } catch {
            Write-Host "۵) Ollama       : پاسخ نمی‌دهد (چت جواب نمی‌دهد ولی /health بالا می‌آید) — ollama serve را بررسی کنید" -ForegroundColor Yellow
        }

        Write-Host ""
        if ($ok) {
            Write-Host "✓ همه بررسی‌های داخل سرور سبز است." -ForegroundColor Green
            Write-Host "اگر از بیرون باز نمی‌شود، مشکل خارج از ویندوز است:" -ForegroundColor Yellow
            Write-Host "  • پورت $Port را در پنل فایروال شرکت میزبانی (پنل ابری سرور) هم باز کنید."
            Write-Host "  • از سیستم خودتان تست کنید:  http://<IP-سرور>:$Port/health"
        } else {
            Write-Host "✗ یک یا چند مورد بالا قرمز است؛ راه‌حل‌های کنار هر مورد را اجرا کنید و دوباره diagnose بگیرید." -ForegroundColor Yellow
        }
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

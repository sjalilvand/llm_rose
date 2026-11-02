<#
.SYNOPSIS
    تست سریع API مدل فارسی‌زبان + اندازه‌گیری سرعت
.DESCRIPTION
    روی خود سرور اجرا کنید یا با پارامتر -Server از سیستم دیگر.
    اجرا:  .\test_api.ps1
           .\test_api.ps1 -Server 192.168.1.10
#>

param(
    [string]$Server = "localhost",
    [string]$Model = "qwen3:8b"
)

$body = @{
    model    = $Model
    think    = $false
    messages = @(
        @{ role = "system"; content = "تو یک دستیار فارسی‌زبان هستی." },
        @{ role = "user";   content = "سلام! در دو جمله خودت را معرفی کن." }
    )
    stream   = $false
} | ConvertTo-Json -Depth 5

# بدنه باید UTF-8 بایت باشد تا متن فارسی درست ارسال شود (مخصوصاً در PowerShell 5.1)
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)

$sw = [System.Diagnostics.Stopwatch]::StartNew()
try {
    $resp = Invoke-RestMethod -Uri "http://${Server}:11434/api/chat" -Method Post -Body $bytes -ContentType "application/json"
}
catch {
    Write-Host "اتصال به Ollama ناموفق بود: $_" -ForegroundColor Red
    Write-Host "بررسی کنید: سرویس Ollama روشن است؟ مدل دانلود شده؟ (ollama list)" -ForegroundColor Yellow
    exit 1
}
$sw.Stop()

Write-Host "`n--- پاسخ مدل ---" -ForegroundColor Green
Write-Host $resp.message.content

$speed = $resp.eval_count / [math]::Max($resp.eval_duration / 1e9, 0.001)
Write-Host ("`nزمان کل: {0:N1} ثانیه | توکن خروجی: {1} | سرعت تولید: {2:N1} توکن/ثانیه" -f `
        $sw.Elapsed.TotalSeconds, $resp.eval_count, $speed) -ForegroundColor Cyan

Write-Host "`nآمار RAM:" -ForegroundColor Cyan
Get-Process -Name "ollama*" -ErrorAction SilentlyContinue |
    Select-Object Name, @{ n = 'RAM(MB)'; e = { [math]::Round($_.WorkingSet64 / 1MB) } } |
    Format-Table -AutoSize

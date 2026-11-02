# llm_rose

راهنمای انتخاب، نصب و استفاده از یک **مدل زبانی بزرگ (LLM) رایگان و فارسی‌زبان** روی سرور ویندوزی **بدون کارت گرافیک (فقط CPU)**.

- مدل پیشنهادی اصلی: **Qwen3-8B** — متن‌باز با مجوز Apache 2.0، رایگان برای استفاده تجاری، پشتیبانی رسمی از فارسی
- ابزار اجرا: **Ollama** — نصب ساده روی ویندوز، API آماده و سازگار با OpenAI
- سکوی هدف: Windows Server 2025 Standard، ۱۲ هسته CPU، ۲۴GB RAM

---

## ۱) مشخصات سرور هدف

| مورد | مقدار |
|---|---|
| سیستم‌عامل | Microsoft Windows Server 2025 Standard (64-bit) |
| CPU | QEMU Virtual CPU — ۱۲ هسته / ۱۲ رشته — 2.3GHz |
| RAM | ۲۴GB (حدود ۱۴GB آزاد در زمان بررسی) |
| دیسک | ۲۰۰GB (حدود ۱۵۶GB آزاد) |
| GPU | ندارد — اجرا کاملاً روی CPU |
| سرویس‌های فعال | Docker Desktop، Redis، ClamAV (مصرف‌کننده RAM) |

> نکته مهم: چون Docker Desktop (~۰.۷GB)، ClamAV (~۱GB) و Redis (~۰.۲۵GB) فعال‌اند، عملاً حدود ۱۴GB RAM آزاد در اختیار داریم. مدل‌هایی که حداکثر ~۹GB فضا اشغال کنند، با خیال راحت روی این سرور اجرا می‌شوند.

## ۲) مدل پیشنهادی و گزینه‌های جایگزین

| مدل | دستور دانلود | حجم دانلود | RAM در حال کار | کیفیت فارسی | سرعت تقریبی روی این سرور | مجوز |
|---|---|---|---|---|---|---|
| **Qwen3-8B** (پیشنهاد اصلی) | `ollama pull qwen3:8b` | ~5.2GB | ~6–7GB | خیلی خوب | ~۶ تا ۱۲ توکن/ثانیه | Apache 2.0 (تجاری آزاد) |
| Gemma 3 12B | `ollama pull gemma3:12b` | ~8.1GB | ~9–10GB | عالی (۱۴۰+ زبان) | ~۳ تا ۷ توکن/ثانیه | Gemma Terms (تجاری با شرط) |
| Aya Expanse 8B | `ollama pull aya-expanse:8b` | ~5.1GB | ~6–7GB | عالی (تخصصی ۲۳ زبان) | ~۶ تا ۱۲ توکن/ثانیه | CC-BY-NC (فقط غیرتجاری) |
| Qwen3-4B (سریع) | `ollama pull qwen3:4b` | ~2.6GB | ~3–4GB | خوب | ~۱۵ تا ۲۵ توکن/ثانیه | Apache 2.0 |
| Dorna2 (فارسی‌محور PartAI) | GGUF از HuggingFace | ~4.9GB | ~6GB | عالی برای فارسی | ~۶ تا ۱۲ توکن/ثانیه | Llama 3.1 Community |

### چرا Qwen3-8B؟

1. **رایگان و متن‌باز** با مجوز Apache 2.0؛ استفاده تجاری و استقرار در سازمان آزاد است.
2. رسماً از **بیش از ۱۰۰ زبان از جمله فارسی** پشتیبانی می‌کند و پاسخ‌های فارسی روان و طبیعی می‌دهد.
3. در کوانتیزاسیون Q4 فقط حدود 5.2GB فضا و 6–7GB RAM می‌خواهد؛ یعنی روی این سرور **حتی با Docker و Redis روشن** هم راحت جا می‌شود.
4. روی ۱۲ هسته CPU با فرکانس 2.3GHz، سرعت قابل قبول ۶ تا ۱۲ توکن بر ثانیه می‌دهد.
5. مسیر ارتقا باز است: هر وقت RAM بیشتری آزاد کردید می‌توانید به `qwen3:14b` (کیفیت بالاتر، ~9GB) یا `gemma3:12b` مهاجرت کنید.

### حالت «تفکر» در Qwen3

Qwen3 مدل هیبریدی است و به‌طور پیش‌فرض قبل از پاسخ، مرحله استدلال (thinking) اجرا می‌کند. این کار کیفیت را بالا می‌برد اما روی CPU پاسخ را کند می‌کند:

- در API: پارامتر `"think": false` را بفرستید تا پاسخ مستقیم و سریع بگیرید.
- در محیط تعاملی: دستور `/set nothink` را اجرا کنید.

## ۳) نصب قدم‌به‌قدم روی Windows Server 2025

کل مراحل این بخش را اسکریپت آماده [scripts/setup-ollama.ps1](scripts/setup-ollama.ps1) به‌صورت خودکار انجام می‌دهد. اگر می‌خواهید دستی انجام دهید:

### گام ۱ — نصب Ollama

```powershell
winget install Ollama.Ollama
# اگر winget نبود، نصاب را از https://ollama.com/download/windows دانلود و اجرا کنید
```

### گام ۲ — تنظیم متغیرهای محیطی (بهینه برای CPU و RAM محدود)

```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_HOST","0.0.0.0","Machine")          # دسترسی از شبکه
[Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE","-1","Machine")          # مدل همیشه در RAM بماند
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_PARALLEL","1","Machine")         # یک درخواست همزمان (صرفه‌جویی RAM)
[Environment]::SetEnvironmentVariable("OLLAMA_MAX_LOADED_MODELS","1","Machine")    # فقط یک مدل لود شود
[Environment]::SetEnvironmentVariable("OLLAMA_FLASH_ATTENTION","1","Machine")      # کاهش مصرف RAM کش
[Environment]::SetEnvironmentVariable("OLLAMA_KV_CACHE_TYPE","q8_0","Machine")     # نیم‌کردن RAM حافظه KV
[Environment]::SetEnvironmentVariable("OLLAMA_CONTEXT_LENGTH","8192","Machine")    # طول زمینه ۸K
```

سپس Ollama را یک‌بار ببندید و دوباره باز کنید تا متغیرها اعمال شوند.

### گام ۳ — باز کردن پورت در فایروال (فقط اگر از سیستم‌های دیگر به API وصل می‌شوید)

```powershell
New-NetFirewallRule -DisplayName "Ollama API 11434" -Direction Inbound -Protocol TCP -LocalPort 11434 -Action Allow
```

### گام ۴ — دانلود و اجرای مدل

```powershell
ollama pull qwen3:8b      # دانلود حدود 5.2GB — چند دقیقه طول می‌کشد
ollama run qwen3:8b       # اجرای محیط چت تعاملی
```

یک تست سریع در محیط چت:

```
>>> /set nothink
>>> سلام! خودت را در دو جمله به فارسی معرفی کن.
```

### گام ۵ — بررسی وضعیت

```powershell
ollama list                        # لیست مدل‌های دانلودشده
ollama ps                          # مدل‌های لودشده در RAM
Invoke-WebRequest http://localhost:11434/api/tags   # تست سلامت API
```

## ۴) استفاده در برنامه‌ها

Ollama بعد از اجرا یک **API سازگار با OpenAI** روی پورت `11434` ارائه می‌دهد؛ یعنی تقریباً هر کتابخانه و ابزاری که با OpenAI کار می‌کند، بدون تغییر اساسی با مدل محلی شما هم کار می‌کند.

### ۴.۱) REST API (curl / هر زبانی)

```bash
curl http://localhost:11434/api/chat -d '{
  "model": "qwen3:8b",
  "think": false,
  "messages": [
    { "role": "system", "content": "تو یک دستیار فارسی‌زبان هستی." },
    { "role": "user", "content": "سلام! در دو جمله خودت را معرفی کن." }
  ],
  "stream": false
}'
```

نقطه پایانی سازگار با OpenAI: `http://localhost:11434/v1/chat/completions` (مقدار API Key هر چیزی می‌تواند باشد).

### ۴.۲) Python — مثال کامل و چت جریانی

فایل آماده: [examples/python_chat.py](examples/python_chat.py)

```python
# pip install openai
from openai import OpenAI

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

response = client.chat.completions.create(
    model="qwen3:8b",
    messages=[
        {"role": "system", "content": "تو یک دستیار فارسی‌زبان، دقیق و مودب هستی."},
        {"role": "user", "content": "سلام! در دو جمله خودت را معرفی کن."},
    ],
    extra_body={"think": False},  # پاسخ سریع بدون مرحله تفکر
)
print(response.choices[0].message.content)
```

### ۴.۳) Node.js

فایل آماده: [examples/node_chat.js](examples/node_chat.js)

```javascript
// Node.js 18+
const res = await fetch("http://localhost:11434/api/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    model: "qwen3:8b",
    think: false,
    messages: [{ role: "user", content: "سلام! به فارسی جواب بده." }],
    stream: false,
  }),
});
const data = await res.json();
console.log(data.message.content);
```

### ۴.۴) سرویس وب با FastAPI (برای اتصال اپلیکیشن‌های خودتان)

فایل آماده: [examples/fastapi_app.py](examples/fastapi_app.py)

```powershell
pip install fastapi uvicorn openai
uvicorn fastapi_app:app --host 0.0.0.0 --port 8000
```

سپس هر برنامه‌ای می‌تواند `POST http://SERVER_IP:8000/chat` با بدنه `{"text": "سلام"}` صدا بزند.

### ۴.۵) تست سریع با PowerShell

فایل آماده: [examples/test_api.ps1](examples/test_api.ps1) — زمان پاسخ و سرعت توکن/ثانیه را هم اندازه می‌گیرد.

### ۴.۶) اجرای Docker (گزینه جایگزین)

فایل آماده: [examples/docker-compose.yml](examples/docker-compose.yml)

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    ports: ["11434:11434"]
    volumes: ["ollama_data:/root/.ollama"]
    environment:
      - OLLAMA_KEEP_ALIVE=-1
      - OLLAMA_NUM_PARALLEL=1
      - OLLAMA_FLASH_ATTENTION=1
      - OLLAMA_KV_CACHE_TYPE=q8_0
    restart: unless-stopped
volumes:
  ollama_data:
```

> توجه: روی ویندوز سرور، Docker Desktop خودش ۱ تا ۲ گیگ RAM اضافه مصرف می‌کند. چون این سرور RAM آزاد محدودی دارد، **نصب بومی Ollama (بخش ۳) توصیه می‌شود** و Docker را برای زمانی بگذارید که بقیه سرویس‌ها بسته باشند.

## ۵) مدل فارسی‌محور Dorna2 (اختیاری)

اگر خروجی کاملاً بومی فارسی برایتان مهم‌تر از تنوع زبانی است، مدل **Dorna2-Llama3.1-8B-Instruct** شرکت Part AI که روی داده فارسی آموزش دیده را می‌توانید به Ollama اضافه کنید:

1. فایل GGUF کوانتیزه Q4_K_M را از HuggingFace دانلود کنید (جستجو: `Dorna2-Llama3.1-8B-Instruct GGUF`، حجم ~4.9GB).
2. کنار فایل، یک فایل متنی به نام `Modelfile` بسازید:

```
FROM ./dorna2-llama3.1-8b-instruct-q4_k_m.gguf
SYSTEM """تو یک دستیار فارسی‌زبان هستی."""
```

3. مدل را وارد و اجرا کنید:

```powershell
ollama create dorna2 -f Modelfile
ollama run dorna2
```

## ۶) نکات کارایی روی CPU

- **سرعت انتظاری:** برای Qwen3-8B با کوانتیزه Q4 روی این سرور حدود ۶ تا ۱۲ توکن بر ثانیه. برای پاسخ سریع‌تر حتماً `think:false` را فعال کنید یا از `qwen3:4b` استفاده کنید.
- **RAM:** با `OLLAMA_KV_CACHE_TYPE=q8_0` و `OLLAMA_FLASH_ATTENTION=1` مصرف RAM حافظه موقت تقریباً نصف می‌شود.
- **همزمانی:** روی CPU تعداد درخواست موازی را روی ۱ نگه دارید (`OLLAMA_NUM_PARALLEL=1`)؛ صف‌بندی درخواست‌ها تجربه بهتری می‌دهد.
- **بقا در حافظه:** `OLLAMA_KEEP_ALIVE=-1` باعث می‌شود مدل همیشه در RAM بماند و هر درخواست ۱۰ تا ۳۰ ثانیه تأخیر بارگذاری نداشته باشد.
- **قبل از نصب مدل ۱۲B یا ۱۴B:** Docker Desktop و ClamAV را ببندید تا حدود ۱۱GB RAM آزاد شود.

## ۷) عیب‌یابی

| مشکل | راه‌حل |
|---|---|
| خطای کمبود RAM هنگام لود مدل | مدل کوچک‌تر (`qwen3:4b`)، بستن Docker/ClamAV، کاهش `OLLAMA_CONTEXT_LENGTH` به 4096 |
| پاسخ‌دهی خیلی کند | `think:false`، مدل 4B، اطمینان از `OLLAMA_NUM_PARALLEL=1` |
| از سیستم دیگر به API دسترسی نیست | بررسی `OLLAMA_HOST=0.0.0.0`، قانون فایروال پورت 11434، ری‌استارت Ollama |
| خطای illegal instruction هنگام اجرا | CPU مجازی QEMU ممکن است دستورهای AVX2 را پاس نداده باشد؛ تنظیم CPU میزبان را روی host-passthrough بگذارید |
| پورت 11434 اشغال است | برنامه دیگری روی این پورت را پیدا و متوقف کنید یا `OLLAMA_HOST=0.0.0.0:11435` بگذارید |

## ۸) امنیت

- **هرگز توکن، کلید API یا رمز را داخل کد و مخزن کامیت نکنید.** توکن GitHub که در مکالمه به اشتراک گذاشته شد، نباید در هیچ فایلی از این مخزن ذخیره شود و پس از اتمام کار باید از GitHub (Settings > Developer settings > Personal access tokens) باطل شود.
- API مدل را فقط داخل شبکه داخلی ارائه دهید؛ پورت 11434 را مستقیم روی اینترنت باز نکنید.
- برای محدودسازی دسترسی، جلوی API یک Reverse Proxy با احراز هویت (مثلاً Nginx یا Caddy) بگذارید.

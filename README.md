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

## ۷) برنامه تست سرعت و کیفیت (Benchmark)

برنامه [benchmark/bench_app.py](benchmark/bench_app.py) مدل شما را محک می‌زند — فقط با پایتون استاندارد (بدون نصب هیچ پکیجی):

```powershell
python benchmark/bench_app.py              # تست کامل: سرعت + کیفیت + ذخیره گزارش
python benchmark/bench_app.py --speed      # فقط تست سرعت (کوتاه/متوسط/بلند)
python benchmark/bench_app.py --quality    # فقط ۱۰ تست کیفیت فارسی
python benchmark/bench_app.py --think      # مقایسه سرعت با/بدون حالت تفکر
python benchmark/bench_app.py --chat       # چت تعاملی با نمایش توکن/ثانیه هر پاسخ
python benchmark/bench_app.py --server 192.168.1.10   # تست مدل از یک سیستم دیگر
```

**چه چیزی اندازه‌گیری می‌شود؟**

- سرعت: توکن/ثانیه، زمان تا اولین توکن (TTFT)، زمان لود سرد مدل، برای سه طول پاسخ کوتاه/متوسط/بلند
- کیفیت: ۱۰ تست فارسی — دانش عمومی، خلاصه‌سازی، ترجمه دوطرفه، استدلال عددی، خروجی JSON، نگارش ایمیل، تحلیل حس، دستورپیروی و حافظه مکالمه چند نوبته
- خروجی: جدول رنگی در کنسول + گزارش کامل Markdown و داده خام JSON در پوشه `benchmark/reports/` + توصیه‌های خودکار بر اساس نتایج

نکته: اگر در کنسول قدیمی ویندوز متن فارسی به‌هم ریخت، اول `chcp 65001` را اجرا کنید یا از Windows Terminal / PowerShell 7 استفاده کنید.

> نتیجه تست واقعی روی سرور هدف (آبان ۱۴۰۵): میانگین سرعت **۴.۳ توکن/ثانیه** (TTFT حدود ۴ ثانیه، لود سرد ۱۱ ثانیه) و کیفیت فارسی **۲۳ از ۲۳** — کیفیت فارسی عالی است؛ سرعت با چت استریم تجربه روانی دارد و برای پاسخ سریع‌تر می‌توانید `qwen3:4b` را هم امتحان کنید.

## ۸) چت وب آنلاین و API با توکن (پورت 8093)

برنامه [chat_server/chat_server.py](chat_server/chat_server.py) یک **چت وب فارسی** با پاسخ استریمی، **تم شب/روز**، هویت «دستیار هوش مصنوعی مرکز مشاور رز»، پاسخ خودکار از محتوای وب‌سایت مرکز، **جستجوی وب (DuckDuckGo)**، **ایجنت‌های تخصصی روان‌شناسی**، **تحلیل عکس با مدل بینایی**، **پیوست فایل (Word/Excel/PDF/عکس)**، **اجرای کد HTML و رسم نمودار فرایند**، **تاریخچه ماندگار**، **API سازگار با OpenAI و سیستم توکن** ارائه می‌دهد — فقط پایتون استاندارد، بدون نصب هیچ پکیجی.

### اجرای سریع (تست)

```powershell
cd C:\Users\Administrator\llm_rose
git pull
python chat_server\chat_server.py --port 8093
```

سپس در مرورگر: `http://<IP-سرور>:8093` — چت را باز کنید؛ زیر هر پاسخ، سرعت لحظه‌ای (توکن/ثانیه) نمایش داده می‌شود.

### امکانات صفحه چت

| امکان | توضیح |
|---|---|
| 💬 گفتگوهای جدید | دکمه «＋ گفتگوی جدید» + سایدبار لیست گفتگوها با حذف تک‌تک |
| 🕘 تاریخچه | گفتگوها روی سرور (پوشه `chat_server\data\history\`) و در مرورگر ذخیره می‌شوند و با تغییر مرورگر/دستگاه باقی می‌مانند |
| 📎 پیوست فایل | عکس (png/jpg/webp)، Word (docx)، Excel (xlsx)، PowerPoint (pptx)، PDF و فایل‌های متنی (txt/csv/md/json/…) تا ۸ مگابایت؛ متن فایل استخراج و به پاسخ مدل اضافه می‌شود |
| 🖼 تحلیل عکس | عکس‌ها به‌صورت خودکار به مدل بینایی مسیریابی می‌شوند (پیش‌فرض `qwen2.5vl:3b`؛ قابل تغییر با کلید `vision_model` یا پارامتر `-VisionModel` نصب‌کننده). اگر مدل بینایی نصب نباشد، پیام راهنما با دستور pull نمایش داده می‌شود |
| ▶ اجرای کد | بلوک‌های HTML/SVG و JavaScript دکمه «اجرا ▶» دارند: پیش‌نمایش در iframe امن و خروجی console جاوااسکریپت زیر کد نمایش داده می‌شود |
| 📊 نمودار فرایند | اگر «فلوچارت/نمودار/فرایند» بخواهید، مدل بلوک ```mermaid می‌سازد و صفحه همان لحظه آن را به نمودار SVG تبدیل می‌کند (دکمه نمایش کد/نمودار) |
| 📋 کپی | دکمه کپی روی هر پاسخ و هر بلوک کد |
| 🌙 تم شب/روز + انتخاب مدل | تم تیره/روشن با ذخیره انتخاب؛ سوییچ مدل (مثلاً `qwen3:4b` برای سرعت بیشتر) از نوار بالا |
| 🌐 جستجوی وب | دکمه «جستجوی وب» بالای چت: با روشن‌شدن، مدل قبل از پاسخ در DuckDuckGo جستجو می‌کند و ۲ صفحه اول را می‌خواند و پاسخ را با ذکر منبع [۱] [۲] می‌دهد. لینک‌هایی که در پیام بگذارید همیشه خوانده می‌شوند؛ عبارت‌هایی مثل «جستجو کن» یا «آخرین اخبار» هم جستجو را خودکار روشن می‌کنند |
| 🧑‍⚕️ ایجنت‌های تخصصی | منوی «انتخاب مشاور» بالای چت: ۷ ایجنت آماده (عمومی، روان‌شناس بالینی، خانواده و زوج، کودک و نوجوان، CBT، تحصیلی/شغلی، همراه بحران) با پرامپت حرفه‌ای و محدودیت‌های اخلاقی (بدون تشخیص/تجویز، ارجاع در بحران) |
| ⚡ بهینه‌سازی سرعت | `think:false` (حذف توکن‌های پنهان حالت تفکر Qwen3)، `keep_alive:-1` (مدل همیشه در RAM)، سقف طول پاسخ و بودجه متن تاریخچه — همه به‌صورت پیش‌فرض فعال‌اند |

### تم شب/روز

در نوار بالای چت دکمه 🌙/☀️ قرار دارد؛ با یک کلیک بین **تم شب** (تیره) و **تم روز** (روشن) جابه‌جا شوید. انتخاب کاربر در مرورگر او ذخیره می‌شود (`localStorage`) و در بازدید بعدی همان تم اعمال می‌شود؛ اگر کاربر تمی انتخاب نکرده باشد، تم پیش‌فرض سیستم‌عامل او (dark/light) به‌صورت خودکار تشخیص داده می‌شود.

### هویت دستیار و پاسخ از محتوای وب‌سایت مرکز مشاور رز

دستیار خودش را **«دستیار هوش مصنوعی مرکز مشاور رز»** معرفی می‌کند و برای پرسش‌های مرتبط با سایت مرکز (خدمات، قیمت‌ها، شعبه‌ها، نحوه نوبت‌دهی و…) از **پایگاه دانش خودکار** استفاده می‌کند:

- ماژول [chat_server/site_kb.py](chat_server/site_kb.py) محتوای `site_url` (پیش‌فرض: `http://130.185.73.157/`) را می‌خواند: صفحه اصلی، متن‌های فارسی داخل باندل JS سایت (سوالات متداول، توضیح خدمات…) و **APIهای عمومی سایت** (فهرست خدمات با قیمت، شعبه‌ها با آدرس/تلفن و مشاوران هر شعبه).
- نتیجه در `chat_server\data\site_kb.json` ذخیره می‌شود (حدود ۶۰ قطعه دانش).
- در هر پرسش، فقط **بخش‌های مرتبط** انتخاب و به پرامپت مدل اضافه می‌شود (RAG سبک)؛ برای سلام‌واحوال و پرسش‌های عمومی چیزی اضافه نمی‌شود تا سرعت پایین بیاید.
- **به‌روزرسانی خودکار** هر ۱۲ ساعت در پس‌زمینه؛ به‌روزرسانی دستی:

```powershell
python chat_server\chat_server.py refresh-site
```

تنظیمات اختیاری در `chat_server\data\config.json`:

| کلید | پیش‌فرض | توضیح |
|---|---|---|
| `system_prompt` | پرامپت هویت مرکز مشاور رز | متن کامل نقش دستیار (قابل ویرایش) |
| `app_title` | `دستیار هوشمند رز` | عنوان نوار بالای چت و تب مرورگر |
| `site_url` | `http://130.185.73.157/` | وب‌سایتی که پایگاه دانش از آن ساخته می‌شود |
| `site_kb` | `true` | روشن/خاموش‌کردن پاسخ از محتوای سایت |
| `site_kb_refresh_hours` | `12` | فاصله به‌روزرسانی خودکار پایگاه دانش |
| `kb_context_chars` | `1800` | حداکثر طول اطلاعات تزریقی به هر پاسخ |
| `vision_model` | `qwen2.5vl:3b` | مدل بینایی برای تحلیل عکس (یا پارامتر `--vision-model`) |
| `web_search` | `true` | اجازه جستجوی وب (DuckDuckGo) |
| `search_max_pages` | `2` | چند نتیجه اول کامل خوانده شود |
| `search_timeout` | `9` | مهلای هر درخواست وب به ثانیه |

> نکته: اگر قبلاً سرور را اجرا کرده‌اید، `config.json` شما به‌صورت خودکار به هویت جدید مهاجرت می‌کند؛ نیازی به ویرایش دستی نیست.

### نصب دائمی (شروع خودکار با ویندوز + فایروال + توکن اول)

```powershell
powershell -ExecutionPolicy Bypass -File chat_server\install_service.ps1 -Action install -Port 8093 -SetOllamaEnv
```

- `-SetOllamaEnv` متغیرهای بهینه (`OLLAMA_KEEP_ALIVE=-1` و ...) را ثبت می‌کند تا مدل همیشه در RAM بماند و تأخیر ۱۱ ثانیه‌ای پاسخ اول حذف شود. **برای تأثیر کامل، بعد از اجرای این فرمان یک بار Ollama را هم ری‌استارت کنید** (یا سرور را). اگر قبلاً بدون این سوییچ نصب کرده‌اید، همین فرمان را دوباره بزنید و Ollama را ری‌استارت کنید.
- برای فعال‌کردن تحلیل عکس، مدل بینایی را یک بار بکشید و سرویس را با آن نصب کنید:

```powershell
ollama pull qwen2.5vl:3b
powershell -ExecutionPolicy Bypass -File chat_server\install_service.ps1 -Action install -Port 8093 -SetOllamaEnv -VisionModel qwen2.5vl:3b
```
- سرویس با حساب **SYSTEM** ثبت می‌شود؛ یعنی با بستن RDP یا ری‌استارت ویندوز از کار نمی‌افتد و بعد از هر بوت خودش بالا می‌آید.
- بعد از هر `git pull` برای اعمال کد جدید فقط سرویس را ری‌استارت کنید:

```powershell
powershell -ExecutionPolicy Bypass -File chat_server\install_service.ps1 -Action restart -Port 8093
```

- اگر سایت یا `/health` باز نمی‌شود، عیب‌یابی گام‌به‌گام:

```powershell
powershell -ExecutionPolicy Bypass -File chat_server\install_service.ps1 -Action diagnose -Port 8093
```

- حذف سرویس: `-Action remove` — بررسی وضعیت: `-Action status`

### ساخت و مدیریت توکن API

```powershell
python chat_server\chat_server.py add-token --name "اپ-موبایل"   # توکن lr_... فقط یک‌بار نمایش داده می‌شود
python chat_server\chat_server.py list-tokens                     # لیست توکن‌ها + آمار مصرف
python chat_server\chat_server.py revoke <شناسه>                  # ابطال توکن
python chat_server\chat_server.py show-admin-key                  # کلید ادمین برای مسیرهای /admin
```

توکن‌ها فقط به‌صورت هش SHA-256 ذخیره می‌شوند. ساخت توکن از راه دور هم ممکن است: `POST /admin/tokens` با هدر `X-Admin-Key` و بدنه `{"name":"..."}` — و ابطال با `POST /admin/tokens/revoke` و بدنه `{"id":"..."}`.

### استفاده از API (سازگار با OpenAI) در برنامه‌ها

```python
from openai import OpenAI

client = OpenAI(base_url="http://130.185.73.157:8093/v1", api_key="lr_xxxxxxxxxxxx")
r = client.chat.completions.create(
    model="qwen3:8b",
    messages=[{"role": "user", "content": "سلام"}],
)
print(r.choices[0].message.content)
```

با curl:

```bash
curl http://130.185.73.157:8093/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer lr_xxxxxxxxxxxx" \
  -d '{"model":"qwen3:8b","messages":[{"role":"user","content":"سلام"}]}'
```

پاسخ استریم هم پشتیبانی می‌شود: `"stream": true` (فرمت SSE استاندارد OpenAI با `data: [DONE]`).

### نکات امنیتی

- اگر سرورتان فایروال بیرونی دارد (پنل شرکت میزبانی/کلود)، پورت 8093 را آنجا هم باز کنید.
- API همیشه نیازمند توکن است (پیش‌فرض ۳۰ درخواست/دقیقه برای هر توکن). صفحه چت تا زمانی که تست تمام نشده عمومی است (۱۰ درخواست/دقیقه برای هر IP)؛ برای قفل‌کردن آن در `chat_server\data\config.json` مقدار `chat_public` را `false` کنید و سرور را دوباره اجرا کنید.
- پوشه `chat_server\data\` شامل کلید ادمین و هش توکن‌هاست؛ هرگز آن را کامیت یا به اشتراک نگذارید (در .gitignore است).

## ۹) عیب‌یابی

| مشکل | راه‌حل |
|---|---|
| سایت چت یا `/health` باز نمی‌شود (ERR_CONNECTION_TIMED_OUT) | روی سرور: `powershell -ExecutionPolicy Bypass -File chat_server\install_service.ps1 -Action diagnose -Port 8093`. اگر سرویس اجرا نیست: `-Action restart`. اگر همه موارد سبز بود، پورت 8093 را در پنل فایروال شرکت میزبانی هم باز کنید |
| سرویس بعد از بستن RDP یا ری‌استارت ویندوز از کار افتاده | نسخه‌های قدیمی نصب‌کننده، تسک را با حساب کاربری ثبت می‌کردند. یک بار `-Action install` را دوباره اجرا کنید تا سرویس با حساب SYSTEM ثبت شود |
| خطای کمبود RAM هنگام لود مدل | مدل کوچک‌تر (`qwen3:4b`)، بستن Docker/ClamAV، کاهش `OLLAMA_CONTEXT_LENGTH` به 4096 |
| پاسخ‌دهی خیلی کند | `think:false`، مدل 4B، اطمینان از `OLLAMA_NUM_PARALLEL=1` |
| از سیستم دیگر به API دسترسی نیست | بررسی `OLLAMA_HOST=0.0.0.0`، قانون فایروال پورت 11434، ری‌استارت Ollama |
| خطای illegal instruction هنگام اجرا | CPU مجازی QEMU ممکن است دستورهای AVX2 را پاس نداده باشد؛ تنظیم CPU میزبان را روی host-passthrough بگذارید |
| پورت 11434 اشغال است | برنامه دیگری روی این پورت را پیدا و متوقف کنید یا `OLLAMA_HOST=0.0.0.0:11435` بگذارید |

## ۱۰) امنیت

- **هرگز توکن، کلید API یا رمز را داخل کد و مخزن کامیت نکنید.** توکن GitHub که در مکالمه به اشتراک گذاشته شد، نباید در هیچ فایلی از این مخزن ذخیره شود و پس از اتمام کار باید از GitHub (Settings > Developer settings > Personal access tokens) باطل شود.
- API مدل را فقط داخل شبکه داخلی ارائه دهید؛ پورت 11434 را مستقیم روی اینترنت باز نکنید.
- برای محدودسازی دسترسی، جلوی API یک Reverse Proxy با احراز هویت (مثلاً Nginx یا Caddy) بگذارید.

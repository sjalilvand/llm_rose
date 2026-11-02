#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM Rose — سرور چت وب آنلاین + API سازگار با OpenAI همراه با مدیریت توکن
=======================================================================

امکانات:
  - صفحه چت وب فارسی (RTL) با پاسخ جریانی (استریم) روی پورت دلخواه (پیش‌فرض 8093)
  - تم شب/روز با دکمه تغییر فوری (ذخیره در مرورگر کاربر)
  - هویت «دستیار هوش مصنوعی کلینیک رز» + پاسخ خودکار از محتوای وب‌سایت کلینیک
    (پایگاه دانش خودکار از صفحه اصلی، باندل JS سایت و APIهای عمومی — ماژول site_kb.py)
  - API سازگار با OpenAI:  POST /v1/chat/completions  و  GET /v1/models
  - سیستم توکن API (lr_...) با ساخت/لیست/ابطال و آمار مصرف هر توکن
  - محدودیت نرخ درخواست (per-token و per-IP برای صفحه عمومی)
  - فقط کتابخانه استاندارد پایتون — بدون نیاز به pip

اجرا:
    python chat_server.py                          # پورت 8093، مدل qwen3:8b
    python chat_server.py --port 8093 --model qwen3:8b --ollama http://localhost:11434

مدیریت توکن:
    python chat_server.py add-token --name "اپ موبایل"
    python chat_server.py list-tokens
    python chat_server.py revoke <شناسه>
    python chat_server.py show-admin-key

پایگاه دانش سایت:
    python chat_server.py refresh-site             # به‌روزرسانی دستی دانش سایت
    (به‌روزرسانی خودکار هر ۱۲ ساعت؛ با کلید site_kb_refresh_hours در config.json)

پس‌از اجرا:
    صفحه چت:        http://<IP-سرور>:8093
    سلامت سرویس:    http://<IP-سرور>:8093/health
    API:            http://<IP-سرور>:8093/v1/chat/completions  (با هدر Authorization: Bearer lr_...)
    پنل مدیریت:     POST /admin/tokens با هدر X-Admin-Key
"""

import argparse
import hashlib
import json
import os
import secrets
import socket
import sys
import threading
import time
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib import request as urlreq
from urllib.error import HTTPError, URLError

# ماژول پایگاه دانش سایت — اگر کنار سرور نباشد، سرور بدون آن هم کار می‌کند
try:
    import site_kb
except ImportError:
    site_kb = None

if sys.platform == "win32":
    os.system("")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent

# پرامپت پیش‌فرض نسخه‌های قبلی — برای مهاجرت خودکار config.json کاربران قدیمی
LEGACY_DEFAULT_PROMPT = ("تو یک دستیار فارسی‌زبان، دقیق و مودب هستی. "
                         "پاسخ‌ها کوتاه، مفید و به زبان فارسی باشند.")

DEFAULT_SITE_URL = "http://130.185.73.157/"
DEFAULT_APP_TITLE = "دستیار هوشمند رز"

# هویت دستیار: با کلید system_prompt در config.json قابل تغییر است
DEFAULT_SYSTEM_PROMPT = (
    "تو «دستیار هوشمند رز» هستی؛ دستیار هوش مصنوعیِ شرکت مشاوره رز — کلینیک تخصصی مشاوره و روان‌درمانی (رزپسی).\n"
    "هرگاه از تو پرسیدند «تو کیستی؟»، خودت را این‌گونه معرفی کن:\n"
    "«من دستیار هوش مصنوعی کلینیک رز هستم؛ برای راهنمایی درباره خدمات مشاوره و روان‌درمانی، "
    "نوبت‌دهی آنلاین، شعبه‌ها و پاسخ به پرسش‌های شما در خدمتم.»\n"
    "قواعد پاسخ‌گویی:\n"
    "۱) همیشه فارسی، کوتاه، گرم و حرفه‌ای بنویس.\n"
    "۲) درباره خدمات، قیمت‌ها، شعبه‌ها و نوبت‌دهی فقط از «اطلاعات رسمی وب‌سایت» که در پیام سامانه ارسال می‌شود "
    "استفاده کن؛ عدد، قیمت یا آدرس از خودت نساز.\n"
    "۳) اگر پاسخ در اطلاعات رسمی نبود، صادقانه بگو و کاربر را به فرم درخواست مشاوره در سایت یا تماس با پذیرش هدایت کن.\n"
    "۴) برای رزرو نوبت، کاربر را به بخش نوبت‌دهی آنلاین سایت هدایت کن.\n"
    "۵) پرسش‌های عمومی روان‌شناسی را ساده و با احتیاط پاسخ بده؛ تشخیص و تجویز درمان مخصوص متخصص است. "
    "در موارد بحرانی (مانند افکار خودآسیبی) فوراً به اورژانس ۱۲۳ یا پذیرش کلینیک ارجاع بده."
)

KB_CONTEXT_HEADER = ("\n\n=== اطلاعات رسمی وب‌سایت کلینیک (مبنای پاسخ به این پرسش) ===\n")
KB_CONTEXT_FOOTER = ("\n=== پایان اطلاعات وب‌سایت ===\n"
                     "برای خدمات، قیمت، آدرس شعبه‌ها و نوبت‌دهی فقط بر اساس همین اطلاعات پاسخ بده؛ "
                     "اگر پاسخ کامل در این اطلاعات نبود، کاربر را به فرم درخواست مشاوره یا پذیرش هدایت کن.")

# =====================================================================
# تنظیمات (ذخیره در data/config.json — کلید ادمین در اولین اجرا ساخته می‌شود)
# =====================================================================
def load_settings(args):
    data_dir = Path(getattr(args, "data_dir", None) or (BASE_DIR / "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = data_dir / "config.json"

    cfg = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}

    s = SimpleNamespace()
    s.data_dir = data_dir
    s.host = getattr(args, "host", None) or "0.0.0.0"
    s.port = int(getattr(args, "port", None) or cfg.get("port", 8093))
    s.ollama = (getattr(args, "ollama", None) or cfg.get("ollama", "http://localhost:11434")).rstrip("/")
    s.model = getattr(args, "model", None) or cfg.get("model", "qwen3:8b")
    s.ctx = int(getattr(args, "ctx", None) or cfg.get("ctx", 8192))
    s.max_output_tokens = int(cfg.get("max_output_tokens", 1024))
    s.rate_web_per_min = int(cfg.get("rate_web_per_min", 10))
    s.rate_token_per_min = int(cfg.get("rate_token_per_min", 30))
    s.chat_public = cfg.get("chat_public", True)
    if getattr(args, "private", False):
        s.chat_public = False
    sp = cfg.get("system_prompt")
    if sp and sp.strip() == LEGACY_DEFAULT_PROMPT.strip():
        sp = None  # پرامپت پیش‌فرض قدیمی → مهاجرت به پرامپت هویت جدید
    s.system_prompt = sp or DEFAULT_SYSTEM_PROMPT

    # وب‌سایت و پایگاه دانش (RAG سبک)
    s.site_url = ((getattr(args, "site_url", None) or cfg.get("site_url", DEFAULT_SITE_URL))
                  or DEFAULT_SITE_URL).rstrip("/") + "/"
    s.app_title = cfg.get("app_title", DEFAULT_APP_TITLE)
    s.site_kb_enabled = bool(cfg.get("site_kb", True))
    s.site_kb = s.site_kb_enabled and (site_kb is not None)
    s.site_kb_refresh_hours = float(cfg.get("site_kb_refresh_hours", 12))
    s.kb_context_chars = int(cfg.get("kb_context_chars", 1800))
    s.admin_key = cfg.get("admin_key") or secrets.token_hex(16)

    cfg.update({
        "port": s.port, "ollama": s.ollama, "model": s.model, "ctx": s.ctx,
        "max_output_tokens": s.max_output_tokens,
        "rate_web_per_min": s.rate_web_per_min,
        "rate_token_per_min": s.rate_token_per_min,
        "chat_public": s.chat_public, "system_prompt": s.system_prompt,
        "site_url": s.site_url, "app_title": s.app_title,
        "site_kb": s.site_kb_enabled, "site_kb_refresh_hours": s.site_kb_refresh_hours,
        "kb_context_chars": s.kb_context_chars,
        "admin_key": s.admin_key,
    })
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    # صفحه HTML با عنوان و آدرس سایت پر می‌شود (یک‌بار در شروع)
    s.html_page = HTML_PAGE.replace("__APP_TITLE__", s.app_title).replace("__SITE_URL__", s.site_url)
    return s


# =====================================================================
# ذخیره‌گاه توکن — فقط هش توکن ذخیره می‌شود؛ توکن کامل یک‌بار نمایش داده می‌شود
# =====================================================================
class TokenStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.tokens = []
        self._mtime = 0.0
        self._load()
        self._save()

    def _load(self):
        """بارگذاری از فایل (تا توکن‌های ساخته‌شده توسط CLI در سرور درحال‌اجرا هم دیده شوند)"""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.tokens = data.get("tokens", [])
            self._mtime = self.path.stat().st_mtime
        except Exception:
            pass

    def _maybe_reload(self):
        """اگر فایل توسط فرایند دیگری (CLI) تغییر کرده باشد، دوباره بخوان"""
        try:
            if self.path.stat().st_mtime > self._mtime:
                self._load()
        except FileNotFoundError:
            pass

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": 1, "tokens": self.tokens},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
        try:
            self._mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            pass

    def create(self, name):
        raw = "lr_" + secrets.token_urlsafe(24)
        rec = {
            "id": secrets.token_hex(4),
            "name": name or "token",
            "prefix": raw[:9],
            "hash": hashlib.sha256(raw.encode()).hexdigest(),
            "created": datetime.now().isoformat(timespec="seconds"),
            "revoked": False,
            "requests": 0,
            "tokens_out": 0,
            "last_used": "",
        }
        with self.lock:
            self.tokens.append(rec)
            self._save()
        return raw, rec

    def verify(self, raw):
        if not raw:
            return None
        h = hashlib.sha256(raw.encode()).hexdigest()
        with self.lock:
            self._maybe_reload()
            for t in self.tokens:
                if t.get("hash") == h and not t.get("revoked"):
                    return t
        return None

    def bump(self, rec, tokens_out):
        with self.lock:
            rec["requests"] = int(rec.get("requests", 0)) + 1
            rec["tokens_out"] = int(rec.get("tokens_out", 0)) + int(tokens_out or 0)
            rec["last_used"] = datetime.now().isoformat(timespec="seconds")
            self._save()

    def list(self):
        with self.lock:
            self._maybe_reload()
            return [dict(t) for t in self.tokens]

    def revoke(self, ident):
        with self.lock:
            self._maybe_reload()
            for t in self.tokens:
                if t["id"] == ident or t["prefix"] == ident:
                    t["revoked"] = True
                    self._save()
                    return t
        return None


class RateLimiter:
    """پنجره لغزان ساده در حافظه"""
    def __init__(self):
        self.lock = threading.Lock()
        self.hits = {}

    def allow(self, key, limit_per_min):
        now = time.time()
        with self.lock:
            dq = self.hits.setdefault(key, deque())
            while dq and dq[0] < now - 60.0:
                dq.popleft()
            if len(dq) >= max(int(limit_per_min), 1):
                return False
            dq.append(now)
            return True


# =====================================================================
# ارتباط با Ollama
# =====================================================================
def ollama_chat_stream(settings, messages, num_predict):
    payload = {
        "model": settings.model,
        "messages": messages,
        "stream": True,
        "think": False,  # پاسخ سریع روی CPU؛ برای سرعت حالت تفکر خاموش است
        "options": {
            "num_ctx": settings.ctx,
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "num_predict": num_predict,
        },
    }
    req = urlreq.Request(
        settings.ollama + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urlreq.urlopen(req, timeout=600)
    try:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
    finally:
        resp.close()


# =====================================================================
# صفحه چت وب (تک‌فایل، RTL، تم شب/روز)
# =====================================================================
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__APP_TITLE__ | کلینیک رز</title>
<style>
:root{--bg:#0f1117;--panel:#171a23;--panel2:#1e2230;--line:#2a2f40;--text:#e8eaf0;
--dim:#98a1b3;--accent:#e91e63;--accent2:#ff5c8d;--ok:#2ecc71;--err:#ff6b6b;
--keybar-bg:#2a1620;--shadow:none;--user-b:#c2185b;color-scheme:dark}
html[data-theme="light"]{--bg:#f3f5fa;--panel:#ffffff;--panel2:#e9edf5;--line:#d9e0ee;--text:#1d2333;
--dim:#5f6b84;--accent:#d81b60;--accent2:#e91e63;--ok:#1e9e5a;--err:#d64545;
--keybar-bg:#fdeef4;--shadow:0 1px 4px rgba(25,40,80,.10);--user-b:#ad1457;color-scheme:light}
body,header,#composer,.msg,.badge,#guide,#inp,.stats,#keybar{transition:background-color .25s ease,color .25s ease,border-color .25s ease}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--text);display:flex;flex-direction:column;
font-family:"Vazirmatn",Vazir,Tahoma,"Segoe UI",sans-serif}
header{display:flex;align-items:center;gap:10px;padding:10px 16px;background:var(--panel);
border-bottom:1px solid var(--line);flex-wrap:wrap}
.logo{width:34px;height:34px;border-radius:50%;flex:0 0 auto;
background:linear-gradient(135deg,var(--accent),#8e24aa);display:flex;align-items:center;
justify-content:center;font-weight:700;color:#fff}
h1{font-size:16px;margin:0;font-weight:600}
.badge{font-size:12px;background:var(--panel2);border:1px solid var(--line);
border-radius:20px;padding:4px 10px;color:var(--dim)}
.dot{width:9px;height:9px;border-radius:50%;background:#666;display:inline-block;margin-left:5px}
.dot.on{background:var(--ok);box-shadow:0 0 6px var(--ok)}
.spacer{flex:1}
#chat{flex:1;overflow-y:auto;padding:18px 16px;display:flex;flex-direction:column;gap:12px}
.msg{max-width:82%;padding:10px 14px;border-radius:14px;line-height:2;
white-space:pre-wrap;word-wrap:break-word;font-size:14.5px}
.user{align-self:flex-start;background:linear-gradient(135deg,var(--accent),var(--user-b));
color:#fff;border-bottom-right-radius:4px}
.bot{align-self:flex-end;background:var(--panel);border:1px solid var(--line);
border-bottom-left-radius:4px;box-shadow:var(--shadow)}
.stats{font-size:11px;color:var(--dim);align-self:flex-end;background:var(--panel2);
border:1px solid var(--line);border-radius:10px;padding:2px 8px}
#guide{margin:0 16px;background:var(--panel);border:1px solid var(--line);border-radius:12px;
font-size:12.5px;color:var(--dim)}
#guide summary{cursor:pointer;padding:8px 14px;color:var(--dim)}
#guide div{padding:0 14px 12px;line-height:2.1}
#guide pre{background:var(--bg);border:1px solid var(--line);border-radius:8px;
padding:8px 12px;overflow-x:auto;direction:ltr;text-align:left;font-size:12px}
#composer{display:flex;gap:8px;padding:12px 16px;background:var(--panel);
border-top:1px solid var(--line);align-items:flex-end}
#inp{flex:1;resize:none;background:var(--panel2);border:1px solid var(--line);color:var(--text);
border-radius:12px;padding:10px 14px;font-family:inherit;font-size:14.5px;outline:none;
max-height:140px;line-height:1.8}
#inp:focus{border-color:var(--accent)}
button{border:0;border-radius:12px;padding:10px 18px;font-family:inherit;font-size:14px;
cursor:pointer;color:#fff;background:linear-gradient(135deg,var(--accent),#c2185b)}
button:disabled{opacity:.45;cursor:not-allowed}
#stop{background:var(--panel2);border:1px solid var(--line);color:var(--dim)}
#keybar{display:none;gap:8px;padding:10px 16px;background:var(--keybar-bg);border-bottom:1px solid var(--accent)}
#keybar input{flex:1;background:var(--panel2);border:1px solid var(--line);color:var(--text);
border-radius:8px;padding:8px 12px;font-family:inherit;outline:none}
#themebtn{background:var(--panel2);border:1px solid var(--line);color:var(--text);
width:36px;height:32px;padding:0;font-size:15px;line-height:1;border-radius:10px}
#themebtn:hover{border-color:var(--accent)}
a.badge{text-decoration:none}
a.badge:hover{color:var(--accent);border-color:var(--accent)}
@media (max-width:640px){ .msg{max-width:94%} h1{font-size:14px} }
</style>
</head>
<body>
<header>
  <div class="logo" title="__APP_TITLE__">R</div>
  <h1>__APP_TITLE__</h1>
  <span class="badge"><span class="dot" id="dot"></span><span id="modelname">…</span></span>
  <span class="badge" id="speedbadge">سرعت: —</span>
  <a class="badge" href="__SITE_URL__" target="_blank" rel="noopener" title="وب‌سایت کلینیک رز">وب‌سایت کلینیک ↗</a>
  <span class="spacer"></span>
  <span class="badge" id="clearbtn" style="cursor:pointer">پاک‌کردن گفتگو</span>
  <button id="themebtn" title="تغییر تم شب/روز">🌙</button>
</header>

<div id="keybar">
  <input id="keyinp" placeholder="کلید API (lr_...) — فقط وقتی چت خصوصی است لازم می‌شود">
  <button id="keysave">ذخیره</button>
</div>

<div id="chat"><div class="msg bot" id="welcome">سلام 👋 من دستیار هوشمند کلینیک رز هستم؛ درباره خدمات، هزینه‌ها، شعبه‌ها و نوبت‌دهی آنلاین می‌توانم کمکتان کنم. بپرسید!</div></div>

<details id="guide">
  <summary>راهنمای استفاده از API (برای برنامه‌های شما)</summary>
  <div>
    این سرور یک API سازگار با OpenAI روی همان آدرس ارائه می‌دهد. ابتدا روی سرور با اجرای
    <b>python chat_server.py add-token --name test</b> یک توکن بسازید:
    <pre>curl http://<span class="host"></span>/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer lr_xxxxxxxx" \
  -d '{"model":"<span class="mname"></span>","messages":[{"role":"user","content":"سلام"}]}'</pre>
    <pre>from openai import OpenAI
client = OpenAI(base_url="http://<span class="host"></span>/v1", api_key="lr_xxxxxxxx")
r = client.chat.completions.create(
    model="<span class="mname"></span>",
    messages=[{"role":"user","content":"سلام"}])
print(r.choices[0].message.content)</pre>
  </div>
</details>

<div id="composer">
  <textarea id="inp" rows="1" placeholder="پیام خود را بنویسید…"></textarea>
  <button id="stop" hidden>توقف</button>
  <button id="send">ارسال</button>
</div>

<script>
const chat = document.getElementById("chat");
const inp = document.getElementById("inp");
const sendBtn = document.getElementById("send");
const stopBtn = document.getElementById("stop");
let messages = [];
let busy = false;
let ctl = null;

// ---------- تم شب / روز ----------
const rootEl = document.documentElement;
const themeBtn = document.getElementById("themebtn");
function applyTheme(t) {
  rootEl.setAttribute("data-theme", t);
  try { localStorage.setItem("lr_theme", t); } catch (e) {}
  themeBtn.textContent = t === "light" ? "🌙" : "☀️";
  themeBtn.title = t === "light" ? "رفتن به تم شب" : "رفتن به تم روز";
}
let savedTheme = null;
try { savedTheme = localStorage.getItem("lr_theme"); } catch (e) {}
applyTheme(savedTheme || ((window.matchMedia && matchMedia("(prefers-color-scheme: light)").matches) ? "light" : "dark"));
themeBtn.onclick = () => applyTheme(rootEl.getAttribute("data-theme") === "light" ? "dark" : "light");

fetch("/health").then(r => r.json()).then(h => {
  document.getElementById("modelname").textContent = h.model;
  document.getElementById("dot").classList.add("on");
  document.querySelectorAll(".mname").forEach(e => e.textContent = h.model);
}).catch(() => {});
document.querySelectorAll(".host").forEach(e => e.textContent = location.host);

function authHeaders() {
  const k = localStorage.getItem("lr_key");
  return k ? { "Authorization": "Bearer " + k } : {};
}
function showKeybar(show) {
  document.getElementById("keybar").style.display = show ? "flex" : "none";
}
document.getElementById("keysave").onclick = () => {
  localStorage.setItem("lr_key", document.getElementById("keyinp").value.trim());
  showKeybar(false);
};
if (localStorage.getItem("lr_key")) document.getElementById("keyinp").value = localStorage.getItem("lr_key");

function addBubble(cls, text) {
  const d = document.createElement("div");
  d.className = "msg " + cls;
  d.textContent = text;
  chat.appendChild(d);
  scrollDown();
  return d;
}
function scrollDown() { chat.scrollTop = chat.scrollHeight; }

const welcomeEl = document.getElementById("welcome");
document.getElementById("clearbtn").onclick = () => {
  if (busy) return;
  messages = []; chat.innerHTML = "";
  if (welcomeEl) chat.appendChild(welcomeEl);
};

function setBusy(b) {
  busy = b;
  sendBtn.disabled = b;
  stopBtn.hidden = !b;
}

async function send() {
  const text = inp.value.trim();
  if (!text || busy) return;
  inp.value = ""; inp.style.height = "auto";
  messages.push({ role: "user", content: text });
  addBubble("user", text);
  setBusy(true);
  const bot = addBubble("bot", "در حال نوشتن…");
  ctl = new AbortController();
  const t0 = performance.now();
  let ttft = null, buf = "", full = "";

  try {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, authHeaders()),
      body: JSON.stringify({ messages: messages }),
      signal: ctl.signal
    });
    if (res.status === 401) { showKeybar(true); bot.textContent = "این چت خصوصی است؛ کلید API را در نوار بالا وارد کنید."; bot.classList.add("errm"); throw new Error("auth"); }
    if (res.status === 429) { bot.textContent = "تعداد درخواست‌ها زیاد است؛ کمی صبر کنید و دوباره بفرستید."; bot.classList.add("errm"); throw new Error("429"); }
    if (!res.ok) { bot.textContent = "خطای سرور: " + res.status; bot.classList.add("errm"); throw new Error("http"); }

    const reader = res.body.getReader();
    const dec = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, idx); buf = buf.slice(idx + 2);
        const line = block.split("\n").find(l => l.startsWith("data: "));
        if (!line) continue;
        let obj; try { obj = JSON.parse(line.slice(6)); } catch (e) { continue; }
        if (obj.error) { bot.textContent = (full ? full + "\n" : "") + "خطا: " + obj.error; bot.classList.add("errm"); }
        if (obj.content) {
          if (ttft === null) { ttft = performance.now() - t0; bot.textContent = ""; }
          full += obj.content;
          bot.textContent = full;
          scrollDown();
        }
        if (obj.done && obj.stats) {
          const chip = document.createElement("div");
          chip.className = "stats";
          chip.textContent = obj.stats.tps + " توکن/ثانیه — " + obj.stats.tokens + " توکن — شروع پاسخ: " + obj.stats.ttft + " ثانیه";
          chat.appendChild(chip);
          document.getElementById("speedbadge").textContent = "سرعت: " + obj.stats.tps + " tok/s";
          scrollDown();
        }
      }
    }
    if (full) messages.push({ role: "assistant", content: full });
  } catch (e) {
    if (e.name !== "AbortError" && !full) {
      bot.textContent = "خطا در ارتباط با سرور. سرویس مدل را بررسی کنید.";
      bot.classList.add("errm");
    }
  }
  setBusy(false);
  scrollDown();
}

sendBtn.onclick = send;
stopBtn.onclick = () => { if (ctl) ctl.abort(); setBusy(false); };
inp.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
});
inp.addEventListener("input", () => {
  inp.style.height = "auto";
  inp.style.height = Math.min(inp.scrollHeight, 140) + "px";
});
</script>
</body>
</html>
"""


# =====================================================================
# هندلر HTTP
# =====================================================================
def build_handler(settings, store, limiter, boot_ts):
    MAX_BODY = 262144  # 256KB

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "LLMRose/1.1"

        # ---------- مقاوم‌سازی اتصال (قطع ناگهانی مرورگر/هلت‌چک نباید Traceback چاپ کند) ----------
        def handle(self):
            try:
                BaseHTTPRequestHandler.handle(self)
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError):
                self.close_connection = True

        # ---------- ابزارهای پایه ----------
        def log_message(self, fmt, *args):
            if args and isinstance(args[0], str) and "/health" in args[0]:
                return  # لاگ هلت‌چک‌های پرتکرار نمایش داده نشود
            print(f"{datetime.now().strftime('%H:%M:%S')} | {self.client_address[0]} | {fmt % args}",
                  flush=True)

        def _json(self, code, obj):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")  # برای تست؛ در محیط تولید محدود کنید
            self.end_headers()
            self.wfile.write(data)

        def _body(self, limit=MAX_BODY):
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > limit:
                raise ValueError("حجم بدنه نامعتبر است")
            return json.loads(self.rfile.read(n).decode("utf-8", errors="replace"))

        def _bearer(self):
            h = self.headers.get("Authorization") or ""
            if h.lower().startswith("bearer "):
                return h[7:].strip()
            return (self.headers.get("x-api-key") or "").strip()

        def _admin_ok(self):
            key = self.headers.get("X-Admin-Key") or ""
            return bool(key) and secrets.compare_digest(key, settings.admin_key)

        def _sse_headers(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

        def _sse(self, obj):
            self.wfile.write(("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8"))
            self.wfile.flush()

        def _clean_messages(self, msgs, max_turns=40, max_chars=8000):
            clean = []
            for m in (msgs or [])[-max_turns:]:
                if not isinstance(m, dict):
                    continue
                role = m.get("role")
                content = m.get("content")
                if role in ("system", "user", "assistant") and isinstance(content, str):
                    clean.append({"role": role, "content": content[:max_chars]})
            return clean

        @staticmethod
        def _stats_from(st, ttft, wall):
            eval_count = st.get("eval_count") or 0
            eval_s = (st.get("eval_duration") or 0) / 1e9
            return {
                "tokens": eval_count,
                "tps": round(eval_count / eval_s, 1) if eval_s > 0 else 0.0,
                "ttft": round(ttft, 2),
                "wall": round(wall, 1),
                "prompt_tokens": st.get("prompt_eval_count") or 0,
            }

        # ---------- پایگاه دانش سایت ----------
        def _kb_context(self, query):
            """زمینه مرتبط از وب‌سایت؛ اگر چیزی مرتبط نبود، رشته خالی"""
            if not (settings.site_kb and site_kb and getattr(settings, "kb", None)):
                return ""
            try:
                return site_kb.build_context(settings.kb, query or "",
                                             max_chars=settings.kb_context_chars)
            except Exception:
                return ""

        def _effective_system(self, msgs):
            """پرامپت هویت + (در صورت مرتبط بودن پرسش) اطلاعات رسمی سایت"""
            base = settings.system_prompt
            last_user = ""
            for m in reversed(msgs):
                if m.get("role") == "user":
                    last_user = m.get("content") or ""
                    break
            ctx = self._kb_context(last_user)
            if ctx:
                base = base + KB_CONTEXT_HEADER + ctx + KB_CONTEXT_FOOTER
            return base

        def _inject_kb(self, msgs):
            """اگر کلاینت پیام system داشت، فقط اطلاعات سایت به آن افزوده می‌شود"""
            ctx_all = ""
            last_user = ""
            for m in reversed(msgs):
                if m.get("role") == "user":
                    last_user = m.get("content") or ""
                    break
            ctx_all = self._kb_context(last_user)
            if not ctx_all:
                return msgs
            out = list(msgs)
            for i, m in enumerate(out):
                if m.get("role") == "system":
                    out[i] = {"role": "system",
                              "content": m["content"] + KB_CONTEXT_HEADER + ctx_all + KB_CONTEXT_FOOTER}
                    break
            return out

        # ---------- GET ----------
        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                data = settings.html_page.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
            elif path == "/health":
                kb = getattr(settings, "kb", None)
                self._json(200, {
                    "status": "ok",
                    "service": "llm-rose-chat",
                    "model": settings.model,
                    "ollama": settings.ollama,
                    "chat_public": settings.chat_public,
                    "site_kb": {
                        "enabled": settings.site_kb,
                        "chunks": len(kb["chunks"]) if kb else 0,
                        "built_at": kb.get("built_at") if kb else None,
                    },
                    "uptime_s": int(time.time() - boot_ts),
                })
            elif path == "/v1/models":
                if not store.verify(self._bearer()):
                    return self._json(401, {"error": {"message": "توکن نامعتبر است",
                                                      "type": "auth_error"}})
                self._json(200, {"object": "list", "data": [
                    {"id": settings.model, "object": "model", "owned_by": "llm-rose"}]})
            else:
                self._json(404, {"error": "یافت نشد"})

        # ---------- POST ----------
        def do_POST(self):
            path = self.path.split("?")[0]
            # بدنه فقط یک‌بار و قبل از هر پاسخی خوانده می‌شود تا اتصال keep-alive سالم بماند
            body = {}
            try:
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if 0 < n <= MAX_BODY else b""
                if raw:
                    body = json.loads(raw.decode("utf-8", errors="replace"))
                    if not isinstance(body, dict):
                        body = {"__invalid": True}
            except Exception:
                body = {"__invalid": True}
            try:
                if path == "/api/chat/stream":
                    self.handle_web_chat(body)
                elif path == "/v1/chat/completions":
                    self.handle_openai_api(body)
                elif path == "/admin/tokens":
                    self.handle_admin_create(body)
                elif path == "/admin/tokens/revoke":
                    self.handle_admin_revoke(body)
                else:
                    self._json(404, {"error": "یافت نشد"})
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True
            except Exception as exc:
                try:
                    self._json(500, {"error": f"خطای داخلی: {exc}"})
                except Exception:
                    self.close_connection = True

        # ---------- چت وب (استریم SSE) ----------
        def handle_web_chat(self, body):
            if body.get("__invalid"):
                return self._json(400, {"error": "بدنه درخواست نامعتبر است"})

            rec = None
            if settings.chat_public:
                if not limiter.allow("ip:" + self.client_address[0], settings.rate_web_per_min):
                    return self._json(429, {"error": "تعداد درخواست‌های شما زیاد است؛ کمی بعد دوباره تلاش کنید"})
            else:
                rec = store.verify(self._bearer())
                if not rec:
                    return self._json(401, {"error": "این چت خصوصی است؛ کلید API معتبر لازم است"})
                if not limiter.allow("tok:" + rec["id"], settings.rate_token_per_min):
                    return self._json(429, {"error": "محدودیت نرخ توکن؛ کمی صبر کنید"})

            msgs = self._clean_messages(body.get("messages") or [])
            if not msgs:
                return self._json(400, {"error": "پیامی ارسال نشده است"})
            if not any(m["role"] == "system" for m in msgs):
                msgs = [{"role": "system", "content": self._effective_system(msgs)}] + msgs
            else:
                msgs = self._inject_kb(msgs)

            self._sse_headers()
            ttft, full, last_stats = None, "", {}
            t0 = time.perf_counter()
            try:
                for obj in ollama_chat_stream(settings, msgs, settings.max_output_tokens):
                    if obj.get("done"):
                        last_stats = obj
                        break
                    delta = (obj.get("message") or {}).get("content") or ""
                    if delta:
                        if ttft is None:
                            ttft = time.perf_counter() - t0
                        full += delta
                        self._sse({"content": delta})
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True
                return
            except Exception as exc:
                try:
                    self._sse({"error": f"ارتباط با مدل برقرار نشد: {exc}"})
                except Exception:
                    pass
                self.close_connection = True
                return
            wall = time.perf_counter() - t0
            stats = self._stats_from(last_stats, ttft if ttft is not None else wall, wall)
            try:
                self._sse({"done": True, "stats": stats})
            except Exception:
                pass
            if rec:
                store.bump(rec, stats["tokens"])
            self.close_connection = True

        # ---------- API سازگار با OpenAI ----------
        def handle_openai_api(self, body):
            rec = store.verify(self._bearer())
            if not rec:
                return self._json(401, {"error": {"message": "توکن نامعتبر یا حذف‌شده است. "
                                                             "با دستور add-token یک توکن بسازید",
                                                  "type": "auth_error"}})
            if not limiter.allow("tok:" + rec["id"], settings.rate_token_per_min):
                return self._json(429, {"error": {"message": "محدودیت نرخ درخواست توکن",
                                                  "type": "rate_limit_error"}})
            if body.get("__invalid"):
                return self._json(400, {"error": {"message": "بدنه نامعتبر",
                                                  "type": "invalid_request_error"}})

            msgs = self._clean_messages(body.get("messages") or [])
            if not msgs:
                return self._json(400, {"error": {"message": "messages الزامی است",
                                                  "type": "invalid_request_error"}})
            if not any(m["role"] == "system" for m in msgs):
                msgs = [{"role": "system", "content": self._effective_system(msgs)}] + msgs
            else:
                msgs = self._inject_kb(msgs)

            stream = bool(body.get("stream", False))
            try:
                max_tokens = int(body.get("max_tokens") or settings.max_output_tokens)
            except Exception:
                max_tokens = settings.max_output_tokens
            num_predict = max(1, min(max_tokens, settings.max_output_tokens))

            cid = "chatcmpl-" + secrets.token_hex(6)
            created = int(time.time())
            model_name = body.get("model") or settings.model
            t0 = time.perf_counter()
            ttft, full, last_stats = None, "", {}

            if stream:
                self._sse_headers()
                try:
                    for obj in ollama_chat_stream(settings, msgs, num_predict):
                        if obj.get("done"):
                            last_stats = obj
                            break
                        delta = (obj.get("message") or {}).get("content") or ""
                        if delta:
                            if ttft is None:
                                ttft = time.perf_counter() - t0
                            self._sse({"id": cid, "object": "chat.completion.chunk",
                                       "created": created, "model": model_name,
                                       "choices": [{"index": 0, "delta": {"content": delta},
                                                    "finish_reason": None}]})
                    self._sse({"id": cid, "object": "chat.completion.chunk", "created": created,
                               "model": model_name,
                               "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    self.close_connection = True
                    return
                except Exception as exc:
                    try:
                        self._sse({"error": f"ارتباط با مدل برقرار نشد: {exc}"})
                    except Exception:
                        pass
                    self.close_connection = True
                    return
                wall = time.perf_counter() - t0
                stats = self._stats_from(last_stats, ttft if ttft is not None else wall, wall)
                store.bump(rec, stats["tokens"])
                self.close_connection = True
            else:
                try:
                    for obj in ollama_chat_stream(settings, msgs, num_predict):
                        if obj.get("done"):
                            last_stats = obj
                            break
                        delta = (obj.get("message") or {}).get("content") or ""
                        if delta:
                            if ttft is None:
                                ttft = time.perf_counter() - t0
                            full += delta
                except HTTPError as e:
                    return self._json(502, {"error": {"message": f"خطای سرور مدل: {e.code}",
                                                      "type": "upstream_error"}})
                except Exception as exc:
                    return self._json(502, {"error": {"message": f"ارتباط با مدل برقرار نشد: {exc}",
                                                      "type": "upstream_error"}})
                wall = time.perf_counter() - t0
                stats = self._stats_from(last_stats, ttft if ttft is not None else wall, wall)
                store.bump(rec, stats["tokens"])
                self._json(200, {
                    "id": cid, "object": "chat.completion", "created": created,
                    "model": model_name,
                    "choices": [{"index": 0,
                                 "message": {"role": "assistant", "content": full},
                                 "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": stats["prompt_tokens"],
                              "completion_tokens": stats["tokens"],
                              "total_tokens": stats["prompt_tokens"] + stats["tokens"]},
                })

        # ---------- مدیریت توکن (نیازمند کلید ادمین) ----------
        def handle_admin_create(self, body):
            if not self._admin_ok():
                return self._json(403, {"error": "کلید ادمین نامعتبر است (هدر X-Admin-Key)"})
            if body.get("__invalid"):
                body = {}
            raw, rec = store.create(body.get("name") or "token")
            self._json(201, {
                "message": "توکن ساخته شد؛ توکن را همین حالا ذخیره کنید (دوباره نمایش داده نمی‌شود)",
                "id": rec["id"], "name": rec["name"], "token": raw,
                "created": rec["created"],
            })

        def handle_admin_revoke(self, body):
            if not self._admin_ok():
                return self._json(403, {"error": "کلید ادمین نامعتبر است (هدر X-Admin-Key)"})
            if body.get("__invalid"):
                body = {}
            rec = store.revoke(body.get("id") or "")
            if rec:
                self._json(200, {"message": f"توکن {rec['name']} باطل شد", "id": rec["id"]})
            else:
                self._json(404, {"error": "توکنی با این شناسه یافت نشد"})

    return Handler


# =====================================================================
# پایگاه دانش سایت: بارگذاری + به‌روزرسانی خودکار در پس‌زمینه
# =====================================================================
def load_kb_into(settings):
    """بارگذاری KB موجود از فایل؛ خروجی: dict یا None"""
    if not settings.site_kb:
        return None
    kb = site_kb.load_kb(settings.data_dir / "site_kb.json")
    if kb:
        settings.kb = kb
        print(f"  پایگاه دانش   : فعال — {len(kb['chunks'])} قطعه (ساخته {kb.get('built_at')})")
    else:
        settings.kb = None
        print("  پایگاه دانش   : هنوز ساخته نشده — در پس‌زمینه ساخته می‌شود…")
    return kb


def kb_refresh_loop(settings):
    """حلقه پس‌زمینه: اگر فایل نبود یا قدیمی شد، دوباره از سایت می‌سازد"""
    path = settings.data_dir / "site_kb.json"
    check_every_s = 1800  # هر ۳۰ دقیقه وضعیت را بررسی کن
    while True:
        try:
            stale = True
            if path.exists():
                age_h = (time.time() - path.stat().st_mtime) / 3600.0
                stale = age_h >= max(settings.site_kb_refresh_hours, 0.5)
            if stale:
                data, err = site_kb.build_kb(settings.site_url, path,
                                             log=lambda m: print(f"[KB] {m}", flush=True))
                if data:
                    settings.kb = site_kb.load_kb(path) or settings.kb
                    print(f"[KB] پایگاه دانش آماده شد: {len(data['chunks'])} قطعه", flush=True)
                elif err:
                    print(f"[KB] به‌روزرسانی ناموفق: {err}", flush=True)
        except Exception as exc:
            print(f"[KB] خطای غیرمنتظره: {exc}", flush=True)
        time.sleep(check_every_s)


# =====================================================================
# اجرای سرور
# =====================================================================
def local_ips():
    ips = set()
    try:
        for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(i[4][0])
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    return sorted(ips)


def run_server(settings):
    store = TokenStore(settings.data_dir / "tokens.json")
    limiter = RateLimiter()
    boot_ts = time.time()
    handler = build_handler(settings, store, limiter, boot_ts)

    print("=" * 64)
    print("  LLM Rose — سرور چت وب و API فارسی")
    print("=" * 64)
    print(f"  مدل           : {settings.model}   (Ollama: {settings.ollama})")
    print(f"  چت عمومی      : {'بله (برای قفل‌کردن chat_public=false در config.json)' if settings.chat_public else 'خیر — کلید API لازم است'}")
    print(f"  هویت دستیار   : {settings.app_title}  (سایت: {settings.site_url})")
    print(f"  پوشه داده     : {settings.data_dir}")
    print(f"  کلید ادمین    : {settings.admin_key}")
    print("  برای ساخت توکن: python chat_server.py add-token --name \"نام\"")
    print("-" * 64)
    for ip in local_ips():
        print(f"  چت وب         : http://{ip}:{settings.port}")
    print(f"  API (OpenAI)  : http://<IP-سرور>:{settings.port}/v1/chat/completions")
    print("=" * 64)

    load_kb_into(settings)
    if settings.site_kb:
        threading.Thread(target=kb_refresh_loop, args=(settings,), daemon=True).start()
    elif not site_kb and settings.site_kb_enabled:
        print("  توجه: فایل site_kb.py کنار سرور نیست؛ پاسخ از محتوای سایت غیرفعال است.")

    server = ThreadingHTTPServer((settings.host, settings.port), handler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nسرور متوقف شد.")


# =====================================================================
# ابزارهای خط فرمان مدیریت توکن
# =====================================================================
def print_token_table(tokens):
    active = [t for t in tokens if not t.get("revoked")]
    revoked = [t for t in tokens if t.get("revoked")]
    if active:
        print(f"{'شناسه':<10} {'نام':<18} {'توکن':<12} {'درخواست':>8} {'توکن خروجی':>12}  آخرین استفاده")
        print("-" * 84)
        for t in active:
            print(f"{t['id']:<10} {t['name'][:17]:<18} {t['prefix']}…  {t.get('requests', 0):>8} "
                  f"{t.get('tokens_out', 0):>12}  {t.get('last_used') or '—'}")
    if revoked:
        print(f"\n{len(revoked)} توکن باطل‌شده (خارج از لیست فعال)")
    if not tokens:
        print("هنوز توکنی ساخته نشده است. دستور: python chat_server.py add-token --name \"نام\"")


def main():
    argv = sys.argv[1:]

    ap = argparse.ArgumentParser(description="سرور چت وب + API فارسی (LLM Rose)")
    ap.add_argument("command", nargs="?", default="serve",
                    help="serve (پیش‌فرض) | add-token | list-tokens | revoke | show-admin-key | refresh-site")
    ap.add_argument("--name", help="نام توکن (برای add-token)")
    ap.add_argument("ident", nargs="?", help="شناسه توکن (برای revoke)")
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--ollama", default=None, help="آدرس سرور Ollama")
    ap.add_argument("--model", default=None)
    ap.add_argument("--ctx", type=int, default=None, help="طول زمینه (پیش‌فرض 8192)")
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--site-url", default=None,
                    help="آدرس وب‌سایت کلینیک برای پایگاه دانش (پیش‌فرض از config.json)")
    ap.add_argument("--private", action="store_true",
                    help="چت وب فقط با کلید API (به‌جای عمومی)")
    args = ap.parse_args(argv)

    settings = load_settings(args)
    store = TokenStore(settings.data_dir / "tokens.json")

    cmd = args.command
    if cmd == "serve":
        run_server(settings)
    elif cmd == "refresh-site":
        if not site_kb:
            print("ماژول site_kb.py کنار chat_server.py نیست؛ به‌روزرسانی ممکن نیست.")
            sys.exit(1)
        print(f"به‌روزرسانی پایگاه دانش از: {settings.site_url}")
        data, err = site_kb.build_kb(settings.site_url, settings.data_dir / "site_kb.json", log=print)
        if data:
            print(f"✓ {len(data['chunks'])} قطعه دانش ذخیره شد: {settings.data_dir / 'site_kb.json'}")
            if data.get("errors"):
                print(f"  هشدارها: {'؛ '.join(data['errors'])}")
            print("  (سرور در حال اجرا ظرف حداکثر ۳۰ دقیقه خودش آن را می‌بیند؛ برای اعمال فوری، سرور را ری‌استارت کنید)")
        else:
            print(f"✗ ناموفق: {err}")
            sys.exit(1)
    elif cmd == "add-token":
        raw, rec = store.create(args.name or "token")
        print("=" * 56)
        print(f"  توکن جدید ساخته شد (نام: {rec['name']})")
        print(f"  شناسه : {rec['id']}")
        print(f"  توکن  : {raw}")
        print("  توجه: این توکن فقط همین یک بار نمایش داده می‌شود؛ در جای امن ذخیره کنید.")
        print("  استفاده در API: هدر  Authorization: Bearer <توکن>")
        print("=" * 56)
    elif cmd == "list-tokens":
        print_token_table(store.list())
    elif cmd == "revoke":
        if not args.ident:
            print("شناسه توکن را بدهید: python chat_server.py revoke <id>")
            sys.exit(1)
        rec = store.revoke(args.ident)
        print(f"توکن {rec['name']} باطل شد." if rec else "توکنی با این شناسه یافت نشد.")
    elif cmd == "show-admin-key":
        print(f"کلید ادمین: {settings.admin_key}")
        print("استفاده: هدر  X-Admin-Key: <کلید>  در مسیرهای /admin/tokens")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()

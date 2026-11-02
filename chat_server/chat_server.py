#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM Rose — سرور چت وب آنلاین + API سازگار با OpenAI همراه با مدیریت توکن
=======================================================================

امکانات:
  - صفحه چت وب فارسی (RTL) با پاسخ جریانی (استریم) روی پورت دلخواه (پیش‌فرض 8093)
  - تم شب/روز + انتخاب مدل + سایدبار گفتگوها + تاریخچه ماندگار (سرور + مرورگر)
  - پیوست فایل: عکس، Word (docx)، Excel (xlsx)، PowerPoint (pptx)، PDF و متنی (استخراج متن فقط با کتابخانه استاندارد)
  - اجرای کد HTML/JS داخل صفحه، رندر نمودار فرایند (زیرمجموعه mermaid)، کپی پیام‌ها و کدها
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
import base64
import hashlib
import html as html_lib
import io
import json
import os
import re
import secrets
import socket
import sys
import threading
import time
import zipfile
import zlib
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib import request as urlreq
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

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
    "در موارد بحرانی (مانند افکار خودآسیبی) فوراً به اورژانس ۱۲۳ یا پذیرش کلینیک ارجاع بده.\n"
    "۶) قالب پاسخ: مارک‌داون ساده (تیتر با ##، لیست با -، پررنگ با **…**)؛ کدها همیشه داخل بلوک سه‌بک‌تیک با نام زبان؛ "
    "اگر کاربر کد HTML خواست، یک سند کامل و قابل‌اجرا با <!DOCTYPE html> بده.\n"
    "۷) اگر کاربر «نمودار، فرایند، فلوچارت یا مدل» خواست، یک بلوک ```mermaid بساز با فقط این قواعد: "
    "خط اول flowchart TD (یا LR)، گره‌ها به‌شکل A[متن] یا A(متن) یا A{متن}، یال‌ها فقط --> یا -.-> یا --- "
    "و برچسب یال با |متن|. از subgraph، classDef، استایل و نویسه‌های خاص داخل متن پرهیز کن."
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
# استخراج متن از فایل‌های پیوست (docx / xlsx / pptx / pdf / متنی) — فقط کتابخانه استاندارد
# =====================================================================
ATTACH_MAX_CHARS = 12000
TEXT_EXTS = {"txt", "csv", "md", "log", "json", "py", "js", "css", "html", "htm",
             "xml", "yml", "yaml", "tsv", "ini", "sql", "ts", "jsx", "tsx"}
IMG_EXTS = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}


def _x_docx(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
    xml = re.sub(r"<w:br[^>]*/>", "\n", xml)
    txt = re.sub(r"<[^>]+>", "", xml)
    return html_lib.unescape(txt)


def _x_pptx(data):
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in sorted(n for n in z.namelist()
                           if re.match(r"ppt/slides/slide\d+\.xml$", n)):
            xml = z.read(name).decode("utf-8", errors="replace")
            texts = [html_lib.unescape(t) for t in re.findall(r"<a:t>([^<]*)</a:t>", xml)]
            if texts:
                out.append(" — ".join(texts))
    return "\n".join(out)


def _x_xlsx(data):
    lines = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            ss = z.read("xl/sharedStrings.xml").decode("utf-8", errors="replace")
            shared = [html_lib.unescape(re.sub(r"<[^>]+>", "", m))
                      for m in re.findall(r"<si>(.*?)</si>", ss, re.S)]
        sheets = sorted(n for n in z.namelist()
                        if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
        for sh in sheets:
            x = z.read(sh).decode("utf-8", errors="replace")
            for row in re.findall(r"<row[^>]*>(.*?)</row>", x, re.S)[:2000]:
                cells = []
                for cm in re.finditer(r"<c([^>]*)>(.*?)</c>", row, re.S):
                    attrs, inner = cm.group(1), cm.group(2)
                    v = re.search(r"<v>([^<]*)</v>", inner)
                    t = re.search(r"<t[^>]*>([^<]*)</t>", inner)
                    if 't="s"' in attrs and v:
                        try:
                            val = shared[int(v.group(1))]
                        except (ValueError, IndexError):
                            val = v.group(1)
                    elif t:
                        val = t.group(1)
                    elif v:
                        val = v.group(1)
                    else:
                        val = ""
                    cells.append(val)
                if any(c.strip() for c in cells):
                    lines.append(" | ".join(cells))
    return "\n".join(lines)


def _x_pdf(data):
    """استخراج سادهٔ متن PDF (بهترین تلاش — PDFهای اسکنی متن ندارند)"""
    texts = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        chunk = m.group(1)
        try:
            d = zlib.decompress(chunk)
        except Exception:
            d = chunk
        for om in re.finditer(rb"\[((?:[^\[\]\\]|\\.)*)\]\s*TJ|\(((?:[^()\\]|\\.)*)\)\s*Tj", d):
            if om.group(1) is not None:
                parts = re.findall(rb"\(((?:[^()\\]|\\.)*)\)", om.group(1))
                s = b"".join(parts)
            else:
                s = om.group(2)
            s = s.replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")
            try:
                texts.append(s.decode("utf-16-be", errors="replace")
                             if s.startswith(b"\xfe\xff")
                             else s.decode("latin-1", errors="replace"))
            except Exception:
                pass
        if len(texts) > 4000:
            break
    return "\n".join(texts)


def extract_text_from(name, data):
    """خروجی: (متن، نوع) — نوع: text/docx/xlsx/pptx/pdf/image/doc-legacy/binary"""
    ext = (name.rsplit(".", 1)[-1] if "." in name else "").lower()
    if ext in IMG_EXTS:
        return "", "image"
    try:
        if ext == "docx":
            return _x_docx(data)[:ATTACH_MAX_CHARS], "docx"
        if ext == "pptx":
            return _x_pptx(data)[:ATTACH_MAX_CHARS], "pptx"
        if ext in ("xlsx", "xlsm"):
            return _x_xlsx(data)[:ATTACH_MAX_CHARS], "xlsx"
        if ext == "pdf":
            return _x_pdf(data)[:ATTACH_MAX_CHARS], "pdf"
    except Exception:
        return "", "binary"
    if ext == "doc":
        return "", "doc-legacy"
    if ext in TEXT_EXTS or ext == "":
        try:
            return data.decode("utf-8", errors="replace")[:ATTACH_MAX_CHARS], "text"
        except Exception:
            pass
    return "", "binary"


# =====================================================================
# تاریخچه گفتگوها — پشتیبان سمت سرور برای مرورگر کاربر (هر uid یک فایل)
# =====================================================================
class HistoryStore:
    def __init__(self, data_dir):
        self.dir = Path(data_dir) / "history"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    @staticmethod
    def safe_uid(uid):
        return isinstance(uid, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{8,64}", uid))

    def _path(self, uid):
        return self.dir / (uid + ".json")

    def load(self, uid):
        try:
            return json.loads(self._path(uid).read_text(encoding="utf-8")).get("chats", [])
        except Exception:
            return []

    def save(self, uid, chats):
        if not isinstance(chats, list):
            raise ValueError("chats باید لیست باشد")
        slim = []
        for c in chats[:80]:
            if not isinstance(c, dict):
                continue
            cc = {"id": str(c.get("id") or secrets.token_hex(6)),
                  "title": str(c.get("title") or "گفتگو")[:80],
                  "updated": str(c.get("updated") or ""),
                  "msgs": []}
            for m in (c.get("msgs") or [])[:120]:
                if not isinstance(m, dict):
                    continue
                mm = {"role": m.get("role"), "content": str(m.get("content") or "")[:12000]}
                if isinstance(m.get("att"), list) and m["att"]:
                    mm["att"] = [{"name": str(a.get("name") or "")[:80],
                                  "kind": str(a.get("kind") or "file")}
                                 for a in m["att"][:6]]
                cc["msgs"].append(mm)
            slim.append(cc)
        data = {"version": 1, "updated": datetime.now().isoformat(timespec="seconds"),
                "chats": slim}
        with self.lock:
            tmp = self._path(uid).with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._path(uid))

    def delete(self, uid, chat_id=None):
        with self.lock:
            if chat_id is None:
                try:
                    self._path(uid).unlink()
                except FileNotFoundError:
                    pass
                return
            chats = [c for c in self.load(uid) if c.get("id") != chat_id]
            self.save(uid, chats)


# لیست مدل‌های Ollama با کش ۶۰ ثانیه‌ای (برای انتخاب‌مدل در صفحه چت)
_ol_models_cache = {"t": 0.0, "names": []}


def list_models(settings):
    now = time.time()
    if now - _ol_models_cache["t"] > 60:
        try:
            r = urlreq.urlopen(settings.ollama + "/api/tags", timeout=5)
            data = json.loads(r.read().decode("utf-8", errors="replace"))
            names = [m.get("name") for m in data.get("models", []) if m.get("name")]
            if names:
                _ol_models_cache.update(t=now, names=names)
        except Exception:
            pass
    names = list(_ol_models_cache["names"])
    if settings.model and settings.model not in names:
        names.insert(0, settings.model)
    return names or [settings.model]


MODEL_RE = re.compile(r"[A-Za-z0-9._:\-/]{1,64}")


# =====================================================================
# ارتباط با Ollama
# =====================================================================
def ollama_chat_stream(settings, messages, num_predict, model=None):
    payload = {
        "model": model if model and MODEL_RE.fullmatch(model) else settings.model,
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
HTML_PAGE = r"""
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__APP_TITLE__ | کلینیک رز</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='16' fill='%23e91e63'/%3E%3Ctext x='16' y='22' font-size='18' font-weight='bold' text-anchor='middle' fill='white' font-family='Arial'%3ER%3C/text%3E%3C/svg%3E">
<style>
:root{--bg:#0f1117;--panel:#171a23;--panel2:#1e2230;--line:#2a2f40;--text:#e8eaf0;
--dim:#98a1b3;--accent:#e91e63;--accent2:#ff5c8d;--ok:#2ecc71;--err:#ff6b6b;
--keybar-bg:#2a1620;--shadow:none;--user-b:#c2185b;--codebg:#0d0f14;color-scheme:dark}
html[data-theme="light"]{--bg:#f3f5fa;--panel:#ffffff;--panel2:#e9edf5;--line:#d9e0ee;--text:#1d2333;
--dim:#5f6b84;--accent:#d81b60;--accent2:#e91e63;--ok:#1e9e5a;--err:#d64545;
--keybar-bg:#fdeef4;--shadow:0 1px 4px rgba(25,40,80,.10);--user-b:#ad1457;--codebg:#f0f2f8;color-scheme:light}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--text);font-family:"Vazirmatn",Vazir,Tahoma,"Segoe UI",sans-serif}
#app{display:flex;height:100%}
/* ---------- سایدبار گفتگوها ---------- */
#side{width:262px;flex:0 0 262px;background:var(--panel);border-left:1px solid var(--line);
display:flex;flex-direction:column;transition:margin .25s ease}
#side.hide{margin-right:-262px}
#newchat{margin:12px;border-radius:12px;padding:11px;font-size:14px;font-weight:600}
#chatlist{flex:1;overflow-y:auto;padding:0 10px 10px}
.citem{padding:9px 12px;border-radius:10px;cursor:pointer;font-size:13px;margin-bottom:4px;
display:flex;align-items:center;gap:6px;border:1px solid transparent}
.citem:hover{background:var(--panel2)}
.citem.on{background:var(--panel2);border-color:var(--accent)}
.citem .ct{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.citem .cd{font-size:11px;color:var(--dim)}
.citem .cdel{opacity:.45;font-size:13px;padding:2px 4px;border-radius:6px}
.citem .cdel:hover{opacity:1;background:var(--err);color:#fff}
.sidefoot{padding:10px 14px;font-size:11px;color:var(--dim);border-top:1px solid var(--line);line-height:1.9}
/* ---------- بخش اصلی ---------- */
#main{flex:1;display:flex;flex-direction:column;min-width:0}
header{display:flex;align-items:center;gap:8px;padding:10px 16px;background:var(--panel);
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
#burger{background:var(--panel2);border:1px solid var(--line);color:var(--text);width:34px;
height:32px;border-radius:10px;font-size:16px;padding:0;display:none}
#modelsel{background:var(--panel2);border:1px solid var(--line);color:var(--text);
border-radius:20px;padding:4px 10px;font-family:inherit;font-size:12px;outline:none;max-width:150px}
#themebtn{background:var(--panel2);border:1px solid var(--line);color:var(--text);
width:36px;height:32px;padding:0;font-size:15px;line-height:1;border-radius:10px}
#themebtn:hover{border-color:var(--accent)}
a.badge{text-decoration:none}
a.badge:hover{color:var(--accent);border-color:var(--accent)}
#keybar{display:none;gap:8px;padding:10px 16px;background:var(--keybar-bg);border-bottom:1px solid var(--accent)}
#keybar input{flex:1;background:var(--panel2);border:1px solid var(--line);color:var(--text);
border-radius:8px;padding:8px 12px;font-family:inherit;outline:none}
/* ---------- چت ---------- */
#chat{flex:1;overflow-y:auto;padding:18px 16px;display:flex;flex-direction:column;gap:12px}
.msg{max-width:84%;padding:10px 14px;border-radius:14px;line-height:2;font-size:14.5px;
word-wrap:break-word;overflow-wrap:anywhere}
.user{align-self:flex-start;background:linear-gradient(135deg,var(--accent),var(--user-b));
color:#fff;border-bottom-right-radius:4px}
.bot{align-self:flex-end;background:var(--panel);border:1px solid var(--line);
border-bottom-left-radius:4px;box-shadow:var(--shadow)}
.msg.errm{border-color:var(--err)}
.msgfoot{display:flex;gap:6px;margin-top:6px;justify-content:flex-start}
.mbtn{font-size:11px;background:var(--panel2);border:1px solid var(--line);color:var(--dim);
border-radius:8px;padding:2px 10px;cursor:pointer;font-family:inherit}
.mbtn:hover{color:var(--accent);border-color:var(--accent)}
.stats{font-size:11px;color:var(--dim);align-self:flex-end;background:var(--panel2);
border:1px solid var(--line);border-radius:10px;padding:2px 8px}
/* ---------- مارک‌داون داخل پیام ربات ---------- */
.bot p{margin:2px 0}
.bot h4,.bot h5{margin:10px 0 2px;color:var(--accent2)}
.bot ul,.bot ol{margin:4px 0;padding-right:22px}
.bot blockquote{margin:6px 0;padding:4px 12px;border-right:3px solid var(--accent);
background:var(--panel2);border-radius:8px;color:var(--dim)}
.bot a{color:var(--accent2)}
.bot .ic{background:var(--codebg);border:1px solid var(--line);border-radius:6px;
padding:1px 6px;direction:ltr;unicode-bidi:embed;font-size:13px;font-family:Consolas,Menlo,monospace}
.bot hr{border:0;border-top:1px dashed var(--line)}
/* ---------- بلوک کد ---------- */
.codebox{direction:ltr;text-align:left;background:var(--codebg);border:1px solid var(--line);
border-radius:12px;margin:8px 0;overflow:hidden}
.codehead{display:flex;align-items:center;gap:6px;padding:5px 10px;background:var(--panel2);
border-bottom:1px solid var(--line)}
.codehead .lang{font-size:11px;color:var(--dim);font-family:Consolas,monospace;flex:1}
.codebtn{font-size:11px;border:1px solid var(--line);background:var(--panel);color:var(--dim);
border-radius:7px;padding:2px 9px;cursor:pointer;font-family:inherit}
.codebtn:hover{color:var(--accent);border-color:var(--accent)}
.codebox pre{margin:0;padding:10px 12px;overflow-x:auto;font-size:12.5px;line-height:1.8;
font-family:Consolas,Menlo,"Courier New",monospace;color:var(--text)}
.tok-str{color:#7ec699}.tok-com{color:#8a93a5;font-style:italic}.tok-kw{color:#e48ac2}
.tok-tag{color:#6cb2f7}.tok-attr{color:#d9b36c}.tok-num{color:#e5a66b}
html[data-theme="light"] .tok-str{color:#1e7d46}html[data-theme="light"] .tok-com{color:#7c8798}
html[data-theme="light"] .tok-kw{color:#b0308a}html[data-theme="light"] .tok-tag{color:#1565c0}
html[data-theme="light"] .tok-attr{color:#9a6b00}html[data-theme="light"] .tok-num{color:#a05a12}
.codeout{border-top:1px dashed var(--line);max-height:360px;overflow:auto}
.codeout iframe{display:block;width:100%;height:340px;border:0;background:#fff}
.jout{font:12px/1.9 Consolas,monospace;padding:6px 12px;direction:ltr;text-align:left;color:var(--text)}
.jout .je{color:var(--err)}.jout .jw{color:#d9a03c}
/* ---------- نمودار ---------- */
.diagram{background:var(--panel2);border:1px dashed var(--line);border-radius:12px;
padding:10px;margin:8px 0;overflow:auto;text-align:center}
.diagram svg{max-width:100%;height:auto}
/* ---------- پیوست‌ها ---------- */
.chip{display:inline-flex;align-items:center;gap:6px;background:rgba(255,255,255,.16);
border:1px solid rgba(255,255,255,.35);border-radius:10px;padding:2px 10px;margin:3px 2px;
font-size:12px;max-width:100%}
.chip .cn{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:170px}
.chip .cx{cursor:pointer;font-weight:700;opacity:.7}.chip .cx:hover{opacity:1}
.chip.cker{background:rgba(0,0,0,.25);border-color:var(--err)}
.bot .chip,.msghist .chip{background:var(--panel2);border:1px solid var(--line);color:var(--dim)}
#attachbar{display:none;flex-wrap:wrap;gap:2px;padding:6px 16px 0;background:var(--panel)}
#composer{display:flex;gap:8px;padding:12px 16px;background:var(--panel);
border-top:1px solid var(--line);align-items:flex-end}
#attach{background:var(--panel2);border:1px solid var(--line);color:var(--dim);width:42px;
height:42px;border-radius:12px;font-size:18px;padding:0;flex:0 0 auto}
#attach:hover{color:var(--accent);border-color:var(--accent)}
#inp{flex:1;resize:none;background:var(--panel2);border:1px solid var(--line);color:var(--text);
border-radius:12px;padding:10px 14px;font-family:inherit;font-size:14.5px;outline:none;
max-height:140px;line-height:1.8}
#inp:focus{border-color:var(--accent)}
button{border:0;border-radius:12px;padding:10px 18px;font-family:inherit;font-size:14px;
cursor:pointer;color:#fff;background:linear-gradient(135deg,var(--accent),#c2185b)}
button:disabled{opacity:.45;cursor:not-allowed}
#stop{background:var(--panel2);border:1px solid var(--line);color:var(--dim)}
#guide{margin:0 16px 8px;background:var(--panel);border:1px solid var(--line);border-radius:12px;
font-size:12.5px;color:var(--dim)}
#guide summary{cursor:pointer;padding:8px 14px}
#guide div{padding:0 14px 12px;line-height:2.1}
#guide pre{background:var(--bg);border:1px solid var(--line);border-radius:8px;
padding:8px 12px;overflow-x:auto;direction:ltr;text-align:left;font-size:12px}
#toast{position:fixed;bottom:86px;right:50%;transform:translateX(50%);background:var(--accent);
color:#fff;border-radius:20px;padding:6px 18px;font-size:13px;opacity:0;pointer-events:none;
transition:opacity .3s;z-index:50}
@media (max-width:820px){
  #side{position:fixed;top:0;bottom:0;right:0;z-index:40;margin-right:-262px;box-shadow:-4px 0 18px rgba(0,0,0,.3)}
  #side.show{margin-right:0}
  #burger{display:block}
  .msg{max-width:95%}
  h1{font-size:14px}
  #speedbadge{display:none}
}
</style>
</head>
<body>
<div id="app">
  <aside id="side">
    <button id="newchat">＋ گفتگوی جدید</button>
    <div id="chatlist"></div>
    <div class="sidefoot">تاریخچه گفتگوها روی سرور ذخیره می‌شود و با تغییر مرورگر هم باقی می‌ماند.</div>
  </aside>
  <main id="main">
    <header>
      <button id="burger" title="لیست گفتگوها">☰</button>
      <div class="logo" title="__APP_TITLE__">R</div>
      <h1>__APP_TITLE__</h1>
      <span class="badge"><span class="dot" id="dot"></span><span id="modelname">…</span></span>
      <select id="modelsel" title="انتخاب مدل (سرعت/کیفیت)"></select>
      <span class="badge" id="speedbadge">سرعت: —</span>
      <a class="badge" href="__SITE_URL__" target="_blank" rel="noopener" title="وب‌سایت کلینیک رز">وب‌سایت کلینیک ↗</a>
      <span class="spacer"></span>
      <span class="badge" id="clearbtn" style="cursor:pointer">🧹 پاک‌کردن گفتگو</span>
      <button id="themebtn" title="تغییر تم شب/روز">🌙</button>
    </header>

    <div id="keybar">
      <input id="keyinp" placeholder="کلید API (lr_...) — فقط وقتی چت خصوصی است لازم می‌شود">
      <button id="keysave">ذخیره</button>
    </div>

    <div id="chat"><div class="msg bot" id="welcome">سلام 👋 من دستیار هوش مصنوعی کلینیک رز هستم؛ درباره خدمات، هزینه‌ها، شعبه‌ها و نوبت‌دهی آنلاین می‌توانم کمکتان کنم.
می‌توانید عکس، فایل Word، Excel یا PDF هم پیوست کنید، از من کد HTML بخواهید تا همین‌جا اجرا کنم، یا برای فرایندها نمودار بکشم. بپرسید!</div></div>

    <details id="guide">
      <summary>راهنمای امکانات و API (برای برنامه‌های شما)</summary>
      <div>
        <b>امکانات صفحه چت:</b> پیوست عکس/Word/Excel/PDF 📎 — اجرای کد HTML و JavaScript — نمایش نمودار فرایند (mermaid) —
        کپی پیام‌ها و کدها — تاریخچه گفتگوها — تم شب/روز — انتخاب مدل.<br>
        برای نمودار کافی است بخواهید: «فرایند نوبت‌دهی را به‌صورت فلوچارت بکش».<br><br>
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
        <b>تحلیل عکس:</b> مدل پیش‌فرض متن‌محور است؛ برای دیدن عکس‌ها روی سرور یک مدل بینایی بکشید:
        <pre>ollama pull gemma3:4b   <span style="opacity:.6"># یا qwen2.5vl:7b</span></pre>
        سپس از انتخاب‌مدل بالای صفحه همان را انتخاب کنید.
      </div>
    </details>

    <div id="attachbar"></div>
    <div id="composer">
      <button id="attach" title="پیوست فایل (عکس، Word، Excel، PDF، متن)">📎</button>
      <input type="file" id="file" multiple hidden
             accept=".png,.jpg,.jpeg,.gif,.webp,.pdf,.docx,.xlsx,.csv,.txt,.md,.log,.json,.pptx">
      <textarea id="inp" rows="1" placeholder="پیام خود را بنویسید… (Enter = ارسال)"></textarea>
      <button id="stop" hidden>توقف</button>
      <button id="send">ارسال</button>
    </div>
  </main>
</div>
<div id="toast">کپی شد ✓</div>

<script>
"use strict";
const chat = document.getElementById("chat");
const inp = document.getElementById("inp");
const sendBtn = document.getElementById("send");
const stopBtn = document.getElementById("stop");
const welcomeEl = document.getElementById("welcome");

let messages = [];      // پیام‌های گفتگوی جاری (شکل API)
let chats = [];         // لیست گفتگوها
let curId = null;
let busy = false, ctl = null;
let pending = [];       // پیوست‌های آماده ارسال
let pendingBusy = false;

/* ---------- ابزار کوچک ---------- */
const $ = id => document.getElementById(id);
function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function toast(t){const el=$("toast");el.textContent=t;el.style.opacity=1;setTimeout(()=>el.style.opacity=0,1200);}
function scrollDown(){chat.scrollTop=chat.scrollHeight;}
function uid10(){let s="";for(let i=0;i<12;i++)s+="abcdefghijklmnopqrstuvwxyz0123456789"[Math.floor(Math.random()*36)];return s;}
function faDate(iso){try{return new Date(iso).toLocaleDateString("fa-IR",{month:"short",day:"numeric"});}catch(e){return "";}}

/* ---------- تم شب / روز ---------- */
const rootEl = document.documentElement;
const themeBtn = $("themebtn");
function applyTheme(t){
  rootEl.setAttribute("data-theme", t);
  try{localStorage.setItem("lr_theme", t);}catch(e){}
  themeBtn.textContent = t === "light" ? "🌙" : "☀️";
}
let savedTheme = null;
try{ savedTheme = localStorage.getItem("lr_theme"); }catch(e){}
applyTheme(savedTheme || ((window.matchMedia && matchMedia("(prefers-color-scheme: light)").matches) ? "light" : "dark"));
themeBtn.onclick = () => applyTheme(rootEl.getAttribute("data-theme")==="light" ? "dark" : "light");

/* ---------- کلید API (چت خصوصی) ---------- */
function authHeaders(){const k=localStorage.getItem("lr_key");return k?{"Authorization":"Bearer "+k}:{};}
function showKeybar(v){$("keybar").style.display=v?"flex":"none";}
$("keysave").onclick=()=>{localStorage.setItem("lr_key",$("keyinp").value.trim());showKeybar(false);};
if(localStorage.getItem("lr_key")) $("keyinp").value=localStorage.getItem("lr_key");

/* ---------- سلامت + لیست مدل‌ها ---------- */
fetch("/health").then(r=>r.json()).then(h=>{
  $("modelname").textContent=h.model;
  $("dot").classList.add("on");
  document.querySelectorAll(".mname").forEach(e=>e.textContent=h.model);
}).catch(()=>{});
document.querySelectorAll(".host").forEach(e=>e.textContent=location.host);

let chosenModel = localStorage.getItem("lr_model") || "";
async function loadModels(){
  try{
    const r=await fetch("/api/models");const d=await r.json();
    const sel=$("modelsel");sel.innerHTML="";
    (d.models||[]).forEach(m=>{
      const o=document.createElement("option");o.value=m;o.textContent=m;
      if(m===(chosenModel||d.current))o.selected=true;sel.appendChild(o);
    });
    chosenModel=sel.value;
  }catch(e){}
}
$("modelsel").onchange=e=>{chosenModel=e.target.value;try{localStorage.setItem("lr_model",chosenModel);}catch(x){}};
loadModels();

/* ---------- تاریخچه گفتگوها (سرور + مرورگر) ---------- */
let LRUID="";
try{
  LRUID=localStorage.getItem("lr_uid")||"";
  if(!/^[A-Za-z0-9_-]{8,64}$/.test(LRUID)){LRUID=uid10()+uid10()+uid10();localStorage.setItem("lr_uid",LRUID);}
}catch(e){LRUID=uid10()+uid10()+uid10();}

function slimChats(){
  return chats.map(c=>({id:c.id,title:c.title,updated:c.updated,
    msgs:c.msgs.map(m=>{const o={role:m.role,content:m.content};
      if(m.att&&m.att.length)o.att=m.att.map(a=>({name:a.name,kind:a.kind,error:a.error||""}));return o;})}));
}
let saveTimer=null;
function scheduleSave(){
  clearTimeout(saveTimer);
  saveTimer=setTimeout(()=>{
    try{localStorage.setItem("lr_chats",JSON.stringify(slimChats()));}catch(e){}
    fetch("/api/history",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({uid:LRUID,chats:slimChats()})}).catch(()=>{});
  },600);
}
function loadHistory(){
  // نمایش فوری از کش مرورگر
  try{
    const c=JSON.parse(localStorage.getItem("lr_chats")||"[]");
    if(Array.isArray(c)&&c.length){chats=c;}
  }catch(e){}
  renderChatList();
  // سپس همگام‌سازی با سرور
  fetch("/api/history?uid="+LRUID).then(r=>r.json()).then(d=>{
    if(Array.isArray(d.chats)&&(d.chats.length>0||chats.length===0)){chats=d.chats;renderChatList();}
    else if(chats.length>0){scheduleSave();}
  }).catch(()=>{});
}
function renderChatList(){
  const box=$("chatlist");box.innerHTML="";
  if(!chats.length){box.innerHTML='<div style="color:var(--dim);font-size:12px;padding:10px;text-align:center">هنوز گفتگویی ندارید</div>';return;}
  chats.forEach(c=>{
    const d=document.createElement("div");
    d.className="citem"+(c.id===curId?" on":"");
    d.innerHTML='<span class="ct">'+esc(c.title||"گفتگو")+'</span><span class="cd">'+esc(faDate(c.updated))+'</span><span class="cdel" title="حذف">🗑</span>';
    d.onclick=()=>{if(busy)return;openChat(c.id);};
    d.querySelector(".cdel").onclick=ev=>{
      ev.stopPropagation();if(busy)return;
      chats=chats.filter(x=>x.id!==c.id);
      if(curId===c.id){curId=null;messages=[];chat.innerHTML="";chat.appendChild(welcomeEl);}
      fetch("/api/history?uid="+LRUID+"&id="+c.id,{method:"DELETE"}).catch(()=>{});
      scheduleSave();renderChatList();
    };
    box.appendChild(d);
  });
}
function newChat(){
  if(busy)return;
  curId=null;messages=[];pending=[];
  chat.innerHTML="";chat.appendChild(welcomeEl);
  renderAttachBar();renderChatList();inp.focus();
}
function openChat(id){
  const c=chats.find(x=>x.id===id);if(!c)return;
  curId=id;messages=(c.msgs||[]).map(m=>Object.assign({},m));
  chat.innerHTML="";
  messages.forEach(m=>{
    if(m.role==="user")addUserBubble(m);
    else if(m.role==="assistant"){const b=addBubble("bot","");b.appendChild(renderMD(m.content));addMsgFoot(b,m.content);}
  });
  if(!messages.length){chat.appendChild(welcomeEl);}
  renderChatList();scrollDown();
}
$("newchat").onclick=newChat;
$("burger").onclick=()=>{$("side").classList.toggle("show");};
$("clearbtn").onclick=()=>{
  if(busy)return;
  const c=chats.find(x=>x.id===curId);
  if(c){c.msgs=[];scheduleSave();}
  messages=[];chat.innerHTML="";chat.appendChild(welcomeEl);
};

/* ---------- حباب‌های پیام ---------- */
function addBubble(cls,text){
  const d=document.createElement("div");
  d.className="msg "+cls;
  if(text)d.textContent=text;
  chat.appendChild(d);scrollDown();return d;
}
function addMsgFoot(bubble,rawText){
  const f=document.createElement("div");f.className="msgfoot";
  const cp=document.createElement("button");cp.className="mbtn";cp.textContent="📋 کپی";
  cp.onclick=()=>{copyText(rawText);};
  f.appendChild(cp);bubble.appendChild(f);
}
function addUserBubble(m){
  const d=addBubble("user","");
  let html="";
  (m.att||[]).forEach(a=>{
    html+='<span class="chip">'+(a.kind==="image"?"🖼":"📄")+' <span class="cn">'+esc(a.name)+"</span>"+(a.error?' ⚠️':"")+"</span>";
  });
  if(m.content)html+=esc(m.content).replace(/\n/g,"<br>");
  d.innerHTML=html||"(فایل پیوست)";
}
function copyText(t){
  const done=()=>toast("کپی شد ✓");
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t).then(done).catch(()=>fallbackCopy(t,done));}
  else fallbackCopy(t,done);
}
function fallbackCopy(t,done){
  const ta=document.createElement("textarea");ta.value=t;ta.style.position="fixed";ta.style.opacity="0";
  document.body.appendChild(ta);ta.select();
  try{document.execCommand("copy");done();}catch(e){}
  document.body.removeChild(ta);
}

/* ---------- هایلایت ساده کد ---------- */
function hl(lang,code){
  const l=(lang||"").toLowerCase();
  let s=String(code).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  if(/^(html|xml|svg)$/.test(l)){
    s=s.replace(/&lt;!--[\s\S]*?--&gt;/g,m=>'<span class="tok-com">'+m+'</span>');
    s=s.replace(/&lt;(\/?)([a-zA-Z][\w:-]*)((?:[^&]|&(?!gt;))*?)(\/?)&gt;/g,
      (m,sl,tn,attrs,slv)=>'<span class="tok-tag">&lt;'+sl+tn+'</span>'+
        attrs.replace(/([a-zA-Z-]+)=("[^"]*")/g,'<span class="tok-attr">$1</span>=$2')+
        '<span class="tok-tag">'+slv+'&gt;</span>');
    return s;
  }
  const kwMap={
    js:"const let var function return if else for while class new import from export try catch finally async await throw typeof of in break continue switch case default null undefined true false this document window console",
    javascript:"const let var function return if else for while class new import from export try catch finally async await throw typeof of in break continue switch case default null undefined true false this document window console",
    py:"def return if elif else for while import from class try except finally with as pass raise lambda None True False and or not in is print self range len str int float dict list",
    python:"def return if elif else for while import from class try except finally with as pass raise lambda None True False and or not in is print self range len str int float dict list",
    sql:"select from where insert update delete join left right on as and or not null group by order limit"};
  const kw=kwMap[l]||"";
  const hashCom=/^(py|python|sh|bash|yaml|yml|rb|ruby)$/.test(l)?'|#[^\\n]*':'';
  const kwPart=kw?('\\b(?:'+kw.split(" ").join("|")+')\\b'):'\\b\\B';
  const re=new RegExp(
    '(\\/\\*[\\s\\S]*?\\*\\/|\\/\\/[^\\n]*'+hashCom+')'+
    '|("(?:[^"\\\\\\n]|\\\\.)*"|\'(?:[^\'\\\\\\n]|\\\\.)*\'|`(?:[^`\\\\]|\\\\.)*`)'+
    '|('+kwPart+')'+
    '|\\b(\\d+(?:\\.\\d+)?)\\b','g');
  s=s.replace(re,(m,c,st,k2)=>{
    if(c!==undefined)return '<span class="tok-com">'+m+'</span>';
    if(st!==undefined)return '<span class="tok-str">'+m+'</span>';
    if(k2!==undefined)return '<span class="tok-kw">'+m+'</span>';
    return '<span class="tok-num">'+m+'</span>';
  });
  return s;
}

/* ---------- اجرای کد ---------- */
const _jsRuns=[];
window.addEventListener("message",e=>{
  if(e.data&&e.data.__lr){
    const run=_jsRuns.find(r=>r.el.contentWindow===e.source);
    if(run){const l=document.createElement("div");
      if(e.data.kind==="error")l.className="je";else if(e.data.kind==="warn")l.className="jw";
      l.textContent=e.data.text;run.out.appendChild(l);}
  }
});
function runHtml(code,out){
  out.innerHTML="";
  const f=document.createElement("iframe");
  f.setAttribute("sandbox","allow-scripts allow-forms allow-modals allow-popups");
  f.srcdoc=code;out.appendChild(f);
}
function runJs(code,out){
  out.innerHTML="";
  const log=document.createElement("div");log.className="jout";
  log.innerHTML='<div style="opacity:.6">خروجی کنسول:</div>';out.appendChild(log);
  const f=document.createElement("iframe");
  f.setAttribute("sandbox","allow-scripts");
  f.style.display="none";
  const safe=code.replace(/<\/script/gi,"<\\/script");
  f.srcdoc='<!doctype html><html><head><meta charset="utf-8"></head><body><script>\n'+
    'const send=(k,t)=>{try{parent.postMessage({__lr:1,kind:k,text:t},"*")}catch(e){}};\n'+
    '["log","info","warn","error"].forEach(k=>{console[k]=(...a)=>{send(k,a.map(x=>{try{return typeof x==="object"?JSON.stringify(x):String(x)}catch(e){return String(x)}}).join(" "))};});\n'+
    'window.onerror=(m,s,l)=>send("error",m+" (خط "+l+")");\n'+
    "<\/script><script>"+safe+"\n<\/script></body></html>";
  out.appendChild(f);
  _jsRuns.push({el:f,out:log});
}
/* ---------- رندر نمودار (زیرمجموعه mermaid: flowchart TD/LR) ---------- */
let _flowN=0;
function renderFlow(src){
  const lines=src.split(/\r?\n/).map(l=>l.trim()).filter(l=>l&&!l.startsWith("%%"));
  let dir="TD",body=lines;
  const head=lines.length?lines[0].match(/^(?:flowchart|graph)\s+(TD|TB|LR|RL)/i):null;
  if(head){dir=head[1].toUpperCase();body=lines.slice(1);}
  if(dir==="TB")dir="TD";
  if(dir==="RL")dir="LR";
  const isTD=dir==="TD";
  const nodes={},edges=[],order=[];
  function parseNode(raw){
    raw=raw.trim().replace(/^["\u201c](.*)["\u201d]$/,"$1");
    const m=raw.match(/^([\w\u0600-\u06FF]+)\s*(.*)$/);
    if(!m)return null;
    const id=m[1];let rest=m[2].trim(),shape="rect",label=id;
    if(rest.length>1){
      const a=rest[0],b=rest[rest.length-1];let inner=rest.slice(1,-1).trim();
      if(a==="["&&b==="]")shape="rect";
      else if(a==="("&&b===")")shape=(inner.startsWith("(")&&inner.endsWith(")"))?"circle":"round";
      else if(a==="{"&&b==="}")shape="diamond";
      if(inner)label=inner.replace(/^["\u201c](.*)["\u201d]$/,"$1");
    }
    if(!nodes[id]){nodes[id]={id,label,shape};order.push(id);}
    else if(label!==id)nodes[id].label=label;
    return nodes[id];
  }
  const ere=/(-\.->|==>|-->|---)\s*(?:\|([^|]*)\|)?\s*/;
  for(const line of body){
    let rest=line,parts=[],labels=[],ops=[];
    let m,last=0;
    while((m=rest.slice(last).match(ere))){
      const at=last+m.index;
      parts.push(rest.slice(0,at).trim());
      labels.push(m[2]||"");ops.push(m[1]);
      rest=rest.slice(at+m[0].length);last=0;
    }
    parts.push(rest.trim());
    const nds=parts.map(parseNode);
    for(let i=0;i<nds.length-1;i++)
      if(nds[i]&&nds[i+1])edges.push({from:nds[i].id,to:nds[i+1].id,label:labels[i]||"",dash:ops[i]==="-.->"});
  }
  if(!order.length)throw new Error("گرهی پیدا نشد");
  // عمق هر گره = بلندترین مسیر از ریشه‌ها
  const depth={},adj={};
  edges.forEach(e=>{(adj[e.from]=adj[e.from]||[]).push(e.to);});
  function dfs(id,d){const cur=(depth[id]===undefined?-(1e9):depth[id]);if(cur>=d)return;depth[id]=d;(adj[id]||[]).forEach(t=>dfs(t,d+1));}
  order.forEach(id=>{if(!edges.some(e=>e.to===id))dfs(id,0);});
  order.forEach(id=>{if(depth[id]===undefined)dfs(id,0);});
  const rows=[];
  order.forEach(id=>{const d=depth[id]||0;(rows[d]=rows[d]||[]).push(id);});
  function nsize(n){
    const parts=String(n.label).split(/\s*\|\s*|\n/);
    const w=Math.max(84,Math.min(230,Math.max(...parts.map(x=>x.length))*8.4+34));
    const h=(n.shape==="diamond"?62:42)+(parts.length-1)*17;
    return{w:w,h:h};
  }
  const pos={},size={};
  rows.forEach(row=>row.forEach(id=>{size[id]=nsize(nodes[id]);}));
  // چیدمان لایه‌ای
  const layerMax=rows.map(row=>Math.max(...row.map(id=>isTD?size[id].h:size[id].w)));
  const off=[];let acc=16;
  for(let r=0;r<rows.length;r++){off[r]=acc;acc+=layerMax[r]+(isTD?76:118);}
  rows.forEach((row,r)=>{
    let cur=16;
    row.forEach(id=>{
      const s=size[id];
      pos[id]=isTD?{x:cur+s.w/2,y:off[r]+s.h/2}:{x:off[r]+s.w/2,y:cur+s.h/2};
      cur+=(isTD?s.w:s.h)+46;
    });
  });
  const cross=rows.map(row=>Math.max(...row.map(id=>isTD?size[id].w:size[id].h)));
  const W=(isTD?Math.max(...cross,140):Math.max(acc-118,140))+16;
  const H=(isTD?Math.max(acc-76,140):Math.max(...cross,140))+16;
  function geo(id){const p=pos[id],s=size[id];return{cx:p.x,cy:p.y,x:p.x-s.w/2,y:p.y-s.h/2,w:s.w,h:s.h};}
  const mid="arw"+(++_flowN);
  let sh="";
  edges.forEach(e=>{
    const a=geo(e.from),b=geo(e.to);
    let x1,y1,x2,y2;
    if(isTD){x1=a.cx;y1=a.y+a.h;x2=b.cx;y2=b.y;}
    else{x1=a.x+a.w;y1=a.cy;x2=b.x;y2=b.cy;}
    const mx=(x1+x2)/2,my=(y1+y2)/2;
    sh+='<line x1="'+x1.toFixed(1)+'" y1="'+y1.toFixed(1)+'" x2="'+x2.toFixed(1)+'" y2="'+y2.toFixed(1)+'" stroke="var(--dim)" stroke-width="1.6"'+(e.dash?' stroke-dasharray="6 4"':"")+' marker-end="url(#'+mid+')"/>';
    if(e.label)sh+='<text x="'+mx.toFixed(1)+'" y="'+(my-6).toFixed(1)+'" font-size="11.5" fill="var(--dim)" text-anchor="middle" style="direction:rtl">'+esc(e.label)+"</text>";
  });
  order.forEach(id=>{
    const c=geo(id),n=nodes[id];
    let shapeEl="";
    if(n.shape==="diamond")
      shapeEl='<polygon points="'+c.x+","+(c.y+c.h/2)+" "+(c.x+c.w/2)+","+c.y+" "+(c.x+c.w)+","+(c.y+c.h/2)+" "+(c.x+c.w/2)+","+(c.y+c.h)+'" fill="var(--panel)" stroke="var(--accent)" stroke-width="1.5"/>';
    else if(n.shape==="circle")
      shapeEl='<ellipse cx="'+(c.x+c.w/2)+'" cy="'+(c.y+c.h/2)+'" rx="'+(Math.max(c.w,c.h)/2)+'" ry="'+(Math.max(c.w,c.h)/2)+'" fill="var(--panel)" stroke="var(--accent)" stroke-width="1.5"/>';
    else
      shapeEl='<rect x="'+c.x+'" y="'+c.y+'" width="'+c.w+'" height="'+c.h+'" rx="'+(n.shape==="round"?18:8)+'" fill="var(--panel)" stroke="var(--accent)" stroke-width="1.5"/>';
    sh+=shapeEl;
    const parts=String(n.label).split(/\s*\|\s*|\n/);
    const lh=17,y0=c.cy-(parts.length-1)*lh/2+4.5;
    parts.forEach((ln,i)=>{sh+='<text x="'+c.cx.toFixed(1)+'" y="'+(y0+i*lh).toFixed(1)+'" font-size="12.5" fill="var(--text)" text-anchor="middle" style="direction:rtl">'+esc(ln)+"</text>";});
  });
  return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 '+W.toFixed(0)+" "+H.toFixed(0)+'" style="max-width:100%">'+
    '<defs><marker id="'+mid+'" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'+
    '<path d="M0,0 L10,5 L0,10 z" fill="var(--dim)"/></marker></defs>'+sh+"</svg>";
}

/* ---------- بلوک کد تعاملی ---------- */
function makeCodeBlock(lang,code){
  const box=document.createElement("div");box.className="codebox";
  const head=document.createElement("div");head.className="codehead";
  head.innerHTML='<span class="lang">'+esc(lang||"code")+"</span>";
  const pre=document.createElement("pre");
  const cd=document.createElement("code");
  cd.innerHTML=hl(lang,code);pre.appendChild(cd);
  const out=document.createElement("div");out.className="codeout";out.style.display="none";
  const cp=document.createElement("button");cp.className="codebtn";cp.textContent="کپی";
  cp.onclick=()=>copyText(code);
  head.appendChild(cp);
  const l=(lang||"").toLowerCase();
  let shown=false;
  function toggleOut(builder,label){
    const btn=document.createElement("button");btn.className="codebtn";btn.textContent=label;
    btn.onclick=()=>{
      shown=!shown;
      out.style.display=shown?"block":"none";
      if(shown&&!out.childNodes.length)builder();
      btn.textContent=shown?(l==="js"?"بستن خروجی":"بستن پیش‌نمایش"):label;
    };
    head.appendChild(btn);return btn;
  }
  if(l==="html"||l==="svg")toggleOut(()=>runHtml(code,out),"اجرا ▶");
  else if(l==="js"||l==="javascript")toggleOut(()=>runJs(code,out),"اجرا ▶");
  else if(l==="mermaid"||l==="flowchart"||l==="diagram"||l==="graph"){
    let built=false,codeShown=false;
    function buildDiagram(){
      out.innerHTML="";
      const dv=document.createElement("div");dv.className="diagram";
      try{dv.innerHTML=renderFlow(code);}
      catch(err){dv.innerHTML='<div style="color:var(--err);font-size:12px">رندر نمودار ممکن نشد: '+esc(err.message)+"</div>";}
      out.appendChild(dv);
    }
    const btn=document.createElement("button");btn.className="codebtn";btn.textContent="نمایش کد";
    btn.onclick=()=>{
      codeShown=!codeShown;
      pre.style.display=codeShown?"block":"none";
      out.style.display=codeShown?"none":"block";
      if(!codeShown&&!built){buildDiagram();built=true;}
      btn.textContent=codeShown?"نمایش نمودار":"نمایش کد";
    };
    head.appendChild(btn);
    pre.style.display="none";
    out.style.display="block";
    requestAnimationFrame(()=>{if(!built){buildDiagram();built=true;}});
  }
  box.appendChild(head);box.appendChild(pre);box.appendChild(out);
  return box;
}

/* ---------- رندر مارک‌داون سبک ---------- */
function renderMD(text){
  const codes=[];
  let t=String(text).replace(/```([\w+-]*)\r?\n?([\s\S]*?)(?:```|$)/g,(m,lang,code)=>{
    codes.push({lang:(lang||"").toLowerCase(),code:code.replace(/\n$/,"")});
    return "\uE000"+(codes.length-1)+"\uE001";
  });
  t=esc(t);
  t=t.replace(/\*\*([^*\n]+)\*\*/g,"<b>$1</b>");
  t=t.replace(/`([^`\n]+)`/g,'<code class="ic">$1</code>');
  t=t.replace(/(https?:\/\/[^\s<\uE000-\uE001]+)/g,'<a href="$1" target="_blank" rel="noopener">$1</a>');
  const lines=t.split("\n");
  let html="",listType=null,listBuf=[];
  const flushList=()=>{
    if(listType&&listBuf.length){
      html+="<"+listType+">"+listBuf.map(x=>"<li>"+x+"</li>").join("")+"</"+listType+">";
    }
    listType=null;listBuf=[];
  };
  for(const raw of lines){
    const line=raw;
    const lm=line.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)$/);
    if(lm){
      const isOl=/^\s*\d/.test(line);
      if(listType&&listType!==(isOl?"ol":"ul"))flushList();
      listType=isOl?"ol":"ul";listBuf.push(lm[1]);continue;
    }
    flushList();
    if(/^\s*$/.test(line)){continue;}
    let hm;
    if((hm=line.match(/^(#{1,4})\s+(.*)$/))){html+="<h5>"+hm[2]+"</h5>";continue;}
    if(/^\s*(---+|\*\*\*+|___+)\s*$/.test(line)){html+="<hr>";continue;}
    if((hm=line.match(/^&gt;\s?(.*)$/))){html+="<blockquote>"+hm[1]+"</blockquote>";continue;}
    html+='<p>'+line+"</p>";
  }
  flushList();
  html=html.replace(/\uE000(\d+)\uE001/g,(m,i)=>'<div data-code="'+i+'"></div>');
  const wrap=document.createElement("div");
  wrap.innerHTML=html;
  wrap.querySelectorAll("div[data-code]").forEach(el=>{
    const c=codes[+el.getAttribute("data-code")];
    if(c)el.replaceWith(makeCodeBlock(c.lang,c.code));
  });
  return wrap;
}

/* ---------- پیوست فایل ---------- */
const MAXF=8*1024*1024;
function renderAttachBar(){
  const bar=$("attachbar");
  if(!pending.length){bar.style.display="none";bar.innerHTML="";return;}
  bar.style.display="flex";bar.innerHTML="";
  pending.forEach((p,i)=>{
    const c=document.createElement("span");
    c.className="chip"+(p.error?" cker":"");
    c.innerHTML=(p.kind==="image"?"🖼":p.busy?"⏳":"📄")+' <span class="cn">'+esc(p.name)+"</span>"+(p.error?' <b style="color:var(--err)">⚠</b>':"")+' <span class="cx" title="حذف">✕</span>';
    c.querySelector(".cx").onclick=()=>{pending.splice(i,1);renderAttachBar();};
    bar.appendChild(c);
  });
}
function fileToB64(file){
  return new Promise((res,rej)=>{
    const r=new FileReader();
    r.onload=()=>res(String(r.result).split(",")[1]||"");
    r.onerror=rej;r.readAsDataURL(file);
  });
}
function shrinkImage(b64,mime){
  return new Promise(res=>{
    const img=new Image();
    img.onload=()=>{
      const mx=1024;let w=img.width,h=img.height;
      if(w>mx||h>mx){const k=Math.min(mx/w,mx/h);w=Math.round(w*k);h=Math.round(h*k);}
      const cv=document.createElement("canvas");cv.width=w;cv.height=h;
      cv.getContext("2d").drawImage(img,0,0,w,h);
      res(cv.toDataURL("image/jpeg",0.85).split(",")[1]);
    };
    img.onerror=()=>res(b64);
    img.src="data:"+mime+";base64,"+b64;
  });
}
async function addFiles(files){
  for(const f of files){
    if(f.size>MAXF){pending.push({name:f.name,kind:"file",error:"حجم بیش از ۸ مگابایت"});renderAttachBar();continue;}
    const item={name:f.name,kind:"file",busy:true};
    pending.push(item);renderAttachBar();
    try{
      const b64=await fileToB64(f);
      const ext=(f.name.split(".").pop()||"").toLowerCase();
      if(/^(png|jpg|jpeg|gif|webp|bmp)$/.test(ext)){
        const sb=await shrinkImage(b64,"image/"+(ext==="jpg"?"jpeg":ext));
        item.kind="image";item.b64=sb;item.busy=false;
      }else{
        const r=await fetch("/api/extract",{method:"POST",headers:{"Content-Type":"application/json"},
          body:JSON.stringify({name:f.name,b64:b64})});
        const d=await r.json();
        item.kind=d.kind||"file";item.busy=false;
        if(d.error)item.error=d.error;
        if(d.text)item.text=d.text;
      }
    }catch(e){item.busy=false;item.error="خواندن فایل ناموفق بود";}
    renderAttachBar();
  }
}
$("attach").onclick=()=>$("file").click();
$("file").onchange=e=>{addFiles([...e.target.files]);e.target.value="";};

/* ---------- ارسال ---------- */
function setBusy(b){busy=b;sendBtn.disabled=b||pendingBusy;stopBtn.hidden=!b;}
async function send(){
  const text=inp.value.trim();
  if(busy||pendingBusy)return;
  if(!text&&!pending.length)return;
  inp.value="";inp.style.height="auto";
  // ساخت پیام کاربر
  const msg={role:"user",content:text,att:[]};
  const imgs=[],atts=[];
  pending.forEach(p=>{
    if(p.kind==="image"&&p.b64){imgs.push(p.b64);msg.att.push({name:p.name,kind:"image"});}
    else{atts.push({name:p.name,kind:p.kind,text:p.text||"",error:p.error||""});
         msg.att.push({name:p.name,kind:p.kind,error:p.error||""});}
  });
  if(atts.length)msg.attachments=atts;
  if(imgs.length)msg.images=imgs;
  pending=[];renderAttachBar();
  messages.push(msg);
  // ثبت در تاریخچه
  if(!curId){
    curId=uid10()+uid10();
    chats.unshift({id:curId,title:(text||msg.att[0].name||"گفتگو").slice(0,48),updated:new Date().toISOString(),msgs:[]});
  }
  const cur=chats.find(c=>c.id===curId);
  if(cur){cur.updated=new Date().toISOString();cur.msgs=messages.map(m=>{const o={role:m.role,content:m.content};if(m.att)o.att=m.att;return o;});}
  renderChatList();
  addUserBubble(msg);
  setBusy(true);
  const bot=addBubble("bot","در حال نوشتن…");
  ctl=new AbortController();
  const t0=performance.now();
  let ttft=null,buf="",full="";
  try{
    const res=await fetch("/api/chat/stream",{
      method:"POST",
      headers:Object.assign({"Content-Type":"application/json"},authHeaders()),
      body:JSON.stringify({messages:messages,model:chosenModel||undefined}),
      signal:ctl.signal
    });
    if(res.status===401){showKeybar(true);bot.textContent="این چت خصوصی است؛ کلید API را در نوار بالا وارد کنید.";bot.classList.add("errm");throw new Error("auth");}
    if(res.status===429){bot.textContent="تعداد درخواست‌ها زیاد است؛ کمی صبر کنید و دوباره بفرستید.";bot.classList.add("errm");throw new Error("429");}
    if(!res.ok){bot.textContent="خطای سرور: "+res.status;bot.classList.add("errm");throw new Error("http");}
    const reader=res.body.getReader();
    const dec=new TextDecoder();
    while(true){
      const {done,value}=await reader.read();
      if(done)break;
      buf+=dec.decode(value,{stream:true});
      let idx;
      while((idx=buf.indexOf("\n\n"))>=0){
        const block=buf.slice(0,idx);buf=buf.slice(idx+2);
        const line=block.split("\n").find(l=>l.startsWith("data: "));
        if(!line)continue;
        let obj;try{obj=JSON.parse(line.slice(6));}catch(e){continue;}
        if(obj.error){bot.textContent=(full?full+"\n":"")+"خطا: "+obj.error;bot.classList.add("errm");}
        if(obj.content){
          if(ttft===null){ttft=performance.now()-t0;bot.textContent="";}
          full+=obj.content;
          bot.textContent=full;
          scrollDown();
        }
        if(obj.done&&obj.stats){
          const chip=document.createElement("div");
          chip.className="stats";
          chip.textContent=obj.stats.tps+" توکن/ثانیه — "+obj.stats.tokens+" توکن — شروع پاسخ: "+obj.stats.ttft+" ثانیه";
          chat.appendChild(chip);
          $("speedbadge").textContent="سرعت: "+obj.stats.tps+" tok/s";
          scrollDown();
        }
      }
    }
    if(full){
      messages.push({role:"assistant",content:full});
      if(cur){cur.msgs=messages.map(m=>{const o={role:m.role,content:m.content};if(m.att)o.att=m.att;return o;});}
      // رندر نهایی مارک‌داون + دکمه‌ها
      bot.classList.remove("errm");
      bot.innerHTML="";bot.appendChild(renderMD(full));
      addMsgFoot(bot,full);
      scheduleSave();
    }
  }catch(e){
    if(e.name!=="AbortError"&&!full){
      bot.textContent="خطا در ارتباط با سرور. سرویس مدل را بررسی کنید.";
      bot.classList.add("errm");
    }
    if(full){try{bot.innerHTML="";bot.appendChild(renderMD(full));addMsgFoot(bot,full);}catch(e){bot.textContent=full;}if(cur){cur.msgs=messages.map(m=>{const o={role:m.role,content:m.content};if(m.att)o.att=m.att;return o;});scheduleSave();}}
  }
  setBusy(false);
  if(pendingBusy)sendBtn.disabled=true;
  scrollDown();
}
sendBtn.onclick=send;
stopBtn.onclick=()=>{if(ctl)ctl.abort();setBusy(false);};
inp.addEventListener("keydown",e=>{
  if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send();}
});
inp.addEventListener("input",()=>{
  inp.style.height="auto";
  inp.style.height=Math.min(inp.scrollHeight,140)+"px";
});
$("send").disabled=false;

/* ---------- شروع ---------- */
loadHistory();
</script>
</body>
</html>
"""






# =====================================================================
# هندلر HTTP
# =====================================================================
def build_handler(settings, store, limiter, boot_ts, hist):
    MAX_BODY = 12 * 1024 * 1024  # 12MB (برای پیوست فایل)

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
                    out = {"role": role, "content": content[:max_chars]}
                    if role == "user":
                        # عکس‌ها برای مدل‌های بینایی به Ollama پاس داده می‌شوند
                        imgs = m.get("images")
                        if isinstance(imgs, list):
                            ok = [i for i in imgs[:4]
                                  if isinstance(i, str) and 0 < len(i) <= 9_000_000]
                            if ok:
                                out["images"] = ok
                        # متن استخراج‌شدهٔ پیوست‌ها به محتوای پیام افزوده می‌شود
                        atts = m.get("attachments")
                        if isinstance(atts, list) and atts:
                            folded = []
                            for a in atts[:6]:
                                if isinstance(a, dict) and a.get("name"):
                                    folded.append("«فایل پیوست: " + str(a["name"])[:80] + "»\n"
                                                  + str(a.get("text") or "")[:6000])
                            if folded:
                                out["content"] = out["content"] + "\n\n" + "\n\n".join(folded)
                    clean.append(out)
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
            elif path == "/api/models":
                self._json(200, {"models": list_models(settings), "current": settings.model})
            elif path == "/api/history":
                qs = parse_qs(urlparse(self.path).query)
                uid = (qs.get("uid") or [""])[0]
                if not HistoryStore.safe_uid(uid):
                    return self._json(400, {"error": "شناسه نامعتبر است"})
                self._json(200, {"chats": hist.load(uid)})
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
                elif path == "/api/extract":
                    self.handle_extract(body)
                elif path == "/api/history":
                    self.handle_history_save(body)
                else:
                    self._json(404, {"error": "یافت نشد"})
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True
            except Exception as exc:
                try:
                    self._json(500, {"error": f"خطای داخلی: {exc}"})
                except Exception:
                    self.close_connection = True

        # ---------- DELETE (حذف تاریخچه) ----------
        def do_DELETE(self):
            path = self.path.split("?")[0]
            if path == "/api/history":
                qs = parse_qs(urlparse(self.path).query)
                uid = (qs.get("uid") or [""])[0]
                if not HistoryStore.safe_uid(uid):
                    return self._json(400, {"error": "شناسه نامعتبر است"})
                hist.delete(uid, (qs.get("id") or [None])[0])
                return self._json(200, {"ok": True})
            self._json(404, {"error": "یافت نشد"})

        # ---------- استخراج متن پیوست ----------
        def handle_extract(self, body):
            name = str(body.get("name") or "file")
            b64 = body.get("b64") or ""
            if not isinstance(b64, str) or not b64:
                return self._json(400, {"error": "فایلی دریافت نشد"})
            if len(b64) > 11_000_000:
                return self._json(413, {"error": "حجم فایل بیش از حد مجاز است (حداکثر ۸ مگابایت)"})
            try:
                data = base64.b64decode(b64)
            except Exception:
                return self._json(400, {"error": "فایل قابل خواندن نبود"})
            text, kind = extract_text_from(name, data)
            res = {"name": name[:120], "kind": kind, "chars": len(text)}
            if kind == "image":
                res["image_ok"] = True
            elif kind == "doc-legacy":
                res["error"] = "قالب doc قدیمی پشتیبانی نمی‌شود؛ فایل را با پسوند docx ذخیره و دوباره پیوست کنید."
            elif kind == "binary":
                res["error"] = "از این نوع فایل نمی‌توان متن استخراج کرد."
            elif not text.strip():
                res["error"] = "متنی در فایل پیدا نشد (اگر PDF اسکن‌شده است، متن ندارد)."
            else:
                res["text"] = text
            self._json(200, res)

        # ---------- ذخیره تاریخچه ----------
        def handle_history_save(self, body):
            uid = body.get("uid")
            if not HistoryStore.safe_uid(uid):
                return self._json(400, {"error": "شناسه نامعتبر است"})
            try:
                hist.save(uid, body.get("chats") or [])
            except Exception as exc:
                return self._json(400, {"error": f"ذخیره ناموفق: {exc}"})
            self._json(200, {"ok": True})

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
            model = body.get("model")
            if not (isinstance(model, str) and MODEL_RE.fullmatch(model)):
                model = None
            if not any(m["role"] == "system" for m in msgs):
                msgs = [{"role": "system", "content": self._effective_system(msgs)}] + msgs
            else:
                msgs = self._inject_kb(msgs)

            self._sse_headers()
            ttft, full, last_stats = None, "", {}
            t0 = time.perf_counter()
            try:
                for obj in ollama_chat_stream(settings, msgs, settings.max_output_tokens, model=model):
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
            model_use = (model_name if isinstance(model_name, str) and MODEL_RE.fullmatch(model_name)
                         else settings.model)
            model_name = model_use
            t0 = time.perf_counter()
            ttft, full, last_stats = None, "", {}

            if stream:
                self._sse_headers()
                try:
                    for obj in ollama_chat_stream(settings, msgs, num_predict, model=model_use):
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
                    for obj in ollama_chat_stream(settings, msgs, num_predict, model=model_use):
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
    hist = HistoryStore(settings.data_dir)
    boot_ts = time.time()
    handler = build_handler(settings, store, limiter, boot_ts, hist)

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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
site_kb.py — پایگاه دانش خودکار از وب‌سایت کلینیک (فقط کتابخانه استاندارد)
===========================================================================

این ماژول محتوای وب‌سایت کلینیک را می‌خواند و به دانش قابل‌جست‌وجو تبدیل می‌کند:

  ۱) صفحهٔ اصلی سایت          → عنوان و توضیحات متا
  ۲) باندل جاوااسکریپت سایت   → متن‌های فارسی داخل رابط کاربری (خدمات، سوالات متداول، مسیر نوبت‌دهی…)
  ۳) APIهای عمومی سایت        → فهرست خدمات (با مدت و قیمت)، شعبه‌ها با آدرس/تلفن و مشاوران هر شعبه

خروجی در  data/site_kb.json  ذخیره می‌شود و chat_server.py هنگام پاسخ‌گویی،
بخش‌های مرتبط با پرسش کاربر را انتخاب و به پرامپت مدل اضافه می‌کند (RAG سبک).

اجرا:
    python site_kb.py                                  # سایت پیش‌فرض
    python site_kb.py http://130.185.73.157/            # آدرس دلخواه
    python site_kb.py <آدرس> <مسیر-خروجی.json>
"""

import json
import re
import sys
import time
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

DEFAULT_SITE_URL = "http://130.185.73.157/"
DEFAULT_OUT_NAME = "site_kb.json"
USER_AGENT = "LLMRose-KB/1.0 (+knowledge builder for site assistant)"
FETCH_TIMEOUT = 15
MAX_ASSET_BUNDLES = 2          # حداکثر تعداد فایل JS خوانده‌شده از سایت
SENT_PER_CHUNK = 700           # طول تقریبی هر قطعه دانش (نویسه)

# APIهای عمومی سایت که محتوای زنده می‌دهند
KNOWN_PUBLIC_APIS = {
    "/api/v1/public/services": "خدمات",
    "/api/v1/public/clinics-map": "شعبه‌ها",
    "/api/v1/public/counselors": "مشاوران",
}

SESSION_TYPE_FA = {"in_person": "حضوری", "online": "آنلاین", "phone": "تلفنی"}
CURRENCY_FA = {"IRR": "ریال", "IRT": "تومان"}

# =====================================================================
# نرمال‌سازی و توکن‌سازی فارسی
# =====================================================================
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_ARABIC_TO_FA = str.maketrans({"ي": "ی", "ك": "ک", "أ": "ا", "إ": "ا", "ؤ": "و",
                               "ئ": "ی", "ة": "ه", "ۀ": "ه"})
_DIACRITICS = re.compile(r"[\u064B-\u065F\u0670\u0640]")
# نشانه‌گذاری عربی (؟ ، ؛ ۀ۔) داخل بازه ‎\u0600-\u06FF‎ است و باید صریحاً حذف شود
_ARABIC_PUNCT = re.compile(r"[\u060C\u061B\u061F\u06D4\u066B\u066C\u066D\u06DD]")
_NON_WORD = re.compile(r"[^\w\u0600-\u06FF]+", re.UNICODE)
_SPACES = re.compile(r"\s+")

STOPWORDS = set("""
از به با که و در را برای بر می این آن اینها آنها چه چیست هست هستی است هستند بود بودن
من تو ما شما او ایشان اون خود های ها تر ترین تا هم یا اگر ولی اما هر هیچ چرا چگونه چطور
کی کجا چند وقتی که وقتی لطفا سلام ممنون مرسی بله خیر نه آیا دیگر دیگری باید شده شود کند
کردن شدن دارد ندارد دارم دارید دارن بود بودم بودند میشه باشه هستن هستم هستید کن کنید کنه
خواهم خواهیم خواهید بده بدم بدید فکر نظر مورد روش حال حالا الان بعد قبل بین روی زیر بالا
پایین فقط هم چیز چیزی کس کسی جای جایی وقت وقتی امروز دیروز فردا خیلی کمی بسیار شاید حتما
the a an of to in on is are was were be been and or not for with what how why where when
i you we they he she it this that your my our their do does did can could will would
""".split())


def normalize(text):
    """نرمال‌سازی متن فارسی برای جست‌وجو (ی/ک عربی، اعراب، نیم‌فاصله، اعداد)."""
    if not text:
        return ""
    t = text.translate(_DIGITS).translate(_ARABIC_TO_FA)
    t = _DIACRITICS.sub("", t)
    t = t.replace("\u200c", " ")
    t = _ARABIC_PUNCT.sub(" ", t)
    t = _NON_WORD.sub(" ", t)
    return _SPACES.sub(" ", t).strip().lower()


# جمع‌های رایج حوزه سلامت روان → مفرد (برای تطابق بهتر پرسش با دانش)
_PLURAL = {
    "خدمات": "خدمت", "جلسات": "جلسه", "مشاوران": "مشاور", "مشاورین": "مشاور",
    "درمانگران": "درمانگر", "روانشناسان": "روانشناس", "رواندرمانگران": "درمانگر",
    "مقالات": "مقاله", "سوالات": "سوال", "ساعات": "ساعت", "مراکز": "مرکز",
    "کارگاه‌ها": "کارگاه", "کلینیک‌ها": "کلینیک", "قیمت‌ها": "قیمت",
    "نوبت‌ها": "نوبت", "هزینه‌ها": "هزینه", "شعبه‌ها": "شعبه",
    "پرسش‌ها": "پرسش", "پاسخ‌ها": "پاسخ", "بسته‌ها": "بسته",
}


def tokenize(text):
    """توکن‌های معنادار (بدون ایست‌واژه‌ها، با یکسان‌سازی جمع/مفرد)"""
    out = []
    for w in normalize(text).split():
        if len(w) <= 1 or w in STOPWORDS:
            continue
        out.append(_PLURAL.get(w, w))
    return out


# =====================================================================
# دریافت صفحات
# =====================================================================
def _fetch_text(url):
    """دریافت متن یک آدرس؛ در خطا None برمی‌گرداند."""
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT,
                                    "Accept": "text/html,application/json,*/*"})
        with urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            raw = resp.read()
        for enc in ("utf-8", "cp1256"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return None


class _TextExtract(HTMLParser):
    """استخراج متن قابل‌خواندن از HTML (بدون اسکریپت و استایل)"""
    SKIP = {"script", "style", "noscript", "svg", "head", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def html_visible_text(raw_html):
    p = _TextExtract()
    try:
        p.feed(raw_html)
    except Exception:
        pass
    return " ".join(p.parts)


def html_meta(raw_html):
    """(عنوان، توضیحات متا) از HTML"""
    m = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.S | re.I)
    title = _SPACES.sub(" ", re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""
    m = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']',
                  raw_html, re.S | re.I)
    desc = m.group(1).strip() if m else ""
    if not desc:
        m = re.search(r'<meta\s+content=["\'](.*?)["\']\s+name=["\']description["\']',
                      raw_html, re.S | re.I)
        desc = m.group(1).strip() if m else ""
    return title, desc


# =====================================================================
# استخراج جمله‌های فارسی از باندل JS (سایت‌های SPA متن را در JS نگه می‌دارند)
# =====================================================================
_SENT = re.compile(
    r"[\u0600-\u06FF][\u0600-\u06FF\u200c\s\d،.,!؟?:؛()%«»+\-—/]{14,500}")
_DROP_PREFIX = ("خطا در", "err", "fail")


def fa_sentences(raw_js):
    """جمله‌های فارسی خوانا از داخل کد جاوااسکریپت"""
    out, seen = [], set()
    for m in _SENT.finditer(raw_js or ""):
        s = _SPACES.sub(" ", m.group(0)).strip(" ،.,!؟-—")
        if len(s) < 20 or s in seen:
            continue
        low = s.lower()
        if low.startswith(_DROP_PREFIX) or "http" in low or ".js" in low \
                or "/api/" in s or "\\u" in s:
            continue
        if len(s.split()) < 3:
            continue
        seen.add(s)
        out.append(s)
    return out


def _group_sentences(sentences, title, source, limit=SENT_PER_CHUNK):
    """گروه‌بندی جمله‌ها در قطعه‌های ~<limit> نویسه"""
    chunks, buf, size = [], [], 0
    for s in sentences:
        if size + len(s) > limit and buf:
            chunks.append({"title": title, "text": "\n".join(buf), "source": source})
            buf, size = [], 0
        buf.append(s)
        size += len(s) + 1
    if buf:
        chunks.append({"title": title, "text": "\n".join(buf), "source": source})
    return chunks


# =====================================================================
# قالب‌بندی داده‌های API عمومی
# =====================================================================
def _fmt_price(amount, currency):
    try:
        num = f"{int(float(amount)):,}"
    except (TypeError, ValueError):
        return ""
    cur = CURRENCY_FA.get((currency or "IRR").upper(), currency or "ریال")
    return f"{num} {cur}"


def chunks_from_services(items):
    out = []
    for it in items:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        lines = [f"خدمت: {title}"]
        if it.get("description"):
            lines.append(f"توضیح: {it['description'].strip()}")
        if it.get("duration_minutes"):
            lines.append(f"مدت جلسه: {it['duration_minutes']} دقیقه")
        stype = SESSION_TYPE_FA.get(it.get("session_type"), it.get("session_type"))
        if stype:
            lines.append(f"نوع ارائه: {stype}")
        price = _fmt_price(it.get("price_amount"), it.get("price_currency"))
        if price:
            lines.append(f"هزینه: {price}")
        out.append({"title": f"خدمت: {title}", "text": "\n".join(lines),
                    "source": "/api/v1/public/services"})
    return out


def chunks_from_clinics(items, counselor_total=None):
    out = []
    for it in items:
        name = (it.get("name") or "").strip()
        if not name:
            continue
        lines = [f"شعبه کلینیک: {name}"]
        city, prov = (it.get("city") or "").strip(), (it.get("province") or "").strip()
        if city or prov:
            lines.append(f"شهر/استان: {city}{' — ' + prov if prov and prov != city else ''}")
        if it.get("address"):
            lines.append(f"آدرس: {it['address'].strip()}")
        if it.get("phone"):
            lines.append(f"تلفن: {it['phone']}")
        if it.get("manager_name"):
            mg = f"مدیر شعبه: {it['manager_name']}"
            if it.get("manager_phone"):
                mg += f" — {it['manager_phone']}"
            lines.append(mg)
        if it.get("working_hours"):
            lines.append(f"ساعات کاری: {it['working_hours']}")
        if it.get("map_url"):
            lines.append(f"لینک نقشه: {it['map_url']}")
        cons = it.get("counselors") or []
        if cons:
            names = []
            for c in cons[:25]:
                nm = c.get("name") or ""
                if not nm:
                    continue
                deg = c.get("degree") or ""
                tag = " | رزرو آنلاین" if c.get("bookable") else ""
                names.append(f"{nm} ({deg}{tag})" if deg else f"{nm}{tag}")
            lines.append(f"مشاوران این شعبه ({len(cons)} نفر): " + "، ".join(names))
        out.append({"title": f"شعبه: {name}", "text": "\n".join(lines),
                    "source": "/api/v1/public/clinics-map"})

    # قطعه خلاصه شبکه شعبه‌ها
    cities = sorted({(it.get("city") or "").strip() for it in items
                     if (it.get("city") or "").strip()})
    if cities:
        txt = (f"کلینیک رز شبکه‌ای از {len(items)} شعبه در شهرهای زیر دارد:\n"
               + "، ".join(cities)
               + ".\nآدرس دقیق، تلفن و مشاوران هر شعبه در بخش «نقشه کلینیک‌ها» سایت موجود است.")
        if counselor_total:
            txt = f"در مجموع {counselor_total} مشاور و روان‌درمانگر در شعبه‌های کلینیک رز فعالیت می‌کنند.\n" + txt
        out.insert(0, {"title": "شعبه‌های کلینیک رز", "text": txt,
                       "source": "/api/v1/public/clinics-map"})
    return out


# =====================================================================
# ساخت پایگاه دانش
# =====================================================================
def build_kb(base_url, out_path, log=None):
    """ساخت کامل پایگاه دانش از سایت؛ خروجی: (data یا None، پیام خطا یا None)"""
    log = log or (lambda *a: None)
    base = base_url if "://" in base_url else "http://" + base_url
    base = base.rstrip("/") + "/"
    chunks, errors = [], []
    stats = {"home": False, "assets": 0, "apis": 0, "sentences": 0}

    # ۱) صفحه اصلی
    home = _fetch_text(base)
    if home:
        stats["home"] = True
        title, desc = html_meta(home)
        visible = html_visible_text(home)
        intro = "\n".join(x for x in (title, desc, visible) if x)
        if intro.strip():
            chunks.append({"title": "معرفی کلینیک (از وب‌سایت)",
                           "text": intro[:1200], "source": "صفحه اصلی سایت"})
        # ۲) باندل‌های JS سایت SPA
        assets = re.findall(r'(?:src|href)=["\'](/assets/[^"\']+\.js)["\']', home)
        seen = set()
        picked = [a for a in assets if not (a in seen or seen.add(a))][:MAX_ASSET_BUNDLES]
        for a in picked:
            js = _fetch_text(urljoin(base, a))
            if not js:
                continue
            stats["assets"] += 1
            sents = fa_sentences(js)
            stats["sentences"] += len(sents)
            chunks.extend(_group_sentences(
                sents, "اطلاعات عمومی وب‌سایت کلینیک", f"باندل سایت {a}"))
    else:
        errors.append("صفحه اصلی سایت در دسترس نبود")

    # ۳) APIهای عمومی (داده زنده)
    api_hits = {}
    for ep in KNOWN_PUBLIC_APIS:
        raw = _fetch_text(urljoin(base, ep.lstrip("/")))
        if not raw:
            errors.append(f"API {ep} پاسخ نداد")
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            errors.append(f"API {ep} پاسخ JSON معتبر نداد")
            continue
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            continue
        api_hits[ep] = items
        stats["apis"] += 1

    svc = api_hits.get("/api/v1/public/services") or []
    clm = api_hits.get("/api/v1/public/clinics-map") or []
    cns = api_hits.get("/api/v1/public/counselors") or []

    if svc:
        chunks.extend(chunks_from_services(svc))
        chunks.append({"title": "توجه درباره قیمت‌ها",
                       "text": "مبالغ خدمات بر پایه داده رسمی سایت است و ممکن است تغییر کند؛ "
                               "قیمت قطعی و تخفیف‌ها را پذیرش کلینیک اعلام می‌کند.",
                       "source": "/api/v1/public/services"})
    if clm:
        chunks.extend(chunks_from_clinics(clm, counselor_total=len(cns) or None))

    if not chunks:
        msg = "هیچ محتوایی از سایت دریافت نشد: " + ("؛ ".join(errors) or "دلیل نامشخص")
        return None, msg

    data = {
        "version": 1,
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "base_url": base,
        "stats": stats,
        "errors": errors,
        "chunks": chunks,
    }
    try:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(out_path) + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(out_path)
    except OSError as e:
        return None, f"ذخیره فایل پایگاه دانش ممکن نشد: {e}"
    log(f"پایگاه دانش ساخته شد: {len(chunks)} قطعه "
        f"(صفحه اصلی: {'✓' if stats['home'] else '✗'}، باندل JS: {stats['assets']}، "
        f"API: {stats['apis']}، جمله‌ها: {stats['sentences']})")
    return data, None


# =====================================================================
# بارگذاری و بازیابی (RAG سبک)
# =====================================================================
def load_kb(path):
    """بارگذاری KB و محاسبه توکن‌ها برای امتیازدهی سریع"""
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(d, dict) or not d.get("chunks"):
        return None
    for c in d["chunks"]:
        c["_tt"] = set(tokenize(c.get("title") or ""))
        freq = {}
        for w in tokenize(c.get("text") or ""):
            freq[w] = freq.get(w, 0) + 1
        c["_tw"] = freq
    return d


def retrieve(kb, query, top_k=3, min_score=None):
    """بهترین قطعه‌های مرتبط با پرسش کاربر

    min_score خودکار است: پرسش یک‌کلمه‌ای حد پایین‌تر دارد تا موضوعات تک‌کلیدواژه‌ای
    (مثل «نوروفیدبک») هم پیدا شوند؛ پرسش‌های بلندتر سخت‌گیرانه‌تر فیلتر می‌شوند.
    """
    if not kb or not query:
        return []
    qtoks = set(tokenize(query))
    if not qtoks:
        return []
    if min_score is None:
        min_score = 2 * min(len(qtoks), 2)
    scored = []
    for c in kb["chunks"]:
        s = 0
        for w in qtoks:
            if w in c["_tt"]:
                s += 3
            tw = c["_tw"].get(w)
            if tw:
                s += 2 + min(tw - 1, 2)
        if s >= min_score:
            scored.append((s, c))
    if not scored:
        return []
    scored.sort(key=lambda x: (-x[0], len(x[1].get("text") or "")))
    best = scored[0][0]
    return [c for s, c in scored[:top_k] if s >= best * 0.6]


def build_context(kb, query, max_chars=1800):
    """متن زمینه آماده تزریق به پرامپت؛ اگر چیز مرتبطی نبود رشته خالی"""
    hits = retrieve(kb, query)
    if not hits:
        return ""
    parts, used = [], 0
    for c in hits:
        block = f"— {c.get('title') or 'اطلاعات سایت'} —\n{(c.get('text') or '').strip()}"
        if parts and used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


# =====================================================================
# اجرای مستقل (دستی)
# =====================================================================
def main():
    base = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SITE_URL
    out = sys.argv[2] if len(sys.argv) > 2 else str(
        Path(__file__).resolve().parent / "data" / DEFAULT_OUT_NAME)

    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print(f"ساخت پایگاه دانش از: {base}")
    t0 = time.time()
    data, err = build_kb(base, out, log=print)
    if err or not data:
        print(f"✗ ناموفق: {err}")
        sys.exit(1)
    print(f"✓ ذخیره شد: {out}  ({time.time() - t0:.1f} ثانیه)")
    print(f"  ساخت       : {data['built_at']}")
    print(f"  قطعه‌ها    : {len(data['chunks'])}")
    if data.get("errors"):
        print(f"  هشدارها    : {'؛ '.join(data['errors'])}")
    print("  نمونه عنوان‌ها:")
    for c in data["chunks"][:10]:
        print(f"   • {c['title']}")
    # آزمون سریع بازیابی
    kb = load_kb(out)
    for q in ("هزینه جلسه آنلاین چقدر است؟", "آدرس شعبه تهران", "نوروفیدبک چیست؟",
              "چطور نوبت بگیرم؟"):
        hits = retrieve(kb, q)
        titles = " | ".join(h["title"] for h in hits) or "—"
        print(f"  بازیابی «{q}» → {titles}")


if __name__ == "__main__":
    main()

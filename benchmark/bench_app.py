#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM Rose — برنامه تست سرعت و کیفیت مدل زبانی فارسی (Qwen3-8B روی Ollama)
=======================================================================

فقط با کتابخانه استاندارد پایتون اجرا می‌شود؛ نیازی به نصب هیچ پکیجی نیست.

پیش‌نیازها:
    1) Ollama در حال اجرا باشد (برنامه Ollama یا سرویس آن فعال باشد)
    2) مدل دانلود شده باشد:   ollama pull qwen3:8b
    3) پایتون 3.9 به بالا

نحوه اجرا:
    python bench_app.py                    تست کامل: سرعت + کیفیت + ذخیره گزارش
    python bench_app.py --speed            فقط تست سرعت
    python bench_app.py --quality          فقط ۱۰ تست کیفیت فارسی
    python bench_app.py --think            مقایسه سرعت با/بدون حالت تفکر Qwen3
    python bench_app.py --chat             چت تعاملی با نمایش سرعت هر پاسخ
    python bench_app.py --server 192.168.1.10 --model qwen3:8b

خروجی گزارش:
    benchmark/reports/bench_report_<زمان>.md   گزارش خوانا
    benchmark/reports/bench_raw_<زمان>.json    داده خام برای تحلیل
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib import request as urlreq
from urllib.error import HTTPError, URLError

# ---------- آماده‌سازی یونیکد و رنگ برای کنسول ویندوز ----------
if sys.platform == "win32":
    os.system("")  # فعال‌سازی پشتیبانی ANSI در کنسول ویندوز
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

GREEN, YELLOW, RED, CYAN, DIM, RESET, BOLD = (
    "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[2m", "\033[0m", "\033[1m",
)

PERSIAN_RE = re.compile(r"[\u0600-\u06FF\u200c]")
LATIN_RE = re.compile(r"[A-Za-z]")
FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
REPORT_DIR = Path(__file__).resolve().parent / "reports"


def ns2s(ns):
    return (ns or 0) / 1e9


def fa_ratio(text):
    """نسبت نویسه‌های فارسی در متن"""
    return len(PERSIAN_RE.findall(text or "")) / max(len(text or ""), 1)


def latin_ratio(text):
    return len(LATIN_RE.findall(text or "")) / max(len(text or ""), 1)


def norm_digits(text):
    """تبدیل ارقام فارسی/عربی به لاتین برای مقایسه"""
    return (text or "").translate(FA_DIGITS)


def parse_json_block(text):
    """اولین بلوک JSON موجود در متن را استخراج و پارس می‌کند"""
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def check(cond, name, detail=""):
    return {"check": name, "passed": bool(cond), "detail": detail}


def speed_verdict(tps):
    if tps >= 15:
        return "عالی"
    if tps >= 10:
        return "خوب"
    if tps >= 6:
        return "قابل قبول"
    return "کند"


# =====================================================================
# کلاینت Ollama
# =====================================================================
class OllamaClient:
    def __init__(self, server, model):
        self.server = server.rstrip("/")
        self.model = model

    def _post(self, path, payload, timeout=900):
        data = json.dumps(payload).encode("utf-8")
        req = urlreq.Request(
            f"{self.server}{path}", data=data,
            headers={"Content-Type": "application/json"},
        )
        return urlreq.urlopen(req, timeout=timeout)

    def info(self):
        """نسخه سرور و مشخصات مدل"""
        out = {}
        try:
            with urlreq.urlopen(f"{self.server}/api/version", timeout=10) as r:
                out["version"] = json.loads(r.read().decode()).get("version", "?")
        except Exception:
            out["version"] = "?"
        try:
            with self._post("/api/show", {"model": self.model}, timeout=15) as r:
                d = json.loads(r.read().decode())
                det = d.get("details", {})
                out["params"] = det.get("parameter_size", "?")
                out["quant"] = det.get("quantization_level", "?")
        except Exception:
            out["params"] = "?"
            out["quant"] = "?"
        return out

    def chat(self, messages, think=False, stream=True, options=None, on_delta=None):
        """
        یک درخواست چت به /api/chat (استریم NDJSON).
        خروجی: (متن پاسخ، متن تفکر، آمار شامل ttft/wall/eval_count/...)
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": bool(stream),
            "think": bool(think),
            "options": {"num_ctx": 8192, "temperature": 0.7, "top_p": 0.8, "top_k": 20},
        }
        if options:
            payload["options"].update(options)

        data = json.dumps(payload).encode("utf-8")
        req = urlreq.Request(
            f"{self.server}/api/chat", data=data,
            headers={"Content-Type": "application/json"},
        )
        t0 = time.perf_counter()
        ttft = None
        parts, think_parts = [], []
        stats = {}
        with urlreq.urlopen(req, timeout=900) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = obj.get("message") or {}
                delta = msg.get("content") or ""
                t_delta = msg.get("thinking") or ""
                if delta or t_delta:
                    if ttft is None:
                        ttft = time.perf_counter() - t0
                if delta:
                    parts.append(delta)
                    if on_delta:
                        on_delta(delta)
                if t_delta:
                    think_parts.append(t_delta)
                if obj.get("done"):
                    stats = obj
        text = "".join(parts)
        wall = time.perf_counter() - t0
        merged = dict(stats)
        merged["ttft"] = ttft if ttft is not None else wall
        merged["wall"] = wall
        return text, "".join(think_parts), merged


def tok_stats(st):
    """استخراج شاخص‌های سرعت از آمار خام Ollama"""
    eval_count = st.get("eval_count") or 0
    eval_s = ns2s(st.get("eval_duration"))
    prompt_count = st.get("prompt_eval_count") or 0
    prompt_s = ns2s(st.get("prompt_eval_duration"))
    return {
        "eval_count": eval_count,
        "tps": (eval_count / eval_s) if eval_s > 0 else 0.0,
        "prompt_tps": (prompt_count / prompt_s) if prompt_s > 0 else 0.0,
        "ttft": st.get("ttft", 0.0),
        "wall": st.get("wall", 0.0),
        "load_s": ns2s(st.get("load_duration")),
    }


# =====================================================================
# تست‌های سرعت
# =====================================================================
SPEED_CASES = [
    ("کوتاه", "در یک جمله بگو هواپیما چگونه پرواز می‌کند.", 120),
    ("متوسط", "در سه پاراگراف مزایای کتاب‌خوانی را توضیح بده.", 350),
    ("بلند", "یک مقاله حدود ۴۰۰ کلمه‌ای درباره تاریخ تهران و تحولات آن در سده اخیر بنویس.", 700),
]


def run_speed(client):
    rows = []
    print(f"\n{BOLD}گرم کردن (لود مدل در صورت سرد بودن)...{RESET}", flush=True)
    _, _, st = client.chat(
        [{"role": "user", "content": "سلام. فقط بگو آماده‌ام."}],
        think=False, options={"num_predict": 10},
    )
    warm = tok_stats(st)
    if warm["load_s"] > 0.5:
        print(f"{DIM}مدل سرد بود؛ زمان لود در RAM: {warm['load_s']:.1f} ثانیه "
              f"(برای حذف این تأخیر: OLLAMA_KEEP_ALIVE=-1){RESET}")
    else:
        print(f"{DIM}مدل از قبل در RAM گرم است.{RESET}")

    for name, prompt, max_tok in SPEED_CASES:
        print(f"\n  اجرای سناریو {BOLD}{name}{RESET} ...", flush=True)
        text, _, st = client.chat(
            [{"role": "user", "content": prompt}],
            think=False, options={"num_predict": max_tok},
        )
        ts = tok_stats(st)
        rows.append({"case": name, "tokens": ts["eval_count"], "tps": ts["tps"],
                     "ttft": ts["ttft"], "wall": ts["wall"], "chars": len(text)})
        print(f"    {GREEN}{ts['tps']:.1f}{RESET} توکن/ثانیه | "
              f"TTFT {CYAN}{ts['ttft']:.2f}s{RESET} | "
              f"{ts['eval_count']} توکن | {ts['wall']:.1f} ثانیه | {len(text)} نویسه")
    return rows


def run_think_compare(client):
    """مقایسه سرعت پاسخ کوتاه با و بدون حالت تفکر Qwen3"""
    prompt = SPEED_CASES[0][1]
    out = {}
    for label, think in (("بدون تفکر", False), ("با تفکر", True)):
        print(f"\n  اجرای {BOLD}{label}{RESET} ...", flush=True)
        text, ttext, st = client.chat(
            [{"role": "user", "content": prompt}],
            think=think, options={"num_predict": 400},
        )
        ts = tok_stats(st)
        out[label] = {"tokens": ts["eval_count"], "tps": ts["tps"],
                      "ttft": ts["ttft"], "wall": ts["wall"], "think_chars": len(ttext)}
        print(f"    {GREEN}{ts['tps']:.1f}{RESET} توکن/ثانیه | TTFT {ts['ttft']:.2f}s | "
              f"{ts['eval_count']} توکن | {ts['wall']:.1f} ثانیه"
              + (f" | {DIM}متن تفکر: {len(ttext)} نویسه{RESET}" if ttext else ""))
    return out


# =====================================================================
# تست‌های کیفیت فارسی
# =====================================================================
SUMMARY_TEXT = (
    "شهر تهران در دو سده اخیر از روستایی کوچک به یکی از بزرگ‌ترین کلان‌شهرهای جهان تبدیل شده است. "
    "انتخاب تهران به پایتخت در دوران قاجار رشد سریع آن را آغاز کرد. "
    "در دهه‌های اخیر مترو، بزرگراه‌ها و برج‌های بلند چهره شهر را کاملاً دگرگون کرده‌اند. "
    "با این حال مشکلاتی مانند آلودگی هوا و ترافیک سنگین، زندگی روزمره شهروندان را دشوار کرده است. "
    "کارشناسان معتقدند توسعه حمل‌ونقل عمومی کلید حل این مشکلات است."
)

QUALITY_CASES = [
    {
        "id": "knowledge", "title": "دانش عمومی فارسی", "category": "پرسش و پاسخ",
        "prompt": "پایتخت ایران کدام شهر است و ایران چند استان دارد؟ کوتاه جواب بده.",
        "num_predict": 150,
        "checks": lambda t: [
            check("تهران" in t, "ذکر پایتخت (تهران)"),
            check(re.search(r"\b31\b", norm_digits(t)) is not None or "سی‌ویک" in t,
                  "تعداد استان‌ها (31)"),
            check(fa_ratio(t) > 0.2, "پاسخ فارسی"),
        ],
    },
    {
        "id": "summarize", "title": "خلاصه‌سازی متن", "category": "درک مطلب",
        "prompt": "متن زیر را در حداکثر دو جمله خلاصه کن:\n\n«" + SUMMARY_TEXT + "»",
        "num_predict": 150,
        "checks": lambda t: [
            check(len(t) <= 600, "کوتاه بودن خلاصه (زیر ۶۰۰ نویسه)", f"{len(t)} نویسه"),
            check(fa_ratio(t) > 0.25, "خلاصه فارسی"),
            check(("مترو" in t) or ("پایتخت" in t) or ("تهران" in t) or ("آلودگی" in t),
                  "ارجاع به مفاهیم کلیدی متن"),
        ],
    },
    {
        "id": "fa2en", "title": "ترجمه فارسی به انگلیسی", "category": "ترجمه",
        "prompt": "این جمله را به انگلیسی ترجمه کن و فقط ترجمه را بنویس:\n"
                  "«هوای امروز بسیار زیباست و قصد داریم به پارک شهر برویم.»",
        "num_predict": 150,
        "checks": lambda t: [
            check(latin_ratio(t) > 0.5, "خروجی انگلیسی"),
            check("park" in t.lower(), "برگردان واژه پارک"),
            check(any(w in t.lower() for w in ("weather", "beautiful", "lovely", "nice")),
                  "برگردان توصیف هوا"),
        ],
    },
    {
        "id": "en2fa", "title": "ترجمه انگلیسی به فارسی", "category": "ترجمه",
        "prompt": "این جمله را به فارسی روان ترجمه کن و فقط ترجمه را بنویس:\n"
                  '"Life is a journey, not a destination."',
        "num_predict": 150,
        "checks": lambda t: [
            check(fa_ratio(t) > 0.3, "خروجی فارسی"),
            check("زندگی" in t, "برگردان واژه زندگی"),
            check(("سفر" in t) or ("مقصد" in t), "برگردان journey/destination"),
        ],
    },
    {
        "id": "math", "title": "حساب ذهنی ساده", "category": "استدلال",
        "prompt": "باغی ۱۲ درخت سیب دارد و هر درخت ۵ سیب می‌دهد. مجموع سیب‌ها چند عدد است؟ "
                  "فقط عدد نهایی را بنویس.",
        "num_predict": 100,
        "checks": lambda t: [
            check(re.search(r"\b60\b", norm_digits(t)) is not None, "پاسخ صحیح (60)"),
        ],
    },
    {
        "id": "json", "title": "خروجی ساختاریافته JSON", "category": "قابلیت برنامه‌نویسی",
        "prompt": "فقط و فقط یک شیء JSON معتبر برگردان (بدون هیچ متن اضافه) با کلیدهای "
                  "name، language و greeting که مقادیر آن‌ها به فارسی باشد.",
        "num_predict": 200,
        "checks": lambda t: [
            check(parse_json_block(t) is not None, "JSON معتبر و قابل پارس"),
            check((lambda j: bool(j) and "name" in j)(parse_json_block(t)), "وجود کلید name"),
        ],
    },
    {
        "id": "writing", "title": "نگارش ایمیل رسمی", "category": "تولید متن",
        "prompt": "یک ایمیل رسمی و کوتاه به مدیر شرکت بنویس و یک روز مرخصی درخواست کن.",
        "num_predict": 300,
        "checks": lambda t: [
            check(fa_ratio(t) > 0.2, "متن فارسی"),
            check("مرخصی" in t, "ذکر واژه مرخصی"),
            check(len(t) > 100, "کامل بودن ایمیل"),
        ],
    },
    {
        "id": "sentiment", "title": "تحلیل حس جمله", "category": "طبقه‌بندی",
        "prompt": "حس این جمله مثبت است یا منفی؟ فقط با یک کلمه جواب بده:\n"
                  "«امروز آزمونم را عالی دادم و خیلی خوشحالم.»",
        "num_predict": 60,
        "checks": lambda t: [
            check("مثبت" in t, "پاسخ صحیح (مثبت)"),
        ],
    },
    {
        "id": "instructions", "title": "پیروی دقیق از دستور", "category": "دستورپیروی",
        "prompt": "فقط نام ۳ شهر ایران را در قالب لیست شماره‌دار بنویس. هیچ توضیح اضافه‌ای ننویس.",
        "num_predict": 100,
        "checks": lambda t: [
            check(re.search(r"(?m)^\s*[1-3][.)\-]\s*\S+", norm_digits(t)) is not None,
                  "قالب لیست شماره‌دار"),
            check(len([l for l in t.splitlines() if l.strip()]) <= 6, "بدون توضیح اضافه"),
        ],
    },
    {
        "id": "memory", "title": "حافظه مکالمه (چند نوبته)", "category": "مکالمه",
        "special": "memory",
    },
]


def run_memory_case(client):
    """تست حافظه: ابتدا اطلاعات معرفی می‌شود، سپس در نوبت بعدی پرسیده می‌شود"""
    msgs = [{"role": "user",
             "content": "سلام! اسم من «علی» است و در تهران زندگی می‌کنم. فقط بگو یادداشت کردی."}]
    text1, _, st1 = client.chat(msgs, think=False, options={"num_predict": 60})
    msgs.append({"role": "assistant", "content": text1})
    msgs.append({"role": "user",
                 "content": "اسم من چه بود و کجا زندگی می‌کنم؟ در یک جمله کوتاه بگو."})
    text2, _, st2 = client.chat(msgs, think=False, options={"num_predict": 100})
    checks = [
        check("علی" in text2, "به یاد آوردن نام (علی)"),
        check("تهران" in text2, "به یاد آوردن شهر (تهران)"),
    ]
    return {"first": text1, "final": text2, "stats": st2, "checks": checks}


def run_quality(client):
    results = []
    for case in QUALITY_CASES:
        print(f"\n  تست {BOLD}{case['title']}{RESET} {DIM}({case['category']}){RESET} ...",
              flush=True)
        if case.get("special") == "memory":
            mem = run_memory_case(client)
            ts = tok_stats(mem["stats"])
            resp_text, checks = mem["final"], mem["checks"]
            raw = {"first_turn": mem["first"][:400]}
        else:
            resp_text, _, st = client.chat(
                [{"role": "user", "content": case["prompt"]}],
                think=False, options={"num_predict": case.get("num_predict", 300)},
            )
            ts = tok_stats(st)
            checks = case["checks"](resp_text)
            raw = {}
        results.append({
            "id": case["id"], "title": case["title"], "category": case["category"],
            "response": resp_text, "checks": checks,
            "tps": ts["tps"], "tokens": ts["eval_count"], "wall": ts["wall"], "raw": raw,
        })
        for c in checks:
            mark = f"{GREEN}PASS{RESET}" if c["passed"] else f"{RED}FAIL{RESET}"
            extra = f" {DIM}({c['detail']}){RESET}" if c.get("detail") else ""
            print(f"      [{mark}] {c['check']}{extra}")
        print(f"      {DIM}{ts['tps']:.1f} توکن/ثانیه | {ts['eval_count']} توکن{RESET}")
    return results


# =====================================================================
# چت تعاملی
# =====================================================================
def run_chat(client):
    print(f"{BOLD}چت تعاملی با {client.model}{RESET} — برای خروج: exit یا خروج\n")
    msgs = [{"role": "system",
             "content": "تو یک دستیار فارسی‌زبان، دقیق و مودب هستی. پاسخ‌ها کوتاه و مفید باشند."}]
    while True:
        try:
            q = input(f"{BOLD}شما:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            continue
        if q.lower() in ("exit", "quit", "خروج", "/bye"):
            break
        msgs.append({"role": "user", "content": q})
        print(f"{BOLD}دستیار:{RESET} ", end="", flush=True)
        text, _, st = client.chat(
            msgs, think=False,
            on_delta=lambda d: print(d, end="", flush=True),
            options={"num_predict": 800},
        )
        ts = tok_stats(st)
        print(f"\n{DIM}[{ts['tps']:.1f} توکن/ثانیه | TTFT {ts['ttft']:.2f}s | "
              f"{ts['eval_count']} توکن]{RESET}\n")
        msgs.append({"role": "assistant", "content": text})


# =====================================================================
# گزارش
# =====================================================================
def build_recommendations(avg_tps, q_passed, q_total, think_out, cold_load_s):
    recs = []
    if cold_load_s and cold_load_s > 20:
        recs.append("زمان لود مدل زیاد بود؛ OLLAMA_KEEP_ALIVE=-1 را تنظیم کنید تا مدل "
                    "همیشه در RAM بماند (اسکریپت setup-ollama.ps1 این کار را می‌کند).")
    if avg_tps >= 12:
        recs.append("سرعت عالی است؛ اگر کیفیت بالاتر می‌خواهید با بستن Docker/ClamAV "
                    "می‌توانید gemma3:12b یا qwen3:14b را هم آزمایش کنید.")
    elif avg_tps >= 7:
        recs.append("سرعت برای چت‌بات و ابزار داخلی مناسب است؛ think:false را نگه دارید.")
    else:
        recs.append("سرعت پایین است؛ مدل qwen3:4b را امتحان کنید، OLLAMA_CONTEXT_LENGTH "
                    "را به 4096 کاهش دهید و مطمئن شوید سرویس‌های دیگر بار CPU نمی‌گیرند.")
    ratio = (q_passed / q_total) if q_total else 0.0
    if ratio >= 0.9:
        recs.append("کیفیت فارسی در تست‌ها عالی بود و برای استفاده در برنامه‌ها آماده است.")
    elif ratio >= 0.7:
        recs.append("کیفیت فارسی خوب است؛ برای وظایف حساس (استدلال، ترجمه تخصصی) "
                    "حالت think:true پاسخ دقیق‌تری می‌دهد اما کندتر است.")
    elif q_total:
        recs.append("چند تست کیفیت پاس نشد؛ gemma3:12b یا مدل فارسی‌محور Dorna2 "
                    "(بخش ۲ و ۵ راهنما) را جایگزین کنید.")
    if think_out:
        a = think_out.get("بدون تفکر", {}).get("tps", 0)
        b = think_out.get("با تفکر", {}).get("tps", 0)
        if a > 0 and b > 0:
            drop = (1 - b / a) * 100
            recs.append(f"حالت تفکر سرعت تولید را حدود {drop:.0f} درصد کاهش داد "
                        f"({a:.1f} در برابر {b:.1f} توکن/ثانیه).")
    return recs


def write_report(server, model, info, speed_rows, think_out, quality_results,
                 avg_tps, q_passed, q_total, cold_load_s):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = REPORT_DIR / f"bench_report_{stamp}.md"
    raw_path = REPORT_DIR / f"bench_raw_{stamp}.json"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    L = []
    L.append(f"# گزارش تست مدل {model}")
    L.append("")
    L.append(f"- تاریخ: {now}")
    L.append(f"- سرور: {server}")
    L.append(f"- نسخه Ollama: {info.get('version', '?')} | پارامترها: "
             f"{info.get('params', '?')} | کوانتیزه: {info.get('quant', '?')}")
    if cold_load_s:
        L.append(f"- زمان لود سرد مدل: {cold_load_s:.1f} ثانیه")
    L.append("")
    if speed_rows:
        L.append("## نتایج سرعت")
        L.append("")
        L.append("| سناریو | توکن خروجی | توکن/ثانیه | TTFT (ثانیه) | زمان کل (ثانیه) |")
        L.append("|---|---|---|---|---|")
        for r in speed_rows:
            L.append(f"| {r['case']} | {r['tokens']} | {r['tps']:.1f} | "
                     f"{r['ttft']:.2f} | {r['wall']:.1f} |")
        L.append(f"\n**میانگین سرعت: {avg_tps:.1f} توکن/ثانیه — ارزیابی: {speed_verdict(avg_tps)}**")
        L.append("")
    if think_out:
        L.append("## مقایسه حالت تفکر")
        L.append("")
        L.append("| حالت | توکن | توکن/ثانیه | TTFT | زمان کل |")
        L.append("|---|---|---|---|---|")
        for label, v in think_out.items():
            L.append(f"| {label} | {v['tokens']} | {v['tps']:.1f} | "
                     f"{v['ttft']:.2f} | {v['wall']:.1f} |")
        L.append("")
    if quality_results:
        L.append("## نتایج کیفیت فارسی")
        L.append("")
        for r in quality_results:
            passed = sum(1 for c in r["checks"] if c["passed"])
            total = len(r["checks"])
            L.append(f"### {r['title']} ({r['category']})")
            L.append(f"- چک‌های موفق: {passed}/{total}")
            L.append(f"- سرعت: {r['tps']:.1f} توکن/ثانیه ({r['tokens']} توکن)")
            for c in r["checks"]:
                mark = "PASS" if c["passed"] else "FAIL"
                det = f" — {c['detail']}" if c.get("detail") else ""
                L.append(f"- [{mark}] {c['check']}{det}")
            L.append("- پاسخ مدل:")
            short = (r["response"] or "").strip()[:500]
            for line in short.splitlines():
                L.append(f"  > {line}")
            L.append("")
    recs = build_recommendations(avg_tps, q_passed, q_total, think_out, cold_load_s)
    L.append("## جمع‌بندی و توصیه‌ها")
    L.append("")
    if speed_rows:
        L.append(f"- میانگین سرعت: **{avg_tps:.1f} توکن/ثانیه** ({speed_verdict(avg_tps)})")
    if quality_results:
        L.append(f"- امتیاز کیفیت: **{q_passed}/{q_total} چک موفق**")
    for rec in recs:
        L.append(f"- {rec}")
    L.append("")

    md_path.write_text("\n".join(L), encoding="utf-8")

    raw = {
        "timestamp": now, "server": server, "model": model, "info": info,
        "speed": speed_rows, "think_compare": think_out,
        "quality": quality_results,
        "summary": {"avg_tps": avg_tps, "checks_passed": q_passed, "checks_total": q_total},
    }
    raw_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, raw_path


# =====================================================================
# اجرای اصلی
# =====================================================================
def main():
    ap = argparse.ArgumentParser(
        description="برنامه تست سرعت و کیفیت مدل فارسی روی Ollama (LLM Rose)")
    ap.add_argument("--server", default="http://localhost:11434",
                    help="آدرس سرور Ollama (پیش‌فرض: http://localhost:11434)")
    ap.add_argument("--model", default="qwen3:8b", help="نام مدل (پیش‌فرض: qwen3:8b)")
    ap.add_argument("--speed", action="store_true", help="فقط تست سرعت")
    ap.add_argument("--quality", action="store_true", help="فقط تست کیفیت فارسی")
    ap.add_argument("--chat", action="store_true", help="چت تعاملی با نمایش سرعت")
    ap.add_argument("--think", action="store_true",
                    help="مقایسه سرعت با/بدون حالت تفکر Qwen3")
    ap.add_argument("--no-report", action="store_true", help="ذخیره نکردن فایل گزارش")
    args = ap.parse_args()

    if not (args.speed or args.quality or args.chat):
        args.speed = args.quality = True

    server = args.server if args.server.startswith("http") else f"http://{args.server}"
    client = OllamaClient(server, args.model)

    print(f"{BOLD}{'=' * 62}")
    print("  LLM Rose — برنامه تست سرعت و کیفیت مدل فارسی")
    print(f"{'=' * 62}{RESET}")

    # بررسی اتصال
    try:
        urlreq.urlopen(f"{client.server}/api/version", timeout=5)
    except Exception:
        print(f"{RED}اتصال به Ollama برقرار نشد ({server}).")
        print(f"بررسی کنید: برنامه Ollama در حال اجراست؟ پورت 11434 باز است؟{RESET}")
        sys.exit(2)

    info = client.info()
    print(f"  سرور  : {server}  (Ollama {info['version']})")
    print(f"  مدل   : {client.model}  ({info['params']}، کوانتیزه {info['quant']})")

    try:
        # ---------- حالت چت ----------
        if args.chat:
            run_chat(client)
            return

        speed_rows, think_out, quality_results = [], None, []
        if args.speed:
            speed_rows = run_speed(client)
        if args.think:
            think_out = run_think_compare(client)
        if args.quality:
            quality_results = run_quality(client)

        # ---------- جمع‌بندی ----------
        print(f"\n{BOLD}{'=' * 62}")
        print("  جمع‌بندی")
        print(f"{'=' * 62}{RESET}")

        q_passed = sum(1 for r in quality_results for c in r["checks"] if c["passed"])
        q_total = sum(len(r["checks"]) for r in quality_results)
        if speed_rows:
            avg_tps = sum(r["tps"] for r in speed_rows) / len(speed_rows)
        elif quality_results:
            avg_tps = sum(r["tps"] for r in quality_results) / len(quality_results)
        else:
            avg_tps = 0.0

        if speed_rows or think_out:
            print(f"  میانگین سرعت : {GREEN}{avg_tps:.1f}{RESET} توکن/ثانیه "
                  f"— ارزیابی: {BOLD}{speed_verdict(avg_tps)}{RESET}")
        if quality_results:
            ratio = q_passed / max(q_total, 1)
            color = GREEN if ratio >= 0.99 else (YELLOW if ratio >= 0.7 else RED)
            print(f"  کیفیت فارسی  : {color}{q_passed}/{q_total}{RESET} چک موفق")

        recs = build_recommendations(avg_tps, q_passed, q_total, think_out, 0.0)
        print(f"\n{BOLD}توصیه‌ها:{RESET}")
        for rec in recs:
            print(f"  - {rec}")

        # ---------- ذخیره گزارش ----------
        if not args.no_report:
            cold_load = warm.get("load_s", 0.0) if False else 0.0
            md_path, raw_path = write_report(
                server, args.model, info, speed_rows, think_out,
                quality_results, avg_tps, q_passed, q_total, cold_load)
            print(f"\n{CYAN}گزارش ذخیره شد:{RESET}")
            print(f"  {md_path}")
            print(f"  {raw_path}")
    except HTTPError as e:
        body = ""
        try:
            body = e.read().decode(errors="replace")[:300]
        except Exception:
            pass
        print(f"{RED}خطای سرور {e.code}: {body}{RESET}")
        print(f"{YELLOW}آیا مدل با نام درست دانلود شده؟ (ollama list){RESET}")
        sys.exit(2)
    except URLError:
        print(f"{RED}ارتباط با Ollama قطع شد.{RESET}")
        sys.exit(2)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}تست توسط کاربر متوقف شد.{RESET}")


if __name__ == "__main__":
    main()

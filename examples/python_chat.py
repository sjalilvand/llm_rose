# -*- coding: utf-8 -*-
"""
چت تعاملی فارسی با مدل محلی Qwen3-8B از طریق Ollama (سازگار با OpenAI API)

پیش‌نیاز:
    pip install openai
    (مدل باید با ollama run qwen3:8b اجرا شده باشد)

اجرا:
    python python_chat.py
"""

from openai import OpenAI

# Ollama یک نقطه پایانی سازگار با OpenAI روی پورت 11434 ارائه می‌دهد
# مقدار api_key اهمیتی ندارد، فقط باید غیرخالی باشد
client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)

# اگر سرور مدل روی ماشین دیگری است، به‌جای localhost آدرس سرور را بگذارید
# base_url="http://192.168.1.10:11434/v1"

SYSTEM_PROMPT = "تو یک دستیار فارسی‌زبان، دقیق و مودب هستی. پاسخ‌ها را کوتاه و مفید بده."

messages = [{"role": "system", "content": SYSTEM_PROMPT}]

print("چت با مدل محلی (برای خروج: exit یا خروج)\n")

while True:
    user_input = input("شما: ").strip()
    if not user_input:
        continue
    if user_input.lower() in ("exit", "quit", "خروج"):
        print("پایان چت.")
        break

    messages.append({"role": "user", "content": user_input})

    # پاسخ جریانی (streaming) برای دیدن کلمه‌به‌کلمه پاسخ
    stream = client.chat.completions.create(
        model="qwen3:8b",
        messages=messages,
        stream=True,
        extra_body={"think": False},  # غیرفعال کردن مرحله تفکر Qwen3 برای پاسخ سریع‌تر
    )

    print("دستیار: ", end="", flush=True)
    reply = ""
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        print(delta, end="", flush=True)
        reply += delta
    print("\n")

    messages.append({"role": "assistant", "content": reply})

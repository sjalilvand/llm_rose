# -*- coding: utf-8 -*-
"""
سرویس وب فارسی روی مدل محلی — برای اتصال اپلیکیشن‌های خودتان به LLM

پیش‌نیاز:
    pip install fastapi uvicorn openai

اجرا:
    uvicorn fastapi_app:app --host 0.0.0.0 --port 8000

تست:
    curl -X POST http://SERVER_IP:8000/chat -H "Content-Type: application/json" -d '{"text": "سلام"}'
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI

app = FastAPI(title="LLM Rose — Persian Chat API", version="1.0")

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)

MODEL = "qwen3:8b"
SYSTEM_PROMPT = "تو یک دستیار فارسی‌زبان هستی. پاسخ‌ها کوتاه، دقیق و مفید باشند."


class ChatRequest(BaseModel):
    text: str


@app.get("/health")
def health():
    """بررسی سلامت سرویس"""
    return {"status": "ok", "model": MODEL}


@app.post("/chat")
def chat(req: ChatRequest):
    """دریافت متن فارسی و برگرداندن پاسخ مدل"""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="متن خالی است.")

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": req.text},
            ],
            extra_body={"think": False},  # پاسخ سریع بدون مرحله تفکر
        )
        return {"reply": response.choices[0].message.content}
    except Exception as exc:  # اتصال به Ollama برقرار نیست
        raise HTTPException(
            status_code=502,
            detail=f"خطا در ارتباط با مدل محلی: {exc}",
        ) from exc

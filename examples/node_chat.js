// مثال Node.js برای استفاده از مدل فارسی‌زبان محلی Qwen3-8B از طریق Ollama
// پیش‌نیاز: Node.js 18+ (داشتن fetch داخلی)
// اجرا:  node node_chat.js

const MODEL = "qwen3:8b";
const OLLAMA_BASE = process.env.OLLAMA_BASE || "http://localhost:11434";

async function ask(question) {
  const res = await fetch(`${OLLAMA_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: MODEL,
      think: false, // غیرفعال کردن مرحله تفکر Qwen3 برای پاسخ سریع‌تر
      messages: [
        { role: "system", content: "تو یک دستیار فارسی‌زبان هستی." },
        { role: "user", content: question },
      ],
      stream: false,
    }),
  });

  if (!res.ok) {
    throw new Error(`خطای HTTP ${res.status}: ${await res.text()}`);
  }
  const data = await res.json();
  return data.message.content;
}

// نمونه استفاده: درخواست ساده
const answer = await ask("سلام! در دو جمله خودت را به فارسی معرفی کن.");
console.log("پاسخ مدل:", answer);

// نمونه استفاده: پاسخ جریانی (streaming) — برای نمایش زنده در وب
async function askStreaming(question, onToken) {
  const res = await fetch(`${OLLAMA_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: MODEL,
      think: false,
      messages: [{ role: "user", content: question }],
      stream: true,
    }),
  });

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let full = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop(); // خط ناقص آخر را نگه دار

    for (const line of lines) {
      if (!line.trim()) continue;
      const chunk = JSON.parse(line);
      if (chunk.message?.content) {
        full += chunk.message.content;
        onToken?.(chunk.message.content);
      }
    }
  }
  return full;
}

console.log("\nپاسخ جریانی:");
await askStreaming("یک جمله انگیزشی کوتاه به فارسی بگو.", (t) => process.stdout.write(t));
console.log();

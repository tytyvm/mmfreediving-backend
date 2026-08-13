"""
MM Freediving — website chat backend.

A tiny FastAPI service that powers the chat bubble on mmfreediving.com.

Endpoints:
  GET  /        -> health check (open this URL in a browser to confirm it's running)
  POST /chat    -> { "session_id": "...", "message": "..." }  ->  { "reply": "..." }

Conversation history is kept in memory per session (it resets if the server
restarts — totally fine for a website chat bubble).

Environment variables (set these in Render):
  ANTHROPIC_API_KEY   (required)  your Anthropic API key
  CLAUDE_MODEL        (optional)  defaults to claude-haiku-4-5-20251001
  ALLOWED_ORIGIN      (optional)  defaults to https://mmfreediving.com
"""

import os
from collections import defaultdict, deque

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic

MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://mmfreediving.com")

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

SYSTEM_PROMPT = """You are the friendly assistant for MM Freediving, a freediving \
instruction business in South Florida. You answer questions from website visitors about \
courses, pricing, scheduling, and booking. Keep replies short, warm, and conversational \
— usually 1-3 sentences. Never invent prices, dates, or policies beyond the facts below. \
For anything you're unsure about, point them to email mmfreediving@gmail.com or the \
contact form on the site.

ABOUT:
- MM Freediving is based in South Florida, led by a certified freediving instructor with \
5+ years of experience teaching complete beginners through experienced spearfishermen.
- Approach: calm, patient, safety-first. Warm water and great visibility year-round.
- Instagram: @mattmfreediving. Email: mmfreediving@gmail.com.

COURSES:
1) Level 1 Freediving — $500 per person. 2 days (Day 1: theory + pool covering dive \
physiology, the mammalian dive reflex, equalization, hypoxia / shallow water blackout, \
and the buddy system; Day 2: open water dives). Max 6 students. All levels welcome — no \
experience required, just be a comfortable swimmer. Equipment provided. Ends with a \
Level 1 certification. Next available date: August 1-2 (Saturday & Sunday).
2) Private Sessions — one-on-one instruction, any level. Half day or full day, at a \
location and schedule that work for the student. Equipment provided. Certification \
available on request. Pricing is not fixed — it is discussed directly, so tell them to \
reach out via the contact form or email.

GEAR & EQUIPMENT 
-Required gear is a mask, snorkel, fins (preferably freediving long fins), exposure protection (either rash guard or wetsuit), weight belt 
-Rash guards are typically fine for warm summer months a 1.5-3mm open cell freediving wetsuit is recommended for colder months. Each individual is different so go based on your needs.
-Reccomended gear is a freediving watch or waterproof watch 
-Some gear is available for rent at an extra cost, reach out for availability. 

BOOKING & PAYMENT:
- Book online on the Book page. Payment is handled securely through Square.
- For Level 1, two options: pay in full ($500 per person), OR reserve with a $200 deposit \
per person. With the deposit, the remaining $300 per person is sent as a Square invoice, \
due on the first day of class.
- Private session pricing is arranged directly — direct them to contact."""

app = FastAPI(title="MM Freediving Chat")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN, "https://www.mmfreediving.com"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# In-memory conversation history: session_id -> recent messages (auto-trims to last 12)
HISTORY = defaultdict(lambda: deque(maxlen=12))


class ChatIn(BaseModel):
    session_id: str
    message: str


@app.get("/")
def health():
    return {"status": "ok", "service": "mmfreediving-chat", "model": MODEL}


@app.post("/chat")
def chat(body: ChatIn):
    msg = (body.message or "").strip()
    if not msg:
        return {"reply": "Ask me anything about our freediving courses, dates, or booking! \U0001F93F"}

    history = HISTORY[body.session_id]
    history.append({"role": "user", "content": msg})

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=list(history),
        )
        reply = "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception as e:
        print("Anthropic error:", repr(e))
        return {"reply": "Sorry, I'm having a hiccup right now. Please email "
                         "mmfreediving@gmail.com and we'll get right back to you."}

    history.append({"role": "assistant", "content": reply})
    return {"reply": reply}

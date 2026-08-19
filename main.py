"""
MM Freediving — website chat + contact-email backend.

Endpoints:
  GET  /          -> health check
  POST /chat      -> { session_id, message } -> { reply }        (chat widget)
  POST /contact   -> { firstName, lastName, email, interest,     (contact form)
                       experience, message, honey } -> { ok }

Contact form behavior is controlled by the AUTO_SEND env var:
  AUTO_SEND=false (default)  -> AI drafts a reply; it's emailed to the OWNER to
                                review and send.  The visitor gets no email yet.
  AUTO_SEND=true             -> the AI reply is emailed straight to the visitor,
                                and the owner gets a copy.
Flip it anytime in the Render dashboard — no code change.

Environment variables (set in Render):
  ANTHROPIC_API_KEY  (required)  your Anthropic API key
  CLAUDE_MODEL       (optional)  default claude-haiku-4-5-20251001
  ALLOWED_ORIGIN     (optional)  default https://mmfreediving.com
  SMTP_USER          (for email) your Gmail address (mmfreediving@gmail.com)
  SMTP_PASS          (for email) a Gmail *App Password* (not your login password)
  OWNER_EMAIL        (optional)  where lead notifications go (default = SMTP_USER)
  AUTO_SEND          (optional)  "true" to auto-send AI replies (default "false")
"""

import os
import ssl
import smtplib
from email.message import EmailMessage
from collections import defaultdict, deque

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic

MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://mmfreediving.com")
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "") or SMTP_USER

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment


def auto_send_enabled():
    return os.environ.get("AUTO_SEND", "false").strip().lower() in ("1", "true", "yes", "on")


# ── Shared business knowledge (used by BOTH chat and email) ──
KNOWLEDGE = """ABOUT:
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
available on request. Pricing is not fixed — it is discussed directly.

BOOKING & PAYMENT:
- Book online on the Book page. Payment is handled securely through Square.
- For Level 1, two options: pay in full ($500 per person), OR reserve with a $200 deposit \
per person. With the deposit, the remaining $300 per person is sent as a Square invoice, \
due on the first day of class.
- Private session pricing is arranged directly."""

SYSTEM_PROMPT = """You are the friendly assistant for MM Freediving, a freediving \
instruction business in South Florida. You answer questions from website visitors about \
courses, pricing, scheduling, and booking. Keep replies short, warm, and conversational \
— usually 1-3 sentences. Never invent prices, dates, or policies beyond the facts below. \
For anything you're unsure about, point them to email mmfreediving@gmail.com or the \
contact form on the site.

""" + KNOWLEDGE

EMAIL_SYSTEM = """You are writing a warm, professional email reply on behalf of MM \
Freediving to someone who just submitted the website contact form. Use ONLY the business \
facts below — never invent prices, dates, or policies. Address their specific interest or \
question. Keep it friendly and concise: a greeting using their first name if given, one or \
two helpful paragraphs, and a warm sign-off as "MM Freediving". If their question needs \
details you don't have (custom scheduling, private pricing specifics, etc.), warmly tell \
them an instructor will follow up personally. Write ONLY the email body — no subject line, \
and no bracketed placeholders like [Name].

""" + KNOWLEDGE

app = FastAPI(title="MM Freediving Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN, "https://www.mmfreediving.com"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

HISTORY = defaultdict(lambda: deque(maxlen=12))


# ── Email helper ──
def send_email(to, subject, body, reply_to=None):
    if not (SMTP_USER and SMTP_PASS):
        raise RuntimeError("SMTP not configured (SMTP_USER / SMTP_PASS missing)")
    msg = EmailMessage()
    msg["From"] = f"MM Freediving <{SMTP_USER}>"
    msg["To"] = to
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    ctx = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.starttls(context=ctx)
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)


# ── Models ──
class ChatIn(BaseModel):
    session_id: str
    message: str


class ContactIn(BaseModel):
    firstName: str = ""
    lastName: str = ""
    email: str = ""
    interest: str = ""
    experience: str = ""
    message: str = ""
    honey: str = ""  # honeypot — real users leave this empty


# ── Routes ──
@app.get("/")
def health():
    return {
        "status": "ok",
        "service": "mmfreediving-backend",
        "model": MODEL,
        "email_configured": bool(SMTP_USER and SMTP_PASS),
        "auto_send": auto_send_enabled(),
    }


@app.post("/chat")
def chat(body: ChatIn):
    msg = (body.message or "").strip()
    if not msg:
        return {"reply": "Ask me anything about our freediving courses, dates, or booking! \U0001F93F"}
    history = HISTORY[body.session_id]
    history.append({"role": "user", "content": msg})
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=400, system=SYSTEM_PROMPT, messages=list(history)
        )
        reply = "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception as e:
        print("Anthropic error:", repr(e))
        return {"reply": "Sorry, I'm having a hiccup right now. Please email "
                         "mmfreediving@gmail.com and we'll get right back to you."}
    history.append({"role": "assistant", "content": reply})
    return {"reply": reply}


def generate_email_reply(body: ContactIn):
    lead = (
        "A website visitor submitted the contact form.\n"
        f"First name: {body.firstName or '(not given)'}\n"
        f"Interested in: {body.interest or '(not specified)'}\n"
        f"Experience level: {body.experience or '(not specified)'}\n"
        f"Their message: {body.message or '(they left the message blank)'}\n\n"
        "Write the email reply now."
    )
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=500, system=EMAIL_SYSTEM,
            messages=[{"role": "user", "content": lead}],
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception as e:
        print("email draft generation failed:", repr(e))
        return (f"Hi {body.firstName or 'there'},\n\nThanks so much for reaching out to MM "
                "Freediving! We got your message and will get back to you within 24 hours "
                "with everything you need.\n\nIn the meantime you can see courses and book at "
                "https://mmfreediving.com.\n\nTalk soon,\nMM Freediving")


@app.post("/contact")
def contact(body: ContactIn):
    # Honeypot: bots fill hidden fields. Silently accept and drop.
    if body.honey.strip():
        return {"ok": True}

    draft = generate_email_reply(body)
    auto = auto_send_enabled()

    lead = (
        f"Name: {body.firstName} {body.lastName}".rstrip() + "\n"
        f"Email: {body.email or '(none)'}\n"
        f"Interested in: {body.interest or '—'}\n"
        f"Experience: {body.experience or '—'}\n\n"
        f"Message:\n{body.message or '(no message)'}"
    )

    if auto:
        owner_subject = f"[Lead — auto-replied] {body.firstName} {body.lastName}".rstrip()
        owner_note = "An AI reply was AUTO-SENT to this person (copy below). Follow up if needed."
    else:
        owner_subject = f"[Lead — needs reply] {body.firstName} {body.lastName}".rstrip()
        owner_note = (f"Review the suggested reply below, then send it to {body.email} "
                      "(just hit Reply — this email's reply-to is set to them).")

    owner_body = f"{owner_note}\n\n{lead}\n\n" + "-" * 40 + f"\nSUGGESTED REPLY:\n" + "-" * 40 + f"\n{draft}"

    # 1) Always notify the owner. This is the critical path — if it fails, tell the site.
    try:
        send_email(OWNER_EMAIL, owner_subject, owner_body, reply_to=(body.email or None))
    except Exception as e:
        print("owner notification failed:", repr(e))
        return {"ok": False, "error": "notify_failed"}

    # 2) In auto mode, also send the reply to the visitor.
    if auto and body.email:
        try:
            send_email(body.email, "Re: your message to MM Freediving", draft, reply_to=OWNER_EMAIL)
        except Exception as e:
            print("customer email failed:", repr(e))  # owner already has it; not fatal

    return {"ok": True}

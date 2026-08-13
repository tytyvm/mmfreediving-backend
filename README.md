# MM Freediving — Website Chat Backend

Tiny FastAPI service that powers the chat bubble on mmfreediving.com. It answers
visitor questions about courses, pricing, dates, and booking using Claude.

## Endpoints
- `GET /` — health check (open in a browser to confirm it's running)
- `POST /chat` — body `{ "session_id": "...", "message": "..." }` → `{ "reply": "..." }`

## Deploy on Render (free)
1. Put these files in a new **public** GitHub repo (e.g. `mmfreediving-backend`).
2. On https://render.com → **New → Web Service** → connect that repo.
3. Render auto-detects Python. Confirm:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Instance type: **Free**
4. Add environment variables:
   - `ANTHROPIC_API_KEY` = your key from console.anthropic.com
   - `CLAUDE_MODEL` = `claude-haiku-4-5-20251001` (optional, this is the default)
   - `ALLOWED_ORIGIN` = `https://mmfreediving.com`
5. **Create Web Service.** After it builds, visit the URL — you should see the
   health JSON. Your chat endpoint is then `https://<your-app>.onrender.com/chat`.

## Test it
```bash
curl -X POST https://<your-app>.onrender.com/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test1","message":"how much is the level 1 course?"}'
```
You should get back `{"reply":"..."}` with a real answer.

## Notes
- Free tier sleeps after ~15 min idle; the first request after that takes
  30-60s to wake, then it's fast.
- Conversation history is in-memory and resets on restart (fine for a chat bubble).
- Edit the course facts in `SYSTEM_PROMPT` inside `main.py` whenever prices or
  dates change, then redeploy (push to GitHub → Render auto-deploys).

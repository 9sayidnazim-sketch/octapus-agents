from __future__ import annotations

import os
import uuid
from pathlib import Path

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).parent
MODEL = "claude-sonnet-5-5"
MAX_TURNS = 20

# Load .env if present
for env_path in (BASE_DIR / ".env", BASE_DIR.parent / ".env"):
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip("'\"")

def get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    if not api_key:
        raise HTTPException(status_code=500, detail="Set ANTHROPIC_API_KEY in environment variables.")
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    if base_url:
        return anthropic.Anthropic(api_key=api_key, base_url=base_url)
    return anthropic.Anthropic(api_key=api_key)

COMPANY_INFO_PATH = BASE_DIR / "company_info.md"
COMPANY_INFO = COMPANY_INFO_PATH.read_text(encoding="utf-8") if COMPANY_INFO_PATH.exists() else ""

SYSTEM_PROMPT = f"""You are the customer assistant for Octapus LLC.
Answer using only the company information below. If the answer is not there,
say you don't know and direct the customer to info@octapus.ae.
Never invent prices, policies, or promises. Keep answers short and friendly.

<company_information>
{COMPANY_INFO}
</company_information>"""

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Octapus Customer Assistant", description="AI Customer Service Agent for Octapus LLC")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

if (BASE_DIR / "static" / "assets").exists():
    app.mount("/assets", StaticFiles(directory=BASE_DIR / "static" / "assets"), name="assets")


@app.get("/octapus-logo.jpg")
def octapus_logo():
    logo_path = BASE_DIR / "static" / "octapus-logo.jpg"
    if logo_path.exists():
        return FileResponse(logo_path, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Logo not found")

from typing import Optional

# In-memory store. Replace with a database (Redis, Postgres) in production.
sessions: dict[str, list[dict]] = {}


class ChatIn(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatOut(BaseModel):
    reply: str
    session_id: str


@app.get("/health")
def health():
    return {"status": "ok", "app": "octapus-customer-agent", "model": MODEL}


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.post("/chat/reset")
def reset_chat(body: dict):
    s_id = body.get("session_id")
    if s_id and s_id in sessions:
        sessions.pop(s_id, None)
    return {"status": "cleared"}


@app.post("/chat", response_model=ChatOut)
def chat(body: ChatIn):
    message = body.message.strip()
    if not message or len(message) > 2000:
        raise HTTPException(status_code=400, detail="Message must be 1-2000 characters.")

    session_id = body.session_id or str(uuid.uuid4())
    history = sessions.setdefault(session_id, [])
    history.append({"role": "user", "content": message})

    try:
        client = get_client()
        response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=history[-MAX_TURNS:],
        )
    except anthropic.APIError:
        history.pop()  # keep history consistent after a failed call
        raise HTTPException(status_code=502, detail="The assistant is unavailable right now.")

    reply = "".join(b.text for b in response.content if b.type == "text")
    history.append({"role": "assistant", "content": reply})
    return ChatOut(reply=reply, session_id=session_id)

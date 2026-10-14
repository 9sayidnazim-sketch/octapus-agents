#!/usr/bin/env python3
"""Autonomous Meeting Agent Loop for Horus AI with Resilient Multilingual Engine.

Connects AgentCall meeting bridge (Google Meet) with Horus AI.
Features:
1. Auto-greeting in original Malayalam/Manglish slang upon joining
2. Watches meeting speech & chat in real time
3. Resilient conversational intelligence:
   - Responds fluently in English when requested or when addressed in English
   - Responds in original, authentic Malayalam/Manglish slang when addressed in Malayalam/Manglish
   - Answers questions about Octapus LLC (websites, ERP, WhatsApp automation, payments)
4. Monitored commands from meeting-commands.jsonl
"""
import os
import sys
import json
import time
import re
import subprocess
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR / "customer-agent"))

# Load environment
for env_path in (BASE_DIR / ".env", BASE_DIR / "customer-agent" / ".env"):
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k.strip(), v.strip("\"'"))

meeting_url = sys.argv[1] if len(sys.argv) > 1 else "https://meet.google.com/tre-wwzn-zva"
bot_name = sys.argv[2] if len(sys.argv) > 2 else "Horus AI"

events_file = BASE_DIR / "meeting-events.jsonl"
commands_file = BASE_DIR / "meeting-commands.jsonl"

events_file.touch()
commands_file.touch()

from media.tts_handler import clean_for_speech, is_malayalam_or_manglish

bridge_script = BASE_DIR / ".agents" / "skills" / "join-meeting" / "scripts" / "python" / "bridge.py"
python_bin = BASE_DIR / ".venv" / "bin" / "python"

print(f"=== Horus AI Meeting Assistant (Resilient Multilingual Engine) ===")
print(f"Target URL: {meeting_url}")
print(f"Bot Name: {bot_name}")

cmd = [
    str(python_bin),
    str(bridge_script),
    meeting_url,
    "--name", bot_name,
    "--voice", "af_heart",
    "--output", str(events_file)
]

bridge_proc = subprocess.Popen(
    cmd,
    stdin=subprocess.PIPE,
    text=True,
    bufsize=1,
    env=os.environ
)

lock = threading.Lock()

def send_command(payload: dict):
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    print(f"[Meeting Command -> Bot]: {line.strip()}", flush=True)
    with lock:
        try:
            bridge_proc.stdin.write(line)
            bridge_proc.stdin.flush()
        except Exception as e:
            print(f"[Error writing to bridge stdin]: {e}", flush=True)

# Background file monitor for meeting-commands.jsonl
def watch_commands_file():
    with open(commands_file, "r", encoding="utf-8") as cf:
        cf.seek(0, os.SEEK_END)
        while bridge_proc.poll() is None:
            cmd_line = cf.readline()
            if not cmd_line:
                time.sleep(0.2)
                continue
            cmd_line = cmd_line.strip()
            if not cmd_line:
                continue
            try:
                data = json.loads(cmd_line)
                send_command(data)
            except Exception:
                pass

cmd_thread = threading.Thread(target=watch_commands_file, daemon=True)
cmd_thread.start()

def generate_intelligent_reply(text: str) -> str:
    """Generate intelligent English-only response with comprehensive doubt clearance."""
    norm = text.lower().strip()
    # Normalize punctuation and common STT transcription quirks
    norm_clean = re.sub(r"[^\w\s]", " ", norm)
    words = set(norm_clean.split())

    # 0. Closing Clients & Deal Conversion
    if any(k in words for k in ["closing", "close", "deals", "deal", "conversion", "converting"]) or \
       any(k in norm for k in ["closing client", "closing clients", "close client", "close clients", "close deal", "close deals", "sales feature", "need that feature", "closing feature"]):
        return (
            "For closing clients, our CRM provides a high-converting deal pipeline. "
            "It includes one-click proposal generation, automated WhatsApp follow-up reminders so prospective deals never slip away, and direct payment links for instant deposit payments. "
            "You even receive instant alerts the moment a client opens your quotation so your sales rep can follow up immediately. "
            "Does your sales team close clients primarily over phone calls, meetings, or WhatsApp?"
        )

    # 1. CRM / ERP / Business Management Systems
    if any(k in words for k in ["crm", "crn", "erp", "crms", "erps"]) or \
       any(k in norm for k in ["need crm", "need crn", "business system", "customer relationship", "lead management", "tailoring", "inventory"]):
        return (
            "We build custom CRM and ERP software tailored to your specific business operations. "
            "Our systems feature custom lead tracking, sales pipelines, inventory management, automated invoicing, role-based staff access, and WhatsApp integrations. "
            "We have also built specialized systems for retail and tailoring workshops. "
            "What specific workflow or features are you looking to manage in your CRM?"
        )

    # 2. Dubai / UAE Business Context
    if any(k in words for k in ["dubai", "uae", "emirates"]) or "business in dubai" in norm:
        return (
            "Octapus LLC is based right here in Dubai, UAE! "
            "We help businesses across Dubai digitize their operations through custom web applications, ERP software, automated WhatsApp customer support, and local payment integrations. "
            "What specific business challenges or systems are you looking to solve in Dubai?"
        )

    # 3. Language & English Confirmation
    if any(k in norm for k in ["english", "speak in english", "talk in english", "only in english", "can you speak english", "in english"]):
        return (
            "Understood! I will speak strictly in English. "
            "I am ready to clear any doubts you have about our technology, CRM, websites, and software services. "
            "What would you like to discuss first?"
        )

    # 4. Website Design & Web Development
    if any(k in words for k in ["website", "web", "portal", "ecommerce", "store"]) or \
       any(k in norm for k in ["web design", "web development", "landing page", "online store", "web app"]):
        return (
            "We design and build bespoke, high-performance corporate websites, client portals, and e-commerce platforms. "
            "All our websites are built with modern frameworks, mobile responsiveness, fast loading speeds, and built-in SEO. "
            "Are you looking to launch a brand new website or revamp an existing one?"
        )

    # 5. Payment Gateway & POS Integration
    if any(k in words for k in ["payment", "payments", "pos", "stripe", "checkout", "telr"]) or "payment gateway" in norm:
        return (
            "To clarify how our payment integration works: Octapus connects your chosen licensed payment gateway—like Stripe, Telr, or Network International—directly into your website, ERP, or invoice system. "
            "This ensures customer payments settle directly into your own bank account with complete security. Which payment provider are you planning to use?"
        )

    # 6. WhatsApp Business Automation
    if any(k in words for k in ["whatsapp", "automation", "chatbot", "bot", "broadcast"]) or "whatsapp business" in norm:
        return (
            "Our WhatsApp Business integration automates your customer communication 24/7. "
            "We build intelligent AI support bots, automated lead qualification, instant inquiry routing, and notification broadcasts through the official WhatsApp Business API. "
            "It connects directly to your CRM so your sales team never loses a customer lead."
        )

    # 7. Pricing & Quotes
    if any(k in words for k in ["price", "pricing", "cost", "quote", "proposal", "rates", "package"]) or \
       any(k in norm for k in ["how much", "what is the price", "cost of"]):
        return (
            "At Octapus, our pricing is transparent and scoped specifically to the features and modules your project requires, rather than rigid packages. "
            "Once we outline your requirements, our technical team provides a clear proposal with milestone deliverables. "
            "What kind of software or website project would you like an estimate for?"
        )

    # 8. Timeline & Delivery
    if any(k in words for k in ["timeline", "duration", "time", "weeks", "days", "long"]) or \
       any(k in norm for k in ["how long", "when can you deliver", "delivery time"]):
        return (
            "Typically, custom corporate websites take 2 to 4 weeks, while comprehensive CRM and ERP solutions take 4 to 8 weeks depending on the number of modules and integrations. "
            "We work in iterative milestone sprints so you can test features as they are built. What timeline do you have in mind?"
        )

    # 9. All Services Overview
    if any(k in words for k in ["service", "services", "offer", "products", "work"]) or \
       any(k in norm for k in ["what do you do", "what does octapus do", "tell me about octapus", "services you have"]):
        return (
            "Octapus LLC specializes in five core digital services: "
            "First, custom website development and web applications. "
            "Second, business ERP and CRM software. "
            "Third, automated WhatsApp Business bots. "
            "Fourth, secure payment gateway integrations. "
            "And fifth, autonomous AI assistants. Which of these areas would you like to explore?"
        )

    # 10. Who are you / Identity
    if any(phrase in norm for phrase in ["who are you", "who are u", "what is your name", "what's your name", "introduce yourself", "who is this", "who am i speaking to"]):
        return "I am Horus AI, a voice assistant for Octapus LLC. We build custom websites, business ERP and CRM software, and WhatsApp automations. How can I help you today?"

    # 11. Working Hours
    if any(k in words for k in ["hours", "timings", "timing", "open", "schedule"]) or \
       any(k in norm for k in ["working hours", "office hours", "business hours", "what time", "when are you open", "working time"]):
        return "Our working hours are Monday to Friday, 9:00 AM to 6:00 PM Gulf Standard Time. Our team is also reachable anytime at info at octapus dot a e."

    # 12. Getting Started & Contact
    if any(k in words for k in ["contact", "email", "office", "start", "hire"]) or \
       any(k in norm for k in ["get started", "how to start", "where are you located"]):
        return (
            "Getting started is straightforward! You can share your project requirements on our website at octapus.ae or email us at info at octapus dot a e. "
            "Our team will arrange a technical discovery session and send a detailed project roadmap."
        )

    # 13. Greetings & Hearing Checks (Answer directly without re-introducing)
    if any(k in words for k in ["hello", "hi", "hey", "morning", "afternoon", "evening", "namaskaram"]):
        return "Hello! How can I help you with your project today?"

    if any(k in words for k in ["test", "testing"]) or any(k in norm for k in ["can you hear me", "are you there", "listen"]):
        return "Yes, I can hear you loud and clear! Please go right ahead with your question."

    # 14. Stop / Standby
    if any(k in words for k in ["stop", "quiet", "wait", "pause"]):
        return "Understood, standing by silently whenever you are ready."

    # 15. Short affirmative or conversational check
    if norm_clean in ["yes", "yeah", "yep", "sure", "ok", "okay", "alright", "tell me", "explain"]:
        return "I am ready! What specific question or project requirement can I help you with?"

    # 16. Unclear mumble or empty
    if not text.strip() or norm in ("um", "uh", "mumble", "hmm"):
        return "Sorry, could you repeat that?"

    # 17. Unknown question fallback
    return "I don't have that specific information right now. I would be happy to connect you with our team directly at info at octapus dot a e."

has_greeted = False

# Start at current end of events_file
with open(events_file, "r", encoding="utf-8") as f:
    f.seek(0, os.SEEK_END)
    initial_offset = f.tell()

print(f"[Bridge active] Listening for meeting events in English...", flush=True)

try:
    with open(events_file, "r", encoding="utf-8") as f:
        f.seek(initial_offset)
        while bridge_proc.poll() is None:
            line = f.readline()
            if not line:
                time.sleep(0.3)
                continue
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except Exception:
                continue

            event_type = evt.get("event")

            # 1. Bot Ready (Admitted into meeting) - strictly in English
            if event_type == "call.bot_ready" and not has_greeted:
                has_greeted = True
                print(">>> BOT READY IN MEETING! Sending welcome greeting in English...", flush=True)
                send_command({"command": "mic", "action": "on"})
                send_command({
                    "command": "send_chat",
                    "message": "Hello everyone! I am Horus AI from Octapus LLC. I am here to assist and clear any doubts you have regarding our custom CRM & ERP software, websites, and WhatsApp automations. Feel free to ask anything!"
                })
                send_command({
                    "command": "tts.speak",
                    "text": "Hello everyone! I am Horus AI from Octapus LLC. I am here to clear any doubts you have regarding our custom CRM and ERP software, website development, and WhatsApp automation. How can I help you today?",
                    "voice": "af_heart",
                    "speed": 0.95
                })

            # 2. User spoke in meeting
            elif event_type in ("transcript.final", "user.message"):
                speaker = evt.get("speaker") or "Participant"
                text = (evt.get("text") or "").strip()
                if not text:
                    continue

                # Ignore bot speaking its own text if echoed
                if speaker.lower() in (bot_name.lower(), "horus", "horus ai"):
                    continue

                print(f"[Meeting Speech from {speaker}]: {text}", flush=True)

                reply_text = generate_intelligent_reply(text)
                print(f"[Horus AI Response (English)]: {reply_text}", flush=True)
                cleaned_spoken = clean_for_speech(reply_text)

                send_command({"command": "send_chat", "message": reply_text})
                send_command({
                    "command": "tts.speak",
                    "text": cleaned_spoken,
                    "voice": "af_heart",
                    "speed": 0.95
                })

            # 3. Meeting Chat message received from user
            elif event_type in ("chat.message", "chat.received"):
                sender = evt.get("sender") or "Participant"
                text = (evt.get("message") or evt.get("text") or "").strip()
                if sender.lower() not in (bot_name.lower(), "horus", "horus ai") and text:
                    print(f"[Meeting Chat from {sender}]: {text}", flush=True)
                    reply_text = generate_intelligent_reply(text)
                    cleaned_spoken = clean_for_speech(reply_text)
                    send_command({"command": "send_chat", "message": reply_text})
                    if "stop" not in text.lower():
                        send_command({
                            "command": "tts.speak",
                            "text": cleaned_spoken,
                            "voice": "af_heart",
                            "speed": 0.95
                        })

finally:
    if bridge_proc.poll() is None:
        bridge_proc.terminate()
        bridge_proc.wait()

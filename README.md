# Octapus AI Agents Platform

Production AI platform for **Octapus LLC** (Dubai, UAE), featuring a human-like Customer Agent (Web & WhatsApp), an Orbit WhatsApp Gateway Bridge, persistent SQLite storage, and an internal Staff Assistant.

📖 **For detailed architecture, database schemas, and API references, see [DOCUMENTATION.md](file:///Users/ceooctapus/Downloads/octapus-agents/DOCUMENTATION.md).**

---

## Architecture Overview

- **Customer Agent (`customer-agent/`)**: Public customer service coordinator persona (**Horus**) operating over Web chat and WhatsApp. Restriced strictly to [`company_info.md`](file:///Users/ceooctapus/Downloads/octapus-agents/customer-agent/company_info.md).
- **WhatsApp Bridge (`whatsapp-bridge.js`)**: Express webhook service linking the Orbit WhatsApp Gateway (`http://localhost:8098`) to the Customer Agent with live automated replies.
- **Persistent Database (`customer-agent/db.py`)**: SQLite 3 database (`customer_agent.db`) saving all Web and WhatsApp chat histories and leads across restarts.
- **Staff Assistant (`staff-assistant/`)**: Internal, password-protected team copilot powered by [`internal_info.md`](file:///Users/ceooctapus/Downloads/octapus-agents/staff-assistant/internal_info.md).

---

## Quick Start

### 1. Install & Configure
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r customer-agent/requirements.txt -r staff-assistant/requirements.txt
npm install
```

Configure `.env` with your API keys (see `DOCUMENTATION.md`).

### 2. Run All Services
```bash
# Starts Customer Agent (8000), Staff Assistant (8001), and WhatsApp Bridge (3000)
.venv/bin/python3 run_dev.py --with-bridge
```

### 3. Service Ports
- **Customer Agent Web Chat**: `http://localhost:8000`
- **WhatsApp Bridge Webhook**: `http://localhost:3000`
- **Orbit WhatsApp Gateway**: `http://localhost:8098`
- **Staff Assistant**: `http://localhost:8001`


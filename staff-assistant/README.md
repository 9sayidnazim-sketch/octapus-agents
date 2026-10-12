# Octapus Staff Assistant

An internal, password-protected operations assistant and REST API agent for Octapus LLC built with FastAPI and Claude tool use.

## Overview
- **Internal Knowledge**: Consults `internal_info.md` for company workflows, approvals, and guidelines.
- **REST API Tools**: Calls external Octapus API endpoints via Claude tool use:
  - `GET /clients/{id}`: Look up specific client details (`get_client`).
  - `GET /projects?status=open`: Fetch open or filtered projects (`get_projects`).
  - `POST /leads`: Create new sales leads (`create_lead`).
- **Safe Write Operations**: Write operations (such as lead creation) require explicit staff confirmation (`yes`) before any network request is executed, enforced by session state (`pending_action`).
- **Security**: Password protected using `STAFF_PASSWORD` (HMAC comparison).

---

## Environment Variables

Copy `.env.example` to `.env` (or configure in the root `.env`):

| Variable | Description | Example / Default |
| :--- | :--- | :--- |
| `ANTHROPIC_API_KEY` | Anthropic Claude API Key | `sk-ant-...` |
| `ANTHROPIC_BASE_URL` | Optional API endpoint or proxy URL | `https://api.anthropic.com` |
| `OCTAPUS_API_BASE_URL` | Base URL for the Octapus REST API | `https://api.example.com/v1` |
| `OCTAPUS_API_KEY` | API Key for external REST API (`X-API-Key`) | `your-octapus-api-key` |
| `STAFF_PASSWORD` | Access password for the Staff Assistant UI & API | `octapus-dev-staff-2026` |

---

## Setup & Installation

1. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

---

## Running the Server

### Standalone Staff Assistant:
```bash
uvicorn app:app --reload --port 8001
```

### From Project Root:
```bash
python3 run_dev.py --app staff
# or run both Customer Agent & Staff Assistant concurrently:
python3 run_dev.py --app all
```

Open [http://localhost:8001](http://localhost:8001) in your browser and enter your `STAFF_PASSWORD`.

---

## Running Unit Tests

Run the test suite using `pytest`:
```bash
pytest tests/test_api_client.py -v
```

The tests use `httpx.MockTransport` to cover:
- Successful `GET` requests (e.g. `/clients/{id}`)
- `401 Unauthorized` responses
- `404 Not Found` responses
- Request timeouts (10s limit)
- Write operation confirmation workflow (staged `pending_action` before execution)

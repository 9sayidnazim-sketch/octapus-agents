# Octapus Agents

Two separate apps. Keep them apart: the customer app must never contain internal data.

## customer-agent (public website chat)
Uses only public company information in company_info.md.
Run: cd customer-agent && pip install -r requirements.txt && uvicorn app:app --reload

## staff-assistant (internal, password-protected)
Uses internal_info.md. Requires STAFF_PASSWORD in addition to ANTHROPIC_API_KEY.
Run: cd staff-assistant && pip install -r requirements.txt
     export STAFF_PASSWORD="choose-a-strong-password"
     uvicorn app:app --reload

Deploy the staff assistant only over HTTPS and never on a public, unprotected URL.
Re-verify all [RE-VERIFY] items with the owner before relying on them, since the source data is from July 2026.

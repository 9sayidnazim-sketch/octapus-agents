from __future__ import annotations

import datetime
import logging
import time
from typing import Any, Dict, List, Optional
from pathlib import Path

from .models import (
    CampaignRecipient,
    CampaignStatus,
    CampaignState,
    DeliveryLogEntry,
    SendResult,
)
from .validator import RecipientValidator, DEFAULT_ALLOWED_RECIPIENTS
from .gateway import WhatsAppGateway

try:
    from customer_agent import db
except ImportError:
    try:
        import db
    except ImportError:
        from .. import db

logger = logging.getLogger("octapus.campaigns.workflow")

HORUS_DEFAULT_INTRODUCTION = """Good morning! ☀️

I’m Horus AI, your new AI assistant, being introduced to our team to help make our daily work smarter, faster, and more efficient.

I’m currently in the testing phase, learning how to assist with our team’s communication and workflows.

Over time, I aim to help with information, routine tasks, and productivity while keeping human team members in control.

This is an initial introduction as we test and improve the system.

Wishing everyone a productive and successful day!

— Horus AI 🤖"""

TONE_TEMPLATES = {
    "warm_professional": HORUS_DEFAULT_INTRODUCTION,
    "energetic": """Good morning team! ☀️🚀

I’m Horus AI, our new AI assistant, joining the team today to help accelerate our daily communication, tasks, and efficiency!

I am currently in my initial testing and learning phase, working alongside everyone while keeping all team members in full control.

Wishing each of you an inspired, productive, and high-impact day ahead!

— Horus AI 🤖""",
    "concise": """Good morning! ☀️

I’m Horus AI, our new AI assistant. I'm being introduced to help with everyday information, productivity, and workflows.

We are currently running an initial system test. Have a wonderful and productive day ahead!

— Horus AI 🤖""",
}


class CampaignWorkflowManager:
    """
    Manages the Horus AI WhatsApp team rollout workflow with mandatory Test Mode,
    manual approval gates, deduplication, and failure safeguards.
    """

    def __init__(
        self,
        campaign_id: str = "horus-team-intro-2026",
        campaign_name: str = "Horus AI — WhatsApp Team Introduction & Good Morning Automation",
        db_path: Optional[Path] = None,
        gateway: Optional[WhatsAppGateway] = None,
    ):
        self.campaign_id = campaign_id
        self.campaign_name = campaign_name
        self.db_path = db_path
        self.gateway = gateway or WhatsAppGateway()

        # Ensure campaign record exists in database with test_mode=1 by default
        self._sync_db_init()

    def _sync_db_init(self) -> None:
        """Initialize or fetch campaign record in DB."""
        db.get_or_create_campaign(
            campaign_id=self.campaign_id,
            name=self.campaign_name,
            template=HORUS_DEFAULT_INTRODUCTION,
            tone="warm_professional",
            db_path=self.db_path,
        )

    def get_campaign_record(self) -> Dict[str, Any]:
        """Fetch current DB record for campaign."""
        record = db.get_campaign(self.campaign_id, db_path=self.db_path)
        if not record:
            self._sync_db_init()
            record = db.get_campaign(self.campaign_id, db_path=self.db_path) or {}
        return record

    def get_workflow_state(self) -> Dict[str, Any]:
        """
        Builds complete workflow state for dashboard and API:
        - Validated team recipients
        - Message preview and metadata
        - Current test recipient and test approval state
        - Gateway connectivity status
        - Delivery statistics and logs
        """
        campaign = self.get_campaign_record()
        recipients = RecipientValidator.load_team_recipients(DEFAULT_ALLOWED_RECIPIENTS)
        logs = db.get_campaign_logs(self.campaign_id, db_path=self.db_path)
        gateway_status = self.gateway.check_connection()

        # Calculate statistics
        test_logs = [l for l in logs if l.get("is_test") == 1]
        rollout_logs = [l for l in logs if l.get("is_test") == 0]

        delivered_count = sum(1 for l in rollout_logs if l.get("status") == "delivered")
        failed_count = sum(1 for l in rollout_logs if l.get("status") == "failed")
        pending_count = len(recipients) - delivered_count - failed_count
        if pending_count < 0:
            pending_count = 0

        stats = {
            "total_recipients": len(recipients),
            "test_messages_sent": len(test_logs),
            "delivered": delivered_count,
            "failed": failed_count,
            "pending": pending_count,
            "skipped": sum(1 for l in rollout_logs if l.get("status") == "skipped"),
        }

        # Latest test log
        latest_test_log = test_logs[-1] if test_logs else None

        template_text = campaign.get("message_template") or HORUS_DEFAULT_INTRODUCTION

        return {
            "campaign_id": self.campaign_id,
            "name": campaign.get("name") or self.campaign_name,
            "status": campaign.get("status", "draft"),
            "test_mode": bool(campaign.get("test_mode", 1)),
            "test_recipient": campaign.get("test_recipient"),
            "test_approved": bool(campaign.get("test_approved", 0)),
            "tone": campaign.get("tone", "warm_professional"),
            "message_template": template_text,
            "message_stats": {
                "character_count": len(template_text),
                "word_count": len(template_text.split()),
                "estimated_read_seconds": round(len(template_text.split()) / 3.5, 1),
            },
            "recipients": [r.model_dump() for r in recipients],
            "gateway_status": gateway_status,
            "stats": stats,
            "logs": logs,
            "latest_test_result": latest_test_log,
            "ready_for_rollout": (
                bool(campaign.get("test_approved", 0))
                and gateway_status.get("is_online", False)
            ),
        }

    def update_template(self, template: str, tone: Optional[str] = None) -> Dict[str, Any]:
        """Update campaign message template or tone preset."""
        cleaned_template = template.strip() if template else HORUS_DEFAULT_INTRODUCTION
        selected_tone = tone or "warm_professional"

        if tone and tone in TONE_TEMPLATES and not template:
            cleaned_template = TONE_TEMPLATES[tone]

        db.update_campaign(
            self.campaign_id,
            {"message_template": cleaned_template, "tone": selected_tone},
            db_path=self.db_path,
        )
        return self.get_workflow_state()

    def set_test_recipient(self, phone_number: str) -> CampaignRecipient:
        """Validate and set explicitly configured test recipient."""
        recipient = RecipientValidator.validate_and_format(phone_number)
        if not recipient.is_valid:
            raise ValueError(f"Invalid phone number: {recipient.validation_error}")

        db.update_campaign(
            self.campaign_id,
            {"test_recipient": recipient.phone_number},
            db_path=self.db_path,
        )
        return recipient

    def send_test_message(self, test_number: Optional[str] = None) -> SendResult:
        """
        Phase 1: Send a single test message ONLY to the explicitly approved test recipient.
        Strictly records success/failure, latency, and error details in logs.
        Never contacts other team members.
        """
        campaign = self.get_campaign_record()
        target_number = test_number or campaign.get("test_recipient")

        if not target_number:
            raise ValueError(
                "No test recipient configured. Please configure your test phone number before sending."
            )

        recipient = RecipientValidator.validate_and_format(target_number)
        if not recipient.is_valid:
            raise ValueError(f"Invalid test recipient number: {recipient.validation_error}")

        # Update test_recipient if changed
        db.update_campaign(
            self.campaign_id,
            {"test_recipient": recipient.phone_number, "status": "testing"},
            db_path=self.db_path,
        )

        template_text = campaign.get("message_template") or HORUS_DEFAULT_INTRODUCTION

        # Dispatch via gateway
        result = self.gateway.send_message(recipient.phone_number, template_text)

        # Record test delivery log
        db.save_campaign_log(
            campaign_id=self.campaign_id,
            phone_number=recipient.phone_number,
            clean_number=recipient.clean_number,
            country=recipient.country,
            is_test=1,
            status=result.status,
            attempts=1,
            error_details=result.error_details,
            delivered_at=result.timestamp if result.success else None,
            db_path=self.db_path,
        )

        # Update campaign status
        new_status = "test_sent" if result.success else "draft"
        db.update_campaign(
            self.campaign_id,
            {"status": new_status},
            db_path=self.db_path,
        )

        return result

    def approve_test(self) -> Dict[str, Any]:
        """
        Phase 1 -> Phase 3 Gate:
        User manually inspects the test result and approves rollout.
        """
        logs = db.get_campaign_logs(self.campaign_id, is_test=1, db_path=self.db_path)
        if not logs:
            raise ValueError("Cannot approve test: No test message has been sent yet.")

        latest = logs[-1]
        if latest.get("status") != "delivered":
            raise ValueError(
                f"Cannot approve test: The latest test was not confirmed as delivered (Status: {latest.get('status')}, Error: {latest.get('error_details')})."
            )

        db.update_campaign(
            self.campaign_id,
            {"test_approved": 1, "status": "test_approved"},
            db_path=self.db_path,
        )
        return self.get_workflow_state()

    def execute_rollout(
        self,
        confirm: bool = False,
        delay_seconds: float = 1.5,
    ) -> Dict[str, Any]:
        """
        Phase 3: Controlled Team Rollout.
        Mandatory preconditions:
        1. Explicit user confirmation (confirm=True).
        2. Prior test message must have been approved (test_approved=True).
        3. Never send duplicates to recipients already delivered in this campaign.
        4. Halts immediately on account restriction, rate limit, or fatal gateway error.
        5. Does not discover unknown contacts; operates strictly on the 8 validated team numbers.
        """
        if not confirm:
            raise ValueError("Rollout requires explicit confirmation. Please confirm to proceed.")

        campaign = self.get_campaign_record()
        if not campaign.get("test_approved"):
            raise ValueError(
                "Rollout blocked: Test message has not been approved yet. Complete Phase 1 test and approval first."
            )

        # Fetch existing delivered logs for deduplication
        existing_logs = db.get_campaign_logs(self.campaign_id, is_test=0, db_path=self.db_path)
        delivered_clean_numbers = {
            log["clean_number"]
            for log in existing_logs
            if log.get("status") == "delivered"
        }

        recipients = RecipientValidator.load_team_recipients(DEFAULT_ALLOWED_RECIPIENTS)
        template_text = campaign.get("message_template") or HORUS_DEFAULT_INTRODUCTION

        db.update_campaign(
            self.campaign_id,
            {"status": "rolling_out"},
            db_path=self.db_path,
        )

        dispatched = []
        aborted_reason = None

        for rec in recipients:
            if not rec.is_valid:
                db.save_campaign_log(
                    campaign_id=self.campaign_id,
                    phone_number=rec.phone_number,
                    clean_number=rec.clean_number,
                    country=rec.country,
                    is_test=0,
                    status="failed",
                    attempts=1,
                    error_details=f"Invalid format: {rec.validation_error}",
                    db_path=self.db_path,
                )
                continue

            # Deduplication check
            if rec.clean_number in delivered_clean_numbers:
                logger.info("Skipping %s: already delivered in this campaign.", rec.phone_number)
                db.save_campaign_log(
                    campaign_id=self.campaign_id,
                    phone_number=rec.phone_number,
                    clean_number=rec.clean_number,
                    country=rec.country,
                    is_test=0,
                    status="skipped",
                    attempts=0,
                    error_details="Deduplicated: already delivered in this campaign.",
                    db_path=self.db_path,
                )
                continue

            # Dispatch individually
            result = self.gateway.send_message(rec.phone_number, template_text)
            dispatched.append(result)

            db.save_campaign_log(
                campaign_id=self.campaign_id,
                phone_number=rec.phone_number,
                clean_number=rec.clean_number,
                country=rec.country,
                is_test=0,
                status=result.status,
                attempts=1,
                error_details=result.error_details,
                delivered_at=result.timestamp if result.success else None,
                db_path=self.db_path,
            )

            # Safety stop checks
            if result.is_rate_limited:
                aborted_reason = f"Campaign stopped: WhatsApp rate limit (HTTP 429) encountered on {rec.phone_number}."
                break

            if result.is_restricted:
                aborted_reason = f"Campaign stopped: WhatsApp account restriction / auth error encountered on {rec.phone_number}."
                break

            # Rate pacing delay
            if delay_seconds > 0:
                time.sleep(delay_seconds)

        final_status = "paused" if aborted_reason else "completed"
        db.update_campaign(
            self.campaign_id,
            {"status": final_status},
            db_path=self.db_path,
        )

        workflow_state = self.get_workflow_state()
        workflow_state["aborted_reason"] = aborted_reason
        workflow_state["dispatched_count"] = len(dispatched)
        return workflow_state

    def reset_campaign(self) -> Dict[str, Any]:
        """Reset campaign logs and approval status to allow fresh testing."""
        db.reset_campaign_logs(self.campaign_id, db_path=self.db_path)
        db.update_campaign(
            self.campaign_id,
            {
                "test_approved": 0,
                "status": "draft",
                "test_mode": 1,
            },
            db_path=self.db_path,
        )
        return self.get_workflow_state()

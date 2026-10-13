from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    TESTING = "testing"
    TEST_SENT = "test_sent"
    TEST_APPROVED = "test_approved"
    ROLLING_OUT = "rolling_out"
    COMPLETED = "completed"
    PAUSED = "paused"
    FAILED = "failed"


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    SKIPPED = "skipped"


class CampaignRecipient(BaseModel):
    phone_number: str
    clean_number: str
    formatted: str
    country: str
    country_code: str
    is_valid: bool = True
    validation_error: Optional[str] = None
    role_or_note: Optional[str] = None


class SendResult(BaseModel):
    success: bool
    recipient: str
    clean_number: str
    timestamp: str
    status: str
    status_code: Optional[int] = None
    message_id: Optional[str] = None
    error_details: Optional[str] = None
    is_rate_limited: bool = False
    is_restricted: bool = False
    latency_ms: Optional[float] = None


class DeliveryLogEntry(BaseModel):
    id: str
    campaign_id: str
    phone_number: str
    clean_number: str
    country: str
    is_test: bool
    status: str
    attempts: int = 1
    error_details: Optional[str] = None
    delivered_at: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None


class CampaignState(BaseModel):
    id: str
    name: str
    message_template: str
    tone: str
    test_mode: bool = True
    test_recipient: Optional[str] = None
    test_approved: bool = False
    status: str
    recipients: List[CampaignRecipient] = Field(default_factory=list)
    logs: List[DeliveryLogEntry] = Field(default_factory=list)
    stats: Dict[str, int] = Field(default_factory=dict)

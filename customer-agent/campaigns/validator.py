from __future__ import annotations

import re
from typing import List, Optional, Tuple
from .models import CampaignRecipient

DEFAULT_ALLOWED_RECIPIENTS = [
    "+918157070717",
    "+971508621612",
    "+971545696499",
    "+918089170148",
    "+918590851447",
    "+919745482646",
    "+919746283316",
    "+971544556613",
]

RECIPIENT_ROLES = {
    "+918157070717": "Team Member — Engineering (India)",
    "+971508621612": "Team Executive — Octapus LLC (UAE)",
    "+971545696499": "Team Member — Operations (UAE)",
    "+918089170148": "Team Member — Development (India)",
    "+918590851447": "Team Member — Support (India)",
    "+919745482646": "Team Member — Engineering (India)",
    "+919746283316": "Team Member — Development (India)",
    "+971544556613": "Team Member — Management (UAE)",
}


class RecipientValidator:
    """Validates and formats WhatsApp phone numbers according to E.164 and regional standards."""

    @staticmethod
    def clean_number(raw: str) -> str:
        """Strip non-numeric characters except leading '+' if present."""
        if not raw:
            return ""
        return re.sub(r"[^\d]", "", raw)

    @classmethod
    def validate_and_format(cls, raw: str) -> CampaignRecipient:
        """Validate an individual phone number and return a structured CampaignRecipient."""
        raw_trimmed = (raw or "").strip()
        digits = cls.clean_number(raw_trimmed)

        if not digits:
            return CampaignRecipient(
                phone_number=raw_trimmed,
                clean_number="",
                formatted=raw_trimmed,
                country="Unknown",
                country_code="XX",
                is_valid=False,
                validation_error="Empty or missing phone number.",
            )

        # Detect India (+91)
        if digits.startswith("91") and len(digits) == 12:
            local = digits[2:]
            formatted = f"+91 {local[:5]} {local[5:]}"
            standard_e164 = f"+{digits}"
            role = RECIPIENT_ROLES.get(standard_e164)
            return CampaignRecipient(
                phone_number=standard_e164,
                clean_number=digits,
                formatted=formatted,
                country="India",
                country_code="IN",
                is_valid=True,
                role_or_note=role,
            )

        # Detect UAE (+971)
        if digits.startswith("971") and len(digits) == 12:
            local = digits[3:]
            formatted = f"+971 {local[:2]} {local[2:5]} {local[5:]}"
            standard_e164 = f"+{digits}"
            role = RECIPIENT_ROLES.get(standard_e164)
            return CampaignRecipient(
                phone_number=standard_e164,
                clean_number=digits,
                formatted=formatted,
                country="United Arab Emirates",
                country_code="AE",
                is_valid=True,
                role_or_note=role,
            )

        # If user entered local number starting with 0 or 5 for UAE (9 digits)
        if digits.startswith("05") and len(digits) == 10:
            full_digits = f"971{digits[1:]}"
            local = full_digits[3:]
            standard_e164 = f"+{full_digits}"
            return CampaignRecipient(
                phone_number=standard_e164,
                clean_number=full_digits,
                formatted=f"+971 {local[:2]} {local[2:5]} {local[5:]}",
                country="United Arab Emirates",
                country_code="AE",
                is_valid=True,
                role_or_note=RECIPIENT_ROLES.get(standard_e164),
            )

        # If user entered 10 digits for India starting with 7, 8, 9
        if len(digits) == 10 and digits[0] in ("6", "7", "8", "9"):
            full_digits = f"91{digits}"
            standard_e164 = f"+{full_digits}"
            return CampaignRecipient(
                phone_number=standard_e164,
                clean_number=full_digits,
                formatted=f"+91 {digits[:5]} {digits[5:]}",
                country="India",
                country_code="IN",
                is_valid=True,
                role_or_note=RECIPIENT_ROLES.get(standard_e164),
            )

        # Generic fallback validation check
        if 8 <= len(digits) <= 15:
            return CampaignRecipient(
                phone_number=f"+{digits}",
                clean_number=digits,
                formatted=f"+{digits}",
                country="International",
                country_code="INT",
                is_valid=True,
                validation_error=None,
            )

        return CampaignRecipient(
            phone_number=raw_trimmed,
            clean_number=digits,
            formatted=raw_trimmed,
            country="Unknown",
            country_code="XX",
            is_valid=False,
            validation_error=f"Invalid phone number length ({len(digits)} digits). Must be E.164 compatible.",
        )

    @classmethod
    def load_team_recipients(cls, numbers: Optional[List[str]] = None) -> List[CampaignRecipient]:
        """Load and validate the team numbers."""
        targets = numbers if numbers is not None else DEFAULT_ALLOWED_RECIPIENTS
        return [cls.validate_and_format(n) for n in targets]

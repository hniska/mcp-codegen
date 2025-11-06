"""Privacy and PII scrubbing for logs.

Redacts emails, phone numbers, and other sensitive data from logs
before they reach the model. Supports multiple scrubbing levels.
"""
from __future__ import annotations
import re
import json
from typing import Any, Union, Dict, List, Tuple, Optional

# PII detection patterns
EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
# US phone numbers (try to be less aggressive to avoid false positives)
US_PHONE_RE = re.compile(r'\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b')
# International E.164 format (more precise)
INTL_PHONE_RE = re.compile(r'\+\d{1,3}[-.\s]?\d{6,14}\b')
SSN_RE = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
CREDIT_CARD_RE = re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b')
# Private IP ranges (only redacted in strict mode)
PRIVATE_IP_RE = re.compile(r'\b(?:10\.|172\.(?:1[6-9]|2[0-9]|3[01])\.|192\.168\.)\d{1,3}\b')

# E.164 phone normalization helper
try:
    import phonenumbers
    from phonenumbers import PhoneNumberType
    PHONENUMBERS_AVAILABLE = True
except ImportError:
    PHONENUMBERS_AVAILABLE = False

class Scrubber:
    """Redacts sensitive data from text with configurable levels.

    Levels:
        - "basic": Email, SSN, credit cards (low false positive rate)
        - "strict": All basic + phone numbers, private IPs
    """

    def __init__(self, level: str = "basic"):
        """Initialize scrubber with specified level.

        Args:
            level: "basic" or "strict"
        """
        self.level = level
        self._patterns = []

        # Always include these (low false positive rate)
        self._patterns.extend([
            (EMAIL_RE, "[EMAIL]"),
            (SSN_RE, "[SSN]"),
            (CREDIT_CARD_RE, "[CREDIT_CARD]"),
        ])

        if level == "strict":
            # Add these with more careful patterns
            self._patterns.extend([
                (INTL_PHONE_RE, "[PHONE]"),
                (PRIVATE_IP_RE, "[PRIVATE_IP]"),
            ])

            # Add US phone pattern with caution
            self._patterns.append((US_PHONE_RE, "[PHONE]"))

    def validate_phone(self, text: str) -> bool:
        """Validate if text looks like a phone number.

        Uses phonenumbers library if available, otherwise uses regex.
        """
        if PHONENUMBERS_AVAILABLE:
            try:
                # Try parsing as E.164 or national format
                parsed = phonenumbers.parse(text, None)
                return phonenumbers.is_valid_number(parsed)
            except:
                return False
        else:
            # Fallback to regex
            return bool(INTL_PHONE_RE.search(text) or US_PHONE_RE.search(text))

    def scrub_text(self, text: str) -> str:
        """Scrub sensitive data from text.

        Args:
            text: Input text

        Returns:
            Text with PII redacted
        """
        if not isinstance(text, str):
            text = str(text)

        for pattern, replacement in self._patterns:
            text = pattern.sub(replacement, text)

        return text

    def scrub_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Scrub sensitive data from dictionary.

        Args:
            data: Input dictionary

        Returns:
            Dictionary with PII redacted
        """
        scrubbed = {}
        for key, value in data.items():
            if isinstance(value, str):
                # Check if key suggests sensitive data
                key_lower = key.lower()
                if any(term in key_lower for term in ['password', 'token', 'secret', 'key', 'auth']):
                    scrubbed[key] = "[REDACTED]"
                else:
                    scrubbed[key] = self.scrub_text(value)
            elif isinstance(value, dict):
                scrubbed[key] = self.scrub_dict(value)
            elif isinstance(value, list):
                scrubbed[key] = [self.scrub_text(v) if isinstance(v, str) else v for v in value]
            else:
                scrubbed[key] = value

        return scrubbed

    def scrub_json(self, data: str) -> str:
        """Scrub sensitive data from JSON string.

        Args:
            data: JSON string

        Returns:
            JSON string with PII redacted
        """
        try:
            parsed = json.loads(data)
            scrubbed = self.scrub_dict(parsed)
            return json.dumps(scrubbed, indent=2)
        except (json.JSONDecodeError, TypeError):
            # Not valid JSON, treat as plain text
            return self.scrub_text(data)

# Global scrubber instance
_scrubber = Scrubber()

def scrub(text: str) -> str:
    """Scrub PII from text (convenience function).

    Args:
        text: Input text

    Returns:
        Text with PII redacted
    """
    return _scrubber.scrub_text(text)

def redact_value(value: str) -> str:
    """Redact entire value if it might contain PII.

    Args:
        value: Value to check

    Returns:
        "[REDACTED]" if likely sensitive, otherwise original value
    """
    # Check for common PII patterns
    if EMAIL_RE.search(value) or INTL_PHONE_RE.search(value) or SSN_RE.search(value):
        return "[REDACTED]"
    return value

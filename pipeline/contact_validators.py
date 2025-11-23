"""
Contact Validators

Validation logic for phone numbers, WhatsApp, and LinkedIn profiles.
Ensures contacts are properly formatted and (where possible) reachable.
"""

import re
import logging
from typing import Optional, Dict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of contact validation."""
    is_valid: bool
    normalized_value: str
    reason: Optional[str] = None
    metadata: Dict = None

    def __post_init__(self):
        if not self.metadata:
            self.metadata = {}


class PhoneValidator:
    """Validates phone numbers."""

    # Country code patterns
    COUNTRY_CODES = {
        '+1': 'US/Canada',
        '+44': 'UK',
        '+48': 'Poland',
        '+49': 'Germany',
        '+33': 'France',
        '+39': 'Italy',
        '+34': 'Spain',
        '+91': 'India',
        '+86': 'China',
        '+81': 'Japan',
        '+61': 'Australia'
    }

    @staticmethod
    def validate(phone: str) -> ValidationResult:
        """
        Validate and normalize phone number.

        Args:
            phone: Phone number string

        Returns:
            ValidationResult
        """
        # Remove all non-digit characters except +
        cleaned = re.sub(r'[^\d+]', '', phone)

        # Must have digits
        if not cleaned:
            return ValidationResult(
                is_valid=False,
                normalized_value=phone,
                reason="No digits found"
            )

        # Ensure it starts with +
        if not cleaned.startswith('+'):
            # Try to add + if it looks like international format
            digits_only = re.sub(r'\D', '', cleaned)
            if len(digits_only) >= 10:
                cleaned = '+' + digits_only
            else:
                return ValidationResult(
                    is_valid=False,
                    normalized_value=phone,
                    reason="Invalid format (must start with + or be 10+ digits)"
                )

        # Validate length (7-15 digits)
        digits = re.sub(r'\D', '', cleaned)
        if len(digits) < 7:
            return ValidationResult(
                is_valid=False,
                normalized_value=cleaned,
                reason="Too short (minimum 7 digits)"
            )

        if len(digits) > 15:
            return ValidationResult(
                is_valid=False,
                normalized_value=cleaned,
                reason="Too long (maximum 15 digits)"
            )

        # Try to identify country
        country = None
        for code, country_name in PhoneValidator.COUNTRY_CODES.items():
            if cleaned.startswith(code):
                country = country_name
                break

        return ValidationResult(
            is_valid=True,
            normalized_value=cleaned,
            metadata={
                'country': country,
                'digit_count': len(digits)
            }
        )


class WhatsAppValidator:
    """Validates WhatsApp numbers."""

    @staticmethod
    def validate(whatsapp: str) -> ValidationResult:
        """
        Validate WhatsApp number.

        WhatsApp numbers must be valid phone numbers.

        Args:
            whatsapp: WhatsApp number or wa.me link

        Returns:
            ValidationResult
        """
        # Extract number from wa.me link if present
        if 'wa.me/' in whatsapp:
            number = whatsapp.split('wa.me/')[-1].split('?')[0]
        elif 'whatsapp.com' in whatsapp:
            # Try to extract from various WhatsApp URL formats
            match = re.search(r'phone=([\d+]+)', whatsapp)
            if match:
                number = match.group(1)
            else:
                return ValidationResult(
                    is_valid=False,
                    normalized_value=whatsapp,
                    reason="Could not extract number from WhatsApp link"
                )
        else:
            number = whatsapp

        # Use phone validator
        phone_result = PhoneValidator.validate(number)

        if not phone_result.is_valid:
            return ValidationResult(
                is_valid=False,
                normalized_value=whatsapp,
                reason=f"Invalid phone number: {phone_result.reason}"
            )

        # Valid WhatsApp number
        return ValidationResult(
            is_valid=True,
            normalized_value=phone_result.normalized_value,
            metadata={
                **phone_result.metadata,
                'original_format': 'link' if 'wa.me' in whatsapp else 'number'
            }
        )


class LinkedInValidator:
    """Validates LinkedIn profile URLs."""

    VALID_PATTERNS = [
        r'^https?://([a-z]+\.)?linkedin\.com/company/[\w\-]+/?$',
        r'^https?://([a-z]+\.)?linkedin\.com/in/[\w\-]+/?$',
        r'^https?://([a-z]+\.)?linkedin\.com/pub/[\w\-/]+/?$'
    ]

    @staticmethod
    def validate(linkedin_url: str) -> ValidationResult:
        """
        Validate LinkedIn profile URL.

        Args:
            linkedin_url: LinkedIn URL

        Returns:
            ValidationResult
        """
        # Normalize URL
        url = linkedin_url.strip()

        # Add https:// if missing
        if not url.startswith('http'):
            url = f'https://{url}'

        # Remove tracking parameters
        url = url.split('?')[0]

        # Ensure trailing slash is consistent
        url = url.rstrip('/') + '/'

        # Check against patterns
        profile_type = None
        for pattern in LinkedInValidator.VALID_PATTERNS:
            if re.match(pattern, url, re.IGNORECASE):
                if '/company/' in url:
                    profile_type = 'company'
                elif '/in/' in url:
                    profile_type = 'individual'
                elif '/pub/' in url:
                    profile_type = 'public_profile'

                return ValidationResult(
                    is_valid=True,
                    normalized_value=url.rstrip('/'),  # Remove trailing slash for final value
                    metadata={'profile_type': profile_type}
                )

        return ValidationResult(
            is_valid=False,
            normalized_value=linkedin_url,
            reason="Invalid LinkedIn URL format"
        )


class SocialMediaValidator:
    """Validates social media profile URLs."""

    PLATFORM_PATTERNS = {
        'instagram': r'^https?://(www\.)?instagram\.com/[\w\.]+/?$',
        'facebook': r'^https?://(www\.)?(facebook|fb)\.com/[\w\.]+/?$',
        'twitter': r'^https?://(www\.)?(twitter|x)\.com/[\w]+/?$',
        'youtube': r'^https?://(www\.)?youtube\.com/([@\w]+|channel/[\w\-]+)/?$',
        'tiktok': r'^https?://(www\.)?tiktok\.com/@[\w\.]+/?$'
    }

    @staticmethod
    def validate(url: str, platform: str = None) -> ValidationResult:
        """
        Validate social media profile URL.

        Args:
            url: Social media URL
            platform: Platform name (optional, will auto-detect)

        Returns:
            ValidationResult
        """
        # Normalize URL
        normalized = url.strip()

        if not normalized.startswith('http'):
            normalized = f'https://{normalized}'

        # Remove tracking parameters
        normalized = normalized.split('?')[0]

        # Auto-detect platform if not specified
        detected_platform = None
        for plat, pattern in SocialMediaValidator.PLATFORM_PATTERNS.items():
            if plat.replace('_', '') in normalized.lower():
                detected_platform = plat
                break

        if not detected_platform:
            return ValidationResult(
                is_valid=False,
                normalized_value=url,
                reason="Unknown social media platform"
            )

        # Validate against pattern
        pattern = SocialMediaValidator.PLATFORM_PATTERNS[detected_platform]
        if re.match(pattern, normalized, re.IGNORECASE):
            return ValidationResult(
                is_valid=True,
                normalized_value=normalized.rstrip('/'),
                metadata={'platform': detected_platform}
            )

        return ValidationResult(
            is_valid=False,
            normalized_value=url,
            reason=f"Invalid {detected_platform} URL format"
        )


# Convenience functions
def validate_phone(phone: str) -> ValidationResult:
    """Quick phone validation."""
    return PhoneValidator.validate(phone)


def validate_whatsapp(whatsapp: str) -> ValidationResult:
    """Quick WhatsApp validation."""
    return WhatsAppValidator.validate(whatsapp)


def validate_linkedin(url: str) -> ValidationResult:
    """Quick LinkedIn validation."""
    return LinkedInValidator.validate(url)


def validate_social(url: str, platform: str = None) -> ValidationResult:
    """Quick social media validation."""
    return SocialMediaValidator.validate(url, platform)

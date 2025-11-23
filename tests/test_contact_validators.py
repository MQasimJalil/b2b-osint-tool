"""
Tests for contact validators.
"""

import pytest
from pipeline.contact_validators import (
    validate_phone,
    validate_whatsapp,
    validate_linkedin,
    validate_social,
    ValidationResult
)


class TestPhoneValidation:
    """Test phone number validation."""

    @pytest.mark.unit
    def test_valid_us_phone(self):
        """Test valid US phone number."""
        result = validate_phone('+1-555-123-4567')
        assert result.is_valid is True
        assert '+1' in result.normalized_value or '1' in result.normalized_value

    @pytest.mark.unit
    def test_valid_us_phone_formats(self):
        """Test various US phone formats."""
        valid_formats = [
            '555-123-4567',
            '(555) 123-4567',
            '555.123.4567',
            '+1 555 123 4567'
        ]

        for phone in valid_formats:
            result = validate_phone(phone)
            assert result.is_valid is True, f"Failed for {phone}"

    @pytest.mark.unit
    def test_valid_international_phone(self):
        """Test valid international phone."""
        result = validate_phone('+44 20 7946 0958')
        assert result.is_valid is True
        assert '+44' in result.normalized_value or '44' in result.normalized_value

    @pytest.mark.unit
    def test_invalid_phone(self):
        """Test invalid phone number."""
        invalid_phones = [
            'invalid-phone',
            '123',
            'abc-def-ghij',
            ''
        ]

        for phone in invalid_phones:
            result = validate_phone(phone)
            assert result.is_valid is False, f"Should be invalid: {phone}"

    @pytest.mark.unit
    def test_phone_normalization(self):
        """Test phone number normalization."""
        result = validate_phone('(555) 123-4567')
        # Should normalize to consistent format
        assert result.normalized_value is not None
        # Should remove formatting characters
        assert '(' not in result.normalized_value
        assert ')' not in result.normalized_value


class TestWhatsAppValidation:
    """Test WhatsApp number validation."""

    @pytest.mark.unit
    def test_valid_whatsapp_number(self):
        """Test valid WhatsApp number."""
        result = validate_whatsapp('+1-555-123-4567')
        assert result.is_valid is True

    @pytest.mark.unit
    def test_valid_whatsapp_url(self):
        """Test valid WhatsApp URL."""
        urls = [
            'https://wa.me/15551234567',
            'https://api.whatsapp.com/send?phone=15551234567',
            'https://wa.me/4420794609568'
        ]

        for url in urls:
            result = validate_whatsapp(url)
            assert result.is_valid is True, f"Failed for {url}"
            assert 'whatsapp_url' in result.metadata

    @pytest.mark.unit
    def test_invalid_whatsapp(self):
        """Test invalid WhatsApp."""
        result = validate_whatsapp('invalid')
        assert result.is_valid is False


class TestLinkedInValidation:
    """Test LinkedIn URL validation."""

    @pytest.mark.unit
    def test_valid_company_profile(self):
        """Test valid company profile."""
        url = 'https://linkedin.com/company/example'
        result = validate_linkedin(url)
        assert result.is_valid is True
        assert 'linkedin_type' in result.metadata
        assert result.metadata['linkedin_type'] == 'company'

    @pytest.mark.unit
    def test_valid_individual_profile(self):
        """Test valid individual profile."""
        url = 'https://linkedin.com/in/john-doe'
        result = validate_linkedin(url)
        assert result.is_valid is True
        assert 'linkedin_type' in result.metadata
        assert result.metadata['linkedin_type'] == 'individual'

    @pytest.mark.unit
    def test_linkedin_url_normalization(self):
        """Test LinkedIn URL normalization."""
        urls = [
            'https://www.linkedin.com/company/example?tracking=123',
            'http://linkedin.com/company/example/',
            'linkedin.com/company/example'
        ]

        for url in urls:
            result = validate_linkedin(url)
            assert result.is_valid is True
            # Should be normalized (no query params, trailing slashes, etc.)
            assert '?' not in result.normalized_value
            assert not result.normalized_value.endswith('/')

    @pytest.mark.unit
    def test_invalid_linkedin(self):
        """Test invalid LinkedIn URL."""
        invalid_urls = [
            'https://linkedin.com/feed/update/123',  # Not a profile
            'https://example.com',  # Not LinkedIn
            'invalid-url',
            ''
        ]

        for url in invalid_urls:
            result = validate_linkedin(url)
            assert result.is_valid is False, f"Should be invalid: {url}"


class TestSocialValidation:
    """Test social media URL validation."""

    @pytest.mark.unit
    def test_valid_social_platforms(self):
        """Test valid social media platforms."""
        urls = {
            'instagram': 'https://instagram.com/example',
            'twitter': 'https://twitter.com/example',
            'facebook': 'https://facebook.com/example',
            'youtube': 'https://youtube.com/@example',
            'tiktok': 'https://tiktok.com/@example'
        }

        for platform, url in urls.items():
            result = validate_social(url)
            assert result.is_valid is True, f"Failed for {platform}: {url}"
            assert 'platform' in result.metadata
            assert result.metadata['platform'] == platform

    @pytest.mark.unit
    def test_social_url_normalization(self):
        """Test social media URL normalization."""
        urls = [
            ('https://www.instagram.com/example/?hl=en', 'instagram'),
            ('http://twitter.com/example?ref=123', 'twitter'),
            ('facebook.com/example/', 'facebook')
        ]

        for url, platform in urls:
            result = validate_social(url)
            assert result.is_valid is True
            # Should be normalized
            assert '?' not in result.normalized_value
            assert not result.normalized_value.endswith('/')

    @pytest.mark.unit
    def test_invalid_social_urls(self):
        """Test invalid social media URLs."""
        invalid_urls = [
            'https://instagram.com/p/ABC123/',  # Post, not profile
            'https://twitter.com/user/status/123',  # Tweet, not profile
            'https://example.com',  # Not a social platform
            'invalid-url',
            ''
        ]

        for url in invalid_urls:
            result = validate_social(url)
            assert result.is_valid is False, f"Should be invalid: {url}"


class TestValidationResult:
    """Test ValidationResult dataclass."""

    @pytest.mark.unit
    def test_validation_result_creation(self):
        """Test creating ValidationResult."""
        result = ValidationResult(
            is_valid=True,
            normalized_value='+1-555-123-4567',
            confidence=0.95,
            metadata={'country': 'US'}
        )

        assert result.is_valid is True
        assert result.normalized_value == '+1-555-123-4567'
        assert result.confidence == 0.95
        assert result.metadata['country'] == 'US'

    @pytest.mark.unit
    def test_validation_result_invalid(self):
        """Test invalid ValidationResult."""
        result = ValidationResult(
            is_valid=False,
            normalized_value=None,
            confidence=0.0,
            metadata={'error': 'Invalid format'}
        )

        assert result.is_valid is False
        assert result.normalized_value is None
        assert result.confidence == 0.0

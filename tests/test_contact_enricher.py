"""
Tests for contact enrichment.
"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path
from pipeline.contact_enricher import ContactEnricher, EnrichedContact, EnrichmentResult


class TestEnrichedContact:
    """Test EnrichedContact dataclass."""

    @pytest.mark.unit
    def test_create_enriched_contact(self):
        """Test creating EnrichedContact."""
        contact = EnrichedContact(
            type='phone',
            value='+1-555-123-4567',
            confidence=0.9,
            source='website',
            metadata={'country': 'US'}
        )

        assert contact.type == 'phone'
        assert contact.value == '+1-555-123-4567'
        assert contact.confidence == 0.9
        assert contact.source == 'website'
        assert contact.metadata['country'] == 'US'


class TestContactEnricher:
    """Test ContactEnricher class."""

    @pytest.mark.unit
    def test_init(self):
        """Test initialization."""
        enricher = ContactEnricher()
        assert enricher is not None

    @pytest.mark.unit
    def test_determine_search_mode_with_valid_emails(self, sample_profile):
        """Test search mode determination with valid emails."""
        enricher = ContactEnricher()

        # Profile with valid emails -> lenient mode
        profile = sample_profile.copy()
        profile['emails'] = ['valid@example.com']
        mode = enricher.determine_search_mode(profile)
        assert mode == 'lenient'

    @pytest.mark.unit
    def test_determine_search_mode_without_emails(self, sample_profile):
        """Test search mode determination without emails."""
        enricher = ContactEnricher()

        # Profile without emails -> aggressive mode
        profile = sample_profile.copy()
        profile['emails'] = []
        mode = enricher.determine_search_mode(profile)
        assert mode == 'aggressive'

    @pytest.mark.unit
    def test_enrich_from_profile(self, sample_profile):
        """Test enriching from profile data."""
        enricher = ContactEnricher()

        result = enricher.enrich_from_profile(sample_profile)

        assert isinstance(result, EnrichmentResult)
        assert result.domain == 'example.com'
        # Should extract social media from profile
        assert len(result.social_media) >= 0

    @pytest.mark.unit
    def test_calculate_contact_score_high(self):
        """Test contact score calculation - high score."""
        enricher = ContactEnricher()

        phones = [
            EnrichedContact('phone', '+1-555-1234', 0.9, 'website', {})
        ]
        whatsapp = [
            EnrichedContact('whatsapp', '+1-555-1234', 0.9, 'website', {})
        ]
        linkedin = [
            EnrichedContact('linkedin_company', 'https://linkedin.com/company/example', 0.9, 'search', {})
        ]
        social = [
            EnrichedContact('instagram', 'https://instagram.com/example', 0.9, 'search', {})
        ]

        score = enricher._calculate_contact_score(phones, whatsapp, linkedin, social)
        assert score == 'high'

    @pytest.mark.unit
    def test_calculate_contact_score_medium(self):
        """Test contact score calculation - medium score."""
        enricher = ContactEnricher()

        phones = [
            EnrichedContact('phone', '+1-555-1234', 0.9, 'website', {})
        ]
        whatsapp = []
        linkedin = []
        social = []

        score = enricher._calculate_contact_score(phones, whatsapp, linkedin, social)
        assert score == 'medium'

    @pytest.mark.unit
    def test_calculate_contact_score_low(self):
        """Test contact score calculation - low score."""
        enricher = ContactEnricher()

        score = enricher._calculate_contact_score([], [], [], [])
        assert score == 'low'

    @pytest.mark.unit
    def test_dedupe_enriched_contacts(self):
        """Test deduplication of contacts."""
        enricher = ContactEnricher()

        contacts = [
            EnrichedContact('phone', '+1-555-1234', 0.9, 'website', {}),
            EnrichedContact('phone', '+1-555-1234', 0.8, 'google', {}),  # Duplicate
            EnrichedContact('phone', '+1-555-5678', 0.9, 'website', {})
        ]

        deduped = enricher._dedupe_enriched_contacts(contacts)

        # Should keep only unique values
        assert len(deduped) == 2
        # Should keep highest confidence
        assert deduped[0].confidence == 0.9

    @pytest.mark.unit
    def test_dedupe_prefers_higher_confidence(self):
        """Test that deduplication prefers higher confidence."""
        enricher = ContactEnricher()

        contacts = [
            EnrichedContact('phone', '+1-555-1234', 0.6, 'google', {}),
            EnrichedContact('phone', '+1-555-1234', 0.9, 'website', {}),  # Higher confidence
            EnrichedContact('phone', '+1-555-1234', 0.7, 'social', {})
        ]

        deduped = enricher._dedupe_enriched_contacts(contacts)

        assert len(deduped) == 1
        assert deduped[0].confidence == 0.9
        assert deduped[0].source == 'website'

    @pytest.mark.unit
    def test_generate_notes(self):
        """Test notes generation."""
        enricher = ContactEnricher()

        phones = [EnrichedContact('phone', '+1-555-1234', 0.9, 'website', {})]
        whatsapp = [EnrichedContact('whatsapp', '+1-555-1234', 0.9, 'website', {})]
        linkedin = []
        social = []

        notes = enricher._generate_notes(phones, whatsapp, linkedin, social)

        assert 'phone' in notes.lower() or 'contact' in notes.lower()

    @pytest.mark.unit
    def test_merge_results(self):
        """Test merging enrichment results."""
        enricher = ContactEnricher()

        result1 = EnrichmentResult(
            domain='example.com',
            phones=[EnrichedContact('phone', '+1-555-1234', 0.9, 'website', {})],
            whatsapp=[],
            linkedin_profiles=[],
            social_media=[],
            contact_score='low',
            enriched_at='2025-01-01T00:00:00'
        )

        result2 = EnrichmentResult(
            domain='example.com',
            phones=[EnrichedContact('phone', '+1-555-5678', 0.8, 'google', {})],
            whatsapp=[],
            linkedin_profiles=[],
            social_media=[],
            contact_score='low',
            enriched_at='2025-01-01T00:00:00'
        )

        merged = enricher._merge_results([result1, result2])

        # Should combine phones from both results
        assert len(merged.phones) == 2


class TestEnrichmentResult:
    """Test EnrichmentResult dataclass."""

    @pytest.mark.unit
    def test_create_enrichment_result(self):
        """Test creating EnrichmentResult."""
        result = EnrichmentResult(
            domain='example.com',
            phones=[],
            whatsapp=[],
            linkedin_profiles=[],
            social_media=[],
            contact_score='low',
            enriched_at='2025-01-01T00:00:00',
            notes='Test notes'
        )

        assert result.domain == 'example.com'
        assert result.contact_score == 'low'
        assert result.notes == 'Test notes'
        assert isinstance(result.phones, list)

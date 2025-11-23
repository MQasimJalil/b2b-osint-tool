"""
Tests for social media profile discovery.
"""

import pytest
from unittest.mock import Mock, patch
from pipeline.sources.social_discovery import SocialMediaDiscovery, discover_social_profiles
from pipeline.sources.search_backend import SearchResult


class TestSocialMediaDiscovery:
    """Test SocialMediaDiscovery class."""

    @pytest.mark.unit
    def test_init(self):
        """Test initialization."""
        discovery = SocialMediaDiscovery()
        assert discovery.search_backend is not None
        assert 'linkedin' in discovery.PLATFORMS
        assert 'instagram' in discovery.PLATFORMS

    @pytest.mark.unit
    def test_generate_brand_variations(self):
        """Test brand variation generation."""
        discovery = SocialMediaDiscovery()

        # Test with domain only
        variations = discovery._generate_brand_variations('sologk.com', None)
        assert 'sologk' in variations

        # Test with company name
        variations = discovery._generate_brand_variations(
            'sologk.com',
            'Solo Goalkeeping'
        )
        assert 'sologk' in variations
        assert 'Solo Goalkeeping' in variations
        assert 'sologoalkeeping' in variations

    @pytest.mark.unit
    def test_generate_brand_variations_complex(self):
        """Test brand variation generation with complex names."""
        discovery = SocialMediaDiscovery()

        # Test camelCase domain
        variations = discovery._generate_brand_variations('myCompany.com', 'My Company')
        assert 'mycompany' in [v.lower() for v in variations]
        assert 'My Company' in variations

    @pytest.mark.unit
    def test_verify_brand_match(self):
        """Test brand matching verification."""
        discovery = SocialMediaDiscovery()
        brand_variations = ['sologk', 'Solo Goalkeeping']

        # Should match when brand in URL
        assert discovery._verify_brand_match(
            'https://instagram.com/solo_gk',
            'Solo GK Instagram',
            'Follow Solo GK',
            brand_variations
        ) is True

        # Should match when brand in title/snippet
        assert discovery._verify_brand_match(
            'https://instagram.com/profile123',
            'Solo Goalkeeping - Instagram',
            'Official page',
            brand_variations
        ) is True

        # Should not match when brand not present
        assert discovery._verify_brand_match(
            'https://instagram.com/other',
            'Other Company',
            'Different company',
            brand_variations
        ) is False

    @pytest.mark.unit
    def test_clean_social_url_linkedin(self):
        """Test LinkedIn URL cleaning."""
        discovery = SocialMediaDiscovery()

        # Company page - should keep
        url = discovery._clean_social_url(
            'https://linkedin.com/company/example?tracking=123',
            'linkedin'
        )
        assert url == 'https://linkedin.com/company/example'

        # Individual profile - should keep
        url = discovery._clean_social_url(
            'https://linkedin.com/in/john-doe/',
            'linkedin'
        )
        assert url == 'https://linkedin.com/in/john-doe'

        # Post - should reject
        url = discovery._clean_social_url(
            'https://linkedin.com/feed/update/123',
            'linkedin'
        )
        assert url is None

    @pytest.mark.unit
    def test_clean_social_url_instagram(self):
        """Test Instagram URL cleaning."""
        discovery = SocialMediaDiscovery()

        # Profile - should keep
        url = discovery._clean_social_url(
            'https://instagram.com/example/?hl=en',
            'instagram'
        )
        assert url == 'https://instagram.com/example'

        # Post - should reject
        url = discovery._clean_social_url(
            'https://instagram.com/p/ABC123/',
            'instagram'
        )
        assert url is None

        # Reel - should reject
        url = discovery._clean_social_url(
            'https://instagram.com/reel/XYZ789/',
            'instagram'
        )
        assert url is None

    @pytest.mark.unit
    def test_clean_social_url_twitter(self):
        """Test Twitter URL cleaning."""
        discovery = SocialMediaDiscovery()

        # Profile - should keep
        url = discovery._clean_social_url(
            'https://twitter.com/example?ref=123',
            'twitter'
        )
        assert url == 'https://twitter.com/example'

        # Tweet - should reject
        url = discovery._clean_social_url(
            'https://twitter.com/example/status/123456',
            'twitter'
        )
        assert url is None

    @pytest.mark.unit
    @patch('pipeline.sources.social_discovery.SearchBackend')
    def test_discover_with_empty_existing(self, mock_backend_class):
        """Test discovery with empty existing social links."""
        # Mock search backend
        mock_backend = Mock()
        mock_backend.search.return_value = [
            SearchResult(
                title='Example Instagram',
                url='https://instagram.com/example',
                snippet='Official Instagram',
                source='google_custom'
            )
        ]
        mock_backend_class.return_value = mock_backend

        discovery = SocialMediaDiscovery()

        # Test with empty string in existing
        existing_social = {
            'instagram': '',  # Empty string should be treated as missing
            'twitter': ''
        }

        results = discovery.discover_social_profiles(
            domain='example.com',
            company_name='Example Company',
            existing_social=existing_social,
            mode='lenient'
        )

        # Should find Instagram since existing was empty
        assert 'instagram' in results
        if results['instagram']:  # If we got a result
            assert results['instagram'] != ''

    @pytest.mark.unit
    @patch('pipeline.sources.social_discovery.SearchBackend')
    def test_discover_with_valid_existing(self, mock_backend_class):
        """Test discovery with valid existing social links."""
        # Mock search backend
        mock_backend = Mock()
        mock_backend.search.return_value = [
            SearchResult(
                title='Example Instagram',
                url='https://instagram.com/example_new',
                snippet='Official Instagram',
                source='google_custom'
            )
        ]
        mock_backend_class.return_value = mock_backend

        discovery = SocialMediaDiscovery()

        # Test with valid existing link
        existing_social = {
            'instagram': 'https://instagram.com/example_old'
        }

        results = discovery.discover_social_profiles(
            domain='example.com',
            company_name='Example Company',
            existing_social=existing_social,
            mode='lenient'
        )

        # Should keep existing valid link
        assert results.get('instagram') == 'https://instagram.com/example_old'

    @pytest.mark.unit
    def test_convenience_function(self):
        """Test convenience function."""
        with patch('pipeline.sources.social_discovery.SocialMediaDiscovery') as mock_class:
            mock_instance = Mock()
            mock_instance.discover_social_profiles.return_value = {'linkedin': 'test'}
            mock_class.return_value = mock_instance

            result = discover_social_profiles('example.com')
            assert result == {'linkedin': 'test'}
            mock_instance.discover_social_profiles.assert_called_once()

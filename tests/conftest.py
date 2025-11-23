"""
Pytest configuration and shared fixtures.
"""

import pytest
import os
from pathlib import Path
from typing import Dict, List


# Test data directory
TEST_DATA_DIR = Path(__file__).parent / 'test_data'


@pytest.fixture
def sample_domain():
    """Sample domain for testing."""
    return 'example.com'


@pytest.fixture
def sample_company_name():
    """Sample company name for testing."""
    return 'Example Company'


@pytest.fixture
def sample_profile():
    """Sample company profile data."""
    return {
        'domain': 'example.com',
        'company': 'Example Company',
        'emails': ['contact@example.com'],
        'social_media': {
            'linkedin': 'https://linkedin.com/company/example',
            'twitter': 'https://twitter.com/example',
            'instagram': '',  # Empty string
            'facebook': ''  # Empty string
        },
        'phones': [],
        'description': 'A sample company for testing'
    }


@pytest.fixture
def sample_search_results():
    """Sample search results."""
    from pipeline.sources.search_backend import SearchResult
    return [
        SearchResult(
            title='Example Company - LinkedIn',
            url='https://linkedin.com/company/example',
            snippet='Example Company official LinkedIn page',
            source='google_custom'
        ),
        SearchResult(
            title='Example Company (@example) - Twitter',
            url='https://twitter.com/example',
            snippet='Official Twitter account of Example Company',
            source='google_custom'
        )
    ]


@pytest.fixture
def mock_google_api_key(monkeypatch):
    """Mock Google API key environment variable."""
    monkeypatch.setenv('GOOGLE_SEARCH_KEY', 'test_api_key')
    monkeypatch.setenv('GOOGLE_SEARCH_ENGINE_ID', 'test_cx')


@pytest.fixture
def mock_no_api_keys(monkeypatch):
    """Remove all API keys from environment."""
    monkeypatch.delenv('GOOGLE_SEARCH_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_SEARCH_ENGINE_ID', raising=False)
    monkeypatch.delenv('BING_SEARCH_API_KEY', raising=False)


@pytest.fixture
def sample_linkedin_urls():
    """Sample LinkedIn URLs for testing."""
    return [
        'https://linkedin.com/company/example-company',
        'https://linkedin.com/in/john-doe-12345',
        'https://linkedin.com/in/jane-smith-67890'
    ]


@pytest.fixture
def sample_social_urls():
    """Sample social media URLs."""
    return {
        'linkedin': 'https://linkedin.com/company/example',
        'instagram': 'https://instagram.com/example',
        'twitter': 'https://twitter.com/example',
        'facebook': 'https://facebook.com/example',
        'youtube': 'https://youtube.com/@example',
        'tiktok': 'https://tiktok.com/@example'
    }


@pytest.fixture
def sample_phone_numbers():
    """Sample phone numbers for testing."""
    return [
        '+1-555-123-4567',
        '555-123-4567',
        '(555) 123-4567',
        '+44 20 7946 0958',
        'invalid-phone'
    ]


@pytest.fixture
def sample_whatsapp_numbers():
    """Sample WhatsApp numbers."""
    return [
        '+1-555-123-4567',
        'https://wa.me/15551234567',
        'https://api.whatsapp.com/send?phone=15551234567'
    ]


# Test data creation helpers

def create_test_profile(domain: str, **kwargs) -> Dict:
    """Create a test profile with custom fields."""
    profile = {
        'domain': domain,
        'company': kwargs.get('company', domain.split('.')[0].title()),
        'emails': kwargs.get('emails', []),
        'social_media': kwargs.get('social_media', {}),
        'phones': kwargs.get('phones', []),
        'description': kwargs.get('description', f'Test company for {domain}')
    }
    return profile


# Pytest markers

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "requires_api: mark test as requiring API keys"
    )
    config.addinivalue_line(
        "markers", "requires_network: mark test as requiring network access"
    )

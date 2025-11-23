"""
Tests for search backend with fallback chain.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pipeline.sources.search_backend import SearchBackend, SearchResult


class TestSearchBackend:
    """Test SearchBackend class."""

    @pytest.mark.unit
    def test_init_with_google_api(self, mock_google_api_key):
        """Test initialization with Google API key."""
        backend = SearchBackend()
        assert backend.google_api_key == 'test_api_key'
        assert backend.google_cx == 'test_cx'
        assert backend._engines_available.get('google_custom') is True

    @pytest.mark.unit
    def test_init_without_api_keys(self, mock_no_api_keys):
        """Test initialization without API keys."""
        backend = SearchBackend()
        assert backend.google_api_key is None
        assert backend.bing_api_key is None

    @pytest.mark.unit
    def test_engine_order_with_google_api(self, mock_google_api_key):
        """Test engine order when Google API is available."""
        backend = SearchBackend()
        order = backend._get_engine_order()
        # Should only use Google Custom Search when available
        assert order == ['google_custom']

    @pytest.mark.unit
    def test_engine_order_without_google_api(self, mock_no_api_keys):
        """Test engine order without Google API."""
        with patch.object(SearchBackend, '_check_google_custom', return_value=False):
            backend = SearchBackend()
            order = backend._get_engine_order()
            # Should not include DuckDuckGo
            assert 'duckduckgo' not in order
            # Should include Bing and Google scrape
            assert 'bing' in order or 'google_scrape' in order

    @pytest.mark.unit
    @patch('pipeline.sources.search_backend.requests.get')
    def test_search_google_custom(self, mock_get, mock_google_api_key):
        """Test Google Custom Search."""
        # Mock response
        mock_response = Mock()
        mock_response.json.return_value = {
            'items': [
                {
                    'title': 'Test Result',
                    'link': 'https://example.com',
                    'snippet': 'Test snippet'
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        backend = SearchBackend()
        results = backend._search_google_custom('test query', max_results=10)

        assert len(results) == 1
        assert results[0].title == 'Test Result'
        assert results[0].url == 'https://example.com'
        assert results[0].source == 'google_custom'

    @pytest.mark.unit
    def test_search_result_dataclass():
        """Test SearchResult dataclass."""
        result = SearchResult(
            title='Test',
            url='https://example.com',
            snippet='Test snippet',
            source='google_custom'
        )
        assert result.title == 'Test'
        assert result.url == 'https://example.com'
        assert result.snippet == 'Test snippet'
        assert result.source == 'google_custom'

    @pytest.mark.unit
    def test_rate_limit_detection(self):
        """Test rate limit error detection."""
        backend = SearchBackend()

        # Test various rate limit errors
        rate_limit_errors = [
            Exception('429 Too Many Requests'),
            Exception('Rate limit exceeded'),
            Exception('Quota exceeded'),
            Exception('Ratelimit')
        ]

        for error in rate_limit_errors:
            assert backend._is_rate_limit_error(error) is True

        # Test non-rate-limit error
        normal_error = Exception('Connection timeout')
        assert backend._is_rate_limit_error(normal_error) is False

    @pytest.mark.integration
    @pytest.mark.requires_api
    @pytest.mark.requires_network
    def test_real_search_with_api(self):
        """Test real search with API (requires API key)."""
        # Skip if no API key
        import os
        if not os.getenv('GOOGLE_SEARCH_KEY'):
            pytest.skip('No Google API key available')

        backend = SearchBackend()
        results = backend.search('site:linkedin.com example company', max_results=5)

        assert isinstance(results, list)
        # Should get some results
        if results:
            assert all(isinstance(r, SearchResult) for r in results)
            assert all(hasattr(r, 'url') for r in results)

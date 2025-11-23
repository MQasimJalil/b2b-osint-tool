"""
Tests for LinkedIn profile discovery.
"""

import pytest
from unittest.mock import Mock, patch
from pipeline.sources.linkedin_scraper import LinkedInDiscovery, discover_linkedin_profiles
from pipeline.sources.search_backend import SearchResult


class TestLinkedInDiscovery:
    """Test LinkedInDiscovery class."""

    @pytest.mark.unit
    def test_init(self):
        """Test initialization."""
        discovery = LinkedInDiscovery(max_results=5)
        assert discovery.max_results == 5
        assert discovery.search_backend is not None

    @pytest.mark.unit
    def test_verify_company_match(self):
        """Test company match verification."""
        discovery = LinkedInDiscovery()

        # Should match when company in URL
        assert discovery._verify_company_match(
            'https://linkedin.com/company/example-company',
            'Example Company on LinkedIn',
            'Example Company',
            'example'
        ) is True

        # Should match when domain in context
        assert discovery._verify_company_match(
            'https://linkedin.com/company/xyz',
            'example.com - LinkedIn',
            'Example Company',
            'example'
        ) is True

        # Should not match unrelated company
        assert discovery._verify_company_match(
            'https://linkedin.com/company/other',
            'Other Company',
            'Example Company',
            'example'
        ) is False

    @pytest.mark.unit
    def test_verify_employee_match(self):
        """Test employee match verification."""
        discovery = LinkedInDiscovery()

        # Should match with "at Company" pattern
        assert discovery._verify_employee_match(
            'https://linkedin.com/in/john-doe',
            'John Doe - CEO at Example Company',
            'Example Company',
            'example'
        ) is True

        # Should match with company in context
        assert discovery._verify_employee_match(
            'https://linkedin.com/in/jane-smith',
            'Jane Smith | Example Company',
            'Example Company',
            'example'
        ) is True

        # Should not match employee of different company
        assert discovery._verify_employee_match(
            'https://linkedin.com/in/bob-jones',
            'Bob Jones - CEO at Other Company',
            'Example Company',
            'example'
        ) is False

    @pytest.mark.unit
    def test_calculate_relevance_score(self):
        """Test relevance score calculation."""
        discovery = LinkedInDiscovery()

        # High relevance - company in URL and context
        score = discovery._calculate_relevance_score(
            'https://linkedin.com/company/example',
            'example company official page',
            'Example Company',
            'example'
        )
        assert score >= 0.8

        # Medium relevance - company in context only
        score = discovery._calculate_relevance_score(
            'https://linkedin.com/company/xyz',
            'example company page',
            'Example Company',
            'example'
        )
        assert 0.5 < score < 0.8

        # Low relevance - no clear match
        score = discovery._calculate_relevance_score(
            'https://linkedin.com/company/other',
            'different company',
            'Example Company',
            'example'
        )
        assert score <= 0.5

    @pytest.mark.unit
    def test_extract_name_from_url(self):
        """Test name extraction from LinkedIn URL."""
        discovery = LinkedInDiscovery()

        # Standard profile URL
        name = discovery._extract_name_from_linkedin_url(
            'https://linkedin.com/in/john-doe-12345678'
        )
        assert name == 'John Doe'

        # Profile without numbers
        name = discovery._extract_name_from_linkedin_url(
            'https://linkedin.com/in/jane-smith'
        )
        assert name == 'Jane Smith'

        # Complex name
        name = discovery._extract_name_from_linkedin_url(
            'https://linkedin.com/in/mary-ann-johnson-987'
        )
        assert name == 'Mary Ann Johnson'

        # Company URL (not a person)
        name = discovery._extract_name_from_linkedin_url(
            'https://linkedin.com/company/example'
        )
        assert name is None

    @pytest.mark.unit
    @patch('pipeline.sources.linkedin_scraper.SearchBackend')
    def test_discover_profiles_lenient(self, mock_backend_class):
        """Test profile discovery in lenient mode."""
        # Mock search backend
        mock_backend = Mock()
        mock_backend.search.return_value = [
            SearchResult(
                title='Example Company - LinkedIn',
                url='https://linkedin.com/company/example',
                snippet='Example Company official page',
                source='google_custom'
            )
        ]
        mock_backend_class.return_value = mock_backend

        discovery = LinkedInDiscovery()
        results = discovery.discover_profiles(
            domain='example.com',
            company_name='Example Company',
            mode='lenient'
        )

        # In lenient mode, should only find company pages
        assert 'company_pages' in results
        assert 'employee_profiles' in results
        assert len(results['employee_profiles']) == 0

    @pytest.mark.unit
    @patch('pipeline.sources.linkedin_scraper.SearchBackend')
    def test_discover_profiles_aggressive(self, mock_backend_class):
        """Test profile discovery in aggressive mode."""
        # Mock search backend
        mock_backend = Mock()

        def mock_search(query, max_results):
            if 'company' in query:
                return [
                    SearchResult(
                        title='Example Company - LinkedIn',
                        url='https://linkedin.com/company/example',
                        snippet='Example Company official page',
                        source='google_custom'
                    )
                ]
            else:  # Employee search
                return [
                    SearchResult(
                        title='John Doe - CEO at Example Company',
                        url='https://linkedin.com/in/john-doe',
                        snippet='CEO at Example Company',
                        source='google_custom'
                    )
                ]

        mock_backend.search.side_effect = mock_search
        mock_backend_class.return_value = mock_backend

        discovery = LinkedInDiscovery()
        results = discovery.discover_profiles(
            domain='example.com',
            company_name='Example Company',
            mode='aggressive'
        )

        # In aggressive mode, should find both company and employees
        assert 'company_pages' in results
        assert 'employee_profiles' in results

    @pytest.mark.unit
    @patch('pipeline.sources.linkedin_scraper.SearchBackend')
    def test_employee_limit(self, mock_backend_class):
        """Test that employee results are limited to 3."""
        # Mock search backend with many results
        mock_backend = Mock()

        # Create 10 employee results
        employee_results = []
        for i in range(10):
            employee_results.append(
                SearchResult(
                    title=f'Person {i} - Example Company',
                    url=f'https://linkedin.com/in/person-{i}',
                    snippet=f'Employee at Example Company',
                    source='google_custom'
                )
            )

        def mock_search(query, max_results):
            if 'company' in query:
                return []
            else:
                return employee_results

        mock_backend.search.side_effect = mock_search
        mock_backend_class.return_value = mock_backend

        discovery = LinkedInDiscovery()
        results = discovery.discover_profiles(
            domain='example.com',
            company_name='Example Company',
            mode='aggressive'
        )

        # Should only return top 3 employees
        assert len(results['employee_profiles']) <= 3

    @pytest.mark.unit
    def test_convenience_function(self):
        """Test convenience function."""
        with patch('pipeline.sources.linkedin_scraper.LinkedInDiscovery') as mock_class:
            mock_instance = Mock()
            mock_instance.discover_profiles.return_value = {'company_pages': [], 'employee_profiles': []}
            mock_class.return_value = mock_instance

            result = discover_linkedin_profiles('example.com')
            assert 'company_pages' in result
            assert 'employee_profiles' in result
            mock_instance.discover_profiles.assert_called_once()

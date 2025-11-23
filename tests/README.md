# Testing Guide

## Overview

This directory contains comprehensive tests for the B2B OSINT Tool using pytest.

## Test Structure

```
tests/
├── conftest.py                    # Pytest configuration and fixtures
├── test_search_backend.py         # Search backend tests
├── test_social_discovery.py       # Social media discovery tests
├── test_linkedin_scraper.py       # LinkedIn scraper tests
├── test_contact_validators.py     # Contact validation tests
├── test_contact_enricher.py       # Contact enrichment tests
└── README.md                      # This file
```

## Installation

Install development dependencies:

```bash
pip install -r requirements-dev.txt
```

## Running Tests

### Run all tests
```bash
pytest
```

### Run with verbose output
```bash
pytest -v
```

### Run specific test file
```bash
pytest tests/test_search_backend.py
```

### Run specific test class
```bash
pytest tests/test_search_backend.py::TestSearchBackend
```

### Run specific test function
```bash
pytest tests/test_search_backend.py::TestSearchBackend::test_init_with_google_api
```

### Run tests by marker
```bash
# Unit tests only
pytest -m unit

# Integration tests only
pytest -m integration

# Skip slow tests
pytest -m "not slow"

# Skip tests requiring API keys
pytest -m "not requires_api"

# Skip tests requiring network
pytest -m "not requires_network"
```

## Test Markers

- `@pytest.mark.unit` - Unit tests (fast, no external dependencies)
- `@pytest.mark.integration` - Integration tests (may require external services)
- `@pytest.mark.slow` - Slow running tests
- `@pytest.mark.requires_api` - Tests requiring API keys
- `@pytest.mark.requires_network` - Tests requiring network access

## Coverage

### Run tests with coverage report
```bash
pytest --cov=pipeline --cov-report=html --cov-report=term
```

### View HTML coverage report
```bash
# Open in browser
start htmlcov/index.html  # Windows
open htmlcov/index.html   # macOS
xdg-open htmlcov/index.html  # Linux
```

## Writing Tests

### Test Naming Convention

- Test files: `test_*.py`
- Test classes: `Test*`
- Test functions: `test_*`

### Example Test

```python
import pytest
from pipeline.sources.search_backend import SearchBackend

class TestMyFeature:
    """Test my feature."""

    @pytest.mark.unit
    def test_something(self):
        """Test something specific."""
        # Arrange
        backend = SearchBackend()

        # Act
        result = backend.do_something()

        # Assert
        assert result is not None
```

### Using Fixtures

```python
@pytest.mark.unit
def test_with_fixture(sample_domain, sample_company_name):
    """Test using fixtures from conftest.py."""
    assert sample_domain == 'example.com'
    assert sample_company_name == 'Example Company'
```

### Mocking External Services

```python
from unittest.mock import Mock, patch

@pytest.mark.unit
@patch('pipeline.sources.search_backend.requests.get')
def test_with_mock(mock_get):
    """Test with mocked HTTP requests."""
    # Setup mock
    mock_response = Mock()
    mock_response.json.return_value = {'result': 'success'}
    mock_get.return_value = mock_response

    # Test code here
    # ...
```

## Continuous Integration

Tests can be integrated with CI/CD pipelines:

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: pytest -m "not requires_api and not requires_network"
```

## Best Practices

1. **Keep tests fast** - Use mocks for external services
2. **Test one thing** - Each test should verify one behavior
3. **Use descriptive names** - Test names should explain what they test
4. **Arrange-Act-Assert** - Structure tests clearly
5. **Use fixtures** - Reuse common test data
6. **Mark appropriately** - Use markers for test categorization
7. **Mock external calls** - Don't hit real APIs in unit tests

## Troubleshooting

### Tests fail with import errors
```bash
# Make sure you're in the project root
cd D:\Raqim\b2b_osint_tool

# Install in development mode
pip install -e .
```

### Tests requiring API keys fail
```bash
# Set environment variables
export GOOGLE_SEARCH_KEY=your_key
export GOOGLE_SEARCH_ENGINE_ID=your_cx

# Or skip these tests
pytest -m "not requires_api"
```

### Coverage report not generated
```bash
# Install pytest-cov
pip install pytest-cov

# Run with coverage
pytest --cov=pipeline --cov-report=html
```

## Next Steps

- Add more test cases for edge cases
- Increase test coverage to 90%+
- Add integration tests with real API calls (gated by environment variables)
- Add performance/benchmark tests
- Add end-to-end tests

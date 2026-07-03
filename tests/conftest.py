import pytest


@pytest.fixture(autouse=True)
def _dummy_anthropic_key(monkeypatch):
    """Every agent constructor needs an API key to build its client.
    No network call is made; a placeholder is enough for unit tests."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

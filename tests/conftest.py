import pytest


@pytest.fixture(autouse=True)
def no_raw_log_dir(monkeypatch):
    """A shell-exported OER_RAW_LOG_DIR must not collect output from unit tests."""
    monkeypatch.delenv("OER_RAW_LOG_DIR", raising=False)

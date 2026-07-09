"""Tests for core/rate_limiter.py — forces memory path via monkeypatching."""
import time
import pytest
from unittest.mock import patch


def _make_limiter():
    """Fresh import of rate_limiter with clean module state."""
    import importlib
    import core.rate_limiter as rl
    importlib.reload(rl)
    return rl


@pytest.fixture(autouse=True)
def patch_db_and_key(monkeypatch):
    """Force memory path (DB returns None) and fix the client key."""
    monkeypatch.setattr("core.rate_limiter._db_check_and_record", lambda *a, **kw: None)
    monkeypatch.setattr("core.rate_limiter._client_key", lambda: "test:fixed-ip")


def test_under_limit_allows():
    import importlib
    import core.rate_limiter as rl
    importlib.reload(rl)
    with patch.object(rl, "_db_check_and_record", return_value=None), \
         patch.object(rl, "_client_key", return_value="test:ip1"):
        for _ in range(5):
            assert rl.is_rate_limited(max_requests_per_minute=10) is False


def test_over_limit_blocks():
    import importlib
    import core.rate_limiter as rl
    importlib.reload(rl)
    with patch.object(rl, "_db_check_and_record", return_value=None), \
         patch.object(rl, "_client_key", return_value="test:ip2"):
        for _ in range(3):
            rl.is_rate_limited(max_requests_per_minute=3)
        assert rl.is_rate_limited(max_requests_per_minute=3) is True


def test_different_keys_isolated():
    import importlib
    import core.rate_limiter as rl
    importlib.reload(rl)
    with patch.object(rl, "_db_check_and_record", return_value=None):
        with patch.object(rl, "_client_key", return_value="test:ip_a"):
            for _ in range(3):
                rl.is_rate_limited(max_requests_per_minute=3)
            assert rl.is_rate_limited(max_requests_per_minute=3) is True
        # Different key should still be allowed
        with patch.object(rl, "_client_key", return_value="test:ip_b"):
            assert rl.is_rate_limited(max_requests_per_minute=3) is False


def test_window_expiry_reallows():
    import importlib
    import core.rate_limiter as rl
    importlib.reload(rl)
    with patch.object(rl, "_db_check_and_record", return_value=None), \
         patch.object(rl, "_client_key", return_value="test:ip3"):
        # Fill up the limit
        for _ in range(2):
            rl.is_rate_limited(max_requests_per_minute=2)
        assert rl.is_rate_limited(max_requests_per_minute=2) is True
        # Simulate time passing — backdating the timestamps
        import core.rate_limiter as rl2
        key = "test:ip3"
        with rl2._mem_lock:
            dq = rl2._mem_store.get(key)
            if dq:
                old_ts = time.monotonic() - 61
                for i in range(len(dq)):
                    dq[i] = old_ts
        # Now should be allowed again
        assert rl.is_rate_limited(max_requests_per_minute=2) is False


def test_db_verdict_takes_precedence():
    import importlib
    import core.rate_limiter as rl
    importlib.reload(rl)
    # DB says True (rate limited) — should return True regardless of memory
    with patch.object(rl, "_db_check_and_record", return_value=True), \
         patch.object(rl, "_client_key", return_value="test:ip4"):
        assert rl.is_rate_limited(max_requests_per_minute=100) is True
    # DB says False (allowed) — should return False
    with patch.object(rl, "_db_check_and_record", return_value=False), \
         patch.object(rl, "_client_key", return_value="test:ip5"):
        assert rl.is_rate_limited(max_requests_per_minute=100) is False

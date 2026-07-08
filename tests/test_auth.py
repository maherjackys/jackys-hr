"""Tests for the ADMIN_PASSWORD fallback security fix (FIX H2).

Scenarios:
1. Unknown username + correct legacy secret → REJECTED (no master-password bypass)
2. username=admin + correct legacy secret when no DB row exists → migrates once, returns True
3. After migration, admin row exists → bcrypt path used, plain-text fallback never reached
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Test 1 — unknown username + correct legacy secret → rejected
# ---------------------------------------------------------------------------

def test_unknown_username_with_legacy_secret_is_rejected():
    import core.auth as auth

    with (
        patch.object(auth, "get_admin_user", return_value=None),
        patch.object(auth, "_get_secret", return_value="S3cret"),
        patch.object(auth, "_record_failure"),
        patch.object(auth, "_log_login"),
        patch.object(auth, "_is_locked_out", return_value=(False, 0)),
    ):
        # note: check_login(password, username)
        ok, msg = auth.check_login("S3cret", "hacker")

    assert ok is False, "Unknown username must not authenticate via legacy secret"
    assert "Incorrect" in msg


# ---------------------------------------------------------------------------
# Test 2 — admin + legacy secret with no DB row → migrates once, returns True
# ---------------------------------------------------------------------------

def test_admin_legacy_secret_migrates_when_no_row():
    import core.auth as auth

    db_mock = MagicMock()

    with (
        patch.object(auth, "get_admin_user", return_value=None),  # no row yet
        patch.object(auth, "_get_secret", return_value="S3cret"),
        patch.object(auth, "_db", return_value=db_mock),
        patch.object(auth, "_record_failure"),
        patch.object(auth, "_clear_failures"),
        patch.object(auth, "_update_last_login"),
        patch.object(auth, "_log_login"),
        patch.object(auth, "_is_locked_out", return_value=(False, 0)),
    ):
        ok, msg = auth.check_login("S3cret", "admin")

    assert ok is True, "admin + correct legacy secret should succeed when no DB row"
    # Verify upsert was called with username="admin"
    call_args = db_mock.table.return_value.upsert.call_args[0][0]
    assert call_args["username"] == "admin"
    assert call_args["role"] == "super_admin"


# ---------------------------------------------------------------------------
# Test 3 — after migration admin row exists → bcrypt path, no plain-text check
# ---------------------------------------------------------------------------

def test_admin_after_migration_uses_bcrypt_path():
    import core.auth as auth

    hashed = auth.hash_password("S3cret")
    admin_row = {
        "username": "admin",
        "password_hash": hashed,
        "role": "super_admin",
        "is_active": True,
    }

    get_secret_mock = MagicMock(return_value="S3cret")

    with (
        patch.object(auth, "get_admin_user", return_value=admin_row),
        patch.object(auth, "_get_secret", get_secret_mock),
        patch.object(auth, "_record_failure"),
        patch.object(auth, "_clear_failures"),
        patch.object(auth, "_update_last_login"),
        patch.object(auth, "_log_login"),
        patch.object(auth, "_is_locked_out", return_value=(False, 0)),
    ):
        ok, msg = auth.check_login("S3cret", "admin")

    assert ok is True, "admin should authenticate via bcrypt after migration"
    # _get_secret should NOT have been called — bcrypt path resolves before fallback
    get_secret_mock.assert_not_called()

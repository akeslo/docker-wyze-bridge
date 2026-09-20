import threading
from unittest import mock

from wyzebridge.wyze_api import WyzeApi, authenticated
from wyzecam.api import AccessTokenError


def _bare_api():
    """A WyzeApi with __init__ skipped, so no env/secret/disk access happens."""
    api = WyzeApi.__new__(WyzeApi)
    api.auth = mock.Mock()
    api.creds = mock.Mock()
    api._last_pull = 0
    api._last_auth_attempt = 0
    api._auth_lock = threading.Lock()
    return api


def test_authenticated_retries_once_then_raises_on_repeated_token_error():
    """Regression test for the infinite-loop hang documented in findings.md:
    an AccessTokenError used to be able to retry forever if refresh_token()
    never cleared the underlying condition. The decorator must retry exactly
    once (via the internal _retried flag) and then propagate."""
    api = _bare_api()

    calls = {"n": 0}

    @authenticated
    def flaky(self):
        calls["n"] += 1
        raise AccessTokenError("expired")

    with mock.patch.object(WyzeApi, "refresh_token") as refresh_mock:
        try:
            flaky(api)
            assert False, "expected AccessTokenError to propagate after one retry"
        except AccessTokenError:
            pass

    assert calls["n"] == 2, "should call the wrapped function exactly twice (original + 1 retry)"
    refresh_mock.assert_called_once()


def test_authenticated_succeeds_after_single_refresh():
    api = _bare_api()

    calls = {"n": 0}

    @authenticated
    def recovers(self):
        calls["n"] += 1
        if calls["n"] == 1:
            raise AccessTokenError("expired")
        return "ok"

    with mock.patch.object(WyzeApi, "refresh_token") as refresh_mock:
        assert recovers(api) == "ok"

    assert calls["n"] == 2
    refresh_mock.assert_called_once()


def test_authenticated_logs_in_when_no_auth_present():
    api = _bare_api()
    api.auth = None

    @authenticated
    def should_not_run(self):
        raise AssertionError("wrapped function must not run without auth")

    with mock.patch.object(WyzeApi, "login", return_value=False) as login_mock:
        assert should_not_run(api) is None

    login_mock.assert_called_once()


def test_check_auth_lock_rate_limits_within_window():
    api = _bare_api()
    assert api.check_auth_lock() is False, "first call should not be rate-limited"
    assert api.check_auth_lock() is True, "immediate second call should be rate-limited"


def test_check_auth_lock_update_false_does_not_arm_the_window():
    api = _bare_api()
    assert api.check_auth_lock(update=False) is False
    assert api.check_auth_lock(update=False) is False, "update=False must never arm the rate limit"


def test_refresh_token_short_circuits_when_rate_limited():
    """refresh_token() must not call the network refresh_token() helper while
    check_auth_lock() says a refresh was just attempted."""
    api = _bare_api()

    with (
        mock.patch.object(WyzeApi, "check_auth_lock", return_value=True),
        mock.patch("wyzebridge.wyze_api.refresh_token") as net_refresh,
    ):
        result = api.refresh_token()

    net_refresh.assert_not_called()
    assert result is api.auth


def test_refresh_token_falls_back_to_login_outside_the_lock_on_failure():
    """When the network refresh raises, refresh_token() must fall back to
    login() only AFTER releasing _auth_lock — calling it while still holding
    the lock is exactly the deadlock findings.md warns about (a concurrent
    thread's refresh_token() would wedge forever waiting on the same lock)."""
    api = _bare_api()

    lock_held_during_login = {"value": None}

    def fake_login(self, fresh_data=False):
        lock_held_during_login["value"] = api._auth_lock.locked()
        return "logged-in"

    with (
        mock.patch.object(WyzeApi, "check_auth_lock", return_value=False),
        mock.patch.object(WyzeApi, "login", side_effect=fake_login, autospec=True),
        mock.patch("wyzebridge.wyze_api.refresh_token", side_effect=RuntimeError("boom")),
    ):
        result = api.refresh_token()

    assert result == "logged-in"
    assert lock_held_during_login["value"] is False, "login() must run outside _auth_lock"

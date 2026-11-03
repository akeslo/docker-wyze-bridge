from unittest import mock

import pytest
from flask import Flask
from werkzeug.security import generate_password_hash

from wyzebridge import web_ui


@pytest.fixture
def app():
    return Flask(__name__)


@pytest.fixture
def wb_auth(monkeypatch):
    auth = mock.Mock()
    auth.api = "secret-api"
    auth.username = "user"
    auth.enabled = True
    auth.hashed_password.return_value = generate_password_hash("pw")
    monkeypatch.setattr(web_ui, "WbAuth", auth)
    monkeypatch.setattr(web_ui, "HASS_TOKEN", "")
    return auth


def _verify(app, path, username=None, password=None, headers=None, remote="1.2.3.4", query=""):
    with app.test_request_context(
        path + query, headers=headers or {}, environ_base={"REMOTE_ADDR": remote}
    ):
        return web_ui.verify_password(username, password)


@pytest.mark.parametrize("path", ["/api/x", "/img/a.jpg", "/snapshot/a", "/thumb/a", "/photo/a", "/signaling/cam"])
def test_api_key_allowed_on_machine_endpoints(app, wb_auth, path):
    assert _verify(app, path, headers={"api": "secret-api"})


def test_signaling_is_in_allowlist():
    assert "/signaling" in web_ui.API_ENDPOINTS


def test_api_key_rejected_on_non_api_paths(app, wb_auth):
    assert not _verify(app, "/settings", headers={"api": "secret-api"})


def test_api_key_via_query_arg(app, wb_auth):
    assert _verify(app, "/api/x", query="?api=secret-api")


def test_hass_ingress_ip_bypass(app, wb_auth, monkeypatch):
    monkeypatch.setattr(web_ui, "HASS_TOKEN", "tok")
    assert _verify(app, "/settings", remote="172.30.32.2")
    assert not _verify(app, "/settings", remote="9.9.9.9")


def test_password_fallback(app, wb_auth):
    assert _verify(app, "/", username="user", password="pw")
    assert not _verify(app, "/", username="user", password="bad")


def test_auth_disabled_allows_anonymous(app, wb_auth):
    wb_auth.enabled = False
    assert _verify(app, "/")


def test_auth_enabled_rejects_anonymous(app, wb_auth):
    assert not _verify(app, "/")

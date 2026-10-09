import json
from unittest import mock

import pytest

from wyzebridge import hass


@pytest.fixture
def options(tmp_path, monkeypatch):
    def _write(conf):
        path = tmp_path / "options.json"
        path.write_text(json.dumps(conf))
        real_open = open

        def fake_open(file, *a, **kw):
            if file == "/data/options.json":
                return real_open(path, *a, **kw)
            return real_open(file, *a, **kw)

        monkeypatch.setattr("builtins.open", fake_open)

    return _write


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # setup_hass writes straight into os.environ; restore it after each test.
    monkeypatch.setattr(hass, "environ", hass.environ.copy())


def _resp(payload):
    r = mock.Mock()
    r.json.return_value = payload
    return r


def test_no_token_is_noop(monkeypatch):
    get = mock.Mock()
    monkeypatch.setattr(hass.requests, "get", get)
    hass.setup_hass(None)
    get.assert_not_called()


def test_both_supervisor_calls_use_timeout(options, monkeypatch):
    options({})
    get = mock.Mock(return_value=_resp({}))
    monkeypatch.setattr(hass.requests, "get", get)
    hass.setup_hass("tok")
    assert get.call_count == 2
    for call in get.call_args_list:
        assert call.kwargs["timeout"] == hass.SUPERVISOR_TIMEOUT


def test_network_failure_does_not_block_mqtt_lookup(options, monkeypatch):
    options({"MQTT": True})
    mqtt = {
        "result": "ok",
        "data": {"host": "h", "port": 1883, "username": "u", "password": "p"},
    }

    def fake_get(url, **kw):
        if "network" in url:
            raise TimeoutError("no answer")
        return _resp(mqtt)

    monkeypatch.setattr(hass.requests, "get", fake_get)
    hass.setup_hass("tok")
    assert hass.environ["MQTT_HOST"] == "h:1883"
    assert hass.environ["MQTT_AUTH"] == "u:p"


def test_mqtt_failure_is_swallowed(options, monkeypatch):
    options({})

    def fake_get(url, **kw):
        if "mqtt" in url:
            raise ConnectionError("down")
        return _resp({"data": {"interfaces": []}})

    monkeypatch.setattr(hass.requests, "get", fake_get)
    hass.setup_hass("tok")
    assert "MQTT_HOST" not in hass.environ


def test_wb_ip_from_primary_interface(options, monkeypatch):
    options({})
    net = {
        "data": {
            "interfaces": [
                {"primary": False, "ipv4": {"address": ["1.1.1.1/24"]}},
                {"primary": True, "ipv4": {"address": ["10.0.0.5/24"]}},
            ]
        }
    }
    monkeypatch.setattr(hass.requests, "get", lambda url, **kw: _resp(net))
    hass.setup_hass("tok")
    assert hass.environ["WB_IP"] == "10.0.0.5"


def test_configured_wb_ip_wins_over_supervisor_network(options, monkeypatch):
    options({"WB_IP": "9.9.9.9"})
    net = {
        "data": {
            "interfaces": [{"primary": True, "ipv4": {"address": ["10.0.0.5/24"]}}]
        }
    }
    monkeypatch.setattr(hass.requests, "get", lambda url, **kw: _resp(net))
    hass.setup_hass("tok")
    assert hass.environ["WB_IP"] == "9.9.9.9"

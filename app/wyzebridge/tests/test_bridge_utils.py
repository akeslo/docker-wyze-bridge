import pytest

from wyzebridge.bridge_utils import env_bool, env_cam


@pytest.mark.parametrize("raw", ["", "no", "None", "FALSE", "  false  ", "'false'"])
def test_env_bool_falsey_values_return_default(monkeypatch, raw):
    monkeypatch.setenv("WB_TEST", raw)
    assert env_bool("WB_TEST") == ""
    assert env_bool("WB_TEST", false="dflt") == "dflt"
    assert env_bool("WB_TEST", style="bool") is False


def test_env_bool_unset_uses_default(monkeypatch):
    monkeypatch.delenv("WB_TEST", raising=False)
    assert env_bool("WB_TEST", false="x") == "x"


def test_env_bool_strips_quotes_and_lowercases(monkeypatch):
    monkeypatch.setenv("WB_TEST", "'Hello'")
    assert env_bool("WB_TEST") == "hello"
    assert env_bool("WB_TEST", style="original") == "Hello"
    assert env_bool("WB_TEST", style="upper") == "HELLO"


def test_env_bool_true_value(monkeypatch):
    monkeypatch.setenv("WB_TEST", "yes")
    assert env_bool("WB_TEST", true="on") == "on"
    assert env_bool("WB_TEST", style="bool") is True


def test_env_bool_dash_name_maps_to_underscore(monkeypatch):
    monkeypatch.setenv("WB_DASH_NAME", "1")
    assert env_bool("wb-dash-name", style="bool") is True


def test_env_bool_int_style(monkeypatch):
    monkeypatch.setenv("WB_TEST", "24h")
    assert env_bool("WB_TEST", style="int") == 24
    monkeypatch.delenv("WB_TEST")
    assert env_bool("WB_TEST", false=5, style="int") == 5
    assert env_bool("WB_TEST", style="int") == 0


def test_env_bool_float_style(monkeypatch):
    monkeypatch.setenv("WB_TEST", "1.5")
    assert env_bool("WB_TEST", style="float") == 1.5
    monkeypatch.setenv("WB_TEST", "abc")
    assert env_bool("WB_TEST", false=2, style="float") == 2.0


def test_env_cam_precedence(monkeypatch):
    for k in ("SNAP", "SNAP_ALL", "SNAP_CAM1"):
        monkeypatch.delenv(k, raising=False)
    assert env_cam("SNAP", "cam1", default="d") == "d"
    monkeypatch.setenv("SNAP_ALL", "all")
    assert env_cam("SNAP", "cam1", default="d") == "all"
    monkeypatch.setenv("SNAP", "global")
    assert env_cam("SNAP", "cam1", default="d") == "global"
    monkeypatch.setenv("SNAP_CAM1", "specific")
    assert env_cam("SNAP", "cam1", default="d") == "specific"
    assert env_cam("SNAP", "cam2", default="d") == "global"

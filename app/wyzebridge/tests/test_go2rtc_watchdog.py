from unittest import mock

from wyzebridge.go2rtc_server import Go2RtcServer, API_FAIL_THRESHOLD


def _server_with_streams(streams):
    server = Go2RtcServer()
    for uri in streams:
        server._stream_fail_counts[uri] = 0
    server.sub_process = mock.Mock()
    server.sub_process.poll.return_value = None  # process is "running"
    server._last_health_check = 0  # force the interval gate to pass
    return server


def test_api_failure_does_not_restart_before_threshold(monkeypatch):
    server = _server_with_streams(["cam1"])
    monkeypatch.setattr(Go2RtcServer, "get_streams_status", lambda self: None)
    restart_mock = mock.Mock()
    monkeypatch.setattr(Go2RtcServer, "restart_process", restart_mock)

    for _ in range(API_FAIL_THRESHOLD - 1):
        server._last_health_check = 0
        server.health_check_streams()

    restart_mock.assert_not_called()
    assert server._api_fail_count == API_FAIL_THRESHOLD - 1


def test_api_failure_restarts_process_after_threshold(monkeypatch):
    server = _server_with_streams(["cam1"])
    monkeypatch.setattr(Go2RtcServer, "get_streams_status", lambda self: None)
    restart_mock = mock.Mock()
    monkeypatch.setattr(Go2RtcServer, "restart_process", restart_mock)

    for _ in range(API_FAIL_THRESHOLD):
        server._last_health_check = 0
        server.health_check_streams()

    restart_mock.assert_called_once()


def test_api_recovery_resets_fail_count(monkeypatch):
    server = _server_with_streams(["cam1"])
    server._api_fail_count = API_FAIL_THRESHOLD - 1

    monkeypatch.setattr(
        Go2RtcServer,
        "get_streams_status",
        lambda self: {"cam1": {"producers": [{}], "consumers": []}},
    )
    server._last_health_check = 0
    server.health_check_streams()

    assert server._api_fail_count == 0


def test_restart_process_stops_and_starts_and_resets_stream_counts(monkeypatch):
    server = _server_with_streams(["cam1", "cam2"])
    server._stream_fail_counts["cam1"] = 2
    stop_mock = mock.Mock()
    start_mock = mock.Mock()
    monkeypatch.setattr(Go2RtcServer, "stop", stop_mock)
    monkeypatch.setattr(Go2RtcServer, "start", start_mock)

    server.restart_process()

    stop_mock.assert_called_once()
    start_mock.assert_called_once()
    assert server._stream_fail_counts == {"cam1": 0, "cam2": 0}


def test_process_not_running_skips_health_check_entirely(monkeypatch):
    server = _server_with_streams(["cam1"])
    server.sub_process.poll.return_value = 1  # process has exited
    get_streams_mock = mock.Mock()
    monkeypatch.setattr(Go2RtcServer, "get_streams_status", get_streams_mock)

    server.health_check_streams()

    get_streams_mock.assert_not_called()

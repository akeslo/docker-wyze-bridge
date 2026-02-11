# Progress Log - Camera Connection Issues

- Initialized planning files.
- Searched codebase for "reconnect", "timeout", "disconnect".
- Identified potential issue in `webrtc_stream.py` with the 10-reconnect limit (later found to be dead code).
- Analyzed `WyzeApi` and identified an infinite loop vulnerability in `@authenticated` combined with `auth_locked`.
- Discovered missing timeouts in `requests` calls in `wyzecam/api.py`.
- Discovered that `go2rtc` and `SnapshotManager` were not monitored for crashes.
- Implemented `_auth_lock` in `WyzeApi` to handle concurrent refreshes safely.
- Fixed `@authenticated` to prevent infinite loops during token expiration.
- Converted `auth_locked` property to a `check_auth_lock()` method to remove side-effects.
- Added 30s timeouts to all Wyze API requests.
- Added a watchdog loop in `WyzeBridge.run()` to restart `go2rtc` and `SnapshotManager` if they die.
- Verified syntax of all modified files.
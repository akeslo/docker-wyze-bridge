# Findings - Camera Connection Issues

## Discoveries
- **Infinite Loop in Auth:** The `@authenticated` decorator in `wyze_api.py` could enter a tight infinite loop if a token expired and `refresh_token` was skipped due to the `auth_locked` property. This would hang Flask worker threads and spike CPU usage.
- **Hanging Requests:** `wyzecam/api.py` was missing timeouts on all `requests` calls, which could cause threads to hang indefinitely if the Wyze API was slow or unreachable.
- **Missing Watchdog:** `go2rtc` and `SnapshotManager` were started once but never monitored. If they crashed, they remained dead until the container was rebooted.
- **Dead Code:** `webrtc_stream.py` and `stream_manager.py` are legacy components not used by the current `go2rtc`-based implementation.

## Root Cause Analysis
The "reboot every few days" requirement was likely due to the combination of token expiration (every 24h) and the infinite loop/hanging request issues. When a token expired, concurrent requests for signaling or snapshots would trigger the auth loop or hang the Flask workers, eventually making the entire bridge unresponsive.

## Fixes Implemented
- Added `threading.Lock` to `WyzeApi` for thread-safe authentication.
- Added retry limit to `@authenticated` to break infinite loops.
- Added 30s timeouts to all Wyze API calls.
- Implemented a watchdog in `WyzeBridge.run()` to monitor and restart subprocesses.
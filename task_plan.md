# Task: Investigate camera connection drops and fix reconnection logic

## Goal
Understand why camera connections drop after a few days and require a container reboot, and implement a robust reconnection strategy.

## Status
- [x] Phase 1: Root Cause Investigation — see findings.md (infinite auth loop, missing request timeouts, no subprocess watchdog).
    - [x] Analyze logs for connection drop patterns (if available).
    - [x] Audit `webrtc_stream.py` reconnection logic — dead code in production, superseded by go2rtc; kept only because `test_turn_reconnect.py` still imports it.
    - [x] Check for resource leaks (memory, threads, file descriptors).
- [x] Phase 2: Pattern Analysis
    - [x] Compare with other streaming implementations in the codebase.
    - [x] Identify if the 10-attempt limit is the primary cause — not the primary cause; root cause was the auth infinite-loop/hang combo (see findings.md Root Cause Analysis).
- [x] Phase 3: Hypothesis and Testing
    - [x] Test if resetting the reconnect counter or increasing the limit helps — superseded by the go2rtc-level watchdog (0b802e8, 76a77d5) rather than tuning the counter.
    - [x] Test if credentials expire and aren't being refreshed — confirmed as a contributing factor (24h token expiry compounding the auth lock issue).
- [x] Phase 4: Implementation
    - [x] Implement improved reconnection logic — `WyzeApi` threading.Lock + retry limit, 30s API timeouts, go2rtc process/stream watchdog (0b802e8, 76a77d5).
    - [x] Verify fix with long-running tests (if possible) or simulated failures — `test_go2rtc_watchdog.py` added alongside the escalation fix.

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| | | |

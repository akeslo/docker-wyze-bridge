# Task: Investigate camera connection drops and fix reconnection logic

## Goal
Understand why camera connections drop after a few days and require a container reboot, and implement a robust reconnection strategy.

## Status
- [ ] Phase 1: Root Cause Investigation
    - [ ] Analyze logs for connection drop patterns (if available).
    - [ ] Audit `webrtc_stream.py` reconnection logic.
    - [ ] Check for resource leaks (memory, threads, file descriptors).
- [ ] Phase 2: Pattern Analysis
    - [ ] Compare with other streaming implementations in the codebase.
    - [ ] Identify if the 10-attempt limit is the primary cause.
- [ ] Phase 3: Hypothesis and Testing
    - [ ] Test if resetting the reconnect counter or increasing the limit helps.
    - [ ] Test if credentials expire and aren't being refreshed.
- [ ] Phase 4: Implementation
    - [ ] Implement improved reconnection logic.
    - [ ] Verify fix with long-running tests (if possible) or simulated failures.

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| | | |

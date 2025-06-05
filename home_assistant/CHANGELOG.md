# What's Changed

## What's Changed in v3.10.14

- Made MQTT config value optional Fixes #39
- Fix MQTT parameters minimum value for bitrate and fps
- Don't emit MQTT state messages unless the state has changed
- Fix warning in  BOA check
- Add missing OFFLINE_TIME and DOMAIN options
- Added documentation of the option defaults.

## What's Changed in v3.10.13

- Fix schema for MQTT discovery messages

## What's Changed in v3.10.12

- Filled out the missing translations and docs
- Fix busted device configuration table (the device.json file had some XML in it)
- Fix bad handling of WYZEDB3 message protocol support
- Clean up wyzecam to adopt original upstream MAIN fixes
- Sync with upstream wysecam DEV branch
- Fix sleep when no data is ready (was waiting 0 seconds instead of the intended 1/80th of a second)
- Yield frame_info in the receive data iterations.
- Decode both FrameInfoStruct OR FrameInfo3Struct and whine if something is wrong.
- Don't discard messages without an expected_response_code as we know what it's supposed to be anyway.
- Proper type, use literals, better logging, eliminate dead code
- Remove exit logging
- Revert type of resend and remove redundant SDK license set
- Add resp so debug structure are visible

## What's Changed in v3.10.11

- Fix errors in startup avClientStartEx doesn't return a tuple
- Fix path construction for MediaMTX
- Fix python lint warnings and a whole lot of logging and type cleanup
- Move environment stuff to config and config reading out of mtx_server
- Don't complain about directories existing in migration
- Attempt to ensure directories for recordings
- Capture stdout of MediaMTX and openssl for logging
- Capture the traceback before context corrupted
- Switched to better logging syntax
- Let's declare the ports we EXPOSE in the Dockerfile(s)

## What's Changed in v3.10.10

- Add camera IP to MQTT message
- Adjust the recording path construction more
- Added STUN_SERVER support
- Switched all home assistant configs to host_network
- Don't default WB_AUTH nor MQTT on and don't force the MQTT_TOPIC
- Restored the fps to the K10056SetResolvingBit message
- Lots more logging to help track down the recording issue
- Cleanup a bunch of Python warnings
- Bump MediaMTX to 1.12.3
- Bump Wyze app version to 3.5.5.8
- Don't force MediaMTX logging level to info
- Better tagging for Docker images
- Unified more the normal/hardware/multiarch docker build files
- Add devcontainer.json and tasks.json for VSCode

## What's Changed in v3.10.9

- Revert tutk_protocol change in `K10056SetResolvingBit`

## What's Changed in v3.10.8

- Removed forced leading "/" from RECORD_PATH
- Removed the IP restrictions from the MediaMTX "publisher" role
- Sync up with Elliot Kroo's [wyzecam library](https://github.com/kroo/wyzecam)
  - add HL_WCO2 camera support
  - K10020CheckCameraParams support
  - Fix `authentication_type`'s type
  - Add fps to the `K10056SetResolvingBit` message
  - Fix time setting to always advance one second (for lag) in `K10092SetCameraTime`
  - Send/recv time and blank (PST flag?) to `K11006GetCurCruisePoint`/`K11010GetCruisePoints`/`K11012SetCruisePoints`
- Changed the MediaMTX config builder to emit correct config for recording
- Cleanup the warnings in the app code and added `mtx_event` pipe receipt logging
- Updated Wyze iOS app version to 3.5.0.8 (for user agent)
- Use `SIGTERM` for more graceful shutdown
- More startup logging for the MTX configuration of `RECORD_PATH`
- Sync up all the ports listed in MediaMTX with the ports exposed in the docker-compose files

## What's Changed in v3.10.7

- Reverted defaulting of RECORD_PATH option specifying `{cam_name}` instead of `%path` (need to fix that another way)
- Changed the MediaMTX config builder to emit correct config for recording.
  
## What's Changed in v3.10.6

- ~Changed the documentation and defaults for the RECORD_PATH option to specify `{cam_name}` instead of `%path` to
  eliminate recording errors~ Reverted in v3.10.7
- Add exception handling to ffmpeg pruning logic to prevent snapshot prunes from killing each other
- Now gathers the list of parents that might be pruned and does that after purging the files
- Fixed python lint message in get_livestream_cmd

## What's Changed in v3.10.5

- Fix regression for snapshot pruning

## What's Changed in v3.10.4

- Catch exceptions when pruning snapshots so we don't stop grabbing them if something breaks a prune.
- Allow the ffmpeg error messages to reach the normal runtime
- Bump to [MediaMTX 1.12.2](https://github.com/bluenviron/mediamtx/releases/tag/v1.12.2) to [fix regression on RaspberryPIs](https://github.com/bluenviron/mediamtx/compare/v1.12.1...v1.12.2)

## What's Changed in v3.10.3

- Bump MediaMTX to 1.12.1

## What's Changed in v3.10.2

- Added code to protect against the aggressive syntax check in MediaMTX 1.12.0 which
  complains about the `recordPath` missing required elements even when recording is
  not enabled (it really shouldn't validate that setting unless one or more paths
  request recording...and didn't through 1.11.3).
  For reference, the pattern is computed from our `RECORD_PATH` and `RECORD_FILE_NAME`
  settings and the combination of them must contain the `strftime` format specifiers
  of *either* a `"%s"` or **all** of of "%Y", "%m", "%d", "%H", "%M", "%S" (case-sensitive).
  If the value is not compliant, to keep MediaMTX from erroring out, we append `"_%s"` whatever
  was specified and emit a warning.
- Changed the default `RECORD_PATH` to ~`"record/%path/%Y/%m/%d/"`~ *v3.10.7* `"%path/{cam_name}/%Y/%m/%d"`
- Changed the default `RECORD_FILE_NAME` to `"%Y-%m-%d-%H-%M-%S"`

## What's Changed in v3.10.1

- Add `TOTP_KEY` and `MQTT_DTOPIC` to *config.yml* schema to avoid logged warning noise
- Add `MQTT_DTOPIC` to *config.yml* options to ensure a usable default
- Add `video: true` to all the *config.yml* variants to ensure hardware encoding can
  use video card
- Upgrade to `python:3.13-slim-bookworm` for docker base image
- Cleaned up Dockerfile scripts for testing and multiarch
- Safer docker build by testing the tarballs downloaded for MediaMTX or FFMpeg

## What's Changed in v3.10.0

- Attempt upgrade of MediaMTX to 1.12.0 (again)
- Fixed schema of RECORD_LENGTH config option (it needs an `s` or `h` suffix, so must be string)
- Added RECORD_KEEP to the config.yml so it can be actually be configured in the add-on

## What's Changed in v3.0.7

- Better logging of exceptions and pass the MediaMTX messages through to main logs
- Correct building of permissions for MediaMTX
- Documented all the possible points in the docker-compose files.

## What's Changed in v3.0.6

- Revert MediaMTX to 1.11.3 because 1.12 doesn't work here.

## What's Changed in v3.0.5 ~DELETED~

- Fix MediaMTX to pass a user name [since 1.12.0 now requires one](https://github.com/bluenviron/mediamtx/compare/v1.11.3...v1.12.0#diff-b5c575fc54691bae05c5cc598fac91c97876b3d15687c359f970a8b832ab3ab6R23-R41)

## What's Changed in v3.0.4  ~DELETED~

- Chore: Bump [MediaMTX to 1.12.0](https://github.com/bluenviron/mediamtx/releases/tag/v1.12.0)

## What's Changed in v3.0.3

Rehoming this to ensure it lives on since PR merges have stalled in the original (and most excellent) @mrlt8 repo, I am surfacing a new
release with the PRs I know work. **Note** The badges on the GitHub repo may be broken and the donation links *still* go to @mrlt8 (as they should!)

- Chore: Bump Flask to 3.1.*
- Chore: Bump Pydantic to 2.11.*
- Chore: Bump Python-dotenv to 1.1.*
- Chore: Bump MediaMTX to 1.11.3
- FIX: Add host_network: true for use in Home Assistant by @jdeath to allow communications in Docker
- FIX: Hardware accelerated rotation by @giorgi1324
- Enhancement: Add more details to the cams.m3u8 endpoint by @IDisposable
- FIX: Fix mixed case when URI_MAC=true by @unlifelike
- Update: Update Homebridge-Camera-FFMpeg documentation link by @donavanbecker
- FIX: Add formatting of {cam_name} and {img} to webhooks.py by @traviswparker which was lost
- Chore: Adjust everything for move to my GitHub repo and Docker Hub account

[View previous changes](https://github.com/idisposable/docker-wyze-bridge/releases)

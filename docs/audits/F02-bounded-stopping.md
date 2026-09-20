# F02 — Stalled detector / stop audit

Status: fixed for shipped native collectors; 11 focused regression tests passed on Linux.

## Change

- Native window, process, audio-device and display collectors run in persistent spawned subprocesses. Only minimized Result objects return to the parent. Collector state persists across polls.
- Each native scan has a 3-second deadline. A timeout retires that collector until a newly consented session. Shutdown terminates, then kills if necessary, with 0.2-second joins per attempt. There is no blocking shutdown message to a stalled receiver.
- Engine scans run outside the state/audit lock. Session identity checks discard late results; concurrent polls do not queue behind scans.
- The service checks heartbeat/session expiry independently every 0.5 seconds. The existing 15-second heartbeat threshold is unchanged. Device shutdown is initiated before waiting for the sampling loop during service exit.
- Camera acquisition is serialized against close, closed detectors cannot reopen, and the camera process has terminate/kill escalation. Each detector gets a cleanup attempt even when another cleanup raises. Cleanup failure blocks a fresh session and is reported as an error.

## Verification

`python -m unittest discover -s tests -p test_shutdown.py -v`: 11 passed.

Checks cover heartbeat and stop while a detector thread remains blocked; independent service watchdog expiry during a blocked scan; rejection of old results and old-watchdog actions after session replacement; continuation of camera cleanup after another cleanup fails; actual spawned never-returning probes with timeout and explicit stop; persistent collector state; no camera restart after close; real stuck-process termination through the camera cleanup path; and a process-only session through the production registry.

The blocked-thread stop and heartbeat check requires completion within 0.5 seconds. Hung-probe timeout is tested within 2 seconds using a shortened 0.6-second deadline; explicit stop within 1.5 seconds. The camera test uses a real stuck subprocess but no physical camera. The original 52 Python tests also passed after the implementation change.

## Conclusion and limits

The reproduced native-scan lock dependency is removed and the shipped native probes can be killed. These are OS-scheduled deadlines, not hard real-time guarantees. This work does not claim bounded completion for stalled filesystem/audit I/O or arbitrary third-party detector implementations. A killed process cannot continue collecting, but physical device-indicator release and Windows/macOS spawn, permissions and packaged sidecar behavior still need platform testing. Camera first-measurement timeout (F07) remains a separate issue.

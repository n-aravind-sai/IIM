# F07 — Camera startup timeout

Status: fixed. Seven focused tests passed (`test_camera_timeout.py`).

A spawned camera has a 10-second first-measurement deadline, checked at the next camera poll (normally every two seconds). Before its first measurement the detector returns `waiting`, not usable `partial` coverage. Measurements subsequently expire after three seconds, checked at the next poll. Startup timeout, stale measurements, EOF and worker errors terminate/reap the camera worker and close its pipe. Failure remains explicit until a new consented session; polling does not silently reopen hardware. Spawn failure closes both pipe ends and does not expose exception details.

Tests use mocked process/pipe objects and a controlled clock, covering silent live startup, pre-deadline waiting, first-measurement transition, stale data, worker error, EOF and spawn failure. F02 separately tests termination of a real stuck subprocess. No physical camera or native permission UI was tested. Deadlines depend on scheduling and poll cadence, not hard real-time guarantees.

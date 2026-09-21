# Scenario coverage enhancements

This increment adds candidate-reviewed immutable session rules, an optional
unscored dashboard-focus scope, detector coverage transitions and gap durations,
sampled audio/display inventory count changes, and browser import timing.
Disclosure v3 is required for new sessions. Older exports remain readable.

Permitted process names remain visible with zero weight. Display-limit notices
are also unscored: Windows currently enumerates attached adapters, not a verified
physical-monitor topology. Phase is recorded context, not speech enforcement.
Stereo Mix no longer produces a routing penalty; virtual-audio name matching
includes VB-Audio, VoiceMeeter, OBS Virtual Audio, Krisp and SteelSeries Sonar.
Matching names do not establish active routing or assistance.

Focus reports are session-bound and sequence-checked, coalesce browser focus and
visibility events, and use server receipt timing. They identify dashboard
departure only, not the destination application. They cannot prevent a modified
client from withholding or fabricating events. An interrupted interval is
explicitly incomplete. Detector unavailability and recovery appear in the signed
timeline and PDF. Existing watchdog/disconnect behavior still ends monitoring.

Validation: 103 Python tests pass locally, including new policy validation,
consent/session isolation, replay handling, duration measurement, incomplete
intervals, coverage recovery, inventory count changes, audio classification,
process exceptions and display-limit deduplication. JavaScript production-handler
tests cover consent/demo isolation and focus-event coalescing in addition to
device cleanup. CI must confirm Windows/macOS and Chromium on the published commit.

Remaining: authenticated interviewer policy delivery, native foreground-app
events, complete monitor topology, active routing detection, remote-session
classification, camera liveness/freeze checks, cross-detector episode grouping,
and empirical accuracy/false-positive measurement. No speech recognition,
shortcut blocking, content capture or browser-profile scanning was added.
Independent devices and off-camera assistance remain outside observable coverage.

# F03 — Transient evidence retention audit

Status: fixed; all 6 focused regression tests passed, including generated-PDF text extraction.

## Change

The engine appends the complete minimized signal as a signed `signal_observed` event before publishing it to dashboard snapshots. Fields include ID, detector, evidence, confidence, weight, title, explanation and limitation; the signed event envelope includes time. Changed details and recurrence create further events. Steady observations do not create duplicate events on every poll.

Separate `signal_resolved` events identify the signal and why tracking ended. A detector no longer returning a signal is described as an observation/coverage change; session stop is described as ending tracking. Neither claims the underlying activity definitely ceased. Periodic samples continue to describe coverage and the technical index.

Reports collect unique observations from signed events with a sample-only fallback for older archives. Full evidence, limitations and first/latest observation-event times appear in the PDF. Every recurrence/revision remains in the signed JSON; the PDF summarizes each unique signal using its latest observed details.

## Verification

`python -m unittest discover -s tests -p test_evidence.py -v`: 6 passed.

The original failure case was reproduced as a controlled timeline: empty sample at t=100, unique observation at t=102, empty result at t=104, then stop. Both the periodic and stop samples contain no signals, but the live export and final verified export contain the complete observation. Poppler extraction of the actual generated PDF confirms the unique evidence, limitation and timestamp text survive.

Additional checks cover recurrence, changed confidence under the same ID, duplicate suppression, resolution/stop events, sample-only legacy compatibility, and tamper/removal rejection. Simulated evidence-write failure raises before the signal can enter a dashboard snapshot.

## Conclusion and limits

The reproduced loss of sub-sample-duration evidence is closed for observations accepted by the engine. This does not detect events between detector scans, recover evidence omitted by old versions, or prove observations are accurate. The signature establishes integrity of retained bytes, not truth or completeness of device activity. Platform/hardware validation and remaining medium-priority report/disclosure issues are still outstanding.

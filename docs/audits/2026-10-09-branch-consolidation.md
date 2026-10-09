# Audit branch consolidation review — 9 October 2026

Compared `audit/remediation` at `cf5db8559d51409c0289b2b934771549b19122b3`
with `main` at `086118949a5fc83084d03f776566bd796df2e76d`.
The original audit work was merged in PR #1. One subsequent audit commit,
"Add consented session rules focus timing and coverage events", remained unique
to the branch. Its complete diff, tests and affected current call paths were reviewed.

## Decision

Retain the current application implementation. Preserve the audit tip as a second
parent of the consolidation commit so its source and tests remain reachable after
the branch is deleted. This records the review disposition without enabling the
older implementations or changing monitoring consent. Only this review record,
its backlog reference and the source manifest change in the consolidation tree.

| Audit change | Disposition |
|---|---|
| Session rules and application exceptions | Superseded by main's versioned rules, session/revision guards and unverified-approval state. The audit implementation sets matching process weights to zero based on candidate declarations; importing it would restore a scoring bypass. |
| Display-limit notices | Superseded by main's distinct Windows desktop-monitor count and freshness-aware assessment. The audit comparison uses adapter inventory as its count. |
| Coverage transitions and gap durations | Superseded by structured, signed gap identities and durable transitions on main, including startup, stale measurements, stop and interruption. |
| Browser import timing | Superseded by main's session-bound v3 envelope, export/import provenance claims and expiring coverage. |
| Stereo Mix handling | Already implemented on main as a retained, zero-weight informational observation. |
| Dashboard focus timing | Useful prototype for P1-02, retained in history rather than activated. It observes only the dashboard, not an external interview tab or destination app. Its sequence/interval state advances before the audit write, so a failed write can consume the event and make a retry appear duplicate. Port only with durable-before-acknowledgment semantics, failure/retry tests and a new consent version. |
| Audio input counts and device-count change events | Useful prototype for P1-04, retained in history. A future port should use actual desktop-monitor counts, explicit freshness/gap handling and signed changes. Equal counts do not establish unchanged device identity, and input endpoints are not necessarily distinct physical devices. |
| Expanded audio-name rules | Retain as P0-06 research fixtures. Broad substring matches for products such as Krisp and SteelSeries Sonar do not establish virtual routing or active assistance; do not automatically add adverse weights without reviewed legitimate-use fixtures and classification evidence. |

## Follow-up acceptance checks

- P1-02: exercise audit-write failure followed by retry, old-session delivery,
  duplicate/out-of-order events, initially unfocused dashboards, disconnects and
  incomplete intervals. Keep destination/content collection absent and events unscored.
- P1-04: distinguish endpoint/adapter/monitor counts; test unavailable or stale
  inventories, recovery, same-count replacements and short changes between samples.
- P0-06: separate device presence, hardware loopback, virtual routing, noise
  suppression and observable active use. Ordinary conferencing/accessibility
  setups must be represented in negative fixtures.

These are existing roadmap items, not newly enabled detection capabilities.
The historical commit remains available at
[cf5db85](https://github.com/n-aravind-sai/IIM/commit/cf5db8559d51409c0289b2b934771549b19122b3).

## Validation scope

This consolidation changes documentation and source checksums only. Compare every
published blob with the local manifest and verify that application and test files
match the reviewed main tree. No new runtime-test result is claimed for this
documentation-only consolidation; the previous fix validation remains recorded
in `docs/foundation-progress.md`.

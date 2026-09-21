# F05 — Device and metadata disclosures

Status: fixed. Three focused disclosure checks and all 10 pre-flight lifecycle tests passed.

Disclosure `iim-consent-2` explicitly covers eye-position consistency, quality/calibration statistics, lighting, face count and multiple-face observations. The engine rejects v1 for new sessions. The consent UI, privacy panel, README, architecture, security/API documentation and PDF describe the retained metadata and the separate optional local camera/microphone preview. Preview data is not retained or sent to the worker; audio is never recorded. The trigger explicitly names both devices, with explanatory text next to it. Demo device access remains disabled.

Verification confirms old consent rejection, current version in UI/API, new disclosure sealed in the exported session, required metadata categories in the consent UI, and hardware-free demo behavior. Historical reports display the actual recorded disclosure version instead of relabelling old consent. This is a code/data-contract alignment audit, not a legal-compliance or physical-device assessment.

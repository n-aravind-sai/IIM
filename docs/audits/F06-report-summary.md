# F06 — Report summary accuracy

Status: fixed. All eight summary/evaluator tests passed.

The shipped report now uses a local deterministic summary without invoking a mock or external provider. It counts only the engine's six actual scopes, distinguishes enabled scope choices from available measurements, reports retained unique observations and explicitly describes disabled/unknown coverage. The PDF labels its summary method and no longer displays a misleading compliance percentage.

For explicitly supplied development providers, acceptance requires a passing evaluator result, no policy violations and the configured passing score. The unused `strict_compliance` relaxation option was removed; supplying it fails explicitly. Fallback scores come from evaluating the fallback text instead of a fixed number. Neither an internal text-check score nor passing tests establishes legal compliance, factual truth or detection accuracy.

Verification covers the previous acceptance-as-scope error, the default no-provider path, configured 1.0 threshold rejecting a 0.85 draft, evaluated fallback scores, invalid settings, removed unsupported settings and existing correction-loop/terminology tests. No external data transfer was introduced.

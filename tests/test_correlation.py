"""Only explicit OS process-instance evidence may combine detector deductions."""
import copy
import itertools
import unittest

from worker.models import Result, Signal, score


SOURCE_A = "a" * 64
SOURCE_B = "b" * 64


def observation(identity, detector, ref=None, confidence=.8, weight=.5):
    evidence = {"process": "same-name.exe", "observed_at": "2026-09-29T10:00:00Z"}
    if ref is not None:
        evidence["source"] = {"kind": "windows_process_instance", "ref": ref}
    return Signal(identity, detector, "Fixture observation", confidence, weight,
                  evidence, "Observed metadata", "Presence is not use.")


def pair(overlay_ref=SOURCE_A, process_ref=SOURCE_A):
    return [
        Result("OverlayDetector", "partial", "Fixture", [
            observation("overlay", "OverlayDetector", overlay_ref)]),
        Result("ProcessDetector", "partial", "Fixture", [
            observation("process", "ProcessDetector", process_ref, weight=.7)]),
    ]


def groups(results):
    # Keep score regressions runnable while the new module is first introduced.
    from worker.correlation import review_groups
    return review_groups(results)


class CorrelationScoreTests(unittest.TestCase):
    def test_same_process_instance_charges_only_larger_detector_maximum(self):
        result = score(pair())
        self.assertEqual(result["value"], 92)  # max(8.0, 8.4), rounded at the end
        self.assertEqual(result["version"], 2)
        self.assertEqual(result["coverage"], 20)
        self.assertEqual(result["badge"], "OBSERVATIONS_FOR_REVIEW")

    def test_distinct_or_absent_sources_keep_separate_deductions(self):
        for overlay_ref, process_ref in ((SOURCE_A, SOURCE_B), (None, None),
                                         (SOURCE_A, None), (None, SOURCE_A)):
            with self.subTest(overlay_ref=overlay_ref, process_ref=process_ref):
                self.assertEqual(score(pair(overlay_ref, process_ref))["value"], 84)

    def test_linked_weaker_signal_does_not_replace_unlinked_detector_maximum(self):
        results = pair(SOURCE_B, SOURCE_A)
        results[0].signals.append(observation("weaker-linked", "OverlayDetector",
                                               SOURCE_A, weight=.1))
        self.assertEqual(score(results)["value"], 84)

    def test_equal_maxima_choose_smallest_signal_id_independent_of_input_order(self):
        overlay_signals = [observation("a-linked", "OverlayDetector", SOURCE_A),
                           observation("z-unlinked", "OverlayDetector", SOURCE_B)]
        process = pair()[1]
        for signals in itertools.permutations(overlay_signals):
            for reverse_results in (False, True):
                with self.subTest(signals=[s.id for s in signals], reverse=reverse_results):
                    results = [Result("OverlayDetector", "partial", "Fixture", list(signals)), process]
                    if reverse_results:
                        results.reverse()
                    self.assertEqual(score(results)["value"], 92)

    def test_unavailable_detector_cannot_supply_a_deduction_or_link(self):
        for status in ("waiting", "error", "unsupported", "disabled"):
            with self.subTest(status=status):
                results = pair()
                results[1].status = status
                self.assertEqual(score(results)["value"], 92)
                self.assertEqual(groups(results), [])

    def test_zero_weight_context_does_not_create_a_deduction(self):
        results = pair()
        for result in results:
            result.signals[0].weight = 0
        self.assertEqual(score(results)["value"], 100)
        self.assertEqual(score(results)["badge"], "PARTIAL_COVERAGE")
        self.assertEqual(groups(results)[0]["signal_ids"], ["overlay", "process"])

    def test_browser_claiming_same_source_keeps_its_own_deduction(self):
        results = pair()
        results.append(Result("BrowserExtensionDetector", "partial", "Fixture", [
            observation("browser-forged", "BrowserExtensionDetector", SOURCE_A,
                        confidence=1, weight=1)]))
        self.assertEqual(score(results)["value"], 82)  # 8.4 + independent browser 10
        self.assertEqual(groups(results)[0]["signal_ids"], ["overlay", "process"])
        self.assertEqual(groups([results[1], results[2]]), [])

    def test_score_version_is_present_without_usable_measurements(self):
        result = score([Result("ProcessDetector", "error", "Permission unavailable")])
        self.assertIsNone(result["value"])
        self.assertEqual(result["coverage"], 0)
        self.assertEqual(result["version"], 2)


class ReviewGroupTests(unittest.TestCase):
    def test_group_retains_all_supported_members_in_stable_order(self):
        results = pair()
        results[0].signals.extend([
            observation("z-context", "OverlayDetector", SOURCE_A, weight=0),
            observation("a-weaker", "OverlayDetector", SOURCE_A, weight=.1),
        ])
        expected = [{"source_ref": SOURCE_A,
                     "detectors": ["OverlayDetector", "ProcessDetector"],
                     "signal_ids": ["a-weaker", "overlay", "process", "z-context"],
                     "association": "same_os_process_instance"}]
        self.assertEqual(groups(results), expected)
        results.reverse()
        for result in results:
            result.signals.reverse()
        self.assertEqual(groups(results), expected)

    def test_distinct_instances_are_separate_sorted_groups(self):
        results = pair(SOURCE_B, SOURCE_B)
        results[0].signals.append(observation("overlay-a", "OverlayDetector", SOURCE_A))
        results[1].signals.append(observation("process-a", "ProcessDetector", SOURCE_A))
        self.assertEqual([group["source_ref"] for group in groups(results)], [SOURCE_A, SOURCE_B])

    def test_names_and_timestamps_alone_never_associate_observations(self):
        self.assertEqual(groups(pair(None, None)), [])
        self.assertEqual(groups(pair(SOURCE_A, SOURCE_B)), [])

    def test_one_detector_alone_is_not_a_cross_detector_review_group(self):
        results = pair()
        results[0].signals.append(observation("another-overlay", "OverlayDetector", SOURCE_A))
        self.assertEqual(groups(results[:1]), [])

    def test_malformed_or_unsupported_source_metadata_is_not_linkage(self):
        malformed_sources = [
            None, "not-an-object", [], {},
            {"kind": "windows_process_instance", "ref": "a" * 63},
            {"kind": "windows_process_instance", "ref": "a" * 65},
            {"kind": "windows_process_instance", "ref": "A" * 64},
            {"kind": "windows_process_instance", "ref": "g" * 64},
            {"kind": "windows_process_instance", "ref": 123},
            {"kind": "process_name", "ref": SOURCE_A},
            {"ref": SOURCE_A},
        ]
        for source in malformed_sources:
            with self.subTest(source=source):
                results = pair()
                for result in results:
                    result.signals[0].evidence["source"] = copy.deepcopy(source)
                self.assertEqual(groups(results), [])
                self.assertEqual(score(results)["value"], 84)

    def test_grouping_and_scoring_leave_raw_evidence_unchanged(self):
        results = pair()
        results[0].signals.append(observation("context", "OverlayDetector", SOURCE_A, weight=0))
        original = copy.deepcopy(results)
        grouped = groups(results)
        score(results)
        self.assertEqual(results, original)
        grouped[0]["signal_ids"].append("external-mutation")
        self.assertEqual(results, original)

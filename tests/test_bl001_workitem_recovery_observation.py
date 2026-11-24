"""BL-001: observations do not authorize replay of non-atomic WorkPool jobs."""
import itertools
from dataclasses import FrozenInstanceError
import unittest
from unittest import mock

from text_category_profiler.pipeline.workpool import (
    WorkItemRecoveryObservation, classify_external_work_item_locations,
)


def classify(incoming, processing, processed, work_id="private-job-01"):
    return classify_external_work_item_locations(
        work_id, incoming=incoming, processing=processing, processed=processed,
    )


class WorkItemRecoveryObservationTests(unittest.TestCase):
    def test_all_27_three_value_observations_are_fail_closed(self):
        for incoming, processing, processed in itertools.product(
                (None, False, True), repeat=3):
            with self.subTest(incoming=incoming, processing=processing,
                              processed=processed):
                observation = classify(incoming, processing, processed)
                self.assertIsInstance(observation, WorkItemRecoveryObservation)
                self.assertIs(observation.automatic_retry_authorized, False)
                self.assertIs(observation.delivery_verified, False)
                self.assertIs(observation.requires_operator_review, True)
                self.assertEqual(
                    observation.observations_complete,
                    all(x is not None for x in
                        (incoming, processing, processed)),
                )
                self.assertNotIn("private-job", str(observation))

    def test_single_observed_location_is_not_proof_of_liveness_or_completion(self):
        for conditions, expected in (
            ((True, False, False), "INCOMING_ONLY"),
            ((False, True, False), "PROCESSING_ONLY"),
            ((False, False, True), "PROCESSED_ONLY"),
            ((False, False, False), "NO_LOCATION_OBSERVED"),
        ):
            with self.subTest(status=expected):
                self.assertEqual(classify(*conditions).status, expected)
        self.assertFalse(classify(False, False, True).delivery_verified)

    def test_multiple_locations_are_conflict_even_when_one_is_unknown(self):
        for conditions in (
            (True, True, False), (True, False, True), (False, True, True),
            (True, True, True), (True, True, None),
        ):
            with self.subTest(conditions=conditions):
                self.assertEqual(classify(*conditions).status,
                                 "MULTIPLE_LOCATIONS")

    def test_any_unknown_without_known_collision_is_insufficient(self):
        for conditions in (
            (True, False, None), (False, None, True),
            (None, False, False), (None, None, None),
        ):
            with self.subTest(conditions=conditions):
                self.assertEqual(classify(*conditions).status,
                                 "INCOMPLETE_OBSERVATION")

    def test_location_names_only_not_private_work_id_or_paths(self):
        observation = classify(True, False, False, work_id="中文 工作單 2026")
        self.assertEqual(observation.observed_locations, ("incoming",))
        self.assertNotIn("中文", str(observation))
        self.assertEqual(observation.status, "INCOMING_ONLY")

    def test_invalid_work_id_and_unknown_type_are_rejected_before_assessment(self):
        for work_id in ("", "CON", "../escape", "job:ADS", None):
            with self.subTest(work_id=repr(work_id)):
                with self.assertRaisesRegex(ValueError,
                                            "EXTERNAL_WORK_ID_INVALID"):
                    classify(True, False, False, work_id=work_id)
        for unexpected in (0, 1, "true", (), []):
            with self.subTest(value=repr(unexpected)):
                with self.assertRaisesRegex(
                    TypeError, "WORKITEM_RECOVERY_OBSERVATION_NOT_BOOLEAN"
                ):
                    classify(unexpected, False, False)

    def test_immutable_observation_does_not_require_fs_io(self):
        with mock.patch("os.listdir",
                        side_effect=AssertionError("no filesystem reads")):
            observation = classify(False, True, False)
        with self.assertRaises(FrozenInstanceError):
            observation.status = "SAFE_TO_RETRY"
        self.assertFalse(observation.automatic_retry_authorized)


if __name__ == "__main__":
    unittest.main()

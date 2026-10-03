import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from benchmark import DATA, InputError, replay, score, verify
from router import decision


class BenchmarkTests(unittest.TestCase):
    def test_ordinary_label_is_scored_and_a_failed_review_is_not_correct(self):
        cases = [{"id": "one", "expected": "no_skill"}, {"id": "two", "expected": "review"}]
        valid = decision("__no_skill__", {"only-skill": 0.0, "__no_skill__": 1.0, "__review__": 0.0}, 0.9, "jev", "model_choice", 1, 8, 2)
        failed = decision("__review__", {}, None, "api", "api_unavailable", 1, None, None)
        observations = [{"id": "one", "repeat": 1, "decision": valid, "latency_ms": 12},
                        {"id": "two", "repeat": 1, "decision": failed, "latency_ms": 24}]
        verify(observations, cases, {"only-skill"}, 1)
        result = score(observations, cases)
        self.assertEqual((result["exact"], result["expected_no_skill"], result["api_errors"], result["observations"]), (1, 1, 1, 2))

    def test_missing_duplicate_and_extra_observations_are_rejected(self):
        case = {"id": "one", "expected": "review"}
        failed = decision("__review__", {}, None, "api", "api_unavailable", 1, None, None)
        row = {"id": "one", "repeat": 1, "decision": failed, "latency_ms": 10}
        verify([row], [case], {"only-skill"}, 1)
        for observations in ([], [row, row], [{**row, "id": "other"}], [{**row, "repeat": 2}]):
            with self.subTest(observations=observations), self.assertRaises(InputError):
                verify(observations, [case], {"only-skill"}, 1)

    def test_zero_attempt_cannot_replace_error(self):
        case = {"id": "one", "expected": "review"}
        row = {"id": "one", "repeat": 1,
               "decision": decision("__review__", {}, None, "api", "api_unavailable", 0, None, None),
               "latency_ms": 10}
        with self.assertRaises(InputError):
            verify([row], [case], {"only-skill"}, 1)

    def test_portable_replay_checks_all_360_records(self):
        with patch("urllib.request.build_opener", side_effect=AssertionError("offline replay used network")):
            summary = replay(DATA / "live-360.jsonl", DATA / "ordinary-6-results.jsonl")
        self.assertEqual((summary["live"]["observations"], summary["live"]["exact"],
                          summary["live"]["wrong_routes"], summary["live"]["api_errors"]),
                         (360, 347, 9, 0))
        self.assertEqual((summary["ordinary_controls"]["expected_no_skill"],
                          summary["ordinary_controls"]["exact"], summary["lexical_same_120"]["exact"]),
                         (6, 6, 31))
        with tempfile.TemporaryDirectory() as folder:
            data = (DATA / "live-360.jsonl").read_text().splitlines()
            target = Path(folder) / "missing.jsonl"
            target.write_text("\n".join(data[:-1]) + "\n")
            with self.assertRaisesRegex(InputError, "planned id and repeat"):
                replay(target, DATA / "ordinary-6-results.jsonl")
            target.write_text("\n".join(data[:-1] + [data[0]]) + "\n")
            with self.assertRaisesRegex(InputError, "planned id and repeat"):
                replay(target, DATA / "ordinary-6-results.jsonl")


if __name__ == "__main__":
    unittest.main()

import unittest
import tempfile
import json
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from benchmark import DATA, InputError, replay, score, verify
from router import decision, route


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
        for observations in ([], [row, row], [{**row, "id": "other"}], [{**row, "repeat": 2}],
                             [{**row, "repeat": True}]):
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
        with patch("benchmark.LIVE_SHA", "0" * 64), self.assertRaisesRegex(InputError, "pinned input changed"):
            replay(DATA / "live-360.jsonl", DATA / "ordinary-6-results.jsonl")
        with tempfile.TemporaryDirectory() as folder:
            data = (DATA / "live-360.jsonl").read_text().splitlines()
            target = Path(folder) / "missing.jsonl"
            target.write_text("\n".join(data) + "\n")
            self.assertEqual(replay(target, DATA / "ordinary-6-results.jsonl")["live"]["exact"], 347)
            target.write_text("\n".join(data[:-1]) + "\n")
            with self.assertRaisesRegex(InputError, "planned id and repeat"):
                replay(target, DATA / "ordinary-6-results.jsonl")
            target.write_text("\n".join(data[:-1] + [data[0]]) + "\n")
            with self.assertRaisesRegex(InputError, "planned id and repeat"):
                replay(target, DATA / "ordinary-6-results.jsonl")

    def test_recorded_model_choice_obeys_maximum_and_route_thresholds(self):
        case = [{"id": "one", "expected": "only-skill"}]
        def check(choice, probabilities, confidence, reason="model_choice"):
            result = decision(choice, probabilities, confidence, "jev", reason, 1, 8, 2)
            verify([{"id": "one", "repeat": 1, "decision": result, "latency_ms": 10}], case, {"only-skill"}, 1)

        high = {"only-skill": 1.0, "__no_skill__": 0.0, "__review__": 0.0}
        check("only-skill", high, 0.55)
        check("__no_skill__", {"only-skill": 0.0, "__no_skill__": 1.0, "__review__": 0.0}, 0.2)
        check("__review__", {"only-skill": 0.0, "__no_skill__": 0.0, "__review__": 1.0}, 0.2)
        for choice, probabilities, confidence in (
            ("only-skill", {"only-skill": 0.4, "__no_skill__": 0.6, "__review__": 0.0}, 0.9),
            ("only-skill", high, 0.5),
            ("only-skill", {"only-skill": 0.54, "__no_skill__": 0.46, "__review__": 0.0}, 0.9),
            ("__no_skill__", high, 0.9),
            ("__review__", high, 0.9),
        ):
            with self.subTest(choice=choice, confidence=confidence, probabilities=probabilities), self.assertRaisesRegex(InputError, "choice contradicts"):
                check(choice, probabilities, confidence)

    def test_uncertain_review_requires_a_maximal_low_threshold_skill(self):
        case = [{"id": "one", "expected": "review"}]
        def check(probabilities, confidence, reason="uncertain"):
            result = decision("__review__", probabilities, confidence, "jev", reason, 1, 8, 2)
            verify([{"id": "one", "repeat": 1, "decision": result, "latency_ms": 10}], case, {"only-skill"}, 1)

        high = {"only-skill": 1.0, "__no_skill__": 0.0, "__review__": 0.0}
        check(high, 0.5)
        check({"only-skill": 0.54, "__no_skill__": 0.46, "__review__": 0.0}, 0.9)
        with self.assertRaisesRegex(InputError, "uncertain review contradicts"):
            check(high, 0.9)
        with self.assertRaisesRegex(InputError, "uncertain review contradicts"):
            check({"only-skill": 0.0, "__no_skill__": 0.0, "__review__": 1.0}, 0.5)
        with self.assertRaisesRegex(InputError, "choice contradicts"):
            check(high, 0.5, "model_choice")

    def test_frozen_runtime_decisions_pass_offline_policy_mirror(self):
        catalogue = [{"id": "only-skill", "description": "Fix this specialist task", "examples": ["Fix task"]}]
        cases = [{"id": "one", "expected": "review"}]
        for choice, probabilities, confidence, outcome, reason in (
            ("only-skill", {"only-skill": 0.55, "__no_skill__": 0.45, "__review__": 0.0}, 0.55, "route", "model_choice"),
            ("only-skill", {"only-skill": 0.54, "__no_skill__": 0.46, "__review__": 0.0}, 0.9, "review", "uncertain"),
            ("only-skill", {"only-skill": 1.0, "__no_skill__": 0.0, "__review__": 0.0}, 0.5, "review", "uncertain"),
            ("only-skill", {"only-skill": 0.5, "__no_skill__": 0.5, "__review__": 0.0}, 0.5, "review", "uncertain"),
            ("__no_skill__", {"only-skill": 0.0, "__no_skill__": 1.0, "__review__": 0.0}, 0.2, "no_skill", "model_choice"),
            ("__review__", {"only-skill": 0.0, "__no_skill__": 0.0, "__review__": 1.0}, 0.2, "review", "model_choice"),
        ):
            response = {"model": "jev-1.13.0", "answers": {"route": {"type": "choice", "choice": choice,
                        "probabilities": probabilities, "confidence": confidence}},
                        "usage": {"input_tokens": 8, "output_tokens": 2}}
            class Opener:
                def open(self, request, timeout):
                    return BytesIO(json.dumps(response).encode())
            with self.subTest(choice=choice, confidence=confidence), patch("urllib.request.build_opener", return_value=Opener()):
                result = route("Fix task", catalogue, api_key="fake-test-key")
                self.assertEqual((result["outcome"], result["reason"]), (outcome, reason))
                verify([{"id": "one", "repeat": 1, "decision": result, "latency_ms": 10}], cases, {"only-skill"}, 1)

    def test_error_remains_unscored_and_claimed_metadata_cannot_be_ignored(self):
        case = [{"id": "one", "expected": "review"}]
        error = decision("__review__", {}, None, "api", "api_unavailable", 1, None, None)
        row = {"id": "one", "repeat": 1, "decision": error, "latency_ms": 10}
        verify([row], case, {"only-skill"}, 1)
        self.assertEqual((score([row], case)["exact"], score([row], case)["api_errors"]), (0, 1))
        for altered in ({**error, "model": "jev-other"},
                        {**error, "source": "jev"},
                        {**error, "usage": {**error["usage"], "input_tokens": 8}},
                        {**error, "usage": {**error["usage"], "estimated_input_usd": 1.0}}):
            with self.subTest(altered=altered), self.assertRaises(InputError):
                verify([{**row, "decision": altered}], case, {"only-skill"}, 1)
        with self.assertRaisesRegex(InputError, "unexpected observation fields"):
            verify([{**row, "runtime_commit": "wrong"}], case, {"only-skill"}, 1)

    def test_cli_rejects_reviewer_perfect_score_with_unchanged_probabilities(self):
        originals = [json.loads(line) for line in (DATA / "live-360.jsonl").read_text().splitlines()]
        expected = {case["id"]: case["expected"] for case in
                    (json.loads(line) for line in (DATA / "known-120.jsonl").read_text().splitlines())}
        for row in originals:
            target = expected[row["id"]]
            row["decision"].update(outcome="review" if target == "review" else "route",
                                   skill_id=None if target == "review" else target, reason="model_choice")
        with tempfile.TemporaryDirectory() as folder:
            fixture = Path(folder) / "impossible.jsonl"
            fixture.write_text("".join(json.dumps(row) + "\n" for row in originals))
            run = subprocess.run([sys.executable, str(DATA.parent / "benchmark.py"), "--live", str(fixture)],
                                 capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn("contradicts frozen router policy", run.stderr)


if __name__ == "__main__":
    unittest.main()

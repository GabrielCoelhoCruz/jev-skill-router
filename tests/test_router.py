import json
import os
import subprocess
import sys
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from router import InputError, catalogue_from, evaluate, route


ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = json.loads((ROOT / "data/catalogue.json").read_text())


class RouterTests(unittest.TestCase):
    def test_offline_choice_and_abstentions(self):
        cases = [
            ("Optimize this SQL query using the EXPLAIN plan and an index.", "route", "sql-tuning"),
            ("Hi there, how are you?", "no_skill", None),
            ("Fix the CI workflow and application tests equally.", "review", None),
        ]
        for request, outcome, skill_id in cases:
            with self.subTest(request=request):
                answer = route(request, CATALOGUE, dry_run=True)
                self.assertEqual((answer["outcome"], answer["skill_id"]), (outcome, skill_id))
                self.assertAlmostEqual(sum(answer["probabilities"].values()), 1.0)

    def test_missing_key_uses_lexical_without_network(self):
        with patch("urllib.request.build_opener", side_effect=AssertionError("network used")):
            answer = route("Fix the Dockerfile image build", CATALOGUE)
        self.assertEqual((answer["source"], answer["skill_id"], answer["usage"]["requests"]), ("lexical", "container-build", 0))

    def test_api_error_falls_back_without_exposing_key(self):
        with patch("urllib.request.build_opener", side_effect=OSError("offline")):
            answer = route("Fix the Dockerfile image build", CATALOGUE, api_key="secret-value")
        self.assertEqual((answer["source"], answer["skill_id"], answer["usage"]["requests"]), ("lexical", "container-build", 1))
        self.assertIsNone(answer["usage"]["estimated_input_usd"])
        self.assertNotIn("secret-value", json.dumps(answer))

    def test_valid_jev_choice_and_invalid_distribution_fallback(self):
        class Response(BytesIO):
            pass

        class Opener:
            def __init__(self, probabilities):
                self.probabilities = probabilities

            def open(self, request, timeout):
                self_payload = json.loads(request.data)
                options = self_payload["questions"]["route"]["criteria"]
                probabilities = {name: (self.probabilities if name == "container-build" else 0.0) for name in options}
                return Response(json.dumps({"model": "jev-1.13.0", "answers": {"route": {
                    "type": "choice", "choice": "container-build", "confidence": 0.9,
                    "probabilities": probabilities}}, "usage": {"input_tokens": 100, "output_tokens": 20}}).encode())

        with patch("urllib.request.build_opener", return_value=Opener(1.0)):
            answer = route("Fix the Dockerfile image build", CATALOGUE, api_key="fake-test-key")
        self.assertEqual((answer["source"], answer["skill_id"], answer["usage"]["input_tokens"]), ("jev", "container-build", 100))
        with patch("urllib.request.build_opener", return_value=Opener(0.5)):
            answer = route("Fix the Dockerfile image build", CATALOGUE, api_key="fake-test-key")
        self.assertEqual((answer["source"], answer["skill_id"], answer["reason"]), ("lexical", "container-build", "api_unavailable_or_invalid"))

    def test_invalid_catalogue_and_case_are_rejected(self):
        with self.assertRaisesRegex(InputError, "duplicate"):
            catalogue_from(CATALOGUE + [CATALOGUE[0]])
        with self.assertRaisesRegex(InputError, "each case"):
            evaluate([{"id": "x", "request": "Hi", "expected": "nonexistent"}], CATALOGUE, dry_run=True)

    def test_golden_eval_reports_wrong_routes_and_reviews(self):
        cases = [{"id": "one", "request": "Fix the Dockerfile image build", "expected": "container-build"},
                 {"id": "two", "request": "Hi there, how are you?", "expected": "code-tests"}]
        summary = evaluate(cases, CATALOGUE, dry_run=True)["summary"]
        self.assertEqual((summary["cases"], summary["correct"], summary["accuracy"], summary["api_requests"]), (2, 1, 0.5, 0))

    def test_cli_dry_run_ignores_present_key_and_never_overwrites_report(self):
        env = os.environ.copy()
        env["TYPESAFE_API_KEY"] = "invalid value with spaces"
        cmd = [sys.executable, str(ROOT / "router.py"), "eval", "--dry-run", "--catalogue", str(ROOT / "data/catalogue.json"), "--dataset", str(ROOT / "data/own-36.jsonl")]
        first = subprocess.run(cmd, capture_output=True, text=True, env=env)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)["cases"], 36)
        self.assertNotIn(env["TYPESAFE_API_KEY"], first.stdout + first.stderr)
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder) / "existing.json")
            Path(target).write_text("keep")
            second = subprocess.run(cmd + ["--output", target], capture_output=True, text=True, env=env)
            self.assertEqual(second.returncode, 2)
            self.assertEqual(Path(target).read_text(), "keep")

    def test_cli_invalid_request_is_actionable_and_has_no_skill(self):
        run = subprocess.run([sys.executable, str(ROOT / "router.py"), "route", "--dry-run", "--catalogue", str(ROOT / "data/catalogue.json"), "--request", " "], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertEqual((json.loads(run.stdout)["outcome"], json.loads(run.stdout)["skill_id"]), ("invalid", None))
        self.assertIn("request must be nonempty", run.stderr)


if __name__ == "__main__":
    unittest.main()

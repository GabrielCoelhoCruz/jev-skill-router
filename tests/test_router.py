import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from router import InputError, catalogue_from, evaluate, route


ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = json.loads((ROOT / "data/catalogue.json").read_text())


@contextmanager
def local_api(reply):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            body = json.dumps(reply).encode() if isinstance(reply, dict) else reply
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        with patch("router.ENDPOINT", f"http://127.0.0.1:{server.server_port}/choice"):
            yield received
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def choice_response(skill="container-build", model="jev-1.13.0", confidence=0.9, probability=1.0, usage=True):
    options = {entry["id"]: 0.0 for entry in CATALOGUE} | {"__no_skill__": 0.0, "__review__": 0.0}
    options[skill] = probability
    result = {"model": model, "answers": {"route": {"type": "choice", "choice": skill,
              "confidence": confidence, "probabilities": options}}}
    if usage:
        result["usage"] = {"input_tokens": 100, "output_tokens": 20}
    return result


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

    def test_missing_key_requires_review_without_network(self):
        with patch("urllib.request.build_opener", side_effect=AssertionError("network used")):
            answer = route("Fix the Dockerfile image build", CATALOGUE)
        self.assertEqual((answer["outcome"], answer["source"], answer["reason"], answer["usage"]["requests"]),
                         ("review", "validation", "missing_api_key", 0))

    def test_dry_run_with_key_never_uses_network(self):
        with patch("urllib.request.build_opener", side_effect=AssertionError("network used")):
            answer = route("Fix the Dockerfile image build", CATALOGUE, dry_run=True, api_key="fake-test-key")
        self.assertEqual((answer["source"], answer["skill_id"], answer["usage"]["requests"]),
                         ("lexical", "container-build", 0))

    def test_api_error_requires_review_without_exposing_key(self):
        with patch("urllib.request.build_opener", side_effect=OSError("offline")):
            answer = route("Fix the Dockerfile image build", CATALOGUE, api_key="secret-value")
        self.assertEqual((answer["outcome"], answer["source"], answer["reason"], answer["usage"]["requests"]),
                         ("review", "api", "api_unavailable", 1))
        self.assertIsNone(answer["usage"]["estimated_input_usd"])
        self.assertNotIn("secret-value", json.dumps(answer))

    def test_valid_jev_choice_and_invalid_distribution_requires_review(self):
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
        self.assertEqual((answer["source"], answer["skill_id"], answer["reason"]), ("api", None, "api_invalid_response"))

    def test_local_http_contract_never_sends_label_or_evaluation_metadata(self):
        with local_api(choice_response()) as received:
            report = evaluate([{"id": "private-case", "request": "Fix the Dockerfile image build",
                                "expected": "code-tests", "annotation": "private-label"}], CATALOGUE, api_key="fake-test-key")
        self.assertEqual(report["cases"][0]["predicted"], "container-build")
        self.assertEqual((report["summary"]["wrong_routes"], report["summary"]["api_requests"]), (1, 1))
        self.assertEqual(received[0]["state"], {"request": "Fix the Dockerfile image build"})
        self.assertNotIn("private-case", json.dumps(received))
        self.assertNotIn("private-label", json.dumps(received))
        self.assertNotIn("code-tests\"", json.dumps(received[0]["state"]))

    def test_local_http_uncertainty_missing_usage_and_invalid_schema(self):
        with local_api(choice_response(confidence=0.4, usage=False)):
            uncertain = route("Fix the Dockerfile image build", CATALOGUE, api_key="fake-test-key")
        self.assertEqual((uncertain["outcome"], uncertain["reason"], uncertain["usage"]["input_tokens"]),
                         ("review", "uncertain", None))
        with local_api(choice_response(model="jev-unsupported")):
            invalid = route("Fix the Dockerfile image build", CATALOGUE, api_key="fake-test-key")
        self.assertEqual((invalid["outcome"], invalid["reason"], invalid["probabilities"]),
                         ("review", "api_model_mismatch", {}))
        with local_api(b"not json"):
            malformed = route("Fix the Dockerfile image build", CATALOGUE, api_key="fake-test-key")
        self.assertEqual((malformed["outcome"], malformed["reason"]), ("review", "api_invalid_response"))

    def test_local_http_abstentions_and_timeout(self):
        for sentinel, expected in (("__review__", "review"), ("__no_skill__", "no_skill")):
            with self.subTest(sentinel=sentinel), local_api(choice_response(skill=sentinel)):
                answer = route("Request outside the catalogue", CATALOGUE, api_key="fake-test-key")
            self.assertEqual((answer["outcome"], answer["skill_id"], answer["reason"]), (expected, None, "model_choice"))
        with patch("urllib.request.build_opener", side_effect=TimeoutError("timed out")):
            answer = route("Fix the Dockerfile image build", CATALOGUE, api_key="fake-test-key")
        self.assertEqual((answer["outcome"], answer["reason"], answer["usage"]["requests"]),
                         ("review", "api_unavailable", 1))

    def test_invalid_catalogue_and_case_are_rejected(self):
        with self.assertRaisesRegex(InputError, "duplicate"):
            catalogue_from(CATALOGUE + [CATALOGUE[0]])
        with self.assertRaisesRegex(InputError, "each case"):
            evaluate([{"id": "x", "request": "Hi", "expected": "nonexistent"}], CATALOGUE, dry_run=True)
        with self.assertRaisesRegex(InputError, "distinct"):
            catalogue_from([{"id": "one", "description": "Description", "examples": ["repeat", "repeat"]}])
        with self.assertRaisesRegex(InputError, "--model"):
            route("Fix the Dockerfile image build", CATALOGUE, model="other-model")

    def test_golden_eval_reports_wrong_routes_and_reviews(self):
        cases = [{"id": "one", "request": "Fix the Dockerfile image build", "expected": "container-build"},
                 {"id": "two", "request": "Hi there, how are you?", "expected": "code-tests"}]
        summary = evaluate(cases, CATALOGUE, dry_run=True)["summary"]
        self.assertEqual((summary["cases"], summary["correct"], summary["accuracy"], summary["api_requests"]), (2, 1, 0.5, 0))
        self.assertEqual(summary["automatic_route_coverage"], {"numerator": 1, "denominator": 2})
        self.assertEqual(summary["route_recall"], {"numerator": 1, "denominator": 2})

    def test_eval_serialization_and_incomplete_cost(self):
        cases = [{"id": "one", "request": "Fix the Dockerfile image build", "expected": "container-build"},
                 {"id": "two", "request": "Hi there", "expected": "no_skill"}]
        with local_api(choice_response(usage=False)):
            report = evaluate(cases, CATALOGUE, api_key="fake-test-key")
        copied = json.loads(json.dumps(report))
        self.assertEqual(copied["summary"]["unknown_usage_cases"], 2)
        self.assertIsNone(copied["summary"]["estimated_input_usd"])
        self.assertEqual(copied["confusion"]["no_skill"]["container-build"], 1)
        self.assertEqual(copied["summary"]["api_requests"], 2)
        self.assertGreaterEqual(copied["summary"]["observed_latency_ms"], 0)

    def test_cli_dry_run_ignores_present_key_and_never_overwrites_report(self):
        env = os.environ.copy()
        env["TYPESAFE_API_KEY"] = "invalid value with spaces"
        cmd = [sys.executable, str(ROOT / "router.py"), "eval", "--dry-run", "--catalogue", str(ROOT / "data/catalogue.json"), "--dataset", str(ROOT / "data/own-36.jsonl")]
        first = subprocess.run(cmd, capture_output=True, text=True, env=env)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)["cases"], 36)
        self.assertNotIn(env["TYPESAFE_API_KEY"], first.stdout + first.stderr)
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder) / "existing.json")
            Path(target).write_text("keep")
            second = subprocess.run(cmd + ["--output", target], capture_output=True, text=True, env=env)
            self.assertEqual(second.returncode, 2)
            self.assertEqual(Path(target).read_text(), "keep")
            output = str(Path(folder) / "report.json")
            third = subprocess.run(cmd + ["--output", output], capture_output=True, text=True, env=env)
            self.assertEqual(third.returncode, 0, third.stderr)
            saved = json.loads(Path(output).read_text())
            self.assertEqual(saved["provenance"]["settings"]["dry_run"], True)
            self.assertEqual(len(saved["provenance"]["dataset_sha256"]), 64)
            self.assertEqual(len(saved["cases"]), 36)

    def test_cli_invalid_request_is_actionable_and_has_no_skill(self):
        run = subprocess.run([sys.executable, str(ROOT / "router.py"), "route", "--dry-run", "--catalogue", str(ROOT / "data/catalogue.json"), "--request", " "], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertEqual((json.loads(run.stdout)["outcome"], json.loads(run.stdout)["skill_id"]), ("invalid", None))
        self.assertIn("request must be nonempty", run.stderr)

    def test_cli_catalogue_error_and_unsupported_model(self):
        with tempfile.TemporaryDirectory() as folder:
            catalogue = Path(folder) / "catalogue.json"
            catalogue.write_text(json.dumps([{"id": "one", "description": "Description", "examples": []}]))
            cmd = [sys.executable, str(ROOT / "router.py"), "route", "--dry-run", "--request", "Fix Dockerfile"]
            invalid = subprocess.run(cmd + ["--catalogue", str(catalogue)], capture_output=True, text=True)
            self.assertEqual(invalid.returncode, 2)
            self.assertEqual((json.loads(invalid.stdout)["outcome"], json.loads(invalid.stdout)["skill_id"]), ("invalid", None))
            self.assertIn("examples must be", invalid.stderr)
            unsupported = subprocess.run(cmd + ["--catalogue", str(ROOT / "data/catalogue.json"), "--model", "other-model"], capture_output=True, text=True)
            self.assertEqual(unsupported.returncode, 2)
            self.assertIn("--model must be", unsupported.stderr)


if __name__ == "__main__":
    unittest.main()

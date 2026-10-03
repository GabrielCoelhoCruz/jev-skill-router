import hashlib
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

from router import InputError, catalogue_from, evaluate, evaluate_repeats, grade, route


ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = json.loads((ROOT / "data/catalogue.json").read_text())


@contextmanager
def local_api(reply, mode="normal"):
    class Captured(list):
        pass

    received = Captured()
    received.raw = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.raw.append(body)
            received.append(json.loads(body))
            if mode == "aborted_status":
                self.close_connection = True
                return
            body = json.dumps(reply).encode() if isinstance(reply, dict) else reply
            self.send_response(200)
            if mode == "truncated_chunk":
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                self.wfile.write(b'20\r\n{"model":')
                self.wfile.flush()
                self.close_connection = True
                return
            self.send_header("Content-Length", str(len(body) + 100 if mode == "aborted_length" else len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            if mode == "aborted_length":
                self.close_connection = True

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    received.endpoint = f"http://127.0.0.1:{server.server_port}/choice"
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        with patch("router.ENDPOINT", received.endpoint):
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
            evaluate([{"id": "other-case", "request": "Fix the Dockerfile image build",
                       "expected": "review", "annotation": "different-label"}], CATALOGUE, api_key="fake-test-key")
        self.assertEqual(report["cases"][0]["predicted"], "container-build")
        self.assertEqual((report["summary"]["wrong_routes"], report["summary"]["api_requests"]), (1, 1))
        self.assertEqual(received[0]["state"], {"request": "Fix the Dockerfile image build"})
        self.assertNotIn("private-case", json.dumps(received))
        self.assertNotIn("private-label", json.dumps(received))
        self.assertNotIn("code-tests\"", json.dumps(received[0]["state"]))
        self.assertEqual(received[0], received[1])

    def test_provider_payload_bytes_match_original_base(self):
        cases = [
            ("Fix the Dockerfile image build", CATALOGUE,
             "65d56108bca4d31f63c95ee4e62ed38e65dfd3e7f2ddc646058a40104c90eac1"),
            ("Crie testes para o analisador, sem mudar o CI.",
             [{"id": "code-tests", "description": "Add tests for code", "examples": ["Test a parser"]}],
             "76d54b0dd6b89773c4209a736d8dea4de3a3d54be52da1a8ab3a485390b7732c"),
        ]
        for request, catalogue, expected_hash in cases:
            with self.subTest(request=request), local_api(choice_response()) as received:
                route(request, catalogue, api_key="fake-test-key")
            payload = json.loads(received.raw[0])
            criteria = payload["questions"]["route"]["criteria"]
            self.assertEqual(criteria["__no_skill__"],
                             "No concrete task or artifact is requested; an ordinary answer or conversation needs no specialist workflow.")
            self.assertEqual(criteria["__review__"],
                             "A concrete task or artifact is requested but no listed skill supports its deliverable, or the goal is ambiguous or equally spans multiple skills.")
            criteria["__no_skill__"] = "An ordinary answer needs no specialist workflow."
            criteria["__review__"] = "The goal is ambiguous, several workflows are equally primary, or no listed skill supports this specialist task."
            self.assertEqual(hashlib.sha256(json.dumps(payload).encode()).hexdigest(), expected_hash)

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

    def test_cli_truncated_http_read_returns_review_and_eval_records_error(self):
        env = os.environ.copy()
        env["TYPESAFE_API_KEY"] = "fake-test-key"
        with local_api(b"", mode="truncated_chunk") as received:
            code = "import router; router.ENDPOINT=" + repr(received.endpoint) + "; raise SystemExit(router.main(['route', '--request', 'Fix the Dockerfile']))"
            run = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        answer = json.loads(run.stdout)
        self.assertEqual((answer["outcome"], answer["source"], answer["reason"], answer["usage"]["requests"]),
                         ("review", "api", "api_unavailable", 1))
        self.assertIsNone(answer["usage"]["input_tokens"])
        self.assertNotIn("fake-test-key", run.stdout + run.stderr)
        self.assertNotIn("Traceback", run.stderr)
        with tempfile.TemporaryDirectory() as folder, local_api(b"", mode="truncated_chunk") as received:
            dataset = Path(folder) / "cases.jsonl"
            output = Path(folder) / "report.json"
            dataset.write_text(json.dumps({"id": "one", "request": "Fix the Dockerfile", "expected": "review"}) + "\n")
            code = ("import router; router.ENDPOINT=" + repr(received.endpoint) +
                    "; raise SystemExit(router.main(['eval', '--dataset', " + repr(str(dataset)) +
                    ", '--output', " + repr(str(output)) + "]))")
            run = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            report = json.loads(output.read_text())
        self.assertEqual((report["summary"]["correct"], report["summary"]["api_failures"],
                          report["summary"]["unscored_errors"]), (0, 1, 1))
        self.assertEqual(report["cases"][0]["scored_action"], "api_unavailable")

    def test_adjacent_aborted_http_reads_and_invalid_json(self):
        for mode in ("aborted_length", "aborted_status"):
            with self.subTest(mode=mode), local_api(b"", mode=mode):
                answer = route("Fix the Dockerfile image build", CATALOGUE, api_key="fake-test-key")
            self.assertEqual((answer["outcome"], answer["reason"], answer["usage"]["requests"]),
                             ("review", "api_unavailable", 1))
            self.assertIsNone(answer["usage"]["output_tokens"])
        with local_api(b"not json"):
            malformed = route("Fix the Dockerfile image build", CATALOGUE, api_key="fake-test-key")
        self.assertEqual((malformed["outcome"], malformed["reason"]), ("review", "api_invalid_response"))

    def test_timeout_during_body_read_is_not_a_successful_review(self):
        class Response:
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, size):
                raise TimeoutError("body stalled")

        class Opener:
            def open(self, request, timeout):
                return Response()

        with patch("urllib.request.build_opener", return_value=Opener()):
            report = evaluate([{"id": "one", "request": "Fix CI and tests equally", "expected": "review"}],
                              CATALOGUE, api_key="fake-test-key")
        answer = report["cases"][0]["decision"]
        self.assertEqual((answer["outcome"], answer["source"], answer["reason"], answer["usage"]["requests"]),
                         ("review", "api", "api_unavailable", 1))
        self.assertEqual((report["summary"]["correct"], report["summary"]["api_failures"]), (0, 1))
        self.assertIsNone(answer["usage"]["input_tokens"])
        self.assertNotIn("fake-test-key", json.dumps(report))

    def test_rounded_distribution_is_normalized_without_silencing_invalid_data(self):
        with local_api(choice_response(skill="__review__", probability=0.99)):
            answer = route("Handle two unrelated tasks", CATALOGUE, api_key="fake-test-key")
        self.assertEqual((answer["outcome"], answer["source"], answer["reason"]),
                         ("review", "jev", "model_choice"))
        self.assertAlmostEqual(sum(answer["probabilities"].values()), 1.0)
        with local_api(choice_response(probability=0.94)):
            invalid = route("Fix the Dockerfile image build", CATALOGUE, api_key="fake-test-key")
        self.assertEqual((invalid["outcome"], invalid["reason"]), ("review", "api_invalid_response"))

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

    def test_grader_deterministic_correct_wrong_all_review_empty_and_invalid(self):
        correct = evaluate([{"id": "one", "request": "Fix the Dockerfile image build", "expected": "container-build"}],
                           CATALOGUE, dry_run=True)["cases"][0]
        wrong = {**correct, "id": "two", "expected": "code-tests", "correct": False}
        all_review = evaluate([{"id": "three", "request": "Fix the CI workflow and application tests equally.",
                                "expected": "review"}], CATALOGUE, dry_run=True)["cases"][0]
        labels = {entry["id"] for entry in CATALOGUE} | {"review", "no_skill"}
        planned = [("one", 1), ("two", 1), ("three", 1)]
        first = grade([correct, wrong, all_review], labels, planned)
        second = grade(json.loads(json.dumps([correct, wrong, all_review])), labels, planned)
        self.assertEqual(first, second)
        self.assertEqual((first["summary"]["cases"], first["summary"]["correct"],
                          first["summary"]["wrong_routes"], first["summary"]["unnecessary_reviews"]), (3, 2, 1, 0))
        self.assertEqual(grade([all_review], labels, [("three", 1)])["summary"]["correct"], 1)
        with self.assertRaisesRegex(InputError, "at least one"):
            grade([], labels, planned)
        with self.assertRaisesRegex(InputError, "invalid stored outcome"):
            grade([{**correct, "predicted": "unknown-skill"}], labels, [("one", 1)])

    def test_grader_rejects_missing_duplicate_or_wrong_repeat_observations(self):
        cases = [{"id": "one", "request": "Fix the Dockerfile image build", "expected": "container-build"},
                 {"id": "two", "request": "Hi there", "expected": "no_skill"}]
        report = evaluate_repeats(cases, CATALOGUE, None, repeats=2, dry_run=True)
        labels = {entry["id"] for entry in CATALOGUE} | {"review", "no_skill"}
        planned = [("one", 1), ("two", 1), ("one", 2), ("two", 2)]
        self.assertEqual((report["summary"]["planned_observations"], report["summary"]["planned_cases"],
                          report["summary"]["planned_repetitions"], len(report["plan"])), (4, 2, 2, 4))
        stored = json.loads(json.dumps(report))
        restored_plan = [(item["id"], item["repeat"]) for item in stored["plan"]]
        self.assertEqual(grade(stored["cases"], labels, restored_plan)["summary"]["correct"],
                         report["summary"]["correct"])
        with self.assertRaisesRegex(InputError, "planned case and repeat"):
            grade(report["cases"][:-1], labels, planned)
        with self.assertRaisesRegex(InputError, "planned case and repeat"):
            grade(report["cases"][:3] + [report["cases"][0]], labels, planned)
        with self.assertRaisesRegex(InputError, "planned case and repeat"):
            grade(report["cases"][:3] + [{**report["cases"][3], "repeat": 3}], labels, planned)
        with self.assertRaisesRegex(InputError, "planned case and repeat"):
            grade(report["cases"][:3] + [{**report["cases"][3], "repeat": []}], labels, planned)

    def test_api_error_is_not_counted_as_correct_review(self):
        with patch("urllib.request.build_opener", side_effect=OSError("offline")):
            report = evaluate([{"id": "one", "request": "Fix CI and tests equally", "expected": "review"}],
                              CATALOGUE, api_key="fake-test-key")
        self.assertEqual((report["summary"]["correct"], report["summary"]["api_failures"],
                          report["summary"]["unscored_errors"]), (0, 1, 1))
        self.assertEqual(report["confusion"]["review"]["api_unavailable"], 1)

    def test_repeats_make_distinct_requests_and_cluster_by_family(self):
        cases = [{"id": "a", "request": "Fix the Dockerfile image build", "expected": "container-build"},
                 {"id": "b", "request": "Build the Docker image", "expected": "container-build"}]
        with local_api(choice_response()) as received:
            report = evaluate_repeats(cases, CATALOGUE, {"a": "CD1", "b": "CD1"},
                                      repeats=3, api_key="fake-test-key")
        self.assertEqual((len(received), report["summary"]["cases"], report["summary"]["unique_cases"],
                          report["summary"]["repetitions"], report["summary"]["families"]), (6, 6, 2, 3, 1))
        self.assertEqual(report["case_variability"]["a"]["observed_actions"], ["container-build"] * 3)
        self.assertEqual(report["family_variability"]["CD1"]["changing_cases"], 0)
        with self.assertRaisesRegex(InputError, "repeats must"):
            evaluate_repeats(cases, CATALOGUE, None, repeats=4, dry_run=True)
        with self.assertRaisesRegex(InputError, "families must"):
            evaluate_repeats(cases, CATALOGUE, {"a": "CD1"}, repeats=3, dry_run=True)

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

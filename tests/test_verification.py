import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "skills/verify-jev-skill-router/scripts/verify.py"


class VerificationTests(unittest.TestCase):
    def test_real_cli_without_secret_preserves_evidence_after_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence = Path(folder) / "proof"
            env = dict(os.environ, TYPESAFE_API_KEY="dummy-key-must-not-be-used")
            command = [sys.executable, str(HELPER), "--repo", str(ROOT), "--evidence", str(evidence), "--feature", "route"]
            run = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)["live_requests"], 0)
            dry = json.loads((evidence / "dry-route.stdout").read_text())
            self.assertEqual((dry["source"], dry["skill_id"], dry["usage"]["requests"]), ("lexical", "sql-tuning", 0))
            without_key = json.loads((evidence / "no-key.stdout").read_text())
            self.assertEqual((without_key["outcome"], without_key["reason"]), ("review", "missing_api_key"))
            before = json.loads((evidence / "before-cleanup.json").read_text())
            after = json.loads((evidence / "after-cleanup.json").read_text())
            self.assertTrue(before["scratch_exists"])
            self.assertTrue(after["scratch_removed"])
            self.assertIn("dry-route.stdout", after["proof_sha256"])
            self.assertIn("verification denies network", (evidence / "deny-control.stderr").read_text())
            second = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(json.loads((evidence / "dry-route.stdout").read_text()), dry)

    def test_model_feature_reports_pinned_default_and_explicit_model(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence = Path(folder) / "proof"
            command = [sys.executable, str(HELPER), "--repo", str(ROOT), "--evidence", str(evidence), "--feature", "model"]
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            default = json.loads((evidence / "model-default-report.json").read_text())["provenance"]["settings"]["model"]
            explicit = json.loads((evidence / "model-explicit-report.json").read_text())["provenance"]["settings"]["model"]
            self.assertEqual((default, explicit), ("jev-1.13.0", "jev-1.14.0"))
            self.assertEqual(json.loads((evidence / "model-invalid.stdout").read_text())["outcome"], "invalid")

    @unittest.skipUnless((ROOT / ".git").exists(), "needs a git checkout to clone")
    def test_doctor_reports_new_untracked_file_as_dirty(self):
        with tempfile.TemporaryDirectory() as folder:
            checkout = Path(folder) / "checkout"
            subprocess.run(["git", "clone", "--quiet", str(ROOT), str(checkout)], check=True)
            command = [sys.executable, str(HELPER), "--repo", str(checkout), "--evidence", str(Path(folder) / "unused"), "--doctor"]
            clean = json.loads(subprocess.run(command, capture_output=True, text=True, check=True).stdout)["dirty"]
            (checkout / "new_module.py").write_text("")
            untracked = json.loads(subprocess.run(command, capture_output=True, text=True, check=True).stdout)["dirty"]
            self.assertEqual((clean, untracked), (False, True))
            self.assertFalse((Path(folder) / "unused").exists())


if __name__ == "__main__":
    unittest.main()

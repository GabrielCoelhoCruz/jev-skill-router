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


if __name__ == "__main__":
    unittest.main()

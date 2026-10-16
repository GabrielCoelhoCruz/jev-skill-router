#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description="Verify the real router CLI without a secret or network")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--feature", choices=("help", "route", "eval", "catalogue", "replay", "all"), default="all")
    parser.add_argument("--doctor", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    for name in ("router.py", "benchmark.py", "data/catalogue.json", "benchmark/summary.json"):
        if not (repo / name).is_file():
            parser.error(f"missing {name}; pass --repo with the router checkout root")
    if sys.version_info < (3, 11):
        parser.error("use Python 3.11 or newer")
    source = hashlib.sha256((repo / "router.py").read_bytes()).hexdigest()
    if args.doctor:
        print(json.dumps({"ready": True, "python": sys.version.split()[0], "router_sha256": source}))
        return 0
    evidence = args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    receipts = []
    with tempfile.TemporaryDirectory(prefix="jev-verify-") as folder:
        scratch = Path(folder)
        (scratch / "sitecustomize.py").write_text(
            "import sys\n"
            "def deny(event, args):\n"
            "    if event in ('socket.connect', 'socket.getaddrinfo'):\n"
            "        raise RuntimeError('verification denies network: ' + event)\n"
            "sys.addaudithook(deny)\n"
        )
        env = {key: os.environ[key] for key in ("PATH", "HOME", "SYSTEMROOT") if key in os.environ}
        env.update(PYTHONPATH=str(scratch), PYTHONDONTWRITEBYTECODE="1")

        def run(name, arguments, expected_exit=0, present_key=False):
            child_env = dict(env)
            if present_key:
                child_env["TYPESAFE_API_KEY"] = "invalid verification key with spaces"
            command = [sys.executable, *arguments]
            result = subprocess.run(command, cwd=repo, env=child_env, capture_output=True, text=True, timeout=60)
            (evidence / f"{name}.stdout").write_text(result.stdout)
            (evidence / f"{name}.stderr").write_text(result.stderr)
            receipts.append({"name": name, "command": command, "exit": result.returncode,
                             "expected_exit": expected_exit, "dummy_key_present": present_key})
            assert result.returncode == expected_exit, f"{name}: inspect {name}.stderr"
            return result.stdout

        try:
            denial = run("deny-control", ["-c", "import socket; socket.create_connection(('127.0.0.1', 9))"], 1)
            assert not denial
            assert "verification denies network: socket.getaddrinfo" in (evidence / "deny-control.stderr").read_text()
            if args.feature in ("all", "help"):
                text = run("help", ["router.py", "--help"])
                assert "Decide which skill to use; never execute it" in text
                text = run("route-help", ["router.py", "route", "--help"])
                assert "--dry-run" in text and "--catalogue" in text
            if args.feature in ("all", "route"):
                request = "Reduce latency of a slow SELECT"
                answer = json.loads(run("no-key", ["router.py", "route", "--request", request]))
                assert (answer["outcome"], answer["reason"], answer["usage"]["requests"]) == ("review", "missing_api_key", 0)
                answer = json.loads(run("dry-route", ["router.py", "route", "--dry-run", "--request", request], present_key=True))
                assert (answer["outcome"], answer["skill_id"], answer["source"], answer["usage"]["requests"]) == ("route", "sql-tuning", "lexical", 0)
            if args.feature in ("all", "eval"):
                dataset = scratch / "one.jsonl"
                dataset.write_text(json.dumps({"id": "public-example", "request": "Reduce latency of a slow SELECT", "expected": "sql-tuning"}) + "\n")
                report = scratch / "report.json"
                command = ["router.py", "eval", "--dry-run", "--dataset", str(dataset), "--output", str(report)]
                summary = json.loads(run("eval", command, present_key=True))
                assert (summary["cases"], summary["correct"], summary["api_requests"]) == (1, 1, 0)
                saved = json.loads(report.read_text())
                assert saved["cases"][0]["predicted"] == "sql-tuning"
                (evidence / "eval-report.json").write_bytes(report.read_bytes())
                before = report.read_bytes()
                run("eval-no-overwrite", command, 2)
                assert report.read_bytes() == before
            if args.feature in ("all", "catalogue"):
                catalogue = scratch / "catalogue.json"
                catalogue.write_text(json.dumps([{"id": "container-build", "description": "Repair a Docker image build", "examples": ["Fix a Docker multi-stage build"]}]))
                answer = json.loads(run("custom-catalogue", ["router.py", "route", "--dry-run", "--catalogue", str(catalogue), "--request", "Fix a Docker multi-stage build"]))
                assert (answer["outcome"], answer["skill_id"], answer["usage"]["requests"]) == ("route", "container-build", 0)
                catalogue.write_text("[]")
                text = run("invalid-catalogue", ["router.py", "route", "--dry-run", "--catalogue", str(catalogue), "--request", "Fix a Docker multi-stage build"], 2)
                assert json.loads(text)["outcome"] == "invalid"
            if args.feature in ("all", "replay"):
                text = run("replay", ["benchmark.py"])
                assert text.encode() == (repo / "benchmark/summary.json").read_bytes()
        finally:
            (evidence / "commands.json").write_text(json.dumps(receipts, indent=2) + "\n")
            (evidence / "before-cleanup.json").write_text(json.dumps({"scratch_exists": scratch.exists(), "files": sorted(p.name for p in evidence.iterdir()), "router_sha256": source}, indent=2) + "\n")
    assert not scratch.exists()
    proof = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence.iterdir() if p.is_file()}
    (evidence / "after-cleanup.json").write_text(json.dumps({"scratch_removed": True, "proof_sha256": proof}, indent=2) + "\n")
    print(json.dumps({"verified": args.feature, "commands": len(receipts), "live_requests": 0, "cleanup": "scratch removed; evidence retained"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

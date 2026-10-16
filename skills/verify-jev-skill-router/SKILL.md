---
name: verify-jev-skill-router
description: Verify Jev skill router CLI help, credential-free routing, lexical dry-run, custom catalogue, pinned model selection, evaluation output, and archived replay. Use after CLI changes or before reporting that these paths work.
---

# Verify Jev skill router without a secret

The user goal is to run the router without a secret. This skill uses Python 3.11+ and the standard library.
The CLI recommends a skill. It does not execute a skill or prove semantic accuracy.

## Launch

Use a fresh checkout of `GabrielCoelhoCruz/jev-skill-router`. There is no build, package install, server, or port to launch.
Run from its root. Set `SKILL` to this folder, whether it lives in the checkout or was copied to Capy Drive.

```sh
SKILL="$PWD/skills/verify-jev-skill-router"
python3 "$SKILL/scripts/verify.py" --repo "$PWD" --evidence "$HOME/.capy/work/jev-verify-unused" --doctor
```

## Doctor

The command above prints `"ready": true`, the Python version, the runtime SHA-256, the checkout `head`, and `dirty`.
Compare `head` with the commit you were asked to verify. A dirty checkout proves only its working tree.
`dirty` is true when a tracked file changed or a new untracked file exists. Files that `.gitignore` lists, such as `__pycache__/`, do not count.
The router's own `provenance.source_dirty` report field still ignores untracked files. Do not read one as the other.
It reads files without calling an API or creating the evidence directory.
If it fails, correct `--repo` or use Python 3.11+ before driving the CLI.

## Drive

Choose a fresh evidence path. The helper refuses an existing directory.
It removes configured credentials from child processes.
A Python audit hook in each Python child denies `socket.connect` and `socket.getaddrinfo`. That covers the TCP connection and DNS lookup that the router's `urllib` call makes. [features/README.md](features/README.md) lists what the hook does not cover.
Its denial control must fail before the selected feature runs. Dry-run also runs with an invalid dummy key present.

```sh
python3 "$SKILL/scripts/verify.py" --repo "$PWD" --evidence "$HOME/.capy/work/jev-verify-route-001" --feature route
```

Expect `"verified": "route"`, `"live_requests": 0`, and `"cleanup": "scratch removed; evidence retained"`.
The real CLI must return review with `missing_api_key` and zero requests without a key.
Dry-run must return `route`, `sql-tuning`, `lexical`, and zero requests for the public SELECT example.
Use `--feature all` to drive the six entries in [features/README.md](features/README.md).
This skill has no live-API option. A live measurement needs its own approved protocol and budget.
The map lists the paths this helper does not test. Report them as NOT TESTED.

## Evidence

Keep stdout, stderr, command arguments, exits, and JSON reports in the selected evidence directory.
`commands.json` records each executed command. `before-cleanup.json` and `after-cleanup.json` prove cleanup preserves the captured files.
The helper asserts literal outputs and saved file behavior. The replay entry checks byte equality with the existing historical summary.
That check is an integration smoke test, not a new accuracy audit or provider-authenticity proof.

## Cleanup

The helper removes only its temporary guard, catalogue, dataset, and report files, including after a failed assertion.
It starts no long-lived process. Inspect evidence after failures. Keep the evidence directory for review.
Check that `after-cleanup.json` names the surviving proof files after a successful run.

## Helpers

`scripts/verify.py` accepts `--feature help`, `route`, `eval`, `catalogue`, `model`, `replay`, or `all`.
Run the command above with the feature from the map. Use `--doctor` for a read-only check.
Use the `maintain-verification-skill` workflow when the CLI changes to keep this map current.

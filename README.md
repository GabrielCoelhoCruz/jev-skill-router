# Jev skill router

Choose a specialist workflow for a request without loading or executing a skill. This Python 3.11+ command-line tool reads a declarative catalogue of `id`, `description`, and short `examples`. It returns `route` with a skill ID, `no_skill`, `review`, or `invalid` for rejected CLI input. A successful decision includes P for every considered option and confidence. Jev supplies probabilities when available; offline lexical scores are normalized for display and are **not calibrated probabilities**.

The router uses Python's standard library only. It sends the request and public skill descriptions to [TypeSafe Jev](https://docs.typesafe.ai/api.md) when `TYPESAFE_API_KEY` is set, and uses a deterministic lexical fallback without a key or after an API error. `--dry-run` forces that fallback without network access, even with a key set. An API failure may result in a wrong lexical route; inspect `source` and `reason` before using a result. Neither route grants permission to execute a skill.

## Run locally

From the repository root:

```sh
python3 router.py route --dry-run --request "Speed up this SELECT using its execution plan"
python3 router.py eval --dry-run --dataset data/own-36.jsonl
python3 -m unittest discover -s tests -v
```

For a live decision, set `TYPESAFE_API_KEY` only in the process environment and omit `--dry-run`. The key is never accepted as a CLI argument, saved in reports, or included in errors. Only send requests and catalogue descriptions you are permitted to share with TypeSafe. A malformed request or catalogue gives an actionable stderr error and exit status 2; `route` also emits an `invalid` JSON decision. The default model is pinned to `jev-1.13.0`; `--model` accepts another Jev identifier. A response with a different model than requested falls back to lexical routing, so mutable aliases may not work.

The catalogue supports at most 253 skills in one Choice request, leaving two options for no skill and review. It does not prune larger catalogues. `CONTRACT.md` records the request, skill, decision, and evaluation shapes before implementation.

## Reproduce the evaluation

The dataset `data/own-36.jsonl` contains 36 manually labeled synthetic requests: 24 routes across 12 skills, six ordinary requests, and six review cases. The catalogue examples and evaluation prompts were written for this project. Run the evaluation and inspect every prediction:

```sh
python3 router.py eval --dry-run --dataset data/own-36.jsonl --output /tmp/own-baseline.json
# With TYPESAFE_API_KEY set in the process environment:
python3 router.py eval --dataset data/own-36.jsonl --output /tmp/own-jev.json
```

Output paths must not already exist. Without the key, the last command also uses the lexical fallback. The `summary` reports exact-outcome accuracy, wrong skill routes, total reviews, unnecessary reviews, fallbacks, API requests, token counts, and estimated input cost. The detailed JSON report records each expected label, prediction, distribution, confidence, and usage. Checked-in results are `data/baseline-own.json` and `data/jev-own.json`.

Measured on 2026-10-03, with the fixed catalogue and labels above:

| Dataset and method | Exact outcomes | Wrong skill routes | Reviews | Unnecessary reviews | API requests | Input/output tokens | Estimated input USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Own 36, Jev `jev-1.13.0`, one run | 36/36 (100%) | 0 | 6 | 0 | 36 | 34,678 / 5,604 | 0.001456476 |
| Own 36, lexical baseline | 27/36 (75%) | 1 | 7 | 5 | 0 | 0 / 0 | 0 |

The USD figure is calculated as `34,678 × $0.042 / 1,000,000` from [TypeSafe's advertised input rate](https://typesafe.ai/blog/introducing-system-one-models-and-jev). Its public pricing states that output tokens are free. This is an estimate, not a bill; it omits taxes and any account-specific terms. For failed API requests, usage is unknown and the report shows only a known-input lower bound, not a fabricated total.

These are synthetic prompts from the same authors who designed the catalogue. A single Jev run has no variance estimate. The perfect score does not validate real-world accuracy, calibration, adversarial resistance, large catalogues, or skill execution.

## Design trade-offs

- One Jev Choice covers the bounded catalogue in one API request. The 253-skill limit rules out larger catalogues unless the caller divides them.
- An API error falls back to a deterministic lexical decision. This preserves an offline path, but a wrong lexical route can be worse than abstaining; callers can check `source` and enforce their own policy.
- A line-oriented JSONL dataset accepts new test cases without changing Python code. GitHub Actions runs the offline tests without a key or non-stdlib packages.
- `--dry-run` guarantees no network even if a credential exists in the environment. It makes the lexical evaluation reproducible, but does not imply that live Jev output is deterministic.

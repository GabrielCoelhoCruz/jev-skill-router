# Model selection

## Sub-features
The default request model is the alias `jev-preview`. An explicit `--model` pins a concrete version such as `jev-1.14.0`, or names another alias such as `jev-latest`. Both reach the saved evaluation report as `provenance.settings.model`. A value that is neither a pinned `jev-X.Y.Z` version nor a lowercase alias returns actionable invalid input. The partial version `jev-1.14` is invalid.
Each decision carries two separate fields. `requested_model` is the model the HTTP body named. `served_model` is the concrete version the response named. Offline decisions have `null` in both.
## How to get to it (user POV)
Run `python3 router.py eval --dry-run --dataset path/to/cases.jsonl --output path/to/report.json`, with and without `--model jev-1.14.0`. Read `provenance.settings.model`, `provenance.source_commit`, `cases[0].decision.served_model` and `summary.served_models` in the report.
## Driving it with the CLI helper
Use `--feature model`. Expect `jev-preview` without `--model`, `jev-1.14.0` with it, and the checkout HEAD as `source_commit` in both saved reports. Expect `served_model: null`, `served_models: {}` and `unknown_served_model: 0` in both dry-run reports.
`route --dry-run --model 'jev latest'` and `route --dry-run --model jev-1.14` must exit 2, emit `invalid`, and name the `--model` rule on stderr.
## Gotchas
Dry-run sends nothing, so this proves CLI parsing and report provenance, not the model id sent over HTTP or the model that answers. `tests/test_router.py` covers the HTTP body and the reply check at the `route()` call with a local fake server, not through the CLI.
The reply check depends on the request. A pinned version must come back unchanged, else the decision is `review` with `api_model_mismatch` and the reported version in `served_model`. An alias must come back as a concrete `jev-X.Y.Z` version, else the decision is `review` with `api_model_unresolved` and `served_model: null`.
An alias moves without a code change. Pin a version with `--model` when results must stay comparable with an earlier run. Change the expected default here in the same commit that changes `MODEL` in `router.py`.

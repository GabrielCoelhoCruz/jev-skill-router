# Model selection

## Sub-features
The default pinned model and an explicit `--model` reach the saved evaluation report. An identifier outside the Jev pattern returns actionable invalid input.
## How to get to it (user POV)
Run `python3 router.py eval --dry-run --dataset path/to/cases.jsonl --output path/to/report.json`, with and without `--model jev-1.14.0`. Read `provenance.settings.model` and `provenance.source_commit` in the report.
## Driving it with the CLI helper
Use `--feature model`. Expect `jev-1.13.0` without `--model`, `jev-1.14.0` with it, and the checkout HEAD as `source_commit` in both saved reports.
`route --dry-run --model 'jev latest'` must exit 2, emit `invalid`, and name the `--model` rule on stderr.
## Gotchas
Dry-run sends nothing, so this proves CLI parsing and report provenance, not the model id sent over HTTP. Unit tests cover the request body with a local fake server.
Change the expected default here in the same commit that changes `MODEL` in `router.py`. Pin version IDs, never an alias such as `jev-latest`: aliases move without a code change.

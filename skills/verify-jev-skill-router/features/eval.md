# Evaluation

## Sub-features
Evaluation prints aggregate results and saves a detailed report. An existing output file remains unchanged.
## How to get to it (user POV)
Use `python3 router.py eval --dry-run --dataset path/to/cases.jsonl --output path/to/report.json`.
## Driving it with the CLI helper
Use `--feature eval`. The helper creates one original public example and expects one correct observation, zero API requests, and saved `sql-tuning`.
The second write exits 2. The helper compares the existing report bytes and preserves the first report as `eval-report.json`.
## Gotchas
This one-case smoke test does not measure general accuracy. The helper removes its dataset and output from scratch, not the preserved evidence.

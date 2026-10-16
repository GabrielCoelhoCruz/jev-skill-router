# Routing

## Sub-features
Routing without a key returns review. Explicit dry-run selects a lexical recommendation even with a configured key.
## How to get to it (user POV)
Run `python3 router.py route --dry-run --request 'Reduce latency of a slow SELECT'`.
## Driving it with the CLI helper
Use `--feature route`. Expect `sql-tuning` from dry-run and `missing_api_key` without credentials, each with zero requests.
## Gotchas
The helper removes a real configured key, then uses an invalid dummy key only for dry-run. A recommendation does not execute SQL.

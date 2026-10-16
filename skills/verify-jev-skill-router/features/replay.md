# Archived replay

## Sub-features
The replay checks frozen files and prints the archived summary without credentials or API use.
## How to get to it (user POV)
Run `python3 benchmark.py` from a checkout with the original benchmark files.
## Driving it with the CLI helper
Use `--feature replay`. Expect exit 0 and stdout byte-identical to `benchmark/summary.json`, with the network denial control active.
## Gotchas
These are known synthetic observations, not fresh heldout results. The replay pins the measured source and rejects a changed runtime.
Preserve that history when changing production code. Do not relabel historical scores as new measurements.

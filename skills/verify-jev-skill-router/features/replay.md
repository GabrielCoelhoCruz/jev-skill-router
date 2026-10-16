# Archived replay

## Sub-features
The replay checks frozen files and prints the archived summary without credentials or API use.
## How to get to it (user POV)
Run `python3 benchmark.py` from a checkout with the original benchmark files.
## Driving it with the CLI helper
Use `--feature replay`. Expect exit 0 and stdout byte-identical to `benchmark/summary.json`, with the network denial control active.
## Gotchas
These are known synthetic observations, not fresh heldout results. They came from `router.py` SHA-256 `cff71463…` with the pinned model `jev-1.13.0`; the summary names both. The replay pins the archive, corpus and catalogue bytes. It no longer requires the current `router.py` to equal that measured runtime, because the default model changed after the measurement.
The archive records predate `requested_model` and `served_model`. The replay rejects a record that carries them, so the archive cannot be relabelled as a `jev-latest` run. Do not relabel historical scores as new measurements.

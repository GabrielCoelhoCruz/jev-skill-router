# Help

## Sub-features
The top-level help names route and eval. Route help lists the catalogue and dry-run flags.
## How to get to it (user POV)
Run `python3 router.py --help` and `python3 router.py route --help` from the checkout root.
## Driving it with the CLI helper
Use `--feature help`. Expect exit 0 and the description `Decide which skill to use; never execute it`.
## Gotchas
Help does not validate credentials or prove API access. The helper saves both help outputs.

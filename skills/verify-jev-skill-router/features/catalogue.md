# Custom catalogue

## Sub-features
A valid catalogue supplies skill descriptions and examples. An empty catalogue returns actionable invalid input.
## How to get to it (user POV)
Pass `--catalogue path/to/catalogue.json` to `python3 router.py route --dry-run --request 'Fix a Docker multi-stage build'`.
## Driving it with the CLI helper
Use `--feature catalogue`. Expect `route` with `container-build` and zero API requests from a one-skill catalogue.
An empty catalogue must exit 2 and emit `invalid` in stdout.
## Gotchas
The catalogue is data, not executable commands. The helper creates and removes its own catalogue.

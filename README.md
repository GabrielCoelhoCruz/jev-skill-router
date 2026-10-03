# Jev skill router

Choose a specialist workflow for a request without loading or executing a skill. This Python 3.11+ command-line tool uses a declarative catalogue with an `id`, a `description`, and short `examples` for each skill. It returns `route` with a skill ID, `no_skill`, `review`, or `invalid` for rejected CLI input. A route is a recommendation, never permission to execute the skill.

With `TYPESAFE_API_KEY` in the process environment, the router sends the request and catalogue descriptions to [TypeSafe Jev](https://docs.typesafe.ai/api.md). A missing key, failed request, mismatched model, or invalid response produces `review`, rather than a lexical route. `--dry-run` is a separate, network-free lexical baseline, even when a key is set. The `source` and `reason` fields explain the decision. Jev probabilities represent option mass, and `confidence` is a concentration value. Neither is calibrated correctness. Dry-run scores are normalized for display and are not model probabilities.

## Run locally

From the repository root:

```sh
python3 router.py route --dry-run --request "Speed up this SELECT using its execution plan"
python3 router.py eval --dry-run --dataset data/own-36.jsonl --output /tmp/router-offline.json
python3 -m unittest discover -s tests -v
```

For a live decision, set `TYPESAFE_API_KEY` only in the process environment and omit `--dry-run`. Do not send requests or catalogue descriptions that you cannot share with TypeSafe. The key is not accepted as a CLI argument or saved in reports. A malformed request, catalogue, or model identifier gives an actionable stderr error and exit code 2; `route` also emits an `invalid` JSON decision. The default model is `jev-1.13.0`; `--model` accepts another Jev identifier, but the response must name the requested model. The catalogue supports at most 253 skills per Choice request, including two additional abstention options.

An offline caller that previously relied on the implicit lexical fallback must now pass `--dry-run`. A live caller must treat `review` as a request for human assessment, including after API failure. Do not turn that result into an automatic route.

## Evaluate a dataset

The JSONL dataset contains one object per line with `id`, `request`, and `expected`. The expected value is a skill ID, `no_skill`, or `review`. The router sends only `request` and the public catalogue to Jev. The CLI prints aggregate metrics and, with `--output`, writes a reusable JSON report without overwriting an existing file:

```sh
python3 router.py eval --dry-run --dataset data/own-36.jsonl --output /tmp/router-offline.json
# With TYPESAFE_API_KEY in the process environment, omit --dry-run for a bounded live run.
python3 router.py eval --dataset path/to/dev.jsonl --metadata path/to/dev-metadata.json --repeats 3 --output /tmp/router-dev.json
```

The report includes each expected and observed action, source, reason, distribution, usage, wall latency, a full confusion matrix, and run provenance. Provenance includes the source commit, model, catalogue, dataset and metadata SHA-256, and a config hash containing the router source hash. Commit the candidate before running the final comparison so its report names the candidate commit. All metrics use the number of case observations as the denominator unless stated otherwise. Three repeats of 60 cases produce 180 observations, not 180 independent cases. `case_variability` and `family_variability` group decisions by case and family; the metadata is read locally and is never sent to Jev. `correct` counts exact labels, including justified review; an API or credential error is not a correct review. `wrong_routes` counts a predicted skill ID that differs from the expected action. `unnecessary_reviews` counts valid review when a skill or `no_skill` was expected. `automatic_route_coverage` is predicted skill routes over all observations; `route_recall` is correctly selected skills over observations expected to select a skill. API failures and invalid responses are separate counts. Unknown token usage makes total input cost incomplete; the known-input figure is only a lower bound. The published input rate is $0.042 per million tokens; output tokens are not included in that estimate. Latency includes the CLI's routing work, not only the model.

`data/own-36.jsonl` and its checked-in reports are a small synthetic demonstration written alongside the catalogue. Its previous 36/36 live result does not validate production routing. For a comparative study, use identical development requests, model, catalogue, and policy settings on baseline and candidate. Run three independent repeats, document at most two one-hypothesis adjustment rounds, and do not retry or cherry-pick responses. Cache only identical model and request hashes; the CLI does not cache. If the baseline already reaches 95% accuracy, prioritize lower cost and latency without harming correct actions. Keep a separately authored final set sealed until the candidate commit and configuration are frozen. Report the final result separately, without tuning after seeing it. The [routing contract](CONTRACT.md) fixes these definitions before the development run.

The runtime uses only Python's standard library. GitHub Actions runs offline tests without a key. Deterministic local HTTP tests check the request and response contract; they do not establish Jev's routing accuracy.

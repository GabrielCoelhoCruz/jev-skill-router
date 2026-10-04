# Jev skill router

Choose a specialist workflow for a request without loading or executing a skill. This Python 3.11+ command-line tool uses a declarative catalogue with an `id`, a `description`, and short `examples` for each skill. It returns `route` with a skill ID, `no_skill`, `review`, or `invalid` for rejected CLI input. A route is a recommendation, never permission to execute the skill.

With `TYPESAFE_API_KEY` in the process environment, the router sends the request and catalogue descriptions to [TypeSafe Jev](https://docs.typesafe.ai/api.md). A missing key, failed request, mismatched model, or invalid response produces `review`, rather than a lexical route. `--dry-run` is a separate, network-free lexical baseline, even when a key is set. The `source` and `reason` fields explain the decision. Jev probabilities represent option mass, and `confidence` is a concentration value. Neither is calibrated correctness. Dry-run scores are normalized for display and are not model probabilities.

The router accepts a Jev probability sum within 0.02 of one and normalizes the returned distribution. This handles small rounding errors; larger schema errors still require review.

## Scope and evidence

The published-main runtime at commit `37a05e2ad3edb145f47ccaffdbc151c5b37856d0` keeps the original catalogue, model, thresholds, and provider prompt. Its source SHA-256 is `cff71463063cfc572f935feaf67fb03e5cc30d9469f25c59cbcf08d0cdc5eee2`. Its failure handling and evaluation differ from the original base, although local fake-server checks found identical provider request bytes. This branch adds a benchmark and documentation without changing that runtime.

On October 3, 2026, that exact published-main runtime selected the expected action in **347/360** archived live observations of 120 previously used synthetic requests repeated three times. Codex agents produced the requests and labels under Gabriel's ownership; these are not human judgments. It selected the correct skill in 285/288 skill-labeled observations and routed a skill on 294/360 observations. Nine wrong routes selected a skill on three unique review-labeled requests, each repeated three times. None chose the wrong skill for a skill-labeled request. Three unnecessary reviews came from one unique skill-labeled request repeated three times.

The three repeat scores were 116/120, 115/120, and 116/120. The 360 archived attempts reported valid decisions with zero operational failures. Six separately authored ordinary-answer requests produced six `no_skill` answers, but they do not enter the 360-observation score. The weak lexical overlap comparator scored 31/120 on the same 120 requests, with no API calls. It is not a best-free baseline.

The original 120 requests are known from an earlier evaluation. They are not fresh heldout data, human-labeled traffic, or evidence of production accuracy. The agents that authored the data and the first technical reviewer belong to the Codex model family. A later review of the decision trail by another model family cannot turn the labels into independent human ground truth. The 60 paired families and three repeats are correlated. A fixed-seed family-resampling interval for the exact-action rate is 91.94% to 99.72%; that interval describes this synthetic corpus, not production traffic.

Observed routing latency was 360.284 ms at P50 and 421.007 ms at P95. Returned usage for the 360 attempts was complete: 350,784 input tokens and 56,027 output tokens. At TypeSafe's [published Jev 1.13 input rate](https://docs.typesafe.ai/models.md) of $0.042 per million input tokens, the input-only estimate is $0.014732928, not an invoice. Total charged cost is not established here. The six controls used another 5,752 input tokens, or $0.000241584 at the same rate. The agent model runs on Gabriel's Codex subscription; no numerical agent-model bill is claimed.

The separate prompt-optimization experiment at `b5dc848a0a985b0c6135ae1190b29d5d7ba59541` failed its declared quality goal on a synthetic final set. Against base `fcbde53efe0e7ec871f171a268e97b7402ba10ae`, that exact experimental head had 351/360 versus 341/360 exact actions and 3 versus 9 wrong routes. But unnecessary reviews rose from 2/288 to 3/288, and correct skill choices fell from 286/288 to 285/288. Those are correlated synthetic observations, not production validation. The prompt change is excluded here. Neither historical score belongs to the published-main runtime measured above. This branch makes no semantic-routing improvement claim.

## Replay the measured results offline

`benchmark/PROTOCOL.md` froze the plan and six ordinary controls before the live calls. `benchmark/known-120.jsonl` and `benchmark/metadata.json` preserve the owner-original corpus bytes. `benchmark/live-360.jsonl` and `benchmark/ordinary-6-results.jsonl` hold sanitized decisions and latency for each attempted request; they contain no credentials, headers, or raw HTTP bodies. The committed `benchmark/summary.json` comes from the command below.

```sh
python3 benchmark.py > /tmp/jev-main-replay.json
cmp benchmark/summary.json /tmp/jev-main-replay.json
python3 -m unittest discover -s tests -v
```

Replay needs no key or network. It pins the runtime, catalogue, corpus, metadata, and default archived observation hashes. It rejects a missing, duplicate, unexpected, or zero-attempt observation instead of shrinking the denominator. For alternate `--live` files, it checks that recorded choices agree with maximal option probabilities, the frozen 0.55 thresholds, and the stored outcome and reason. `uncertain` reviews remain valid when a maximal skill option misses either threshold. It recomputes exact actions, skill selection, wrong routes, ordinary `no_skill` controls, usage, latency, per-repeat scores, and fixed-seed family variability. Tests remove and duplicate records and reject an impossible 360/360 rewrite that retains the original probabilities.

The validation proves internal consistency, not provider authenticity. A caller could rewrite actions and probabilities together. The records lack per-call timestamps and provider response IDs. The live runner froze the runtime hash and wrote each decision after an attempt, but a saved record cannot cryptographically prove the provider response. The ordinary controls have a separate denominator of six.

To make **new** live calls, review the requests and catalogue before sending them to TypeSafe. The following command makes 360 planned calls, three repetitions of each of the 120 known synthetic requests, with no retry or cache. It writes a new CLI report, not the archived streaming JSONL records, and its scores may differ from the October 3 run.

```sh
python3 router.py eval --dataset benchmark/known-120.jsonl --metadata benchmark/metadata.json --repeats 3 --output /tmp/jev-new-live.json
```

Set `TYPESAFE_API_KEY` in the process environment before this command. Do not use `--dry-run` for live measurement. `router.py eval --dry-run` remains a network-free lexical demonstration.

## Run locally

For CLI verification without a secret, use [the offline verification skill](skills/verify-jev-skill-router/SKILL.md). Its helper strips configured credentials, denies network access, drives the real CLI, and preserves command outputs after cleanup. The feature map covers help, routing, evaluation files, custom catalogues, and archived replay.

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

The report includes each expected and observed action, source, reason, distribution, usage, wall latency, a full confusion matrix, and run provenance. Provenance includes the source commit, model, catalogue, dataset and metadata SHA-256, and a config hash containing the router source hash. Commit the candidate before a comparison so its report names the candidate commit. The `plan` lists every expected case ID and repeat. The grader rejects a missing, duplicate, or unexpected observation instead of shrinking the denominator. To regrade a saved report, pass its `cases` and `plan` to `grade` after converting each plan object to an `(id, repeat)` tuple. All metrics use planned observations as the denominator unless stated otherwise. Three repeats of 60 cases produce 180 observations, not 180 independent cases. `case_variability` and `family_variability` group decisions by case and family; the metadata is read locally and is never sent to Jev. `correct` counts exact labels, including justified review; an API or credential error is not a correct review. `wrong_routes` counts a predicted skill ID that differs from the expected action. `unnecessary_reviews` counts valid review when a skill or `no_skill` was expected. `automatic_route_coverage` is predicted skill routes over all observations; `route_recall` is correctly selected skills over observations expected to select a skill. API failures and invalid responses are separate counts. Unknown token usage makes total input cost incomplete; the known-input figure is only a lower bound. The published input rate is $0.042 per million tokens; output tokens are not included in that estimate. Latency includes the CLI's routing work, not only the model.

`data/own-36.jsonl` and its checked-in reports are a small synthetic demonstration written alongside the catalogue. Its previous 36/36 live result does not validate production routing. For a future comparative study, use identical development requests, model, and catalogue. Run independent repeats, do not retry or cherry-pick responses, and keep an independent final set out of tuning. The CLI does not cache. The [routing contract](CONTRACT.md) defines the metrics and failure accounting.

The runtime uses only Python's standard library. GitHub Actions runs offline tests without a key. Deterministic local HTTP tests check the request and response contract; they do not establish Jev's routing accuracy.

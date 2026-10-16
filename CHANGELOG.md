# Changelog

## Unreleased

- Send `jev-preview` by default. `--model jev-X.Y.Z` still pins one version, `--model jev-latest` names the stable alias, and partial versions such as `jev-1.14` or versions with non-ASCII digits are rejected.
- Keep the concrete `served_model` of a response rejected as `api_invalid_response`. The model check now runs before the schema check.
- Add `requested_model` and `served_model` to every decision. A pinned request still rejects another version (`api_model_mismatch`). An alias request accepts a concrete version and rejects a reply without one (`api_model_unresolved`).
- Count `served_models` and `unknown_served_model` in evaluation summaries.
- Keep the archived `jev-1.13.0` replay byte-identical. The replay no longer requires the current `router.py` to equal the measured runtime, but it refuses to run when the lexical comparator source differs from the measured commit.

## 0.1.0 (2026-10-03)

- Add a standard-library Python router with Jev Choice and deterministic offline fallback.
- Add a labeled, reproducible JSONL evaluation using original synthetic requests.
- Add offline unit tests and GitHub Actions.

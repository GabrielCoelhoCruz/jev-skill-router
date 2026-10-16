# Changelog

## Unreleased

- Send `jev-latest` by default. `--model jev-X.Y.Z` still pins one version, and partial versions such as `jev-1.14` are rejected.
- Add `requested_model` and `served_model` to every decision. A pinned request still rejects another version (`api_model_mismatch`). An alias request accepts a concrete version and rejects a reply without one (`api_model_unresolved`).
- Count `served_models` and `unknown_served_model` in evaluation summaries.
- Keep the archived `jev-1.13.0` replay byte-identical. The replay no longer requires the current `router.py` to equal the measured runtime.

## 0.1.0 (2026-10-03)

- Add a standard-library Python router with Jev Choice and deterministic offline fallback.
- Add a labeled, reproducible JSONL evaluation using original synthetic requests.
- Add offline unit tests and GitHub Actions.

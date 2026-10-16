# CLI feature map

Run `scripts/verify.py` as documented in [the verification skill](../SKILL.md).
Each feature uses real CLI subprocesses with credentials removed and network denied.

| Feature | User goal | Helper selection |
| --- | --- | --- |
| [Help](help.md) | Find supported flags without a secret | `--feature help` |
| [Routing](route.md) | Get a safe decision offline | `--feature route` |
| [Evaluation](eval.md) | Save results without overwriting proof | `--feature eval` |
| [Catalogue](catalogue.md) | Use a valid custom catalogue | `--feature catalogue` |
| [Model selection](model.md) | Know which pinned model a report used | `--feature model` |
| [Replay](replay.md) | Reproduce archived evidence offline | `--feature replay` |

## Not tested by this helper

These paths are NOT TESTED here. Report them as NOT TESTED, never as passing, when this helper is the only proof.

- Live routing and live evaluation with a real `TYPESAFE_API_KEY`. They need their own approved protocol and budget.
- The model id and request body sent over HTTP. Only the offline unit tests cover them, with a local fake server.
- `eval --repeats` and `eval --metadata` family reports.
- Accuracy on any dataset. The one-case evaluation is a smoke test.

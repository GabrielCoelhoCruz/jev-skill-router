# CLI feature map

Run `scripts/verify.py` as documented in [the verification skill](../SKILL.md).
Each feature uses real CLI subprocesses with credentials removed and network denied.

| Feature | User goal | Helper selection |
| --- | --- | --- |
| [Help](help.md) | Find supported flags without a secret | `--feature help` |
| [Routing](route.md) | Get a safe decision offline | `--feature route` |
| [Evaluation](eval.md) | Save results without overwriting proof | `--feature eval` |
| [Catalogue](catalogue.md) | Use a valid custom catalogue | `--feature catalogue` |
| [Replay](replay.md) | Reproduce archived evidence offline | `--feature replay` |

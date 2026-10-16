# CLI feature map

Run `scripts/verify.py` as documented in [the verification skill](../SKILL.md).
Each feature uses real CLI subprocesses with credentials removed. In those Python children, an audit hook denies `socket.connect` and `socket.getaddrinfo`.

| Feature | User goal | Helper selection |
| --- | --- | --- |
| [Help](help.md) | Find supported flags without a secret | `--feature help` |
| [Routing](route.md) | Get a safe decision offline | `--feature route` |
| [Evaluation](eval.md) | Save results without overwriting proof | `--feature eval` |
| [Catalogue](catalogue.md) | Use a valid custom catalogue | `--feature catalogue` |
| [Model selection](model.md) | Know which model a report requested, and that offline paths report no served model | `--feature model` |
| [Replay](replay.md) | Reproduce archived evidence offline | `--feature replay` |

## Not tested by this helper

These paths are NOT TESTED here. Report them as NOT TESTED, never as passing, when this helper is the only proof.

- Live routing and live evaluation with a real `TYPESAFE_API_KEY`. They need their own approved protocol and budget.
- The model id and request body sent over HTTP. `tests/test_router.py` covers them at the `route()` call with a local fake server: a byte pin of the pinned `jev-1.13.0` body, a default body that differs only by `"model": "jev-latest"`, an explicit `jev-1.14.0` that must reach the body and match the reply, and alias replies with and without a concrete version. The CLI path from `--model` to the HTTP body has no test.
- The `served_model` of a real TypeSafe response, and which version `jev-latest` resolves to on a given day. Only a live call can show them.
- Network isolation of the host. The hook loads through `sitecustomize` in Python children only. It does not deny UDP `sendto`, `socket.gethostbyname`, `python -I` children, or processes that are not Python.
- `eval --repeats` and `eval --metadata` family reports.
- Accuracy on any dataset. The one-case evaluation is a smoke test.

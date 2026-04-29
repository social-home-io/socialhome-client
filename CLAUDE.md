# CLAUDE.md — socialhome-client

Instruction file for Claude Code. Read before editing.

## What this library is

Thin async client for the Social Home HTTP + WebSocket API. Consumed
by the Home Assistant integration at `social-home-io/ha-integration`.
Spec: §6 of `spec_work.md` in the Social Home meta-repo.

## Hard rules

- **Python 3.13 floor.** HA Core runs on 3.13. Do not require 3.14
  syntax (PEP 695 generic syntax is fine; match/case is fine;
  `f'{x=}'` is fine — don't adopt newer grammar for its own sake).
- **Never import from `social_home` (core).** This library is stand-
  alone. Its only runtime dependency is `aiohttp>=3.9`.
- **All I/O is async.** No `time.sleep`, no blocking calls.
- **All imports at the top of the file.** Only `if TYPE_CHECKING:`
  exceptions; no inline imports inside functions.
- **Tests are plain `async def test_xxx()` functions** — no
  `TestXxx` classes. One test file per module, matching tree.
- **All domain exceptions descend from `SHClientError`.** Auth =
  `SHAuthError`, not-found = `SHNotFoundError`. Every HTTP helper
  raises one of these on non-2xx.
- **Keep the surface small.** The spec (§6.1) lists the method
  inventory. Adding a convenience wrapper on the client is fine;
  adding a whole new subsystem needs a spec update first.
- **Typed dataclasses only.** Responses deserialise into
  `@dataclass` objects from `models.py`. No untyped `dict`s leak
  out of the client.

## Layout

```
socialhome_client/
  __init__.py          # public re-exports
  client.py            # SocialHomeClient
  ws_manager.py        # SocialHomeWsManager
  models.py            # typed response dataclasses
  exceptions.py        # SHClientError hierarchy
tests/                 # pytest tree mirroring the module tree
```

## Testing

```sh
pip install -e .[dev]
pytest                       # ≥85 % branch coverage gate
ruff check socialhome_client/ tests/
mypy socialhome_client/
```

Tests use `aioresponses` to stub HTTP and a fake `aiohttp.ClientWebSocketResponse`
for WS. No real network. No sockets.

## Keep docs in sync

`docs/` is the public reference for the library's design. Treat the
matching doc file as part of the same change:

- **Added a new resource or method on `SocialHomeClient`?** Update
  the resource table in `docs/architecture.md` and, if the README's
  usage example is affected, update the example block too.
- **Changed `SocialHomeWsManager`'s reconnect schedule, heartbeat,
  or connect timeout?** Update the constants block and the sequence
  diagram in `docs/architecture.md`. The CHANGELOG mentions of these
  numbers should match the doc.
- **Changed the exception hierarchy** (new `SHClient*Error`,
  changed status mapping)? Update `docs/architecture.md` and the
  "One exception hierarchy" section in `docs/principles.md`.
- **Changed the test strategy** (coverage gate, mock approach,
  shared fixtures)? Update `docs/testing.md` so the commands and
  numbers there match `pyproject.toml`.
- **Touched a §6 invariant** (raised the Python floor, added a
  runtime dependency, started importing from core, removed type
  hints from a public surface)? Update `docs/principles.md` AND
  flag the change in the PR description for explicit reviewer
  sign-off.
- **Added a new top-level doc file under `docs/`?** Link it from
  `docs/README.md` and from the repo-root `README.md` under
  "Documentation".

Reviewer checklist: if a PR adds a public method, changes the WS
behaviour, changes an exception, or shifts the test strategy and the
docs aren't touched, push back. Incremental accuracy beats big-bang
rewrites.

## Releasing

CalVer without a ``v`` prefix — tags look like ``2026.4.22`` or
``2026.4.22.1`` for same-day patch releases. The version in
``pyproject.toml`` is dynamic (``hatch-vcs``); do not edit it.

```sh
git tag 2026.4.22
git push origin 2026.4.22
```

GitHub Actions picks up the tag, builds the wheel + sdist, and
publishes to PyPI via OIDC trusted publishing.

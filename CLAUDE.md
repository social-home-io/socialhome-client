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

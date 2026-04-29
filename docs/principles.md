# Design principles

`socialhome-client` is a thin async client for the Social Home HTTP +
WebSocket API. These principles are why it stays thin. Distilled from
§6 of `spec_work.md` plus the existing `CLAUDE.md` / `AGENTS.md` rules.

## Standalone of the core

The library never imports from `social_home` (the core application).
Its only runtime dependency is `aiohttp>=3.9`. This is what lets it
ship to PyPI as `socialhome-client` and install cleanly inside Home
Assistant Core — the integration imports it without dragging in the
core's transitive graph.

## Python 3.13 floor

Home Assistant Core runs on Python 3.13. The library matches that
floor and does not require 3.14 grammar. Newer syntax (PEP 695
generics, `match/case`, `f'{x=}'`) is fine; bumping the floor is
not — it would lock HA out.

## Async everywhere

All I/O is `async def`. No `time.sleep`, no synchronous file or socket
work. The integration runs inside HA's event loop; a blocking call
here stalls the entire HA process.

## Typed responses, not `dict`s

Every HTTP method on the client returns a frozen `@dataclass` from
`models.py` (or `None` for void operations). Raw `dict[str, Any]`
never crosses the public boundary. Callers get IDE completion,
mypy coverage, and stable shapes that survive backend evolution.

## Feature-grouped resources

The client groups methods under feature resources rather than a flat
surface. `c.me.get()`, `c.shopping.add(...)`, `c.bot.create(...)`,
`c.federation.set_base(...)` — the structure mirrors how a contributor
thinks about the API. Each resource is its own class
(`_MeResource`, `_ShoppingResource`, …) wired up once on the parent
client and exposed as a property.

## One exception hierarchy

All domain failures descend from `SHClientError`. Auth failures
(HTTP 401) raise `SHAuthError`; missing resources (HTTP 404) raise
`SHNotFoundError`; everything else raises `SHClientError` with the
HTTP status code attached. The HA integration's coordinator maps
`SHAuthError` → `ConfigEntryAuthFailed` and any other
`SHClientError` → `UpdateFailed`. Adding a new exception subclass is
a public-API change.

## Imports stay at the top

All imports live at the top of every module. The only exception is
`if TYPE_CHECKING:` blocks for type-only circular dependencies. No
inline imports inside functions, no lazy loaders.

## Spec-driven public surface

The library's public method inventory comes from §6.1 of
`spec_work.md`. Adding a new method is fine when it covers an existing
spec endpoint; introducing a whole new subsystem requires a spec
update first. This keeps the client predictable for the integration
that consumes it.

## Test boundary, not production boundary

Tests mock at the test boundary — `aioresponses` for HTTP and a fake
`aiohttp.ClientWebSocketResponse` for WS. The client itself never
ships env-var-gated stubs or test-only branches. Production code
always uses the real `aiohttp.ClientSession`.

## Spec references

- §6 — repository overview
- §6.1 — full HTTP method inventory
- §6.2 — `SocialHomeWsManager`
- §6.3 — model dataclasses

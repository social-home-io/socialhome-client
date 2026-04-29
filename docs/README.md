# socialhome-client — Documentation

Reference material for the library. The code is the source of truth;
these docs are derived from the current code plus the spec — when
they disagree, the code wins and the docs should be fixed.

## Contents

- **[principles.md](./principles.md)** — Why the library stays thin:
  standalone of the core, Python 3.13 floor, async everywhere, typed
  responses, feature-grouped resources, one exception hierarchy.
- **[architecture.md](./architecture.md)** — Module layout: HTTP
  client + 8 feature resources, WebSocket manager
  (`5s → 15s → 30s → 60s` reconnect schedule), response models,
  exception hierarchy.
- **[testing.md](./testing.md)** — Test strategy: 85 % branch
  coverage gate, `aioresponses` HTTP stubbing, fake WebSocket,
  release flow.

## Where the spec lives

The authoritative specification is `spec_work.md` in the meta-repo.
Spec section references appear throughout as "§NN". This library is
covered primarily by §6 (and consumed by §7's HA integration).

# socialhome-client

Async HTTP + WebSocket client for [Social Home](https://github.com/social-home-io/core),
published to PyPI as `socialhome-client` and consumed by the
[Home Assistant integration](https://github.com/social-home-io/ha-integration).

Never imports from `social_home` (core). Safe to install inside Home
Assistant Core, which runs on Python 3.13.

## Install

```sh
pip install socialhome-client
```

## Use

The client groups methods under feature resources — e.g. `c.me.get()`,
`c.shopping.add(...)`, `c.bot.create(...)` — rather than a flat surface.

```python
import asyncio

from socialhome_client import SocialHomeClient, SocialHomeWsManager


async def main() -> None:
    async with SocialHomeClient("http://homeassistant.local:8099", token="…") as sh:
        me = await sh.me.get()
        print(me.display_name)

        await sh.shopping.add("milk")
        events = await sh.calendar.list_events("cal-1", "2026-05-01", "2026-06-01")
        print(f"{len(events)} events this month")

        ws = SocialHomeWsManager(sh)
        await ws.connect()
        ws.register(
            ["post_created"],
            lambda frame: asyncio.sleep(0, print(frame)),
        )


asyncio.run(main())
```

### Bots

Home Assistant automations can post into a space feed through the
bot-bridge. Each bot has its own Bearer token (shown once on create)
and posts render with the bot's icon + name instead of a generic
"Home Assistant" avatar.

```python
# Admin turns on bot posting for the space, then registers a household bot.
await sh.space.update(space_id, bot_enabled=True)
bot = await sh.bot.create(
    space_id, scope="space", slug="doorbell",
    name="Doorbell", icon="🔔",
)

# Persist bot.token somewhere safe — the backend will not show it again.
await sh.bot.post(
    space_id, bot.token,
    title="Ring", message="Front door",
)
```

## Develop

```sh
pip install -e .[dev]
pre-commit install
pytest
```

## License

[Mozilla Public License 2.0](LICENSE).

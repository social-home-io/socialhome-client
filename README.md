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

```python
import asyncio

from socialhome_client import SocialHomeClient, SocialHomeWsManager


async def main() -> None:
    async with SocialHomeClient("http://homeassistant.local:8099", token="…") as sh:
        me = await sh.get_me()
        print(me.display_name)

        ws = SocialHomeWsManager(sh)
        await ws.connect()
        ws.register(
            ["post_created"],
            lambda frame: asyncio.sleep(0, print(frame)),
        )


asyncio.run(main())
```

## Develop

```sh
pip install -e .[dev]
pre-commit install
pytest
```

## License

[Mozilla Public License 2.0](LICENSE).

from __future__ import annotations

from typing import Awaitable, Callable


class NatsBus:
    """Thin wrapper around nats-py.

    We import nats lazily to keep import-time lightweight.
    """

    def __init__(self, nats_url: str, client_name: str, creds_path: str = "") -> None:
        self.nats_url = nats_url
        self.client_name = client_name
        self.creds_path = creds_path
        self._nc = None

    async def connect(self) -> None:
        nats_module = __import__("nats.aio.client", fromlist=["Client"])
        nats_class = getattr(nats_module, "Client")
        self._nc = nats_class()
        opts = dict(
            servers=[self.nats_url],
            name=self.client_name,
            connect_timeout=10,
            max_reconnect_attempts=-1,
            reconnect_time_wait=2,
        )
        if self.creds_path:
            opts["user_credentials"] = self.creds_path
        await self._nc.connect(**opts)

    async def publish(self, subject: str, payload: bytes) -> None:
        if self._nc is None:
            raise RuntimeError("NATS not connected")
        await self._nc.publish(subject, payload)

    async def subscribe(self, subject: str, cb: Callable[..., Awaitable[None]]):
        if self._nc is None:
            raise RuntimeError("NATS not connected")
        return await self._nc.subscribe(subject, cb=cb)

    async def drain(self) -> None:
        if self._nc is not None:
            await self._nc.drain()

"""Bounded synchronization and failure controls for synthetic providers only."""

import asyncio


class Checkpoint:
    """One-shot pause; cancellation and timeout never leave a waiting participant."""

    def __init__(self, timeout: float = 2.0) -> None:
        self.timeout = timeout
        self.reached = asyncio.Event()
        self.released = asyncio.Event()
        self.waiters = 0

    async def wait(self) -> None:
        self.waiters += 1
        self.reached.set()
        try:
            async with asyncio.timeout(self.timeout):
                await self.released.wait()
        finally:
            self.waiters -= 1

    async def wait_until_reached(self) -> None:
        async with asyncio.timeout(self.timeout):
            await self.reached.wait()

    def release(self) -> None:
        self.released.set()

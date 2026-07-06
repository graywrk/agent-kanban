"""In-process async pub/sub for WebSocket fan-out.

Phase 1 is single-process; this avoids an external broker. If we ever scale
horizontally, swap this for Redis pub/sub without changing call sites.
"""
import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, channel: str) -> AsyncIterator[dict]:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[channel].add(queue)

        async def iterator():
            try:
                while True:
                    yield await queue.get()
            finally:
                self._subscribers[channel].discard(queue)

        return iterator()

    async def publish(self, channel: str, payload: dict) -> None:
        for queue in list(self._subscribers.get(channel, ())):
            await queue.put(payload)


event_bus = EventBus()

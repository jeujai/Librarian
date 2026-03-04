"""
SearXNG Client for Web Search Integration.

Async HTTP client for the SearXNG JSON API. Uses lazy session
creation so instantiation never opens network connections.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class SearXNGResult:
    """A single result from a SearXNG search."""

    title: str
    url: str
    content: str
    score: float
    engine: str


class SearXNGClient:
    """Async client for the SearXNG JSON API."""

    def __init__(
        self,
        host: str,
        port: int,
        timeout: float = 10.0,
    ):
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazy session creation — no connections at init time."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            )
        return self._session

    async def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> List[SearXNGResult]:
        """Search via the SearXNG JSON API."""
        session = await self._get_session()
        params = {
            "q": query,
            "format": "json",
            "categories": "general",
        }
        async with session.get(
            f"{self.base_url}/search", params=params,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            results = data.get("results", [])[:max_results]
            return [
                SearXNGResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    content=r.get("content", ""),
                    score=r.get("score", 0.5),
                    engine=r.get("engine", "unknown"),
                )
                for r in results
            ]

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

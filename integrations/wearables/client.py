from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class WearablesClient:
    """Core checks service availability without owning provider behavior."""

    base_url: str

    async def health(self) -> dict[str, str]:
        health_url = f"{self.base_url.rstrip('/')}/health"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(health_url)
            response.raise_for_status()
            return {"status": "healthy"}
        except (httpx.HTTPError, ValueError):
            return {"status": "unavailable"}

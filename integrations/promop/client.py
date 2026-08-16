from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class PRomopClient:
    """Connectivity-only client; PRomop retains ownership of OMOP behavior."""

    base_url: str
    api_base: str = "/api/v1/"

    async def health(self) -> dict[str, str]:
        health_url = f"{self.base_url.rstrip('/')}/api/health/"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(health_url)
            response.raise_for_status()
            return {"status": "healthy"}
        except (httpx.HTTPError, ValueError):
            return {"status": "unavailable"}

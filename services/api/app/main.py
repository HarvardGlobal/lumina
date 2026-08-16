import asyncio
import os

import httpx
from fastapi import FastAPI

from integrations.promop import PRomopClient
from integrations.wearables import WearablesClient


async def archive_health(base_url: str) -> dict[str, str]:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{base_url.rstrip('/')}/health")
        response.raise_for_status()
        return {"status": "healthy"}
    except (httpx.HTTPError, ValueError):
        return {"status": "unavailable"}


def create_app(
    archive_base_url: str | None = None,
    promop_base_url: str | None = None,
    wearables_base_url: str | None = None,
) -> FastAPI:
    app = FastAPI(title="LUMINA API", version="1.0.0")
    app.state.archive_base_url = archive_base_url or os.getenv("ARCHIVE_BASE_URL", "http://archive:8200")
    app.state.promop_base_url = promop_base_url or os.getenv("PROMOP_BASE_URL", "http://promop:8000")
    app.state.wearables_base_url = wearables_base_url or os.getenv("WEARABLES_BASE_URL", "http://wearables:8300")

    @app.get("/health")
    async def health():
        return {"status": "healthy", "service": "lumina-api"}

    @app.get("/api/v1/status")
    async def component_status():
        archive, promop, wearables = await asyncio.gather(
            archive_health(app.state.archive_base_url),
            PRomopClient(app.state.promop_base_url).health(),
            WearablesClient(app.state.wearables_base_url).health(),
        )
        return {
            "status": "healthy" if all(item["status"] == "healthy" for item in (archive, promop, wearables)) else "degraded",
            "components": {
                "archive": archive,
                "promop": promop,
                "wearables": wearables,
            },
        }

    return app


app = create_app()

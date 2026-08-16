import asyncio

from integrations.promop import PRomopClient
from integrations.wearables import WearablesClient


def test_promop_connectivity_reports_unavailable_without_live_service():
    result = asyncio.run(PRomopClient("http://127.0.0.1:1").health())
    assert result == {"status": "unavailable"}


def test_wearables_connectivity_reports_unavailable_without_live_service():
    result = asyncio.run(WearablesClient("http://127.0.0.1:1").health())
    assert result == {"status": "unavailable"}

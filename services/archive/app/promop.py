"""Narrow client for PRomop's supported FHIR synchronization contract."""

from __future__ import annotations

import os
from typing import Any

import httpx


class PromopPromotionError(RuntimeError):
    pass


class PromopClient:
    def __init__(self, base_url: str | None = None, service_token: str | None = None, timeout_seconds: float | None = None):
        self.base_url = (base_url or os.getenv("PROMOP_BASE_URL", "http://promop:8000")).rstrip("/")
        self.service_token = service_token if service_token is not None else os.getenv("PROMOP_SERVICE_AUTH_TOKEN", "")
        self.timeout_seconds = timeout_seconds or float(os.getenv("PROMOP_REQUEST_TIMEOUT_SECONDS", "30"))

    def promote_fhir(self, *, archive_record_id: str, person_id: int, bundle: dict[str, Any], fhir_version: str | None = None) -> dict[str, Any]:
        if not self.service_token:
            raise PromopPromotionError("PRomop service token is not configured")
        headers = {
            "Authorization": f"Bearer {self.service_token}",
            "X-Archive-Record-ID": archive_record_id,
        }
        if fhir_version:
            headers["FHIR-Version"] = fhir_version
        try:
            response = httpx.post(
                f"{self.base_url}/api/v1/fhir/sync/",
                json={"person_id": person_id, "bundle": bundle},
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise PromopPromotionError("PRomop promotion request could not be completed") from error
        if response.status_code != 201:
            raise PromopPromotionError(f"PRomop rejected the promotion (HTTP {response.status_code})")
        try:
            result = response.json()
        except ValueError as error:
            raise PromopPromotionError("PRomop returned an invalid promotion response") from error
        if not isinstance(result, dict):
            raise PromopPromotionError("PRomop returned an invalid promotion response")
        return result

#!/usr/bin/env python3
"""Fail fast when a LUMINA production environment contains local defaults."""

from __future__ import annotations

import os
import sys


def value(name: str) -> str:
    return os.getenv(name, "").strip()


def unsafe_secret(name: str, minimum: int, blocked: set[str]) -> str | None:
    candidate = value(name)
    if len(candidate) < minimum or candidate.lower() in blocked:
        return f"{name} must be a unique secret of at least {minimum} characters"
    return None


def require_https(name: str) -> str | None:
    if not value(name).startswith("https://"):
        return f"{name} must be an https:// URL in production"
    return None


def main() -> int:
    if value("LUMINA_ENV").lower() != "production":
        return 0

    errors: list[str] = []
    checks = [
        unsafe_secret("ARCHIVE_BEARER_TOKEN", 32, {"change-me", "archive-test-token"}),
        unsafe_secret("ARCHIVE_DB_PASSWORD", 20, {"lumina_local_only", "password", "change-me"}),
        unsafe_secret("PROMOP_POSTGRES_PASSWORD", 20, {"promop", "password", "change-me"}),
        unsafe_secret("PROMOP_SERVICE_AUTH_TOKEN", 32, {"lumina-local-promop-service-token", "change-me"}),
        unsafe_secret("PROMOP_SECRET_KEY", 50, {"dev-secret-key-change-in-production", "change-me"}),
        unsafe_secret("PROMOP_ADMIN_PASSWORD", 20, {"change-me", "password"}),
        require_https("PROMOP_APP_BASE_URL"),
        require_https("PROMOP_PUBLIC_URL"),
    ]
    errors.extend(check for check in checks if check)

    if value("PROMOP_DEBUG").lower() not in {"false", "0"}:
        errors.append("PROMOP_DEBUG must be False in production")
    if value("ARCHIVE_OBJECT_STORE_BACKEND") != "s3":
        errors.append("ARCHIVE_OBJECT_STORE_BACKEND must be s3 in production")
    if not value("ARCHIVE_S3_BUCKET"):
        errors.append("ARCHIVE_S3_BUCKET is required in production")
    if value("ARCHIVE_S3_SSE") != "aws:kms" or not value("ARCHIVE_S3_KMS_KEY_ID"):
        errors.append("ARCHIVE_S3_SSE=aws:kms and ARCHIVE_S3_KMS_KEY_ID are required in production")
    try:
        if int(value("ARCHIVE_RATE_LIMIT_REQUESTS_PER_MINUTE")) < 1:
            errors.append("ARCHIVE_RATE_LIMIT_REQUESTS_PER_MINUTE must be at least 1 in production")
    except ValueError:
        errors.append("ARCHIVE_RATE_LIMIT_REQUESTS_PER_MINUTE must be a positive integer in production")
    try:
        maximum = int(value("ARCHIVE_MAX_REQUEST_BYTES"))
        if maximum < 1 or maximum > 100 * 1024 * 1024:
            errors.append("ARCHIVE_MAX_REQUEST_BYTES must be between 1 and 104857600 in production")
    except ValueError:
        errors.append("ARCHIVE_MAX_REQUEST_BYTES must be an integer in production")

    if errors:
        print("LUMINA production configuration is not safe to start:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("[OK] Production configuration contains no known local defaults.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

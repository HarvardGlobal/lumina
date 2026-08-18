#!/usr/bin/env python3
"""Materialize and verify exact external component revisions for LUMINA.

The component manifest is intentionally a small, restricted YAML subset so no
YAML parser is needed in the pinned development shell. Component changes are
never destructive: a dirty cache checkout prevents switching revisions.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "components.yaml"
SHA = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_FILES = {
    "promop": ("Dockerfile", "manage.py"),
    "lumina-wearables": ("Dockerfile", "app/main.py"),
    "open-wearables": ("docker-compose.yml", "backend/app/main.py"),
}
VERSION_FILES = {
    "lumina-wearables": ("VERSION", re.compile(r"^([^\n]+)$")),
    "open-wearables": ("backend/pyproject.toml", re.compile(r'^version = "([^"]+)"$', re.MULTILINE)),
}


def run(*args: str, cwd: Path | None = None, capture: bool = False) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout.strip() if capture else ""


def components_dir() -> Path:
    configured = os.environ.get("LUMINA_COMPONENTS_DIR", ".lumina/components")
    path = Path(configured)
    return path if path.is_absolute() else ROOT / path


def parse_manifest() -> list[dict[str, str]]:
    """Read only the components mapping in config/components.yaml."""
    components: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    in_components = False
    for raw_line in MANIFEST.read_text().splitlines():
        if raw_line == "components:":
            in_components = True
            continue
        if in_components and raw_line and not raw_line.startswith(" "):
            break
        if not in_components or not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line.startswith("  ") and not raw_line.startswith("    ") and raw_line.rstrip().endswith(":"):
            if current is not None:
                components.append(current)
            current = {"name": raw_line.strip()[:-1]}
            continue
        if current is not None and raw_line.startswith("    ") and ":" in raw_line:
            key, value = raw_line.strip().split(":", 1)
            current[key] = value.strip().strip('"')
    if current is not None:
        components.append(current)

    for component in components:
        missing = {"name", "clone_url", "git_ref"} - component.keys()
        if missing:
            raise ValueError(f"{component.get('name', 'unnamed')} is missing {', '.join(sorted(missing))}")
        if not SHA.fullmatch(component["git_ref"]):
            raise ValueError(f"{component['name']} must use a full 40-character commit SHA")
    return components


def is_dirty(path: Path) -> bool:
    return bool(run("git", "status", "--porcelain", cwd=path, capture=True))


def current_revision(path: Path) -> str | None:
    try:
        return run("git", "rev-parse", "HEAD", cwd=path, capture=True)
    except subprocess.CalledProcessError:
        return None


def validate_layout(component: dict[str, str], target: Path) -> None:
    missing = [name for name in REQUIRED_FILES.get(component["name"], ()) if not (target / name).is_file()]
    if missing:
        raise RuntimeError(
            f"Pinned {component['name']} revision {component['git_ref']} is missing "
            f"required files: {', '.join(missing)}. Publish a compatible component revision, "
            "then update config/components.yaml to that tested SHA."
        )
    expected_version = component.get("version")
    if expected_version is None:
        return
    version_file, version_pattern = VERSION_FILES.get(component["name"], ("", re.compile("$^")))
    if not version_file:
        raise RuntimeError(f"Pinned {component['name']} declares an unsupported version check")
    match = version_pattern.search((target / version_file).read_text())
    actual_version = match.group(1).strip() if match else None
    if actual_version != expected_version:
        raise RuntimeError(
            f"Pinned {component['name']} revision {component['git_ref']} reports version "
            f"{actual_version!r}, expected {expected_version!r} from config/components.yaml."
        )


def sync_component(component: dict[str, str]) -> None:
    target = components_dir() / component["name"]
    desired = component["git_ref"]
    if target.exists():
        if not (target / ".git").exists():
            raise RuntimeError(f"Refusing to replace non-Git component directory: {target}")
        actual = current_revision(target)
        if actual != desired and is_dirty(target):
            raise RuntimeError(
                f"Refusing to switch dirty component {component['name']} ({actual} -> {desired}). "
                "Commit, stash, or remove local changes first."
            )
        if actual == desired:
            if is_dirty(target):
                raise RuntimeError(f"Pinned component {component['name']} has local changes: {target}")
            validate_layout(component, target)
            version = f" version {component['version']}" if component.get("version") else ""
            print(f"[OK] {component['name']} is pinned at {desired}{version}")
            return
        run("git", "fetch", "--depth", "1", "origin", desired, cwd=target)
        run("git", "checkout", "--detach", "FETCH_HEAD", cwd=target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        run("git", "init", str(target))
        run("git", "remote", "add", "origin", component["clone_url"], cwd=target)
        run("git", "fetch", "--depth", "1", "origin", desired, cwd=target)
        run("git", "checkout", "--detach", "FETCH_HEAD", cwd=target)

    actual = current_revision(target)
    if actual != desired:
        raise RuntimeError(f"{component['name']} resolved to {actual}, expected {desired}")
    if is_dirty(target):
        raise RuntimeError(f"Pinned component {component['name']} has local changes: {target}")
    validate_layout(component, target)
    version = f" version {component['version']}" if component.get("version") else ""
    print(f"[OK] {component['name']} is pinned at {desired}{version}")


def status_component(component: dict[str, str]) -> bool:
    target = components_dir() / component["name"]
    desired = component["git_ref"]
    actual = current_revision(target) if target.exists() else None
    if actual == desired and not is_dirty(target):
        try:
            validate_layout(component, target)
        except RuntimeError as error:
            print(f"[INVALID] {component['name']}: {error}")
            return False
        version = f" version {component['version']}" if component.get("version") else ""
        print(f"[OK] {component['name']}: {actual}{version}")
        return True
    if actual is None:
        print(f"[MISSING] {component['name']}: run `make components`")
    else:
        suffix = " (dirty)" if is_dirty(target) else ""
        print(f"[DRIFT] {component['name']}: {actual}, expected {desired}{suffix}")
    return False


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"sync", "status"}:
        print("Usage: components.py {sync|status}", file=sys.stderr)
        return 2
    try:
        components = parse_manifest()
        if sys.argv[1] == "sync":
            for component in components:
                sync_component(component)
            return 0
        print(f"LUMINA version: {(ROOT / 'VERSION').read_text().strip()}")
        print("Archive schema version: 1.0.0")
        print("OMOP CDM version: 5.4")
        results = [status_component(component) for component in components]
        return 0 if all(results) else 1
    except (OSError, ValueError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"[FAIL] component resolution: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

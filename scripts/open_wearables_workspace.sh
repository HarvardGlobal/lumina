#!/usr/bin/env bash
set -euo pipefail

# Create an editable sibling checkout without ever substituting it for Core's
# immutable .lumina/components/open-wearables runtime checkout.
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace_dir="$(dirname "$root_dir")"
target_dir="${LUMINA_OPEN_WEARABLES_WORKSPACE:-$workspace_dir/open-wearables}"
read -r repository revision component_version < <(
  cd "$root_dir"
  python3 - <<'PY'
from scripts.components import parse_manifest

component = next(item for item in parse_manifest() if item["name"] == "open-wearables")
print(component["clone_url"], component["git_ref"], component["version"])
PY
)
branch="lumina/open-wearables-$component_version"

if [[ -e "$target_dir" && ! -d "$target_dir/.git" ]]; then
  echo "Refusing to replace non-Git path: $target_dir" >&2
  exit 1
fi

if [[ -e "$target_dir" ]] && git -C "$target_dir" show-ref --verify --quiet "refs/heads/$branch"; then
  current_branch="$(git -C "$target_dir" branch --show-current)"
  if [[ "$current_branch" != "$branch" ]]; then
    if [[ -n "$(git -C "$target_dir" status --porcelain)" ]]; then
      echo "Refusing to switch dirty editable Open Wearables checkout: $target_dir" >&2
      exit 1
    fi
    git -C "$target_dir" switch "$branch"
  fi
  if [[ "$(git -C "$target_dir" rev-parse HEAD)" != "$revision" ]]; then
    echo "[EDIT] Editable Open Wearables checkout is ahead of the manifest pin: $target_dir"
    echo "[EDIT] Commit/push this branch, then update config/components.yaml when the change is approved."
    exit 0
  fi
fi

if [[ ! -e "$target_dir" ]]; then
  git clone --no-checkout "$repository" "$target_dir"
fi

git -C "$target_dir" fetch --depth 1 origin "$revision"
current_revision="$(git -C "$target_dir" rev-parse HEAD 2>/dev/null || true)"
if [[ "$current_revision" != "$revision" ]] && [[ -n "$(git -C "$target_dir" status --porcelain)" ]]; then
  echo "Refusing to switch dirty editable Open Wearables checkout: $target_dir" >&2
  exit 1
fi
if git -C "$target_dir" show-ref --verify --quiet "refs/heads/$branch"; then
  git -C "$target_dir" switch "$branch"
else
  git -C "$target_dir" switch -c "$branch" FETCH_HEAD
fi
if [[ "$(git -C "$target_dir" rev-parse HEAD)" != "$revision" ]]; then
  echo "[EDIT] Editable branch $branch is ahead of the manifest pin; it was left unchanged."
  exit 0
fi

echo "[OK] Editable Open Wearables checkout: $target_dir"
echo "[OK] Branch: $branch at $revision"
echo "Commit and push your change, then update config/components.yaml to its resulting SHA."

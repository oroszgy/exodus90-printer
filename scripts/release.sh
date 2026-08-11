#!/usr/bin/env bash
set -euo pipefail

PART=""
DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --dry-run)
            DRY_RUN=1
            ;;
        major|minor|patch)
            if [ -n "$PART" ]; then
                echo "error: duplicate bump part '$arg'" >&2
                exit 2
            fi
            PART="$arg"
            ;;
        *)
            echo "error: unknown argument '$arg'" >&2
            echo "usage: $0 [--dry-run] (major|minor|patch)" >&2
            exit 2
            ;;
    esac
done
PART="${PART:-patch}"

if [ "$(git branch --show-current)" != "main" ]; then
    echo "error: must run on the 'main' branch" >&2
    exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "error: working tree is dirty; commit or stash changes first" >&2
    exit 1
fi

git fetch origin
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
    echo "error: local main is not up to date with origin/main; run 'git pull' first" >&2
    exit 1
fi

PREV="$(uvx bump-my-version show current_version)"

if [ "$DRY_RUN" = 1 ]; then
    uvx bump-my-version bump --dry-run "$PART"
    echo "Dry run complete; nothing was changed."
    exit 0
fi

uvx bump-my-version bump "$PART"
uv lock

NEW="$(uvx bump-my-version show current_version)"
echo "Bumped version: $PREV -> $NEW"

git add pyproject.toml addon/config.yaml uv.lock
git commit -m "Bump version: $PREV -> $NEW"
git tag "v$NEW"

git push origin main
git push origin "v$NEW"

echo "Released v$NEW (GHCR + PyPI workflows will publish)."

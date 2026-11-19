#!/usr/bin/env bash
# One-time migration (roadmap phase 0): move every AppImage out of Git into
# GitHub Releases, then purge them from the history.
#
#   Step 1  upload   each tracked AppImage becomes a release on the commit
#                    that added it (DevBuilds/ChatGPT Test = pre-release,
#                    Public Releases = release). Existing tags are skipped,
#                    nothing is overwritten.
#   Step 2  remove   git rm the binaries in a normal commit on main.
#   Step 3  purge    git filter-repo rewrites the history without *.AppImage
#                    and force-pushes. DESTRUCTIVE: every clone must be
#                    re-cloned afterwards. Run only after step 1 succeeded.
#
# Needs: gh (logged in, write access), git-filter-repo for step 3.
# Usage: tools/migrate-binaries-to-releases.sh upload|remove|purge [--dry-run]
set -euo pipefail

STEP="${1:-}"
DRY="${2:-}"
run() { if [ "$DRY" = "--dry-run" ]; then echo "+ $*"; else "$@"; fi; }

cd "$(git rev-parse --show-toplevel)"

tag_for() { # path -> tag name
  local f; f=$(basename "$1" .AppImage)
  case "$f" in
    FlipperOne-OSINT-*-PC)     echo "legacy-pc-${f#FlipperOne-OSINT-}" | sed 's/-PC$//' ;;
    FlipperOne-OSINT-*)        local v=${f#FlipperOne-OSINT-}; v=${v%-aarch64}; v=${v%-x86_64}
                               case "$1" in "Public Releases/"*) echo "v$v" ;; *) echo "v$v-dev" ;; esac ;;
    ChatGPT-Test-*)            local v=${f#ChatGPT-Test-}; echo "chatgpt-test-${v%-aarch64}" ;;
    *)                         echo "misc-$f" ;;
  esac
}

case "$STEP" in
upload)
  git ls-files -z '*.AppImage' | while IFS= read -r -d '' f; do
    tag=$(tag_for "$f")
    if gh release view "$tag" >/dev/null 2>&1; then
      echo "skip  $tag (exists)"; continue
    fi
    sha=$(git log --diff-filter=A --format=%H -1 -- "$f")
    pre=--prerelease
    [[ "$f" == "Public Releases/"* ]] && pre=
    echo "create $tag  <- $f  @ ${sha::7}"
    run gh release create "$tag" "$f" --target "$sha" --title "${tag}" \
        --notes "Migrated from \`$f\` (added in $sha)." $pre
  done ;;
remove)
  run git rm -r --cached -- '*.AppImage'
  run git commit -m "Move AppImages to GitHub Releases"
  echo "Push with: git push origin main" ;;
purge)
  command -v git-filter-repo >/dev/null || { echo "install git-filter-repo first (pip install git-filter-repo)"; exit 1; }
  read -r -p "Rewrite ALL history without *.AppImage and force-push? Type 'purge': " ok
  [ "$ok" = "purge" ] || exit 1
  url=$(git remote get-url origin)
  run git filter-repo --force --path-glob '*.AppImage' --invert-paths
  run git remote add origin "$url"
  run git push --force --all origin
  run git push --force --tags origin
  echo "Done. Everyone must re-clone; experiment branches can now be archived." ;;
*)
  sed -n '2,17p' "$0"; exit 2 ;;
esac

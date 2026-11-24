#!/bin/sh
# Assemble the public site (the Atlas viewer as the front page, gram, methods, location lists) and
# force-push it to the "site" branch, which GitHub Pages serves. The branch keeps no history, so
# rebuilding the viewer's data never makes the repository grow.
#   usage: sh viewer/deploy_site.sh <built viewer folder>
#   test:  DRY=1 sh viewer/deploy_site.sh <built viewer folder>   (assembles in a temporary folder, pushes nothing)
set -e
REPO=$(cd "$(dirname "$0")/.." && pwd)
VIEW=${1:-/home/claude/site}
# refuse to deploy from an out-of-date copy of the code: an old checkout would overwrite newer pages on the live site
git -C "$REPO" fetch -q --depth=50 origin main
if ! git -C "$REPO" merge-base --is-ancestor origin/main HEAD; then
  echo "This copy of the code is behind GitHub's main branch. Run 'git pull' first, then rebuild and deploy."; exit 1
fi
OUT=$(mktemp -d)
# the Atlas (the built viewer) is the front page
cp -r "$VIEW/index.html" "$VIEW/data" "$OUT/"
cp -r "$REPO/gram" "$REPO/locations" "$REPO/methods" "$OUT/"
# the viewer's old address forwards to the front page, so links shared before the rename keep working
mkdir -p "$OUT/fingerprints"
cp "$REPO/viewer/forward.html" "$OUT/fingerprints/index.html"
touch "$OUT/.nojekyll"
# the custom domain: GitHub Pages reads it from this file, and a force-push without it would drop the domain
echo "haloskyatlas.com" > "$OUT/CNAME"
# DRY=1 sh viewer/deploy_site.sh <folder>: assemble only and print where, for a local test
if [ -n "$DRY" ]; then echo "$OUT"; exit 0; fi
cd "$OUT"
git init -q -b site
git config user.email "noreply@anthropic.com"; git config user.name "Claude"
git add -A
git commit -q -m "Site build $(date -u +%Y-%m-%dT%H:%MZ)"
git remote add origin "$(git -C "$REPO" remote get-url origin)"
git -c http.postBuffer=524288000 push -q --force origin site
echo "pushed $(du -sh . | cut -f1) to branch site"
rm -rf "$OUT"

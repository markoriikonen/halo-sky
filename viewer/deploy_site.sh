#!/bin/sh
# Assemble the public site (landing page, gram, built viewer) and force-push it to the
# "site" branch, which GitHub Pages serves. The branch keeps no history, so rebuilding
# the viewer's data never makes the repository grow.
#   usage: sh viewer/deploy_site.sh <built viewer folder>
set -e
REPO=$(cd "$(dirname "$0")/.." && pwd)
VIEW=${1:-/home/claude/site}
OUT=$(mktemp -d)
# the landing page on the site branch points at the viewer copy next to it
sed -e 's#href="https://claude.ai/artifact/QLgEuMgeaU1XYKTv3nErfs"#href="fingerprints/"#' \
    -e 's#A world map of about 2,000 sites: cloud-layer fingerprints, the elliptical-halo mid-layer search and high-cloud seasons.#A world map of about 2,500 sites: cloud-layer fingerprints, the elliptical-halo mid-layer search, high-cloud seasons, and photographed halo displays.#' \
    "$REPO/index.html" > "$OUT/index.html"
cp -r "$REPO/gram" "$REPO/locations" "$OUT/"
mkdir -p "$OUT/fingerprints"
cp -r "$VIEW/index.html" "$VIEW/data" "$OUT/fingerprints/"
touch "$OUT/.nojekyll"
cd "$OUT"
git init -q -b site
git config user.email "noreply@anthropic.com"; git config user.name "Claude"
git add -A
git commit -q -m "Site build $(date -u +%Y-%m-%dT%H:%MZ)"
git remote add origin "$(git -C "$REPO" remote get-url origin)"
git -c http.postBuffer=524288000 push -q --force origin site
echo "pushed $(du -sh . | cut -f1) to branch site"
rm -rf "$OUT"

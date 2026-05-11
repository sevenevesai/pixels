#!/bin/bash
# prepare-release.sh — Download GitHub Release artifacts and prepare for self-hosted deployment
#
# Usage: ./scripts/prepare-release.sh <version>
# Example: ./scripts/prepare-release.sh 1.2.1
#
# This script:
#   1. Downloads all artifacts from the GitHub draft release
#   2. Sorts updater bundles into updates/ and installers into downloads/
#   3. Rewrites latest.json URLs from GitHub → seveneves.ai
#
# After running, deploy the sevenevesai site folder to your host.

set -euo pipefail

VERSION="${1:?Usage: $0 <version>}"
TAG="v${VERSION}"

SITE_ROOT="/s/sevenevesai/public_html/pixels"
UPDATES_DIR="${SITE_ROOT}/updates"
DOWNLOADS_DIR="${SITE_ROOT}/downloads"
TEMP_DIR=$(mktemp -d)

SITE_BASE="https://seveneves.ai/pixels"

echo "=== Preparing release ${TAG} ==="
echo ""

# Download all artifacts from GitHub release
echo "Downloading artifacts from GitHub release ${TAG}..."
gh release download "${TAG}" -D "${TEMP_DIR}" || {
  echo "ERROR: Failed to download release ${TAG}. Is it built?"
  exit 1
}

echo ""
echo "Downloaded:"
ls -1 "${TEMP_DIR}"
echo ""

# Sort files into updates/ and downloads/
echo "Sorting artifacts..."

for file in "${TEMP_DIR}"/*; do
  name=$(basename "$file")
  case "$name" in
    # Updater bundles and signatures → updates/
    *.tar.gz|*.tar.gz.sig|*.nsis.zip|*.nsis.zip.sig|*.msi.zip|*.msi.zip.sig|*.deb.sig|*.AppImage.sig|*.exe.sig|*.msi.sig)
      cp "$file" "${UPDATES_DIR}/"
      echo "  updates/  ${name}"
      ;;
    # latest.json → updates/ (will be rewritten below)
    latest.json)
      cp "$file" "${UPDATES_DIR}/"
      echo "  updates/  ${name}"
      ;;
    # Installers → downloads/
    *.msi|*.exe|*.dmg|*.deb|*.AppImage)
      cp "$file" "${DOWNLOADS_DIR}/"
      echo "  downloads/ ${name}"
      ;;
    *)
      echo "  skipped  ${name}"
      ;;
  esac
done

echo ""

# Rewrite latest.json URLs from GitHub to self-hosted
echo "Rewriting latest.json URLs..."

LATEST="${UPDATES_DIR}/latest.json"
LATEST_WIN=$(cygpath -w "${LATEST}" 2>/dev/null || echo "${LATEST}")
GITHUB_PREFIX="https://github.com/sevenevesai/pixels/releases/download/${TAG}/"

python -c "
import json, sys, os

latest_path = sys.argv[1]
github_prefix = sys.argv[2]
site_base = sys.argv[3]

with open(latest_path, 'r') as f:
    data = json.load(f)

for platform, info in data['platforms'].items():
    url = info['url']
    if not url.startswith(github_prefix):
        continue
    filename = url[len(github_prefix):]
    if filename.endswith(('.tar.gz', '.nsis.zip', '.msi.zip')):
        info['url'] = site_base + '/updates/' + filename
    else:
        info['url'] = site_base + '/downloads/' + filename

with open(latest_path, 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
" "${LATEST_WIN}" "${GITHUB_PREFIX}" "${SITE_BASE}" || {
  echo "ERROR: Failed to rewrite latest.json. Is python3 available?"
  exit 1
}

echo ""
echo "=== latest.json ==="
cat "${LATEST}"
echo ""
echo "=== Done ==="
echo "Files are ready in:"
echo "  ${UPDATES_DIR}"
echo "  ${DOWNLOADS_DIR}"
echo ""
echo "Next: deploy to your Namecheap host."

rm -rf "${TEMP_DIR}"

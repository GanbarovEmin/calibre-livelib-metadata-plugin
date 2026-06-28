#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_DIR="$ROOT_DIR/plugin"
DIST_DIR="$ROOT_DIR/dist"
ZIP_PATH="$DIST_DIR/LiveLib.Metadata.zip"

mkdir -p "$DIST_DIR"
rm -f "$ZIP_PATH"

cd "$PLUGIN_DIR"
zip -q -r "$ZIP_PATH" . -x '__pycache__/*' '*.pyc' '.DS_Store'

echo "$ZIP_PATH"

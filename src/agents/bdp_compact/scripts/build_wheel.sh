#!/bin/bash
# BDP Compact Agent Wheel Build
# Builds a standalone Python wheel package
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== BDP Compact Agent Wheel Build ==="
echo "Project directory: $PROJECT_DIR"
echo ""

# Clean previous builds
echo "[1/3] Cleaning previous builds..."
rm -rf dist/ build/ *.egg-info bdp_compact.egg-info

# Install build dependencies
echo "[2/3] Installing build tools..."
python3 -m pip install --quiet --upgrade build wheel

# Build wheel
echo "[3/3] Building wheel..."
python3 -m build --wheel

echo ""
echo "=== Build Complete ==="
ls -la dist/

# Show wheel contents
echo ""
echo "=== Wheel Contents ==="
WHEEL_FILE=$(ls dist/*.whl 2>/dev/null | head -1)
if [ -n "$WHEEL_FILE" ]; then
    python3 -c "import zipfile; zf=zipfile.ZipFile('$WHEEL_FILE'); print('\n'.join(sorted([f.filename for f in zf.filelist])[:20]))"
    echo "..."
fi

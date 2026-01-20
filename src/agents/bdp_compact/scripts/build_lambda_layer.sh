#!/bin/bash
# BDP Compact Agent Lambda Layer Build
# Builds a Lambda layer ZIP containing the package and dependencies
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== BDP Compact Agent Lambda Layer Build ==="
echo "Project directory: $PROJECT_DIR"
echo ""

# Build wheel first
echo "[1/5] Building wheel..."
"$SCRIPT_DIR/build_wheel.sh"

# Create layer directory
LAYER_DIR="$PROJECT_DIR/layer"
echo ""
echo "[2/5] Creating layer directory..."
rm -rf "$LAYER_DIR"
mkdir -p "$LAYER_DIR/python"

# Install dependencies for Lambda (manylinux platform)
echo "[3/5] Installing dependencies for Lambda..."
python3 -m pip install \
    --platform manylinux2014_x86_64 \
    --target "$LAYER_DIR/python" \
    --implementation cp \
    --python-version 3.11 \
    --only-binary=:all: \
    --upgrade \
    boto3 pydantic pyod numpy scipy 2>/dev/null || {
    echo "Warning: manylinux wheel download failed, using local platform..."
    python3 -m pip install \
        --target "$LAYER_DIR/python" \
        --upgrade \
        boto3 pydantic pyod numpy scipy
}

# Install the bdp-compact package
echo "[4/5] Installing bdp-compact package..."
WHEEL_FILE=$(ls dist/*.whl 2>/dev/null | head -1)
if [ -z "$WHEEL_FILE" ]; then
    echo "Error: No wheel file found in dist/"
    exit 1
fi

# Unzip wheel directly into the python directory
unzip -q -o "$WHEEL_FILE" -d "$LAYER_DIR/python/"

# Remove unnecessary files to reduce size
echo "Cleaning up unnecessary files..."
find "$LAYER_DIR/python" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$LAYER_DIR/python" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find "$LAYER_DIR/python" -name "*.pyc" -delete 2>/dev/null || true
find "$LAYER_DIR/python" -name "*.pyo" -delete 2>/dev/null || true

# Create Lambda layer ZIP
echo "[5/5] Creating Lambda layer ZIP..."
cd "$LAYER_DIR"
zip -r9 "$PROJECT_DIR/dist/bdp-compact-layer.zip" python/

# Calculate size
LAYER_SIZE=$(du -h "$PROJECT_DIR/dist/bdp-compact-layer.zip" | cut -f1)
LAYER_SIZE_BYTES=$(stat -f%z "$PROJECT_DIR/dist/bdp-compact-layer.zip" 2>/dev/null || stat -c%s "$PROJECT_DIR/dist/bdp-compact-layer.zip" 2>/dev/null)

# Lambda layer size limit: 250MB uncompressed, ~50MB compressed is reasonable
echo ""
echo "=== Lambda Layer Build Complete ==="
echo "Layer file: dist/bdp-compact-layer.zip"
echo "Layer size: $LAYER_SIZE"

if [ "$LAYER_SIZE_BYTES" -gt 52428800 ]; then  # 50MB
    echo ""
    echo "⚠️  Warning: Layer size exceeds 50MB, consider optimization"
fi

echo ""
echo "=== Layer Contents (top 20) ==="
unzip -l "$PROJECT_DIR/dist/bdp-compact-layer.zip" | head -25

echo ""
echo "=== Usage ==="
echo "Deploy to AWS Lambda:"
echo "  aws lambda publish-layer-version \\"
echo "      --layer-name bdp-compact \\"
echo "      --zip-file fileb://dist/bdp-compact-layer.zip \\"
echo "      --compatible-runtimes python3.11 python3.12"

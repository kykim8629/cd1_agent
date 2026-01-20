# BDP Compact Agent - Build Automation
# ====================================
#
# Usage:
#   make wheel    - Build Python wheel package
#   make layer    - Build Lambda layer ZIP
#   make clean    - Clean all build artifacts
#   make install  - Install package locally
#   make test     - Run tests
#   make lint     - Run linter
#   make all      - Clean, build wheel, and build layer

.PHONY: all wheel layer clean install test lint dev-install help

# Default target
all: clean layer

# Build Python wheel
wheel:
	@echo "Building wheel..."
	./scripts/build_wheel.sh

# Build Lambda layer (includes wheel)
layer: wheel
	@echo "Building Lambda layer..."
	./scripts/build_lambda_layer.sh

# Clean all build artifacts
clean:
	@echo "Cleaning build artifacts..."
	rm -rf dist/ build/ layer/ *.egg-info bdp_compact.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

# Install package locally (editable mode)
install:
	@echo "Installing package..."
	pip install -e .

# Install with development dependencies
dev-install:
	@echo "Installing with dev dependencies..."
	pip install -e ".[dev,server]"

# Run tests
test:
	@echo "Running tests..."
	pytest tests/ -v --cov=bdp_compact --cov-report=term-missing

# Run linter
lint:
	@echo "Running linter..."
	ruff check bdp_compact/
	mypy bdp_compact/

# Format code
format:
	@echo "Formatting code..."
	ruff format bdp_compact/

# Show help
help:
	@echo "BDP Compact Agent - Build Commands"
	@echo "==================================="
	@echo ""
	@echo "Build targets:"
	@echo "  make wheel       Build Python wheel package"
	@echo "  make layer       Build Lambda layer ZIP (includes wheel)"
	@echo "  make clean       Clean all build artifacts"
	@echo "  make all         Clean + build layer"
	@echo ""
	@echo "Development targets:"
	@echo "  make install     Install package locally"
	@echo "  make dev-install Install with dev dependencies"
	@echo "  make test        Run tests"
	@echo "  make lint        Run linter"
	@echo "  make format      Format code"
	@echo ""
	@echo "Output files:"
	@echo "  dist/bdp_compact-*.whl         Python wheel"
	@echo "  dist/bdp-compact-layer.zip     Lambda layer"

# CD1 Agent Makefile
# Build, test, and deployment automation

.PHONY: help install dev test lint format wheel layer build publish clean

# Default target
help:
	@echo "CD1 Agent Build Commands"
	@echo ""
	@echo "Development:"
	@echo "  make install      Install package in development mode"
	@echo "  make dev          Install with all development dependencies"
	@echo "  make test         Run tests with coverage"
	@echo "  make lint         Run linting (ruff + mypy)"
	@echo "  make format       Format code with black"
	@echo ""
	@echo "Build:"
	@echo "  make wheel        Build wheel package"
	@echo "  make layer        Build Lambda layer (basic)"
	@echo "  make layer-full   Build Lambda layer with all optional deps"
	@echo "  make build        Build wheel + Lambda layer (both)"
	@echo ""
	@echo "Publish:"
	@echo "  make publish      Publish to CodeArtifact"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean        Remove build artifacts"

# Development
install:
	pip install -e .

dev:
	pip install -e ".[dev,luminol,vllm,gemini,rds]"

# Testing
test:
	pytest tests/ -v --cov=src --cov-report=term-missing

test-unit:
	pytest tests/ -v -m "unit" --cov=src

test-integration:
	pytest tests/ -v -m "integration"

# Linting
lint:
	ruff check src/ tests/
	mypy src/

format:
	black src/ tests/
	ruff check --fix src/ tests/

# Build
wheel: clean
	./scripts/build_wheel.sh

layer: wheel
	./scripts/build_lambda_layer.sh

layer-vllm: wheel
	./scripts/build_lambda_layer.sh --with-vllm

layer-gemini: wheel
	./scripts/build_lambda_layer.sh --with-gemini

layer-rds: wheel
	./scripts/build_lambda_layer.sh --with-rds

layer-full: wheel
	./scripts/build_lambda_layer.sh --with-vllm --with-gemini --with-rds

build: wheel layer
	@echo "=== Build Complete: Wheel + Layer ==="

# Publish
publish: wheel
	./scripts/publish_codeartifact.sh

# Cleanup
clean:
	rm -rf dist/ build/ layer/ *.egg-info
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Docker (optional)
docker-build:
	docker build -t cd1-agent .

docker-test:
	docker run --rm cd1-agent pytest tests/ -v

# Local testing with mock providers
run-mock:
	AWS_PROVIDER=mock LLM_PROVIDER=mock RDS_PROVIDER=mock \
		python -c "from src.agents.bdp.handler import handler; print(handler({'detection_type': 'scheduled'}, None))"

# ============================================================================
# LocalStack Integration
# ============================================================================

.PHONY: localstack-up localstack-down localstack-test localstack-logs localstack-status
.PHONY: scenario-cpu-spike scenario-error-flood scenario-auth-failure scenario-db-timeout

# LocalStack environment management
localstack-up:
	@echo "=== Starting LocalStack environment ==="
	docker-compose -f docker-compose.localstack.yml up -d
	@echo "Waiting for LocalStack to be healthy..."
	@timeout 60 bash -c 'until curl -s http://localhost:4566/_localstack/health | grep -q "running"; do sleep 2; done' || (echo "LocalStack failed to start" && exit 1)
	@echo "Waiting for MySQL to be healthy..."
	@timeout 60 bash -c 'until docker-compose -f docker-compose.localstack.yml exec -T mysql mysqladmin ping -h localhost -u root -plocalstack 2>/dev/null; do sleep 2; done' || (echo "MySQL failed to start" && exit 1)
	@echo "=== LocalStack environment ready ==="

localstack-down:
	@echo "=== Stopping LocalStack environment ==="
	docker-compose -f docker-compose.localstack.yml down -v
	@echo "=== LocalStack environment stopped ==="

localstack-logs:
	docker-compose -f docker-compose.localstack.yml logs -f

localstack-status:
	@echo "=== LocalStack Status ==="
	@curl -s http://localhost:4566/_localstack/health | python3 -m json.tool 2>/dev/null || echo "LocalStack not running"
	@echo ""
	@echo "=== MySQL Status ==="
	@docker-compose -f docker-compose.localstack.yml exec -T mysql mysqladmin status -h localhost -u root -plocalstack 2>/dev/null || echo "MySQL not running"

# Run tests against LocalStack
localstack-test:
	@echo "=== Running tests against LocalStack ==="
	TEST_AWS_PROVIDER=localstack LOCALSTACK_ENDPOINT=http://localhost:4566 \
		pytest tests/agents/bdp/test_localstack_scenarios.py -v -m localstack

localstack-test-all:
	@echo "=== Running all BDP tests against LocalStack ==="
	TEST_AWS_PROVIDER=localstack LOCALSTACK_ENDPOINT=http://localhost:4566 \
		pytest tests/agents/bdp/ -v

# Failure scenario injection
scenario-cpu-spike:
	@echo "=== Injecting CPU Spike Scenario ==="
	LOCALSTACK_ENDPOINT=http://localhost:4566 ./localstack/scenarios/high-cpu-spike.sh test-function

scenario-error-flood:
	@echo "=== Injecting Error Flood Scenario ==="
	LOCALSTACK_ENDPOINT=http://localhost:4566 ./localstack/scenarios/error-flood.sh /aws/lambda/test-function

scenario-auth-failure:
	@echo "=== Injecting Auth Failure Scenario ==="
	LOCALSTACK_ENDPOINT=http://localhost:4566 MYSQL_HOST=localhost ./localstack/scenarios/auth-failure.sh /aws/lambda/auth-service

scenario-db-timeout:
	@echo "=== Injecting DB Timeout Scenario ==="
	LOCALSTACK_ENDPOINT=http://localhost:4566 MYSQL_HOST=localhost ./localstack/scenarios/db-timeout.sh /aws/lambda/data-processor

# Quick verification commands
localstack-verify-metrics:
	@echo "=== Verifying CloudWatch Metrics ==="
	awslocal cloudwatch list-metrics --namespace AWS/Lambda --endpoint-url http://localhost:4566

localstack-verify-logs:
	@echo "=== Verifying CloudWatch Logs ==="
	awslocal logs describe-log-groups --endpoint-url http://localhost:4566

localstack-verify-dynamodb:
	@echo "=== Verifying DynamoDB Tables ==="
	awslocal dynamodb list-tables --endpoint-url http://localhost:4566

localstack-verify-eventbridge:
	@echo "=== Verifying EventBridge ==="
	awslocal events list-event-buses --endpoint-url http://localhost:4566

localstack-verify-mysql:
	@echo "=== Verifying MySQL Patterns ==="
	docker-compose -f docker-compose.localstack.yml exec -T mysql \
		mysql -u cd1_user -pcd1_password cd1_agent -e "SELECT pattern_id, pattern_name, severity FROM detection_patterns;"

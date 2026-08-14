.PHONY: help install install-dev sync update lint format build-image push-image test test-feature-server test-registry test-discovery test-auth test-no-auth clean

PYTHON ?= python
PYTEST ?= pytest
PYTEST_FLAGS ?= -v

IMAGE_NAME ?= feast-mcp
IMAGE_TAG ?= latest
CONTAINER_RUNTIME ?= $(shell command -v podman 2>/dev/null || echo docker)

# External server URLs — set these to skip automatic server startup
# and test against servers you started in another terminal.
#
#   export FEAST_FEATURE_SERVER_URL=http://localhost:6566
#   export FEAST_REGISTRY_SERVER_URL=http://localhost:6572
#   export FEAST_MCP_SERVER_URL=http://localhost:8000
#
# For auth tests:
#   export FEAST_MOCK_OIDC_URL=http://localhost:8081
#   export FEAST_AUTH_FEATURE_SERVER_URL=http://localhost:6567
#   export FEAST_AUTH_REGISTRY_SERVER_URL=http://localhost:6573

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  External server mode:"
	@echo "    Set env vars to test against your own running servers:"
	@echo "      FEAST_FEATURE_SERVER_URL   Feature server base URL"
	@echo "      FEAST_REGISTRY_SERVER_URL  Registry server base URL"
	@echo "      FEAST_MCP_SERVER_URL       Standalone MCP server base URL"
	@echo ""
	@echo "  Container:"
	@echo "    IMAGE_NAME=feast-mcp IMAGE_TAG=latest make build-image"
	@echo "    CONTAINER_RUNTIME=podman make build-image"

# ---------------------------------------------------------------------------
# Install & dependency management
# ---------------------------------------------------------------------------

install: ## Install project from uv.lock (production deps only)
	uv sync --no-dev

install-dev: ## Install project with dev dependencies from uv.lock
	uv sync

sync: install-dev ## Alias for install-dev

update: ## Update all dependencies and refresh uv.lock
	uv lock --upgrade
	uv sync

# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------

lint: ## Lint all source and test files
	uv run ruff check feast_mcp/ tests/

format: ## Auto-format all source and test files
	uv run ruff format feast_mcp/ tests/
	uv run ruff check --fix feast_mcp/ tests/

# ---------------------------------------------------------------------------
# Container image
# ---------------------------------------------------------------------------

build-image: ## Build container image (IMAGE_NAME, IMAGE_TAG, CONTAINER_RUNTIME)
	$(CONTAINER_RUNTIME) build -f Containerfile -t $(IMAGE_NAME):$(IMAGE_TAG) .

push-image: ## Push container image to registry
	$(CONTAINER_RUNTIME) push $(IMAGE_NAME):$(IMAGE_TAG)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

test: ## Run all MCP migration tests
	uv run $(PYTEST) $(PYTEST_FLAGS) tests/

test-feature-server: ## Run feature server tool tests only
	uv run $(PYTEST) $(PYTEST_FLAGS) tests/test_feature_server.py

test-registry: ## Run registry server tool tests only
	uv run $(PYTEST) $(PYTEST_FLAGS) tests/test_registry_server.py

test-discovery: ## Run endpoint coverage check only
	uv run $(PYTEST) $(PYTEST_FLAGS) tests/test_discovery.py

test-auth: ## Run authorization tests only
	uv run $(PYTEST) $(PYTEST_FLAGS) tests/test_authorization.py

test-no-auth: ## Run all tests except authorization
	uv run $(PYTEST) $(PYTEST_FLAGS) tests/ --ignore=tests/test_authorization.py

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

clean: ## Remove generated artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf tests/feature_repo/data/registry.db tests/feature_repo/data/online_store.db
	rm -rf *.egg-info/ dist/ build/

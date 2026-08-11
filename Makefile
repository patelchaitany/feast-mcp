.PHONY: help install test test-feature-server test-registry test-discovery test-auth test-no-auth test-external lint format clean

PYTHON ?= python
PYTEST ?= pytest
PYTEST_FLAGS ?= -v

# External server URLs — set these to skip automatic server startup
# and test against servers you started in another terminal.
#
#   export FEAST_FEATURE_SERVER_URL=http://localhost:6566
#   export FEAST_REGISTRY_SERVER_URL=http://localhost:6572/api/v1
#   export FEAST_MCP_SERVER_URL=http://localhost:8000
#
# For auth tests:
#   export FEAST_MOCK_OIDC_URL=http://localhost:8081
#   export FEAST_AUTH_FEATURE_SERVER_URL=http://localhost:6567
#   export FEAST_AUTH_REGISTRY_SERVER_URL=http://localhost:6573/api/v1

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  External server mode:"
	@echo "    Set env vars to test against your own running servers:"
	@echo "      FEAST_FEATURE_SERVER_URL   Feature server base URL"
	@echo "      FEAST_REGISTRY_SERVER_URL  Registry server base URL (include /api/v1)"
	@echo "      FEAST_MCP_SERVER_URL       Standalone MCP server base URL"
	@echo ""
	@echo "  Example:"
	@echo "    FEAST_FEATURE_SERVER_URL=http://localhost:6566 \\"
	@echo "    FEAST_MCP_SERVER_URL=http://localhost:8000 \\"
	@echo "      make test-feature-server"

install: ## Install MCP server + test dependencies
	pip install -e ".[dev]"
	pip install -e "../[mcp]"
	pip install httpx

test: ## Run all MCP migration tests
	$(PYTEST) $(PYTEST_FLAGS) tests/

test-feature-server: ## Run feature server tool tests only
	$(PYTEST) $(PYTEST_FLAGS) tests/test_feature_server.py

test-registry: ## Run registry server tool tests only
	$(PYTEST) $(PYTEST_FLAGS) tests/test_registry_server.py

test-discovery: ## Run endpoint coverage check only
	$(PYTEST) $(PYTEST_FLAGS) tests/test_discovery.py

test-auth: ## Run authorization tests only
	$(PYTEST) $(PYTEST_FLAGS) tests/test_authorization.py

test-no-auth: ## Run all tests except authorization
	$(PYTEST) $(PYTEST_FLAGS) tests/ --ignore=tests/test_authorization.py

lint: ## Lint all test and source files
	ruff check tests/ feast_mcp/
	ruff format --check tests/ feast_mcp/

format: ## Auto-format all test and source files
	ruff format tests/ feast_mcp/
	ruff check --fix tests/ feast_mcp/

clean: ## Remove generated artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf tests/feature_repo/data/registry.db tests/feature_repo/data/online_store.db

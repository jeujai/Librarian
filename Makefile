.PHONY: help install dev-install test lint format type-check clean run docker-build docker-run dev up down logs shell test-docker prod clean-docker backup restore health monitor ssl-cert quickstart dev-setup dev-teardown

help: ## Show this help message
	@echo "Multimodal Librarian - Available commands:"
	@echo ""
	@echo "Development:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*Development.*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Testing:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*Test.*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Production:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*Production.*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Resource Management:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*Resource.*$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $1, $2}'
	@echo ""
	@echo "Maintenance:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*Maintenance.*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	pip install -r requirements.txt

dev-install: ## Development - Install development dependencies
	pip install -r requirements.txt
	pip install -e .

test: ## Test - Run tests locally
	pytest -v --tb=short

test-local: ## Test - Run tests against local services
	@echo "Running tests against local Docker Compose services..."
	@if [ ! -f .env.local ]; then \
		echo "Creating .env.local from template for testing..."; \
		cp .env.local.example .env.local; \
	fi
	@echo "Checking if local services are running..."
	@./scripts/health-check-all-services.py --quiet || { \
		echo "⚠️  Local services not running. Starting them..."; \
		make dev-local; \
		echo "Waiting for services to be ready..."; \
		./scripts/wait-for-all-databases.sh --file docker-compose.local.yml --timeout 120; \
	}
	@echo "Running tests with local service configuration..."
	ML_ENVIRONMENT=test ML_DATABASE_TYPE=local pytest -v --tb=short -m "not aws_services" tests/

test-local-unit: ## Test - Run unit tests only (no external services required)
	@echo "Running unit tests (no external services required)..."
	ML_ENVIRONMENT=test pytest -v --tb=short -m "unit" tests/

test-local-integration: ## Test - Run integration tests against local services
	@echo "Running integration tests against local services..."
	@./scripts/health-check-all-services.py --quiet || { \
		echo "❌ Local services not running. Please run 'make dev-local' first."; \
		exit 1; \
	}
	ML_ENVIRONMENT=test ML_DATABASE_TYPE=local pytest -v --tb=short -m "integration and local_services" tests/

test-local-database: ## Test - Run database-specific tests
	@echo "Running database tests against local services..."
	@./scripts/health-check-all-services.py --quiet || { \
		echo "❌ Local services not running. Please run 'make dev-local' first."; \
		exit 1; \
	}
	ML_ENVIRONMENT=test ML_DATABASE_TYPE=local pytest -v --tb=short -m "database" tests/

test-local-config: ## Test - Run configuration tests for local setup
	@echo "Running configuration tests for local setup..."
	ML_ENVIRONMENT=test ML_DATABASE_TYPE=local pytest -v --tb=short tests/config/ tests/clients/

test-cov: ## Test - Run tests with coverage
	pytest --cov=multimodal_librarian --cov-report=html --cov-report=term

test-cov-local: ## Test - Run tests with coverage against local services
	@echo "Running tests with coverage against local services..."
	@./scripts/health-check-all-services.py --quiet || { \
		echo "⚠️  Local services not running. Starting them..."; \
		make dev-local; \
		echo "Waiting for services to be ready..."; \
		./scripts/wait-for-all-databases.sh --file docker-compose.local.yml --timeout 120; \
	}
	ML_ENVIRONMENT=test ML_DATABASE_TYPE=local pytest --cov=multimodal_librarian --cov-report=html --cov-report=term -m "not aws_services" tests/

test-docker: ## Test - Run tests in Docker containers
	docker-compose -f docker-compose.yml -f docker-compose.test.yml up --build --abort-on-container-exit app

test-docker-local: ## Test - Run tests in Docker with local services
	@echo "Running tests in Docker with local services..."
	docker-compose -f docker-compose.local.yml run --rm multimodal-librarian pytest -v --tb=short -m "not aws_services" tests/

test-services-health: ## Test - Check health of all local services
	@echo "Checking health of all local services..."
	@./scripts/health-check-all-services.py --verbose

test-services-connectivity: ## Test - Test connectivity to all local services
	@echo "Testing connectivity to all local services..."
	@python3 -c "\
import sys; \
sys.path.append('src'); \
from tests.test_config_local import LocalServiceTestConfig; \
import socket; \
config = LocalServiceTestConfig(); \
services = config.get_all_configs(); \
failed = []; \
[print(f'✅ {name}: Connected') if not failed.append(name) and socket.create_connection((cfg['host'], cfg['port']), timeout=5) else print(f'❌ {name}: Failed') for name, cfg in services.items()]; \
print('✅ All services accessible') if not failed else (print(f'❌ Failed: {failed}') or exit(1))"

# Configuration Validation Targets
validate-config: ## Validation - Validate configuration settings
	@echo "🔍 Validating configuration..."
	@python3 scripts/validate-config.py

validate-connectivity: ## Validation - Test connectivity to all services
	@echo "🔗 Testing service connectivity..."
	@python3 scripts/validate-config.py --connectivity

validate-docker: ## Validation - Validate Docker environment
	@echo "🐳 Validating Docker environment..."
	@python3 scripts/validate-config.py --docker

validate-all: ## Validation - Run all validation checks
	@echo "🔍 Running comprehensive validation..."
	@python3 scripts/validate-config.py --connectivity --docker

validate-fix: ## Validation - Validate and attempt to fix issues
	@echo "🔧 Validating configuration and attempting fixes..."
	@python3 scripts/validate-config.py --connectivity --docker --fix

validate-json: ## Validation - Output validation results in JSON format
	@python3 scripts/validate-config.py --connectivity --docker --json

lint: ## Run linting
	flake8 src/ tests/

format: ## Format code
	black src/ tests/
	isort src/ tests/

type-check: ## Run type checking
	mypy src/

quality: format lint type-check ## Run all code quality checks

clean: ## Maintenance - Clean up generated files
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/
	rm -rf dist/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/

clean-docker: ## Maintenance - Clean up Docker resources
	docker-compose down -v --remove-orphans
	docker system prune -f
	docker volume prune -f

run: ## Development - Run the application locally
	python -m multimodal_librarian.main

dev: ## Development - Start development environment with Docker
	@echo "Starting development environment..."
	docker-compose up --build -d
	@echo "Services started. Access the application at http://localhost:8000"
	@echo "API docs available at http://localhost:8000/docs"

dev-local: ## Development - Start local development environment with all services
	@echo "Starting local development environment..."
	@if [ ! -f .env.local ]; then \
		echo "Creating .env.local from template..."; \
		cp .env.local.example .env.local; \
		echo "⚠️  Please edit .env.local with your API keys"; \
	fi
	docker-compose -f docker-compose.local.yml up --build -d
	@echo ""
	@echo "🚀 Local development environment started!"
	@echo ""
	@echo "⏳ Waiting for services to be ready..."
	@./scripts/wait-for-all-databases.sh --file docker-compose.local.yml --timeout 300
	@echo ""
	@echo "📋 Services:"
	@echo "  • Application:     http://localhost:8000"
	@echo "  • API Docs:        http://localhost:8000/docs"
	@echo "  • PostgreSQL:      localhost:5432 (ml_user/ml_password)"
	@echo "  • Neo4j Browser:   http://localhost:7474 (neo4j/ml_password)"
	@echo "  • pgAdmin:         http://localhost:5050 (admin@multimodal-librarian.local/admin)"
	@echo "  • Milvus Admin:    http://localhost:3000"
	@echo "  • Redis Commander: http://localhost:8081"
	@echo ""
	@echo "🔧 Useful commands:"
	@echo "  make logs          - View service logs"
	@echo "  make db-status     - Check database status"
	@echo "  make health        - Run health checks"
	@echo "  make network-info  - Show network information"
	@echo "  make down          - Stop all services"
	@echo ""
	@echo "✅ Local development environment is ready for use!"

# =============================================================================
# OPTIMIZED HOT RELOAD TARGETS
# =============================================================================

dev-hot-reload: ## Development - Start optimized hot reload development environment
	@echo "🔥 Starting optimized hot reload development environment..."
	@if [ ! -f .env.local ]; then \
		echo "Creating .env.local from template..."; \
		cp .env.local.example .env.local; \
		echo "⚠️  Please edit .env.local with your API keys"; \
	fi
	@echo "Building optimized development image..."
	docker-compose -f docker-compose.hot-reload-optimized.yml build --parallel
	@echo "Starting optimized services..."
	docker-compose -f docker-compose.hot-reload-optimized.yml up -d
	@echo ""
	@echo "🔥 Optimized hot reload environment started!"
	@echo ""
	@echo "⏳ Waiting for services to be ready..."
	@./scripts/wait-for-services.sh --timeout 120
	@echo ""
	@echo "📋 Services (Optimized):"
	@echo "  • Application:     http://localhost:8000 (with intelligent hot reload)"
	@echo "  • API Docs:        http://localhost:8000/docs"
	@echo "  • PostgreSQL:      localhost:5432 (optimized for development)"
	@echo "  • Neo4j Browser:   http://localhost:7474 (reduced memory footprint)"
	@echo "  • Milvus:          localhost:19530 (optimized configuration)"
	@echo "  • Redis:           localhost:6379 (development cache)"
	@echo ""
	@echo "🚀 Hot Reload Features:"
	@echo "  • Intelligent file watching (excludes cache files)"
	@echo "  • Priority-based restart delays (config: 0.2s, high: 0.5s, medium: 1s, low: 2s)"
	@echo "  • Selective module reloading where possible"
	@echo "  • Memory-efficient file change detection"
	@echo "  • Optimized container resource usage"
	@echo ""
	@echo "🔧 Hot Reload Commands:"
	@echo "  make hot-reload-logs    - View hot reload logs with filtering"
	@echo "  make hot-reload-status  - Check hot reload performance stats"
	@echo "  make hot-reload-restart - Manually restart application"
	@echo "  make hot-reload-stop    - Stop hot reload environment"
	@echo ""
	@echo "✅ Optimized hot reload environment is ready!"

dev-hot-reload-fast: ## Development - Start hot reload with minimal services (fastest startup)
	@echo "⚡ Starting minimal hot reload environment (fastest startup)..."
	@if [ ! -f .env.local ]; then \
		echo "Creating .env.local from template..."; \
		cp .env.local.example .env.local; \
	fi
	docker-compose -f docker-compose.hot-reload-optimized.yml up -d multimodal-librarian postgres redis
	@echo ""
	@echo "⚡ Minimal hot reload environment started!"
	@echo "  • Application: http://localhost:8000"
	@echo "  • Only essential services running for maximum speed"
	@echo ""
	@echo "💡 To add more services: make hot-reload-scale-up"

hot-reload-scale-up: ## Development - Add remaining services to minimal hot reload environment
	@echo "📈 Scaling up hot reload environment..."
	docker-compose -f docker-compose.hot-reload-optimized.yml up -d
	@echo "✅ All services now running"

hot-reload-logs: ## Development - View hot reload logs with intelligent filtering
	@echo "📋 Hot reload logs (filtered for relevance):"
	docker-compose -f docker-compose.hot-reload-optimized.yml logs -f multimodal-librarian | \
	grep -E "(🔄|🚀|✅|❌|⚠️|Hot reload|Server started|File|Error|Exception)" --line-buffered --color=always

hot-reload-logs-all: ## Development - View all hot reload logs
	docker-compose -f docker-compose.hot-reload-optimized.yml logs -f

hot-reload-status: ## Development - Check hot reload performance statistics
	@echo "📊 Hot reload performance statistics:"
	@docker-compose -f docker-compose.hot-reload-optimized.yml exec multimodal-librarian \
		python -c "import json, time; \
		try: \
			from scripts.optimized_hot_reload import OptimizedHotReloadManager; \
			print('Hot reload system is active'); \
		except: \
			print('Hot reload system status: Unknown')" 2>/dev/null || \
		echo "Hot reload container not running"

hot-reload-restart: ## Development - Manually restart the application in hot reload mode
	@echo "🔄 Manually restarting application..."
	docker-compose -f docker-compose.hot-reload-optimized.yml restart multimodal-librarian
	@echo "✅ Application restarted"

hot-reload-shell: ## Development - Open shell in hot reload container
	docker-compose -f docker-compose.hot-reload-optimized.yml exec multimodal-librarian /bin/bash

hot-reload-stop: ## Development - Stop hot reload environment
	@echo "🛑 Stopping hot reload environment..."
	docker-compose -f docker-compose.hot-reload-optimized.yml down
	@echo "✅ Hot reload environment stopped"

hot-reload-clean: ## Maintenance - Clean hot reload environment and volumes
	@echo "🧹 Cleaning hot reload environment..."
	docker-compose -f docker-compose.hot-reload-optimized.yml down -v --remove-orphans
	docker volume prune -f --filter label=com.docker.compose.project=multimodal-librarian-hot-reload
	@echo "✅ Hot reload environment cleaned"

hot-reload-benchmark: ## Development - Benchmark hot reload performance
	@echo "⏱️  Benchmarking hot reload performance..."
	@python3 scripts/benchmark-hot-reload.py

hot-reload-optimize: ## Development - Run hot reload optimization analysis
	@echo "🔧 Analyzing hot reload performance..."
	@python3 scripts/analyze-hot-reload-performance.py

up: ## Development - Start all Docker services
	docker-compose up -d

down: ## Development - Stop all Docker services
	docker-compose down

# =============================================================================
# GRACEFUL SHUTDOWN TARGETS
# =============================================================================

dev-shutdown: ## Development - Graceful shutdown of local development environment
	@echo "🛑 Performing graceful shutdown of local development environment..."
	@python scripts/graceful-shutdown.py

dev-shutdown-force: ## Development - Forced shutdown if graceful shutdown fails
	@echo "🔨 Performing forced shutdown of local development environment..."
	@python scripts/graceful-shutdown.py --force

dev-shutdown-quick: ## Development - Quick shutdown with 30s timeout
	@echo "⚡ Performing quick shutdown (30s timeout)..."
	@python scripts/graceful-shutdown.py --timeout 30

dev-shutdown-services: ## Development - Shutdown specific services only
	@echo "🎯 Shutting down specific services..."
	@read -p "Enter services (comma-separated): " services; \
	python scripts/graceful-shutdown.py --services "$$services"

dev-shutdown-dry-run: ## Development - Show what graceful shutdown would do
	@echo "🔍 Showing what graceful shutdown would do..."
	@python scripts/graceful-shutdown.py --dry-run

dev-shutdown-status: ## Development - Check shutdown status
	@echo "📊 Checking shutdown status..."
	@python -c "from src.multimodal_librarian.shutdown import get_shutdown_status; import json; print(json.dumps(get_shutdown_status(), indent=2))" 2>/dev/null || echo "Application not running or shutdown handler not available"

logs: ## Development - Show logs from all services
	docker-compose logs -f

logs-local: ## Development - Show logs from local development services
	docker-compose -f docker-compose.local.yml logs -f

logs-viewer: ## Development - Interactive log viewer with filtering and search
	@echo "Starting interactive log viewer..."
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import curses, docker" >/dev/null 2>&1; then \
		python3 scripts/logs-viewer.py --compose-file docker-compose.local.yml; \
	else \
		echo "⚠️  Interactive log viewer not available (missing: pip install docker or curses support)"; \
		echo "Using basic log viewer instead:"; \
		docker-compose -f docker-compose.local.yml logs -f; \
	fi

logs-analyze: ## Development - Analyze logs for errors and patterns
	@echo "Analyzing logs..."
	./scripts/logs-analyze.sh

logs-cleanup: ## Maintenance - Clean up old log files
	@echo "Cleaning up log files..."
	./scripts/logs-cleanup.sh

logs-status: ## Maintenance - Show log directory status
	@echo "Log directory status:"
	./scripts/logs-cleanup.sh status

shell: ## Development - Open shell in app container
	docker-compose exec app /bin/bash

docker-build: ## Build Docker image
	docker-compose build

docker-run: ## Run Docker container
	docker run -p 8000:8000 multimodal-librarian

prod: ## Production - Start production environment
	@echo "Starting production environment..."
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

prod-build: ## Production - Build production images
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml build

prod-deploy: ## Production - Deploy to production
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --force-recreate

backup: backup-all-databases ## Maintenance - Backup all databases

restore: ## Maintenance - Restore databases from backup
	./database/postgresql/restore.sh latest

health: ## Maintenance - Check service health
	@echo "Checking service health..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/check-all-database-health.py; \
	else \
		echo "⚠️  Python3 not available, using basic health checks"; \
		curl -f http://localhost:8000/health/simple || echo "App service unhealthy"; \
		./database/postgresql/manage.sh health; \
	fi

debug-service: ## Development - Debug specific service (usage: make debug-service SERVICE=postgres)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Please specify service: make debug-service SERVICE=postgres"; \
		echo "Available services: multimodal-librarian, postgres, neo4j, milvus, redis, etcd, minio"; \
		exit 1; \
	fi
	@echo "Debugging service: $(SERVICE)"
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import docker, requests" >/dev/null 2>&1; then \
		python3 scripts/debug-service.py $(SERVICE) --compose-file docker-compose.local.yml; \
	else \
		echo "⚠️  Service debugger not available (missing: pip install docker requests)"; \
		echo "Using basic debugging:"; \
		docker-compose -f docker-compose.local.yml logs --tail=50 $(SERVICE); \
	fi

debug-network: ## Development - Debug network connectivity issues
	@echo "Debugging network connectivity..."
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import docker, requests" >/dev/null 2>&1; then \
		python3 scripts/debug-network.py --compose-file docker-compose.local.yml; \
	else \
		echo "⚠️  Network debugger not available (missing: pip install docker requests)"; \
		echo "Using basic network checks:"; \
		docker network ls | grep multimodal-librarian; \
		docker-compose -f docker-compose.local.yml ps; \
	fi

health-json: ## Maintenance - Check service health (JSON output)
	@python3 scripts/check-all-database-health.py --json

health-quiet: ## Maintenance - Check service health (summary only)
	@python3 scripts/check-all-database-health.py --quiet

health-postgres: ## Maintenance - Check PostgreSQL health only
	@python3 scripts/check-all-database-health.py --services postgresql

health-neo4j: ## Maintenance - Check Neo4j health only
	@python3 scripts/check-all-database-health.py --services neo4j

health-milvus: ## Maintenance - Check Milvus health only
	@python3 scripts/check-all-database-health.py --services milvus

health-redis: ## Maintenance - Check Redis health only
	@python3 scripts/check-all-database-health.py --services redis

wait-for-databases: ## Development - Wait for all database services to be ready
	@./scripts/wait-for-all-databases.sh

db-status: ## Maintenance - Show database service status
	@echo "Database Service Status:"
	@echo "========================"
	@docker-compose -f docker-compose.local.yml ps postgres neo4j milvus redis etcd minio
	@echo ""
	@echo "Health Status:"
	@echo "=============="
	@python3 scripts/check-all-database-health.py --quiet

monitor: ## Maintenance - Show service status and resource usage
	@echo "Service status:"
	docker-compose -f docker-compose.local.yml ps
	@echo ""
	@echo "Resource usage:"
	docker stats --no-stream

# Network Management Commands
network-info: ## Maintenance - Show network information
	@echo "Network information:"
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import docker" >/dev/null 2>&1; then \
		python3 scripts/network_config.py --network multimodal-librarian-local info; \
	else \
		echo "⚠️  Advanced network info not available (missing: pip install docker)"; \
		docker network ls | grep multimodal-librarian; \
		docker network inspect multimodal-librarian-local 2>/dev/null || echo "Network not found"; \
	fi

network-diagnose: ## Maintenance - Diagnose network connectivity issues
	@echo "Diagnosing network connectivity..."
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import docker, aiohttp" >/dev/null 2>&1; then \
		python3 scripts/network_troubleshoot.py --network multimodal-librarian-local; \
	else \
		echo "⚠️  Network diagnosis not available (missing: pip install docker aiohttp)"; \
		echo "Basic network check:"; \
		docker network inspect multimodal-librarian-local >/dev/null 2>&1 && echo "✅ Network exists" || echo "❌ Network missing"; \
	fi

network-create: ## Maintenance - Create development network
	@echo "Creating development network..."
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import docker" >/dev/null 2>&1; then \
		python3 scripts/network_config.py --network multimodal-librarian-local create; \
	else \
		echo "⚠️  Advanced network creation not available (missing: pip install docker)"; \
		docker network create --driver bridge --subnet 172.21.0.0/16 multimodal-librarian-local; \
	fi

network-remove: ## Maintenance - Remove development network
	@echo "Removing development network..."
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import docker" >/dev/null 2>&1; then \
		python3 scripts/network_config.py --network multimodal-librarian-local remove; \
	else \
		docker network rm multimodal-librarian-local 2>/dev/null || echo "Network not found"; \
	fi

# Service Discovery Commands
service-discovery: ## Maintenance - Run service discovery
	@echo "Running service discovery..."
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import aiohttp, docker" >/dev/null 2>&1; then \
		python3 scripts/service_discovery.py --compose-file docker-compose.local.yml; \
	else \
		echo "⚠️  Service discovery not available (missing: pip install aiohttp docker)"; \
		echo "Use basic health checks instead: make health"; \
	fi

service-monitor: ## Maintenance - Start continuous service monitoring
	@echo "Starting service health monitoring..."
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import aiohttp, docker" >/dev/null 2>&1; then \
		python3 scripts/health_monitor.py --compose-file docker-compose.local.yml --interval 30; \
	else \
		echo "⚠️  Service monitoring not available (missing: pip install aiohttp docker)"; \
		echo "Install requirements: pip install aiohttp docker"; \
	fi

wait-for-services: ## Maintenance - Wait for all services to be ready
	@echo "Waiting for services to be ready..."
	./scripts/wait-for-services.sh --compose-file docker-compose.local.yml --timeout 300

# PostgreSQL Database Management Commands
backup-all: ## Maintenance - Create all types of backups
	@echo "Creating all backup types..."
	./database/postgresql/backup.sh all

restore-file: ## Maintenance - Restore from specific backup file (usage: make restore-file BACKUP_FILE=path/to/backup.sql)
	@if [ -z "$(BACKUP_FILE)" ]; then \
		echo "Please specify backup file: make restore-file BACKUP_FILE=backups/postgres_20231201_120000.sql"; \
		exit 1; \
	fi
	./database/postgresql/restore.sh file $(BACKUP_FILE)

db-maintenance: ## Maintenance - Run database maintenance
	./database/postgresql/manage.sh maintenance

db-shell: ## Development - Open PostgreSQL shell
	./database/postgresql/manage.sh shell

db-reset: ## Development - Reset database (DANGEROUS!)
	./database/postgresql/manage.sh reset

ssl-cert: ## Production - Generate SSL certificates
	@echo "Generating SSL certificates..."
	mkdir -p ssl
	openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
		-keyout ssl/key.pem \
		-out ssl/cert.pem \
		-subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"

setup-env: ## Set up environment file
	cp .env.example .env
	@echo "Please edit .env with your configuration"

init-db: ## Initialize database (placeholder)
	@echo "Database initialization not yet implemented"

quickstart: setup-env dev ## Development - Quick start for new developers
	@echo ""
	@echo "🚀 Multimodal Librarian is starting up!"
	@echo ""
	@echo "📝 Next steps:"
	@echo "1. Edit .env file with your API keys"
	@echo "2. Wait for services to start (check with 'make logs')"
	@echo "3. Access the application at http://localhost:8000"
	@echo "4. API documentation at http://localhost:8000/docs"
	@echo ""
	@echo "🔧 Useful commands:"
	@echo "  make logs    - View service logs"
	@echo "  make shell   - Open app container shell"
	@echo "  make test-docker - Run tests"
	@echo "  make down    - Stop services"

setup: setup-env dev-install ## Complete setup for development
	@echo "Setup complete! Edit .env file and run 'make run' to start the application"

# =============================================================================
# HOT RELOAD DEVELOPMENT TARGETS
# =============================================================================

dev-hot-reload: dev-local-setup ## Development - Start development with enhanced hot reload
	@echo "🔥 Starting development environment with enhanced hot reload..."
	@if [ ! -f .env.local ]; then \
		cp .env.local.example .env.local; \
		echo "✅ Created .env.local from template"; \
		echo "⚠️  Please edit .env.local with your API keys"; \
	fi
	docker-compose -f docker-compose.local.yml up -d --build
	@echo "⏳ Waiting for services to be ready..."
	./scripts/wait-for-services.sh
	@echo ""
	@echo "🔥 Hot reload development environment is ready!"
	@echo ""
	@echo "📋 Services:"
	@echo "  • Application:     http://localhost:8000 (with hot reload)"
	@echo "  • API Docs:        http://localhost:8000/docs"
	@echo "  • PostgreSQL:      localhost:5432 (ml_user/ml_password)"
	@echo "  • Neo4j Browser:   http://localhost:7474 (neo4j/ml_password)"
	@echo "  • pgAdmin:         http://localhost:5050 (admin@multimodal-librarian.local/admin)"
	@echo "  • Milvus Admin:    http://localhost:3000"
	@echo "  • Redis Commander: http://localhost:8081"
	@echo ""
	@echo "🔥 Hot Reload Features:"
	@echo "  • Automatic restart on Python file changes"
	@echo "  • Configuration file monitoring (.env.local, pyproject.toml)"
	@echo "  • YAML/JSON configuration hot reload"
	@echo "  • Intelligent exclusion of cache files"
	@echo "  • Real-time feedback on file changes"
	@echo ""
	@echo "🔧 Useful commands:"
	@echo "  make logs-hot-reload   - View hot reload logs"
	@echo "  make restart-app       - Restart just the application"
	@echo "  make shell-hot-reload  - Open shell in app container"
	@echo "  make down              - Stop all services"

dev-hot-reload-shell: ## Development - Open shell in hot reload container
	docker-compose -f docker-compose.local.yml exec multimodal-librarian /bin/bash

logs-hot-reload: ## Development - Show hot reload application logs
	docker-compose -f docker-compose.local.yml logs -f multimodal-librarian

restart-app: ## Development - Restart just the application container
	@echo "🔄 Restarting application container..."
	docker-compose -f docker-compose.local.yml restart multimodal-librarian
	@echo "✅ Application container restarted"

watch-files: ## Development - Watch file changes (for debugging hot reload)
	@echo "👀 Watching file changes in src/ directory..."
	@echo "Press Ctrl+C to stop watching"
	@if command -v inotifywait >/dev/null 2>&1; then \
		inotifywait -m -r -e modify,create,delete --format '%T %w%f %e' --timefmt '%H:%M:%S' src/; \
	elif command -v fswatch >/dev/null 2>&1; then \
		fswatch -o src/ | while read f; do echo "$$(date '+%H:%M:%S') File change detected"; done; \
	else \
		echo "⚠️  File watching tools not available (install inotify-tools or fswatch)"; \
		echo "Hot reload is still active inside the container"; \
	fi

# =============================================================================
# LOCAL DEVELOPMENT TARGETS
# =============================================================================

# CI/CD Testing Targets
test-ci-local: ## Test - Run CI/CD tests with local services (GitHub Actions compatible)
	@echo "🧪 Running CI/CD tests with local services..."
	./scripts/run-local-tests.sh all --coverage --github-services

test-ci-local-unit: ## Test - Run CI/CD unit tests only
	@echo "🧪 Running CI/CD unit tests..."
	./scripts/run-local-tests.sh unit --fast --github-services

test-ci-local-integration: ## Test - Run CI/CD integration tests
	@echo "🧪 Running CI/CD integration tests..."
	./scripts/run-local-tests.sh integration --github-services

test-ci-local-docker: ## Test - Run CI/CD Docker Compose tests
	@echo "🧪 Running CI/CD Docker Compose tests..."
	./scripts/run-local-tests.sh docker --docker-compose

test-ci-local-performance: ## Test - Run CI/CD performance tests
	@echo "🧪 Running CI/CD performance tests..."
	./scripts/run-local-tests.sh performance --github-services

test-ci-local-clients: ## Test - Run CI/CD database client tests
	@echo "🧪 Running CI/CD database client tests..."
	./scripts/run-local-tests.sh clients --github-services

test-ci-local-config: ## Test - Run CI/CD configuration tests
	@echo "🧪 Running CI/CD configuration tests..."
	./scripts/run-local-tests.sh config --github-services

test-ci-local-parallel: ## Test - Run CI/CD tests in parallel
	@echo "🧪 Running CI/CD tests in parallel..."
	./scripts/run-local-tests.sh all --parallel --coverage --github-services

# Local Testing Script Targets
test-script-local: ## Test - Run local tests using test script
	@echo "🧪 Running local tests using test script..."
	./scripts/run-local-tests.sh all

test-script-local-verbose: ## Test - Run local tests with verbose output
	@echo "🧪 Running local tests with verbose output..."
	./scripts/run-local-tests.sh all --verbose

test-script-local-coverage: ## Test - Run local tests with coverage
	@echo "🧪 Running local tests with coverage..."
	./scripts/run-local-tests.sh all --coverage

test-script-local-fast: ## Test - Run fast local tests only
	@echo "🧪 Running fast local tests..."
	./scripts/run-local-tests.sh all --fast

test-script-local-docker: ## Test - Run local tests with Docker Compose
	@echo "🧪 Running local tests with Docker Compose..."
	./scripts/run-local-tests.sh all --docker-compose

test-script-local-parallel: ## Test - Run local tests in parallel
	@echo "🧪 Running local tests in parallel..."
	./scripts/run-local-tests.sh all --parallel

test-script-services-only: ## Test - Start services only (for manual testing)
	@echo "🚀 Starting services for manual testing..."
	./scripts/run-local-tests.sh all --services

test-script-cleanup: ## Test - Clean up all test resources
	@echo "🧹 Cleaning up test resources..."
	./scripts/run-local-tests.sh --cleanup

# Environment Switching Tests
test-env-switching: ## Test - Test environment switching functionality
	@echo "🔄 Testing environment switching..."
	@export ML_ENVIRONMENT=test && \
	export ML_DATABASE_TYPE=local && \
	python -c "
from multimodal_librarian.config.config_factory import get_database_config
config = get_database_config()
print(f'✅ Local config: {type(config).__name__}')
assert 'Local' in type(config).__name__ or 'local' in str(type(config)).lower()
" && \
	export ML_DATABASE_TYPE=aws && \
	python -c "
from multimodal_librarian.config.config_factory import get_database_config
try:
    config = get_database_config()
    print(f'✅ AWS config: {type(config).__name__}')
except Exception as e:
    print(f'⚠️ AWS config (expected in local env): {e}')
" && \
	echo "✅ Environment switching tests passed"

test-database-factory: ## Test - Test database factory with both environments
	@echo "🏭 Testing database factory..."
	@export ML_ENVIRONMENT=test && \
	export ML_DATABASE_TYPE=local && \
	python -c "
from multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
from multimodal_librarian.config.config_factory import get_database_config
config = get_database_config()
factory = DatabaseClientFactory(config)
print('✅ Database factory created successfully')
print(f'✅ Config type: {type(config).__name__}')
" && \
	echo "✅ Database factory tests passed"

# Test Environment Management
test-env-setup: ## Test - Set up test environment
	@echo "⚙️ Setting up test environment..."
	@if [ ! -f .env.test ]; then \
		cp .env.local.example .env.test; \
		echo "✅ Created .env.test from template"; \
	fi
	@echo "✅ Test environment ready"

test-env-cleanup: ## Test - Clean up test environment
	@echo "🧹 Cleaning up test environment..."
	@rm -f .env.test
	@rm -rf htmlcov/
	@rm -f .coverage
	@rm -f coverage.xml
	@rm -f test-results-*.xml
	@rm -f integration-results-*.xml
	@rm -f client-results-*.xml
	@rm -f benchmark-results.json
	@echo "✅ Test environment cleaned up"

# Test Service Management
test-services-start: ## Test - Start test services
	@echo "🚀 Starting test services..."
	@./scripts/run-local-tests.sh all --services --keep

test-services-stop: ## Test - Stop test services
	@echo "🛑 Stopping test services..."
	@./scripts/run-local-tests.sh --cleanup

test-services-restart: ## Test - Restart test services
	@echo "🔄 Restarting test services..."
	@./scripts/run-local-tests.sh --cleanup
	@sleep 5
	@./scripts/run-local-tests.sh all --services --keep

test-services-status: ## Test - Check test services status
	@echo "📊 Test services status:"
	@docker-compose -f docker-compose.local.yml ps 2>/dev/null || echo "❌ Docker Compose services not running"
	@echo ""
	@echo "🔍 Service connectivity:"
	@python3 -c "
import socket
services = [
    ('PostgreSQL', 'localhost', 5432),
    ('Neo4j', 'localhost', 7687),
    ('Milvus', 'localhost', 19530),
    ('Redis', 'localhost', 6379)
]
for name, host, port in services:
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f'✅ {name}: {host}:{port}')
    except:
        print(f'❌ {name}: {host}:{port}')
"

# Test Reporting
test-report-generate: ## Test - Generate comprehensive test report
	@echo "📋 Generating test report..."
	@if [ -f test-results-*.xml ]; then \
		echo "📊 Test Results Summary:" > test-report.md; \
		echo "======================" >> test-report.md; \
		echo "" >> test-report.md; \
		echo "**Generated:** $(date)" >> test-report.md; \
		echo "" >> test-report.md; \
		for file in test-results-*.xml; do \
			echo "- $$file" >> test-report.md; \
		done; \
		echo "✅ Test report generated: test-report.md"; \
	else \
		echo "❌ No test results found. Run tests first."; \
	fi

test-report-view: ## Test - View test report
	@if [ -f test-report.md ]; then \
		cat test-report.md; \
	else \
		echo "❌ No test report found. Run 'make test-report-generate' first."; \
	fi

test-report-cleanup: ## Test - Clean up test reports
	@echo "🧹 Cleaning up test reports..."
	@rm -f test-report.md
	@rm -f test-summary.md
	@echo "✅ Test reports cleaned up"

# =============================================================================
# LOCAL DEVELOPMENT TARGETS
# =============================================================================

dev-local-admin: dev-local-setup ## Development - Start local environment with admin tools
	@echo "🚀 Starting local development environment with admin tools..."
	docker-compose -f docker-compose.local.yml --profile admin-tools up -d
	@echo "⏳ Waiting for services to be ready..."
	./scripts/wait-for-services.sh

dev-local-full: dev-local-setup ## Development - Start local environment with all profiles
	@echo "🚀 Starting local development environment with all features..."
	docker-compose -f docker-compose.local.yml --profile admin-tools --profile monitoring up -d
	@echo "⏳ Waiting for services to be ready..."
	./scripts/wait-for-services.sh

dev-setup: ## Development - Setup local development environment (initial setup)
	@echo "Setting up local development environment..."
	cp .env.local.example .env.local
	docker-compose -f docker-compose.local.yml pull

dev-local-setup: ## Development - Setup local development environment (enhanced)
	@echo "📋 Setting up local development environment..."
	@echo "🗂️  Creating development directories..."
	@./scripts/setup-development-directories.sh
	@if [ ! -f .env.local ]; then \
		cp .env.local.example .env.local; \
		echo "✅ Created .env.local from template"; \
		echo "⚠️  Please edit .env.local and add your API keys"; \
	else \
		echo "✅ .env.local already exists"; \
	fi
	@chmod +x scripts/wait-for-services.sh

dev-teardown: ## Development - Teardown local development environment
	@echo "Tearing down local development environment..."
	docker-compose -f docker-compose.local.yml down -v
	docker system prune -f

dev-local-teardown: ## Development - Stop and clean up local environment
	@echo "🧹 Tearing down local development environment..."
	docker-compose -f docker-compose.local.yml down -v --remove-orphans
	docker system prune -f

dev-aws: ## Development - Start AWS development environment
	@echo "☁️ Starting AWS development environment..."
	export ML_ENVIRONMENT=aws && uvicorn src.multimodal_librarian.main:app --reload --host 0.0.0.0 --port 8000

# Local database management
db-migrate-local: ## Development - Run database migrations for local environment
	@echo "🔄 Running database migrations for local environment..."
	export ML_ENVIRONMENT=local && python -m src.multimodal_librarian.database.migrations

db-init-neo4j: ## Development - Initialize Neo4j schema for local development
	@echo "🔄 Initializing Neo4j schema..."
	./scripts/initialize-neo4j-schema.sh

db-init-neo4j-no-sample: ## Development - Initialize Neo4j schema without sample data
	@echo "🔄 Initializing Neo4j schema (no sample data)..."
	./scripts/initialize-neo4j-schema.sh --skip-sample-data

db-port-migrations: ## Development - Port existing migrations to local setup
	@echo "🔄 Porting existing migrations to local PostgreSQL setup..."
	python scripts/port-migrations-to-local.py port

db-migration-status: ## Development - Check migration porting status
	@echo "📊 Checking migration porting status..."
	python scripts/port-migrations-to-local.py status

db-migration-verify: ## Development - Verify migration porting
	@echo "🔍 Verifying migration porting..."
	python scripts/port-migrations-to-local.py verify

db-migration-reset: ## Development - Reset migration state (WARNING: clears migration history)
	@echo "⚠️  Resetting migration state..."
	python scripts/port-migrations-to-local.py reset --force

db-seed-local: ## Development - Seed local databases with test data
	@echo "🌱 Seeding local databases with test data..."
	export ML_ENVIRONMENT=local && python scripts/seed-local-data.py

db-reset-local: ## Development - Reset local databases (WARNING: deletes all data)
	@echo "⚠️  Resetting local databases (this will delete all data)..."
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		echo ""; \
		docker-compose -f docker-compose.local.yml down -v; \
		docker-compose -f docker-compose.local.yml up -d; \
		./scripts/wait-for-services.sh; \
	else \
		echo ""; \
		echo "❌ Database reset cancelled"; \
	fi

# Testing with local services
test-local: ## Test - Run tests against local services
	@echo "🧪 Running tests against local services..."
	@echo "📋 Checking local services are running..."
	@if ! docker-compose -f docker-compose.local.yml ps | grep -q "Up"; then \
		echo "❌ Local services not running. Starting them first..."; \
		$(MAKE) dev-local; \
		echo "⏳ Waiting for services to be ready..."; \
		./scripts/wait-for-services.sh; \
	else \
		echo "✅ Local services are running"; \
	fi
	@echo "🔍 Verifying database connectivity..."
	@python3 scripts/check-all-database-health.py --quiet || (echo "❌ Database health check failed" && exit 1)
	@echo "🧪 Running test suite against local services..."
	@export ML_ENVIRONMENT=local && \
	export ML_DATABASE_TYPE=local && \
	export ML_POSTGRES_HOST=localhost && \
	export ML_NEO4J_HOST=localhost && \
	export ML_MILVUS_HOST=localhost && \
	pytest tests/ -v --tb=short \
		--durations=10 \
		--color=yes \
		-m "not slow" \
		--disable-warnings \
		|| (echo "❌ Tests failed against local services" && exit 1)
	@echo "✅ All tests passed against local services!"

test-local-integration: ## Test - Run integration tests against local services
	@echo "🧪 Running integration tests against local services..."
	@echo "📋 Checking local services are running..."
	@if ! docker-compose -f docker-compose.local.yml ps | grep -q "Up"; then \
		echo "❌ Local services not running. Starting them first..."; \
		$(MAKE) dev-local; \
		echo "⏳ Waiting for services to be ready..."; \
		./scripts/wait-for-services.sh; \
	fi
	@echo "🔍 Verifying database connectivity..."
	@python3 scripts/check-all-database-health.py --quiet || (echo "❌ Database health check failed" && exit 1)
	@echo "🧪 Running integration tests against local services..."
	@export ML_ENVIRONMENT=local && \
	export ML_DATABASE_TYPE=local && \
	pytest tests/integration/ -v --tb=short \
		--durations=10 \
		--color=yes \
		|| (echo "❌ Integration tests failed against local services" && exit 1)
	@echo "✅ All integration tests passed against local services!"

test-local-unit: ## Test - Run unit tests with local configuration
	@echo "🧪 Running unit tests with local configuration..."
	@export ML_ENVIRONMENT=local && \
	export ML_DATABASE_TYPE=local && \
	pytest tests/ -v --tb=short \
		--durations=10 \
		--color=yes \
		-m "not integration and not slow" \
		--disable-warnings \
		|| (echo "❌ Unit tests failed with local configuration" && exit 1)
	@echo "✅ All unit tests passed with local configuration!"

test-local-database: ## Test - Run database-specific tests against local services
	@echo "🧪 Running database tests against local services..."
	@echo "📋 Checking local services are running..."
	@if ! docker-compose -f docker-compose.local.yml ps | grep -q "Up"; then \
		echo "❌ Local services not running. Starting them first..."; \
		$(MAKE) dev-local; \
		echo "⏳ Waiting for services to be ready..."; \
		./scripts/wait-for-services.sh; \
	fi
	@echo "🔍 Verifying database connectivity..."
	@python3 scripts/check-all-database-health.py --quiet || (echo "❌ Database health check failed" && exit 1)
	@echo "🧪 Running database tests..."
	@export ML_ENVIRONMENT=local && \
	export ML_DATABASE_TYPE=local && \
	pytest tests/database/ tests/clients/ -v --tb=short \
		--durations=10 \
		--color=yes \
		|| (echo "❌ Database tests failed against local services" && exit 1)
	@echo "✅ All database tests passed against local services!"

test-local-components: ## Test - Run component tests against local services
	@echo "🧪 Running component tests against local services..."
	@echo "📋 Checking local services are running..."
	@if ! docker-compose -f docker-compose.local.yml ps | grep -q "Up"; then \
		echo "❌ Local services not running. Starting them first..."; \
		$(MAKE) dev-local; \
		echo "⏳ Waiting for services to be ready..."; \
		./scripts/wait-for-services.sh; \
	fi
	@echo "🔍 Verifying database connectivity..."
	@python3 scripts/check-all-database-health.py --quiet || (echo "❌ Database health check failed" && exit 1)
	@echo "🧪 Running component tests..."
	@export ML_ENVIRONMENT=local && \
	export ML_DATABASE_TYPE=local && \
	pytest tests/components/ -v --tb=short \
		--durations=10 \
		--color=yes \
		|| (echo "❌ Component tests failed against local services" && exit 1)
	@echo "✅ All component tests passed against local services!"

test-local-fast: ## Test - Run fast tests against local services (excludes slow tests)
	@echo "🧪 Running fast tests against local services..."
	@echo "📋 Checking local services are running..."
	@if ! docker-compose -f docker-compose.local.yml ps | grep -q "Up"; then \
		echo "❌ Local services not running. Starting them first..."; \
		$(MAKE) dev-local; \
		echo "⏳ Waiting for services to be ready..."; \
		./scripts/wait-for-services.sh; \
	fi
	@echo "🔍 Verifying database connectivity..."
	@python3 scripts/check-all-database-health.py --quiet || (echo "❌ Database health check failed" && exit 1)
	@echo "🧪 Running fast test suite..."
	@export ML_ENVIRONMENT=local && \
	export ML_DATABASE_TYPE=local && \
	pytest tests/ -v --tb=short \
		--durations=5 \
		--color=yes \
		-m "not slow and not integration" \
		--disable-warnings \
		|| (echo "❌ Fast tests failed against local services" && exit 1)
	@echo "✅ All fast tests passed against local services!"

test-local-coverage: ## Test - Run tests with coverage against local services
	@echo "🧪 Running tests with coverage against local services..."
	@echo "📋 Checking local services are running..."
	@if ! docker-compose -f docker-compose.local.yml ps | grep -q "Up"; then \
		echo "❌ Local services not running. Starting them first..."; \
		$(MAKE) dev-local; \
		echo "⏳ Waiting for services to be ready..."; \
		./scripts/wait-for-services.sh; \
	fi
	@echo "🔍 Verifying database connectivity..."
	@python3 scripts/check-all-database-health.py --quiet || (echo "❌ Database health check failed" && exit 1)
	@echo "🧪 Running test suite with coverage..."
	@export ML_ENVIRONMENT=local && \
	export ML_DATABASE_TYPE=local && \
	pytest tests/ --cov=multimodal_librarian \
		--cov-report=html --cov-report=term \
		--cov-report=xml \
		-v --tb=short \
		--durations=10 \
		--color=yes \
		-m "not slow" \
		|| (echo "❌ Tests with coverage failed against local services" && exit 1)
	@echo "✅ All tests passed with coverage report generated!"
	@echo "📊 Coverage report available at htmlcov/index.html"

# Local service management
logs-local: ## Development - Show logs from local services
	docker-compose -f docker-compose.local.yml logs -f

status-local: ## Development - Show status of local services
	@echo "📊 Local service status:"
	docker-compose -f docker-compose.local.yml ps
	@echo ""
	@echo "🔗 Service URLs:"
	@echo "   • Application: http://localhost:8000"
	@echo "   • Neo4j Browser: http://localhost:7474 (neo4j/ml_password)"
	@echo "   • MinIO Console: http://localhost:9001 (minioadmin/minioadmin)"
	@echo ""
	@echo "🔧 Admin Tools (with admin profile):"
	@echo "   • pgAdmin: http://localhost:5050"
	@echo "   • Attu (Milvus): http://localhost:3000"
	@echo "   • Redis Commander: http://localhost:8081"

restart-local: ## Development - Restart local services
	@echo "🔄 Restarting local services..."
	docker-compose -f docker-compose.local.yml restart

shell-local: ## Development - Open shell in local app container
	docker-compose -f docker-compose.local.yml exec multimodal-librarian /bin/bash

# =============================================================================
# DATABASE BACKUP AND RESTORE TARGETS
# =============================================================================

# Comprehensive backup targets
backup-all-databases: ## Maintenance - Backup all databases (PostgreSQL, Neo4j, Milvus, Redis)
	@echo "💾 Creating comprehensive backup of all databases..."
	./scripts/backup-all-databases.sh full

backup-all-schema: ## Maintenance - Backup all database schemas only
	@echo "💾 Creating schema-only backup of all databases..."
	./scripts/backup-all-databases.sh schema

backup-all-data: ## Maintenance - Backup all database data only
	@echo "💾 Creating data-only backup of all databases..."
	./scripts/backup-all-databases.sh data

backup-all-compressed: ## Maintenance - Create compressed backups of all databases
	@echo "💾 Creating compressed backup of all databases..."
	./scripts/backup-all-databases.sh compressed

# Individual database backup targets
backup-postgresql: ## Maintenance - Backup PostgreSQL database
	@echo "💾 Backing up PostgreSQL database..."
	./database/postgresql/backup.sh full

backup-postgresql-schema: ## Maintenance - Backup PostgreSQL schema only
	@echo "💾 Backing up PostgreSQL schema..."
	./database/postgresql/backup.sh schema

backup-postgresql-data: ## Maintenance - Backup PostgreSQL data only
	@echo "💾 Backing up PostgreSQL data..."
	./database/postgresql/backup.sh data

backup-postgresql-compressed: ## Maintenance - Create compressed PostgreSQL backup
	@echo "💾 Creating compressed PostgreSQL backup..."
	./database/postgresql/backup.sh compressed

backup-neo4j: ## Maintenance - Backup Neo4j graph database
	@echo "💾 Backing up Neo4j database..."
	./scripts/backup-neo4j.sh cypher

backup-neo4j-json: ## Maintenance - Backup Neo4j as JSON export
	@echo "💾 Backing up Neo4j as JSON..."
	./scripts/backup-neo4j.sh json

backup-neo4j-graphml: ## Maintenance - Backup Neo4j as GraphML export
	@echo "💾 Backing up Neo4j as GraphML..."
	./scripts/backup-neo4j.sh graphml

backup-neo4j-schema: ## Maintenance - Backup Neo4j schema only
	@echo "💾 Backing up Neo4j schema..."
	./scripts/backup-neo4j.sh schema

backup-neo4j-all: ## Maintenance - Create all types of Neo4j backups
	@echo "💾 Creating all Neo4j backup types..."
	./scripts/backup-neo4j.sh all

backup-milvus: ## Maintenance - Backup Milvus vector database
	@echo "💾 Backing up Milvus database..."
	python3 ./scripts/backup-milvus.py all

backup-milvus-system: ## Maintenance - Backup Milvus system information
	@echo "💾 Backing up Milvus system info..."
	python3 ./scripts/backup-milvus.py system

backup-milvus-collection: ## Maintenance - Backup specific Milvus collection (usage: make backup-milvus-collection COLLECTION=collection_name)
	@if [ -z "$(COLLECTION)" ]; then \
		echo "Please specify collection: make backup-milvus-collection COLLECTION=knowledge_chunks"; \
		exit 1; \
	fi
	@echo "💾 Backing up Milvus collection: $(COLLECTION)..."
	python3 ./scripts/backup-milvus.py collection --collection $(COLLECTION)

# Backup maintenance targets
backup-cleanup: ## Maintenance - Clean up old backup files (older than 7 days)
	@echo "🧹 Cleaning up old backup files..."
	./scripts/backup-all-databases.sh cleanup

backup-stats: ## Maintenance - Show backup statistics
	@echo "📊 Backup statistics:"
	./scripts/backup-all-databases.sh stats

backup-verify: ## Maintenance - Verify backup integrity
	@echo "🔍 Verifying backup integrity..."
	./scripts/backup-all-databases.sh verify

# Restore targets
restore-postgresql: ## Maintenance - Restore PostgreSQL from latest backup
	@echo "🔄 Restoring PostgreSQL from latest backup..."
	./database/postgresql/restore.sh latest

restore-postgresql-file: ## Maintenance - Restore PostgreSQL from specific file (usage: make restore-postgresql-file BACKUP_FILE=path/to/backup.sql)
	@if [ -z "$(BACKUP_FILE)" ]; then \
		echo "Please specify backup file: make restore-postgresql-file BACKUP_FILE=backups/postgresql/full_multimodal_librarian_20231201_120000.sql"; \
		exit 1; \
	fi
	@echo "🔄 Restoring PostgreSQL from: $(BACKUP_FILE)..."
	./database/postgresql/restore.sh file $(BACKUP_FILE)

restore-postgresql-schema: ## Maintenance - Restore PostgreSQL schema from latest backup
	@echo "🔄 Restoring PostgreSQL schema from latest backup..."
	./database/postgresql/restore.sh latest-schema

# Legacy backup target (for compatibility)
backup-local: backup-all-databases ## Maintenance - Backup local databases (alias for backup-all-databases)

health-local: ## Maintenance - Check local service health
	@echo "🏥 Checking local service health..."
	./scripts/wait-for-services.sh

# =============================================================================
# PERFORMANCE MONITORING TARGETS
# =============================================================================

monitor-performance: ## Maintenance - Start comprehensive performance monitoring
	@echo "📊 Starting comprehensive performance monitoring..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/monitor-local-development.py start --duration 60 --interval 30; \
	else \
		echo "❌ Python3 not available for performance monitoring"; \
		exit 1; \
	fi

monitor-performance-quick: ## Maintenance - Quick performance check (5 minutes)
	@echo "📊 Running quick performance check..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/monitor-local-development.py start --duration 5 --interval 10; \
	else \
		echo "❌ Python3 not available for performance monitoring"; \
		exit 1; \
	fi

monitor-performance-extended: ## Maintenance - Extended performance monitoring (2 hours)
	@echo "📊 Starting extended performance monitoring..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/monitor-local-development.py start --duration 120 --interval 60; \
	else \
		echo "❌ Python3 not available for performance monitoring"; \
		exit 1; \
	fi

monitor-dashboard: ## Maintenance - Launch interactive performance dashboard
	@echo "📊 Launching performance dashboard..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/monitor-local-development.py dashboard; \
	else \
		echo "❌ Python3 not available for performance dashboard"; \
		exit 1; \
	fi

monitor-health-check: ## Maintenance - Run comprehensive health check
	@echo "🏥 Running comprehensive health check..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/monitor-local-development.py check; \
	else \
		echo "❌ Python3 not available for health check"; \
		exit 1; \
	fi

monitor-benchmark: ## Maintenance - Run performance benchmarks
	@echo "🏁 Running performance benchmarks..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/monitor-local-development.py benchmark; \
	else \
		echo "❌ Python3 not available for benchmarks"; \
		exit 1; \
	fi

monitor-database: ## Maintenance - Monitor database performance only
	@echo "🗄️ Monitoring database performance..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/monitor-database-performance.py --database all --duration 30 --interval 10; \
	else \
		echo "❌ Python3 not available for database monitoring"; \
		exit 1; \
	fi

monitor-database-postgres: ## Maintenance - Monitor PostgreSQL performance only
	@echo "🐘 Monitoring PostgreSQL performance..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/monitor-database-performance.py --database postgres --duration 30 --interval 5; \
	else \
		echo "❌ Python3 not available for PostgreSQL monitoring"; \
		exit 1; \
	fi

monitor-database-neo4j: ## Maintenance - Monitor Neo4j performance only
	@echo "🕸️ Monitoring Neo4j performance..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/monitor-database-performance.py --database neo4j --duration 30 --interval 5; \
	else \
		echo "❌ Python3 not available for Neo4j monitoring"; \
		exit 1; \
	fi

monitor-database-milvus: ## Maintenance - Monitor Milvus performance only
	@echo "🔍 Monitoring Milvus performance..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/monitor-database-performance.py --database milvus --duration 30 --interval 5; \
	else \
		echo "❌ Python3 not available for Milvus monitoring"; \
		exit 1; \
	fi

monitor-resources: ## Maintenance - Monitor system and container resource usage
	@echo "📊 Monitoring system and container resource usage..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/monitor-resource-usage.py --duration 15 --interval 5 --containers; \
	else \
		echo "❌ Python3 not available for resource monitoring"; \
		exit 1; \
	fi

monitor-memory: ## Maintenance - Monitor memory usage for local development
	@echo "🧠 Starting memory usage monitoring..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/monitor-memory-usage.py --duration 30 --interval 10 --leak-detection; \
	else \
		echo "❌ Python3 not available for memory monitoring"; \
		exit 1; \
	fi

monitor-memory-quick: ## Maintenance - Quick memory check (10 minutes)
	@echo "🧠 Running quick memory check..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/monitor-memory-usage.py --duration 10 --interval 5; \
	else \
		echo "❌ Python3 not available for memory monitoring"; \
		exit 1; \
	fi

monitor-memory-extended: ## Maintenance - Extended memory monitoring (2 hours)
	@echo "🧠 Starting extended memory monitoring..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/monitor-memory-usage.py --duration 120 --interval 30 --leak-detection; \
	else \
		echo "❌ Python3 not available for memory monitoring"; \
		exit 1; \
	fi

monitor-memory-containers: ## Maintenance - Monitor container memory usage only
	@echo "🐳 Monitoring container memory usage..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/monitor-memory-usage.py --duration 20 --interval 10 --no-leak-detection; \
	else \
		echo "❌ Python3 not available for container memory monitoring"; \
		exit 1; \
	fi
	@echo "💻 Monitoring resource usage..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/monitor-resource-usage.py --duration 15 --interval 5; \
	else \
		echo "❌ Python3 not available for resource monitoring"; \
		exit 1; \
	fi

monitor-resources-detailed: ## Maintenance - Detailed resource monitoring with alerts
	@echo "💻 Starting detailed resource monitoring..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/monitor-resource-usage.py --duration 30 --interval 2 --alert-cpu 70 --alert-memory 80; \
	else \
		echo "❌ Python3 not available for resource monitoring"; \
		exit 1; \
	fi

monitor-system: ## Maintenance - Monitor overall system performance
	@echo "🖥️ Monitoring overall system performance..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/monitor-local-performance.py --duration 30 --interval 15 --services all; \
	else \
		echo "❌ Python3 not available for system monitoring"; \
		exit 1; \
	fi

monitor-report: ## Maintenance - Generate performance monitoring report
	@echo "📋 Generating performance monitoring report..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/monitor-local-development.py report; \
	else \
		echo "❌ Python3 not available for report generation"; \
		exit 1; \
	fi

monitor-alerts: ## Maintenance - Check for performance alerts
	@echo "🚨 Checking for performance alerts..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/monitor-local-development.py check --alerts; \
	else \
		echo "❌ Python3 not available for alert checking"; \
		exit 1; \
	fi

monitor-config: ## Maintenance - Show monitoring configuration
	@echo "⚙️ Monitoring configuration:"
	@if [ -f monitoring_config.json ]; then \
		cat monitoring_config.json | python3 -m json.tool; \
	else \
		echo "❌ monitoring_config.json not found"; \
		echo "Run 'make monitor-performance' to create default configuration"; \
	fi

monitor-logs: ## Maintenance - View performance monitoring logs
	@echo "📜 Performance monitoring logs:"
	@if [ -f performance_dashboard.log ]; then \
		tail -50 performance_dashboard.log; \
	else \
		echo "❌ No performance monitoring logs found"; \
	fi

monitor-clean: ## Maintenance - Clean up monitoring reports and logs
	@echo "🧹 Cleaning up monitoring reports and logs..."
	@rm -rf monitoring_reports/
	@rm -f performance_dashboard.log
	@rm -f *.json | grep -E "(performance|database|resources)_[0-9]{8}_[0-9]{6}\.json" || true
	@echo "✅ Monitoring cleanup completed"

monitor-status: ## Maintenance - Show monitoring system status
	@echo "📊 Monitoring System Status:"
	@echo "============================"
	@echo ""
	@echo "🔧 Available Scripts:"
	@ls -la scripts/monitor-*.py 2>/dev/null | awk '{print "  " $$9}' || echo "  ❌ No monitoring scripts found"
	@echo ""
	@echo "📁 Report Directory:"
	@if [ -d monitoring_reports ]; then \
		echo "  ✅ monitoring_reports/ exists"; \
		echo "  📊 Reports: $$(ls monitoring_reports/ 2>/dev/null | wc -l) files"; \
	else \
		echo "  ❌ monitoring_reports/ not found"; \
	fi
	@echo ""
	@echo "⚙️ Configuration:"
	@if [ -f monitoring_config.json ]; then \
		echo "  ✅ monitoring_config.json exists"; \
	else \
		echo "  ❌ monitoring_config.json not found"; \
	fi
	@echo ""
	@echo "🐳 Docker Services:"
	@docker-compose -f docker-compose.local.yml ps --services 2>/dev/null | head -5 | while read service; do echo "  • $$service"; done || echo "  ❌ Docker Compose not available"
	@echo ""
	@echo "💡 Quick Start:"
	@echo "  make monitor-performance-quick  # 5-minute performance check"
	@echo "  make monitor-dashboard          # Interactive dashboard"
	@echo "  make monitor-health-check       # Comprehensive health check"

# =============================================================================
# POSTGRESQL OPTIMIZATION TARGETS
# =============================================================================

postgres-optimize: ## Maintenance - Optimize PostgreSQL configuration for development
	@echo "🐘 Optimizing PostgreSQL configuration for development..."
	@echo "Checking current PostgreSQL configuration..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/validate-postgresql-optimization.py; \
	else \
		echo "❌ Python3 not available for PostgreSQL optimization validation"; \
		exit 1; \
	fi

postgres-test-performance: ## Test - Test PostgreSQL performance with current configuration
	@echo "🐘 Testing PostgreSQL performance..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/test-postgresql-performance.py; \
	else \
		echo "❌ Python3 not available for PostgreSQL performance testing"; \
		exit 1; \
	fi

postgres-validate-config: ## Maintenance - Validate PostgreSQL configuration settings
	@echo "🐘 Validating PostgreSQL configuration..."
	@echo "Checking if PostgreSQL is running..."
	@docker-compose -f docker-compose.local.yml ps postgres | grep -q "Up" || { \
		echo "❌ PostgreSQL is not running. Start it with: make dev-local"; \
		exit 1; \
	}
	@echo "✅ PostgreSQL is running"
	@echo "Connecting to PostgreSQL to check configuration..."
	@docker-compose -f docker-compose.local.yml exec postgres psql -U ml_user -d multimodal_librarian -c "\
		SELECT name, setting, unit, short_desc FROM pg_settings \
		WHERE name IN ('shared_buffers', 'work_mem', 'maintenance_work_mem', 'effective_cache_size', \
		               'checkpoint_completion_target', 'wal_buffers', 'max_connections', 'random_page_cost', \
		               'max_parallel_workers_per_gather', 'checkpoint_timeout', 'max_wal_size', 'min_wal_size') \
		ORDER BY name;" || { \
		echo "❌ Failed to connect to PostgreSQL"; \
		exit 1; \
	}

postgres-performance-stats: ## Maintenance - Show PostgreSQL performance statistics
	@echo "🐘 PostgreSQL Performance Statistics"
	@echo "===================================="
	@docker-compose -f docker-compose.local.yml exec postgres psql -U ml_user -d multimodal_librarian -c "\
		SELECT * FROM get_performance_stats();" 2>/dev/null || { \
		echo "❌ Performance functions not available. Run: make postgres-setup-monitoring"; \
		exit 1; \
	}

postgres-health-check: ## Maintenance - Run PostgreSQL health check
	@echo "🐘 PostgreSQL Health Check"
	@echo "=========================="
	@docker-compose -f docker-compose.local.yml exec postgres psql -U ml_user -d multimodal_librarian -c "\
		SELECT * FROM monitoring.health_check();" 2>/dev/null || { \
		echo "❌ Monitoring functions not available. Run: make postgres-setup-monitoring"; \
		exit 1; \
	}

postgres-performance-summary: ## Maintenance - Show PostgreSQL performance summary
	@echo "🐘 PostgreSQL Performance Summary"
	@echo "================================="
	@docker-compose -f docker-compose.local.yml exec postgres psql -U ml_user -d multimodal_librarian -c "\
		SELECT * FROM monitoring.get_performance_summary();" 2>/dev/null || { \
		echo "❌ Monitoring functions not available. Run: make postgres-setup-monitoring"; \
		exit 1; \
	}

postgres-analyze-tables: ## Maintenance - Analyze all PostgreSQL tables for better query planning
	@echo "🐘 Analyzing PostgreSQL tables..."
	@docker-compose -f docker-compose.local.yml exec postgres psql -U ml_user -d multimodal_librarian -c "\
		SELECT analyze_all_tables();" 2>/dev/null || { \
		echo "❌ Analyze function not available"; \
		exit 1; \
	}

postgres-vacuum-tables: ## Maintenance - Vacuum and analyze all PostgreSQL tables
	@echo "🐘 Vacuuming PostgreSQL tables..."
	@docker-compose -f docker-compose.local.yml exec postgres psql -U ml_user -d multimodal_librarian -c "\
		SELECT vacuum_all_tables();" 2>/dev/null || { \
		echo "❌ Vacuum function not available"; \
		exit 1; \
	}

postgres-setup-monitoring: ## Development - Set up PostgreSQL performance monitoring functions
	@echo "🐘 Setting up PostgreSQL performance monitoring..."
	@echo "Checking if PostgreSQL is running..."
	@docker-compose -f docker-compose.local.yml ps postgres | grep -q "Up" || { \
		echo "❌ PostgreSQL is not running. Start it with: make dev-local"; \
		exit 1; \
	}
	@echo "✅ PostgreSQL is running"
	@echo "Installing pg_stat_statements extension..."
	@docker-compose -f docker-compose.local.yml exec postgres psql -U ml_user -d multimodal_librarian -c "\
		CREATE EXTENSION IF NOT EXISTS pg_stat_statements;" 2>/dev/null || true
	@echo "✅ Performance monitoring setup complete"
	@echo ""
	@echo "Available PostgreSQL optimization commands:"
	@echo "  make postgres-validate-config     # Check configuration settings"
	@echo "  make postgres-performance-stats   # Show performance statistics"
	@echo "  make postgres-health-check        # Run health check"
	@echo "  make postgres-performance-summary # Show performance summary"
	@echo "  make postgres-analyze-tables      # Analyze tables for better performance"
	@echo "  make postgres-vacuum-tables       # Vacuum and analyze tables"

postgres-memory-usage: ## Maintenance - Show PostgreSQL memory usage
	@echo "🐘 PostgreSQL Memory Usage"
	@echo "=========================="
	@echo "Container memory limits:"
	@docker-compose -f docker-compose.local.yml config | grep -A 10 -B 5 "postgres:" | grep -E "(memory|cpus):" || echo "No resource limits configured"
	@echo ""
	@echo "Current memory usage:"
	@docker stats --no-stream --format "table {{.Container}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.CPUPerc}}" | grep postgres || echo "PostgreSQL container not found"

postgres-connections: ## Maintenance - Show PostgreSQL connection information
	@echo "🐘 PostgreSQL Connections"
	@echo "========================="
	@docker-compose -f docker-compose.local.yml exec postgres psql -U ml_user -d multimodal_librarian -c "\
		SELECT \
			count(*) as total_connections, \
			count(*) FILTER (WHERE state = 'active') as active_connections, \
			count(*) FILTER (WHERE state = 'idle') as idle_connections, \
			current_setting('max_connections') as max_connections \
		FROM pg_stat_activity;" 2>/dev/null || { \
		echo "❌ Failed to get connection information"; \
		exit 1; \
	}

postgres-slow-queries: ## Maintenance - Show slow PostgreSQL queries (requires pg_stat_statements)
	@echo "🐘 PostgreSQL Slow Queries"
	@echo "=========================="
	@docker-compose -f docker-compose.local.yml exec postgres psql -U ml_user -d multimodal_librarian -c "\
		SELECT * FROM get_slow_queries(5);" 2>/dev/null || { \
		echo "❌ pg_stat_statements not available. Run: make postgres-setup-monitoring"; \
		exit 1; \
	}

postgres-optimization-help: ## Help - Show PostgreSQL optimization help
	@echo "🐘 PostgreSQL Optimization Help"
	@echo "==============================="
	@echo ""
	@echo "Performance Requirements (NFR-1):"
	@echo "  • Memory usage < 8GB total for all services (PostgreSQL target: ~1GB)"
	@echo "  • Query performance within 20% of AWS setup"
	@echo "  • Local setup startup time < 2 minutes"
	@echo "  • Reasonable CPU usage on development machines"
	@echo ""
	@echo "Current Optimizations Applied:"
	@echo "  • shared_buffers: 256MB (main buffer pool)"
	@echo "  • work_mem: 8MB (per-operation memory for sorts/joins)"
	@echo "  • maintenance_work_mem: 128MB (VACUUM, CREATE INDEX operations)"
	@echo "  • effective_cache_size: 1GB (OS cache estimate)"
	@echo "  • random_page_cost: 2.0 (optimized for SSD storage)"
	@echo "  • max_parallel_workers_per_gather: 2 (parallel query execution)"
	@echo "  • checkpoint_timeout: 10min (longer intervals for development)"
	@echo "  • wal_buffers: 32MB (increased WAL buffer size)"
	@echo ""
	@echo "Available Commands:"
	@echo "  make postgres-optimize            # Run full optimization validation"
	@echo "  make postgres-test-performance    # Test current performance"
	@echo "  make postgres-validate-config     # Check configuration settings"
	@echo "  make postgres-performance-stats   # Show performance statistics"
	@echo "  make postgres-health-check        # Run health check"
	@echo "  make postgres-performance-summary # Show performance summary"
	@echo "  make postgres-analyze-tables      # Analyze tables for better performance"
	@echo "  make postgres-vacuum-tables       # Vacuum and analyze tables"
	@echo "  make postgres-memory-usage        # Show memory usage"
	@echo "  make postgres-connections         # Show connection information"
	@echo "  make postgres-slow-queries        # Show slow queries"
	@echo ""
	@echo "Troubleshooting:"
	@echo "  • If performance functions are missing, run: make postgres-setup-monitoring"
	@echo "  • If PostgreSQL is not running, run: make dev-local"
	@echo "  • For detailed validation, run: python3 scripts/validate-postgresql-optimization.py"

# =============================================================================
# RESOURCE MANAGEMENT TARGETS
# =============================================================================

resource-configure: ## Resource - Configure Docker resource limits based on system
	@echo "⚙️ Configuring Docker resource limits..."
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import psutil, yaml" >/dev/null 2>&1; then \
		python3 scripts/configure-resource-limits.py --profile auto --output docker-compose.local.yml; \
	else \
		echo "❌ Resource configuration requires: pip install psutil pyyaml"; \
		exit 1; \
	fi

resource-configure-minimal: ## Resource - Configure minimal resource limits (8GB RAM)
	@echo "⚙️ Configuring minimal resource limits..."
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import psutil, yaml" >/dev/null 2>&1; then \
		python3 scripts/configure-resource-limits.py --profile minimal --output docker-compose.local.yml; \
	else \
		echo "❌ Resource configuration requires: pip install psutil pyyaml"; \
		exit 1; \
	fi

resource-configure-standard: ## Resource - Configure standard resource limits (16GB RAM)
	@echo "⚙️ Configuring standard resource limits..."
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import psutil, yaml" >/dev/null 2>&1; then \
		python3 scripts/configure-resource-limits.py --profile standard --output docker-compose.local.yml; \
	else \
		echo "❌ Resource configuration requires: pip install psutil pyyaml"; \
		exit 1; \
	fi

resource-configure-optimal: ## Resource - Configure optimal resource limits (32GB RAM)
	@echo "⚙️ Configuring optimal resource limits..."
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import psutil, yaml" >/dev/null 2>&1; then \
		python3 scripts/configure-resource-limits.py --profile optimal --output docker-compose.local.yml; \
	else \
		echo "❌ Resource configuration requires: pip install psutil pyyaml"; \
		exit 1; \
	fi

resource-configure-dry-run: ## Resource - Show resource configuration without applying
	@echo "👀 Showing resource configuration (dry run)..."
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import psutil, yaml" >/dev/null 2>&1; then \
		python3 scripts/configure-resource-limits.py --profile auto --dry-run; \
	else \
		echo "❌ Resource configuration requires: pip install psutil pyyaml"; \
		exit 1; \
	fi

resource-validate: ## Resource - Validate current Docker resource limits
	@echo "🔍 Validating Docker resource limits..."
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import docker, yaml" >/dev/null 2>&1; then \
		python3 scripts/validate-resource-limits.py --config docker-compose.local.yml --test-type basic; \
	else \
		echo "❌ Resource validation requires: pip install docker pyyaml"; \
		exit 1; \
	fi

resource-validate-stress: ## Resource - Run stress tests on resource limits
	@echo "🔥 Running stress tests on resource limits..."
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import docker, yaml" >/dev/null 2>&1; then \
		python3 scripts/validate-resource-limits.py --config docker-compose.local.yml --test-type stress --duration 10; \
	else \
		echo "❌ Resource validation requires: pip install docker pyyaml"; \
		exit 1; \
	fi

resource-validate-limits: ## Resource - Test resource limit enforcement
	@echo "⚖️ Testing resource limit enforcement..."
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import docker, yaml" >/dev/null 2>&1; then \
		python3 scripts/validate-resource-limits.py --config docker-compose.local.yml --test-type limits --duration 5; \
	else \
		echo "❌ Resource validation requires: pip install docker pyyaml"; \
		exit 1; \
	fi

resource-validate-all: ## Resource - Run comprehensive resource validation
	@echo "🧪 Running comprehensive resource validation..."
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import docker, yaml" >/dev/null 2>&1; then \
		python3 scripts/validate-resource-limits.py --config docker-compose.local.yml --test-type all --duration 15; \
	else \
		echo "❌ Resource validation requires: pip install docker pyyaml"; \
		exit 1; \
	fi

resource-monitor: ## Resource - Monitor resource usage continuously
	@echo "📊 Starting resource usage monitoring..."
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import psutil, docker" >/dev/null 2>&1; then \
		python3 scripts/monitor-resource-usage.py --duration 15 --interval 5; \
	else \
		echo "❌ Resource monitoring requires: pip install psutil docker"; \
		exit 1; \
	fi

resource-monitor-short: ## Resource - Monitor resource usage for 5 minutes
	@echo "📊 Starting short resource usage monitoring..."
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import psutil, docker" >/dev/null 2>&1; then \
		python3 scripts/monitor-resource-usage.py --duration 5 --interval 2; \
	else \
		echo "❌ Resource monitoring requires: pip install psutil docker"; \
		exit 1; \
	fi

resource-monitor-long: ## Resource - Monitor resource usage for 30 minutes
	@echo "📊 Starting extended resource usage monitoring..."
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import psutil, docker" >/dev/null 2>&1; then \
		python3 scripts/monitor-resource-usage.py --duration 30 --interval 10; \
	else \
		echo "❌ Resource monitoring requires: pip install psutil docker"; \
		exit 1; \
	fi

resource-info: ## Resource - Show system resource information
	@echo "💻 System Resource Information:"
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import psutil" >/dev/null 2>&1; then \
		python3 scripts/configure-resource-limits.py --system-info; \
	else \
		echo "❌ System info requires: pip install psutil"; \
		echo "Basic system info:"; \
		echo "CPU Cores: $$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 'unknown')"; \
		echo "Memory: $$(free -h 2>/dev/null | grep '^Mem:' | awk '{print $$2}' || echo 'unknown')"; \
		echo "Disk: $$(df -h . 2>/dev/null | tail -1 | awk '{print $$2 " total, " $$4 " free"}' || echo 'unknown')"; \
	fi

resource-stats: ## Resource - Show current Docker container resource usage
	@echo "📈 Current Docker Container Resource Usage:"
	@docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.BlockIO}}" 2>/dev/null || echo "❌ No running containers found"

resource-limits-show: ## Resource - Show configured resource limits
	@echo "⚙️ Configured Resource Limits:"
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import yaml" >/dev/null 2>&1; then \
		python3 scripts/configure-resource-limits.py --validate --config docker-compose.local.yml; \
	else \
		echo "❌ Showing limits requires: pip install pyyaml"; \
		echo "Use: docker-compose -f docker-compose.local.yml config | grep -A 10 resources"; \
	fi

resource-optimize: ## Resource - Optimize resource allocation based on usage patterns
	@echo "🎯 Optimizing resource allocation..."
	@echo "📊 Analyzing current usage patterns..."
	@if command -v python3 >/dev/null 2>&1 && python3 -c "import psutil, docker" >/dev/null 2>&1; then \
		python3 scripts/monitor-resource-usage.py --duration 2 --interval 1 --output resource_analysis.json; \
		echo "⚙️ Generating optimized configuration..."; \
		python3 scripts/configure-resource-limits.py --profile auto --output docker-compose.local.yml; \
		echo "✅ Resource optimization complete!"; \
		echo "📋 Review changes and restart services: make down && make dev-local"; \
	else \
		echo "❌ Resource optimization requires: pip install psutil docker pyyaml"; \
		exit 1; \
	fi

resource-reset: ## Resource - Reset resource limits to defaults
	@echo "🔄 Resetting resource limits to defaults..."
	@if [ -f docker-compose.local.yml.backup.* ]; then \
		latest_backup=$$(ls -t docker-compose.local.yml.backup.* | head -1); \
		cp "$$latest_backup" docker-compose.local.yml; \
		echo "✅ Restored from backup: $$latest_backup"; \
	else \
		echo "❌ No backup found. Use 'make resource-configure' to reconfigure."; \
		exit 1; \
	fi

resource-backup: ## Resource - Backup current resource configuration
	@echo "💾 Backing up current resource configuration..."
	@cp docker-compose.local.yml "docker-compose.local.yml.backup.$$(date +%s)"
	@echo "✅ Configuration backed up"

resource-cleanup: ## Resource - Clean up resource monitoring files
	@echo "🧹 Cleaning up resource monitoring files..."
	@rm -f resource_usage_*.json
	@rm -f resource_validation_*.json
	@rm -f resource_analysis.json
	@echo "✅ Resource monitoring files cleaned up"

# =============================================================================
# DEBUG UTILITIES TARGETS
# =============================================================================

debug-status: ## Debug - Check overall system status
	@echo "🔍 Checking overall system status..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/local-debug-cli.py status; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-services: ## Debug - Check Docker services status
	@echo "🐳 Checking Docker services status..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/local-debug-cli.py services; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-databases: ## Debug - Check database connections
	@echo "🗄️ Checking database connections..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/local-debug-cli.py databases; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-health: ## Debug - Check application health endpoints
	@echo "🏥 Checking application health endpoints..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/local-debug-cli.py health; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-logs: ## Debug - Collect and analyze service logs (usage: make debug-logs SERVICE=postgres)
	@if [ -z "$(SERVICE)" ]; then \
		echo "🔍 Collecting logs from all services..."; \
		if command -v python3 >/dev/null 2>&1; then \
			python3 scripts/debug/local-debug-cli.py logs; \
		else \
			echo "❌ Python3 not available for debugging utilities"; \
			exit 1; \
		fi; \
	else \
		echo "🔍 Collecting logs from service: $(SERVICE)"; \
		if command -v python3 >/dev/null 2>&1; then \
			python3 scripts/debug/local-debug-cli.py logs --service $(SERVICE) --lines 200; \
		else \
			echo "❌ Python3 not available for debugging utilities"; \
			exit 1; \
		fi; \
	fi

debug-monitor: ## Debug - Monitor system resources (usage: make debug-monitor DURATION=120)
	@echo "📊 Starting system resource monitoring..."
	@if [ -z "$(DURATION)" ]; then \
		duration=60; \
	else \
		duration=$(DURATION); \
	fi; \
	if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/local-debug-cli.py monitor --duration $$duration; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-network: ## Debug - Diagnose network connectivity
	@echo "🌐 Diagnosing network connectivity..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/local-debug-cli.py network; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-report: ## Debug - Generate comprehensive debug report
	@echo "📋 Generating comprehensive debug report..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/local-debug-cli.py report; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-restart: ## Debug - Restart a service (usage: make debug-restart SERVICE=postgres)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Please specify service: make debug-restart SERVICE=postgres"; \
		echo "Available services: multimodal-librarian, postgres, neo4j, milvus, redis, etcd, minio"; \
		exit 1; \
	fi
	@echo "🔄 Restarting service: $(SERVICE)"
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/local-debug-cli.py restart $(SERVICE); \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-cleanup: ## Debug - Clean up Docker resources
	@echo "🧹 Cleaning up Docker resources..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/local-debug-cli.py cleanup; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

# Database-specific debugging
debug-db-diagnostics: ## Debug - Run comprehensive database diagnostics
	@echo "🗄️ Running comprehensive database diagnostics..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/database-debug-tool.py diagnostics; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-db-performance: ## Debug - Test database performance (usage: make debug-db-performance DURATION=60)
	@echo "🗄️ Testing database performance..."
	@if [ -z "$(DURATION)" ]; then \
		duration=60; \
	else \
		duration=$(DURATION); \
	fi; \
	if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/database-debug-tool.py performance --duration $$duration; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-db-postgres: ## Debug - Test PostgreSQL specifically
	@echo "🐘 Testing PostgreSQL database..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/database-debug-tool.py postgresql; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-db-neo4j: ## Debug - Test Neo4j specifically
	@echo "🕸️ Testing Neo4j database..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/database-debug-tool.py neo4j; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-db-milvus: ## Debug - Test Milvus specifically
	@echo "🔍 Testing Milvus database..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/database-debug-tool.py milvus; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

# Container-specific debugging
debug-container-inspect: ## Debug - Inspect containers (usage: make debug-container-inspect CONTAINER=postgres)
	@if [ -z "$(CONTAINER)" ]; then \
		echo "🐳 Inspecting all containers..."; \
		if command -v python3 >/dev/null 2>&1; then \
			python3 scripts/debug/container-inspector.py inspect; \
		else \
			echo "❌ Python3 not available for debugging utilities"; \
			exit 1; \
		fi; \
	else \
		echo "🐳 Inspecting container: $(CONTAINER)"; \
		if command -v python3 >/dev/null 2>&1; then \
			python3 scripts/debug/container-inspector.py inspect --container $(CONTAINER); \
		else \
			echo "❌ Python3 not available for debugging utilities"; \
			exit 1; \
		fi; \
	fi

debug-container-monitor: ## Debug - Monitor container resources (usage: make debug-container-monitor CONTAINER=postgres DURATION=300)
	@if [ -z "$(CONTAINER)" ]; then \
		echo "Please specify container: make debug-container-monitor CONTAINER=postgres"; \
		echo "Available containers: multimodal-librarian, postgres, neo4j, milvus, redis, etcd, minio"; \
		exit 1; \
	fi
	@if [ -z "$(DURATION)" ]; then \
		duration=300; \
	else \
		duration=$(DURATION); \
	fi
	@echo "📊 Monitoring container $(CONTAINER) for $$duration seconds..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/container-inspector.py monitor $(CONTAINER) --duration $$duration; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-container-logs: ## Debug - Get container logs (usage: make debug-container-logs CONTAINER=postgres LINES=500)
	@if [ -z "$(CONTAINER)" ]; then \
		echo "Please specify container: make debug-container-logs CONTAINER=postgres"; \
		echo "Available containers: multimodal-librarian, postgres, neo4j, milvus, redis, etcd, minio"; \
		exit 1; \
	fi
	@if [ -z "$(LINES)" ]; then \
		lines=200; \
	else \
		lines=$(LINES); \
	fi
	@echo "📜 Getting logs from container $(CONTAINER) (last $$lines lines)..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/container-inspector.py logs $(CONTAINER) --lines $$lines; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-container-logs-follow: ## Debug - Follow container logs in real-time (usage: make debug-container-logs-follow CONTAINER=postgres)
	@if [ -z "$(CONTAINER)" ]; then \
		echo "Please specify container: make debug-container-logs-follow CONTAINER=postgres"; \
		echo "Available containers: multimodal-librarian, postgres, neo4j, milvus, redis, etcd, minio"; \
		exit 1; \
	fi
	@echo "📜 Following logs from container $(CONTAINER) (press Ctrl+C to stop)..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/container-inspector.py logs $(CONTAINER) --follow; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-container-exec: ## Debug - Execute command in container (usage: make debug-container-exec CONTAINER=postgres COMMAND="pg_isready -U ml_user")
	@if [ -z "$(CONTAINER)" ]; then \
		echo "Please specify container: make debug-container-exec CONTAINER=postgres COMMAND=\"pg_isready -U ml_user\""; \
		echo "Available containers: multimodal-librarian, postgres, neo4j, milvus, redis, etcd, minio"; \
		exit 1; \
	fi
	@if [ -z "$(COMMAND)" ]; then \
		echo "Please specify command: make debug-container-exec CONTAINER=postgres COMMAND=\"pg_isready -U ml_user\""; \
		exit 1; \
	fi
	@echo "⚡ Executing command in container $(CONTAINER): $(COMMAND)"
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/container-inspector.py exec $(CONTAINER) "$(COMMAND)"; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

# Log analysis debugging
debug-logs-analyze: ## Debug - Analyze all service logs for patterns and issues
	@echo "📊 Analyzing service logs for patterns and issues..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/log-analyzer.py analyze; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-logs-analyze-service: ## Debug - Analyze specific service logs (usage: make debug-logs-analyze-service SERVICE=postgres LINES=2000)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Please specify service: make debug-logs-analyze-service SERVICE=postgres"; \
		echo "Available services: multimodal-librarian, postgres, neo4j, milvus, redis, etcd, minio"; \
		exit 1; \
	fi
	@if [ -z "$(LINES)" ]; then \
		lines=1000; \
	else \
		lines=$(LINES); \
	fi
	@echo "📊 Analyzing logs from service $(SERVICE) (last $$lines lines)..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/log-analyzer.py analyze --service $(SERVICE) --lines $$lines; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-logs-search: ## Debug - Search for patterns in logs (usage: make debug-logs-search PATTERN="ERROR")
	@if [ -z "$(PATTERN)" ]; then \
		echo "Please specify search pattern: make debug-logs-search PATTERN=\"ERROR\""; \
		echo "Examples: PATTERN=\"connection.*failed\", PATTERN=\"timeout\", PATTERN=\"slow\""; \
		exit 1; \
	fi
	@echo "🔍 Searching for pattern in logs: $(PATTERN)"
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/log-analyzer.py search "$(PATTERN)"; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-logs-search-services: ## Debug - Search for patterns in specific services (usage: make debug-logs-search-services PATTERN="ERROR" SERVICES="postgres neo4j")
	@if [ -z "$(PATTERN)" ]; then \
		echo "Please specify search pattern: make debug-logs-search-services PATTERN=\"ERROR\" SERVICES=\"postgres neo4j\""; \
		exit 1; \
	fi
	@if [ -z "$(SERVICES)" ]; then \
		echo "Please specify services: make debug-logs-search-services PATTERN=\"ERROR\" SERVICES=\"postgres neo4j\""; \
		exit 1; \
	fi
	@echo "🔍 Searching for pattern \"$(PATTERN)\" in services: $(SERVICES)"
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/log-analyzer.py search "$(PATTERN)" --services $(SERVICES); \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-logs-summary: ## Debug - Generate log summary (usage: make debug-logs-summary HOURS=2)
	@if [ -z "$(HOURS)" ]; then \
		hours=1; \
	else \
		hours=$(HOURS); \
	fi
	@echo "📋 Generating log summary for last $$hours hours..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/log-analyzer.py summary --hours $$hours; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

# Network debugging
debug-network-ports: ## Debug - Check all service ports
	@echo "🔌 Checking all service ports..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/network-diagnostics.py ports; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-network-health: ## Debug - Check health endpoints
	@echo "🏥 Checking health endpoints..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/network-diagnostics.py health; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-network-docker: ## Debug - Check Docker networks
	@echo "🐳 Checking Docker networks..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/network-diagnostics.py networks; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-network-connectivity: ## Debug - Test inter-service connectivity
	@echo "🔗 Testing inter-service connectivity..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/network-diagnostics.py connectivity; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-network-dns: ## Debug - Test DNS resolution
	@echo "🌐 Testing DNS resolution..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/network-diagnostics.py dns; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-network-trace: ## Debug - Run network trace (usage: make debug-network-trace HOST=localhost PORT=5432)
	@if [ -z "$(HOST)" ] || [ -z "$(PORT)" ]; then \
		echo "Please specify host and port: make debug-network-trace HOST=localhost PORT=5432"; \
		exit 1; \
	fi
	@echo "🔍 Running network trace to $(HOST):$(PORT)..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/network-diagnostics.py trace $(HOST) $(PORT); \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-network-report: ## Debug - Generate comprehensive network report
	@echo "📋 Generating comprehensive network report..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/network-diagnostics.py report; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

# Debug manager (unified debugging)
debug-manager: ## Debug - Launch unified debugging manager
	@echo "🎛️ Launching unified debugging manager..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/debug-manager.py; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-manager-quick: ## Debug - Run quick health check via debug manager
	@echo "⚡ Running quick health check..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/debug-manager.py --quick-check; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-manager-comprehensive: ## Debug - Run comprehensive diagnostics via debug manager
	@echo "🔬 Running comprehensive diagnostics..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/debug-manager.py --comprehensive; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-manager-monitor: ## Debug - Start system monitoring via debug manager (usage: make debug-manager-monitor DURATION=300)
	@if [ -z "$(DURATION)" ]; then \
		duration=300; \
	else \
		duration=$(DURATION); \
	fi
	@echo "📊 Starting system monitoring for $$duration seconds..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/debug-manager.py --monitor --duration $$duration; \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

debug-manager-troubleshoot: ## Debug - Run targeted troubleshooting (usage: make debug-manager-troubleshoot ISSUE=database)
	@if [ -z "$(ISSUE)" ]; then \
		echo "Please specify issue type: make debug-manager-troubleshoot ISSUE=database"; \
		echo "Available issues: database, network, performance, containers, application"; \
		exit 1; \
	fi
	@echo "🔧 Running targeted troubleshooting for: $(ISSUE)"
	@if command -v python3 >/dev/null 2>&1; then \
		python3 scripts/debug/debug-manager.py --troubleshoot $(ISSUE); \
	else \
		echo "❌ Python3 not available for debugging utilities"; \
		exit 1; \
	fi

# Debug help and information
debug-help: ## Debug - Show comprehensive debugging help
	@echo ""
	@echo "🔧 DEBUGGING UTILITIES HELP"
	@echo "=========================="
	@echo ""
	@echo "📋 Quick Diagnostics:"
	@echo "  debug-status              - Check overall system status"
	@echo "  debug-services            - Check Docker services status"
	@echo "  debug-databases           - Check database connections"
	@echo "  debug-health              - Check application health endpoints"
	@echo "  debug-network             - Diagnose network connectivity"
	@echo "  debug-report              - Generate comprehensive debug report"
	@echo ""
	@echo "🗄️ Database Debugging:"
	@echo "  debug-db-diagnostics      - Run comprehensive database diagnostics"
	@echo "  debug-db-performance      - Test database performance"
	@echo "  debug-db-postgres         - Test PostgreSQL specifically"
	@echo "  debug-db-neo4j            - Test Neo4j specifically"
	@echo "  debug-db-milvus           - Test Milvus specifically"
	@echo ""
	@echo "🐳 Container Debugging:"
	@echo "  debug-container-inspect   - Inspect containers"
	@echo "  debug-container-monitor   - Monitor container resources"
	@echo "  debug-container-logs      - Get container logs"
	@echo "  debug-container-logs-follow - Follow container logs in real-time"
	@echo "  debug-container-exec      - Execute command in container"
	@echo ""
	@echo "📜 Log Analysis:"
	@echo "  debug-logs                - Collect and analyze service logs"
	@echo "  debug-logs-analyze        - Analyze all service logs for patterns"
	@echo "  debug-logs-analyze-service - Analyze specific service logs"
	@echo "  debug-logs-search         - Search for patterns in logs"
	@echo "  debug-logs-search-services - Search in specific services"
	@echo "  debug-logs-summary        - Generate log summary"
	@echo ""
	@echo "🌐 Network Debugging:"
	@echo "  debug-network-ports       - Check all service ports"
	@echo "  debug-network-health      - Check health endpoints"
	@echo "  debug-network-docker      - Check Docker networks"
	@echo "  debug-network-connectivity - Test inter-service connectivity"
	@echo "  debug-network-dns         - Test DNS resolution"
	@echo "  debug-network-trace       - Run network trace"
	@echo "  debug-network-report      - Generate network report"
	@echo ""
	@echo "📊 System Monitoring:"
	@echo "  debug-monitor             - Monitor system resources"
	@echo "  debug-manager-monitor     - Advanced system monitoring"
	@echo ""
	@echo "🎛️ Unified Debugging:"
	@echo "  debug-manager             - Launch unified debugging manager"
	@echo "  debug-manager-quick       - Quick health check"
	@echo "  debug-manager-comprehensive - Comprehensive diagnostics"
	@echo "  debug-manager-troubleshoot - Targeted troubleshooting"
	@echo ""
	@echo "🔧 Service Management:"
	@echo "  debug-restart             - Restart a service"
	@echo "  debug-cleanup             - Clean up Docker resources"
	@echo ""
	@echo "💡 Common Usage Examples:"
	@echo "  make debug-status                                    # Quick system check"
	@echo "  make debug-logs SERVICE=postgres                     # Check PostgreSQL logs"
	@echo "  make debug-container-monitor CONTAINER=postgres DURATION=300  # Monitor PostgreSQL"
	@echo "  make debug-logs-search PATTERN=\"ERROR\"               # Search for errors"
	@echo "  make debug-network-trace HOST=localhost PORT=5432    # Test PostgreSQL connectivity"
	@echo "  make debug-manager-troubleshoot ISSUE=database      # Database troubleshooting"
	@echo ""
	@echo "📚 Documentation: scripts/debug/README.md"

# =============================================================================
# AUTOMATED RESOURCE CLEANUP TARGETS
# =============================================================================

cleanup-local: ## Resource - Automated cleanup of local development resources
	@echo "🧹 Running automated cleanup of local development resources..."
	@python scripts/cleanup-local-resources.py

cleanup-local-dry-run: ## Resource - Show what would be cleaned without doing it
	@echo "🔍 Showing what would be cleaned (dry run)..."
	@python scripts/cleanup-local-resources.py --dry-run

cleanup-local-force: ## Resource - Force cleanup without confirmation prompts
	@echo "🔨 Running forced cleanup without prompts..."
	@python scripts/cleanup-local-resources.py --force

cleanup-local-data: ## Resource - Cleanup including database volumes (DESTRUCTIVE)
	@echo "⚠️  Running cleanup including database volumes (DESTRUCTIVE)..."
	@python scripts/cleanup-local-resources.py --include-data

cleanup-local-containers: ## Resource - Cleanup Docker containers only
	@echo "🐳 Cleaning up Docker containers only..."
	@python scripts/cleanup-local-resources.py --containers-only

cleanup-local-files: ## Resource - Cleanup application files only
	@echo "📁 Cleaning up application files only..."
	@python scripts/cleanup-local-resources.py --files-only

cleanup-report: ## Resource - Generate resource usage report
	@echo "📊 Generating resource usage report..."
	@python scripts/cleanup-local-resources.py --report-only

cleanup-scheduled-start: ## Resource - Start scheduled cleanup service
	@echo "⏰ Starting scheduled cleanup service..."
	@python scripts/scheduled-cleanup.py --daemon

cleanup-scheduled-test: ## Resource - Test scheduled cleanup service
	@echo "🧪 Testing scheduled cleanup service..."
	@python scripts/scheduled-cleanup.py --test

cleanup-scheduled-config: ## Resource - Show scheduled cleanup configuration
	@echo "⚙️ Scheduled cleanup configuration:"
	@cat config/cleanup-config.json | python -m json.tool

cleanup-emergency: ## Resource - Emergency cleanup when disk usage is high
	@echo "🚨 Running emergency cleanup..."
	@python scripts/cleanup-local-resources.py --force --files-only
	@python scripts/cleanup-local-resources.py --force --containers-only

resource-help: ## Resource - Show detailed resource management help
	@echo ""
	@echo "🔧 RESOURCE MANAGEMENT HELP"
	@echo "=========================="
	@echo ""
	@echo "📋 Configuration Commands:"
	@echo "  resource-configure        - Auto-configure based on system specs"
	@echo "  resource-configure-minimal - Configure for 8GB RAM systems"
	@echo "  resource-configure-standard- Configure for 16GB RAM systems"
	@echo "  resource-configure-optimal - Configure for 32GB+ RAM systems"
	@echo "  resource-configure-dry-run - Preview configuration changes"
	@echo ""
	@echo "🔍 Validation Commands:"
	@echo "  resource-validate         - Basic resource limit validation"
	@echo "  resource-validate-stress  - Stress test resource limits"
	@echo "  resource-validate-limits  - Test limit enforcement"
	@echo "  resource-validate-all     - Comprehensive validation"
	@echo ""
	@echo "📊 Monitoring Commands:"
	@echo "  resource-monitor          - Monitor usage for 15 minutes"
	@echo "  resource-monitor-short    - Monitor usage for 5 minutes"
	@echo "  resource-monitor-long     - Monitor usage for 30 minutes"
	@echo "  resource-stats            - Show current container stats"
	@echo ""
	@echo "⚙️ Management Commands:"
	@echo "  resource-info             - Show system resource information"
	@echo "  resource-limits-show      - Show configured limits"
	@echo "  resource-optimize         - Optimize based on usage patterns"
	@echo "  resource-reset            - Reset to previous configuration"
	@echo "  resource-backup           - Backup current configuration"
	@echo "  resource-cleanup          - Clean up monitoring files"
	@echo ""
	@echo "🚀 Quick Start:"
	@echo "  1. make resource-info                    # Check system specs"
	@echo "  2. make resource-configure               # Configure limits"
	@echo "  3. make down && make dev-local           # Restart with new limits"
	@echo "  4. make resource-validate                # Validate configuration"
	@echo "  5. make resource-monitor-short           # Monitor usage"
	@echo ""
	@echo "📚 Documentation: docs/configuration/docker-resource-limits.md"

# Resource management with development workflow integration
dev-with-resources: resource-configure dev-local ## Development - Start with optimized resource limits
	@echo "✅ Development environment started with optimized resource limits"

dev-monitor-resources: ## Development - Start development with resource monitoring
	@echo "🚀 Starting development with resource monitoring..."
	@$(MAKE) dev-local
	@echo "📊 Starting resource monitoring in background..."
	@nohup python3 scripts/monitor-resource-usage.py --duration 60 --interval 10 --output dev_resource_usage.json > resource_monitor.log 2>&1 &
	@echo "✅ Development environment running with resource monitoring"
	@echo "📋 Monitor logs: tail -f resource_monitor.log"
	@echo "📊 Resource stats: make resource-stats"

dev-stop-monitoring: ## Development - Stop resource monitoring
	@echo "🛑 Stopping resource monitoring..."
	@pkill -f "monitor-resource-usage.py" || echo "No monitoring process found"
	@echo "✅ Resource monitoring stopped"
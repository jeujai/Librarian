# Design Document: Health Check Database Decoupling

## Overview

This design addresses the historical architectural issue where ALB health check endpoints were tightly coupled to PostgreSQL database connectivity, creating a circular dependency that caused deployment failures. The solution decouples health check endpoints from database connectivity while maintaining comprehensive system health monitoring through separate, purpose-specific endpoints.

### Historical Context

**The Problem:**
- ALB health checks called `/api/health/simple` and `/api/health/minimal` endpoints
- These endpoints checked database connectivity as part of their health assessment
- Database connectivity required environment variables prefixed with `POSTGRES_*` (e.g., `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`)
- If the prefix was missing or incorrect, database connection would fail
- Failed database connection caused health checks to fail
- Failed health checks caused ALB to mark targets as unhealthy
- Unhealthy targets prevented successful deployment

**The Circular Dependency:**
```
Deployment → Task Start → Health Check → Database Check → Environment Variables
     ↑                                                              ↓
     └──────────────── Deployment Fails ←──── Health Check Fails ←─┘
```

**The Solution:**
- Decouple health check endpoints from database connectivity
- Health checks now verify only that the application process is running and responsive
- Separate endpoints provide database connectivity validation when needed
- This breaks the circular dependency and enables reliable deployments

## Architecture

### Endpoint Hierarchy

The system now implements a three-tier health check architecture:

1. **Basic Health Endpoints** (ALB-facing, no dependencies)
   - `/api/health/minimal` - Absolute minimal check (process alive)
   - `/api/health/simple` - Basic application readiness (no external dependencies)

2. **Component Health Endpoints** (internal monitoring)
   - `/api/health/database` - Database connectivity check
   - `/api/health/storage` - S3/storage connectivity check
   - `/api/health/cache` - Cache service connectivity check

3. **Comprehensive Health Endpoint** (full system validation)
   - `/api/health/full` - Aggregates all component health checks

### Request Flow

```
ALB Health Check Request
    ↓
/api/health/minimal or /api/health/simple
    ↓
Check: Is process running?
Check: Can process handle HTTP requests?
    ↓
Return 200 OK (no database check)
```

Separate monitoring flow:
```
Monitoring System Request
    ↓
/api/health/full
    ↓
Check: Process health
Check: Database connectivity
Check: Storage connectivity
Check: Cache connectivity
    ↓
Return detailed health status
```

## Components and Interfaces

### 1. Health Check Router (`src/multimodal_librarian/api/routers/health.py`)

**Purpose:** Provides all health check endpoints with appropriate dependency isolation.

**Endpoints:**

```python
@router.get("/health/minimal")
async def health_minimal() -> HealthResponse:
    """
    Minimal health check for ALB.
    Returns 200 if process is alive and can handle requests.
    NO external dependencies checked.
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        checks={"process": "ok"}
    )

@router.get("/health/simple")
async def health_simple() -> HealthResponse:
    """
    Simple health check for ALB.
    Verifies basic application readiness without external dependencies.
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        checks={
            "process": "ok",
            "api": "ready"
        }
    )

@router.get("/health/database")
async def health_database(db: Database = Depends(get_database)) -> HealthResponse:
    """
    Database connectivity check.
    Used by monitoring systems, NOT by ALB.
    """
    try:
        await db.execute("SELECT 1")
        return HealthResponse(
            status="healthy",
            timestamp=datetime.utcnow(),
            checks={"database": "connected"}
        )
    except Exception as e:
        return HealthResponse(
            status="unhealthy",
            timestamp=datetime.utcnow(),
            checks={"database": f"error: {str(e)}"}
        )

@router.get("/health/full")
async def health_full(
    db: Database = Depends(get_database),
    storage: StorageService = Depends(get_storage)
) -> HealthResponse:
    """
    Comprehensive health check.
    Aggregates all component health checks.
    Used by monitoring systems, NOT by ALB.
    """
    checks = {}
    
    # Check database
    try:
        await db.execute("SELECT 1")
        checks["database"] = "connected"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
    
    # Check storage
    try:
        await storage.health_check()
        checks["storage"] = "connected"
    except Exception as e:
        checks["storage"] = f"error: {str(e)}"
    
    # Determine overall status
    status = "healthy" if all("error" not in v for v in checks.values()) else "degraded"
    
    return HealthResponse(
        status=status,
        timestamp=datetime.utcnow(),
        checks=checks
    )
```

### 2. Health Response Model (`src/multimodal_librarian/api/models.py`)

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Dict, Literal

class HealthResponse(BaseModel):
    """Response model for health check endpoints."""
    status: Literal["healthy", "degraded", "unhealthy"]
    timestamp: datetime
    checks: Dict[str, str]
    response_time_ms: Optional[float] = None
```

### 3. Database Configuration Validator (`src/multimodal_librarian/validation/database_config_validator.py`)

**Purpose:** Validates environment variable configuration before deployment.

```python
class DatabaseConfigValidator:
    """Validates database configuration for deployment."""
    
    REQUIRED_POSTGRES_VARS = [
        "POSTGRES_HOST",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_PORT"
    ]
    
    def validate_environment_variables(self, env_vars: Dict[str, str]) -> ValidationResult:
        """
        Validates that all required POSTGRES_* variables are present and non-empty.
        
        Args:
            env_vars: Dictionary of environment variables
            
        Returns:
            ValidationResult with success status and any error messages
        """
        errors = []
        
        for var_name in self.REQUIRED_POSTGRES_VARS:
            if var_name not in env_vars:
                errors.append(f"Missing required environment variable: {var_name}")
            elif not env_vars[var_name].strip():
                errors.append(f"Environment variable {var_name} is empty")
        
        # Check for common mistakes (wrong prefix)
        wrong_prefix_vars = [
            key for key in env_vars.keys()
            if any(key.endswith(suffix) for suffix in ["_HOST", "_DB", "_USER", "_PASSWORD"])
            and not key.startswith("POSTGRES_")
        ]
        
        if wrong_prefix_vars:
            errors.append(
                f"Found database variables without POSTGRES_ prefix: {', '.join(wrong_prefix_vars)}. "
                f"Database connectivity requires POSTGRES_* prefix."
            )
        
        return ValidationResult(
            success=len(errors) == 0,
            errors=errors
        )
```

### 4. Health Check Monitor (`src/multimodal_librarian/monitoring/health_check_monitor.py`)

**Purpose:** Monitors health check endpoint performance and detects regressions.

```python
class HealthCheckMonitor:
    """Monitors health check endpoint performance."""
    
    MAX_RESPONSE_TIME_MS = 2000  # 2 seconds
    
    async def monitor_health_endpoint(self, endpoint: str) -> HealthCheckMetrics:
        """
        Monitors a health check endpoint for performance and dependency issues.
        
        Args:
            endpoint: The health check endpoint to monitor
            
        Returns:
            HealthCheckMetrics with performance data
        """
        start_time = time.time()
        
        try:
            response = await self.http_client.get(endpoint)
            response_time_ms = (time.time() - start_time) * 1000
            
            metrics = HealthCheckMetrics(
                endpoint=endpoint,
                response_time_ms=response_time_ms,
                status_code=response.status_code,
                success=response.status_code == 200,
                timestamp=datetime.utcnow()
            )
            
            # Alert if response time exceeds threshold
            if response_time_ms > self.MAX_RESPONSE_TIME_MS:
                await self.alert_service.send_alert(
                    severity="warning",
                    message=f"Health check endpoint {endpoint} exceeded response time threshold: "
                            f"{response_time_ms:.2f}ms > {self.MAX_RESPONSE_TIME_MS}ms"
                )
            
            return metrics
            
        except Exception as e:
            await self.alert_service.send_alert(
                severity="error",
                message=f"Health check endpoint {endpoint} failed: {str(e)}"
            )
            raise
```

### 5. Static Analysis Tool (`scripts/validate-health-check-independence.py`)

**Purpose:** Detects database imports in health check endpoint code during CI/CD.

```python
import ast
import sys
from pathlib import Path

class HealthCheckDependencyAnalyzer(ast.NodeVisitor):
    """Analyzes health check endpoints for database dependencies."""
    
    FORBIDDEN_IMPORTS = [
        "database",
        "db",
        "postgres",
        "sqlalchemy",
        "psycopg2"
    ]
    
    def __init__(self):
        self.violations = []
        self.in_health_minimal = False
        self.in_health_simple = False
    
    def visit_FunctionDef(self, node):
        """Track when we're inside health check functions."""
        if node.name in ["health_minimal", "health_simple"]:
            self.in_health_minimal = True
            self.generic_visit(node)
            self.in_health_minimal = False
        else:
            self.generic_visit(node)
    
    def visit_Import(self, node):
        """Check for forbidden imports in health check functions."""
        if self.in_health_minimal or self.in_health_simple:
            for alias in node.names:
                if any(forbidden in alias.name.lower() for forbidden in self.FORBIDDEN_IMPORTS):
                    self.violations.append(
                        f"Line {node.lineno}: Health check function imports database module: {alias.name}"
                    )
        self.generic_visit(node)
    
    def visit_Call(self, node):
        """Check for database-related function calls."""
        if self.in_health_minimal or self.in_health_simple:
            if isinstance(node.func, ast.Attribute):
                if any(forbidden in node.func.attr.lower() for forbidden in ["execute", "query", "fetch"]):
                    self.violations.append(
                        f"Line {node.lineno}: Health check function calls database method: {node.func.attr}"
                    )
        self.generic_visit(node)

def analyze_health_check_file(file_path: Path) -> List[str]:
    """Analyzes a health check file for database dependencies."""
    with open(file_path, 'r') as f:
        tree = ast.parse(f.read(), filename=str(file_path))
    
    analyzer = HealthCheckDependencyAnalyzer()
    analyzer.visit(tree)
    
    return analyzer.violations
```

## Data Models

### HealthResponse

```python
class HealthResponse(BaseModel):
    """Response model for all health check endpoints."""
    status: Literal["healthy", "degraded", "unhealthy"]
    timestamp: datetime
    checks: Dict[str, str]  # Component name -> status message
    response_time_ms: Optional[float] = None
```

### ValidationResult

```python
class ValidationResult(BaseModel):
    """Result of environment variable validation."""
    success: bool
    errors: List[str] = []
    warnings: List[str] = []
```

### HealthCheckMetrics

```python
class HealthCheckMetrics(BaseModel):
    """Metrics for health check endpoint monitoring."""
    endpoint: str
    response_time_ms: float
    status_code: int
    success: bool
    timestamp: datetime
    dependencies_checked: List[str] = []
```

### EnvironmentConfig

```python
class EnvironmentConfig(BaseModel):
    """Database environment configuration."""
    postgres_host: str
    postgres_db: str
    postgres_user: str
    postgres_password: str
    postgres_port: int = 5432
    
    @classmethod
    def from_env(cls) -> "EnvironmentConfig":
        """Load configuration from environment variables with POSTGRES_* prefix."""
        return cls(
            postgres_host=os.getenv("POSTGRES_HOST"),
            postgres_db=os.getenv("POSTGRES_DB"),
            postgres_user=os.getenv("POSTGRES_USER"),
            postgres_password=os.getenv("POSTGRES_PASSWORD"),
            postgres_port=int(os.getenv("POSTGRES_PORT", "5432"))
        )
```

## Correctness Properties


*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Basic Health Endpoints Database Independence

*For any* call to `/api/health/minimal` or `/api/health/simple`, the endpoint SHALL respond with HTTP 200 status without attempting database connectivity, regardless of database availability state.

**Validates: Requirements 4.1, 4.2, 4.4**

### Property 2: Health Check Response Time

*For any* call to basic health check endpoints (`/api/health/minimal`, `/api/health/simple`), the response time SHALL be less than 2000 milliseconds.

**Validates: Requirements 4.3**

### Property 3: Monitoring Alert on Slow Response

*For any* health check endpoint call where response time exceeds 2000 milliseconds, the monitoring system SHALL trigger an alert with severity "warning" or higher.

**Validates: Requirements 6.1**

### Property 4: Monitoring Failure Logging

*For any* health check endpoint failure, the monitoring system SHALL log an entry containing the endpoint name, failure reason, and timestamp.

**Validates: Requirements 6.2**

### Property 5: Database Call Detection

*For any* execution of basic health check endpoints (`/api/health/minimal`, `/api/health/simple`), if a database connection attempt is made, the monitoring system SHALL trigger an alert indicating a regression.

**Validates: Requirements 6.4**

### Property 6: Environment Variable Validation

*For any* deployment configuration, the validation system SHALL verify that all required POSTGRES_* variables (POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_PORT) are present, non-empty, and correctly prefixed, failing deployment with clear error messages if any validation fails.

**Validates: Requirements 7.1, 7.2, 7.3, 7.4**

### Property 7: Static Analysis Database Import Detection

*For any* Python source code file containing `health_minimal` or `health_simple` function definitions, if the function body contains imports or calls to database-related modules (database, db, postgres, sqlalchemy, psycopg2) or methods (execute, query, fetch), the static analyzer SHALL report a violation.

**Validates: Requirements 8.2**

## Error Handling

### Health Check Endpoint Errors

**Principle:** Basic health check endpoints should never fail due to external dependencies.

**Error Handling Strategy:**

1. **Process-Level Errors:** If the application process cannot handle HTTP requests, the endpoint will not respond (handled by ALB timeout)

2. **Internal Errors:** If an unexpected error occurs within the health check handler:
   ```python
   try:
       # Health check logic
       return HealthResponse(status="healthy", ...)
   except Exception as e:
       # Log error but still return healthy if process is running
       logger.error(f"Health check internal error: {e}")
       return HealthResponse(
           status="healthy",  # Process is still running
           checks={"process": "ok", "internal_error": str(e)}
       )
   ```

3. **Timeout Handling:** ALB configured with 5-second timeout, health endpoints must respond within 2 seconds to provide buffer

### Database-Dependent Endpoint Errors

**Principle:** Database-dependent endpoints should clearly indicate connection failures.

**Error Handling Strategy:**

```python
@router.get("/health/database")
async def health_database(db: Database = Depends(get_database)):
    try:
        await db.execute("SELECT 1")
        return HealthResponse(
            status="healthy",
            checks={"database": "connected"}
        )
    except ConnectionError as e:
        return HealthResponse(
            status="unhealthy",
            checks={"database": f"connection_error: {str(e)}"}
        ), 503
    except TimeoutError as e:
        return HealthResponse(
            status="unhealthy",
            checks={"database": f"timeout: {str(e)}"}
        ), 503
    except Exception as e:
        return HealthResponse(
            status="unhealthy",
            checks={"database": f"error: {str(e)}"}
        ), 503
```

### Validation Errors

**Principle:** Configuration validation should fail fast with actionable error messages.

**Error Handling Strategy:**

```python
def validate_environment_variables(env_vars: Dict[str, str]) -> ValidationResult:
    errors = []
    
    # Check for missing variables
    for var in REQUIRED_POSTGRES_VARS:
        if var not in env_vars:
            errors.append(
                f"Missing required environment variable: {var}. "
                f"Add this variable to your task definition with the POSTGRES_ prefix."
            )
    
    # Check for empty values
    for var in REQUIRED_POSTGRES_VARS:
        if var in env_vars and not env_vars[var].strip():
            errors.append(
                f"Environment variable {var} is empty. "
                f"Provide a non-empty value in your task definition."
            )
    
    # Check for wrong prefix
    wrong_prefix = [k for k in env_vars.keys() 
                   if k.endswith(("_HOST", "_DB", "_USER", "_PASSWORD")) 
                   and not k.startswith("POSTGRES_")]
    if wrong_prefix:
        errors.append(
            f"Found database variables without POSTGRES_ prefix: {', '.join(wrong_prefix)}. "
            f"Rename these variables to use POSTGRES_ prefix (e.g., DB_HOST → POSTGRES_HOST). "
            f"Database connectivity requires the POSTGRES_ prefix."
        )
    
    if errors:
        raise ValidationError(
            "Environment variable validation failed. "
            "Fix the following issues before deployment:\n" + 
            "\n".join(f"  - {e}" for e in errors)
        )
    
    return ValidationResult(success=True)
```

### Monitoring Alert Errors

**Principle:** Monitoring failures should not impact application functionality.

**Error Handling Strategy:**

```python
async def send_alert(self, severity: str, message: str):
    try:
        await self.alert_service.send(severity, message)
    except Exception as e:
        # Log monitoring failure but don't propagate
        logger.error(f"Failed to send alert: {e}")
        # Store alert locally for retry
        await self.store_failed_alert(severity, message)
```

## Testing Strategy

### Dual Testing Approach

This feature requires both unit tests and property-based tests to ensure comprehensive coverage:

- **Unit tests:** Verify specific examples, edge cases, and error conditions
- **Property tests:** Verify universal properties across all inputs

Together, these provide comprehensive coverage where unit tests catch concrete bugs and property tests verify general correctness.

### Property-Based Testing

**Library:** `hypothesis` (Python)

**Configuration:** Each property test runs a minimum of 100 iterations to ensure comprehensive input coverage.

**Test Tagging:** Each property test includes a comment referencing the design document property:
```python
# Feature: health-check-database-decoupling, Property 1: Basic Health Endpoints Database Independence
```

### Test Categories

#### 1. Health Endpoint Independence Tests (Property-Based)

**Property 1 Test:**
```python
from hypothesis import given, strategies as st
import pytest

# Feature: health-check-database-decoupling, Property 1: Basic Health Endpoints Database Independence
@pytest.mark.property
@given(database_state=st.sampled_from(["unavailable", "slow", "error", "timeout"]))
async def test_health_endpoints_database_independence(
    client: TestClient,
    database_state: str,
    mock_database
):
    """
    Property: Basic health endpoints respond successfully without database connectivity.
    
    For any database failure state, /api/health/minimal and /api/health/simple
    should return 200 OK without attempting database connection.
    """
    # Simulate database failure
    mock_database.set_state(database_state)
    
    # Test minimal endpoint
    response = await client.get("/api/health/minimal")
    assert response.status_code == 200
    assert "database" not in response.json()["checks"]
    
    # Test simple endpoint
    response = await client.get("/api/health/simple")
    assert response.status_code == 200
    assert "database" not in response.json()["checks"]
    
    # Verify no database connection attempts
    assert mock_database.connection_attempts == 0
```

**Property 2 Test:**
```python
# Feature: health-check-database-decoupling, Property 2: Health Check Response Time
@pytest.mark.property
@given(endpoint=st.sampled_from(["/api/health/minimal", "/api/health/simple"]))
async def test_health_check_response_time(client: TestClient, endpoint: str):
    """
    Property: Health check endpoints respond within 2 seconds.
    
    For any basic health check endpoint, response time should be < 2000ms.
    """
    start_time = time.time()
    response = await client.get(endpoint)
    response_time_ms = (time.time() - start_time) * 1000
    
    assert response.status_code == 200
    assert response_time_ms < 2000, f"Response time {response_time_ms}ms exceeded 2000ms threshold"
```

#### 2. Monitoring Tests (Property-Based)

**Property 3 Test:**
```python
# Feature: health-check-database-decoupling, Property 3: Monitoring Alert on Slow Response
@pytest.mark.property
@given(
    endpoint=st.sampled_from(["/api/health/minimal", "/api/health/simple"]),
    delay_ms=st.integers(min_value=2001, max_value=5000)
)
async def test_monitoring_alerts_on_slow_response(
    health_monitor: HealthCheckMonitor,
    mock_alert_service: MockAlertService,
    endpoint: str,
    delay_ms: int
):
    """
    Property: Monitoring system alerts on slow health check responses.
    
    For any health check response exceeding 2000ms, an alert should be triggered.
    """
    # Simulate slow endpoint
    with mock_slow_response(endpoint, delay_ms):
        await health_monitor.monitor_health_endpoint(endpoint)
    
    # Verify alert was triggered
    alerts = mock_alert_service.get_alerts()
    assert len(alerts) > 0
    assert any(
        alert.severity in ["warning", "error"] and 
        "exceeded response time threshold" in alert.message
        for alert in alerts
    )
```

**Property 4 Test:**
```python
# Feature: health-check-database-decoupling, Property 4: Monitoring Failure Logging
@pytest.mark.property
@given(
    endpoint=st.sampled_from(["/api/health/minimal", "/api/health/simple"]),
    failure_type=st.sampled_from(["timeout", "connection_error", "500_error"])
)
async def test_monitoring_logs_failures(
    health_monitor: HealthCheckMonitor,
    mock_logger: MockLogger,
    endpoint: str,
    failure_type: str
):
    """
    Property: Monitoring system logs health check failures with details.
    
    For any health check failure, a log entry should contain endpoint, reason, and timestamp.
    """
    # Simulate endpoint failure
    with mock_endpoint_failure(endpoint, failure_type):
        try:
            await health_monitor.monitor_health_endpoint(endpoint)
        except Exception:
            pass
    
    # Verify failure was logged
    logs = mock_logger.get_logs()
    assert any(
        endpoint in log.message and
        failure_type in log.message and
        log.timestamp is not None
        for log in logs
    )
```

#### 3. Validation Tests (Property-Based)

**Property 6 Test:**
```python
# Feature: health-check-database-decoupling, Property 6: Environment Variable Validation
@pytest.mark.property
@given(
    missing_vars=st.lists(
        st.sampled_from(["POSTGRES_HOST", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"]),
        min_size=0,
        max_size=4,
        unique=True
    ),
    empty_vars=st.lists(
        st.sampled_from(["POSTGRES_HOST", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"]),
        min_size=0,
        max_size=4,
        unique=True
    ),
    wrong_prefix_vars=st.lists(
        st.sampled_from(["DB_HOST", "DATABASE_NAME", "DB_USER", "DB_PASSWORD"]),
        min_size=0,
        max_size=4,
        unique=True
    )
)
def test_environment_variable_validation(
    validator: DatabaseConfigValidator,
    missing_vars: List[str],
    empty_vars: List[str],
    wrong_prefix_vars: List[str]
):
    """
    Property: Validation system catches all environment variable configuration errors.
    
    For any configuration with missing, empty, or incorrectly prefixed variables,
    validation should fail with clear error messages.
    """
    # Build test environment
    env_vars = {
        "POSTGRES_HOST": "localhost",
        "POSTGRES_DB": "testdb",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "pass",
        "POSTGRES_PORT": "5432"
    }
    
    # Remove missing vars
    for var in missing_vars:
        env_vars.pop(var, None)
    
    # Empty some vars
    for var in empty_vars:
        if var in env_vars:
            env_vars[var] = ""
    
    # Add wrong prefix vars
    for var in wrong_prefix_vars:
        env_vars[var] = "value"
    
    # Validate
    result = validator.validate_environment_variables(env_vars)
    
    # If any issues exist, validation should fail
    has_issues = len(missing_vars) > 0 or len(empty_vars) > 0 or len(wrong_prefix_vars) > 0
    
    if has_issues:
        assert not result.success
        assert len(result.errors) > 0
        
        # Verify error messages are clear
        for error in result.errors:
            assert len(error) > 20  # Error messages should be descriptive
            assert any(keyword in error.lower() for keyword in ["missing", "empty", "prefix", "variable"])
    else:
        assert result.success
```

#### 4. Static Analysis Tests (Property-Based)

**Property 7 Test:**
```python
# Feature: health-check-database-decoupling, Property 7: Static Analysis Database Import Detection
@pytest.mark.property
@given(
    has_db_import=st.booleans(),
    has_db_call=st.booleans(),
    function_name=st.sampled_from(["health_minimal", "health_simple"])
)
def test_static_analysis_detects_database_dependencies(
    analyzer: HealthCheckDependencyAnalyzer,
    has_db_import: bool,
    has_db_call: bool,
    function_name: str
):
    """
    Property: Static analyzer detects database dependencies in health check code.
    
    For any health check function with database imports or calls,
    the analyzer should report violations.
    """
    # Generate test code
    code = f"""
def {function_name}():
    '''Health check endpoint'''
    """
    
    if has_db_import:
        code += "\n    from database import db"
    
    if has_db_call:
        code += "\n    db.execute('SELECT 1')"
    
    code += "\n    return {'status': 'healthy'}"
    
    # Analyze code
    violations = analyzer.analyze_code(code)
    
    # If database dependencies exist, violations should be reported
    if has_db_import or has_db_call:
        assert len(violations) > 0
        assert any("database" in v.lower() for v in violations)
    else:
        assert len(violations) == 0
```

#### 5. Unit Tests (Specific Examples)

```python
def test_health_minimal_returns_200():
    """Unit test: /api/health/minimal returns 200 OK."""
    response = client.get("/api/health/minimal")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_health_simple_returns_200():
    """Unit test: /api/health/simple returns 200 OK."""
    response = client.get("/api/health/simple")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_health_database_fails_when_db_unavailable():
    """Unit test: /api/health/database returns 503 when database is unavailable."""
    with mock_database_unavailable():
        response = client.get("/api/health/database")
        assert response.status_code == 503
        assert response.json()["status"] == "unhealthy"

def test_validation_catches_missing_postgres_host():
    """Unit test: Validator catches missing POSTGRES_HOST."""
    env_vars = {
        "POSTGRES_DB": "testdb",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "pass"
    }
    result = validator.validate_environment_variables(env_vars)
    assert not result.success
    assert any("POSTGRES_HOST" in error for error in result.errors)

def test_validation_catches_wrong_prefix():
    """Unit test: Validator catches DB_HOST instead of POSTGRES_HOST."""
    env_vars = {
        "DB_HOST": "localhost",
        "POSTGRES_DB": "testdb",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "pass"
    }
    result = validator.validate_environment_variables(env_vars)
    assert not result.success
    assert any("prefix" in error.lower() for error in result.errors)
```

### Integration Tests

```python
@pytest.mark.integration
async def test_alb_health_check_flow():
    """Integration test: Simulate ALB health check flow."""
    # Start application
    app = create_app()
    
    # Simulate database being unavailable
    with mock_database_unavailable():
        # ALB calls health endpoint
        response = await app.test_client().get("/api/health/simple")
        
        # Should still return healthy
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        
        # Verify response time is acceptable
        assert response.elapsed.total_seconds() < 2.0

@pytest.mark.integration
async def test_deployment_validation_flow():
    """Integration test: Simulate deployment validation flow."""
    # Create task definition with wrong env vars
    task_def = {
        "environment": [
            {"name": "DB_HOST", "value": "localhost"},  # Wrong prefix
            {"name": "POSTGRES_DB", "value": "testdb"},
            {"name": "POSTGRES_USER", "value": "user"},
            {"name": "POSTGRES_PASSWORD", "value": "pass"}
        ]
    }
    
    # Run validation
    validator = DatabaseConfigValidator()
    result = validator.validate_task_definition(task_def)
    
    # Should fail with clear error
    assert not result.success
    assert any("prefix" in error.lower() for error in result.errors)
    assert any("DB_HOST" in error for error in result.errors)
```

### CI/CD Integration

All tests run automatically in the CI/CD pipeline:

```yaml
# .github/workflows/health-check-validation.yml
name: Health Check Validation

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Run property-based tests
        run: |
          pytest tests/ -m property --hypothesis-seed=random
      
      - name: Run unit tests
        run: |
          pytest tests/ -m "not property"
      
      - name: Run static analysis
        run: |
          python scripts/validate-health-check-independence.py src/multimodal_librarian/api/routers/health.py
      
      - name: Validate environment config
        run: |
          python scripts/validate-deployment-config.py
```

## Documentation Requirements

### 1. Architecture Decision Record (ADR)

**File:** `docs/architecture/adr-health-check-decoupling.md`

**Content:**
- Historical problem description
- Circular dependency explanation
- Solution rationale
- Trade-offs considered
- Implementation approach
- Monitoring strategy

### 2. Deployment Guide

**File:** `docs/deployment/environment-variables.md`

**Content:**
- Required POSTGRES_* variables
- Correct configuration examples
- Common mistakes and fixes
- Validation process
- Troubleshooting guide

### 3. Operations Runbook

**File:** `docs/operations/health-check-monitoring.md`

**Content:**
- Health check endpoint descriptions
- Monitoring dashboard setup
- Alert response procedures
- Performance baselines
- Troubleshooting steps

### 4. Developer Guide

**File:** `docs/development/health-check-guidelines.md`

**Content:**
- Health check independence principles
- Code review checklist
- Testing requirements
- Static analysis usage
- Common pitfalls to avoid

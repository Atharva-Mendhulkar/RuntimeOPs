# Bob Testing Guide

Comprehensive testing documentation for IBM Bob - Repository Intelligence Agent.

## Table of Contents

- [Overview](#overview)
- [Test Structure](#test-structure)
- [Running Tests](#running-tests)
- [Test Types](#test-types)
- [Writing Tests](#writing-tests)
- [CI/CD Integration](#cicd-integration)
- [Troubleshooting](#troubleshooting)

---

## Overview

Bob's test suite ensures system reliability, performance, and security through comprehensive testing at multiple levels:

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions and database operations
- **E2E Tests**: Test complete workflows from ingestion to query
- **Performance Tests**: Benchmark critical operations and ensure SLA compliance
- **Security Tests**: Verify authentication, authorization, and vulnerability protection
- **Chaos Tests**: Validate system resilience under failure conditions
- **Load Tests**: Simulate realistic user load patterns

### Test Coverage Goals

- **Overall Coverage**: >80%
- **Critical Paths**: >95%
- **Security Components**: 100%

---

## Test Structure

```
tests/
├── conftest.py                 # Shared fixtures and test configuration
├── __init__.py
├── unit/                       # Unit tests
│   ├── test_api.py
│   ├── test_graph.py
│   ├── test_ingestion.py
│   ├── test_parsers.py
│   ├── test_security.py
│   ├── test_storage.py
│   └── test_tools.py
├── integration/                # Integration tests
│   ├── test_agent_integration.py
│   ├── test_databases.py
│   ├── test_endpoints.py
│   ├── test_observability_integration.py
│   └── test_security_integration.py
├── e2e/                        # End-to-end tests
│   └── test_e2e_workflows.py
├── performance/                # Performance benchmarks
│   └── test_performance.py
├── security/                   # Security tests
│   ├── test_security_comprehensive.py
│   └── test_security_vulnerabilities.py
├── chaos/                      # Chaos engineering tests
│   └── test_resilience.py
├── load/                       # Load tests
│   └── locustfile.py
└── fixtures/                   # Test data
    ├── repos/
    ├── stack_traces/
    └── queries/
```

---

## Running Tests

### Prerequisites

```bash
# Install dependencies
cd bob
poetry install --with dev

# Set up test environment
export TEST_POSTGRES_HOST=localhost
export TEST_POSTGRES_PORT=5432
export TEST_NEO4J_URI=bolt://localhost:7687
export TEST_REDIS_HOST=localhost
export TEST_WEAVIATE_URL=http://localhost:8080
```

### All Tests

```bash
poetry run pytest
```

### Specific Test Suites

```bash
# Unit tests only
poetry run pytest tests/unit

# Integration tests
poetry run pytest tests/integration

# E2E tests
poetry run pytest tests/e2e

# Performance tests
poetry run pytest tests/performance

# Security tests
poetry run pytest tests/security

# Chaos tests
poetry run pytest tests/chaos
```

### By Test Markers

```bash
# Run only unit tests
poetry run pytest -m unit

# Run only integration tests
poetry run pytest -m integration

# Run only E2E tests
poetry run pytest -m e2e

# Run only performance tests
poetry run pytest -m performance

# Run only security tests
poetry run pytest -m security

# Run only chaos tests
poetry run pytest -m chaos

# Exclude slow tests
poetry run pytest -m "not slow"
```

### With Coverage

```bash
# Generate coverage report
poetry run pytest --cov=bob --cov-report=html

# View coverage report
open htmlcov/index.html

# Generate XML report (for CI)
poetry run pytest --cov=bob --cov-report=xml

# Show missing lines
poetry run pytest --cov=bob --cov-report=term-missing
```

### Parallel Execution

```bash
# Install pytest-xdist
poetry add --group dev pytest-xdist

# Run tests in parallel (4 workers)
poetry run pytest -n 4

# Run tests in parallel (auto-detect CPU count)
poetry run pytest -n auto
```

### Verbose Output

```bash
# Verbose output
poetry run pytest -v

# Very verbose output
poetry run pytest -vv

# Show print statements
poetry run pytest -s

# Show local variables on failure
poetry run pytest -l
```

---

## Test Types

### 1. Unit Tests

**Purpose**: Test individual functions and classes in isolation.

**Location**: `tests/unit/`

**Example**:
```python
def test_search_request_validation():
    """Test SearchRequest validation"""
    request = SearchRequest(
        repo_id=uuid4(),
        query="authentication middleware",
        k=10,
    )
    assert request.k == 10
    assert len(request.query) > 0
```

**Run**:
```bash
poetry run pytest tests/unit -v
```

### 2. Integration Tests

**Purpose**: Test component interactions and database operations.

**Location**: `tests/integration/`

**Requirements**: Running database services (PostgreSQL, Neo4j, Redis, Weaviate)

**Example**:
```python
async def test_neo4j_connection(test_neo4j):
    """Test Neo4j connection"""
    async with test_neo4j.session() as session:
        result = await session.run("RETURN 1 as num")
        record = await result.single()
        assert record["num"] == 1
```

**Run**:
```bash
# Start services
docker-compose up -d

# Run tests
poetry run pytest tests/integration -v
```

### 3. End-to-End Tests

**Purpose**: Test complete workflows from ingestion to query.

**Location**: `tests/e2e/`

**Example**:
```python
async def test_complete_repository_ingestion(
    test_client,
    sample_repository,
    auth_headers
):
    """Test complete repository ingestion workflow"""
    # 1. Trigger ingestion
    response = await test_client.post(
        "/api/v1/repositories/ingest",
        json={"repo_id": sample_repository["repo_id"]},
        headers=auth_headers
    )
    assert response.status_code == 202
    
    # 2. Wait for completion
    # 3. Verify data in all databases
    # 4. Test semantic search
```

**Run**:
```bash
poetry run pytest tests/e2e -v
```

### 4. Performance Tests

**Purpose**: Benchmark critical operations and ensure SLA compliance.

**Location**: `tests/performance/`

**SLA Targets**:
- Semantic search: P95 < 800ms
- Graph queries: P95 < 400ms
- File retrieval (cached): < 50ms

**Example**:
```python
async def test_semantic_search_performance(
    test_client,
    auth_headers,
    large_repository,
    performance_tracker
):
    """Test semantic search performance under load"""
    latencies = []
    for query in queries:
        start = time.time()
        response = await test_client.post("/api/v1/search", ...)
        latency = time.time() - start
        latencies.append(latency)
    
    assert mean(latencies) < 1.0  # Average < 1 second
    assert median(latencies) < 0.8  # Median < 800ms
```

**Run**:
```bash
poetry run pytest tests/performance -v
```

### 5. Security Tests

**Purpose**: Verify authentication, authorization, and vulnerability protection.

**Location**: `tests/security/`

**Coverage**:
- Authentication bypass attempts
- Authorization violations
- SQL injection
- Path traversal
- XSS attacks
- Rate limiting
- Input validation

**Example**:
```python
async def test_sql_injection_in_search_query(
    test_client,
    auth_headers,
    sql_injection_payloads
):
    """Test SQL injection attempts in search queries"""
    for payload in sql_injection_payloads:
        response = await test_client.post(
            "/api/v1/search",
            json={"query": payload, "repo_id": "test/repo"},
            headers=auth_headers
        )
        # Should not cause error, should sanitize input
        assert response.status_code in [200, 400]
```

**Run**:
```bash
poetry run pytest tests/security -v
```

### 6. Chaos Engineering Tests

**Purpose**: Validate system resilience under failure conditions.

**Location**: `tests/chaos/`

**Scenarios**:
- Database failures
- Cache failures
- Network latency
- Resource exhaustion
- Cascading failures

**Example**:
```python
async def test_postgres_failure_recovery(
    test_client,
    auth_headers,
    chaos_controller
):
    """Test recovery from PostgreSQL failure"""
    # 1. Verify healthy
    # 2. Kill PostgreSQL
    # 3. Verify graceful degradation
    # 4. Restore PostgreSQL
    # 5. Verify recovery
```

**Run**:
```bash
poetry run pytest tests/chaos -v
```

### 7. Load Tests

**Purpose**: Simulate realistic user load patterns.

**Location**: `tests/load/`

**Tool**: Locust

**Usage**:
```bash
# Web UI mode
locust -f tests/load/locustfile.py --host=http://localhost:8000

# Headless mode
locust -f tests/load/locustfile.py \
    --host=http://localhost:8000 \
    --headless \
    -u 100 \
    -r 10 \
    -t 5m \
    --html=report.html

# Specific user class
locust -f tests/load/locustfile.py \
    --host=http://localhost:8000 \
    --class-picker SearchHeavyUser
```

**Load Patterns**:
- `BobUser`: Mixed workload (default)
- `SearchHeavyUser`: Search-focused
- `GraphHeavyUser`: Graph query-focused
- `BurstUser`: Burst traffic pattern

**Load Shapes**:
- `StepLoadShape`: Gradual increase
- `SpikeLoadShape`: Sudden spikes
- `WaveLoadShape`: Sinusoidal pattern

---

## Writing Tests

### Test Structure (AAA Pattern)

```python
async def test_example(test_client, auth_headers):
    """Test description"""
    
    # Arrange: Set up test data
    test_data = {"query": "test", "repo_id": "test/repo"}
    
    # Act: Execute the operation
    response = await test_client.post(
        "/api/v1/search",
        json=test_data,
        headers=auth_headers
    )
    
    # Assert: Verify the results
    assert response.status_code == 200
    assert len(response.json()["results"]) > 0
```

### Using Fixtures

```python
@pytest.fixture
def sample_data():
    """Provide sample test data"""
    return {"key": "value"}

async def test_with_fixture(sample_data):
    """Test using fixture"""
    assert sample_data["key"] == "value"
```

### Async Tests

```python
import pytest

@pytest.mark.asyncio
async def test_async_operation(test_client):
    """Test async operation"""
    response = await test_client.get("/api/v1/health")
    assert response.status_code == 200
```

### Parametrized Tests

```python
@pytest.mark.parametrize("input,expected", [
    ("test1", "result1"),
    ("test2", "result2"),
    ("test3", "result3"),
])
def test_parametrized(input, expected):
    """Test with multiple inputs"""
    result = process(input)
    assert result == expected
```

### Mocking

```python
from unittest.mock import Mock, patch

def test_with_mock(mocker):
    """Test with mocked dependency"""
    mock_service = mocker.patch("bob.service.ExternalService")
    mock_service.return_value.fetch.return_value = "mocked_data"
    
    result = my_function()
    assert result == "mocked_data"
```

---

## CI/CD Integration

### GitHub Actions Workflow

Tests run automatically on:
- Push to `main` or `develop` branches
- Pull requests
- Daily schedule (2 AM UTC)

### Workflow Jobs

1. **Unit Tests**: Fast, no external dependencies
2. **Integration Tests**: With database services
3. **E2E Tests**: Full system tests
4. **Security Tests**: Security scans and vulnerability tests
5. **Performance Tests**: On schedule or with `[perf]` in commit message
6. **Code Quality**: Linting and type checking

### Viewing Results

```bash
# Check workflow status
gh run list

# View specific run
gh run view <run-id>

# Download artifacts
gh run download <run-id>
```

### Coverage Reports

Coverage reports are automatically uploaded to Codecov:
- View at: https://codecov.io/gh/your-org/bob
- Badge: `[![codecov](https://codecov.io/gh/your-org/bob/branch/main/graph/badge.svg)](https://codecov.io/gh/your-org/bob)`

---

## Troubleshooting

### Common Issues

#### 1. Database Connection Errors

**Problem**: Tests fail with connection errors

**Solution**:
```bash
# Check services are running
docker-compose ps

# Restart services
docker-compose restart

# Check logs
docker-compose logs postgres
docker-compose logs neo4j
```

#### 2. Import Errors

**Problem**: `ModuleNotFoundError`

**Solution**:
```bash
# Reinstall dependencies
poetry install --with dev

# Verify installation
poetry run python -c "import bob"
```

#### 3. Async Test Failures

**Problem**: `RuntimeError: Event loop is closed`

**Solution**:
```python
# Ensure pytest-asyncio is installed
poetry add --group dev pytest-asyncio

# Use correct marker
@pytest.mark.asyncio
async def test_async():
    pass
```

#### 4. Fixture Not Found

**Problem**: `fixture 'test_client' not found`

**Solution**:
```bash
# Ensure conftest.py is in the right location
ls tests/conftest.py

# Check fixture is defined
grep "def test_client" tests/conftest.py
```

#### 5. Slow Tests

**Problem**: Tests take too long

**Solution**:
```bash
# Run only fast tests
poetry run pytest -m "not slow"

# Use parallel execution
poetry run pytest -n auto

# Profile slow tests
poetry run pytest --durations=10
```

### Debug Mode

```bash
# Drop into debugger on failure
poetry run pytest --pdb

# Drop into debugger on first failure
poetry run pytest -x --pdb

# Show local variables
poetry run pytest -l

# Verbose output
poetry run pytest -vv
```

### Test Data Cleanup

```bash
# Clean test databases
docker-compose down -v

# Remove test artifacts
rm -rf htmlcov/ .coverage .pytest_cache/

# Fresh start
docker-compose up -d
poetry run pytest
```

---

## Best Practices

### 1. Test Isolation

- Each test should be independent
- Use fixtures for setup/teardown
- Clean up test data after each test

### 2. Test Naming

- Use descriptive names: `test_<what>_<condition>_<expected>`
- Example: `test_search_with_invalid_token_returns_401`

### 3. Assertions

- Use specific assertions
- Include helpful error messages
- Test both success and failure cases

### 4. Test Data

- Use fixtures for reusable test data
- Keep test data minimal
- Use factories for complex objects

### 5. Performance

- Mark slow tests with `@pytest.mark.slow`
- Use mocks for external services
- Run fast tests frequently

### 6. Documentation

- Add docstrings to test functions
- Document test scenarios
- Explain complex test logic

---

## Metrics and Reporting

### Coverage Metrics

```bash
# Generate coverage report
poetry run pytest --cov=bob --cov-report=term-missing

# View HTML report
poetry run pytest --cov=bob --cov-report=html
open htmlcov/index.html
```

### Performance Metrics

Performance tests track:
- Query latency (mean, median, P95, P99)
- Throughput (requests/second)
- Resource usage (memory, CPU)

### Test Execution Time

```bash
# Show slowest tests
poetry run pytest --durations=10

# Show all test durations
poetry run pytest --durations=0
```

---

## Additional Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Locust Documentation](https://docs.locust.io/)
- [Codecov Documentation](https://docs.codecov.com/)

---

## Support

For questions or issues:
- Create an issue in the repository
- Contact the RuntimeOps team
- Check the troubleshooting section above

---

**Made with Bob** 🤖